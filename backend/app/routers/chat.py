import json as json_lib
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException
from openai import APIError, RateLimitError
from langfuse import propagate_attributes
from app.middleware.auth import get_current_user
from app.models.chat import ChatRequest, ChatResponse, ThreadListResponse, ThreadSummary, MessageListResponse, MessageResponse
from app.services.gemini import get_llm_client, generate_chat_response, generate_chat_response_stream, _extract_retry_delay
from app.services.retrieval import retrieve_context
from app.services.agent_supervisor import execute as agent_execute
from app.services.database import create_thread, save_message, get_thread_messages, get_user_threads, get_thread, delete_thread as db_delete_thread
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def build_history(messages: list[dict]) -> list[dict]:
    history = []
    for msg in messages:
        role = "assistant" if msg["role"] == "assistant" else "user"
        content = msg["content"]
        if role == "user":
            try:
                parsed = json_lib.loads(content)
                if isinstance(parsed, dict) and "text" in parsed:
                    parts = [{"type": "text", "text": parsed["text"]}]
                    for img in parsed.get("images", []):
                        parts.append({"type": "image_url", "image_url": {"url": img}})
                    history.append({"role": role, "content": parts})
                    continue
            except (json_lib.JSONDecodeError, TypeError):
                pass
        history.append({"role": role, "content": content})
    return history


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest, user=Depends(get_current_user)):
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
            create_thread(token, user.id, thread_id, title=title)

        stored_content = json_lib.dumps({"text": request.message, "images": request.images}) if request.images else request.message
        save_message(token, user.id, thread_id, "user", stored_content)

        history_messages = get_thread_messages(token, thread_id)[:-1]
        history = build_history(history_messages)

        context_chunks = None
        if request.use_documents:
            retrieval_result = await retrieve_context(token, user.id, request.message, mode=request.retrieval_mode)
            context_chunks = retrieval_result["chunks"]
            logger.info(f"Retrieved {len(context_chunks)} context chunks for user={user.id}")

        try:
            response_text = await generate_chat_response(client, request.message, history, context_chunks, images=request.images)
        except RateLimitError as e:
            retry_hint = _extract_retry_delay(e)
            raise HTTPException(status_code=429, detail=f"Rate limit reached. Please wait {int(retry_hint)} seconds and try again.")
        except APIError:
            raise HTTPException(status_code=503, detail="The AI service is temporarily unavailable. Please try again in a moment.")

        save_message(token, user.id, thread_id, "assistant", response_text)

    return ChatResponse(response=response_text, thread_id=thread_id)


@router.post("/stream")
async def chat_stream(request: ChatRequest, user=Depends(get_current_user)):
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
            create_thread(token, user.id, thread_id, title=title)

        stored_content = json_lib.dumps({"text": request.message, "images": request.images}) if request.images else request.message
        save_message(token, user.id, thread_id, "user", stored_content)

        history_messages = get_thread_messages(token, thread_id)[:-1]
        history = build_history(history_messages)

        async def event_generator():
            full_response = ""
            try:
                async for event in agent_execute(
                    token=token,
                    user_id=user.id,
                    message=request.message,
                    history=history,
                    thread_id=thread_id,
                    use_documents=request.use_documents,
                    retrieval_mode=request.retrieval_mode,
                    enable_web_search=request.enable_web_search,
                    enable_sql=request.enable_sql,
                    images=request.images,
                ):
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
                        full_response += event["content"]
                        yield {
                            "data": json_lib.dumps({
                                "type": "token",
                                "content": event["content"],
                                "thread_id": thread_id,
                                "done": False,
                            })
                        }
                    elif event["type"] == "error":
                        # Persist error message so the DB trigger can flag it
                        if thread_id:
                            try:
                                save_message(token, user.id, thread_id, "assistant", event["content"])
                            except Exception:
                                logger.warning("Failed to save error message to DB", exc_info=True)
                        yield {
                            "data": json_lib.dumps({
                                "type": "error",
                                "content": event["content"],
                                "error_code": event.get("error_code", "unknown"),
                                "thread_id": thread_id,
                            })
                        }
                        return

                save_message(token, user.id, thread_id, "assistant", full_response)

                yield {
                    "data": json_lib.dumps({
                        "type": "done",
                        "content": "",
                        "thread_id": thread_id,
                        "done": True,
                    })
                }
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
    threads = get_user_threads(user.access_token, user.id)
    return ThreadListResponse(
        threads=[
            ThreadSummary(id=t["id"], title=t["title"], created_at=t["created_at"])
            for t in threads
        ]
    )


@router.get("/threads/{thread_id}/messages", response_model=MessageListResponse)
async def list_thread_messages(thread_id: str, user=Depends(get_current_user)):
    thread = get_thread(user.access_token, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    messages = get_thread_messages(user.access_token, thread_id)
    return MessageListResponse(
        messages=[
            MessageResponse(
                id=m["id"],
                role=m["role"],
                content=m["content"],
                created_at=m["created_at"],
            )
            for m in messages
        ]
    )


@router.delete("/threads/{thread_id}")
async def delete_thread_endpoint(thread_id: str, user=Depends(get_current_user)):
    thread = get_thread(user.access_token, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    db_delete_thread(user.access_token, thread_id)
    return {"status": "deleted"}
