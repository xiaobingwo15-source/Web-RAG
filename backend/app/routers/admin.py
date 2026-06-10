"""Admin-only API endpoints for viewing all clients' conversation records."""

import logging
from datetime import UTC, datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.middleware.auth import get_current_user
from app.services.database import (
    accept_tenant_admin_invite,
    create_rag_eval_case,
    get_all_threads_grouped,
    get_rag_eval_run,
    list_rag_eval_cases,
    list_rag_eval_results,
    list_rag_eval_runs,
    list_rag_quality_thumbs_down,
    get_tenant_admin_invite,
    get_thread_messages_admin,
    save_admin_message,
    get_flagged_messages,
    get_flagged_count,
    clear_thread_attention_flags,
    get_tenant_users,
    update_rag_eval_case,
    update_user_status,
)
from app.models.rag_eval import (
    RagEvalCaseCreate,
    RagEvalCaseResponse,
    RagEvalCaseUpdate,
    RagEvalRunCreate,
    RagEvalRunDetail,
    RagEvalRunSummary,
)
from app.models.rag_quality import RagQualityThumbsDownResponse
from app.services.rag_eval import run_rag_eval
from app.services.widget_tokens import hash_token

logger = logging.getLogger(__name__)

router = APIRouter()


def _verify_admin(user) -> None:
    """Raise 403 if the user is not an admin."""
    if user.role != "admin" or not user.tenant_id or user.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )



@router.get("/conversations")
async def list_all_conversations(user=Depends(get_current_user)):
    """Return every client's threads grouped by user email."""
    _verify_admin(user)
    data = get_all_threads_grouped(user.tenant_id)
    logger.info("Admin conversations: %d clients found", len(data))
    for client in data:
        logger.info("  Client: %s, threads: %d", client.get("email"), len(client.get("threads", [])))
    return {"clients": data}


@router.get("/conversations/{thread_id}/messages")
async def get_conversation_messages(thread_id: str, user=Depends(get_current_user)):
    """Return all messages for a specific thread (admin access)."""
    _verify_admin(user)
    messages = get_thread_messages_admin(user.tenant_id, thread_id)
    return {"messages": messages}


class SystemSettingsSchema(BaseModel):
    MODEL_PROVIDER: str | None = None
    GOOGLE_API_KEY: str | None = None
    OPENROUTER_API_KEY: str | None = None
    OPENROUTER_MODEL: str | None = None
    OPENROUTER_FALLBACK_MODEL: str | None = None
    OCR_MODEL: str | None = None
    MISTRAL_API_KEY: str | None = None
    MISTRAL_MODEL: str | None = None
    TAVLY_API_KEY: str | None = None
    COHERE_API_KEY: str | None = None
    QDRANT_URL: str | None = None
    QDRANT_API_KEY: str | None = None
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_BASE_URL: str | None = None


class AcceptInviteRequest(BaseModel):
    token: str


@router.post("/invites/accept")
async def accept_invite(request: AcceptInviteRequest, user=Depends(get_current_user)):
    invite = get_tenant_admin_invite(hash_token(request.token))
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found or already accepted")
    expires_at = datetime.fromisoformat(invite["expires_at"].replace("Z", "+00:00"))
    if expires_at < datetime.now(UTC):
        raise HTTPException(status_code=410, detail="Invite expired")
    if invite["email"].lower() != user.email.lower():
        raise HTTPException(status_code=403, detail="Invite email does not match signed-in user")
    profile = accept_tenant_admin_invite(invite["id"], invite["tenant_id"], user.id, user.email.lower())
    return {"status": "accepted", "profile": profile}


