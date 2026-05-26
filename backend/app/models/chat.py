from pydantic import BaseModel
from typing import Optional


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    use_documents: bool = False


class ChatResponse(BaseModel):
    response: str
    thread_id: str
