import logging
from collections.abc import AsyncGenerator
from app.services.retrieval import retrieve_context
from app.services.gemini import get_llm_client, generate_chat_response_stream, RAG_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def _build_augmented_query(message: str, history: list, max_turns: int = 3) -> str:
    """Prepend recent user messages to give the embedding model context for follow-up queries."""
    recent_user_msgs = [
        msg["content"] if isinstance(msg["content"], str)
        else next((p["text"] for p in msg["content"] if p.get("type") == "text"), "")
        for msg in history[-max_turns * 2:]
        if msg["role"] == "user"
    ]
    if not recent_user_msgs:
        return message
    context_prefix = " ".join(recent_user_msgs)
    return f"{context_prefix} {message}"


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

    augmented_query = _build_augmented_query(message, history)
    context_chunks = await retrieve_context(token, user_id, augmented_query, mode=retrieval_mode, target_user_id=target_user_id)
    print(f"[DOC_RAG] Retrieved {len(context_chunks)} context chunks for user_id={user_id}")

    if not context_chunks:
        yield {"type": "thought", "content": "No matching content found in your documents."}
        yield {"type": "token", "content": "Thank you for your question. Unfortunately, I don't have the specific details needed to address this right now. Could you try rephrasing, or let me know if there's something else I can help with?"}
        return

    yield {"type": "thought", "content": f"Found {len(context_chunks)} relevant chunks. Generating answer..."}

    client = get_llm_client()
    async for chunk in generate_chat_response_stream(client, message, history, context_chunks, images=images, system_prompt=RAG_SYSTEM_PROMPT):
        yield {"type": "token", "content": chunk}
