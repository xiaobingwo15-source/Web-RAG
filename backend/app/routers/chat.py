import asyncio
import json as json_lib
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException
from openai import APIError, RateLimitError
from langfuse import propagate_attributes
from app.middleware.auth import get_current_user
from app.models.chat import ChatRequest, ChatResponse, ThreadListResponse, ThreadSummary, MessageListResponse, MessageResponse, FeedbackRequest
from app.services.gemini import get_llm_client, generate_chat_response, generate_chat_response_stream, _extract_retry_delay
from app.services.groundedness import GROUNDEDNESS_THRESHOLD, check_groundedness
from app.services.retrieval import retrieve_context
from app.services.agent_supervisor import execute as agent_execute
from app.services.database import create_thread, save_message, save_message_streaming, update_message_content, get_thread_messages, get_user_threads, get_thread, delete_thread as db_delete_thread, save_message_feedback, get_message_feedback, get_retrieval_logs, update_retrieval_logs_for_answer
from app.services.rate_limit import check_rate_limit
from app.config import Settings
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def _is_approved_admin(user) -> bool:
    return user.role == "admin" and bool(user.tenant_id) and user.status == "approved"


def _public_sources(sources: list[dict]) -> list[dict]:
    return [{key: value for key, value in source.items() if key != "content"} for source in sources]


def _plain_message_text(content: str) -> str:
    try:
        parsed = json_lib.loads(content)
        if isinstance(parsed, dict) and isinstance(parsed.get("text"), str):
            return parsed["text"]
    except (json_lib.JSONDecodeError, TypeError):
        pass
    return content


def _reply_quote_text(messages: list[dict], reply_to: str | None) -> str | None:
    if not reply_to:
        return None

    for msg in messages:
        if msg.get("id") == reply_to:
            quoted = _plain_message_text(msg.get("content") or "")
            if len(quoted) > 500:
                quoted = quoted[:497] + "..."
            return quoted

    return None


def build_active_message(message: str, messages: list[dict], reply_to: str | None) -> str:
    quoted = _reply_quote_text(messages, reply_to)
    if not quoted:
        return message
    return f"Replying to: {quoted}\n\nUser message: {message}"


