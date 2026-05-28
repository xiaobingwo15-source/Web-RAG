import asyncio
import logging
import os

import cohere
from langfuse import observe

logger = logging.getLogger(__name__)

COHERE_MODEL = "rerank-english-v3.0"


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
        logger.warning(f"Cohere rerank failed, using default scoring: {e}")
        return [{"index": i, "score": 1.0 - i * 0.1} for i in range(min(top_n, len(documents)))]

    scored = [{"index": r.index, "score": r.relevance_score} for r in response.results]
    logger.info(f"Cohere reranked {len(documents)} documents -> top {len(scored)}")
    return scored
