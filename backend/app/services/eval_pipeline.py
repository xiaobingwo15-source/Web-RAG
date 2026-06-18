"""RAGAS-style evaluation pipeline using LLM-as-judge scoring.

Provides:
- create_golden_test_set: Auto-generate Q&A pairs from document chunks
- evaluate_query: Score a single query/response with 4 RAGAS metrics
- run_eval_suite: Run full evaluation suite, return aggregate metrics
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.services.gemini import get_llm_client, generate_chat_response, PRIMARY_MODEL
from app.services.retrieval import retrieve_context
from app.services.database import get_db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class EvalTestCase:
    """A single Q&A pair generated from or evaluated against documents."""
    question: str
    expected_answer: str
    context: str = ""  # source chunk(s) the Q&A was derived from
    tags: list[str] = field(default_factory=list)


@dataclass
class EvalTestSet:
    """A collection of test cases, optionally tied to a document."""
    id: str = ""
    document_id: str = ""
    test_cases: list[EvalTestCase] = field(default_factory=list)
    created_at: str = ""


@dataclass
class MetricScore:
    """Individual metric score with reasoning."""
    name: str
    score: int  # 1-5
    reasoning: str = ""


@dataclass
class EvalResult:
    """Result of evaluating a single query."""
    question: str
    expected_answer: str
    actual_answer: str
    contexts: list[str]
    faithfulness: MetricScore = field(default_factory=lambda: MetricScore("faithfulness", 0))
    answer_relevance: MetricScore = field(default_factory=lambda: MetricScore("answer_relevance", 0))
    context_precision: MetricScore = field(default_factory=lambda: MetricScore("context_precision", 0))
    context_recall: MetricScore = field(default_factory=lambda: MetricScore("context_recall", 0))

    @property
    def average_score(self) -> float:
        scores = [
            self.faithfulness.score,
            self.answer_relevance.score,
            self.context_precision.score,
            self.context_recall.score,
        ]
        return sum(scores) / len(scores) if scores else 0.0

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "expected_answer": self.expected_answer,
            "actual_answer": self.actual_answer,
            "contexts": self.contexts,
            "faithfulness": {"score": self.faithfulness.score, "reasoning": self.faithfulness.reasoning},
            "answer_relevance": {"score": self.answer_relevance.score, "reasoning": self.answer_relevance.reasoning},
            "context_precision": {"score": self.context_precision.score, "reasoning": self.context_precision.reasoning},
            "context_recall": {"score": self.context_recall.score, "reasoning": self.context_recall.reasoning},
            "average_score": round(self.average_score, 2),
        }


@dataclass
class EvalSuiteResult:
    """Aggregate results from running an evaluation suite."""
    run_id: str = ""
    total_cases: int = 0
    avg_faithfulness: float = 0.0
    avg_answer_relevance: float = 0.0
    avg_context_precision: float = 0.0
    avg_context_recall: float = 0.0
    avg_overall: float = 0.0
    results: list[EvalResult] = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    config_json: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "total_cases": self.total_cases,
            "metrics": {
                "faithfulness": round(self.avg_faithfulness, 2),
                "answer_relevance": round(self.avg_answer_relevance, 2),
                "context_precision": round(self.avg_context_precision, 2),
                "context_recall": round(self.avg_context_recall, 2),
                "overall": round(self.avg_overall, 2),
            },
            "results": [r.to_dict() for r in self.results],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "config": self.config_json,
        }


# ---------------------------------------------------------------------------
# LLM-as-judge prompts
# ---------------------------------------------------------------------------

FAITHFULNESS_PROMPT = """You are evaluating the faithfulness of an answer relative to the provided context.

Faithfulness measures whether the answer stays true to the information in the context. A faithful answer does not introduce claims that are unsupported by or contradict the context.

