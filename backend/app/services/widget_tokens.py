import base64
import hashlib
import hmac
import json
import time
import uuid
from app.config import Settings


def _secret() -> bytes:
    settings = Settings()
    secret = settings.widget_token_secret or settings.supabase_service_role_key
    if not secret:
        raise ValueError("WIDGET_TOKEN_SECRET or SUPABASE_SERVICE_ROLE_KEY is required")
    return secret.encode("utf-8")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_invite_token() -> str:
    return base64.urlsafe_b64encode(uuid.uuid4().bytes + uuid.uuid4().bytes).decode("ascii").rstrip("=")


def create_widget_token(tenant_id: str, origin: str, ttl_seconds: int = 3600) -> tuple[str, str]:
    session_id = str(uuid.uuid4())
    payload = {
        "tenant_id": tenant_id,
        "origin": origin,
        "session_id": session_id,
        "exp": int(time.time()) + ttl_seconds,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
    signature = hmac.new(_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{payload_b64}.{signature_b64}", session_id


def verify_widget_token(token: str) -> dict:
    try:
        payload_b64, signature_b64 = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("Invalid widget token") from exc

    expected = hmac.new(_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    actual = base64.urlsafe_b64decode(signature_b64 + "=" * (-len(signature_b64) % 4))
    if not hmac.compare_digest(expected, actual):
        raise ValueError("Invalid widget token signature")

    payload_bytes = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4))
    payload = json.loads(payload_bytes)
    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("Widget token expired")
    return payload
