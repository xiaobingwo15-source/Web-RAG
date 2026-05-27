from pydantic import BaseModel
from typing import Optional


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    use_documents: bool = True
    retrieval_mode: str = "hybrid"  # "vector", "fts", "hybrid"
    enable_web_search: bool = True
    enable_sql: bool = True
    images: Optional[list[str]] = None  # base64 data URLs


class ChatResponse(BaseModel):
    response: str
    thread_id: str


class ThreadSummary(BaseModel):
    id: str
    title: str
    created_at: str


class ThreadListResponse(BaseModel):
    threads: list[ThreadSummary]


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]
