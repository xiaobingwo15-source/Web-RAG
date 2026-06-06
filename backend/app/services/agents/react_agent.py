"""ReAct (Reasoning + Acting) agent for RAG.

Replaces the fixed DAG pipeline with a dynamic reasoning loop where the LLM
decides at each step what to do next: retrieve more, search the web, generate
an answer, or declare done.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from app.services.gemini import (
    get_llm_client, get_primary_model,
    generate_chat_response_stream, RAG_SYSTEM_PROMPT,
)
from app.services.retrieval import retrieve_context
from app.services.web_search import search_web
from app.services.qdrant_db import search_similar_chunks
from app.services.embeddings import get_embedding_client, get_embedding
from app.services.groundedness import check_groundedness_with_llm

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5
MAX_CONTEXT_CHUNKS = 20  # Cap context growth across iterations

THINK_SYSTEM_PROMPT = (
    "You are a reasoning agent with access to a document knowledge base and web search. "
    "Given the user's question and the context gathered so far, decide the NEXT action.\n\n"
    "Possible actions:\n"
    "- 'retrieve': search the knowledge base with a new query\n"
    "- 'web_search': search the web for information\n"
    "- 'generate': you have enough context to answer\n"
    "- 'done': the question is answered or cannot be answered\n\n"
    "Return a JSON object with:\n"
    "- 'type': one of the action types above\n"
    "- 'reasoning': brief explanation of why you chose this action\n"
    "- 'query': (for retrieve/web_search) the search query to use\n\n"
    "Return ONLY valid JSON, no markdown wrapping."
)

VERIFY_SYSTEM_PROMPT = (
    "You are a verification assistant. Given an answer and the source context it was "
    "derived from, determine if the answer is well-supported by the context.\n\n"
    "Reply with ONLY 'yes' if the answer is grounded in the context, or 'no' if it "
    "contains claims not supported by the context."
)


async def _think(query: str, context_chunks: list[str], iteration: int, client) -> dict:
    """Ask the LLM what to do next based on current context."""
    context_preview = ""
    if context_chunks:
        context_preview = "\n---\n".join(c[:300] for c in context_chunks[:5])
        context_preview = f"\n\nContext gathered so far ({len(context_chunks)} sections):\n{context_preview}"

    prompt = (
        f"Question: {query}\n"
        f"Iteration: {iteration}/{MAX_ITERATIONS}{context_preview}\n\n"
        f"What should I do next?"
    )

    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=get_primary_model(),
                messages=[
                    {"role": "system", "content": THINK_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=150,
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

        action = json.loads(raw)
        if isinstance(action, dict) and "type" in action:
            return action

    except (json.JSONDecodeError, IndexError, KeyError) as e:
        logger.warning(f"ReAct think parse failed: {e}")
    except Exception as e:
        logger.warning(f"ReAct think failed: {e}")

    # Default: generate if we have context, else retrieve
    if context_chunks:
        return {"type": "generate", "reasoning": "Fallback: have context, generating answer"}
    return {"type": "retrieve", "reasoning": "Fallback: no context yet", "query": query}


async def _retrieve(query: str, token: str | None, user_id: str | None,
                    target_user_id: str | None, tenant_id: str | None,
                    thread_id: str | None) -> dict:
    """Retrieve from the document knowledge base."""
    try:
        result = await retrieve_context(
            token, user_id, query, mode="hybrid",
            target_user_id=target_user_id, tenant_id=tenant_id, thread_id=thread_id,
        )
        return {
            "chunks": result.get("chunks", []),
            "sources": result.get("sources", []),
        }
    except Exception as e:
        logger.warning(f"ReAct retrieve failed: {e}")
        return {"chunks": [], "sources": []}


async def _search_web(query: str) -> dict:
    """Search the web for information."""
    try:
        results = await search_web(query, max_results=3)
        chunks = []
        sources = []
        for r in results:
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
        return {"chunks": chunks, "sources": sources}
    except Exception as e:
        logger.warning(f"ReAct web search failed: {e}")
        return {"chunks": [], "sources": []}


async def _verify(answer: str, context_chunks: list[str], client) -> bool:
    """Verify if the answer is grounded in the context."""
    try:
        _, is_grounded = await check_groundedness_with_llm(answer, context_chunks, client, get_primary_model())
        return is_grounded
    except Exception as e:
        logger.warning(f"ReAct verification failed: {e}")
        return True  # Assume grounded on failure


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
    """ReAct dynamic reasoning loop for RAG."""

    yield {
        "type": "thought",
        "content": "Starting dynamic reasoning loop...",
        "action_type": "thinking",
        "action_source": "react",
        "action_data": {"query": message, "max_iterations": MAX_ITERATIONS},
    }

    client = get_llm_client()
    context_chunks: list[str] = []
    all_sources: list[dict] = []
    seen_keys: set[str] = set()

    for iteration in range(MAX_ITERATIONS):
        # Think: what should I do next?
        action = await _think(message, context_chunks, iteration, client)
        action_type = action.get("type", "generate")
        reasoning = action.get("reasoning", "")

        yield {
            "type": "thought",
            "content": f"Step {iteration + 1}: {reasoning}",
            "action_type": action_type,
            "action_source": "react",
            "action_data": {"iteration": iteration + 1, "action": action_type},
        }

        if action_type == "retrieve":
            query = action.get("query", message)
            result = await _retrieve(query, token, user_id, target_user_id, tenant_id, thread_id)
            added = 0
            for chunk in result["chunks"]:
                if len(context_chunks) >= MAX_CONTEXT_CHUNKS:
                    break
                key = chunk[:200].strip().lower()
                if key not in seen_keys:
                    seen_keys.add(key)
                    context_chunks.append(chunk)
                    added += 1
            all_sources.extend(result["sources"])

            yield {
                "type": "thought",
                "content": f"Retrieved {added} new sections (total: {len(context_chunks)}).",
                "action_type": "searching",
                "action_source": "react",
                "action_data": {"added": added, "total": len(context_chunks)},
            }

        elif action_type == "web_search":
            query = action.get("query", message)
            result = await _search_web(query)
            added = 0
            for chunk in result["chunks"]:
                if len(context_chunks) >= MAX_CONTEXT_CHUNKS:
                    break
                key = chunk[:200].strip().lower()
                if key not in seen_keys:
                    seen_keys.add(key)
                    context_chunks.append(chunk)
                    added += 1
            all_sources.extend(result["sources"])

            yield {
                "type": "thought",
                "content": f"Web search found {added} new results (total: {len(context_chunks)}).",
                "action_type": "searching",
                "action_source": "react",
                "action_data": {"added": added, "total": len(context_chunks)},
            }

        elif action_type == "generate":
            if not context_chunks:
                yield {
                    "type": "thought",
                    "content": "No context available. Searching documents first...",
                    "action_type": "searching",
                    "action_source": "react",
                }
                result = await _retrieve(message, token, user_id, target_user_id, tenant_id, thread_id)
                context_chunks = result["chunks"]
                all_sources = result["sources"]

            if not context_chunks:
                yield {"type": "token", "content": "I wasn't able to find relevant information to answer your question. Could you try rephrasing?"}
                return

            yield {"type": "sources", "sources": _public_sources(all_sources)}

            # Generate answer (buffered — don't stream until verified)
            from app.services.agents.doc_rag_agent import CORRECTIVE_RAG_SYSTEM_PROMPT
            has_web = any(s.get("document_id") == "web_search" for s in all_sources)
            system_prompt = CORRECTIVE_RAG_SYSTEM_PROMPT if has_web else RAG_SYSTEM_PROMPT

            full_answer = ""
            async for chunk in generate_chat_response_stream(client, message, history, context_chunks, images=images, system_prompt=system_prompt):
                full_answer += chunk

            # Verify groundedness BEFORE streaming to user
            is_grounded = await _verify(full_answer, context_chunks, client)
            if is_grounded:
                yield {
                    "type": "thought",
                    "content": "Answer verified as grounded in sources.",
                    "action_type": "verified",
                    "action_source": "react",
                }
                yield {"type": "token", "content": full_answer}
                return
            else:
                yield {
                    "type": "thought",
                    "content": "Answer not fully grounded. Refining search...",
                    "action_type": "retrying",
                    "action_source": "react",
                }
                # Loop back to think — answer is discarded, not shown to user

        elif action_type == "done":
            if context_chunks:
                yield {"type": "sources", "sources": _public_sources(all_sources)}
                from app.services.agents.doc_rag_agent import CORRECTIVE_RAG_SYSTEM_PROMPT
                has_web = any(s.get("document_id") == "web_search" for s in all_sources)
                system_prompt = CORRECTIVE_RAG_SYSTEM_PROMPT if has_web else RAG_SYSTEM_PROMPT
                async for chunk in generate_chat_response_stream(client, message, history, context_chunks, images=images, system_prompt=system_prompt):
                    yield {"type": "token", "content": chunk}
            else:
                yield {"type": "token", "content": "I wasn't able to find relevant information to answer your question."}
            return

    # Exhausted iterations — generate with what we have
    yield {
        "type": "thought",
        "content": f"Reached maximum iterations ({MAX_ITERATIONS}). Generating best answer with available context.",
        "action_type": "synthesizing",
        "action_source": "react",
    }

    if context_chunks:
        yield {"type": "sources", "sources": _public_sources(all_sources)}
        from app.services.agents.doc_rag_agent import CORRECTIVE_RAG_SYSTEM_PROMPT
        has_web = any(s.get("document_id") == "web_search" for s in all_sources)
        system_prompt = CORRECTIVE_RAG_SYSTEM_PROMPT if has_web else RAG_SYSTEM_PROMPT
        async for chunk in generate_chat_response_stream(client, message, history, context_chunks, images=images, system_prompt=system_prompt):
            yield {"type": "token", "content": chunk}
    else:
        yield {"type": "token", "content": "I wasn't able to find relevant information to answer your question. Could you try rephrasing or providing more details?"}
