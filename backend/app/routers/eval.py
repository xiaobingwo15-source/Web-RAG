"""API endpoints for RAGAS-style RAG evaluation pipeline.

Provides:
- POST /api/eval/generate-test-set: Auto-generate golden test set from documents
- POST /api/eval/run: Run evaluation suite (existing test set or auto-generated)
- GET  /api/eval/runs: List past evaluation runs
- GET  /api/eval/runs/{run_id}: Get detailed evaluation run results
"""

import logging
from datetime import UTC, datetime
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.config import Settings
from app.middleware.auth import get_current_user
from app.services.eval_pipeline import (
    create_golden_test_set,
    run_eval_suite,
    save_eval_run,
    save_eval_test_set,
    list_eval_runs,
    get_eval_run,
    EvalTestCase,
)
from app.services.database import get_user_documents, get_document_chunks
from app.services.audit import log_operation

logger = logging.getLogger(__name__)

router = APIRouter()


def _verify_admin(user) -> None:
    if user.role != "admin" or not user.tenant_id or user.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


# --- Request/Response models ---

class GenerateTestSetRequest(BaseModel):
    document_id: str = Field(..., description="Document ID to generate test cases from")
    num_questions_per_chunk: int = Field(default=3, ge=1, le=10)


class RunEvalRequest(BaseModel):
    test_set_id: str | None = Field(default=None, description="Existing test set ID. If omitted, uses auto-generated set from all docs.")
    document_id: str | None = Field(default=None, description="Document ID for auto-generation (if test_set_id not provided)")
    retrieval_mode: str = Field(default="hybrid", pattern="^(vector|fts|hybrid)$")
    # Experiment tracking config fields
    chunk_size: int | None = Field(default=None, ge=100, le=5000, description="Chunk size used for this experiment")
    top_k: int | None = Field(default=None, ge=1, le=50, description="Number of chunks to retrieve")
    reranker_model: str | None = Field(default=None, description="Reranker model used (default: rerank-v3.5)")
    embedding_model: str | None = Field(default=None, description="Embedding model used")
    notes: str = Field(default="", max_length=1000, description="Free-text notes about this experiment")


class TestCaseResponse(BaseModel):
    question: str
    expected_answer: str
    context: str
    tags: list[str]


class TestSetResponse(BaseModel):
    id: str
    document_id: str | None
    case_count: int
    test_cases: list[TestCaseResponse]
    created_at: str


# --- Endpoints ---

@router.post("/generate-test-set", response_model=TestSetResponse)
async def generate_test_set_endpoint(request_body: GenerateTestSetRequest, request: Request, user=Depends(get_current_user)):
    """Generate a golden test set from a document's chunks using LLM."""
    _verify_admin(user)

    # Fetch document chunks
    chunks = get_document_chunks(user.access_token, request_body.document_id)
    if not chunks:
        raise HTTPException(status_code=404, detail="Document not found or has no chunks")

    # Generate test cases
    chunk_dicts = [{"content": c["content"], "document_id": request_body.document_id} for c in chunks]
    test_cases = await create_golden_test_set(chunk_dicts, request_body.num_questions_per_chunk)

    if not test_cases:
        raise HTTPException(status_code=422, detail="Failed to generate test cases from document")

    # Persist test set
    saved = save_eval_test_set(user.tenant_id, request_body.document_id, test_cases)
    log_operation(
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        actor_email=getattr(user, "email", None),
        actor_role=user.role,
        action="eval_test_set.create",
        resource_type="eval_test_set",
        resource_id=saved.get("id"),
        after={"id": saved.get("id"), "document_id": request_body.document_id, "case_count": len(test_cases)},
        request=request,
    )

    return TestSetResponse(
        id=saved.get("id", ""),
        document_id=request_body.document_id,
        case_count=len(test_cases),
        test_cases=[
            TestCaseResponse(question=tc.question, expected_answer=tc.expected_answer, context=tc.context, tags=tc.tags)
            for tc in test_cases
        ],
        created_at=saved.get("created_at", ""),
    )