Score 1-5:
1 - Completely unfaithful: answer contradicts or ignores the context entirely
2 - Mostly unfaithful: answer introduces significant unsupported claims
3 - Partially faithful: answer mixes supported and unsupported claims
4 - Mostly faithful: answer is largely supported with minor unsupported details
5 - Completely faithful: every claim in the answer is grounded in the context

Context:
{context}

Question: {question}
Answer: {answer}

Respond with ONLY a JSON object: {{"score": <1-5>, "reasoning": "<brief explanation>"}}"""


ANSWER_RELEVANCE_PROMPT = """You are evaluating how relevant an answer is to the question asked.

Answer relevance measures whether the answer actually addresses what was asked, not whether it is correct.

Score 1-5:
1 - Completely irrelevant: answer does not address the question at all
2 - Mostly irrelevant: answer tangentially relates but misses the core question
3 - Partially relevant: answer addresses part of the question but misses key aspects
4 - Mostly relevant: answer addresses the question with minor gaps
5 - Completely relevant: answer directly and fully addresses the question

Question: {question}
Answer: {answer}

Respond with ONLY a JSON object: {{"score": <1-5>, "reasoning": "<brief explanation>"}}"""


CONTEXT_PRECISION_PROMPT = """You are evaluating the precision of retrieved contexts for answering a question.

Context precision measures whether the retrieved contexts are relevant to the question. High precision means most retrieved contexts are useful for answering.

Score 1-5:
1 - No relevant context: none of the contexts relate to the question
2 - Low precision: few contexts are relevant, most are noise
3 - Medium precision: roughly half the contexts are relevant
4 - High precision: most contexts are relevant with minor noise
5 - Perfect precision: every context is directly relevant to the question

Question: {question}

Retrieved contexts:
{context}

Respond with ONLY a JSON object: {{"score": <1-5>, "reasoning": "<brief explanation>"}}"""


CONTEXT_RECALL_PROMPT = """You are evaluating whether the retrieved contexts contain the information needed to produce the expected answer.

Context recall measures coverage: do the contexts contain the key information from the expected answer?

Score 1-5:
1 - No coverage: contexts contain none of the information needed for the expected answer
2 - Low coverage: contexts contain a small fraction of the needed information
3 - Medium coverage: contexts contain about half the needed information
4 - High coverage: contexts contain most of the needed information
5 - Full coverage: contexts contain all the information needed for the expected answer

Expected answer: {expected_answer}

Retrieved contexts:
{context}

Respond with ONLY a JSON object: {{"score": <1-5>, "reasoning": "<brief explanation>"}}"""


GOLDEN_TEST_SET_PROMPT = """You are generating evaluation test cases for a RAG (Retrieval-Augmented Generation) system.

Given a document chunk, generate {num_questions} question-answer pairs that could be used to test whether a RAG system correctly retrieves and answers based on this content.

Requirements:
- Questions should be specific and answerable from the chunk
- Answers should be concise but complete, grounded in the chunk content
- Mix question types: factual, comparison, definition, how-to
- Do NOT reference "the document" or "the text" in questions — ask naturally

Document chunk:
{chunk}

