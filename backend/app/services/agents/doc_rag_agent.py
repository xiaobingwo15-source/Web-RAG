import logging
from collections.abc import AsyncGenerator
from app.services.retrieval import retrieve_context
from app.services.gemini import get_gemini_client, generate_chat_response_stream

logger = logging.getLogger(__name__)


async def execute(
    token: str,
    user_id: str,
    message: str,
    history: list,
    retrieval_mode: str = "hybrid",
) -> AsyncGenerator[dict, None]:
    yield {"type": "thought", "content": "Searching documents for relevant context..."}

    context_chunks = await retrieve_context(token, user_id, message, mode=retrieval_mode)

    if not context_chunks:
        yield {"type": "thought", "content": "No relevant documents found. Providing general answer."}
        client = get_gemini_client()
        async for chunk in generate_chat_response_stream(client, message, history):
            yield {"type": "token", "content": chunk}
        return

    yield {"type": "thought", "content": f"Found {len(context_chunks)} relevant chunks. Generating answer..."}

    client = get_gemini_client()
    async for chunk in generate_chat_response_stream(client, message, history, context_chunks):
        yield {"type": "token", "content": chunk}
