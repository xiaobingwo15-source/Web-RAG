import logging
from collections.abc import AsyncGenerator
from openai import APIError, RateLimitError
from app.services.gemini import get_llm_client, _extract_retry_delay
from app.services.agents import doc_rag_agent, sql_sub_agent, web_search_agent

logger = logging.getLogger(__name__)


def _resolve_target_user_id(token: str, user_id: str) -> tuple[bool, str | None]:
    """Resolve the effective user_id for RAG retrieval.

    For client users with access to admin's shared knowledge base, returns
    the admin's user_id so retrieval searches the admin's documents.

    Returns (use_documents, target_user_id).
    """
    try:
        from app.services.database import get_db, get_admin_user_id

        db = get_db()  # service-role client — bypasses RLS
        profile = db.table("profiles").select("role").eq("id", user_id).single().execute()
        if profile.data and profile.data.get("role") == "client":
            admin_id = get_admin_user_id()
            if admin_id:
                docs = db.table("documents").select("id, status").eq("user_id", admin_id).execute()
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
    enable_sql: bool = True,
    enable_web_search: bool = True,
) -> str:
    lower = message.lower()
    if use_documents:
        return "doc_rag"
    if enable_sql and any(w in lower for w in ["sales", "revenue", "sql", "query database", "total sales", "revenue report"]):
        return "sql"
    if enable_web_search and any(w in lower for w in ["search online", "find online", "look up", "latest news", "current events"]):
        return "web_search"
    return "general"


async def execute(
    token: str,
    user_id: str,
    message: str,
    history: list,
    thread_id: str,
    use_documents: bool = False,
    retrieval_mode: str = "hybrid",
    enable_web_search: bool = True,
    enable_sql: bool = True,
    images: list[str] | None = None,
) -> AsyncGenerator[dict, None]:
    client = get_llm_client()

    # Resolve target_user_id for client users — always, even when use_documents=True
    # (frontend may cache use_documents=True from a previous request, but we still
    # need to redirect to the admin's knowledge base for client users)
    target_user_id = user_id
    auto_enabled, resolved_id = _resolve_target_user_id(token, user_id)
    if auto_enabled:
        target_user_id = resolved_id
        use_documents = True  # Always use RAG for clients with shared docs

    yield {"type": "thought", "content": "Analyzing query intent..."}

    # Client users with shared docs always go through doc_rag — skip keyword routing
    if use_documents:
        route = "doc_rag"
    else:
        route = await route_query(message, use_documents, enable_sql, enable_web_search)
    print(f"[AGENT] Routed to: {route} (use_documents={use_documents}, enable_sql={enable_sql}, enable_web_search={enable_web_search})")
    yield {"type": "thought", "content": f"Routed to: {route}"}

    try:
        if route == "sql" and enable_sql:
            async for event in sql_sub_agent.execute(message, history, images=images):
                yield event
        elif route == "web_search" and enable_web_search:
            async for event in web_search_agent.execute(message, history, images=images):
                yield event
        elif route == "doc_rag" and use_documents:
            async for event in doc_rag_agent.execute(token, user_id, message, history, retrieval_mode, target_user_id=target_user_id, images=images):
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
