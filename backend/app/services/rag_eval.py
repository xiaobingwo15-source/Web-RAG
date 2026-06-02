import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from app.services import database
from app.services.gemini import generate_chat_response, get_llm_client, get_model_provider, get_primary_model
from app.services.retrieval import retrieve_context

logger = logging.getLogger(__name__)


@dataclass
class EvalScore:
    context_relevance_score: float
    groundedness_score: float
    answer_relevance_score: float
    passed: bool
    failure_reason: str | None = None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").casefold()).strip()


def _contains_fact(text: str, fact: str) -> bool:
    return _normalize(fact) in _normalize(text)


def _valid_sources(sources: list[dict]) -> list[dict]:
    return [source for source in sources if source.get("status") != "archived"]


def score_eval_case(
    question: str,
    expected_facts: list[str],
    answer: str,
    sources: list[dict],
    expected_document_id: str | None = None,
) -> EvalScore:
    del question
    facts = [fact.strip() for fact in expected_facts if fact and fact.strip()]
    valid_sources = _valid_sources(sources)
    source_text = "\n".join(
        str(source.get("content") or source.get("snippet") or "")
        for source in valid_sources
    )

    if not facts:
        answer_relevance = 1.0 if answer.strip() else 0.0
        context_relevance = 1.0 if valid_sources else 0.0
        groundedness = 1.0 if valid_sources and answer.strip() else 0.0
        missing_facts: list[str] = []
    else:
        answer_hits = sum(1 for fact in facts if _contains_fact(answer, fact))
        source_hits = sum(1 for fact in facts if _contains_fact(source_text, fact))
        answer_relevance = answer_hits / len(facts)
        context_relevance = source_hits / len(facts) if valid_sources else 0.0
        groundedness = source_hits / len(facts) if valid_sources else 0.0
        missing_facts = [fact for fact in facts if not _contains_fact(answer, fact)]

    failures = []
    if not valid_sources:
        failures.append("no sources returned")
    if expected_document_id and not any(str(source.get("document_id")) == expected_document_id for source in valid_sources):
        failures.append("expected document was not retrieved")
    if missing_facts:
        failures.append("missing expected facts: " + ", ".join(missing_facts))
    if groundedness < 0.7:
        failures.append(f"groundedness below threshold: {groundedness:.2f}")
    if answer_relevance < 0.7:
        failures.append(f"answer relevance below threshold: {answer_relevance:.2f}")

    return EvalScore(
        context_relevance_score=round(context_relevance, 4),
        groundedness_score=round(groundedness, 4),
        answer_relevance_score=round(answer_relevance, 4),
        passed=not failures,
        failure_reason="; ".join(failures) if failures else None,
    )


def _public_sources(sources: list[dict]) -> list[dict]:
    return [{key: value for key, value in source.items() if key != "content"} for source in sources]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def run_rag_eval(
    tenant_id: str,
    admin_user_id: str,
    access_token: str,
    retrieval_mode: str = "hybrid",
) -> dict:
    suite = database.get_or_create_default_eval_suite(tenant_id)
    cases = database.list_rag_eval_cases(tenant_id, enabled_only=True)
    provider = get_model_provider()
    model = get_primary_model()

    run = database.create_rag_eval_run(
        tenant_id=tenant_id,
        suite_id=suite["id"] if suite else None,
        retrieval_mode=retrieval_mode,
        model_provider=provider,
        model_name=model,
        total_cases=len(cases),
    )

    if not cases:
        run = database.update_rag_eval_run(
            tenant_id,
            run["id"],
            {
                "status": "completed",
                "completed_at": _now_iso(),
                "failure_reason": "No enabled eval cases",
            },
        )
        return {"run": run, "results": []}

    results = []
    try:
        client = get_llm_client()
        for case in cases:
            retrieval = await retrieve_context(
                access_token,
                admin_user_id,
                case["question"],
                mode=retrieval_mode,
                tenant_id=tenant_id,
            )
            sources = _valid_sources(retrieval.get("sources", []))
            answer = await generate_chat_response(
                client,
                case["question"],
                history=[],
                context_chunks=retrieval.get("chunks", []),
            )
            score = score_eval_case(
                question=case["question"],
                expected_facts=case.get("expected_facts") or [],
                answer=answer,
                sources=sources,
                expected_document_id=case.get("expected_document_id"),
            )
            result = database.insert_rag_eval_result(
                tenant_id=tenant_id,
                run_id=run["id"],
                case=case,
                answer=answer,
                sources=_public_sources(sources),
                score=score,
            )
            results.append(result)

        total = len(results)
        passed = sum(1 for result in results if result.get("passed"))
        avg_context = sum(float(r.get("context_relevance_score") or 0) for r in results) / total
        avg_grounded = sum(float(r.get("groundedness_score") or 0) for r in results) / total
        avg_answer = sum(float(r.get("answer_relevance_score") or 0) for r in results) / total
        run = database.update_rag_eval_run(
            tenant_id,
            run["id"],
            {
                "status": "completed",
                "passed_cases": passed,
                "avg_context_relevance_score": round(avg_context, 4),
                "avg_groundedness_score": round(avg_grounded, 4),
                "avg_answer_relevance_score": round(avg_answer, 4),
                "completed_at": _now_iso(),
            },
        )
    except Exception as exc:
        logger.exception("RAG eval run failed")
        run = database.update_rag_eval_run(
            tenant_id,
            run["id"],
            {
                "status": "failed",
                "failure_reason": str(exc),
                "completed_at": _now_iso(),
            },
        )
        raise

    return {"run": run, "results": results}
