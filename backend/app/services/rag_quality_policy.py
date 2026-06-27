from __future__ import annotations

from collections import defaultdict
from typing import Any


ZERO_SOURCE_WARNING_RATE = 0.10
WEAK_MATCH_WARNING_RATE = 0.10
GROUNDEDNESS_WARNING_RATE = 0.10
FEEDBACK_WARNING_RATE = 0.10
WEB_FALLBACK_WARNING_RATE = 0.10
CRITICAL_RATE = 0.25
LATENCY_WARNING_MS = 3000
LATENCY_CRITICAL_MS = 6000
MAX_EXAMPLES_PER_SIGNAL = 5
STALENESS_DEGRADATION_RATIO = 0.50
STALENESS_ABSOLUTE_THRESHOLD = 0.30
STALENESS_MIN_LOGS = 10
SCORE_FAMILY_THRESHOLDS = {
    "cohere_rerank": {"weak": 0.40, "near_random": 0.15},
    "vector_similarity": {"weak": 0.40, "near_random": 0.15},
    "rrf_fallback": {"weak": 0.015, "near_random": 0.010},
}


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _rate(count: int, denominator: int) -> float:
    return count / denominator if denominator > 0 else 0.0


def _rate_status(rate: float, warning: float) -> str:
    if rate >= CRITICAL_RATE:
        return "critical"
    if rate >= warning:
        return "watch"
    return "ok"


def _latency_status(p95_ms: int | None) -> str:
    if p95_ms is None:
        return "ok"
    if p95_ms >= LATENCY_CRITICAL_MS:
        return "critical"
    if p95_ms >= LATENCY_WARNING_MS:
        return "watch"
    return "ok"


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return ordered[index]


def _staleness_status(recent_avg: float, older_avg: float) -> str | None:
    if older_avg <= 0:
        return None
    ratio = recent_avg / older_avg
    if ratio < STALENESS_DEGRADATION_RATIO and recent_avg < STALENESS_ABSOLUTE_THRESHOLD:
        return "critical"
    if ratio < STALENESS_DEGRADATION_RATIO:
        return "watch"
    return None


def _diagnostics(row: dict) -> dict:
    return row.get("diagnostics") or {}


def _score_family(row: dict) -> str:
    diagnostics = _diagnostics(row)
    if diagnostics.get("score_family"):
        return str(diagnostics["score_family"])
    sources = row.get("sources") or []
    if sources and isinstance(sources[0], dict) and sources[0].get("score_family"):
        return str(sources[0]["score_family"])
    mode = str(row.get("retrieval_mode") or "")
    if mode == "vector":
        return "vector_similarity"
    if mode == "fts":
        return "fts_rank"
    return "unknown"


def _channel(row: dict) -> str:
    channel = str(_diagnostics(row).get("channel") or "unknown")
    return channel if channel in {"authenticated", "widget"} else "unknown"


def _threshold(row: dict, threshold_name: str) -> float | None:
    thresholds = SCORE_FAMILY_THRESHOLDS.get(_score_family(row))
    if not thresholds:
        return None
    return thresholds[threshold_name]


def _is_zero_source(row: dict) -> bool:
    return _safe_int(row.get("source_count")) == 0 or _safe_int(row.get("chunk_count")) == 0


def _is_weak_match(row: dict) -> bool:
    threshold = _threshold(row, "weak")
    score = _safe_float(row.get("top_score"))
    return _safe_int(row.get("source_count")) > 0 and threshold is not None and score is not None and score < threshold


def _is_near_random(row: dict) -> bool:
    threshold = _threshold(row, "near_random")
    score = _safe_float(row.get("top_score"))
    return _safe_int(row.get("source_count")) > 0 and threshold is not None and score is not None and score < threshold


def _is_groundedness_flag(row: dict) -> bool:
    return bool(row.get("groundedness_flag")) or row.get("grounding_status") in {"low_confidence", "ungrounded"}


def _is_web_fallback_log(row: dict) -> bool:
    diagnostics = _diagnostics(row)
    quality = str(row.get("retrieval_quality") or "")
    return (
        "web_fallback" in quality
        or bool(diagnostics.get("used_web_fallback"))
        or _safe_int(diagnostics.get("web_result_count")) > 0
    )


def _is_widget_policy_violation(row: dict) -> bool:
    diagnostics = _diagnostics(row)
    return _channel(row) == "widget" and (
        bool(diagnostics.get("web_fallback_allowed"))
        or bool(diagnostics.get("used_web_fallback"))
        or _safe_int(diagnostics.get("web_result_count")) > 0
    )


