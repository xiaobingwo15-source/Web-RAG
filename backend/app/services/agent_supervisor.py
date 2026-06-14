import asyncio
import logging
from collections.abc import AsyncGenerator
from openai import APIError, RateLimitError
from app.services.gemini import get_llm_client, get_primary_model, _extract_retry_delay
from app.services.agents import doc_rag_agent, sql_sub_agent, web_search_agent, plan_executor, react_agent

logger = logging.getLogger(__name__)

VALID_ROUTES = {"doc_rag", "sql", "web_search", "general", "plan_execute", "react"}

CLASSIFICATION_SYSTEM_PROMPT = (
    "Classify the user query into exactly one category: "
    "doc_rag (document/knowledge base questions), "
    "sql (database/data queries), "
    "web_search (current events, real-time info), "
    "general (everything else). "
    "Reply with ONLY the category name."
)


def _resolve_target_user_id(token: str, user_id: str, tenant_id: str | None = None) -> tuple[bool, str | None]:
    """Resolve the effective user_id for RAG retrieval.

    For client users with access to admin's shared knowledge base, returns
    the admin's user_id so retrieval searches the admin's documents.

    Returns (use_documents, target_user_id).
    """
    try:
        from app.services.database import get_db, get_tenant_admin_user_id

        db = get_db()  # service-role client - bypasses RLS
        profile = db.table("profiles").select("role").eq("id", user_id).maybe_single().execute()
        if profile.data and profile.data.get("role") == "client":
            admin_id = get_tenant_admin_user_id(tenant_id) if tenant_id else None
            if admin_id:
                docs = db.table("documents").select("id, status").eq("tenant_id", tenant_id).eq("user_id", admin_id).execute()
                has_processed = any(d.get("status") == "processed" for d in (docs.data or []))
                logger.info(f"Client {user_id}: admin shared docs available={has_processed} (admin_id={admin_id}, count={len(docs.data or [])})")
                if has_processed:
                    return True, admin_id
    except Exception as e:
        logger.warning(f"Error checking shared docs for client: {e}")
    return False, None


async def route_query(
    message: str,
    use_documents: bool,
    enable_sql: bool = False,
    enable_web_search: bool = False,
) -> str:
    lower = message.lower()
    if use_documents:
        # Detect complex multi-part queries for plan-and-execute
        multi_part_indicators = ["compare", "and also", "as well as", "both", "difference between"]
        if any(ind in lower for ind in multi_part_indicators):
            return "plan_execute"
        return "doc_rag"
    if enable_sql and any(w in lower for w in ["sales", "revenue", "sql", "query database", "total sales", "revenue report"]):
        return "sql"
    if enable_web_search and any(w in lower for w in ["search online", "find online", "look up", "latest news", "current events"]):
        return "web_search"
    return "general"


async def route_query_llm(
    message: str,
    enable_sql: bool = False,
    enable_web_search: bool = False,
) -> str:
    """LLM-based intent classification with keyword fallback."""
    try:
        client = get_llm_client()
        model = get_primary_model()

        async def _classify() -> str:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                    {"role": "user", "content": message},
                ],
                max_tokens=10,
                temperature=0,
            )
            return (response.choices[0].message.content or "").strip().lower()

        raw = await asyncio.wait_for(_classify(), timeout=3.0)

        route = raw.replace(" ", "_").replace("-", "_")
        if route not in VALID_ROUTES:
            for valid in VALID_ROUTES:
                if route.startswith(valid):
                    route = valid
                    break
            else:
                logger.warning(f"LLM returned invalid route '{raw}', falling back to keyword routing")
                return await route_query(message, False, enable_sql, enable_web_search)

        print(f"[AGENT] LLM routing decision: {raw} -> {route}")
        logger.info(f"LLM routing decision: {raw} -> {route}")
        return route

    except asyncio.TimeoutError:
        logger.warning("LLM routing timed out (3s), falling back to keyword routing")
        return await route_query(message, False, enable_sql, enable_web_search)
    except Exception as e:
        logger.warning(f"LLM routing failed: {e}, falling back to keyword routing")
        return await route_query(message, False, enable_sql, enable_web_search)


