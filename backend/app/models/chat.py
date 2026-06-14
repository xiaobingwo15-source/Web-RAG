from pydantic import BaseModel
from pydantic import field_validator
from typing import Literal, Optional

MAX_MESSAGE_LENGTH = 8000
MAX_IMAGE_COUNT = 4
MAX_IMAGE_DATA_URL_LENGTH = 5_000_000


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    use_documents: bool = True
    retrieval_mode: Literal["vector", "fts", "hybrid"] = "hybrid"
    enable_web_search: bool = False
    enable_sql: bool = False
    images: Optional[list[str]] = None  # base64 data URLs
    reply_to: Optional[str] = None  # message ID being replied to

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
    def validate_images(cls, value: Optional[list[str]]) -> Optional[list[str]]:
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


class RetrievalSource(BaseModel):
    document_id: str
    chunk_id: str
    score: float
    snippet: str
    retrieval_mode: str
    filename: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    thread_id: str
    sources: list[RetrievalSource] = []


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
    reply_to: Optional[str] = None


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]


class FeedbackRequest(BaseModel):
    thread_id: str
    message_id: str
    rating: Literal[1, -1]
    comment: Optional[str] = None
