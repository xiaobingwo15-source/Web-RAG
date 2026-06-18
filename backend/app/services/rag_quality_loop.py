from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime
from typing import Any

from app.services import database

logger = logging.getLogger(__name__)

QUALITY_LOOP_TAG = "quality-loop"
THUMBS_DOWN_SOURCE = "thumbs_down_feedback"
FALLBACK_SOURCE = "fallback_retrieval"
DEFAULT_WINDOW_HOURS = 168
DEFAULT_LIMIT = 50
FALLBACK_GROUP_LIMIT = 20
FALLBACK_MIN_EVENTS = 2
MAX_LOGS_PER_DRAFT = 5
MAX_SOURCES_PER_LOG = 5
MAX_CHUNKS_PER_LOG = 3
MAX_TEXT_CHARS = 1200
MAX_ANSWER_CHARS = 4000
AUTO_PROMOTE_MIN_SIGNALS = 2


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _truncate(value: Any, max_chars: int = MAX_TEXT_CHARS) -> str | None:
    if value is None:
        return None
    text = str(value)
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars - 3].rstrip()}..."


def _safe_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe_tags(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for tag in tags:
        cleaned = re.sub(r"\s+", "-", str(tag or "").strip().lower())
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            unique.append(cleaned)
    return unique


def _normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", (query or "").casefold()).strip()


def _source_ref_for_fallback_query(normalized_query: str) -> str:
    digest = hashlib.sha256(normalized_query.encode("utf-8")).hexdigest()[:16]
    return f"fallback:{digest}"


def _compact_source(source: dict) -> dict:
    return {
        "document_id": source.get("document_id"),
        "chunk_id": source.get("chunk_id"),
        "filename": source.get("filename"),
        "score": _safe_float(source.get("score")),
        "retrieval_mode": source.get("retrieval_mode"),
        "snippet": _truncate(source.get("snippet")),
        "content": _truncate(source.get("content")),
    }


def _compact_log(log: dict) -> dict:
    return {
        "id": log.get("id"),
        "query": log.get("query"),
        "retrieval_mode": log.get("retrieval_mode"),
        "created_at": log.get("created_at"),
        "chunk_count": _safe_int(log.get("chunk_count")),
        "source_count": _safe_int(log.get("source_count")),
        "top_score": _safe_float(log.get("top_score")),
        "duration_ms": _safe_int(log.get("duration_ms")) if log.get("duration_ms") is not None else None,
        "answer_message_id": log.get("answer_message_id"),
        "groundedness_score": _safe_float(log.get("groundedness_score")),
        "groundedness_flag": bool(log.get("groundedness_flag")),
        "grounding_status": log.get("grounding_status") or "not_checked",
        "retrieval_quality": log.get("retrieval_quality"),
        "diagnostics": log.get("diagnostics") or {},
        "sources": [
            _compact_source(source)
            for source in (log.get("sources") or [])[:MAX_SOURCES_PER_LOG]
            if isinstance(source, dict)
        ],
        "chunks": [
            _truncate(chunk)
            for chunk in (log.get("chunks") or [])[:MAX_CHUNKS_PER_LOG]
            if chunk
        ],
    }


def _retrieval_tags(logs: list[dict]) -> list[str]:
    tags = [QUALITY_LOOP_TAG]
    qualities = [str(log.get("retrieval_quality") or "") for log in logs]
    modes = [str(log.get("retrieval_mode") or "") for log in logs]
    if any("fallback" in quality for quality in qualities):
        tags.append("fallback")
    if any(_safe_int(log.get("source_count")) == 0 for log in logs):
        tags.append("no-sources")
    for mode in modes:
        if mode:
            tags.append(f"retrieval-{mode}")
    return _dedupe_tags(tags)


def _feedback_question(item: dict) -> str:
    logs = item.get("retrieval_logs") or []
    return (
        str(item.get("question") or "").strip()
        or str(logs[0].get("query") if logs else "").strip()
        or str(item.get("thread_title") or "").strip()
        or "Review thumbs-down feedback"
    )


def _feedback_payload(item: dict) -> dict | None:
    feedback_id = item.get("feedback_id")
    if not feedback_id:
        return None
    logs = item.get("retrieval_logs") or []
    compact_logs = [_compact_log(log) for log in logs[:MAX_LOGS_PER_DRAFT]]
    metadata = {
        "source": THUMBS_DOWN_SOURCE,
        "promoted_at": _now_iso(),
        "feedback": {
            "id": feedback_id,
            "created_at": item.get("feedback_created_at"),
            "rating": item.get("rating"),
            "comment": item.get("feedback_comment"),
            "client_email": item.get("client_email"),
        },
        "conversation": {
            "thread_id": item.get("thread_id"),
            "thread_title": item.get("thread_title"),
            "question_message_id": item.get("question_message_id"),
            "answer_message_id": item.get("resolved_message_id") or item.get("message_id"),
        },
        "answer": {
            "created_at": item.get("answer_created_at"),
            "content": _truncate(item.get("answer"), MAX_ANSWER_CHARS),
        },
        "retrieval": {
            "summary": item.get("summary") or {},
            "logs": compact_logs,
        },
    }
    return {
        "question": _feedback_question(item),
        "expected_facts": [],
        "expected_answer": None,
        "expected_document_id": None,
        "tags": _dedupe_tags([QUALITY_LOOP_TAG, "thumbs-down", *_retrieval_tags(logs)]),
        "enabled": False,
        "status": "draft",
        "source_type": THUMBS_DOWN_SOURCE,
        "source_ref_id": str(feedback_id),
        "retrieval_metadata": metadata,
    }


def _is_fallback_log(log: dict) -> bool:
    diagnostics = log.get("diagnostics") or {}
    quality = str(log.get("retrieval_quality") or "").casefold()
    return (
        "fallback" in quality
        or bool(diagnostics.get("fallback_reason"))
        or _safe_int(diagnostics.get("web_result_count")) > 0
    )


def _is_heavy_fallback_group(logs: list[dict]) -> bool:
    if len(logs) >= FALLBACK_MIN_EVENTS:
        return True
    return any(_safe_int(log.get("source_count")) == 0 for log in logs)


def _fallback_payload(normalized_query: str, logs: list[dict]) -> dict | None:
    if not normalized_query or not logs:
        return None
    sorted_logs = sorted(logs, key=lambda log: str(log.get("created_at") or ""), reverse=True)
    if not _is_heavy_fallback_group(sorted_logs):
        return None
    primary = sorted_logs[0]
    compact_logs = [_compact_log(log) for log in sorted_logs[:MAX_LOGS_PER_DRAFT]]
    created_values = [str(log.get("created_at") or "") for log in sorted_logs if log.get("created_at")]
    metadata = {
        "source": FALLBACK_SOURCE,
        "promoted_at": _now_iso(),
        "fallback": {
            "normalized_query": normalized_query,
            "fallback_count": len(sorted_logs),
            "retrieval_log_ids": [log.get("id") for log in sorted_logs if log.get("id")],
            "first_seen_at": min(created_values) if created_values else None,
            "last_seen_at": max(created_values) if created_values else None,
        },
        "retrieval": {
            "summary": {
                "retrieval_count": len(sorted_logs),
                "source_count": sum(_safe_int(log.get("source_count")) for log in sorted_logs),
                "chunk_count": sum(_safe_int(log.get("chunk_count")) for log in sorted_logs),
                "top_score": max(
                    [score for score in (_safe_float(log.get("top_score")) for log in sorted_logs) if score is not None],
                    default=None,
                ),
                "zero_source": any(_safe_int(log.get("source_count")) == 0 for log in sorted_logs),
            },
            "logs": compact_logs,
        },
    }
    return {
        "question": str(primary.get("query") or normalized_query).strip() or normalized_query,
        "expected_facts": [],
        "expected_answer": None,
        "expected_document_id": None,
        "tags": _dedupe_tags([QUALITY_LOOP_TAG, "fallback-heavy", *_retrieval_tags(sorted_logs)]),
        "enabled": False,
        "status": "draft",
        "source_type": FALLBACK_SOURCE,
        "source_ref_id": _source_ref_for_fallback_query(normalized_query),
        "retrieval_metadata": metadata,
    }


def _fallback_payloads(retrieval_logs: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for log in retrieval_logs:
        if not _is_fallback_log(log):
            continue
        normalized = _normalize_query(str(log.get("query") or ""))
        if not normalized:
            continue
        grouped.setdefault(normalized, []).append(log)

    payloads = []
    for normalized, logs in grouped.items():
        payload = _fallback_payload(normalized, logs)
        if payload:
            payloads.append(payload)
    return sorted(
        payloads,
        key=lambda payload: str(payload["retrieval_metadata"]["fallback"].get("last_seen_at") or ""),
        reverse=True,
    )[:FALLBACK_GROUP_LIMIT]


def _existing_quality_sources(tenant_id: str) -> set[tuple[str, str]]:
    existing: set[tuple[str, str]] = set()
    for case in database.list_rag_eval_cases(tenant_id):
        source_type = case.get("source_type")
        source_ref_id = case.get("source_ref_id")
        if source_type and source_ref_id:
            existing.add((str(source_type), str(source_ref_id)))
    return existing


def _existing_query_index(tenant_id: str) -> dict[str, str]:
    """Build a normalized-query → case-id index for duplicate detection."""
    index: dict[str, str] = {}
    for case in database.list_rag_eval_cases(tenant_id):
        question = _normalize_query(str(case.get("question") or ""))
        if question and question not in index:
            index[question] = str(case.get("id") or "")
    return index


def _has_similar_case(normalized_query: str, query_index: dict[str, str]) -> bool:
    """Check if a similar case already exists by normalized query match."""
    if not normalized_query:
        return False
    return normalized_query in query_index


def _count_negative_signals(payload: dict) -> int:
    """Count distinct negative feedback signals for a draft payload."""
    source_type = str(payload.get("source_type") or "")
    metadata = payload.get("retrieval_metadata") or {}
    if source_type == THUMBS_DOWN_SOURCE:
        return 1
    if source_type == FALLBACK_SOURCE:
        return _safe_int((metadata.get("fallback") or {}).get("fallback_count"))
    return 1


def _auto_promote_case(tenant_id: str, case: dict, reason: str) -> dict | None:
    """Promote a draft eval case to active and log the promotion."""
    case_id = str(case.get("id") or "")
    if not case_id:
        return None
    promoted = database.update_rag_eval_case(
        tenant_id,
        case_id,
        {"enabled": True, "status": "active"},
    )
    if promoted:
        logger.info(
            "Auto-promoted quality-loop eval case to active",
            extra={
                "tenant_id": tenant_id,
                "case_id": case_id,
                "reason": reason,
                "question": (case.get("question") or "")[:200],
                "source_type": case.get("source_type"),
                "source_ref_id": case.get("source_ref_id"),
            },
        )
    return promoted


def sync_quality_loop_eval_drafts(
    tenant_id: str,
    window_hours: int = DEFAULT_WINDOW_HOURS,
    limit: int = DEFAULT_LIMIT,
) -> dict:
    """Create reviewable draft eval cases from recent quality-loop evidence.

    The sync is idempotent per source_type/source_ref_id, so it is safe to run
    whenever the admin RAG evaluation workspace loads.

    Quality gate: cases whose normalized query already exists in the eval suite
    are skipped to avoid duplicate drafts.

    Auto-promotion: newly created cases with >= 2 negative feedback signals
    (e.g., multiple thumbs-down or heavy fallback groups) are immediately
    promoted to enabled=True, status=active.
    """
    existing = _existing_quality_sources(tenant_id)
    query_index = _existing_query_index(tenant_id)
    created: list[dict] = []
    promoted: list[dict] = []
    skipped_existing = 0
    skipped_similar = 0
    failed = 0

    feedback_items = database.list_rag_quality_thumbs_down(tenant_id, limit=limit)
    retrieval_logs = database.list_recent_retrieval_logs(
        tenant_id,
        window_hours=window_hours,
        limit=max(limit * 4, 100),
    )

    payloads = [
        payload
        for payload in (_feedback_payload(item) for item in feedback_items)
        if payload is not None
    ]
    payloads.extend(_fallback_payloads(retrieval_logs))

    for payload in payloads:
        source_key = (str(payload.get("source_type") or ""), str(payload.get("source_ref_id") or ""))
        if source_key in existing:
            skipped_existing += 1
            continue

        normalized_query = _normalize_query(str(payload.get("question") or ""))
        if _has_similar_case(normalized_query, query_index):
            skipped_similar += 1
            logger.info(
                "Skipping quality-loop draft: similar case already exists",
                extra={
                    "tenant_id": tenant_id,
                    "source_type": payload.get("source_type"),
                    "source_ref_id": payload.get("source_ref_id"),
                    "normalized_query": normalized_query[:200],
                },
            )
            continue

        try:
            created_case = database.create_rag_eval_case(tenant_id, payload)
        except Exception:
            failed += 1
            logger.exception(
                "Failed to create quality-loop eval draft",
                extra={
                    "tenant_id": tenant_id,
                    "source_type": payload.get("source_type"),
                    "source_ref_id": payload.get("source_ref_id"),
                },
            )
            continue
        created.append(created_case)
        existing.add(source_key)
        if normalized_query:
            query_index[normalized_query] = str(created_case.get("id") or "")

        signal_count = _count_negative_signals(payload)
        if signal_count >= AUTO_PROMOTE_MIN_SIGNALS:
            reason = f"auto_promote: {signal_count} negative signals (threshold={AUTO_PROMOTE_MIN_SIGNALS})"
            promoted_case = _auto_promote_case(tenant_id, created_case, reason)
            if promoted_case:
                promoted.append(promoted_case)

    return {
        "created_count": len(created),
        "promoted_count": len(promoted),
        "skipped_existing_count": skipped_existing,
        "skipped_similar_count": skipped_similar,
        "failed_count": failed,
        "created": created,
        "promoted": promoted,
    }