Respond with ONLY a JSON array of objects:
[{{"question": "...", "answer": "..."}}, ...]"""


# ---------------------------------------------------------------------------
# LLM helper
# ---------------------------------------------------------------------------

async def _llm_judge(system_prompt: str, user_prompt: str) -> dict:
    """Call the LLM and parse a JSON response. Returns dict with score+reasoning."""
    client = get_llm_client()
    try:
        response = await client.chat.completions.create(
            model=PRIMARY_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=300,
        )
        raw = response.choices[0].message.content or ""

        # Extract JSON from potential markdown fences
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if json_match:
            parsed = json.loads(json_match.group())
            if isinstance(parsed, dict):
                return parsed

        logger.warning("LLM judge returned non-JSON: %s", raw[:200])
        return {"score": 0, "reasoning": f"Failed to parse LLM response: {raw[:100]}"}

    except Exception as e:
        logger.error("LLM judge call failed: %s", e)
        return {"score": 0, "reasoning": f"LLM call error: {str(e)}"}


async def _llm_generate(prompt: str, max_tokens: int = 1500) -> str:
    """Call the LLM for text generation (golden test set creation)."""
    client = get_llm_client()
    try:
        response = await client.chat.completions.create(
            model=PRIMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error("LLM generation call failed: %s", e)
        return ""


# ---------------------------------------------------------------------------
# Core evaluation functions
# ---------------------------------------------------------------------------

async def evaluate_query(
    query: str,
    expected_answer: str,
    actual_answer: str,
    contexts: list[str],
) -> EvalResult:
    """Score a single query/response with 4 RAGAS-style metrics.

    Args:
        query: The user question
        expected_answer: The ground-truth answer
        actual_answer: The system-generated answer
        contexts: The retrieved context chunks

    Returns:
        EvalResult with faithfulness, answer_relevance, context_precision, context_recall
    """
    context_text = "\n---\n".join(contexts) if contexts else "(no context)"

    # Run all 4 judges in parallel
    faith_task = _llm_judge(
        FAITHFULNESS_PROMPT,
        f"Context:\n{context_text}\n\nQuestion: {query}\nAnswer: {actual_answer}",
    )
    relevance_task = _llm_judge(
        ANSWER_RELEVANCE_PROMPT,
        f"Question: {query}\nAnswer: {actual_answer}",
    )
    precision_task = _llm_judge(
        CONTEXT_PRECISION_PROMPT,
        f"Question: {query}\n\nRetrieved contexts:\n{context_text}",
    )
    recall_task = _llm_judge(
        CONTEXT_RECALL_PROMPT,
        f"Expected answer: {expected_answer}\n\nRetrieved contexts:\n{context_text}",
    )

    faith, relevance, precision, recall = await asyncio.gather(
        faith_task, relevance_task, precision_task, recall_task
    )

    def _clamp_score(val) -> int:
        try:
            s = int(val)
            return max(1, min(5, s))
        except (ValueError, TypeError):
            return 0

    return EvalResult(
        question=query,
        expected_answer=expected_answer,
        actual_answer=actual_answer,
        contexts=contexts,
        faithfulness=MetricScore("faithfulness", _clamp_score(faith.get("score")), faith.get("reasoning", "")),
        answer_relevance=MetricScore("answer_relevance", _clamp_score(relevance.get("score")), relevance.get("reasoning", "")),
        context_precision=MetricScore("context_precision", _clamp_score(precision.get("score")), precision.get("reasoning", "")),
        context_recall=MetricScore("context_recall", _clamp_score(recall.get("score")), recall.get("reasoning", "")),
    )


async def create_golden_test_set(
    chunks: list[dict],
    num_questions_per_chunk: int = 3,
) -> list[EvalTestCase]:
    """Generate Q&A pairs from document chunks using LLM.

    Args:
        chunks: List of dicts with 'content' key (and optionally 'document_id', 'id')
        num_questions_per_chunk: How many Q&A pairs per chunk

    Returns:
        List of EvalTestCase instances
    """
    test_cases: list[EvalTestCase] = []

    # Process chunks concurrently with a semaphore to avoid rate limits
    sem = asyncio.Semaphore(3)

    async def _process_chunk(chunk: dict) -> list[EvalTestCase]:
        async with sem:
            content = chunk.get("content", "")
            if not content or len(content.strip()) < 50:
                return []

            prompt = GOLDEN_TEST_SET_PROMPT.format(
                num_questions=num_questions_per_chunk,
                chunk=content[:3000],  # limit to avoid token overflow
            )
            raw = await _llm_generate(prompt)

            # Parse JSON array from response
            json_match = re.search(r"\[[\s\S]*\]", raw)
            if not json_match:
                logger.warning("Failed to parse golden test set JSON for chunk: %s", content[:80])
                return []

            try:
                pairs = json.loads(json_match.group())
            except json.JSONDecodeError:
                logger.warning("Invalid JSON in golden test set response")
                return []

            cases = []
            for pair in pairs:
                if isinstance(pair, dict) and "question" in pair and "answer" in pair:
                    cases.append(EvalTestCase(
                        question=pair["question"].strip(),
                        expected_answer=pair["answer"].strip(),
                        context=content[:500],
                        tags=["auto-generated"],
                    ))
            return cases

    tasks = [_process_chunk(chunk) for chunk in chunks]
    results = await asyncio.gather(*tasks)
    for cases in results:
        test_cases.extend(cases)

    logger.info("Generated %d test cases from %d chunks", len(test_cases), len(chunks))
    return test_cases


# Default path for the golden test set fixture
_GOLDEN_FIXTURE_PATH = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "golden_test_set.json"


def load_golden_test_set(path: str | Path | None = None) -> list[EvalTestCase]:
    """Load a golden test set from a JSON fixture file.

    Args:
        path: Path to the JSON file. Defaults to backend/tests/fixtures/golden_test_set.json.

    Returns:
        List of EvalTestCase instances (only cases where validated=True, if the field exists).

    Raises:
        FileNotFoundError: If the fixture file does not exist.
        ValueError: If the JSON structure is invalid.
    """
    fixture_path = Path(path) if path else _GOLDEN_FIXTURE_PATH
    if not fixture_path.exists():
        raise FileNotFoundError(f"Golden test set not found: {fixture_path}")

    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict) or "test_cases" not in data:
        raise ValueError(f"Invalid golden test set format: expected dict with 'test_cases' key")

    test_cases: list[EvalTestCase] = []
    for case in data["test_cases"]:
        if not isinstance(case, dict):
            logger.warning("Skipping non-dict test case entry")
            continue
        if "question" not in case or "expected_answer" not in case:
            logger.warning("Skipping test case missing required fields: %s", case)
            continue
        test_cases.append(EvalTestCase(
            question=case["question"],
            expected_answer=case["expected_answer"],
            context=case.get("context", ""),
            tags=case.get("tags", []),
        ))

    logger.info("Loaded %d test cases from %s", len(test_cases), fixture_path)
    return test_cases


async def generate_answer(query: str, contexts: list[str]) -> str:
    """Generate an answer using the RAG system's LLM given query and contexts."""
    client = get_llm_client()
    return await generate_chat_response(
        client,
        query,
        history=[],
        context_chunks=contexts if contexts else None,
    )


