import asyncio
import json
import logging
import re
from collections.abc import AsyncGenerator
from app.services.retrieval import retrieve_context
from app.services.embeddings import get_embedding_client, get_embedding
from app.services.qdrant_db import search_similar_chunks
from app.services.gemini import get_llm_client, generate_chat_response_stream, RAG_SYSTEM_PROMPT, get_primary_model
from app.services.groundedness import GROUNDEDNESS_THRESHOLD, check_groundedness, check_groundedness_with_llm
from app.services.performance import elapsed_ms, log_latency, monotonic_ms
from app.services.web_search import search_web

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dynamic top-k: query complexity classifier
# ---------------------------------------------------------------------------

# Keyword patterns for each complexity tier
_COMPARATIVE_RE = re.compile(
    r"\b(compare|comparison|difference|versus|\bvs\b|pros\s+and\s+cons|"
    r"advantages?\s+and\s+disadvantages?|better\s+than|worse\s+than|"
    r"trade-?offs?|contrast|distinguish)\b"
    r"|比较|对比|区别|差异|优劣|优势和劣势|优点和缺点|哪个更好|权衡",
    re.IGNORECASE,
)
_MULTI_CONTEXT_RE = re.compile(
    r"\b(list\s+all|summarize\s+all|overview\s+of|give\s+me\s+all|"
    r"all\s+(?:the\s+)?(?:details?|information|benefits|features|types|"
    r"steps|ways|methods|reasons|examples)|comprehensive\s+(?:list|overview|summary))\b"
    r"|列出所有|总结所有|概述|全部信息|详细信息|所有类型|所有步骤|综合",
    re.IGNORECASE,
)
_SIMPLE_FACTUAL_RE = re.compile(
    r"^(what|who|when|where|define|definition\s+of|meaning\s+of)\b"
    r"|^(什么是|谁是|何时|哪里|定义|含义)",
    re.IGNORECASE,
)


def classify_query_complexity(query: str) -> int:
    """Return a ``match_count`` value based on lightweight heuristics.

    Tiers:
        3  — simple factual (short, single-definition queries)
        5  — standard (default)
        8  — comparative / complex
        10 — multi-context (asks for broad lists or overviews)
    """
    stripped = query.strip()
    length = len(stripped)
    question_marks = stripped.count("?")

    # Multi-context: long queries or explicit "list all" / "summarize all"
    if length > 150 or _MULTI_CONTEXT_RE.search(stripped):
        return 10

    # Comparative / complex
    if _COMPARATIVE_RE.search(stripped):
        return 8
    if question_marks > 1:
        return 8
    # "and" connecting two question clauses  (e.g. "What is X and how does Y work?")
    if question_marks >= 1 and re.search(r"\band\b.+\?", stripped, re.IGNORECASE):
        return 8

    # Simple factual: short query starting with a question word
    if length < 50 and _SIMPLE_FACTUAL_RE.search(stripped):
        return 3

    # Default
    return 5

REWRITE_SYSTEM_PROMPT = (
    "You are a query rewriting assistant. Given a conversation history and a "
    "follow-up question, rewrite the question as a standalone search query that "
    "contains all necessary context. "
    "IMPORTANT: Write the rewritten query in the SAME LANGUAGE as the follow-up question. "
    "If the follow-up is in English, output English. If in Chinese, output Chinese. "
    "Do NOT switch languages based on the conversation history. "
    "Return ONLY the rewritten query, nothing else."
)

EXPANSION_SYSTEM_PROMPT = (
    "Generate exactly 2 alternative search queries that capture different angles "
    "of the original question. Each variant should use different keywords or phrasing "
    "to improve recall. "
    "IMPORTANT: If the original query contains spelling errors or typos, correct them "
    "in all variants. Use proper domain terminology. "
    "If the query contains abbreviations or acronyms (e.g., AI, ML, NLP, LLM, RAG, IoT, API, SaaS), "
    "include at least one variant that spells them out in full (e.g., Artificial Intelligence, Machine Learning). "
    "Conversely, if the query uses full forms, include at least one variant using the common abbreviation. "
    "Return one query per line, nothing else. No numbering, no bullets."
)

DECOMPOSITION_SYSTEM_PROMPT = (
    "Given a comparative or multi-faceted query, decompose it into 2-3 focused sub-queries "
    "that each address ONE aspect of the comparison. Each sub-query should be self-contained "
    "and searchable. Correct any spelling errors in the process. "
    "Spell out abbreviations and acronyms in full (e.g., AI -> Artificial Intelligence). "
    "Return one query per line, nothing else. No numbering, no bullets.\n\n"
    "Example:\n"
    "Query: Compare Python and Java for web development\n"
    "Python web development advantages and frameworks\n"
    "Java web development advantages and frameworks\n\n"
    "Example:\n"
    "Query: What are the pros and cons of React vs Vue?\n"
    "React pros cons for frontend development\n"
    "Vue pros cons for frontend development"
)

# HyDE constants
HYDE_SYSTEM_PROMPT = (
    "You are a helpful assistant. Given a question, write a short, specific, "
    "factual paragraph that would be the ideal answer if the information existed "
    "in a knowledge base. Be concrete and use domain-appropriate terminology. "
    "If the question contains spelling errors or typos, interpret the intended meaning "
    "and write the paragraph using correct terminology. "
    "IMPORTANT: Always spell out abbreviations and acronyms in full at least once "
    "(e.g., write 'Artificial Intelligence (AI)' instead of just 'AI'). "
    "Return ONLY the hypothetical answer paragraph, nothing else."
)
HYDE_MIN_WORD_COUNT = 5

# Retry HyDE prompt: generates a refined hypothetical answer informed by the weak answer
RETRY_HYDE_PROMPT = (
    "Given a question and a previous answer that was NOT well-supported by documents, "
    "write a refined hypothetical answer that focuses on the specific claims needing "
    "better sourcing. Use domain-appropriate terminology and spell out abbreviations. "
    "Return ONLY the refined hypothetical answer paragraph, nothing else."
)

# Corrective RAG constants
CORRECTIVE_RAG_SYSTEM_PROMPT = (
    "You are a knowledgeable assistant with access to a curated knowledge base "
    "and supplementary web search results. "
    "Answer questions using the reference information provided below. "
    "Be conversational, warm, and direct — like a knowledgeable friend, not a corporate FAQ.\n\n"
    "If the reference information does not contain the answer, say "
    "\"I don't have that information in my knowledge base\" — do not guess or fabricate.\n\n"
    "The reference material comes from two sources:\n"
    "1. INTERNAL DOCUMENTS — the user's own knowledge base (marked as [Document])\n"
    "2. WEB SEARCH RESULTS — supplementary information from the web (marked as [Web])\n\n"
    "Prioritize internal document information when it is relevant and sufficient. "
    "Use web search results to fill gaps or provide additional context. "
    "If sources conflict, note the discrepancy honestly.\n\n"
    "IMPORTANT — Language handling:\n"
    "- Match the user's language. If they write in Chinese, respond in Chinese. If in English, respond in English.\n"
    "- If the user asks for content in a language that is NOT present in the reference material, "
    "answer using the available source language and clearly note that the knowledge base does not contain "
    "content in the requested language.\n"
    "- Do NOT fabricate or hallucinate translations as if they were sourced from documents.\n"
    "- If you provide a translation for convenience, clearly label it as \"(translated for reference)\".\n\n"
    "Structure your answer:\n"
    "1. A brief direct answer (1-2 sentences)\n"
    "2. Supporting details with source references\n"
    "3. Sources section\n\n"
    "When making claims, reference which source supports them using [1], [2], etc. "
    "Each reference tag includes source metadata — use it for precise citations. "
    "Format citations as [N] (Source: filename, p.X, §Section) when page and section info is available. "
    "If page or section info is not provided for a source, just use [N] (Source: filename).\n\n"
    "At the end of your answer, include a 'Sources' section listing each reference you used "
    "with page numbers and section names when available.\n\n"
    "Do not mention \"uploaded files\", \"retrieval\", or \"vector search\" — speak naturally. "
    "When citing web results, you may reference them by title.\n\n"
    "Use natural Markdown formatting as appropriate (headings, bullet points, bold for emphasis). "
    "Keep answers well-structured but not overly rigid."
)

