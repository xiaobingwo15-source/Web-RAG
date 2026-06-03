from pydantic import BaseModel, Field


class RagQualitySource(BaseModel):
    document_id: str | None = None
    chunk_id: str | None = None
    filename: str | None = None
    score: float | None = None
    snippet: str | None = None
    content: str | None = None
    retrieval_mode: str | None = None


class RagQualityRetrievalLog(BaseModel):
    id: str
    query: str
    retrieval_mode: str
    chunk_count: int = 0
    source_count: int = 0
    top_score: float | None = None
    duration_ms: int | None = None
    created_at: str
    sources: list[RagQualitySource] = []
    chunks: list[str] = []
    answer_message_id: str | None = None
    groundedness_score: float | None = None
    groundedness_flag: bool = False
    retrieval_quality: str | None = None


class RagQualitySummary(BaseModel):
    retrieval_count: int = 0
    chunk_count: int = 0
    source_count: int = 0
    top_score: float | None = None
    groundedness_score: float | None = None
    groundedness_flag: bool = False
    zero_source: bool = False


class RagQualityFeedbackItem(BaseModel):
    feedback_id: str
    feedback_created_at: str
    feedback_comment: str | None = None
    rating: int = Field(-1)
    message_id: str | None = None
    resolved_message_id: str | None = None
    thread_id: str
    thread_title: str
    client_user_id: str | None = None
    client_email: str
    question: str = ""
    question_message_id: str | None = None
    answer: str = ""
    answer_created_at: str | None = None
    retrieval_logs: list[RagQualityRetrievalLog] = []
    summary: RagQualitySummary


class RagQualityThumbsDownResponse(BaseModel):
    items: list[RagQualityFeedbackItem]
