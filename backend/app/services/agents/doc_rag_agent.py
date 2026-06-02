import asyncio
import logging
from collections.abc import AsyncGenerator
from app.services.retrieval import retrieve_context
from app.services.gemini import get_llm_client, generate_chat_response_stream, RAG_SYSTEM_PROMPT, get_primary_model
from app.services.web_search import search_web

logger = logging.getLogger(__name__)

REWRITE_SYSTEM_PROMPT = (
    "You are a query rewriting assistant. Given a conversation history and a "
    "follow-up question, rewrite the question as a standalone search query that "
    "contains all necessary context. Return ONLY the rewritten query, nothing else."
)

EXPANSION_SYSTEM_PROMPT = (
    "Generate exactly 2 alternative search queries that capture different angles "
    "of the original question. Each variant should use different keywords or phrasing "
    "to improve recall. Return one query per line, nothing else. No numbering, no bullets."
)

GROUNDEDNESS_THRESHOLD = 0.25  # Minimum token overlap ratio to consider answer grounded


def _public_sources(sources: list[dict]) -> list[dict]:
    return [{k: v for k, v in source.items() if k != "content"} for source in sources]


async def rewrite_query(message: str, history: list, client) -> str:
    """Rewrite a follow-up query into a standalone search query using the LLM."""
    if not history:
        return message

    recent_user_msgs = [
        msg["content"] if isinstance(msg["content"], str)
        else next((p["text"] for p in msg["content"] if p.get("type") == "text"), "")
        for msg in history[-6:]
        if msg["role"] == "user"
    ]
    if not recent_user_msgs:
        return message

    context_block = "\n".join(f"- {m}" for m in recent_user_msgs)
    user_prompt = (
        f"Conversation history:\n{context_block}\n\n"
        f"Follow-up question: {message}\n\n"
        f"Standalone search query:"
    )

    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=get_primary_model(),
                messages=[
                    {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=50,
                temperature=0.2,
            ),
            timeout=5.0,
        )
        rewritten = response.choices[0].message.content.strip()
        if rewritten:
            logger.info(f"Query rewrite: '{message[:60]}' -> '{rewritten[:60]}'")
            print(f"[DOC_RAG] Query rewrite: '{message[:60]}' -> '{rewritten[:60]}'")
            return rewritten
    except Exception as e:
        logger.warning(f"Query rewrite failed, using original: {e}")

    return message


async def expand_queries(message: str, client) -> list[str]:
    """Generate 2 alternative query formulations for better recall."""
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=get_primary_model(),
                messages=[
                    {"role": "system", "content": EXPANSION_SYSTEM_PROMPT},
                    {"role": "user", "content": message},
                ],
                max_tokens=80,
                temperature=0.3,
            ),
            timeout=5.0,
        )
        raw = (response.choices[0].message.content or "").strip()
        variants = [line.strip() for line in raw.split("\n") if line.strip()]
        # Filter out variants that are too similar to the original
        unique = [v for v in variants if v.lower() != message.lower() and len(v) > 10]
        if unique:
            logger.info(f"Query expansion: '{message[:50]}' -> {len(unique)} variants")
            print(f"[DOC_RAG] Query expansion: {len(unique)} variants generated")
            return unique[:2]  # Max 2 variants
    except Exception as e:
        logger.warning(f"Query expansion failed: {e}")
    return []


def _check_groundedness(answer: str, context_chunks: list[str]) -> float:
    """Check if the answer is grounded in the retrieved context.

    Uses token-level overlap (Jaccard-like) between answer and context.
    Returns a score from 0.0 (no grounding) to 1.0 (fully grounded).
    """
    if not context_chunks or not answer:
        return 0.0

    # Combine all context into one string
    context_text = " ".join(context_chunks).lower()
    answer_lower = answer.lower()

    # Tokenize (simple whitespace split, remove very short tokens)
    context_tokens = {t for t in context_text.split() if len(t) > 3}
    answer_tokens = {t for t in answer_lower.split() if len(t) > 3}

    if not answer_tokens:
        return 0.0

    # What fraction of answer tokens appear in the context?
    overlap = answer_tokens & context_tokens
    groundedness = len(overlap) / len(answer_tokens)

    return groundedness


