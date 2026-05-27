import logging
from app.services.embeddings import get_embedding_client, get_embedding
from app.services.reranker import rerank_with_gemini
from app.services.gemini import get_gemini_client
from app.services.database import search_similar_chunks, search_chunks_fts, hybrid_search

logger = logging.getLogger(__name__)


async def retrieve_context(
    token: str,
    user_id: str,
    message: str,
    mode: str = "hybrid",
    match_count: int = 5,
) -> list[str]:
    if mode == "fts":
        chunks = search_chunks_fts(token, user_id, message, match_count)
        results = [chunk["content"] for chunk in chunks]
        logger.info(f"FTS retrieval: {len(results)} chunks")
        return results

    embedding_client = get_embedding_client()
    query_embedding = await get_embedding(embedding_client, message)

    if mode == "hybrid":
        raw = hybrid_search(token, user_id, query_embedding, message, match_count * 2)
        if raw:
            candidates = [chunk["content"] for chunk in raw]
            client = get_gemini_client()
            scored = await rerank_with_gemini(client, message, candidates, top_n=match_count)
            results = [candidates[s["index"]] for s in scored if s["index"] < len(candidates)]
            logger.info(f"Hybrid retrieval: {len(raw)} candidates -> {len(results)} reranked")
            return results
        logger.info("Hybrid: no FTS matches, falling back to vector")
        chunks = search_similar_chunks(token, user_id, query_embedding, match_count)
        return [chunk["content"] for chunk in chunks]

    # mode == "vector"
    chunks = search_similar_chunks(token, user_id, query_embedding, match_count)
    results = [chunk["content"] for chunk in chunks]
    logger.info(f"Vector retrieval: {len(results)} chunks")
    return results