HYBRID_SYSTEM_PROMPT = (
    "You are a knowledgeable assistant. Answer using the reference information below. "
    "Some information comes from a curated knowledge base, some from web search results.\n\n"
    "If the reference information does not contain the answer, say "
    "\"I don't have that information in my knowledge base\" — do not guess or fabricate.\n\n"
    "When using web search information, naturally mention the source (e.g., 'According to [Source]...'). "
    "Be conversational, warm, and direct.\n\n"
    "IMPORTANT — Language handling:\n"
    "- Match the user's language. If they write in Chinese, respond in Chinese. If in English, respond in English.\n"
    "- If the user asks for content in a language that is NOT present in the reference material, "
    "answer using the available source language and clearly note that the knowledge base does not contain "
    "content in the requested language.\n"
    "- Do NOT fabricate or hallucinate translations as if they were sourced from documents.\n"
    "- If you provide a translation for convenience, clearly label it as \"(translated for reference)\".\n\n"
    "Structure your answer:\n"
    "1. A brief direct answer (1-2 sentences)\n"
    "2. Supporting details with source references\n"
    "3. Sources section\n\n"
    "When making claims, reference which source supports them using [1], [2], etc. "
    "Each reference tag includes source metadata — use it for precise citations. "
    "Format citations as [N] (Source: filename, p.X, §Section) when page and section info is available. "
    "If page or section info is not provided for a source, just use [N] (Source: filename).\n\n"
    "At the end of your answer, include a 'Sources' section listing each reference you used "
    "with page numbers and section names when available.\n\n"
    "If neither source fully covers the question, acknowledge what you do know and be honest about the gaps. "
    "Do not make up information.\n\n"
    "Use natural Markdown formatting as appropriate (headings, bullet points, bold for emphasis). "
    "Keep answers well-structured but not overly rigid."
)

VECTOR_SCORE_LOW_THRESHOLD = 0.5
VECTOR_SCORE_MIN_THRESHOLD = 0.4

# Inter-Agent Delegation constants
DELEGATION_PROMPT = (
    "Given a user query, does any part of it require database/data queries "
    "(e.g., sales numbers, counts, metrics, revenue, reports) that can't be "
    "answered from documents alone? "
    "Reply with 'sql' if yes, 'none' if no."
)


def _public_sources(sources: list[dict]) -> list[dict]:
    return [{k: v for k, v in source.items() if k != "content"} for source in sources]


# ---------------------------------------------------------------------------
# Web result relevance filtering
# ---------------------------------------------------------------------------

# Minimum keyword overlap ratio (query tokens found in content / total query tokens)
_WEB_RELEVANCE_THRESHOLD = 0.10


def _compute_keyword_overlap(query: str, content: str) -> float:
    """Compute query-centric keyword overlap between a query and content.

    Returns the fraction of query tokens (3+ chars) that appear in the content.
    This is a lightweight relevance proxy — if none of the user's keywords
    appear in a web result, it is almost certainly irrelevant.

    Returns:
        Float between 0.0 and 1.0.
    """
    query_tokens = set(re.findall(r'\b\w{3,}\b', query.lower()))
    if not query_tokens:
        return 1.0  # no meaningful tokens → don't filter
    content_tokens = set(re.findall(r'\b\w{3,}\b', content.lower()))
    if not content_tokens:
        return 0.0
    intersection = query_tokens & content_tokens
    return len(intersection) / len(query_tokens)


async def rewrite_query(message: str, history: list, client) -> str:
    """Rewrite a follow-up query into a standalone search query using the LLM."""
    if not history:
        return message

    recent_context = []
    for msg in history[-6:]:
        content = msg["content"] if isinstance(msg["content"], str) else next((p["text"] for p in msg["content"] if p.get("type") == "text"), "")
        if msg["role"] == "user":
            recent_context.append(f"User: {content}")
        elif msg["role"] == "assistant":
            recent_context.append(f"Assistant: {content[:200]}")  # Truncate long answers
    if not recent_context:
        return message

    context_block = "\n".join(f"- {m}" for m in recent_context)
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
    """Generate alternative search query formulations for better recall.

    For comparative queries, uses decomposition to generate focused sub-queries.
    For regular queries, uses standard expansion with different phrasings.
    """
    # Check if this is a comparative query that benefits from decomposition
    is_comparative = bool(_COMPARATIVE_RE.search(message))
    prompt = DECOMPOSITION_SYSTEM_PROMPT if is_comparative else EXPANSION_SYSTEM_PROMPT

    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=get_primary_model(),
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": message},
                ],
                max_tokens=100,
                temperature=0.3,
            ),
            timeout=5.0,
        )
        raw = (response.choices[0].message.content or "").strip()
        variants = [line.strip() for line in raw.split("\n") if line.strip()]
        # Filter out variants that are too similar to the original
        unique = [v for v in variants if v.lower() != message.lower() and len(v) > 10]
        if unique:
            mode = "decomposition" if is_comparative else "expansion"
            logger.info(f"Query {mode}: '{message[:50]}' -> {len(unique)} variants")
            print(f"[DOC_RAG] Query {mode}: {len(unique)} variants generated")
            return unique[:2]  # Max 2 variants
    except Exception as e:
        logger.warning(f"Query expansion failed: {e}")
    return []


# ---------------------------------------------------------------------------
# HyDE (Hypothetical Document Embeddings)
# ---------------------------------------------------------------------------

async def generate_hypothetical_answer(query: str, client) -> str | None:
    """Generate a hypothetical answer document for HyDE retrieval."""
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=get_primary_model(),
                messages=[
                    {"role": "system", "content": HYDE_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Question: {query}"},
                ],
                max_tokens=200,
                temperature=0.3,
            ),
            timeout=8.0,
        )
        answer = response.choices[0].message.content.strip()
        if answer:
            logger.info(f"HyDE hypothetical answer generated ({len(answer)} chars)")
            return answer
    except Exception as e:
        logger.warning(f"HyDE hypothetical answer generation failed: {e}")
    return None


def _is_hyde_eligible(query: str) -> bool:
    """Check if a query is suitable for HyDE retrieval.

    Skip very short queries (< 5 words) which are better served by
    direct keyword or vector search.
    """
    return len(query.split()) >= HYDE_MIN_WORD_COUNT


# ---------------------------------------------------------------------------
# Corrective RAG
# ---------------------------------------------------------------------------

def grade_retrieval_quality(sources: list[dict]) -> str:
    """Grade retrieval quality based on vector/reranker scores.

    Returns:
        "high" — at least one strong match, retrieval is reliable
        "low"  — no strong matches, should consider web search fallback
    """
    if not sources:
        return "low"

    scores = [s.get("score", 0) for s in sources]
    max_score = max(scores) if scores else 0

    logger.info(f"Retrieval quality grading: {len(sources)} chunks, scores={[f'{s:.3f}' for s in scores]}, max={max_score:.3f}")

    if max_score >= VECTOR_SCORE_LOW_THRESHOLD:
        return "high"

    above_min = sum(1 for s in scores if s > VECTOR_SCORE_MIN_THRESHOLD)
    if above_min > 0:
        return "high"

    return "low"


