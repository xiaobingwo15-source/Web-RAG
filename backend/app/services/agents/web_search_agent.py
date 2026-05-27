import logging
from collections.abc import AsyncGenerator
from app.services.gemini import get_gemini_client, generate_chat_response_stream
from app.services.web_search import search_web

logger = logging.getLogger(__name__)


async def execute(
    message: str,
    history: list,
) -> AsyncGenerator[dict, None]:
    yield {"type": "thought", "content": f"Searching the web for: {message}"}

    results = await search_web(message, max_results=5)

    if not results:
        yield {"type": "thought", "content": "No web results found."}
        yield {"type": "token", "content": "I couldn't find relevant information on the web for your question."}
        return

    yield {"type": "thought", "content": f"Found {len(results)} results. Synthesizing answer..."}

    context = "\n\n".join(
        f"[{r['title']}]({r['url']}): {r['content'][:300]}" for r in results
    )
    prompt = f"Based on the following web search results, answer the user's question.\n\nResults:\n{context}\n\nQuestion: {message}"

    client = get_gemini_client()
    async for chunk in generate_chat_response_stream(client, prompt, history):
        yield {"type": "token", "content": chunk}
