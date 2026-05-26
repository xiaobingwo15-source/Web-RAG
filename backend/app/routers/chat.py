import json
import logging
import uuid
from fastapi import APIRouter, Depends
from google.genai import types
from langfuse import propagate_attributes
from app.middleware.auth import get_current_user
from app.models.chat import ChatRequest, ChatResponse
from app.services.gemini import get_gemini_client, generate_chat_response, generate_chat_response_stream
from app.services.database import create_thread, save_message, get_thread_messages, get_user_store
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def build_gemini_history(messages: list[dict]) -> list[types.Content]:
    history = []
    for msg in messages:
        role = "model" if msg["role"] == "assistant" else "user"
        history.append(types.Content(
            role=role,
            parts=[types.Part.from_text(text=msg["content"])],
        ))
    return history


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest, user=Depends(get_current_user)):
    client = get_gemini_client()
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
            create_thread(token, user.id, thread_id)

        save_message(token, user.id, thread_id, "user", request.message)

        history_messages = get_thread_messages(token, thread_id)[:-1]
        history = build_gemini_history(history_messages)

        store_name = None
        if request.use_documents:
            store = get_user_store(token, user.id)
            if store:
                store_name = store["store_name"]
        logger.info(f"Chat request from user={user.id} use_documents={request.use_documents} store_name={store_name}")

        response_text = await generate_chat_response(client, request.message, history, store_name)

        save_message(token, user.id, thread_id, "assistant", response_text)

    return ChatResponse(response=response_text, thread_id=thread_id)


@router.post("/stream")
async def chat_stream(request: ChatRequest, user=Depends(get_current_user)):
    client = get_gemini_client()
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
            create_thread(token, user.id, thread_id)

        save_message(token, user.id, thread_id, "user", request.message)

        history_messages = get_thread_messages(token, thread_id)[:-1]
        history = build_gemini_history(history_messages)

        store_name = None
        if request.use_documents:
            store = get_user_store(token, user.id)
            if store:
                store_name = store["store_name"]
        logger.info(f"Stream chat request from user={user.id} use_documents={request.use_documents} store_name={store_name}")

        async def event_generator():
            full_response = ""
            async for chunk in generate_chat_response_stream(client, request.message, history, store_name):
                full_response += chunk
                yield {
                    "data": json.dumps({
                        "content": chunk,
                        "thread_id": thread_id,
                        "done": False,
                    })
                }

            save_message(token, user.id, thread_id, "assistant", full_response)

            yield {
                "data": json.dumps({
                    "content": "",
                    "thread_id": thread_id,
                    "done": True,
                })
            }

        return EventSourceResponse(event_generator())