def _log_example(row: dict, value: Any, reason: str) -> dict:
    diagnostics = _diagnostics(row)
    return {
        "id": row.get("id"),
        "query": row.get("query"),
        "created_at": row.get("created_at"),
        "retrieval_mode": row.get("retrieval_mode"),
        "value": value,
        "reason": reason,
        "details": {
            "source_count": row.get("source_count"),
            "chunk_count": row.get("chunk_count"),
            "top_score": row.get("top_score"),
            "duration_ms": row.get("duration_ms"),
            "retrieval_quality": row.get("retrieval_quality"),
            "thread_id": row.get("thread_id"),
            "answer_message_id": row.get("answer_message_id"),
            "fallback_reason": diagnostics.get("fallback_reason"),
            "web_result_count": diagnostics.get("web_result_count"),
            "web_fallback_allowed": diagnostics.get("web_fallback_allowed"),
            "used_web_fallback": diagnostics.get("used_web_fallback"),
            "channel": _channel(row),
            "score_family": _score_family(row),
            "stage_timings_ms": diagnostics.get("stage_timings_ms"),
            "top_fused_score": diagnostics.get("top_fused_score"),
            "query_type": diagnostics.get("query_type"),
            "cache_hit": diagnostics.get("cache_hit"),
        },
    }


def _feedback_example(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "query": row.get("comment") or "Thumbs-down feedback",
        "created_at": row.get("created_at"),
        "retrieval_mode": "feedback",
        "value": row.get("rating"),
        "reason": "negative_feedback",
        "details": {
            "thread_id": row.get("thread_id"),
            "message_id": row.get("message_id"),
            "client_session_id": row.get("client_session_id"),
        },
    }


def _signal(
    *,
    signal_id: str,
    label: str,
    description: str,
    status: str,
    count: int,
    rate: float,
    threshold: float | int,
    examples: list[dict],
    value: float | int | None = None,
) -> dict:
    payload = {
        "id": signal_id,
        "label": label,
        "description": description,
        "status": status,
        "count": count,
        "rate": round(rate, 4),
        "threshold": threshold,
        "examples": examples[:MAX_EXAMPLES_PER_SIGNAL],
    }
    if value is not None:
        payload["value"] = value
    return payload


def _channel_breakdown(retrieval_logs: list[dict], weak_match_logs: list[dict], web_fallback_logs: list[dict]) -> dict:
    weak_ids = {row.get("id") for row in weak_match_logs}
    fallback_ids = {row.get("id") for row in web_fallback_logs}
    grouped: dict[str, dict] = {
        "authenticated": {"durations": []},
        "widget": {"durations": []},
        "unknown": {"durations": []},
    }
    for row in retrieval_logs:
        channel = _channel(row)
        bucket = grouped.setdefault(channel, {"durations": []})
        bucket["retrieval_count"] = _safe_int(bucket.get("retrieval_count")) + 1
        bucket["zero_source_count"] = _safe_int(bucket.get("zero_source_count")) + int(_is_zero_source(row))
        bucket["weak_source_count"] = _safe_int(bucket.get("weak_source_count")) + int(row.get("id") in weak_ids)
        bucket["groundedness_flag_count"] = _safe_int(bucket.get("groundedness_flag_count")) + int(_is_groundedness_flag(row))
        bucket["fallback_count"] = _safe_int(bucket.get("fallback_count")) + int(row.get("id") in fallback_ids)
        if row.get("duration_ms") is not None:
            bucket["durations"].append(_safe_int(row.get("duration_ms")))

    breakdown = {}
    for channel, values in grouped.items():
        durations = values.pop("durations", [])
        breakdown[channel] = {
            "retrieval_count": _safe_int(values.get("retrieval_count")),
            "zero_source_count": _safe_int(values.get("zero_source_count")),
            "weak_source_count": _safe_int(values.get("weak_source_count")),
            "groundedness_flag_count": _safe_int(values.get("groundedness_flag_count")),
            "fallback_count": _safe_int(values.get("fallback_count")),
            "latency_p95_ms": _percentile(durations, 0.95),
        }
    return breakdown


