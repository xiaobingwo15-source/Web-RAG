"""Plan-and-Execute agent pattern.

Decomposes complex multi-part questions into sub-tasks, executes them
in parallel (document retrieval or web search), and synthesizes a
unified answer from all results.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from app.services.gemini import get_llm_client, get_primary_model, generate_chat_response_stream, RAG_SYSTEM_PROMPT
from app.services.retrieval import retrieve_context
from app.services.web_search import search_web

logger = logging.getLogger(__name__)

PLANNING_SYSTEM_PROMPT = (
    "You are a query planning assistant. Given a user question, decompose it "
    "into 1-3 independent sub-tasks that together fully answer the question.\n\n"
    "Each sub-task should be a standalone search query with a source type:\n"
    "- 'document': search the internal knowledge base\n"
    "- 'web': search the web for current/external information\n"
    "- 'auto': try documents first, fall back to web\n\n"
    "Return a JSON array of objects with 'query' (string) and 'source' (string) fields. "
    "Return ONLY valid JSON, no explanation.\n\n"
    'Example: [{"query": "pricing plans for enterprise", "source": "document"}, '
    '{"query": "Competitor X pricing 2026", "source": "web"}]'
)

MAX_SUB_TASKS = 3


async def _plan_subtasks(query: str, client) -> list[dict]:
    """Use the LLM to decompose a complex query into sub-tasks."""
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=get_primary_model(),
                messages=[
                    {"role": "system", "content": PLANNING_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Question: {query}"},
                ],
                max_tokens=200,
                temperature=0.2,
            ),
            timeout=8.0,
        )
        raw = (response.choices[0].message.content or "").strip()

        # Extract JSON from possible markdown wrapping
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        subtasks = json.loads(raw)
        if not isinstance(subtasks, list):
            subtasks = [subtasks]

        # Validate and limit
        valid = []
        for task in subtasks[:MAX_SUB_TASKS]:
            if isinstance(task, dict) and "query" in task:
                source = task.get("source", "auto")
                if source not in ("document", "web", "auto"):
                    source = "auto"
                valid.append({"query": task["query"], "source": source})

        if valid:
            logger.info(f"Plan: {len(valid)} sub-tasks for query '{query[:60]}'")
            print(f"[PLAN] {len(valid)} sub-tasks: {[t['query'][:40] for t in valid]}")
            return valid

    except (json.JSONDecodeError, IndexError, KeyError) as e:
        logger.warning(f"Plan parsing failed: {e}")
    except Exception as e:
        logger.warning(f"Planning failed: {e}")

    # Fallback: single task with the original query
    return [{"query": query, "source": "auto"}]


async def _execute_subtask(
    subtask: dict,
    token: str | None,
    user_id: str | None,
    target_user_id: str | None,
    tenant_id: str | None,
    thread_id: str | None,
) -> dict:
    """Execute a single sub-task: retrieve from documents or search the web."""
    query = subtask["query"]
    source = subtask["source"]
    chunks = []
    sources = []

    if source in ("document", "auto"):
        try:
            result = await retrieve_context(
                token, user_id, query,
                mode="hybrid",
                target_user_id=target_user_id,
                tenant_id=tenant_id,
                thread_id=thread_id,
            )
            chunks = result.get("chunks", [])
            sources = result.get("sources", [])
        except Exception as e:
            logger.warning(f"Document retrieval failed for '{query[:40]}': {e}")

    if source == "web" or (source == "auto" and not chunks):
        try:
            web_results = await search_web(query, max_results=3)
            if web_results:
                for r in web_results:
                    content = f"[Web] {r['title']}: {r['content'][:500]}"
                    chunks.append(content)
                    sources.append({
                        "id": f"web_{r['url']}",
                        "document_id": "web_search",
                        "content": content,
                        "score": 0.0,
                        "title": r["title"],
                        "url": r["url"],
                    })
        except Exception as e:
            logger.warning(f"Web search failed for '{query[:40]}': {e}")

    return {"query": query, "source": source, "chunks": chunks, "sources": sources}


def _merge_results(results: list[dict]) -> tuple[list[str], list[dict], list[dict]]:
    """Merge sub-task results, deduplicating by content.

    Returns:
        (all_chunks, all_sources, context_sources) — context_sources is aligned 1:1 with all_chunks
    """
    seen_chunk_keys: set[str] = set()
    seen_source_keys: set[str] = set()
    all_chunks: list[str] = []
    all_sources: list[dict] = []
    context_sources: list[dict] = []  # Aligned with all_chunks for LLM source attribution

    for result in results:
        result_chunks = result.get("chunks", [])
        result_sources = result.get("sources", [])
        for i, chunk in enumerate(result_chunks):
            key = chunk[:200].strip().lower()
            if key not in seen_chunk_keys:
                seen_chunk_keys.add(key)
                all_chunks.append(chunk)
                if i < len(result_sources):
                    context_sources.append(result_sources[i])
                else:
                    context_sources.append({})
        for src in result_sources:
            key = src.get("content", "")[:200].strip().lower()
            if key not in seen_source_keys:
                seen_source_keys.add(key)
                all_sources.append(src)

    return all_chunks, all_sources, context_sources


def _public_sources(sources: list[dict]) -> list[dict]:
    return [{k: v for k, v in source.items() if k != "content"} for source in sources]


async def execute(
    token: str | None,
    user_id: str | None,
    message: str,
    history: list,
    target_user_id: str | None = None,
    images: list[str] | None = None,
    tenant_id: str | None = None,
    thread_id: str | None = None,
) -> AsyncGenerator[dict, None]:
    """Plan-and-Execute pipeline: decompose, execute in parallel, synthesize."""

    yield {
        "type": "thought",
        "content": "Analyzing query complexity...",
        "action_type": "planning",
        "action_source": "plan_executor",
        "action_data": {"query": message},
    }

    client = get_llm_client()
    subtasks = await _plan_subtasks(message, client)

    if len(subtasks) == 1 and subtasks[0]["query"] == message:
        # Simple query — no decomposition needed, fall back to single retrieval
        yield {
            "type": "thought",
            "content": "Query is straightforward — executing directly.",
            "action_type": "executing",
            "action_source": "plan_executor",
        }
    else:
        yield {
            "type": "thought",
            "content": f"Decomposed into {len(subtasks)} sub-tasks. Executing in parallel...",
            "action_type": "executing",
            "action_source": "plan_executor",
            "action_data": {"subtasks": [{"query": t["query"][:60], "source": t["source"]} for t in subtasks]},
        }

    # Execute all sub-tasks in parallel with a global timeout
    task_coroutines = [
        _execute_subtask(st, token, user_id, target_user_id, tenant_id, thread_id)
        for st in subtasks
    ]
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*task_coroutines, return_exceptions=True),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        logger.warning("Plan executor: sub-task execution timed out (30s)")
        results = []

    # Filter out exceptions
    valid_results = [r for r in results if isinstance(r, dict)]
    all_chunks, all_sources, context_sources = _merge_results(valid_results)

    yield {
        "type": "thought",
        "content": f"Gathered {len(all_chunks)} context sections from {len(valid_results)} sub-tasks.",
        "action_type": "synthesizing",
        "action_source": "plan_executor",
        "action_data": {
            "total_chunks": len(all_chunks),
            "total_sources": len(all_sources),
            "subtask_count": len(subtasks),
        },
    }

    if not all_chunks:
        yield {"type": "token", "content": "I wasn't able to find relevant information for any part of your question. Could you try rephrasing?"}
        return

    yield {"type": "sources", "sources": _public_sources(all_sources)}

    # Synthesize a unified answer
    from app.services.agents.doc_rag_agent import CORRECTIVE_RAG_SYSTEM_PROMPT
    has_web = any(s.get("document_id") == "web_search" for s in all_sources)
    system_prompt = CORRECTIVE_RAG_SYSTEM_PROMPT if has_web else RAG_SYSTEM_PROMPT

    yield {
        "type": "thought",
        "content": "Synthesizing unified answer from all sub-task results...",
        "action_type": "synthesizing",
        "action_source": "plan_executor",
    }

    async for chunk in generate_chat_response_stream(client, message, history, all_chunks, images=images, system_prompt=system_prompt, context_sources=context_sources):
        yield {"type": "token", "content": chunk}
