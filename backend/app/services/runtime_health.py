"""Process-local liveness and startup diagnostics.

The Render liveness check must not depend on Supabase, Qdrant, or an embedding
provider.  This module intentionally uses only the Python standard library so
it remains available while the rest of the application is starting in
degraded mode.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import UTC, datetime
from threading import Lock
from typing import Any


_PROCESS_STARTED_AT = datetime.now(UTC)
_PROCESS_STARTED_MONOTONIC = time.monotonic()
_state_lock = Lock()
_startup_state: dict[str, Any] = {
    "phase": "starting",
    "started_at": None,
    "completed_at": None,
    "checks": {},
}


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def mark_startup_started() -> None:
    with _state_lock:
        _startup_state.update(
            {
                "phase": "maintenance",
                "started_at": _iso_now(),
                "completed_at": None,
                "checks": {},
            }
        )


def record_startup_check(
    name: str,
    *,
    status: str,
    duration_ms: int,
    detail: str | None = None,
) -> None:
    check = {
        "status": status,
        "duration_ms": max(0, duration_ms),
    }
    if detail:
        check["detail"] = detail
    with _state_lock:
        _startup_state["checks"][name] = check


def mark_startup_complete() -> None:
    with _state_lock:
        checks = _startup_state["checks"].values()
        _startup_state["phase"] = (
            "degraded"
            if any(check["status"] == "failed" for check in checks)
            else "ready"
        )
        _startup_state["completed_at"] = _iso_now()


def startup_snapshot() -> dict[str, Any]:
    with _state_lock:
        return {
            **_startup_state,
            "checks": {
                name: dict(check)
                for name, check in _startup_state["checks"].items()
            },
        }


def process_snapshot() -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "pid": os.getpid(),
        "started_at": _PROCESS_STARTED_AT.isoformat(),
        "uptime_seconds": round(max(0.0, time.monotonic() - _PROCESS_STARTED_MONOTONIC), 3),
    }
    peak_rss_mb = _peak_rss_mb()
    if peak_rss_mb is not None:
        snapshot["peak_rss_mb"] = peak_rss_mb
    return snapshot


def liveness_payload() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "agentic-rag-masterclass",
        "process": process_snapshot(),
        "startup": startup_snapshot(),
    }


def reset_startup_diagnostics_for_tests() -> None:
    """Reset mutable startup state without changing process identity."""
    with _state_lock:
        _startup_state.update(
            {
                "phase": "starting",
                "started_at": None,
                "completed_at": None,
                "checks": {},
            }
        )


def _peak_rss_mb() -> float | None:
    try:
        import resource

        peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports KiB; macOS reports bytes.
        divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
        return round(peak_rss / divisor, 1)
    except (ImportError, OSError, ValueError):
        return None
