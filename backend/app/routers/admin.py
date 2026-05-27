"""Admin-only API endpoints for viewing all clients' conversation records."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from app.middleware.auth import get_current_user
from app.services.database import (
    get_all_threads_grouped,
    get_thread_messages_admin,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Admin email whitelist — must match frontend/src/lib/roles.ts
ADMIN_EMAILS = ["admin@example.com"]


def _verify_admin(user) -> None:
    """Raise 403 if the user is not an admin."""
    # Check database role first, then fallback to email whitelist
    if user.role != "admin" and user.email.lower() not in ADMIN_EMAILS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )



@router.get("/conversations")
async def list_all_conversations(user=Depends(get_current_user)):
    """Return every client's threads grouped by user email."""
    _verify_admin(user)
    data = get_all_threads_grouped(user.access_token)
    logger.info("Admin conversations: %d clients found", len(data))
    for client in data:
        logger.info("  Client: %s, threads: %d", client.get("email"), len(client.get("threads", [])))
    return {"clients": data}


@router.get("/conversations/{thread_id}/messages")
async def get_conversation_messages(thread_id: str, user=Depends(get_current_user)):
    """Return all messages for a specific thread (admin access)."""
    _verify_admin(user)
    messages = get_thread_messages_admin(user.access_token, thread_id)
    return {"messages": messages}


from pydantic import BaseModel

class SystemSettingsSchema(BaseModel):
    GOOGLE_API_KEY: str | None = None
    OPENROUTER_API_KEY: str | None = None
    TAVLY_API_KEY: str | None = None
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_BASE_URL: str | None = None


@router.get("/settings")
async def get_settings(user=Depends(get_current_user)):
    """Return all system settings (API keys redacted)."""
    _verify_admin(user)
    
    from app.services.database import get_user_db
    db = get_user_db(user.access_token)
    
    try:
        result = db.table("system_settings").select("*").execute()
        settings_dict = {row["key"]: row["value"] for row in result.data}
    except Exception as e:
        logger.warning(f"Error reading system settings from DB: {e}")
        settings_dict = {}

    def redact(val: str | None) -> str | None:
        if not val:
            return ""
        if len(val) <= 8:
            return "••••••••"
        return f"{val[:6]}••••••••{val[-4:]}"

    return {
        "GOOGLE_API_KEY": redact(settings_dict.get("GOOGLE_API_KEY")),
        "OPENROUTER_API_KEY": redact(settings_dict.get("OPENROUTER_API_KEY")),
        "TAVLY_API_KEY": redact(settings_dict.get("TAVLY_API_KEY")),
        "LANGFUSE_PUBLIC_KEY": settings_dict.get("LANGFUSE_PUBLIC_KEY", ""),
        "LANGFUSE_SECRET_KEY": redact(settings_dict.get("LANGFUSE_SECRET_KEY")),
        "LANGFUSE_BASE_URL": settings_dict.get("LANGFUSE_BASE_URL", "https://jp.cloud.langfuse.com"),
    }


@router.post("/settings")
async def save_settings(settings: SystemSettingsSchema, user=Depends(get_current_user)):
    """Save or update system settings."""
    _verify_admin(user)
    
    from app.services.database import get_user_db
    db = get_user_db(user.access_token)
    
    updates = settings.model_dump(exclude_unset=True)
    
    for key, value in updates.items():
        if value is None:
            continue
        
        # If value is redacted (contains bullet points), skip updating it
        if "••" in value or "••" in value:
            continue
            
        value = value.strip()
        
        # Save or update key-value pair in system_settings
        try:
            db.table("system_settings").upsert({
                "key": key,
                "value": value,
                "description": f"Admin configured {key}",
                "updated_at": "now()"
            }).execute()
        except Exception as e:
            logger.error(f"Failed to upsert setting {key}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update setting {key}: {str(e)}"
            )
            
    # Clear the settings cache to apply overrides immediately
    from app.config import _get_cached_setting
    _get_cached_setting.cache_clear()
    
    return {"status": "success"}