def lost_in_the_middle_reorder(
    chunks: list[str], sources: list[dict]
) -> tuple[list[str], list[dict]]:
    """Reorder chunks to mitigate the Lost-in-the-Middle effect.

    LLMs pay more attention to information at the beginning and end of their
    context window (Liu et al., 2023). This function places the most relevant
    chunks at position 0 (first) and position N-1 (last), with remaining chunks
    in descending score order filling the middle.

    Strategy:
      - 0-2 chunks: return unchanged (no benefit from reordering)
      - 3+ chunks: interleave so [best, 3rd, 4th, ..., 2nd-best]

    Args:
        chunks: list of chunk text strings
        sources: list of source dicts aligned 1:1 with chunks

    Returns:
        (reordered_chunks, reordered_sources) tuple
    """
    n = len(chunks)
    if n <= 2:
        return chunks, sources

    # Build indexed list with available scores
    indexed = []
    for i, src in enumerate(sources):
        score = src.get("rerank_score")
        if score is None:
            score = src.get("score", 0.0)
        indexed.append((i, score))

    # Sort by score descending (stable sort preserves original order for ties)
    indexed.sort(key=lambda x: x[1], reverse=True)

    # Interleave: best at front, 2nd-best at end, rest in middle descending
    reordered_indices = [indexed[0][0]]  # highest score -> position 0
    # Middle positions: 3rd, 4th, 5th, ... in descending score order
    for idx, _ in indexed[2:]:
        reordered_indices.append(idx)
    # Last position: 2nd highest score
    reordered_indices.append(indexed[1][0])

    new_chunks = [chunks[i] for i in reordered_indices]
    new_sources = [sources[i] for i in reordered_indices]

    if n >= 3:
        top_scores = [f"{score:.3f}" for _, score in indexed[:5]]
        logger.info(f"Lost-in-the-middle reorder: {n} chunks, scores={top_scores}")

    return new_chunks, new_sources


async def augment_with_web_search(query: str, doc_chunks: list[str], doc_sources: list[dict]) -> dict:
    """Search the web and merge results with document chunks."""
    web_results = await search_web(query, max_results=3)

    if not web_results:
        return {"chunks": doc_chunks, "sources": doc_sources, "web_results": []}

    # ── Relevance filtering: drop web results with low keyword overlap ──
    filtered_results = []
    for r in web_results:
        raw_content = f"{r['title']} {r['content'][:500]}"
        overlap = _compute_keyword_overlap(query, raw_content)
        if overlap >= _WEB_RELEVANCE_THRESHOLD:
            filtered_results.append(r)
        else:
            logger.info(
                f"Web relevance filter: dropped '{r['title'][:60]}' "
                f"(keyword_overlap={overlap:.2%} < {_WEB_RELEVANCE_THRESHOLD:.0%})"
            )
    if len(filtered_results) < len(web_results):
        logger.info(
            f"Web relevance filter: {len(web_results) - len(filtered_results)} of "
            f"{len(web_results)} web results dropped (< {_WEB_RELEVANCE_THRESHOLD:.0%} keyword overlap)"
        )
    web_results = filtered_results

    if not web_results:
        return {"chunks": doc_chunks, "sources": doc_sources, "web_results": []}

    web_chunks = []
    web_sources = []
    for r in web_results:
        content = f"[Web] {r['title']}: {r['content'][:500]}"
        web_chunks.append(content)
        web_sources.append({
            "id": f"web_{r['url']}",
            "document_id": "web_search",
            "content": content,
            "score": 0.0,
            "title": r["title"],
            "url": r["url"],
        })

    # Tag document chunks so LLM knows the source type
    tagged_doc_chunks = []
    for chunk in doc_chunks:
        if not chunk.startswith("[Web]"):
            tagged_doc_chunks.append(f"[Document] {chunk}")
        else:
            tagged_doc_chunks.append(chunk)

    merged_chunks = tagged_doc_chunks + web_chunks
    merged_sources = doc_sources + web_sources

    return {"chunks": merged_chunks, "sources": merged_sources, "web_results": web_results}


# ---------------------------------------------------------------------------
# External context detection (existing)
# ---------------------------------------------------------------------------

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
    return query


# Groundedness retry constants
GROUNDEDNESS_RETRY_PROMPT = (
    "You are a search query optimizer. Given a user question and an answer that was "
    "NOT well-supported by the retrieved documents, generate a more specific search query "
    "that would find the missing information. Focus on the key claims that need support. "
    "Return ONLY the refined search query, nothing else."
)


async def _refine_query_for_retry(original_query: str, weak_answer: str, client) -> str:
    """Generate a refined search query based on the weak answer's unsupported claims."""
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=get_primary_model(),
                messages=[
                    {"role": "system", "content": GROUNDEDNESS_RETRY_PROMPT},
                    {"role": "user", "content": f"Original question: {original_query}\n\nWeak answer: {weak_answer[:500]}"},
                ],
                max_tokens=50,
                temperature=0.2,
            ),
            timeout=5.0,
        )
        refined = response.choices[0].message.content.strip()
        if refined:
            logger.info(f"Retry query refinement: '{original_query[:50]}' -> '{refined[:50]}'")
            return refined
    except Exception as e:
        logger.warning(f"Retry query refinement failed: {e}")
    return original_query


# ---------------------------------------------------------------------------
# Inter-Agent Delegation
# ---------------------------------------------------------------------------

async def _check_delegation(query: str, client) -> str:
    """Check if the query needs delegation to another agent (e.g., SQL)."""
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=get_primary_model(),
                messages=[
                    {"role": "system", "content": DELEGATION_PROMPT},
                    {"role": "user", "content": f"Query: {query}"},
                ],
                max_tokens=5,
                temperature=0,
            ),
            timeout=3.0,
        )
        answer = (response.choices[0].message.content or "").strip().lower()
        if "sql" in answer:
            logger.info(f"Delegation check: query needs SQL agent")
            print(f"[DOC_RAG] Delegation: query needs SQL data")
            return "sql"
    except Exception as e:
        logger.warning(f"Delegation check failed: {e}")
    return "none"


async def _execute_sql_delegation(message: str, history: list) -> dict:
    """Delegate to SQL sub-agent and collect results."""
    from app.services.agents import sql_sub_agent

    chunks = []
    sources = []
    full_answer = ""

    try:
        async for event in sql_sub_agent.execute(message, history):
            if event.get("type") == "token":
                full_answer += event.get("content", "")
            elif event.get("type") == "thought":
                action_data = event.get("action_data", {})
                if "rows" in action_data:
                    # Format SQL results as context chunks
                    rows = action_data.get("rows", [])
                    sql = action_data.get("sql", "")
                    if rows:
                        result_text = f"SQL Query: {sql}\nResults:\n"
                        for row in rows[:10]:
                            result_text += str(row) + "\n"
                        chunks.append(f"[Database] {result_text}")
                        sources.append({
                            "id": "sql_delegation",
                            "document_id": "sql_query",
                            "content": result_text,
                            "score": 1.0,
                            "title": "Database Query Results",
                        })
    except Exception as e:
        logger.warning(f"SQL delegation failed: {e}")

    return {"chunks": chunks, "sources": sources, "answer": full_answer}


# ---------------------------------------------------------------------------
# Chain-of-Verification (CoVe)
# ---------------------------------------------------------------------------

COVE_QUESTIONS_PROMPT = (
    "You are a fact-checker. For each factual claim in the following answer, "
    "generate a verification question that would independently confirm or refute it. "
    "Focus on specific facts, numbers, names, and relationships — not opinions or hedging. "
    "Return a JSON array of strings (the questions), nothing else. Limit to the 8 most important claims.\n\n"
    "Answer to verify:\n{draft_answer}"
)

COVE_VERIFY_PROMPT = (
    "You are a strict fact-checker. Answer the following question using ONLY the "
    "context provided below. Do NOT use any outside knowledge.\n\n"
    "Context:\n{context}\n\n"
    "Question: {question}\n\n"
    "Provide a concise answer, then on a new line state whether the claim is "
    "SUPPORTED or NOT SUPPORTED by the context. Format:\n"
    "Answer: <your answer>\nVerdict: SUPPORTED or NOT SUPPORTED"
)