async def execute(
    token: str,
    user_id: str,
    message: str,
    history: list,
    thread_id: str,
    use_documents: bool = False,
    retrieval_mode: str = "hybrid",
    enable_web_search: bool = False,
    enable_sql: bool = False,
    images: list[str] | None = None,
    tenant_id: str | None = None,
    target_user_id: str | None = None,
) -> AsyncGenerator[dict, None]:
    client = get_llm_client()

    # Resolve target_user_id for client users - always, even when use_documents=True
    # (frontend may cache use_documents=True from a previous request, but we still
    # need to redirect to the admin's knowledge base for client users)
    effective_target_user_id = target_user_id or user_id
    if target_user_id is None:
        auto_enabled, resolved_id = _resolve_target_user_id(token, user_id, tenant_id)
        if auto_enabled:
            effective_target_user_id = resolved_id or effective_target_user_id
            use_documents = True  # Always use RAG for clients with shared docs

    yield {
        "type": "thought",
        "content": f'Analyzing query: "{message[:80]}{"..." if len(message) > 80 else ""}',
        "action_type": "analyzing",
        "action_source": "supervisor",
        "action_data": {"query": message},
    }

    # Client users with shared docs always go through doc_rag - skip routing
    if use_documents:
        route = "doc_rag"
    else:
        route = await route_query_llm(message, enable_sql, enable_web_search)
    logger.info(f"Routed to: {route} (use_documents={use_documents}, enable_sql={enable_sql}, enable_web_search={enable_web_search})")

    route_labels = {
        "doc_rag": "Document knowledge base",
        "sql": "Database query",
        "web_search": "Web search",
        "general": "General assistant",
        "plan_execute": "Multi-step planning",
        "react": "Dynamic reasoning",
    }
    route_label = route_labels.get(route, route)
    yield {
        "type": "thought",
        "content": f"Routing to: {route_label}",
        "action_type": "routing",
        "action_source": "supervisor",
        "action_data": {"route": route},
    }

    try:
        if route == "sql" and enable_sql:
            async for event in sql_sub_agent.execute(message, history, images=images):
                yield event
        elif route == "web_search" and enable_web_search:
            async for event in web_search_agent.execute(message, history, images=images):
                yield event
        elif route == "plan_execute" and use_documents:
            async for event in plan_executor.execute(token, user_id, message, history, target_user_id=effective_target_user_id, images=images, tenant_id=tenant_id, thread_id=thread_id):
                yield event
        elif route == "react" and use_documents:
            async for event in react_agent.execute(token, user_id, message, history, target_user_id=effective_target_user_id, images=images, tenant_id=tenant_id, thread_id=thread_id):
                yield event
        elif route == "doc_rag" and use_documents:
            async for event in doc_rag_agent.execute(token, user_id, message, history, retrieval_mode, target_user_id=effective_target_user_id, images=images, tenant_id=tenant_id, thread_id=thread_id, allow_web_fallback=enable_web_search):
                yield event
        else:
            from app.services.gemini import generate_chat_response_stream
            async for chunk in generate_chat_response_stream(client, message, history, images=images):
                yield {"type": "token", "content": chunk}
    except Exception as e:
        logger.error(f"Agent execution failed: {e}", exc_info=True)
        if isinstance(e, RateLimitError):
            retry_hint = _extract_retry_delay(e)
            msg = f"Rate limit reached. Please wait {int(retry_hint)} seconds and try again."
            yield {"type": "error", "content": msg, "error_code": "rate_limit"}
        else:
            yield {
                "type": "error",
                "content": "The AI service is temporarily unavailable. Please try again in a moment.",
                "error_code": "server_error",
            }
