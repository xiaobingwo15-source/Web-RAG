from typing import Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


RetrievalMode = Literal["vector", "fts", "hybrid"]


class RagEvalCaseCreate(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    expected_facts: list[str] = Field(..., min_length=1)
    expected_answer: Optional[str] = None
    expected_document_id: Optional[UUID] = None
    tags: list[str] = []
    enabled: bool = True

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        return value.strip()

    @field_validator("expected_facts", "tags")
    @classmethod
    def strip_list(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()]


class RagEvalCaseUpdate(BaseModel):
    question: Optional[str] = Field(None, min_length=1, max_length=2000)
    expected_facts: Optional[list[str]] = Field(None, min_length=1)
    expected_answer: Optional[str] = None
    expected_document_id: Optional[UUID] = None
    tags: Optional[list[str]] = None
    enabled: Optional[bool] = None

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value is not None else value

    @field_validator("expected_facts", "tags")
    @classmethod
    def strip_list(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return value
        return [item.strip() for item in value if item and item.strip()]


class RagEvalCaseResponse(BaseModel):
    id: str
    suite_id: Optional[str] = None
    tenant_id: str
    question: str
    expected_facts: list[str]
    expected_answer: Optional[str] = None
    expected_document_id: Optional[str] = None
    tags: list[str]
    enabled: bool
    created_at: str
    updated_at: str


class RagEvalRunCreate(BaseModel):
    retrieval_mode: RetrievalMode = "hybrid"


class RagEvalRunSummary(BaseModel):
    id: str
    tenant_id: str
    suite_id: Optional[str] = None
    status: str
    retrieval_mode: str
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    total_cases: int
    passed_cases: int
    avg_context_relevance_score: float
    avg_groundedness_score: float
    avg_answer_relevance_score: float
    failure_reason: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: str


class RagEvalResultResponse(BaseModel):
    id: str
    tenant_id: str
    run_id: str
    case_id: Optional[str] = None
    question: str
    expected_facts: list[str]
    answer: str
    sources: list[dict]
    context_relevance_score: float
    groundedness_score: float
    answer_relevance_score: float
    passed: bool
    failure_reason: Optional[str] = None
    created_at: str


class RagEvalRunDetail(BaseModel):
    run: RagEvalRunSummary
    results: list[RagEvalResultResponse]
