import asyncio
import logging
from app.services.embeddings import get_embedding_client, get_embedding
from app.services.reranker import rerank_with_cohere
from app.services.qdrant_db import search_similar_chunks
from app.services.database import search_chunks_fts

logger = logging.getLogger(__name__)

VECTOR_SIMILARITY_THRESHOLD = 0.1


async def retrieve_context(
    token: str | None,
    user_id: str | None,
    message: str,
    mode: str = "hybrid",
    match_count: int = 5,
    target_user_id: str | None = None,
    tenant_id: str | None = None,
) -> dict:
    """Retrieve context chunks with source metadata.

    Returns:
        {
            "chunks": list[str],       # content strings for LLM consumption
            "sources": list[dict],     # [{id, document_id, content, score}, ...]
        }
    """
    if target_user_id is None:
        target_user_id = user_id
        # Authenticated clients search their tenant admin's shared knowledge base.
        try:
            from app.services.supabase import get_supabase_client_with_token
            from app.services.database import get_tenant_admin_user_id
            if not token or not user_id:
                raise ValueError("anonymous retrieval uses tenant scope")
            db = get_supabase_client_with_token(token)
            profile = db.table("profiles").select("role").eq("id", user_id).single().execute()
            if profile.data and profile.data.get("role") == "client":
                admin_id = get_tenant_admin_user_id(tenant_id) if tenant_id else None
                if admin_id:
                    target_user_id = admin_id
                    logger.info(f"Redirecting RAG search to tenant admin knowledge base: {admin_id}")
        except Exception as e:
            logger.warning(f"Error checking user role in retrieve_context: {e}")

    def _empty():
        return {"chunks": [], "sources": []}

    if mode == "fts":
        chunks = await asyncio.to_thread(search_chunks_fts, token, target_user_id, message, match_count, tenant_id)
        if not chunks:
            return _empty()
        sources = [{"id": c.get("id", ""), "document_id": c.get("document_id", ""), "content": c["content"], "score": c.get("rank", 0)} for c in chunks]
        logger.info(f"FTS retrieval: {len(sources)} chunks")
        return {"chunks": [s["content"] for s in sources], "sources": sources}

    print(f"[RETRIEVAL] query='{message[:80]}...', mode={mode}, target_user_id={target_user_id}")
    logger.info(f"Retrieval: query='{message[:80]}...', mode={mode}, user_id={target_user_id}, tenant_id={tenant_id}")

    if mode == "hybrid":
        # FTS doesn't need the embedding — run it concurrently with embedding generation
        embedding_task = get_embedding(get_embedding_client(), message)
        fts_task = asyncio.to_thread(search_chunks_fts, token, target_user_id, message, match_count * 2, tenant_id)
        query_embedding, fts_results = await asyncio.gather(embedding_task, fts_task)

        # Vector search starts only after embedding completes
        vector_results = await search_similar_chunks(
            target_user_id or "",
            query_embedding,
            match_count * 2,
            similarity_threshold=VECTOR_SIMILARITY_THRESHOLD,
            tenant_id=tenant_id,
        )

        print(f"[RETRIEVAL] Hybrid results: vector={len(vector_results)}, fts={len(fts_results)}")
        logger.info(f"Hybrid retrieval: vector={len(vector_results)} results, fts={len(fts_results)} results")

        if not vector_results and not fts_results:
            print(f"[RETRIEVAL] WARNING: NO results from Qdrant or FTS. Documents may not be indexed for user_id={target_user_id}")
            logger.warning("Hybrid retrieval: NO results from either Qdrant vector search or Supabase FTS. Check if documents are properly indexed.")
            return _empty()

        # Reciprocal Rank Fusion (RRF) merge
        rrf_k = 60
        combined: dict[str, dict] = {}

        for rank, chunk in enumerate(vector_results):
            cid = chunk["id"]
            combined[cid] = {"content": chunk["content"], "document_id": chunk.get("document_id", ""), "score": 1.0 / (rrf_k + rank + 1)}

        for rank, chunk in enumerate(fts_results):
            cid = chunk.get("id", f"fts_{rank}")
            if cid in combined:
                combined[cid]["score"] += 1.0 / (rrf_k + rank + 1)
            else:
                combined[cid] = {"content": chunk["content"], "document_id": chunk.get("document_id", ""), "score": 1.0 / (rrf_k + rank + 1)}

        sorted_results = sorted(combined.values(), key=lambda x: x["score"], reverse=True)
        candidates = [r["content"] for r in sorted_results[:match_count * 2]]
        candidate_metas = sorted_results[:match_count * 2]
        logger.info(f"Hybrid RRF merge: {len(combined)} unique candidates, top {len(candidates)} selected for reranking")

        if candidates:
            scored = await rerank_with_cohere(message, candidates, top_n=match_count)
            sources = []
            for s in scored:
                idx = s["index"]
                if idx < len(candidates):
                    meta = candidate_metas[idx]
                    sources.append({
                        "id": meta.get("id", ""),
                        "document_id": meta.get("document_id", ""),
                        "content": candidates[idx],
                        "score": s.get("score", meta["score"]),
                    })
            logger.info(f"Hybrid reranker: {len(scored)} scored -> {len(sources)} final results")
            return {"chunks": [s["content"] for s in sources], "sources": sources}

        # Fallback to vector-only
        logger.warning("Hybrid: RRF merge produced 0 candidates, falling back to vector-only")
        chunks = await search_similar_chunks(
            target_user_id or "",
            query_embedding,
            match_count,
            similarity_threshold=VECTOR_SIMILARITY_THRESHOLD,
            tenant_id=tenant_id,
        )
        if not chunks:
            return _empty()
        sources = [{"id": c["id"], "document_id": c.get("document_id", ""), "content": c["content"], "score": c.get("similarity", 0)} for c in chunks]
        return {"chunks": [s["content"] for s in sources], "sources": sources}

    # mode == "vector"
    query_embedding = await get_embedding(get_embedding_client(), message)
    chunks = await search_similar_chunks(
        target_user_id or "",
        query_embedding,
        match_count,
        similarity_threshold=VECTOR_SIMILARITY_THRESHOLD,
        tenant_id=tenant_id,
    )
    if not chunks:
        return _empty()
    sources = [{"id": c["id"], "document_id": c.get("document_id", ""), "content": c["content"], "score": c.get("similarity", 0)} for c in chunks]
    logger.info(f"Vector retrieval: {len(sources)} chunks")
    return {"chunks": [s["content"] for s in sources], "sources": sources}
