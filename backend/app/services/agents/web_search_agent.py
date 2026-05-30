import logging
from collections.abc import AsyncGenerator
from app.services.gemini import get_llm_client, generate_chat_response_stream
from app.services.web_search import search_web

logger = logging.getLogger(__name__)


async def execute(
    message: str,
    history: list,
    images: list[str] | None = None,
) -> AsyncGenerator[dict, None]:
    yield {
        "type": "thought",
        "content": f"Searching the web for: {message}",
        "action_type": "searching",
        "action_source": "web_search",
        "action_data": {"query": message},
    }

    results = await search_web(message, max_results=5)

    if not results:
        yield {
            "type": "thought",
            "content": "No web results found.",
            "action_type": "no_results",
            "action_source": "web_search",
            "action_data": {"query": message},
        }
        yield {"type": "token", "content": "I appreciate you reaching out. I wasn't able to find reliable information on that topic at the moment. Is there anything else I can assist you with?"}
        return

    sources = [{"title": r["title"], "url": r["url"], "snippet": r["content"][:300] + "..." if len(r["content"]) > 300 else r["content"]} for r in results]
    source_titles = ", ".join(f"\"{s['title']}\"" for s in sources[:3])
    extra = f" +{len(sources) - 3} more" if len(sources) > 3 else ""

    yield {
        "type": "thought",
        "content": f"Found {len(results)} results: {source_titles}{extra}",
        "action_type": "synthesizing",
        "action_source": "web_search",
        "action_data": {
            "result_count": len(results),
            "sources": sources,
        },
    }

    context = "\n\n".join(
        f"[{r['title']}]({r['url']}): {r['content'][:300]}" for r in results
    )
    prompt = f"Based on the following web search results, answer the user's question.\n\nResults:\n{context}\n\nQuestion: {message}"

    client = get_llm_client()
    async for chunk in generate_chat_response_stream(client, prompt, history, images=images):
        yield {"type": "token", "content": chunk}
