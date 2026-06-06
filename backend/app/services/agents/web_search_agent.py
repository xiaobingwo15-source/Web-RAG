import logging
from collections.abc import AsyncGenerator
from app.services.gemini import get_llm_client, generate_chat_response_stream
from app.services.web_search import search_web

logger = logging.getLogger(__name__)

WEB_SEARCH_SYSTEM_PROMPT = (
    "You are a knowledgeable assistant answering questions using web search results. "
    "Be conversational, warm, and direct.\n\n"
    "When citing information, naturally mention the source by title "
    "(e.g., 'According to [Source Title]...'). "
    "If the search results don't fully answer the question, say so honestly. "
    "Do not make up information.\n\n"
    "Structure your answer:\n"
    "1. A brief direct answer (1-2 sentences)\n"
    "2. Supporting details with source references\n"
    "3. Sources section\n\n"
    "Use natural Markdown formatting (headings, bullet points, bold). "
    "At the end, include a 'Sources' section with URLs."
)


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
    async for chunk in generate_chat_response_stream(client, prompt, history, images=images, system_prompt=WEB_SEARCH_SYSTEM_PROMPT):
        yield {"type": "token", "content": chunk}