@router.get("/settings")
async def get_settings(user=Depends(get_current_user)):
    """Return all system settings (API keys redacted)."""
    _verify_admin(user)
    
    from app.services.database import get_user_db
    db = get_user_db(user.access_token)
    
    try:
        result = db.table("system_settings").select("*").eq("tenant_id", user.tenant_id).execute()
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

    from app.config import DEFAULT_OCR_MODEL, normalize_ocr_model

    return {
        "MODEL_PROVIDER": settings_dict.get("MODEL_PROVIDER", "openrouter"),
        "GOOGLE_API_KEY": redact(settings_dict.get("GOOGLE_API_KEY")),
        "OPENROUTER_API_KEY": redact(settings_dict.get("OPENROUTER_API_KEY")),
        "OPENROUTER_MODEL": settings_dict.get("OPENROUTER_MODEL", ""),
        "OPENROUTER_FALLBACK_MODEL": settings_dict.get("OPENROUTER_FALLBACK_MODEL", ""),
        "OCR_MODEL": normalize_ocr_model(settings_dict.get("OCR_MODEL", DEFAULT_OCR_MODEL)),
        "MISTRAL_API_KEY": redact(settings_dict.get("MISTRAL_API_KEY")),
        "MISTRAL_MODEL": settings_dict.get("MISTRAL_MODEL", "mistral-large-latest"),
        "TAVLY_API_KEY": redact(settings_dict.get("TAVLY_API_KEY")),
        "COHERE_API_KEY": redact(settings_dict.get("COHERE_API_KEY")),
        "QDRANT_URL": settings_dict.get("QDRANT_URL", ""),
        "QDRANT_API_KEY": redact(settings_dict.get("QDRANT_API_KEY")),
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

        if key == "MODEL_PROVIDER" and value not in {"openrouter", "mistral"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MODEL_PROVIDER must be 'openrouter' or 'mistral'",
            )
        if key == "OCR_MODEL":
            from app.config import normalize_ocr_model
            value = normalize_ocr_model(value)
        
        # Save or update key-value pair in system_settings
        try:
            db.table("system_settings").upsert({
                "tenant_id": user.tenant_id,
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
    from app.services.gemini import _llm_clients
    _get_cached_setting.cache_clear()
    _llm_clients.clear()

    return {"status": "success"}


# --- RAG Evaluation endpoints ---

@router.get("/rag-evals/cases", response_model=list[RagEvalCaseResponse])
async def get_rag_eval_cases(user=Depends(get_current_user)):
    _verify_admin(user)
    return list_rag_eval_cases(user.tenant_id)


@router.post("/rag-evals/cases", response_model=RagEvalCaseResponse)
async def create_rag_eval_case_endpoint(request: RagEvalCaseCreate, user=Depends(get_current_user)):
    _verify_admin(user)
    return create_rag_eval_case(user.tenant_id, request.model_dump(mode="json"))


@router.patch("/rag-evals/cases/{case_id}", response_model=RagEvalCaseResponse)
async def update_rag_eval_case_endpoint(case_id: str, request: RagEvalCaseUpdate, user=Depends(get_current_user)):
    _verify_admin(user)
    updated = update_rag_eval_case(
        user.tenant_id,
        case_id,
        request.model_dump(mode="json", exclude_unset=True),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Eval case not found")
    return updated


@router.get("/rag-evals/runs", response_model=list[RagEvalRunSummary])
async def get_rag_eval_runs(user=Depends(get_current_user)):
    _verify_admin(user)
    return list_rag_eval_runs(user.tenant_id)


@router.get("/rag-evals/runs/{run_id}", response_model=RagEvalRunDetail)
async def get_rag_eval_run_detail(run_id: str, user=Depends(get_current_user)):
    _verify_admin(user)
    run = get_rag_eval_run(user.tenant_id, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Eval run not found")
    return {
        "run": run,
        "results": list_rag_eval_results(user.tenant_id, run_id),
    }


@router.post("/rag-evals/runs", response_model=RagEvalRunDetail)
async def start_rag_eval_run(request: RagEvalRunCreate, user=Depends(get_current_user)):
    _verify_admin(user)
    return await run_rag_eval(
        tenant_id=user.tenant_id,
        admin_user_id=user.id,
        access_token=user.access_token,
        retrieval_mode=request.retrieval_mode,
    )


@router.get("/rag-quality/thumbs-down", response_model=RagQualityThumbsDownResponse)
async def get_rag_quality_thumbs_down(limit: int = 50, user=Depends(get_current_user)):
    _verify_admin(user)
    return {"items": list_rag_quality_thumbs_down(user.tenant_id, limit=limit)}


# --- Admin Manual Answer endpoints ---

class AdminRespondRequest(BaseModel):
    content: str


@router.get("/flagged")
async def get_flagged(user=Depends(get_current_user)):
    """Return all messages flagged as needing admin attention."""
    _verify_admin(user)
    flagged = get_flagged_messages(user.tenant_id)
    return {"flagged": flagged}


@router.get("/flagged/count")
async def get_flagged_count_endpoint(user=Depends(get_current_user)):
    """Return the count of flagged messages for the badge counter."""
    _verify_admin(user)
    count = get_flagged_count(user.tenant_id)
    return {"count": count}


@router.post("/conversations/{thread_id}/respond")
async def respond_to_thread(thread_id: str, request: AdminRespondRequest, user=Depends(get_current_user)):
    """Admin submits a manual response to a client's flagged thread."""
    _verify_admin(user)

    if not request.content.strip():
        raise HTTPException(status_code=400, detail="Response content cannot be empty")

    # Look up the thread to get the client's user_id
    from app.services.database import get_thread
    thread = get_thread(user.access_token, thread_id, tenant_id=user.tenant_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    client_user_id = thread.get("user_id")

    # Save admin message (user_id set to client for RLS compatibility)
    saved = save_admin_message(user.tenant_id, thread_id, user.id, client_user_id, request.content.strip())

    # Clear all attention flags in this thread
    clear_thread_attention_flags(user.tenant_id, thread_id)

    return {"status": "success", "message_id": saved["id"]}


# --- User Management endpoints ---

@router.get("/users")
async def list_tenant_users(user=Depends(get_current_user)):
    """List all users in the admin's tenant."""
    _verify_admin(user)
    users = get_tenant_users(user.tenant_id)
    return {"users": users}


@router.post("/users/{user_id}/approve")
async def approve_user(user_id: str, user=Depends(get_current_user)):
    """Approve a pending user."""
    _verify_admin(user)
    result = update_user_status(user.tenant_id, user_id, "approved")
    if not result:
        raise HTTPException(status_code=404, detail="User not found in this tenant")
    return {"status": "approved"}


@router.post("/users/{user_id}/suspend")
async def suspend_user(user_id: str, user=Depends(get_current_user)):
    """Suspend a user."""
    _verify_admin(user)
    if user_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot suspend yourself")
    result = update_user_status(user.tenant_id, user_id, "suspended")
    if not result:
        raise HTTPException(status_code=404, detail="User not found in this tenant")
    return {"status": "suspended"}