@router.post("/run")
async def run_eval_endpoint(request_body: RunEvalRequest, request: Request, user=Depends(get_current_user)):
    """Run a RAGAS-style evaluation suite.

    Either provide test_set_id for an existing test set, or document_id to
    auto-generate one. If neither is provided, generates from all user documents.
    """
    _verify_admin(user)

    from app.services.supabase import get_supabase_client
    db = get_supabase_client()

    test_cases: list[EvalTestCase] = []
    test_set_id = ""

    if request_body.test_set_id:
        # Load existing test set
        result = (
            db.table("eval_test_sets")
            .select("*")
            .eq("id", request_body.test_set_id)
            .eq("tenant_id", user.tenant_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Test set not found")
        ts = result.data[0]
        test_set_id = ts["id"]
        for tc in ts.get("test_cases_json", []):
            test_cases.append(EvalTestCase(
                question=tc["question"],
                expected_answer=tc["expected_answer"],
                context=tc.get("context", ""),
                tags=tc.get("tags", []),
            ))

    elif request_body.document_id:
        # Auto-generate from a single document
        chunks = get_document_chunks(user.access_token, request_body.document_id)
        if not chunks:
            raise HTTPException(status_code=404, detail="Document not found or has no chunks")
        chunk_dicts = [{"content": c["content"], "document_id": request_body.document_id} for c in chunks]
        test_cases = await create_golden_test_set(chunk_dicts)
        if test_cases:
            saved = save_eval_test_set(user.tenant_id, request_body.document_id, test_cases)
            test_set_id = saved.get("id", "")

    else:
        # Auto-generate from all user documents (sample chunks)
        docs = get_user_documents(user.access_token, user.id, user.tenant_id)
        if not docs:
            raise HTTPException(status_code=404, detail="No documents found")
        all_chunks = []
        for doc in docs[:5]:  # Limit to 5 docs to avoid token overflow
            doc_chunks = get_document_chunks(user.access_token, doc["id"])
            for c in doc_chunks[:10]:  # Limit chunks per doc
                all_chunks.append({"content": c["content"], "document_id": doc["id"]})
        if not all_chunks:
            raise HTTPException(status_code=422, detail="No document chunks found")
        test_cases = await create_golden_test_set(all_chunks)
        if test_cases:
            saved = save_eval_test_set(user.tenant_id, "", test_cases)
            test_set_id = saved.get("id", "")

    if not test_cases:
        raise HTTPException(status_code=422, detail="No test cases available for evaluation")

    # Build experiment config for tracking
    settings = Settings()
    config_json = {
        "retrieval_mode": request_body.retrieval_mode,
        "chunk_size": request_body.chunk_size if request_body.chunk_size is not None else settings.child_chunk_size,
        "top_k": request_body.top_k if request_body.top_k is not None else 5,
        "reranker_model": request_body.reranker_model or "rerank-v3.5",
        "embedding_model": request_body.embedding_model or settings.embedding_model,
        "notes": request_body.notes,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    # Run evaluation
    suite_result = await run_eval_suite(
        test_cases=test_cases,
        retrieval_mode=request_body.retrieval_mode,
        access_token=user.access_token,
        user_id=user.id,
        tenant_id=user.tenant_id,
        config_json=config_json,
    )

    # Persist results
    run_record = save_eval_run(user.tenant_id, suite_result, test_set_id)
    suite_result.run_id = run_record.get("id", "")
    log_operation(
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        actor_email=getattr(user, "email", None),
        actor_role=user.role,
        action="eval_run.execute",
        resource_type="eval_run",
        resource_id=suite_result.run_id,
        after={"run_id": suite_result.run_id, "test_set_id": test_set_id},
        request=request,
    )

    return suite_result.to_dict()


@router.get("/runs")
async def list_eval_runs_endpoint(user=Depends(get_current_user)):
    """List recent evaluation runs for the current tenant."""
    _verify_admin(user)
    runs = list_eval_runs(user.tenant_id)
    return {"runs": runs}


@router.get("/runs/{run_id}")
async def get_eval_run_endpoint(run_id: str, user=Depends(get_current_user)):
    """Get detailed results for a specific evaluation run."""
    _verify_admin(user)
    run = get_eval_run(user.tenant_id, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Eval run not found")
    return run
