import logging
from collections.abc import AsyncGenerator
from google.genai.errors import ServerError, ClientError
from app.services.gemini import get_gemini_client, _extract_retry_delay
from app.services.agents import doc_rag_agent, sql_sub_agent, web_search_agent

logger = logging.getLogger(__name__)


async def route_query(message: str, use_documents: bool) -> str:
    lower = message.lower()
    if any(w in lower for w in ["sales", "revenue", "sql", "query database", "total sales", "revenue report"]):
        return "sql"
    if any(w in lower for w in ["search online", "find online", "look up", "latest news", "current events"]):
        return "web_search"
    if use_documents:
        return "doc_rag"
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
) -> AsyncGenerator[dict, None]:
    client = get_gemini_client()

    yield {"type": "thought", "content": "Analyzing query intent..."}
    route = await route_query(message, use_documents)
    yield {"type": "thought", "content": f"Routed to: {route}"}

    try:
        if route == "sql" and enable_sql:
            async for event in sql_sub_agent.execute(message, history):
                yield event
        elif route == "web_search" and enable_web_search:
            async for event in web_search_agent.execute(message, history):
                yield event
        elif route == "doc_rag" and use_documents:
            async for event in doc_rag_agent.execute(token, user_id, message, history, retrieval_mode):
                yield event
        else:
            from app.services.gemini import generate_chat_response_stream
            async for chunk in generate_chat_response_stream(client, message, history):
                yield {"type": "token", "content": chunk}
    except Exception as e:
        logger.error(f"Agent execution failed: {e}", exc_info=True)
        if isinstance(e, (ServerError, ClientError)) and getattr(e, "code", None) == 429:
            retry_hint = _extract_retry_delay(e)
            msg = f"Rate limit reached. Please wait {int(retry_hint)} seconds and try again."
            yield {"type": "error", "content": msg, "error_code": "rate_limit"}
        else:
            yield {
                "type": "error",
                "content": "The AI service is temporarily unavailable. Please try again in a moment.",
                "error_code": "server_error",
            }