def build_history(messages: list[dict]) -> list[dict]:
    # Build a lookup map of message id -> content for reply context
    msg_map = {m["id"]: m["content"] for m in messages if m.get("id")}

    history = []
    for msg in messages:
        role = "assistant" if msg["role"] == "assistant" else "user"
        content = msg["content"]

        # Add reply context for user messages that reference another message
        reply_to = msg.get("reply_to")
        if reply_to and reply_to in msg_map:
            quoted = _plain_message_text(msg_map[reply_to])
            if len(quoted) > 500:
                quoted = quoted[:497] + "..."
            reply_context = f"[Replying to: {quoted}]\n\n"
        else:
            reply_context = ""

        if role == "user":
            try:
                parsed = json_lib.loads(content)
                if isinstance(parsed, dict) and "text" in parsed:
                    parts = [{"type": "text", "text": reply_context + parsed["text"]}]
                    for img in parsed.get("images", []):
                        parts.append({"type": "image_url", "image_url": {"url": img}})
                    history.append({"role": role, "content": parts})
                    continue
            except (json_lib.JSONDecodeError, TypeError):
                pass
        history.append({"role": role, "content": reply_context + content})
    return history


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest, user=Depends(get_current_user)):
    if user.status != "approved":
        raise HTTPException(status_code=403, detail="Your account is pending approval. Please wait for an admin to approve your access.")
    settings = Settings()
    check_rate_limit(f"chat:{user.id}", limit=settings.rate_limit_chat_requests, window_seconds=settings.rate_limit_chat_window)
    allow_web_search = bool(request.enable_web_search and _is_approved_admin(user))
    client = get_llm_client()
    is_new_thread = not request.thread_id
    thread_id = request.thread_id or str(uuid.uuid4())
    token = user.access_token

    with propagate_attributes(
        user_id=user.id,
        session_id=thread_id,
        tags=["chat"],
        trace_name="chat",
    ):
        if is_new_thread:
            title = request.message.strip()
            if len(title) > 40:
                title = title[:37] + "..."
            title = title or "New Chat"
            create_thread(token, user.id, thread_id, title=title, tenant_id=user.tenant_id)

        stored_content = json_lib.dumps({"text": request.message, "images": request.images}) if request.images else request.message
        save_message(token, user.id, thread_id, "user", stored_content, tenant_id=user.tenant_id, reply_to=request.reply_to)

        thread_messages = get_thread_messages(token, thread_id, tenant_id=user.tenant_id)
        active_message = build_active_message(request.message, thread_messages, request.reply_to)
        history_messages = thread_messages[:-1]
        history = build_history(history_messages)

        context_chunks = None
        sources = []
        retrieval_log_ids: list[str] = []
        if request.use_documents:
            retrieval_result = await retrieve_context(
                token,
                user.id,
                active_message,
                mode=request.retrieval_mode,
                tenant_id=user.tenant_id,
                thread_id=thread_id,
                diagnostics={
                    "channel": "authenticated",
                    "web_fallback_allowed": allow_web_search,
                    "direct_chat": True,
                },
            )
            context_chunks = retrieval_result["chunks"]
            sources = retrieval_result["sources"]
            retrieval_log_ids = retrieval_result.get("retrieval_log_ids", [])
            logger.info(f"Retrieved {len(context_chunks)} context chunks for user={user.id}")

        try:
            response_text = await generate_chat_response(client, active_message, history, context_chunks, images=request.images)
        except RateLimitError as e:
            retry_hint = _extract_retry_delay(e)
            raise HTTPException(status_code=429, detail=f"Rate limit reached. Please wait {int(retry_hint)} seconds and try again.")
        except APIError:
            raise HTTPException(status_code=503, detail="The AI service is temporarily unavailable. Please try again in a moment.")

        assistant_message = save_message(token, user.id, thread_id, "assistant", response_text, tenant_id=user.tenant_id)
        if retrieval_log_ids:
            try:
                groundedness = check_groundedness(response_text, context_chunks or [])
                update_retrieval_logs_for_answer(
                    tenant_id=user.tenant_id,
                    retrieval_log_ids=retrieval_log_ids,
                    answer_message_id=assistant_message["id"],
                    groundedness_score=round(groundedness, 3),
                    groundedness_flag=groundedness < GROUNDEDNESS_THRESHOLD,
                    retrieval_quality="direct_chat",
                )
            except Exception:
                logger.warning("Failed to attach retrieval logs for direct chat", exc_info=True)

    return ChatResponse(response=response_text, thread_id=thread_id, sources=_public_sources(sources))


