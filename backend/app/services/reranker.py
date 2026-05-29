import asyncio
import logging
import os

import cohere
from langfuse import observe

logger = logging.getLogger(__name__)

COHERE_MODEL = "rerank-english-v3.0"


def _keyword_overlap_score(query: str, document: str) -> float:
    """Simple term-overlap scoring when Cohere is unavailable."""
    query_terms = set(query.lower().split())
    doc_terms = set(document.lower().split())
    if not query_terms:
        return 0.0
    overlap = query_terms & doc_terms
    return len(overlap) / len(query_terms)


def _get_cohere_client() -> cohere.ClientV2:
    return cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])


@observe(name="rerank_with_cohere", as_type="generation")
async def rerank_with_cohere(
    query: str,
    documents: list[str],
    top_n: int = 5,
) -> list[dict]:
    if not documents:
        return []

    try:
        client = _get_cohere_client()
        response = await asyncio.to_thread(
            client.rerank,
            model=COHERE_MODEL,
            query=query,
            documents=documents,
            top_n=top_n,
            return_documents=False,
        )
    except Exception as e:
        logger.warning(f"Cohere rerank failed, using keyword-overlap fallback: {e}")
        scored = [
            {"index": i, "score": _keyword_overlap_score(query, doc)}
            for i, doc in enumerate(documents)
        ]
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_n]

    scored = [{"index": r.index, "score": r.relevance_score} for r in response.results]
    logger.info(f"Cohere reranked {len(documents)} documents -> top {len(scored)}")
    return scored
