import logging
from collections.abc import Mapping, Sequence
from typing import Any

logger = logging.getLogger(__name__)

SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
    "key",
)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def redact_snapshot(value: Any, depth: int = 0) -> Any:
    """Return a JSON-safe, secret-redacted snapshot for audit storage."""
    if depth > 8:
        return "[truncated]"
    if isinstance(value, Mapping):
        return {
            str(key): "[redacted]" if _is_sensitive_key(str(key)) else redact_snapshot(item, depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_snapshot(item, depth + 1) for item in value[:50]]
    if isinstance(value, bytes):
        return f"[{len(value)} bytes]"
    if isinstance(value, str):
        return value if len(value) <= 4000 else value[:4000] + "...[truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def request_metadata(request: Any | None) -> dict[str, str | None]:
    if request is None:
        return {"ip_address": None, "user_agent": None}
    client = getattr(request, "client", None)
    headers = getattr(request, "headers", {}) or {}
    return {
        "ip_address": getattr(client, "host", None),
        "user_agent": headers.get("user-agent") if hasattr(headers, "get") else None,
    }


def log_operation(
    *,
    tenant_id: str | None,
    actor_user_id: str | None,
    actor_email: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    actor_role: str | None = None,
    before: Any | None = None,
    after: Any | None = None,
    metadata: Mapping[str, Any] | None = None,
    request: Any | None = None,
) -> None:
    """Write one redacted operation audit row. Audit failures are logged, not raised."""
    try:
        from app.services.database import get_db

        request_meta = request_metadata(request)
        row = {
            "tenant_id": tenant_id,
            "actor_user_id": actor_user_id,
            "actor_email": actor_email,
            "actor_role": actor_role,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "before_snapshot": redact_snapshot(before) if before is not None else None,
            "after_snapshot": redact_snapshot(after) if after is not None else None,
            "metadata": redact_snapshot(dict(metadata or {})),
            "ip_address": request_meta["ip_address"],
            "user_agent": request_meta["user_agent"],
        }
        get_db().table("operation_audit_logs").insert(row).execute()
    except Exception as exc:
        logger.warning("Failed to write operation audit log for %s %s: %s", action, resource_type, exc)