@router.post("/stream")
async def chat_stream(request: ChatRequest, user=Depends(get_current_user)):
    if user.status != "approved":
        raise HTTPException(status_code=403, detail="Your account is pending approval. Please wait for an admin to approve your access.")
    settings = Settings()
    check_rate_limit(f"chat_stream:{user.id}", limit=settings.rate_limit_chat_requests, window_seconds=settings.rate_limit_chat_window)
    allow_web_search = bool(request.enable_web_search and _is_approved_admin(user))
    allow_sql = bool(request.enable_sql and settings.sql_tools_enabled and _is_approved_admin(user))
    is_new_thread = not request.thread_id
    thread_id = request.thread_id or str(uuid.uuid4())
    token = user.access_token

    with propagate_attributes(
        user_id=user.id,
        session_id=thread_id,
        tags=["chat", "streaming"],
        trace_name="chat-stream",
    ):
        if is_new_thread:
            title = request.message.strip()
            if len(title) > 40:
                title = title[:37] + "..."
            title = title or "New Chat"
            create_thread(token, user.id, thread_id, title=title, tenant_id=user.tenant_id)

        stored_content = json_lib.dumps({"text": request.message, "images": request.images}) if request.images else request.message
        user_message = save_message(token, user.id, thread_id, "user", stored_content, tenant_id=user.tenant_id, reply_to=request.reply_to)

        thread_messages = get_thread_messages(token, thread_id, tenant_id=user.tenant_id)
        active_message = build_active_message(request.message, thread_messages, request.reply_to)
        history_messages = thread_messages[:-1]
        history = build_history(history_messages)

        # ── Persistent pipeline: runs in background even if client disconnects ──
        # Save a placeholder assistant message immediately so the frontend can
        # detect that a response is being generated.  The background task fills
        # in the real content when the pipeline finishes.
        assistant_placeholder = save_message_streaming(token, user.id, thread_id, tenant_id=user.tenant_id)
        assistant_msg_id = assistant_placeholder["id"]

        _SENTINEL = object()  # signals end-of-stream to the SSE generator
        queue: asyncio.Queue = asyncio.Queue()

        async def _run_pipeline():
            """Background task: runs the full RAG pipeline and persists the answer.

            This task continues running even if the client disconnects.  It
            pushes every event to *queue* so the SSE generator can forward them
            to the client when connected, and always saves the final answer via
            ``update_message_content`` regardless of client state.
            """
            full_response = ""
            retrieval_log_ids: list[str] = []
            groundedness_score: float | None = None
            groundedness_flag = False
            retrieval_quality: str | None = None
            rag_diagnostics: dict | None = None
            try:
                async for event in agent_execute(
                    token=token,
                    user_id=user.id,
                    message=active_message,
                    history=history,
                    thread_id=thread_id,
                    use_documents=request.use_documents,
                    retrieval_mode=request.retrieval_mode,
                    enable_web_search=allow_web_search,
                    enable_sql=allow_sql,
                    images=request.images,
                    tenant_id=user.tenant_id,
                ):
                    # Push every event to the SSE queue (best-effort)
                    try:
                        queue.put_nowait(event)
                    except asyncio.QueueFull:
                        pass  # drop if consumer is too slow

                    if event["type"] == "token":
                        full_response += event["content"]
                    elif event["type"] == "error":
                        # Persist error as the assistant message content
                        try:
                            update_message_content(assistant_msg_id, event["content"], status="complete")
                        except Exception:
                            logger.warning("Failed to save error message to DB", exc_info=True)
                        return
                    elif event["type"] == "rag_quality":
                        retrieval_log_ids = event.get("retrieval_log_ids", []) or retrieval_log_ids
                        groundedness_score = event.get("groundedness")
                        groundedness_flag = bool(event.get("groundedness_flag"))
                        retrieval_quality = event.get("retrieval_quality")
                        rag_diagnostics = event.get("diagnostics")

                # Pipeline completed normally — persist the full answer
                update_message_content(assistant_msg_id, full_response, status="complete")
                if retrieval_log_ids:
                    update_retrieval_logs_for_answer(
                        tenant_id=user.tenant_id,
                        retrieval_log_ids=retrieval_log_ids,
                        answer_message_id=assistant_msg_id,
                        groundedness_score=groundedness_score,
                        groundedness_flag=groundedness_flag,
                        retrieval_quality=retrieval_quality,
                        diagnostics=rag_diagnostics,
                    )
            except asyncio.CancelledError:
                # Server shutdown / deployment — persist whatever we have so far
                logger.warning(f"Background pipeline cancelled, persisting partial response for thread={thread_id}")
                try:
                    update_message_content(assistant_msg_id, full_response or "", status="complete")
                except Exception:
                    logger.warning("Failed to persist partial response on cancellation", exc_info=True)
            except Exception as e:
                logger.error(f"Background pipeline failed: {e}", exc_info=True)
                # Save whatever we have so far (may be partial)
                error_text = full_response or "An unexpected error occurred. Please try again."
                try:
                    update_message_content(assistant_msg_id, error_text, status="complete")
                except Exception:
                    logger.warning("Failed to persist partial response on error", exc_info=True)
                # Push an error event so the SSE generator yields 'error' instead of 'done'
                try:
                    queue.put_nowait({
                        "type": "error",
                        "content": "An unexpected error occurred. Please try again.",
                        "error_code": "server_error",
                    })
                except asyncio.QueueFull:
                    pass
            finally:
                # Always signal end-of-stream so the SSE generator can exit
                try:
                    queue.put_nowait(_SENTINEL)
                except asyncio.QueueFull:
                    pass

        # Launch the pipeline as a background task (detached from the SSE stream)
        pipeline_task = asyncio.create_task(_run_pipeline())

        async def event_generator():
            """SSE generator: reads events from the pipeline queue and yields to the client.

            If the client disconnects, this generator is cancelled but the
            background pipeline task continues running and saves the answer.
            """
            # Yield the user_message confirmation first
            yield {
                "data": json_lib.dumps({
                    "type": "user_message",
                    "thread_id": thread_id,
                    "message_id": user_message["id"],
                    "created_at": user_message.get("created_at"),
                })
            }

            # Yield the placeholder assistant message ID so the frontend can
            # associate streamed tokens with the correct message row.
            yield {
                "data": json_lib.dumps({
                    "type": "assistant_message",
                    "thread_id": thread_id,
                    "message_id": assistant_msg_id,
                    "created_at": assistant_placeholder.get("created_at"),
                })
            }

            try:
                while True:
                    event = await queue.get()
                    if event is _SENTINEL:
                        break

                    if event["type"] == "thought":
                        payload = {
                            "type": "thought",
                            "content": event["content"],
                            "thread_id": thread_id,
                        }
                        for key in ("action_type", "action_source", "action_data"):
                            if key in event:
                                payload[key] = event[key]
                        yield {"data": json_lib.dumps(payload)}
                    elif event["type"] == "token":
                        yield {
                            "data": json_lib.dumps({
                                "type": "token",
                                "content": event["content"],
                                "thread_id": thread_id,
                                "done": False,
                            })
                        }
                    elif event["type"] == "error":
                        yield {
                            "data": json_lib.dumps({
                                "type": "error",
                                "content": event["content"],
                                "error_code": event.get("error_code", "unknown"),
                                "thread_id": thread_id,
                            })
                        }
                        return
                    elif event["type"] == "sources":
                        yield {
                            "data": json_lib.dumps({
                                "type": "sources",
                                "sources": event.get("sources", []),
                                "thread_id": thread_id,
                            })
                        }

                # Pipeline finished — send done event
                yield {
                    "data": json_lib.dumps({
                        "type": "done",
                        "content": "",
                        "thread_id": thread_id,
                        "message_id": assistant_msg_id,
                        "created_at": assistant_placeholder.get("created_at"),
                        "done": True,
                    })
                }
            except asyncio.CancelledError:
                # Client disconnected — the background task continues running
                logger.info(f"SSE generator cancelled (client disconnected), pipeline continues in background for thread={thread_id}")
            except Exception as e:
                logger.error(f"SSE event_generator failed: {e}", exc_info=True)
                error_code = "rate_limit" if isinstance(e, RateLimitError) else "server_error"
                content = "Rate limit reached. Please wait a moment and try again." if error_code == "rate_limit" else "An unexpected error occurred. Please try again."
                yield {
                    "data": json_lib.dumps({
                        "type": "error",
                        "content": content,
                        "error_code": error_code,
                        "thread_id": thread_id,
                    })
                }

        return EventSourceResponse(event_generator())


