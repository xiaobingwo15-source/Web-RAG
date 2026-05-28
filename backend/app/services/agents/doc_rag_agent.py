import logging
from collections.abc import AsyncGenerator
from app.services.retrieval import retrieve_context
from app.services.gemini import get_llm_client, generate_chat_response_stream, RAG_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


async def execute(
    token: str,
    user_id: str,
    message: str,
    history: list,
    retrieval_mode: str = "hybrid",
    target_user_id: str | None = None,
    images: list[str] | None = None,
) -> AsyncGenerator[dict, None]:
    yield {"type": "thought", "content": "Searching documents for relevant context..."}

    context_chunks = await retrieve_context(token, user_id, message, mode=retrieval_mode, target_user_id=target_user_id)
    print(f"[DOC_RAG] Retrieved {len(context_chunks)} context chunks for user_id={user_id}")

    if not context_chunks:
        yield {"type": "thought", "content": "No matching content found in your documents."}
        yield {"type": "token", "content": "I couldn't find relevant information in your uploaded documents to answer this question. Please make sure your documents are uploaded and processed, or try rephrasing your question."}
        return

    yield {"type": "thought", "content": f"Found {len(context_chunks)} relevant chunks. Generating answer..."}

    client = get_llm_client()
    async for chunk in generate_chat_response_stream(client, message, history, context_chunks, images=images, system_prompt=RAG_SYSTEM_PROMPT):
        yield {"type": "token", "content": chunk}
