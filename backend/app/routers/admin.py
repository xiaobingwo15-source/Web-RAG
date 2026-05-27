"""Admin-only API endpoints for viewing all clients' conversation records."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.middleware.auth import get_current_user
from app.services.database import (
    get_all_threads_grouped,
    get_thread_messages_admin,
    save_admin_message,
    get_flagged_messages,
    get_flagged_count,
    clear_thread_attention_flags,
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


# --- Admin Manual Answer endpoints ---

class AdminRespondRequest(BaseModel):
    content: str


@router.get("/flagged")
async def get_flagged(user=Depends(get_current_user)):
    """Return all messages flagged as needing admin attention."""
    _verify_admin(user)
    flagged = get_flagged_messages()
    return {"flagged": flagged}


@router.get("/flagged/count")
async def get_flagged_count_endpoint(user=Depends(get_current_user)):
    """Return the count of flagged messages for the badge counter."""
    _verify_admin(user)
    count = get_flagged_count()
    return {"count": count}


@router.post("/conversations/{thread_id}/respond")
async def respond_to_thread(thread_id: str, request: AdminRespondRequest, user=Depends(get_current_user)):
    """Admin submits a manual response to a client's flagged thread."""
    _verify_admin(user)

    if not request.content.strip():
        raise HTTPException(status_code=400, detail="Response content cannot be empty")

    # Look up the thread to get the client's user_id
    from app.services.database import get_thread
    thread = get_thread(user.access_token, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    client_user_id = thread["user_id"]

    # Save admin message (user_id set to client for RLS compatibility)
    saved = save_admin_message(thread_id, user.id, client_user_id, request.content.strip())

    # Clear all attention flags in this thread
    clear_thread_attention_flags(thread_id)

    return {"status": "success", "message_id": saved["id"]}