@router.get("/threads", response_model=ThreadListResponse)
async def list_threads(user=Depends(get_current_user)):
    threads = get_user_threads(user.access_token, user.id, tenant_id=user.tenant_id)
    return ThreadListResponse(
        threads=[
            ThreadSummary(id=t["id"], title=t["title"], created_at=t["created_at"])
            for t in threads
        ]
    )


@router.get("/threads/{thread_id}/messages", response_model=MessageListResponse)
async def list_thread_messages(thread_id: str, user=Depends(get_current_user)):
    thread = get_thread(user.access_token, thread_id, tenant_id=user.tenant_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    messages = get_thread_messages(user.access_token, thread_id, tenant_id=user.tenant_id)
    return MessageListResponse(
        messages=[
            MessageResponse(
                id=m["id"],
                role=m["role"],
                content=m["content"],
                created_at=m["created_at"],
                reply_to=m.get("reply_to"),
            )
            for m in messages
        ]
    )


@router.delete("/threads/{thread_id}")
async def delete_thread_endpoint(thread_id: str, user=Depends(get_current_user)):
    thread = get_thread(user.access_token, thread_id, tenant_id=user.tenant_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    db_delete_thread(user.access_token, thread_id, tenant_id=user.tenant_id)
    return {"status": "deleted"}


@router.post("/feedback")
async def submit_feedback(request: FeedbackRequest, user=Depends(get_current_user)):
    if user.status != "approved":
        raise HTTPException(status_code=403, detail="Account pending approval.")
    result = save_message_feedback(
        user_id=user.id,
        thread_id=request.thread_id,
        message_id=request.message_id,
        rating=request.rating,
        comment=request.comment,
        tenant_id=user.tenant_id,
    )
    return {"status": "ok", "id": result.get("id") if result else None}


@router.get("/threads/{thread_id}/feedback")
async def get_thread_feedback(thread_id: str, user=Depends(get_current_user)):
    feedback = get_message_feedback(user.id, thread_id)
    return {"feedback": feedback}


@router.get("/retrieval-logs")
async def list_retrieval_logs(
    zero_chunks_only: bool = False,
    limit: int = 50,
    user=Depends(get_current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only.")
    logs = get_retrieval_logs(
        tenant_id=user.tenant_id,
        zero_chunks_only=zero_chunks_only,
        limit=limit,
    )
    return {"logs": logs}