async def generate_verification_questions(draft_answer: str, client, model: str) -> list[str]:
    """Generate fact-checking questions from a draft answer's claims."""
    max_questions = 8
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": COVE_QUESTIONS_PROMPT.format(draft_answer=draft_answer)},
                ],
                max_tokens=500,
                temperature=0.2,
            ),
            timeout=10.0,
        )
        raw = (response.choices[0].message.content or "").strip()
        # Try JSON parse first
        try:
            # Strip markdown code fences if present
            clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
            questions = json.loads(clean)
            if isinstance(questions, list):
                return [str(q).strip() for q in questions if str(q).strip()][:max_questions]
        except (json.JSONDecodeError, TypeError):
            pass
        # Fallback: split on question marks
        parts = re.split(r"\?\s*", raw)
        questions = [p.strip() + "?" for p in parts if p.strip() and len(p.strip()) > 10]
        return questions[:max_questions]
    except Exception as e:
        logger.warning(f"CoVe question generation failed: {e}")
    return []


async def _verify_single_question(
    question: str, context_chunks: list[str], client, model: str
) -> dict:
    """Answer a single verification question using only the context chunks."""
    context = "\n---\n".join(context_chunks[:10])
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": COVE_VERIFY_PROMPT.format(context=context, question=question)},
                ],
                max_tokens=200,
                temperature=0.1,
            ),
            timeout=10.0,
        )
        raw = (response.choices[0].message.content or "").strip()
        # Extract verdict
        supported = "not supported" not in raw.lower()
        # Extract answer portion
        answer = raw
        for marker in ["Verdict:", "verdict:"]:
            idx = raw.find(marker)
            if idx > 0:
                answer = raw[:idx].replace("Answer:", "").strip()
                break
        return {"question": question, "answer": answer, "supported": supported}
    except Exception as e:
        logger.warning(f"CoVe verification failed for question '{question[:50]}': {e}")
        return {"question": question, "answer": "", "supported": True}  # default to supported on error


async def verify_answer_independently(
    questions: list[str], context_chunks: list[str], client, model: str
) -> list[dict]:
    """Answer each verification question independently using only context chunks."""
    tasks = [
        _verify_single_question(q, context_chunks, client, model)
        for q in questions
    ]
    results = await asyncio.gather(*tasks)
    return list(results)


async def chain_of_verification(
    draft_answer: str, context_chunks: list[str], client, model: str
) -> dict:
    """Run the full Chain-of-Verification pipeline.

    Returns:
        {
            "verified": bool,          # True if >= 70% claims supported
            "unsupported_claims": list[str],
            "verification_questions": list[str],
            "verification_results": list[dict],
        }
    """
    questions = await generate_verification_questions(draft_answer, client, model)
    if not questions:
        return {
            "verified": True,
            "unsupported_claims": [],
            "verification_questions": [],
            "verification_results": [],
        }

    results = await verify_answer_independently(questions, context_chunks, client, model)

    unsupported = [r["question"] for r in results if not r["supported"]]
    support_ratio = 1.0 - (len(unsupported) / len(results)) if results else 1.0
    verified = support_ratio >= 0.7

    return {
        "verified": verified,
        "unsupported_claims": unsupported,
        "verification_questions": questions,
        "verification_results": results,
    }