async def run_eval_suite(
    test_cases: list[EvalTestCase],
    retrieval_mode: str = "hybrid",
    access_token: str | None = None,
    user_id: str | None = None,
    tenant_id: str | None = None,
    config_json: dict | None = None,
) -> EvalSuiteResult:
    """Run the full evaluation suite against the RAG pipeline.

    For each test case:
    1. Retrieve context from the RAG system
    2. Generate an answer
    3. Score with all 4 RAGAS metrics

    Args:
        test_cases: The golden test set
        retrieval_mode: "hybrid", "vector", or "fts"
        access_token: Supabase auth token for retrieval
        user_id: User ID for retrieval
        tenant_id: Tenant ID for retrieval

    Returns:
        EvalSuiteResult with aggregate metrics
    """
    started_at = datetime.now(UTC).isoformat()
    results: list[EvalResult] = []
    total = len(test_cases)

    logger.info("Starting eval suite: %d test cases, retrieval_mode=%s", total, retrieval_mode)

    for i, tc in enumerate(test_cases):
        case_num = i + 1
        logger.info("[%d/%d] Evaluating: %s", case_num, total, tc.question[:80])

        try:
            # Step 1: Retrieve context
            logger.info("[%d/%d] Retrieving context...", case_num, total)
            retrieval = await retrieve_context(
                access_token,
                user_id,
                tc.question,
                mode=retrieval_mode,
                tenant_id=tenant_id,
            )
            contexts = retrieval.get("chunks", [])
            logger.info("[%d/%d] Retrieved %d context chunks", case_num, total, len(contexts))

            # Step 2: Generate answer
            logger.info("[%d/%d] Generating answer...", case_num, total)
            actual_answer = await generate_answer(tc.question, contexts)

            # Step 3: Score with LLM-as-judge
            logger.info("[%d/%d] Scoring with LLM-as-judge...", case_num, total)
            result = await evaluate_query(
                query=tc.question,
                expected_answer=tc.expected_answer,
                actual_answer=actual_answer,
                contexts=contexts,
            )
            results.append(result)
            logger.info(
                "[%d/%d] Done — scores: faith=%d rel=%d prec=%d recall=%d avg=%.1f",
                case_num, total,
                result.faithfulness.score,
                result.answer_relevance.score,
                result.context_precision.score,
                result.context_recall.score,
                result.average_score,
            )

        except Exception as e:
            logger.error("[%d/%d] FAILED: %s", case_num, total, e)
            results.append(EvalResult(
                question=tc.question,
                expected_answer=tc.expected_answer,
                actual_answer=f"ERROR: {str(e)}",
                contexts=[],
            ))

    logger.info("Eval suite complete: %d/%d cases processed", len(results), total)

    # Compute aggregates
    n = len(results) or 1
    suite = EvalSuiteResult(
        total_cases=len(results),
        avg_faithfulness=sum(r.faithfulness.score for r in results) / n,
        avg_answer_relevance=sum(r.answer_relevance.score for r in results) / n,
        avg_context_precision=sum(r.context_precision.score for r in results) / n,
        avg_context_recall=sum(r.context_recall.score for r in results) / n,
        avg_overall=sum(r.average_score for r in results) / n,
        results=results,
        started_at=started_at,
        completed_at=datetime.now(UTC).isoformat(),
        config_json=config_json or {},
    )

    return suite


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def save_eval_run(tenant_id: str, suite_result: EvalSuiteResult, test_set_id: str = "") -> dict:
    """Persist an evaluation run to Supabase eval_runs table."""
    db = get_db()
    run_data = {
        "tenant_id": tenant_id,
        "test_set_id": test_set_id or None,
        "total_cases": suite_result.total_cases,
        "metrics_json": {
            "faithfulness": round(suite_result.avg_faithfulness, 2),
            "answer_relevance": round(suite_result.avg_answer_relevance, 2),
            "context_precision": round(suite_result.avg_context_precision, 2),
            "context_recall": round(suite_result.avg_context_recall, 2),
            "overall": round(suite_result.avg_overall, 2),
        },
        "results_json": [r.to_dict() for r in suite_result.results],
        "started_at": suite_result.started_at,
        "completed_at": suite_result.completed_at,
    }
    if suite_result.config_json:
        run_data["config_json"] = suite_result.config_json
    result = db.table("eval_runs").insert(run_data).execute()
    return result.data[0] if result.data else run_data


def save_eval_test_set(tenant_id: str, document_id: str, test_cases: list[EvalTestCase]) -> dict:
    """Persist a golden test set to Supabase eval_test_sets table."""
    db = get_db()
    cases_data = [
        {
            "question": tc.question,
            "expected_answer": tc.expected_answer,
            "context": tc.context,
            "tags": tc.tags,
        }
        for tc in test_cases
    ]
    ts_data = {
        "tenant_id": tenant_id,
        "document_id": document_id or None,
        "test_cases_json": cases_data,
        "case_count": len(cases_data),
    }
    result = db.table("eval_test_sets").insert(ts_data).execute()
    return result.data[0] if result.data else ts_data


def list_eval_runs(tenant_id: str, limit: int = 20) -> list[dict]:
    """List recent evaluation runs for a tenant."""
    db = get_db()
    result = (
        db.table("eval_runs")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


def get_eval_run(tenant_id: str, run_id: str) -> dict | None:
    """Get a specific evaluation run by ID."""
    db = get_db()
    result = (
        db.table("eval_runs")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("id", run_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None