async def _needs_external_context(query: str, context_chunks: list[str], client) -> bool:
    """Check if the query asks for information NOT covered by the retrieved document chunks."""
    context_preview = "\n---\n".join(c[:300] for c in context_chunks[:3])
    prompt = (
        "You are a strict classifier. Given a user query and document excerpts, "
        "determine if the query asks for information about something NOT in the documents "
        "(e.g., comparing with another product, asking about a different brand, requesting "
        "external/up-to-date data).\n\n"
        f"Document excerpts:\n{context_preview}\n\n"
        f"User query: {query}\n\n"
        "Does the query need external information beyond what's in these documents? "
        "Reply with ONLY 'yes' or 'no'."
    )
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=get_primary_model(),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=5,
                temperature=0,
            ),
            timeout=5.0,
        )
        answer = (response.choices[0].message.content or "").strip().lower()
        result = answer.startswith("y")
        logger.info(f"External context check: {result} (raw='{answer}')")
        print(f"[DOC_RAG] External context needed: {result}")
        return result
    except Exception as e:
        logger.warning(f"External context check failed, defaulting to False: {e}")
        return False


async def _extract_search_query(query: str, context_chunks: list[str], client) -> str:
    """Extract a targeted web search query for the missing external information."""
    context_preview = "\n---\n".join(c[:200] for c in context_chunks[:2])
    prompt = (
        "Given a user query and some document context, extract the specific subject "
        "that needs to be searched online. Focus on the missing/comparison item.\n\n"
        f"Document context: {context_preview}\n\n"
        f"User query: {query}\n\n"
        "Generate a concise search query (under 15 words) for the missing information. "
        "Return ONLY the search query."
    )
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=get_primary_model(),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=30,
                temperature=0.2,
            ),
            timeout=5.0,
        )
        search_query = (response.choices[0].message.content or "").strip().strip('"')
        if search_query:
            logger.info(f"Extracted search query: '{search_query}'")
            print(f"[DOC_RAG] Web search query: '{search_query}'")
            return search_query
    except Exception as e:
        logger.warning(f"Search query extraction failed: {e}")
    # Fallback: use the original query
    return query


HYBRID_SYSTEM_PROMPT = (
    "You are a knowledgeable assistant. Answer using the reference information below. "
    "Some information comes from a curated knowledge base, some from web search results.\n\n"
    "When using web search information, naturally mention the source (e.g., 'According to [Source]...'). "
    "Be conversational, warm, and direct.\n\n"
    "If neither source fully covers the question, acknowledge what you do know and be honest about the gaps. "
    "Do not make up information.\n\n"
    "Use natural Markdown formatting as appropriate (headings, bullet points, bold for emphasis). "
    "Keep answers well-structured but not overly rigid."
)


