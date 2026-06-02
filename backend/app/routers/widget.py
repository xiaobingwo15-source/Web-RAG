import json as json_lib
import uuid
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, field_validator
from sse_starlette.sse import EventSourceResponse
from app.models.chat import MAX_IMAGE_COUNT, MAX_IMAGE_DATA_URL_LENGTH, MAX_MESSAGE_LENGTH
from app.routers.chat import build_history
from app.services.agent_supervisor import execute as agent_execute
from app.services.database import (
    create_widget_thread,
    get_thread_messages_service,
    get_thread_service,
    get_tenant_by_slug,
    save_widget_message,
)
from app.services.widget_tokens import create_widget_token, verify_widget_token
from app.services.rate_limit import check_rate_limit

router = APIRouter()


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
    check_rate_limit(f"widget:{tenant_id}:{session_id}", limit=30, window_seconds=60)
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

    async def event_generator():
        full_response = ""
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
        ):
            if event["type"] == "token":
                full_response += event["content"]
            if event["type"] == "error":
                save_widget_message(tenant_id, session_id, thread_id, "assistant", event["content"])
                yield {"data": json_lib.dumps({"type": "error", "content": event["content"], "error_code": event.get("error_code", "unknown"), "thread_id": thread_id})}
                return
            yield {"data": json_lib.dumps({**event, "thread_id": thread_id})}

        save_widget_message(tenant_id, session_id, thread_id, "assistant", full_response)
        yield {"data": json_lib.dumps({"type": "done", "content": "", "thread_id": thread_id, "done": True})}

    return EventSourceResponse(event_generator())