def _family_staleness(retrieval_logs: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in retrieval_logs:
        family = _score_family(row)
        if family not in SCORE_FAMILY_THRESHOLDS:
            continue
        if _safe_float(row.get("top_score")) is None:
            continue
        grouped[family].append(row)

    best: dict | None = None
    status_rank = {"ok": 0, "watch": 1, "critical": 2}
    for family, rows in grouped.items():
        sorted_rows = sorted(rows, key=lambda r: r.get("created_at") or "")
        if len(sorted_rows) < STALENESS_MIN_LOGS:
            continue
        half = len(sorted_rows) // 2
        older_rows = sorted_rows[:half]
        recent_rows = sorted_rows[half:]
        older_scores = [_safe_float(row.get("top_score")) for row in older_rows]
        recent_scores = [_safe_float(row.get("top_score")) for row in recent_rows]
        older = [score for score in older_scores if score is not None]
        recent = [score for score in recent_scores if score is not None]
        older_avg = sum(older) / len(older) if older else 0.0
        recent_avg = sum(recent) / len(recent) if recent else 0.0
        ratio = recent_avg / older_avg if older_avg > 0 else 1.0
        status = _staleness_status(recent_avg, older_avg) or "ok"
        degraded = [
            row for row in recent_rows
            if older_avg > 0
            and (score := _safe_float(row.get("top_score"))) is not None
            and score < older_avg * STALENESS_DEGRADATION_RATIO
        ]
        candidate = {
            "family": family,
            "status": status,
            "ratio": ratio,
            "older_avg": older_avg,
            "recent_avg": recent_avg,
            "recent_count": len(recent),
            "degraded_logs": degraded,
        }
        if best is None:
            best = candidate
            continue
        if status_rank[status] > status_rank[best["status"]] or (
            status_rank[status] == status_rank[best["status"]] and ratio < best["ratio"]
        ):
            best = candidate

    return best or {
        "family": None,
        "status": "ok",
        "ratio": 1.0,
        "older_avg": 0.0,
        "recent_avg": 0.0,
        "recent_count": 0,
        "degraded_logs": [],
    }


def build_rag_quality_signals(
    *,
    retrieval_logs: list[dict],
    feedback_rows: list[dict],
    window_hours: int = 168,
    limit: int = 50,
) -> dict:
    retrieval_total = len(retrieval_logs)
    feedback_total = len(feedback_rows)

    zero_source_logs = [
        row for row in retrieval_logs
        if _is_zero_source(row)
    ]
    weak_match_logs = [
        row for row in retrieval_logs
        if _is_weak_match(row)
    ]
    near_random_logs = [
        row for row in retrieval_logs
        if _is_near_random(row)
    ]

    staleness = _family_staleness(retrieval_logs)
    staleness_degraded_logs = staleness["degraded_logs"]
    staleness_ratio = staleness["ratio"]

    groundedness_logs = [
        row for row in retrieval_logs
        if _is_groundedness_flag(row)
    ]

    duration_values = [
        _safe_int(row.get("duration_ms"))
        for row in retrieval_logs
        if row.get("duration_ms") is not None
    ]
    slow_logs = [
        row for row in retrieval_logs
        if _safe_int(row.get("duration_ms")) >= LATENCY_WARNING_MS
    ]
    latency_p95 = _percentile(duration_values, 0.95)

    thumbs_down_rows = [row for row in feedback_rows if _safe_int(row.get("rating")) == -1]
    web_fallback_logs = [row for row in retrieval_logs if _is_web_fallback_log(row)]
    widget_policy_logs = [row for row in retrieval_logs if _is_widget_policy_violation(row)]
    feedback_rate = _rate(len(thumbs_down_rows), feedback_total)
    web_fallback_rate = _rate(len(web_fallback_logs), retrieval_total)
    channel_breakdown = _channel_breakdown(retrieval_logs, weak_match_logs, web_fallback_logs)

    signals = [
        _signal(
            signal_id="zero_sources",
            label="No Sources",
            description="Queries that returned no document sources or chunks.",
            status=_rate_status(_rate(len(zero_source_logs), retrieval_total), ZERO_SOURCE_WARNING_RATE),
            count=len(zero_source_logs),
            rate=_rate(len(zero_source_logs), retrieval_total),
            threshold=ZERO_SOURCE_WARNING_RATE,
            examples=[
                _log_example(row, row.get("source_count"), "zero_sources")
                for row in zero_source_logs
            ],
        ),
        _signal(
            signal_id="weak_sources",
            label="Weak Sources",
            description=f"Retrieved sources below their score-family threshold. Near-random matches: {len(near_random_logs)}.",
            status=_rate_status(_rate(len(weak_match_logs), retrieval_total), WEAK_MATCH_WARNING_RATE),
            count=len(weak_match_logs),
            rate=_rate(len(weak_match_logs), retrieval_total),
            threshold=WEAK_MATCH_WARNING_RATE,
            examples=[
                _log_example(row, row.get("top_score"), "weak_top_score")
                for row in weak_match_logs
            ],
        ),
        _signal(
            signal_id="groundedness",
            label="Grounding",
            description="Answers marked as not fully grounded in retrieved context.",
            status=_rate_status(_rate(len(groundedness_logs), retrieval_total), GROUNDEDNESS_WARNING_RATE),
            count=len(groundedness_logs),
            rate=_rate(len(groundedness_logs), retrieval_total),
            threshold=GROUNDEDNESS_WARNING_RATE,
            examples=[
                _log_example(row, row.get("groundedness_score"), "groundedness_flag")
                for row in groundedness_logs
            ],
        ),
        _signal(
            signal_id="completion_latency",
            label="Completion Latency",
            description="Retrieval completion latency based on stored retrieval duration.",
            status=_latency_status(latency_p95),
            count=len(slow_logs),
            rate=_rate(len(slow_logs), len(duration_values)),
            threshold=LATENCY_WARNING_MS,
            value=latency_p95,
            examples=[
                _log_example(row, row.get("duration_ms"), "slow_retrieval")
                for row in sorted(slow_logs, key=lambda item: _safe_int(item.get("duration_ms")), reverse=True)
            ],
        ),
        _signal(
            signal_id="negative_feedback",
            label="Negative Feedback",
            description="Thumbs-down feedback submitted by users or widget visitors.",
            status=_rate_status(feedback_rate, FEEDBACK_WARNING_RATE),
            count=len(thumbs_down_rows),
            rate=feedback_rate,
            threshold=FEEDBACK_WARNING_RATE,
            examples=[
                _feedback_example(row) for row in thumbs_down_rows
            ],
        ),
        _signal(
            signal_id="web_fallback",
            label="Web Fallback",
            description="Responses that used web results or web-fallback context.",
            status=_rate_status(web_fallback_rate, WEB_FALLBACK_WARNING_RATE),
            count=len(web_fallback_logs),
            rate=web_fallback_rate,
            threshold=WEB_FALLBACK_WARNING_RATE,
            examples=[
                _log_example(row, row.get("retrieval_quality"), "web_fallback_used")
                for row in web_fallback_logs
            ],
        ),
        _signal(
            signal_id="widget_policy_violation",
            label="Widget Policy",
            description="Widget retrievals must not allow or use web fallback.",
            status="critical" if widget_policy_logs else "ok",
            count=len(widget_policy_logs),
            rate=_rate(len(widget_policy_logs), retrieval_total),
            threshold=0,
            examples=[
                _log_example(row, row.get("retrieval_quality"), "widget_web_fallback_policy")
                for row in widget_policy_logs
            ],
        ),
        _signal(
            signal_id="data_staleness",
            label="Data Staleness",
            description=(
                f"Retrieval quality degradation over time for comparable score family "
                f"{staleness['family'] or 'n/a'}. "
                f"Recent avg top_score: {staleness['recent_avg']:.3f} vs older avg: {staleness['older_avg']:.3f} "
                f"(ratio: {staleness_ratio:.2f})."
            ),
            status=staleness["status"],
            count=len(staleness_degraded_logs),
            rate=_rate(len(staleness_degraded_logs), max(staleness["recent_count"], 1)),
            threshold=STALENESS_DEGRADATION_RATIO,
            value=round(staleness_ratio, 4),
            examples=[
                _log_example(row, row.get("top_score"), "staleness_degradation")
                for row in staleness_degraded_logs
            ],
        ),
    ]

    return {
        "window_hours": window_hours,
        "limit": limit,
        "totals": {
            "retrieval_count": retrieval_total,
            "feedback_count": feedback_total,
            "thumbs_down_count": len(thumbs_down_rows),
            "zero_source_count": len(zero_source_logs),
            "weak_source_count": len(weak_match_logs),
            "groundedness_flag_count": len(groundedness_logs),
            "fallback_count": len(web_fallback_logs),
            "near_random_count": len(near_random_logs),
            "staleness_ratio": round(staleness_ratio, 4),
            "staleness_score_family": staleness["family"],
            "channel_breakdown": channel_breakdown,
            "latency_sample_count": len(duration_values),
            "latency_p95_ms": latency_p95,
        },
        "signals": signals,
    }
