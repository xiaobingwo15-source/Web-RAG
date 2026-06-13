from __future__ import annotations

from typing import Any


ZERO_SOURCE_WARNING_RATE = 0.10
WEAK_MATCH_WARNING_RATE = 0.10
GROUNDEDNESS_WARNING_RATE = 0.10
FEEDBACK_WARNING_RATE = 0.10
CRITICAL_RATE = 0.25
WEAK_TOP_SCORE_THRESHOLD = 0.40
LATENCY_WARNING_MS = 3000
LATENCY_CRITICAL_MS = 6000
MAX_EXAMPLES_PER_SIGNAL = 5


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


def _log_example(row: dict, value: Any, reason: str) -> dict:
    diagnostics = row.get("diagnostics") or {}
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
            "fallback_reason": diagnostics.get("fallback_reason"),
            "web_result_count": diagnostics.get("web_result_count"),
            "channel": diagnostics.get("channel"),
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


def _is_fallback_log(row: dict) -> bool:
    diagnostics = row.get("diagnostics") or {}
    quality = str(row.get("retrieval_quality") or "")
    return (
        "fallback" in quality
        or bool(diagnostics.get("fallback_reason"))
        or _safe_int(diagnostics.get("web_result_count")) > 0
    )


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
        if _safe_int(row.get("source_count")) == 0 or _safe_int(row.get("chunk_count")) == 0
    ]
    weak_match_logs = [
        row for row in retrieval_logs
        if _safe_int(row.get("source_count")) > 0
        and (score := _safe_float(row.get("top_score"))) is not None
        and score < WEAK_TOP_SCORE_THRESHOLD
    ]
    groundedness_logs = [row for row in retrieval_logs if bool(row.get("groundedness_flag"))]

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
    fallback_logs = [row for row in retrieval_logs if _is_fallback_log(row)]
    feedback_rate = _rate(len(thumbs_down_rows), feedback_total)
    fallback_rate = _rate(len(fallback_logs), retrieval_total)
    feedback_fallback_rate = max(feedback_rate, fallback_rate)

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
            description=f"Retrieved sources whose top score is below {WEAK_TOP_SCORE_THRESHOLD:.2f}.",
            status=_rate_status(_rate(len(weak_match_logs), retrieval_total), WEAK_MATCH_WARNING_RATE),
            count=len(weak_match_logs),
            rate=_rate(len(weak_match_logs), retrieval_total),
            threshold=WEAK_TOP_SCORE_THRESHOLD,
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
            signal_id="feedback_fallback",
            label="Feedback & Fallback",
            description="Negative feedback and responses that needed fallback context.",
            status=_rate_status(feedback_fallback_rate, FEEDBACK_WARNING_RATE),
            count=len(thumbs_down_rows) + len(fallback_logs),
            rate=feedback_fallback_rate,
            threshold=FEEDBACK_WARNING_RATE,
            examples=[
                *[_feedback_example(row) for row in thumbs_down_rows],
                *[_log_example(row, row.get("retrieval_quality"), "fallback_used") for row in fallback_logs],
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
            "fallback_count": len(fallback_logs),
            "latency_sample_count": len(duration_values),
            "latency_p95_ms": latency_p95,
        },
        "signals": signals,
    }
