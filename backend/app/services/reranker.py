import asyncio
import logging
import re

import cohere
from langfuse import observe

from app.config import Settings

logger = logging.getLogger(__name__)

COHERE_MODEL = "rerank-v3.5"

_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "must",
    "i", "me", "my", "we", "our", "you", "your", "he", "she", "it",
    "they", "them", "his", "her", "its", "their",
    "this", "that", "these", "those", "what", "which", "who", "whom",
    "where", "when", "why", "how",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as",
    "into", "about", "between", "through", "after", "before",
    "and", "but", "or", "not", "no", "nor",
    "if", "then", "else", "so", "than", "too", "very",
    "just", "also", "now", "here", "there",
})


def _tokenize(text: str) -> set[str]:
    """Lowercase, strip punctuation, remove stop words."""
    tokens = re.findall(r'[a-z0-9]+', text.lower())
    return {t for t in tokens if t not in _STOP_WORDS and len(t) > 1}


def _keyword_overlap_score(query: str, document: str) -> float:
    """Term-overlap scoring with punctuation stripping and stop word removal."""
    query_terms = _tokenize(query)
    doc_terms = _tokenize(document)
    if not query_terms:
        return 0.0
    overlap = query_terms & doc_terms
    return len(overlap) / len(query_terms)


def _get_cohere_client() -> cohere.ClientV2:
    api_key = Settings().get_cohere_api_key
    if not api_key:
        raise RuntimeError("COHERE_API_KEY is not configured")
    return cohere.ClientV2(api_key=api_key)


@observe(name="rerank_with_cohere", as_type="generation")
async def rerank_with_cohere(
    query: str,
    documents: list[str],
    top_n: int = 5,
    fallback_scores: list[float] | None = None,
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
        )
    except Exception as e:
        if fallback_scores and len(fallback_scores) == len(documents):
            logger.warning(f"Cohere rerank failed, using provided fallback scores: {e}")
            scored = [
                {"index": i, "score": fallback_scores[i]}
                for i in range(len(documents))
            ]
            scored.sort(key=lambda x: x["score"], reverse=True)
            return scored[:top_n]

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
