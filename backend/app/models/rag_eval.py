from typing import Any, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, model_validator


RetrievalMode = Literal["vector", "fts", "hybrid"]
RagEvalCaseStatus = Literal["draft", "active"]


class RagEvalCaseCreate(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    expected_facts: list[str] = Field(default_factory=list)
    expected_answer: Optional[str] = None
    expected_document_id: Optional[UUID] = None
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    status: RagEvalCaseStatus = "active"
    source_type: Optional[str] = None
    source_ref_id: Optional[str] = None
    retrieval_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        return value.strip()

    @field_validator("expected_facts", "tags")
    @classmethod
    def strip_list(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()]

    @model_validator(mode="after")
    def active_cases_need_expected_facts(self):
        if self.status == "active" and self.enabled and not self.expected_facts:
            raise ValueError("active enabled eval cases need at least one expected fact")
        return self


class RagEvalCaseUpdate(BaseModel):
    question: Optional[str] = Field(None, min_length=1, max_length=2000)
    expected_facts: Optional[list[str]] = None
    expected_answer: Optional[str] = None
    expected_document_id: Optional[UUID] = None
    tags: Optional[list[str]] = None
    enabled: Optional[bool] = None
    status: Optional[RagEvalCaseStatus] = None
    source_type: Optional[str] = None
    source_ref_id: Optional[str] = None
    retrieval_metadata: Optional[dict[str, Any]] = None

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
    status: RagEvalCaseStatus = "active"
    source_type: Optional[str] = None
    source_ref_id: Optional[str] = None
    retrieval_metadata: dict[str, Any] = Field(default_factory=dict)
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