async def execute(
    token: str | None,
    user_id: str | None,
    message: str,
    history: list,
    retrieval_mode: str = "hybrid",
    target_user_id: str | None = None,
    images: list[str] | None = None,
    tenant_id: str | None = None,
    thread_id: str | None = None,
) -> AsyncGenerator[dict, None]:
    yield {
        "type": "thought",
        "content": f"Searching documents ({retrieval_mode} mode)...",
        "action_type": "searching",
        "action_source": "doc_rag",
        "action_data": {"query": message, "mode": retrieval_mode},
    }

    client = get_llm_client()
    augmented_query = await rewrite_query(message, history, client)
    if augmented_query != message:
        yield {
            "type": "thought",
            "content": f"Expanded query: \"{augmented_query}\"",
            "action_type": "searching",
            "action_source": "doc_rag",
            "action_data": {"original_query": message, "expanded_query": augmented_query},
        }

    # Multi-query retrieval: generate variants and search in parallel
    query_variants = await expand_queries(augmented_query, client)
    all_queries = [augmented_query] + query_variants

    if len(all_queries) > 1:
        yield {
            "type": "thought",
            "content": f"Running {len(all_queries)} query variants for better recall...",
            "action_type": "searching",
            "action_source": "doc_rag",
            "action_data": {"queries": all_queries},
        }

    # Run retrieval for all queries concurrently
    retrieval_tasks = [
        retrieve_context(token, user_id, q, mode=retrieval_mode, target_user_id=target_user_id, tenant_id=tenant_id, thread_id=thread_id)
        for q in all_queries
    ]
    retrieval_results = await asyncio.gather(*retrieval_tasks, return_exceptions=True)

    # Merge results, deduplicating by chunk content
    seen_contents: set[str] = set()
    context_chunks: list[str] = []
    sources: list[dict] = []

    for result in retrieval_results:
        if isinstance(result, Exception):
            logger.warning(f"Multi-query retrieval failed for one variant: {result}")
            continue
        for chunk in result.get("chunks", []):
            # Deduplicate by first 200 chars (fuzzy dedup)
            key = chunk[:200].strip().lower()
            if key not in seen_contents:
                seen_contents.add(key)
                context_chunks.append(chunk)
        for src in result.get("sources", []):
            key = src.get("content", "")[:200].strip().lower()
            if key not in seen_contents:
                # Source already added via chunks; only add unique sources
                pass
        # Use first result's sources as the primary source list
        if not sources and result.get("sources"):
            sources = result["sources"]

    public_sources = _public_sources(sources)
    print(f"[DOC_RAG] Retrieved {len(context_chunks)} context chunks (multi-query: {len(all_queries)} variants) for user_id={user_id}")

    if not context_chunks:
        yield {
            "type": "thought",
            "content": "No matching content found in your documents.",
            "action_type": "no_results",
            "action_source": "doc_rag",
            "action_data": {"query": message},
        }
        yield {"type": "token", "content": "Thank you for your question. Unfortunately, I don't have the specific details needed to address this right now. Could you try rephrasing, or let me know if there's something else I can help with?"}
        return

    # Build content previews — show what the agent actually found
    content_previews = []
    for i, chunk in enumerate(context_chunks):
        preview = chunk[:200].strip()
        if len(chunk) > 200:
            preview += "..."
        content_previews.append(preview)

    # Build a short summary showing what was found
    found_summary = f"Found {len(context_chunks)} relevant section{'s' if len(context_chunks) != 1 else ''} from your documents."
    if content_previews:
        # Show a hint of the first match
        first_snippet = content_previews[0][:120]
        if len(content_previews[0]) > 120:
            first_snippet += "..."
        found_summary += f" Top match: \"{first_snippet}\""

    yield {
        "type": "thought",
        "content": found_summary,
        "action_type": "synthesizing",
        "action_source": "doc_rag",
        "action_data": {
            "chunk_count": len(context_chunks),
            "mode": retrieval_mode,
            "content_previews": content_previews,
            "sources": public_sources,
        },
    }

    yield {
        "type": "sources",
        "sources": public_sources,
    }

    # Check if the query needs external information beyond the documents
    use_hybrid = False
    if context_chunks:
        needs_external = await _needs_external_context(message, context_chunks, client)
        if needs_external:
            yield {
                "type": "thought",
                "content": "Query needs external information. Searching the web...",
                "action_type": "searching",
                "action_source": "doc_rag",
                "action_data": {"reason": "external_context_needed"},
            }
            search_query = await _extract_search_query(message, context_chunks, client)
            web_results = await search_web(search_query, max_results=3)
            if web_results:
                # Add web results as additional context chunks
                web_context = []
                web_sources = []
                for r in web_results:
                    snippet = r["content"][:500]
                    web_context.append(f"[Web] {r['title']}: {snippet}")
                    web_sources.append({"title": r["title"], "url": r["url"]})
                context_chunks = context_chunks + web_context
                public_sources = public_sources + web_sources
                use_hybrid = True
                yield {
                    "type": "thought",
                    "content": f"Found {len(web_results)} web results to supplement document data.",
                    "action_type": "synthesizing",
                    "action_source": "doc_rag",
                    "action_data": {"web_results": len(web_results), "search_query": search_query},
                }
                yield {
                    "type": "sources",
                    "sources": web_sources,
                }

    system_prompt = HYBRID_SYSTEM_PROMPT if use_hybrid else RAG_SYSTEM_PROMPT

    yield {
        "type": "thought",
        "content": "Generating answer from matched documents..." + (" and web search" if use_hybrid else ""),
        "action_type": "synthesizing",
        "action_source": "doc_rag",
        "action_data": {"stage": "llm_generation", "hybrid": use_hybrid},
    }

    # Collect streamed response for groundedness check
    full_answer = ""
    async for chunk in generate_chat_response_stream(client, message, history, context_chunks, images=images, system_prompt=system_prompt):
        full_answer += chunk
        yield {"type": "token", "content": chunk}

    # Post-generation groundedness check
    groundedness = _check_groundedness(full_answer, context_chunks)
    logger.info(f"Groundedness score: {groundedness:.3f} (threshold={GROUNDEDNESS_THRESHOLD})")

    if groundedness < GROUNDEDNESS_THRESHOLD and context_chunks:
        yield {
            "type": "thought",
            "content": f"Low groundedness detected ({groundedness:.0%}). Answer may contain information not found in your documents.",
            "action_type": "guardrail",
            "action_source": "doc_rag",
            "action_data": {"groundedness": round(groundedness, 3), "threshold": GROUNDEDNESS_THRESHOLD},
        }
        # Append a disclaimer
        disclaimer = (
            "\n\n---\n⚠️ *Note: Parts of this answer may not be directly sourced from your documents. "
            "Please verify the information independently.*"
        )
        yield {"type": "token", "content": disclaimer}
