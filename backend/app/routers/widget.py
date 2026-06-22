import asyncio
import json as json_lib
import logging
import uuid
from typing import Literal
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, field_validator
from sse_starlette.sse import EventSourceResponse
from app.models.chat import MAX_IMAGE_COUNT, MAX_IMAGE_DATA_URL_LENGTH, MAX_MESSAGE_LENGTH
from app.routers.chat import build_history
from app.services.agent_supervisor import execute as agent_execute
from app.services.database import (
    create_widget_thread,
    get_db,
    get_thread_messages_service,
    get_thread_service,
    get_tenant_by_slug,
    get_tenant_admin_user_id,
    save_widget_feedback,
    save_widget_message,
    save_widget_message_streaming,
    update_message_content,
    update_retrieval_logs_for_answer,
)
from app.services.widget_tokens import create_widget_token, verify_widget_token
from app.services.rate_limit import check_rate_limit
from app.config import Settings

logger = logging.getLogger(__name__)
router = APIRouter()


def _resolve_widget_rag_target_user_id(tenant_id: str) -> str:
    admin_id = get_tenant_admin_user_id(tenant_id)
    if not admin_id:
        raise HTTPException(status_code=503, detail="Widget RAG is not configured for this tenant.")

    result = (
        get_db()
        .table("documents")
        .select("id")
        .eq("tenant_id", tenant_id)
        .eq("user_id", admin_id)
        .eq("status", "processed")
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=503, detail="Widget RAG has no processed knowledge-base documents for this tenant.")
    return admin_id


class WidgetSessionRequest(BaseModel):
    tenant_slug: str


