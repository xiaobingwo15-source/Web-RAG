import asyncio
import logging
import re
import time
from app.services.embeddings import get_embedding_client, get_embedding
from app.services.reranker import rerank_with_cohere
from app.services.qdrant_db import search_similar_chunks, get_parent_chunks_by_ids
from app.services.database import get_documents_by_ids, search_chunks_fts, log_retrieval
from app.services.performance import elapsed_ms, log_latency, monotonic_ms
from app.services.semantic_cache import get_semantic_cache

logger = logging.getLogger(__name__)

VECTOR_SIMILARITY_THRESHOLD = 0.1
MMR_LAMBDA = 0.5  # Balance between relevance (1.0) and diversity (0.0)
MAX_RETRIEVAL_LOG_ITEMS = 10
MAX_RETRIEVAL_LOG_TEXT_CHARS = 2000


def _snippet(content: str, limit: int = 240) -> str:
    text = " ".join((content or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _truncate_log_text(value: str | None, limit: int = MAX_RETRIEVAL_LOG_TEXT_CHARS) -> str:
    text = value or ""
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _loggable_retrieval_evidence(sources: list[dict], chunks: list[str]) -> tuple[list[dict], list[str]]:
    bounded_sources = []
    for source in sources[:MAX_RETRIEVAL_LOG_ITEMS]:
        bounded_sources.append({
            "document_id": source.get("document_id"),
            "chunk_id": source.get("chunk_id"),
            "filename": source.get("filename"),
            "score": source.get("score"),
            "snippet": _truncate_log_text(source.get("snippet")),
            "content": _truncate_log_text(source.get("content")),
            "retrieval_mode": source.get("retrieval_mode"),
        })
    bounded_chunks = [
        _truncate_log_text(chunk)
        for chunk in chunks[:MAX_RETRIEVAL_LOG_ITEMS]
    ]
    return bounded_sources, bounded_chunks


def _tokenize(text: str) -> set[str]:
    """Simple whitespace + lowercase tokenization for overlap comparison."""
    return set(text.lower().split())


def _text_overlap(a: str, b: str) -> float:
    """Jaccard similarity between two texts (token-level overlap)."""
    tokens_a = _tokenize(a)
    tokens_b = _tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _mmr_diversify(
    candidates: list[dict],
    lambda_param: float = MMR_LAMBDA,
    top_n: int | None = None,
) -> list[dict]:
    """Maximal Marginal Relevance diversification using text overlap.

    Balances relevance (RRF score) with diversity (low overlap with already-selected).
    Uses text Jaccard similarity instead of embedding cosine similarity
    to avoid expensive re-embedding of all candidates.

    Args:
        candidates: list of dicts with 'score' and 'content' keys
        lambda_param: 1.0 = pure relevance, 0.0 = pure diversity
        top_n: number of results to return (defaults to len(candidates))

    Returns:
        diversified list of candidates
    """
    if not candidates or lambda_param >= 1.0:
        return candidates[:top_n] if top_n else candidates

    n = top_n or len(candidates)
    selected: list[dict] = []
    remaining = list(candidates)

    # Normalize scores to [0, 1] for fair comparison
    max_score = max(c["score"] for c in candidates) if candidates else 1.0
    min_score = min(c["score"] for c in candidates) if candidates else 0.0
    score_range = max_score - min_score or 1.0

    while remaining and len(selected) < n:
        best_idx = -1
        best_mmr = float("-inf")

        for i, candidate in enumerate(remaining):
            relevance = (candidate["score"] - min_score) / score_range

            # Max similarity to any already-selected document
            if selected:
                max_sim = max(
                    _text_overlap(candidate["content"], s["content"])
                    for s in selected
                )
            else:
                max_sim = 0.0

            mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim
            if mmr_score > best_mmr:
                best_mmr = mmr_score
                best_idx = i

        if best_idx >= 0:
            selected.append(remaining.pop(best_idx))

    return selected


async def _resolve_parents(sources: list[dict]) -> list[dict]:
    """Replace child chunk content with its parent chunk content.

    When parent-child chunking is active, search results contain child chunks
    (fine-grained, embedded).  This function batch-fetches the corresponding
    parent chunks from Qdrant and swaps the child text for the richer parent
    text.  Multiple children from the same parent are collapsed into one entry
    (the highest-scoring child's score is kept).
    """
    # Collect unique parent IDs
    parent_ids = list({s["parent_id"] for s in sources if s.get("parent_id")})
    if not parent_ids:
        return sources  # no parent-child relationship, return as-is

    parent_map = await get_parent_chunks_by_ids(parent_ids)
    if not parent_map:
        logger.warning("Parent chunk lookup returned empty for IDs: %s", parent_ids)
        return sources

    # Group by parent_id, keep best-scoring child per parent
    grouped: dict[str, dict] = {}
    for s in sources:
        pid = s.get("parent_id")
        if pid and pid in parent_map:
            if pid not in grouped or s.get("score", 0) > grouped[pid].get("score", 0):
                grouped[pid] = {
                    "chunk_id": pid,
                    "document_id": s.get("document_id") or parent_map[pid].get("document_id", ""),
                    "filename": s.get("filename"),
                    "content": parent_map[pid]["content"],
                    "score": s.get("score", 0),
                    "snippet": _snippet(parent_map[pid]["content"]),
                    "retrieval_mode": s.get("retrieval_mode"),
                    "metadata": parent_map[pid].get("metadata", s.get("metadata", {})),
                    "parent_id": pid,
                }
        else:
            # No parent_id or parent not found -- keep original child
            key = s.get("id", id(s))
            grouped[f"__child_{key}"] = s

    resolved = sorted(grouped.values(), key=lambda x: x.get("score", 0), reverse=True)
    logger.info("Parent resolution: %d child sources -> %d parent sources", len(sources), len(resolved))
    return resolved


def _finalize_sources(
    token: str | None,
    raw_sources: list[dict],
    mode: str,
    tenant_id: str | None = None,
) -> list[dict]:
    document_ids = [str(s.get("document_id", "")) for s in raw_sources if s.get("document_id")]
    try:
        documents = get_documents_by_ids(token, document_ids, tenant_id=tenant_id)
    except Exception as e:
        logger.warning("Unable to enrich retrieval sources with document metadata: %s", e)
        documents = {}
    sources = []
    for source in raw_sources:
        document_id = str(source.get("document_id", ""))
        doc = documents.get(document_id, {})
        if doc.get("status") == "archived":
            continue
        content = source.get("content", "")
        sources.append({
            "chunk_id": str(source.get("id", "")),
            "document_id": document_id,
            "filename": doc.get("filename"),
            "score": float(source.get("score", 0) or 0),
            "snippet": _snippet(content),
            "retrieval_mode": mode,
            "content": content,
            "metadata": source.get("metadata", {}),
            **({"parent_id": source["parent_id"]} if source.get("parent_id") else {}),
        })
    return sources


def _classify_query_type(query: str) -> str:
    """Classify a query as 'keyword' or 'semantic' for weighted RRF.

    Keyword queries (error codes, part numbers, exact phrases) benefit from FTS.
    Semantic queries (paraphrased questions) benefit from vector search.
    """
    stripped = query.strip()

    # Guard against empty/whitespace-only queries
    if not stripped:
        return "keyword"

    # Indicators of keyword-heavy queries
    keyword_indicators = 0

    # Contains codes/error messages (alphanumeric with digits, e.g. ERR404, ERR-404, ERR 404)
    if re.search(r'\b[A-Z]{2,}[\s\-_]?\d+\b', stripped):
        keyword_indicators += 2

    # Contains quoted exact phrases (but not single-char quotes in natural language)
    if re.search(r'"[^"]{2,}"', stripped) or re.search(r"'[^']{2,}'", stripped):
        keyword_indicators += 2

    # Short query with digits (technical terms, part numbers)
    words = stripped.lower().split()
    if len(words) <= 3 and any(c.isdigit() for c in stripped):
        keyword_indicators += 1

    # Contains specific technical patterns (version numbers, model names)
    if re.search(r'\b\d+\.\d+(\.\d+)?\b', stripped):
        keyword_indicators += 1

    # All caps words (abbreviations, acronyms)
    caps_words = [w for w in stripped.split() if w.isupper() and len(w) >= 2]
    if caps_words:
        keyword_indicators += 1

    # Short query with strong keyword signals
    if len(words) <= 4 and keyword_indicators >= 2:
        return "keyword"

    # Default to semantic for natural language queries
    return "keyword" if keyword_indicators >= 2 else "semantic"


async def retrieve_context(
    token: str | None,
    user_id: str | None,
    message: str,
    mode: str = "hybrid",
    match_count: int = 5,
    target_user_id: str | None = None,
    tenant_id: str | None = None,
    thread_id: str | None = None,
    diagnostics: dict | None = None,
) -> dict:
    """Retrieve context chunks with source metadata.

    Returns:
        {
            "chunks": list[str],       # content strings for LLM consumption
            "sources": list[dict],     # [{chunk_id, document_id, filename, score, snippet, retrieval_mode, content}, ...]
            "retrieval_log_ids": list[str],
        }
    """
    t0 = time.monotonic()

    # Semantic cache: check for a cached result from a similar query
    cache = get_semantic_cache()
    query_embedding_for_cache: list[float] | None = None

    # For vector/hybrid modes, we'll populate the cache after retrieval
    # For FTS mode, skip caching (no embedding available)
    retrieval_diagnostics = {
        "match_count": match_count,
        **(diagnostics or {}),
    }

    if target_user_id is None:
        target_user_id = user_id
        # Authenticated clients search their tenant admin's shared knowledge base.
        try:
            from app.services.supabase import get_supabase_client_with_token
            from app.services.database import get_tenant_admin_user_id
            if not token or not user_id:
                raise ValueError("anonymous retrieval uses tenant scope")
            db = get_supabase_client_with_token(token)
            profile = db.table("profiles").select("role").eq("id", user_id).maybe_single().execute()
            if profile.data and profile.data.get("role") == "client":
                admin_id = get_tenant_admin_user_id(tenant_id) if tenant_id else None
                if admin_id:
                    target_user_id = admin_id
                    logger.info(f"Redirecting RAG search to tenant admin knowledge base: {admin_id}")
        except Exception as e:
            logger.warning(f"Error checking user role in retrieve_context: {e}")

    cache_namespace = f"mode={mode}|tenant={tenant_id or ''}|target={target_user_id or ''}|match={match_count}"

    def _log_and_return(result: dict) -> dict:
        """Log retrieval metrics then return the result unchanged."""
        result["retrieval_log_ids"] = []
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        sources = result.get("sources", [])
        chunks = result.get("chunks", [])
        top_score = sources[0]["score"] if sources else None
        retrieval_quality = "no_sources" if not sources else "retrieved"
        log_latency(
            "retrieval.total",
            elapsed_ms,
            mode=mode,
            chunk_count=len(result.get("chunks", [])),
            source_count=len(sources),
            top_score=top_score,
            user_id=user_id,
            target_user_id=target_user_id,
            tenant_id=tenant_id,
            thread_id=thread_id,
        )
        try:
            log_sources, log_chunks = _loggable_retrieval_evidence(sources, chunks)
            log_row = log_retrieval(
                query=message,
                retrieval_mode=mode,
                chunk_count=len(chunks),
                source_count=len(sources),
                top_score=top_score,
                duration_ms=elapsed_ms,
                user_id=user_id,
                tenant_id=tenant_id,
                thread_id=thread_id,
                sources=log_sources,
                chunks=log_chunks,
                retrieval_quality=retrieval_quality,
                diagnostics={
                    **retrieval_diagnostics,
                    "chunk_count": len(chunks),
                    "source_count": len(sources),
                    "cache_hit": bool(retrieval_diagnostics.get("cache_hit")),
                },
            )
            if log_row and log_row.get("id"):
                result["retrieval_log_ids"] = [log_row["id"]]
        except Exception:
            pass  # fire-and-forget
        return result

    def _empty():
        return _log_and_return({"chunks": [], "sources": []})

    if mode == "fts":
        fts_start = monotonic_ms()
        chunks = await asyncio.to_thread(search_chunks_fts, token, target_user_id, message, match_count, tenant_id)
        retrieval_diagnostics["fts_result_count"] = len(chunks)
        log_latency(
            "retrieval.fts",
            elapsed_ms(fts_start),
            mode=mode,
            result_count=len(chunks),
            user_id=user_id,
            target_user_id=target_user_id,
            tenant_id=tenant_id,
            thread_id=thread_id,
        )
        if not chunks:
            return _empty()
        raw_sources = [{"id": c.get("id", ""), "document_id": c.get("document_id", ""), "content": c["content"], "score": c.get("rank", 0), "metadata": c.get("metadata", {}), **({"parent_id": c["parent_id"]} if c.get("parent_id") else {})} for c in chunks]
        sources = _finalize_sources(token, raw_sources, mode, tenant_id)
        sources = await _resolve_parents(sources)
        logger.info(f"FTS retrieval: {len(sources)} chunks")
        return _log_and_return({"chunks": [s["content"] for s in sources], "sources": sources})

    print(f"[RETRIEVAL] query='{message[:80]}...', mode={mode}, target_user_id={target_user_id}")
    logger.info(f"Retrieval: query='{message[:80]}...', mode={mode}, user_id={target_user_id}, tenant_id={tenant_id}")

    if mode == "hybrid":
        # FTS doesn't need the embedding — run it concurrently with embedding generation
        async def _embed_query() -> list[float]:
            embedding_start = monotonic_ms()
            result = await get_embedding(get_embedding_client(), message)
            log_latency(
                "retrieval.embedding",
                elapsed_ms(embedding_start),
                mode=mode,
                user_id=user_id,
                target_user_id=target_user_id,
                tenant_id=tenant_id,
                thread_id=thread_id,
            )
            return result

        async def _search_fts() -> list[dict]:
            fts_start = monotonic_ms()
            result = await asyncio.to_thread(search_chunks_fts, token, target_user_id, message, match_count * 2, tenant_id)
            log_latency(
                "retrieval.fts",
                elapsed_ms(fts_start),
                mode=mode,
                result_count=len(result),
                user_id=user_id,
                target_user_id=target_user_id,
                tenant_id=tenant_id,
                thread_id=thread_id,
            )
            return result

        embedding_task = _embed_query()
        fts_task = _search_fts()
        query_embedding, fts_results = await asyncio.gather(embedding_task, fts_task)
        query_embedding_for_cache = query_embedding

        # Check semantic cache after we have the embedding
        cached = cache.lookup(query_embedding, namespace=cache_namespace)
        if cached is not None:
            retrieval_diagnostics["cache_hit"] = True
            logger.info("Semantic cache hit — returning cached retrieval result")
            log_latency(
                "retrieval.cache_hit",
                0,
                mode=mode,
                user_id=user_id,
                target_user_id=target_user_id,
                tenant_id=tenant_id,
                thread_id=thread_id,
            )
            return _log_and_return(cached)

        # Vector search starts only after embedding completes
        vector_start = monotonic_ms()
        vector_results = await search_similar_chunks(
            target_user_id or "",
            query_embedding,
            match_count * 2,
            similarity_threshold=VECTOR_SIMILARITY_THRESHOLD,
            tenant_id=tenant_id,
        )
        retrieval_diagnostics["vector_result_count"] = len(vector_results)
        retrieval_diagnostics["fts_result_count"] = len(fts_results)
        log_latency(
            "retrieval.qdrant_vector",
            elapsed_ms(vector_start),
            mode=mode,
            result_count=len(vector_results),
            user_id=user_id,
            target_user_id=target_user_id,
            tenant_id=tenant_id,
            thread_id=thread_id,
        )

        print(f"[RETRIEVAL] Hybrid results: vector={len(vector_results)}, fts={len(fts_results)}")
        logger.info(f"Hybrid retrieval: vector={len(vector_results)} results, fts={len(fts_results)} results")

        if not vector_results and not fts_results:
            retrieval_diagnostics["fallback_reason"] = "no_retrieval_results"
            print(f"[RETRIEVAL] WARNING: NO results from Qdrant or FTS. Documents may not be indexed for user_id={target_user_id}")
            logger.warning("Hybrid retrieval: NO results from either Qdrant vector search or Supabase FTS. Check if documents are properly indexed.")
            return _empty()

        # Reciprocal Rank Fusion (RRF) merge with dynamic weights
        rrf_k = 60
        query_type = _classify_query_type(message)
        if query_type == "keyword":
            w_vector, w_fts = 0.3, 0.7
        else:
            w_vector, w_fts = 0.7, 0.3
        retrieval_diagnostics["query_type"] = query_type
        logger.info(f"RRF query_type={query_type}, w_vector={w_vector}, w_fts={w_fts}")
        combined: dict[str, dict] = {}

        for rank, chunk in enumerate(vector_results):
            cid = chunk["id"]
            combined[cid] = {"id": cid, "content": chunk["content"], "document_id": chunk.get("document_id", ""), "score": w_vector / (rrf_k + rank + 1), "metadata": chunk.get("metadata", {}), **({"parent_id": chunk["parent_id"]} if chunk.get("parent_id") else {})}

        for rank, chunk in enumerate(fts_results):
            cid = chunk.get("id", f"fts_{rank}")
            if cid in combined:
                combined[cid]["score"] += w_fts / (rrf_k + rank + 1)
            else:
                combined[cid] = {"id": cid, "content": chunk["content"], "document_id": chunk.get("document_id", ""), "score": w_fts / (rrf_k + rank + 1), "metadata": chunk.get("metadata", {}), **({"parent_id": chunk["parent_id"]} if chunk.get("parent_id") else {})}

        sorted_results = sorted(combined.values(), key=lambda x: x["score"], reverse=True)

        # MMR diversification: reduce redundancy in candidates before reranking
        diverse_results = _mmr_diversify(sorted_results, lambda_param=MMR_LAMBDA, top_n=match_count * 2)
        candidates = [r["content"] for r in diverse_results]
        candidate_metas = diverse_results
        retrieval_diagnostics["candidate_count"] = len(candidates)
        logger.info(f"Hybrid RRF merge: {len(combined)} unique -> {len(candidates)} after MMR diversification")

        if candidates:
            rerank_start = monotonic_ms()
            candidate_scores = [m.get("score", 0) for m in candidate_metas]
            scored = await rerank_with_cohere(message, candidates, top_n=match_count, fallback_scores=candidate_scores)
            retrieval_diagnostics["rerank_result_count"] = len(scored)
            log_latency(
                "retrieval.rerank",
                elapsed_ms(rerank_start),
                mode=mode,
                candidate_count=len(candidates),
                result_count=len(scored),
                user_id=user_id,
                target_user_id=target_user_id,
                tenant_id=tenant_id,
                thread_id=thread_id,
            )
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
                        "metadata": meta.get("metadata", {}),
                        **({"parent_id": meta["parent_id"]} if meta.get("parent_id") else {}),
                    })
            sources = _finalize_sources(token, sources, mode, tenant_id)
            sources = await _resolve_parents(sources)
            logger.info(f"Hybrid reranker: {len(scored)} scored -> {len(sources)} final results")
            result = {"chunks": [s["content"] for s in sources], "sources": sources}
            if query_embedding_for_cache:
                cache.store(query_embedding_for_cache, result, namespace=cache_namespace)
            return _log_and_return(result)

        # Fallback to vector-only
        logger.warning("Hybrid: RRF merge produced 0 candidates, falling back to vector-only")
        retrieval_diagnostics["fallback_reason"] = "hybrid_no_candidates"
        fallback_vector_start = monotonic_ms()
        chunks = await search_similar_chunks(
            target_user_id or "",
            query_embedding,
            match_count,
            similarity_threshold=VECTOR_SIMILARITY_THRESHOLD,
            tenant_id=tenant_id,
        )
        retrieval_diagnostics["vector_fallback_result_count"] = len(chunks)
        log_latency(
            "retrieval.qdrant_vector_fallback",
            elapsed_ms(fallback_vector_start),
            mode=mode,
            result_count=len(chunks),
            user_id=user_id,
            target_user_id=target_user_id,
            tenant_id=tenant_id,
            thread_id=thread_id,
        )
        if not chunks:
            return _empty()
        raw_sources = [{"id": c["id"], "document_id": c.get("document_id", ""), "content": c["content"], "score": c.get("similarity", 0), "metadata": c.get("metadata", {}), **({"parent_id": c["parent_id"]} if c.get("parent_id") else {})} for c in chunks]
        sources = _finalize_sources(token, raw_sources, mode, tenant_id)
        sources = await _resolve_parents(sources)
        return _log_and_return({"chunks": [s["content"] for s in sources], "sources": sources})

    # mode == "vector"
    embedding_start = monotonic_ms()
    query_embedding = await get_embedding(get_embedding_client(), message)
    log_latency(
        "retrieval.embedding",
        elapsed_ms(embedding_start),
        mode=mode,
        user_id=user_id,
        target_user_id=target_user_id,
        tenant_id=tenant_id,
        thread_id=thread_id,
    )
    query_embedding_for_cache = query_embedding

    # Check semantic cache
    cached = cache.lookup(query_embedding, namespace=cache_namespace)
    if cached is not None:
        retrieval_diagnostics["cache_hit"] = True
        logger.info("Semantic cache hit (vector mode) — returning cached result")
        log_latency(
            "retrieval.cache_hit",
            0,
            mode=mode,
            user_id=user_id,
            target_user_id=target_user_id,
            tenant_id=tenant_id,
            thread_id=thread_id,
        )
        return _log_and_return(cached)

    vector_start = monotonic_ms()
    chunks = await search_similar_chunks(
        target_user_id or "",
        query_embedding,
        match_count,
        similarity_threshold=VECTOR_SIMILARITY_THRESHOLD,
        tenant_id=tenant_id,
    )
    retrieval_diagnostics["vector_result_count"] = len(chunks)
    log_latency(
        "retrieval.qdrant_vector",
        elapsed_ms(vector_start),
        mode=mode,
        result_count=len(chunks),
        user_id=user_id,
        target_user_id=target_user_id,
        tenant_id=tenant_id,
        thread_id=thread_id,
    )
    if not chunks:
        return _empty()
    raw_sources = [{"id": c["id"], "document_id": c.get("document_id", ""), "content": c["content"], "score": c.get("similarity", 0), "metadata": c.get("metadata", {}), **({"parent_id": c["parent_id"]} if c.get("parent_id") else {})} for c in chunks]
    sources = _finalize_sources(token, raw_sources, mode, tenant_id)
    sources = await _resolve_parents(sources)
    logger.info(f"Vector retrieval: {len(sources)} chunks")
    result = {"chunks": [s["content"] for s in sources], "sources": sources}
    if query_embedding_for_cache:
        cache.store(query_embedding_for_cache, result, namespace=cache_namespace)
    return _log_and_return(result)
