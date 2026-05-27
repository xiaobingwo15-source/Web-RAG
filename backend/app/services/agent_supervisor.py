import logging
from collections.abc import AsyncGenerator
from openai import APIError, RateLimitError
from app.services.gemini import get_llm_client, _extract_retry_delay
from app.services.agents import doc_rag_agent, sql_sub_agent, web_search_agent

logger = logging.getLogger(__name__)


def _check_shared_docs_available(token: str, user_id: str) -> bool:
    """Check if the user is a client with access to admin's shared knowledge base documents.
    
    Uses the service-role client (bypasses RLS) because the client's token
    cannot read admin profiles/documents due to cascading RLS restrictions.
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
                return has_processed
    except Exception as e:
        logger.warning(f"Error checking shared docs for client: {e}")
    return False


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

    # Auto-enable RAG for client users who have access to admin's shared knowledge base
    if not use_documents:
        if _check_shared_docs_available(token, user_id):
            use_documents = True
            logger.info(f"Auto-enabled RAG for client user {user_id} (admin shared docs detected)")

    yield {"type": "thought", "content": "Analyzing query intent..."}
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
            async for event in doc_rag_agent.execute(token, user_id, message, history, retrieval_mode, images=images):
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