# ---------------------------------------------------------------------------
# Main execution pipeline
# ---------------------------------------------------------------------------

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
    enable_hyde: bool = True,
    allow_web_fallback: bool = True,
) -> AsyncGenerator[dict, None]:
    yield {
        "type": "thought",
        "content": f"Searching documents ({retrieval_mode} mode)...",
        "action_type": "searching",
        "action_source": "doc_rag",
        "action_data": {"query": message, "mode": retrieval_mode},
    }

    client = get_llm_client()
    channel = "widget" if not token else "authenticated"

    # ── Inter-Agent Delegation: keyword pre-filter then LLM check ──
    SQL_KEYWORDS = {"sales", "revenue", "total", "count", "average", "sum", "how many",
                    "query", "database", "report", "metrics", "kpi", "quarterly", "monthly"}
    message_words = set(message.lower().split())
    delegated_sql_result = None
    delegation_target = "none"
    if message_words & SQL_KEYWORDS:
        delegation_target = await _check_delegation(message, client)
    if delegation_target == "sql":
        yield {
            "type": "thought",
            "content": "Query involves database data. Delegating to SQL agent...",
            "action_type": "delegating",
            "action_source": "doc_rag",
            "action_data": {"target": "sql"},
        }
        delegated_sql_result = await _execute_sql_delegation(message, history)
        if delegated_sql_result.get("answer"):
            yield {
                "type": "thought",
                "content": "SQL agent retrieved database results. Merging with document context...",
                "action_type": "merging",
                "action_source": "doc_rag",
                "action_data": {"sql_chunks": len(delegated_sql_result.get("chunks", []))},
            }
        elif not delegated_sql_result.get("chunks"):
            yield {
                "type": "thought",
                "content": "SQL delegation returned no results. Proceeding with document search only.",
                "action_type": "merging",
                "action_source": "doc_rag",
            }

    qr_start = monotonic_ms()
    augmented_query = await rewrite_query(message, history, client)
    log_latency("llm.query_rewrite", elapsed_ms(qr_start), user_id=user_id, tenant_id=tenant_id, thread_id=thread_id, rewritten=augmented_query != message)
    if augmented_query != message:
        yield {
            "type": "thought",
            "content": f"Expanded query: \"{augmented_query}\"",
            "action_type": "searching",
            "action_source": "doc_rag",
            "action_data": {"original_query": message, "expanded_query": augmented_query},
        }

    # Multi-query retrieval: generate variants and search in parallel
    qe_start = monotonic_ms()
    query_variants = await expand_queries(augmented_query, client)
    log_latency("llm.query_expansion", elapsed_ms(qe_start), user_id=user_id, tenant_id=tenant_id, thread_id=thread_id, variant_count=len(query_variants))
    all_queries = [augmented_query] + query_variants

    if len(all_queries) > 1:
        yield {
            "type": "thought",
            "content": f"Running {len(all_queries)} query variants for better recall...",
            "action_type": "searching",
            "action_source": "doc_rag",
            "action_data": {"queries": all_queries},
        }

    # Dynamic top-k based on query complexity
    dynamic_match_count = classify_query_complexity(augmented_query)
    logger.info("Query complexity classified: match_count=%d for query='%s'", dynamic_match_count, augmented_query[:80])

    # Run retrieval for all queries concurrently
    retrieval_tasks = [
        retrieve_context(
            token,
            user_id,
            q,
            mode=retrieval_mode,
            match_count=dynamic_match_count,
            target_user_id=target_user_id,
            tenant_id=tenant_id,
            thread_id=thread_id,
            diagnostics={
                "channel": channel,
                "query_variant_count": len(all_queries),
                "query_variant_index": index,
                "web_fallback_allowed": allow_web_fallback,
            },
        )
        for index, q in enumerate(all_queries)
    ]
    retrieval_results = await asyncio.gather(*retrieval_tasks, return_exceptions=True)

    # ── RAG-Fusion: RRF merge across query variants ──
    # Documents appearing in multiple variant result sets get higher fused scores.
    rrf_k = 60
    fused: dict[str, dict] = {}  # key -> {content, sources, score, ...}
    retrieval_log_ids: list[str] = []

    for result in retrieval_results:
        if isinstance(result, Exception):
            logger.warning(f"Multi-query retrieval failed for one variant: {result}")
            continue
        retrieval_log_ids.extend(result.get("retrieval_log_ids", []))
        result_chunks = result.get("chunks", [])
        result_sources = result.get("sources", [])
        for rank, chunk in enumerate(result_chunks):
            key = chunk[:500].strip().lower()
            rrf_score = 1.0 / (rrf_k + rank + 1)
            if key in fused:
                # Document found by another variant — boost its score
                fused[key]["score"] += rrf_score
            else:
                source = result_sources[rank] if rank < len(result_sources) else {}
                fused[key] = {
                    "content": chunk,
                    "source": source,
                    "score": rrf_score,
                }

    # Sort by fused score descending, then dedup into final lists
    sorted_fused = sorted(fused.values(), key=lambda x: x["score"], reverse=True)

    seen_chunk_keys: set[str] = set()
    seen_source_keys: set[str] = set()
    context_chunks: list[str] = []
    context_sources: list[dict] = []
    sources: list[dict] = []

    for item in sorted_fused:
        chunk = item["content"]
        source = item["source"]
        key = chunk[:500].strip().lower()
        if key not in seen_chunk_keys:
            seen_chunk_keys.add(key)
            context_chunks.append(chunk)
            context_sources.append(source)
        src_key = source.get("content", "")[:500].strip().lower() if source else ""
        if src_key and src_key not in seen_source_keys:
            seen_source_keys.add(src_key)
            sources.append(source)

    logger.info(f"RAG-Fusion: {len(fused)} unique chunks from {len(all_queries)} variants, top fused score={sorted_fused[0]['score']:.4f}" if sorted_fused else "RAG-Fusion: 0 chunks")
    public_sources = _public_sources(sources)
    print(f"[DOC_RAG] Retrieved {len(context_chunks)} context chunks (RAG-Fusion: {len(all_queries)} variants, {len(fused)} unique) for user_id={user_id}")

    # ── Merge delegated SQL results into context ──
    if delegated_sql_result and delegated_sql_result.get("chunks"):
        sql_chunks = delegated_sql_result["chunks"]
        sql_sources = delegated_sql_result.get("sources", [])
        for i, chunk in enumerate(sql_chunks):
            key = chunk[:500].strip().lower()
            if key not in seen_chunk_keys:
                seen_chunk_keys.add(key)
                context_chunks.insert(0, chunk)  # Prepend SQL results (high priority)
                if i < len(sql_sources):
                    context_sources.insert(0, sql_sources[i])
                else:
                    context_sources.insert(0, {})
        sources = sql_sources + sources
        public_sources = _public_sources(sources)
        print(f"[DOC_RAG] Merged {len(sql_chunks)} SQL delegation chunks, total now {len(context_chunks)}")
        yield {
            "type": "thought",
            "content": f"Merged {len(sql_chunks)} database results with {len(context_chunks) - len(sql_chunks)} document sections.",
            "action_type": "merging",
            "action_source": "doc_rag",
            "action_data": {"sql_chunks": len(sql_chunks), "total_chunks": len(context_chunks)},
        }

    # HyDE: generate a hypothetical answer, embed it, and search for similar chunks
    if enable_hyde and _is_hyde_eligible(augmented_query):
        yield {
            "type": "thought",
            "content": "Generating hypothetical answer for semantic retrieval (HyDE)...",
            "action_type": "searching",
            "action_source": "doc_rag",
            "action_data": {"stage": "hyde_generation"},
        }
        hyde_start = monotonic_ms()
        hyde_answer = await generate_hypothetical_answer(augmented_query, client)
        log_latency("llm.hyde_generation", elapsed_ms(hyde_start), user_id=user_id, tenant_id=tenant_id, thread_id=thread_id, generated=hyde_answer is not None)
        if hyde_answer:
            try:
                hyde_embedding = await get_embedding(get_embedding_client(), hyde_answer)
                target_uid = target_user_id or user_id or ""
                hyde_chunks = await search_similar_chunks(
                    target_uid, hyde_embedding, match_count=5,
                    similarity_threshold=0.5, tenant_id=tenant_id,
                )
                if hyde_chunks:
                    # HyDE Relevance Backcheck: verify chunks are relevant to the
                    # ORIGINAL query, not just the hypothetical answer.  The HyDE
                    # embedding search finds chunks similar to the hypothetical
                    # answer, which can drift off-topic.  We re-compute similarity
                    # against the original query embedding and reject chunks below
                    # the 0.3 relevance threshold.
                    HYDE_RELEVANCE_THRESHOLD = 0.3
                    try:
                        query_embedding = await get_embedding(get_embedding_client(), augmented_query)

                        def _cosine_sim(a: list[float], b: list[float]) -> float:
                            """Pure-Python cosine similarity between two float vectors."""
                            dot = sum(x * y for x, y in zip(a, b))
                            norm_a = sum(x * x for x in a) ** 0.5
                            norm_b = sum(x * x for x in b) ** 0.5
                            if norm_a == 0 or norm_b == 0:
                                return 0.0
                            return dot / (norm_a * norm_b)

                        original_len = len(hyde_chunks)
                        backchecked_chunks = []
                        for chunk in hyde_chunks:
                            chunk_text = chunk["content"]
                            chunk_embedding = await get_embedding(get_embedding_client(), chunk_text)
                            relevance = _cosine_sim(query_embedding, chunk_embedding)
                            if relevance >= HYDE_RELEVANCE_THRESHOLD:
                                backchecked_chunks.append(chunk)
                            else:
                                logger.info(
                                    f"HyDE backcheck: rejected chunk (relevance={relevance:.3f} < {HYDE_RELEVANCE_THRESHOLD}): "
                                    f"'{chunk_text[:80]}...'"
                                )
                        if len(backchecked_chunks) < original_len:
                            logger.info(
                                f"HyDE backcheck: {original_len - len(backchecked_chunks)} chunks rejected "
                                f"(< {HYDE_RELEVANCE_THRESHOLD} relevance to original query)"
                            )
                        hyde_chunks = backchecked_chunks
                    except Exception as e:
                        logger.warning(f"HyDE relevance backcheck failed, keeping all chunks: {e}")

                    existing_contents = set(seen_chunk_keys)
                    added = 0
                    for chunk in hyde_chunks:
                        content = chunk["content"]
                        key = content[:500].strip().lower()
                        if key not in existing_contents:
                            context_chunks.append(content)
                            hyde_src = {
                                "id": chunk.get("id", ""),
                                "document_id": chunk.get("document_id", ""),
                                "content": content,
                                "score": chunk.get("similarity", 0),
                                "retrieval_method": "hyde",
                            }
                            sources.append(hyde_src)
                            context_sources.append(hyde_src)
                            existing_contents.add(key)
                            seen_chunk_keys.add(key)
                            added += 1
                    if added:
                        print(f"[DOC_RAG] HyDE added {added} new chunks (total now {len(context_chunks)})")
                        logger.info(f"HyDE: added {added} new chunks, total={len(context_chunks)}")
                        yield {
                            "type": "thought",
                            "content": f"HyDE retrieval found {added} additional relevant section{'s' if added != 1 else ''}.",
                            "action_type": "searching",
                            "action_source": "doc_rag",
                            "action_data": {"stage": "hyde_merge", "added": added},
                        }
                    else:
                        print("[DOC_RAG] HyDE: no new unique chunks found")
                else:
                    print("[DOC_RAG] HyDE: vector search returned 0 results")
            except Exception as e:
                print(f"[DOC_RAG] HyDE retrieval failed: {e}")
                logger.warning(f"HyDE retrieval failed: {e}")

    # Update public_sources after HyDE
    public_sources = _public_sources(sources)

    if not context_chunks:
        if not allow_web_fallback:
            yield {
                "type": "thought",
                "content": "No matching content found in the knowledge base. Web fallback is disabled for this channel.",
                "action_type": "no_results",
                "action_source": "doc_rag",
                "action_data": {
                    "query": message,
                    "fallback_reason": "no_doc_results",
                    "retrieval_log_ids": retrieval_log_ids,
                    "web_fallback_allowed": False,
                },
            }
            yield {"type": "token", "content": "I don't have that information in my knowledge base."}
            yield {
                "type": "rag_quality",
                "retrieval_log_ids": retrieval_log_ids,
                "groundedness": None,
                "groundedness_flag": False,
                "retrieval_quality": "no_sources",
                "diagnostics": {
                    "channel": channel,
                    "doc_chunk_count": 0,
                    "web_result_count": 0,
                    "fallback_reason": "no_doc_results",
                    "web_fallback_allowed": False,
                    "query_variant_count": len(all_queries),
                },
            }
            return
        # No document results at all — fall back to web search (Corrective RAG)
        yield {
            "type": "thought",
            "content": "No matching content found in your documents. Searching the web instead...",
            "action_type": "searching",
            "action_source": "doc_rag",
            "action_data": {"query": message, "fallback_reason": "no_doc_results", "retrieval_log_ids": retrieval_log_ids},
        }

        ws_start = monotonic_ms()
        web_results = await search_web(augmented_query, max_results=5)
        log_latency("retrieval.web_search", elapsed_ms(ws_start), user_id=user_id, tenant_id=tenant_id, thread_id=thread_id, result_count=len(web_results) if web_results else 0)
        if web_results:
            # Relevance filtering for web-only fallback
            filtered_web = []
            for r in web_results:
                raw = f"{r['title']} {r['content'][:500]}"
                overlap = _compute_keyword_overlap(augmented_query, raw)
                if overlap >= _WEB_RELEVANCE_THRESHOLD:
                    filtered_web.append(r)
                else:
                    logger.info(f"Web fallback filter: dropped '{r['title'][:60]}' (keyword_overlap={overlap:.2%})")
            if len(filtered_web) < len(web_results):
                logger.info(f"Web fallback filter: {len(web_results) - len(filtered_web)} of {len(web_results)} results dropped")
            web_results = filtered_web

            web_chunks = [f"[Web] {r['title']}: {r['content'][:500]}" for r in web_results]
            web_sources = [{"id": f"web_{r['url']}", "document_id": "web_search", "content": c, "score": 0.0, "title": r["title"], "url": r["url"]} for r, c in zip(web_results, web_chunks)]

            yield {
                "type": "thought",
                "content": f"No documents matched, but found {len(web_results)} relevant web results. Generating answer from web search.",
                "action_type": "synthesizing",
                "action_source": "doc_rag",
                "action_data": {"web_result_count": len(web_results), "fallback": True},
            }

            yield {"type": "token", "content": "> I didn't find relevant documents for your question, so I searched the web for you.\n\n"}

            async for chunk in generate_chat_response_stream(client, message, history, web_chunks, images=images, system_prompt=CORRECTIVE_RAG_SYSTEM_PROMPT, context_sources=web_sources):
                yield {"type": "token", "content": chunk}
            yield {
                "type": "rag_quality",
                "retrieval_log_ids": retrieval_log_ids,
                "groundedness": None,
                "groundedness_flag": False,
                "retrieval_quality": "no_sources_web_fallback",
                "diagnostics": {
                    "channel": channel,
                    "doc_chunk_count": 0,
                    "web_result_count": len(web_results),
                    "fallback_reason": "no_doc_results",
                    "web_fallback_allowed": True,
                    "query_variant_count": len(all_queries),
                },
            }
            return

        yield {
            "type": "thought",
            "content": "No matching content found in documents or web.",
            "action_type": "no_results",
            "action_source": "doc_rag",
            "action_data": {"query": message},
        }
        yield {"type": "token", "content": "Thank you for your question. Unfortunately, I don't have the specific details needed to address this right now. Could you try rephrasing, or let me know if there's something else I can help with?"}
        yield {
            "type": "rag_quality",
            "retrieval_log_ids": retrieval_log_ids,
            "groundedness": None,
            "groundedness_flag": False,
            "retrieval_quality": "no_sources",
            "diagnostics": {
                "channel": channel,
                "doc_chunk_count": 0,
                "web_result_count": 0,
                "fallback_reason": "no_doc_or_web_results",
                "web_fallback_allowed": True,
                "query_variant_count": len(all_queries),
            },
        }
        return

    # --- Corrective RAG: grade retrieval quality ---
    quality = grade_retrieval_quality(sources)
    used_web_fallback = False

    if quality == "low" and not allow_web_fallback:
        logger.info("Corrective RAG: retrieval quality is LOW and web fallback is disabled.")
        yield {
            "type": "thought",
            "content": "Document matches are weak and web fallback is disabled for this channel.",
            "action_type": "guardrail",
            "action_source": "doc_rag",
            "action_data": {
                "quality": quality,
                "fallback_reason": "low_quality_no_web",
                "doc_chunk_count": len(context_chunks),
                "web_fallback_allowed": False,
                "retrieval_log_ids": retrieval_log_ids,
            },
        }
        yield {"type": "sources", "sources": _public_sources(sources)}
        yield {"type": "token", "content": "I don't have enough reliable information in my knowledge base to answer that."}
        yield {
            "type": "rag_quality",
            "retrieval_log_ids": retrieval_log_ids,
            "groundedness": None,
            "groundedness_flag": False,
            "retrieval_quality": "low_no_web",
            "diagnostics": {
                "channel": channel,
                "doc_chunk_count": len(context_chunks),
                "web_result_count": 0,
                "fallback_reason": "low_quality_no_web",
                "web_fallback_allowed": False,
                "query_variant_count": len(all_queries),
            },
        }
        return

    if quality == "low":
        logger.info(f"Corrective RAG: retrieval quality is LOW. Triggering web search.")
        print(f"[DOC_RAG] Corrective RAG: low quality retrieval, augmenting with web search")

        yield {
            "type": "thought",
            "content": f"Document matches are weak (low relevance scores). Searching the web for better context...",
            "action_type": "searching",
            "action_source": "doc_rag",
            "action_data": {"query": augmented_query, "quality": quality, "corrective_action": "web_search"},
        }

        augmented = await augment_with_web_search(augmented_query, context_chunks, sources)
        context_chunks = augmented["chunks"]
        sources = augmented["sources"]
        context_sources = sources  # keep in sync for lost_in_the_middle_reorder
        used_web_fallback = bool(augmented["web_results"])

        if used_web_fallback:
            logger.info(f"Corrective RAG: merged {len(augmented['web_results'])} web results with {len(sources) - len(augmented['web_results'])} doc chunks")
            yield {
                "type": "thought",
                "content": f"Found limited relevant documents, so I also searched the web and found {len(augmented['web_results'])} additional results.",
                "action_type": "synthesizing",
                "action_source": "doc_rag",
                "action_data": {
                    "corrective_action": "web_augmented",
                    "doc_chunk_count": len(sources) - len(augmented["web_results"]),
                    "web_result_count": len(augmented["web_results"]),
                },
            }

    # Build content previews
    content_previews = []
    for i, chunk in enumerate(context_chunks):
        preview = chunk[:200].strip()
        if len(chunk) > 200:
            preview += "..."
        content_previews.append(preview)

    # Build summary
    doc_count = sum(1 for s in sources if s.get("document_id") != "web_search")
    web_count = sum(1 for s in sources if s.get("document_id") == "web_search")

    found_summary = f"Found {doc_count} relevant section{'s' if doc_count != 1 else ''} from your documents."
    if web_count > 0:
        found_summary += f" Augmented with {web_count} web search result{'s' if web_count != 1 else ''}."
    if content_previews:
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
            "doc_chunk_count": doc_count,
            "web_result_count": web_count,
            "mode": retrieval_mode,
            "quality": quality,
            "used_web_fallback": used_web_fallback,
            "content_previews": content_previews,
            "sources": _public_sources(sources),
            "retrieval_log_ids": retrieval_log_ids,
        },
    }

    yield {
        "type": "sources",
        "sources": _public_sources(sources),
    }

    # Check if the query needs external information beyond the documents (existing logic)
    use_hybrid = False
    if context_chunks and not used_web_fallback and allow_web_fallback:
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
            wse_start = monotonic_ms()
            web_results = await search_web(search_query, max_results=3)
            log_latency("retrieval.web_search_external", elapsed_ms(wse_start), user_id=user_id, tenant_id=tenant_id, thread_id=thread_id, result_count=len(web_results) if web_results else 0)
            if web_results:
                # Relevance filtering: drop web results with low keyword overlap
                filtered_web = []
                for r in web_results:
                    raw = f"{r['title']} {r['content'][:500]}"
                    overlap = _compute_keyword_overlap(search_query, raw)
                    if overlap >= _WEB_RELEVANCE_THRESHOLD:
                        filtered_web.append(r)
                    else:
                        logger.info(
                            f"External web filter: dropped '{r['title'][:60]}' "
                            f"(keyword_overlap={overlap:.2%} < {_WEB_RELEVANCE_THRESHOLD:.0%})"
                        )
                if len(filtered_web) < len(web_results):
                    logger.info(
                        f"External web filter: {len(web_results) - len(filtered_web)} of "
                        f"{len(web_results)} results dropped (< {_WEB_RELEVANCE_THRESHOLD:.0%} keyword overlap)"
                    )
                web_results = filtered_web

                web_context = []
                web_sources = []
                for r in web_results:
                    snippet = r["content"][:500]
                    web_context.append(f"[Web] {r['title']}: {snippet}")
                    web_sources.append({"title": r["title"], "url": r["url"]})
                if not web_context:
                    logger.info("External web search: all results filtered out by relevance check")
                context_chunks = context_chunks + web_context
                context_sources = context_sources + web_sources
                public_sources = public_sources + web_sources
                use_hybrid = bool(web_context)
                yield {
                    "type": "thought",
                    "content": f"Found {len(web_results)} relevant web results to supplement document data.",
                    "action_type": "synthesizing",
                    "action_source": "doc_rag",
                    "action_data": {"web_results": len(web_results), "search_query": search_query},
                }
                yield {
                    "type": "sources",
                    "sources": web_sources,
                }

    # Choose the right system prompt
    if used_web_fallback:
        system_prompt = CORRECTIVE_RAG_SYSTEM_PROMPT
    elif use_hybrid:
        system_prompt = HYBRID_SYSTEM_PROMPT
    else:
        system_prompt = RAG_SYSTEM_PROMPT

    # ── Lost-in-the-Middle reorder ──
    # Place most relevant chunks at the beginning and end of context so the LLM
    # gives them maximum attention (Liu et al., 2023).
    if context_chunks:
        context_chunks, context_sources = lost_in_the_middle_reorder(context_chunks, context_sources)

    yield {
        "type": "thought",
        "content": "Generating answer from matched documents..." + (" and web search" if use_hybrid or used_web_fallback else ""),
        "action_type": "synthesizing",
        "action_source": "doc_rag",
        "action_data": {"stage": "llm_generation", "hybrid": use_hybrid or used_web_fallback},
    }

    # Add transparency message when web search was used
    if used_web_fallback:
        yield {"type": "token", "content": "> I found limited relevant documents, so I also searched the web to give you a better answer.\n\n"}

    # ── Generate answer with optional groundedness retry ──
    # Retry 1: query reformulation; Retry 2: HyDE-based retrieval
    max_retries = 2
    attempt = 0
    is_grounded = True
    groundedness = 1.0
    retry_retrieval_log_ids = []

    while attempt <= max_retries:
        full_answer = ""
        llm_start = monotonic_ms()
        first_token_logged = False
        async for chunk in generate_chat_response_stream(client, message, history, context_chunks, images=images, system_prompt=system_prompt, context_sources=context_sources):
            if not first_token_logged:
                log_latency(
                    "llm.first_token",
                    elapsed_ms(llm_start),
                    mode=retrieval_mode,
                    user_id=user_id,
                    target_user_id=target_user_id,
                    tenant_id=tenant_id,
                    thread_id=thread_id,
                    context_chunk_count=len(context_chunks),
                )
                first_token_logged = True
            full_answer += chunk
            yield {"type": "token", "content": chunk}
        log_latency(
            "llm.completion",
            elapsed_ms(llm_start),
            mode=retrieval_mode,
            user_id=user_id,
            target_user_id=target_user_id,
            tenant_id=tenant_id,
            thread_id=thread_id,
            context_chunk_count=len(context_chunks),
            answer_chars=len(full_answer),
        )

        # Groundedness check (two-stage: token-overlap + LLM)
        # Detect if context contains web-fallback content to use web-aware groundedness prompt
        has_web_content = any(c.strip().startswith("[Web]") for c in context_chunks)
        groundedness, is_grounded = await check_groundedness_with_llm(
            full_answer, context_chunks, client, get_primary_model(),
            web_mode=has_web_content,
        )
        if has_web_content:
            logger.info(f"Groundedness check used web-aware prompt (web chunks detected in context)")
        logger.info(f"Groundedness attempt {attempt+1}: score={groundedness:.3f}, is_grounded={is_grounded}")

        if is_grounded or attempt >= max_retries:
            break

        # ── Retry: different strategies per attempt ──
        attempt += 1

        if attempt == 1:
            # Retry 1: Query reformulation — refine the search query based on weak answer
            yield {
                "type": "thought",
                "content": f"Answer may not be fully grounded ({groundedness:.0%}). Refining search query and trying again...",
                "action_type": "retrying",
                "action_source": "doc_rag",
                "action_data": {"attempt": attempt, "groundedness": round(groundedness, 3), "strategy": "query_reformulation"},
            }

            refined_query = await _refine_query_for_retry(augmented_query, full_answer, client)
            yield {
                "type": "thought",
                "content": f"Refined search: “{refined_query[:80]}”",
                "action_type": "searching",
                "action_source": "doc_rag",
                "action_data": {"refined_query": refined_query},
            }

            retry_result = await retrieve_context(
                token, user_id, refined_query, mode=retrieval_mode,
                target_user_id=target_user_id, tenant_id=tenant_id, thread_id=thread_id,
                diagnostics={
                    "channel": channel,
                    "query_variant_count": len(all_queries),
                    "retry": True,
                    "retry_strategy": "query_reformulation",
                    "web_fallback_allowed": allow_web_fallback,
                },
            )
            retry_retrieval_log_ids.extend(retry_result.get("retrieval_log_ids", []))

            if retry_result.get("chunks"):
                # Merge retry chunks with existing, deduplicating
                seen_keys = {c[:500].strip().lower() for c in context_chunks}
                retry_chunks = retry_result["chunks"]
                retry_sources = retry_result.get("sources", [])
                added = 0
                for i, chunk in enumerate(retry_chunks):
                    key = chunk[:500].strip().lower()
                    if key not in seen_keys:
                        context_chunks.append(chunk)
                        if i < len(retry_sources):
                            context_sources.append(retry_sources[i])
                        else:
                            context_sources.append({})
                        seen_keys.add(key)
                        added += 1
                if added:
                    yield {
                        "type": "thought",
                        "content": f"Retry retrieval found {added} additional relevant section{'s' if added != 1 else ''}.",
                        "action_type": "searching",
                        "action_source": "doc_rag",
                        "action_data": {"added": added},
                    }
                    sources = sources + retry_result.get("sources", [])
                    yield {"type": "sources", "sources": _public_sources(sources)}
                else:
                    yield {
                        "type": "thought",
                        "content": "Retry retrieval found no new information.",
                        "action_type": "searching",
                        "action_source": "doc_rag",
                    }
            else:
                yield {
                    "type": "thought",
                    "content": "Retry retrieval found no additional results.",
                    "action_type": "searching",
                    "action_source": "doc_rag",
                }

        elif attempt == 2:
            # Retry 2: HyDE-based retrieval — use the weak answer to generate a
            # hypothetical answer and search Qdrant for similar chunks
            yield {
                "type": "thought",
                "content": f"Groundedness still low ({groundedness:.0%}). Trying HyDE-based retrieval from the draft answer...",
                "action_type": "retrying",
                "action_source": "doc_rag",
                "action_data": {"attempt": attempt, "groundedness": round(groundedness, 3), "strategy": "hyde_retrieval"},
            }

            retry_hyde_added = 0
            try:
                # Generate a refined hypothetical answer informed by the weak answer
                hyde_prompt = (
                    f"Original question: {augmented_query}\n\n"
                    f"Previous answer lacking document support: {full_answer[:500]}\n\n"
                    "Based on the gaps in the previous answer, write a refined hypothetical "
                    "answer that would be ideal if the information existed in a knowledge base."
                )
                response = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=get_primary_model(),
                        messages=[
                            {"role": "system", "content": RETRY_HYDE_PROMPT},
                            {"role": "user", "content": hyde_prompt},
                        ],
                        max_tokens=200,
                        temperature=0.3,
                    ),
                    timeout=8.0,
                )
                retry_hyde_answer = (response.choices[0].message.content or "").strip()

                if retry_hyde_answer:
                    logger.info(f"Retry HyDE: generated refined hypothetical answer ({len(retry_hyde_answer)} chars)")
                    hyde_start = monotonic_ms()
                    hyde_embedding = await get_embedding(get_embedding_client(), retry_hyde_answer)
                    target_uid = target_user_id or user_id or ""
                    hyde_chunks = await search_similar_chunks(
                        target_uid, hyde_embedding, match_count=5,
                        similarity_threshold=0.5, tenant_id=tenant_id,
                    )
                    log_latency("retrieval.retry_hyde", elapsed_ms(hyde_start), user_id=user_id, tenant_id=tenant_id, thread_id=thread_id, chunk_count=len(hyde_chunks) if hyde_chunks else 0)

                    if hyde_chunks:
                        # Dedup and merge
                        seen_keys = {c[:500].strip().lower() for c in context_chunks}
                        for chunk in hyde_chunks:
                            content = chunk["content"]
                            key = content[:500].strip().lower()
                            if key not in seen_keys:
                                context_chunks.append(content)
                                hyde_src = {
                                    "id": chunk.get("id", ""),
                                    "document_id": chunk.get("document_id", ""),
                                    "content": content,
                                    "score": chunk.get("similarity", 0),
                                    "retrieval_method": "retry_hyde",
                                }
                                sources.append(hyde_src)
                                context_sources.append(hyde_src)
                                seen_keys.add(key)
                                retry_hyde_added += 1

                        if retry_hyde_added:
                            yield {
                                "type": "thought",
                                "content": f"Retry HyDE retrieval found {retry_hyde_added} additional relevant section{'s' if retry_hyde_added != 1 else ''}.",
                                "action_type": "searching",
                                "action_source": "doc_rag",
                                "action_data": {"added": retry_hyde_added, "strategy": "hyde_retrieval"},
                            }
                            yield {"type": "sources", "sources": _public_sources(sources)}
                        else:
                            yield {
                                "type": "thought",
                                "content": "Retry HyDE retrieval found no new unique chunks.",
                                "action_type": "searching",
                                "action_source": "doc_rag",
                            }
                    else:
                        yield {
                            "type": "thought",
                            "content": "Retry HyDE vector search returned 0 results.",
                            "action_type": "searching",
                            "action_source": "doc_rag",
                        }
                else:
                    logger.warning("Retry HyDE: hypothetical answer generation returned empty")
                    yield {
                        "type": "thought",
                        "content": "Retry HyDE answer generation produced no output.",
                        "action_type": "searching",
                        "action_source": "doc_rag",
                    }
            except Exception as e:
                logger.warning(f"Retry HyDE retrieval failed: {e}")
                yield {
                    "type": "thought",
                    "content": f"Retry HyDE retrieval encountered an error: {e}",
                    "action_type": "searching",
                    "action_source": "doc_rag",
                }

    # ── Chain-of-Verification (CoVe): secondary check after groundedness ──
    cove_results = None
    if is_grounded and full_answer and context_chunks:
        try:
            cove_start = monotonic_ms()
            yield {
                "type": "thought",
                "content": "Running Chain-of-Verification to independently fact-check claims...",
                "action_type": "verifying",
                "action_source": "doc_rag",
                "action_data": {"stage": "cove_start"},
            }
            cove_results = await chain_of_verification(
                full_answer, context_chunks, client, get_primary_model(),
            )
            log_latency("llm.cove", elapsed_ms(cove_start), user_id=user_id, tenant_id=tenant_id, thread_id=thread_id, verified=cove_results["verified"])
            logger.info(
                f"Chain-of-Verification: verified={cove_results['verified']}, "
                f"support_ratio={1.0 - len(cove_results['unsupported_claims']) / max(len(cove_results['verification_questions']), 1):.2f}, "
                f"questions={len(cove_results['verification_questions'])}, "
                f"unsupported={len(cove_results['unsupported_claims'])}"
            )
            print(
                f"[DOC_RAG] CoVe: verified={cove_results['verified']}, "
                f"questions={len(cove_results['verification_questions'])}, "
                f"unsupported={len(cove_results['unsupported_claims'])}"
            )
            if not cove_results["verified"]:
                is_grounded = False
                yield {
                    "type": "thought",
                    "content": f"Chain-of-Verification found {len(cove_results['unsupported_claims'])} unsupported claim(s). Marking as not fully grounded.",
                    "action_type": "guardrail",
                    "action_source": "doc_rag",
                    "action_data": {
                        "stage": "cove_fail",
                        "unsupported_claims": cove_results["unsupported_claims"],
                        "support_ratio": round(1.0 - len(cove_results["unsupported_claims"]) / max(len(cove_results["verification_questions"]), 1), 3),
                    },
                }
            else:
                yield {
                    "type": "thought",
                    "content": "Chain-of-Verification passed — claims are well-supported.",
                    "action_type": "verifying",
                    "action_source": "doc_rag",
                    "action_data": {"stage": "cove_pass"},
                }
        except Exception as e:
            logger.warning(f"Chain-of-Verification failed (non-fatal): {e}")
            print(f"[DOC_RAG] CoVe failed: {e}")

    # ── Post-retry groundedness handling ──
    if not is_grounded and context_chunks:
        yield {
            "type": "thought",
            "content": f"Groundedness still low after retry ({groundedness:.0%}). Adding disclaimer.",
            "action_type": "guardrail",
            "action_source": "doc_rag",
            "action_data": {"groundedness": round(groundedness, 3), "retried": attempt > 0},
        }
        disclaimer = (
            "\n\n---\n⚠️ *Note: Parts of this answer may not be directly sourced from your documents. "
            "Please verify the information independently.*"
        )
        yield {"type": "token", "content": disclaimer}

    all_retrieval_log_ids = retrieval_log_ids + retry_retrieval_log_ids
    final_doc_count = sum(1 for s in sources if s.get("document_id") != "web_search")
    final_web_count = sum(1 for s in sources if s.get("document_id") == "web_search" or s.get("url"))
    rag_quality_data = {
        "type": "rag_quality",
        "retrieval_log_ids": all_retrieval_log_ids,
        "groundedness": round(groundedness, 3),
        "groundedness_flag": not is_grounded,
        "retrieval_quality": quality,
        "retried": attempt > 0,
        "diagnostics": {
            "channel": channel,
            "doc_chunk_count": final_doc_count,
            "web_result_count": final_web_count,
            "used_web_fallback": used_web_fallback or use_hybrid,
            "web_fallback_allowed": allow_web_fallback,
            "query_variant_count": len(all_queries),
            **({"fallback_reason": "web_augmented"} if used_web_fallback or use_hybrid else {}),
        },
    }
    if cove_results is not None:
        rag_quality_data["cove"] = {
            "verified": cove_results["verified"],
            "question_count": len(cove_results["verification_questions"]),
            "unsupported_count": len(cove_results["unsupported_claims"]),
            "unsupported_claims": cove_results["unsupported_claims"],
        }
    yield rag_quality_data