class WidgetChatRequest(BaseModel):
    message: str
    thread_id: str | None = None
    images: list[str] | None = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message cannot be empty")
        if len(value) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"message must be {MAX_MESSAGE_LENGTH} characters or fewer")
        return value

    @field_validator("images")
    @classmethod
    def validate_images(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        if len(value) > MAX_IMAGE_COUNT:
            raise ValueError(f"images must contain at most {MAX_IMAGE_COUNT} items")
        for image in value:
            if len(image) > MAX_IMAGE_DATA_URL_LENGTH:
                raise ValueError("each image data URL is too large")
            if not image.startswith("data:image/"):
                raise ValueError("images must be data:image URLs")
        return value


class WidgetFeedbackRequest(BaseModel):
    thread_id: str
    message_id: str
    rating: Literal[1, -1]
    comment: str | None = None


@router.post("/session")
async def create_session(request: WidgetSessionRequest, origin: str | None = Header(default=None)):
    if not origin:
        raise HTTPException(status_code=403, detail="Origin header required")

    tenant = get_tenant_by_slug(request.tenant_slug.strip().lower())
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    allowed_origins = [value.rstrip("/") for value in tenant.get("allowed_origins", [])]
    normalized_origin = origin.rstrip("/")
    if normalized_origin not in allowed_origins:
        raise HTTPException(status_code=403, detail="Origin is not allowed for this tenant")

    token, session_id = create_widget_token(tenant["id"], normalized_origin)
    return {"token": token, "session_id": session_id, "expires_in": 3600}


@router.post("/chat/stream")
async def chat_stream(
    request: WidgetChatRequest,
    authorization: str | None = Header(default=None),
    origin: str | None = Header(default=None),
):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Widget token required")
    try:
        payload = verify_widget_token(authorization.split(" ", 1)[1])
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    if origin and origin.rstrip("/") != payload["origin"]:
        raise HTTPException(status_code=403, detail="Origin does not match widget session")

    tenant_id = payload["tenant_id"]
    session_id = payload["session_id"]
    settings = Settings()
    check_rate_limit(f"widget:{tenant_id}:{session_id}", limit=settings.rate_limit_widget_requests, window_seconds=settings.rate_limit_widget_window)

    # Free tier limit: count user messages for this session
    msg_count_result = (
        get_db()
        .table("messages")
        .select("id")
        .eq("tenant_id", tenant_id)
        .eq("client_session_id", session_id)
        .eq("role", "user")
        .execute()
    )
    user_msg_count = len(msg_count_result.data or [])
    if user_msg_count >= settings.widget_free_tier_limit:
        async def _limit_reached():
            yield {"data": json_lib.dumps({
                "type": "error",
                "content": "You've reached the free question limit. Please sign up to continue the conversation.",
                "error_code": "free_tier_limit",
                "thread_id": request.thread_id or "",
            })}
        return EventSourceResponse(_limit_reached())

    target_user_id = _resolve_widget_rag_target_user_id(tenant_id)
    is_new_thread = not request.thread_id
    thread_id = request.thread_id or str(uuid.uuid4())

    if is_new_thread:
        title = request.message.strip()
        if len(title) > 40:
            title = title[:37] + "..."
        create_widget_thread(tenant_id, session_id, thread_id, title=title or "New Chat")
    elif not get_thread_service(tenant_id, thread_id):
        raise HTTPException(status_code=404, detail="Thread not found")

    stored_content = json_lib.dumps({"text": request.message, "images": request.images}) if request.images else request.message
    save_widget_message(tenant_id, session_id, thread_id, "user", stored_content)
    history = build_history(get_thread_messages_service(tenant_id, thread_id)[:-1])

    # ── Persistent pipeline: runs in background even if client disconnects ──
    assistant_placeholder = save_widget_message_streaming(tenant_id, session_id, thread_id)
    assistant_msg_id = str(assistant_placeholder["id"]) if assistant_placeholder and "id" in assistant_placeholder else None

    if not assistant_msg_id:
        # Cannot persist the response — fail loudly rather than silently losing the answer
        logger.error(f"Widget streaming placeholder missing 'id': {assistant_placeholder}")
        raise HTTPException(status_code=500, detail="Failed to create assistant message placeholder")

    _SENTINEL = object()
    queue: asyncio.Queue = asyncio.Queue()

    async def _run_pipeline():
        full_response = ""
        retrieval_log_ids: list[str] = []
        groundedness_score: float | None = None
        groundedness_flag = False
        retrieval_quality: str | None = None
        rag_diagnostics: dict | None = None
        try:
            async for event in agent_execute(
                token="",
                user_id=session_id,
                message=request.message,
                history=history,
                thread_id=thread_id,
                use_documents=True,
                retrieval_mode="hybrid",
                enable_web_search=False,
                enable_sql=False,
                images=request.images,
                tenant_id=tenant_id,
                target_user_id=target_user_id,
            ):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass

                if event["type"] == "token":
                    full_response += event["content"]
                elif event["type"] == "error":
                    if assistant_msg_id:
                        try:
                            update_message_content(assistant_msg_id, event["content"], status="complete")
                        except Exception:
                            logger.warning("Widget: failed to save error message", exc_info=True)
                    return
                elif event["type"] == "rag_quality":
                    retrieval_log_ids = event.get("retrieval_log_ids", []) or retrieval_log_ids
                    groundedness_score = event.get("groundedness")
                    groundedness_flag = bool(event.get("groundedness_flag"))
                    retrieval_quality = event.get("retrieval_quality")
                    rag_diagnostics = event.get("diagnostics")

            # Pipeline completed — persist answer
            if assistant_msg_id:
                update_message_content(assistant_msg_id, full_response, status="complete")
                if retrieval_log_ids:
                    update_retrieval_logs_for_answer(
                        tenant_id=tenant_id,
                        retrieval_log_ids=retrieval_log_ids,
                        answer_message_id=assistant_msg_id,
                        groundedness_score=groundedness_score,
                        groundedness_flag=groundedness_flag,
                        retrieval_quality=retrieval_quality,
                        diagnostics=rag_diagnostics,
                    )
        except asyncio.CancelledError:
            logger.warning(f"Widget pipeline cancelled, persisting partial response for thread={thread_id}")
            if assistant_msg_id:
                try:
                    update_message_content(assistant_msg_id, full_response or "", status="complete")
                except Exception:
                    logger.warning("Widget: failed to persist partial response on cancellation", exc_info=True)
        except Exception as e:
            logger.error(f"Widget background pipeline failed: {e}", exc_info=True)
            if assistant_msg_id:
                try:
                    update_message_content(assistant_msg_id, full_response or "An unexpected error occurred.", status="complete")
                except Exception:
                    logger.warning("Widget: failed to persist partial response", exc_info=True)
            try:
                queue.put_nowait({"type": "error", "content": "An unexpected error occurred.", "error_code": "server_error"})
            except asyncio.QueueFull:
                pass
        finally:
            try:
                queue.put_nowait(_SENTINEL)
            except asyncio.QueueFull:
                pass

    pipeline_task = asyncio.create_task(_run_pipeline())

    async def event_generator():
        try:
            while True:
                event = await queue.get()
                if event is _SENTINEL:
                    break
                if event["type"] == "error":
                    yield {"data": json_lib.dumps({"type": "error", "content": event["content"], "error_code": event.get("error_code", "unknown"), "thread_id": thread_id})}
                    return
                yield {"data": json_lib.dumps({**event, "thread_id": thread_id})}
            yield {"data": json_lib.dumps({"type": "done", "content": "", "thread_id": thread_id, "done": True, "message_id": assistant_msg_id})}
        except asyncio.CancelledError:
            logger.info(f"Widget SSE cancelled (client disconnected), pipeline continues for thread={thread_id}")
        except Exception as e:
            logger.error(f"Widget SSE generator failed: {e}", exc_info=True)

    return EventSourceResponse(event_generator())


@router.post("/feedback")
async def submit_widget_feedback(
    request: WidgetFeedbackRequest,
    authorization: str | None = Header(default=None),
    origin: str | None = Header(default=None),
):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Widget token required")
    try:
        payload = verify_widget_token(authorization.split(" ", 1)[1])
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    if origin and origin.rstrip("/") != payload["origin"]:
        raise HTTPException(status_code=403, detail="Origin does not match widget session")

    result = save_widget_feedback(
        client_session_id=payload["session_id"],
        thread_id=request.thread_id,
        message_id=request.message_id,
        rating=request.rating,
        comment=request.comment,
        tenant_id=payload["tenant_id"],
    )
    return {"status": "ok", "id": result.get("id") if result else None}
