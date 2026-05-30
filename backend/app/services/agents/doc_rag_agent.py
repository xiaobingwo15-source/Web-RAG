import asyncio
import logging
from collections.abc import AsyncGenerator
from app.services.retrieval import retrieve_context
from app.services.gemini import get_llm_client, generate_chat_response_stream, RAG_SYSTEM_PROMPT, PRIMARY_MODEL

logger = logging.getLogger(__name__)

REWRITE_SYSTEM_PROMPT = (
    "You are a query rewriting assistant. Given a conversation history and a "
    "follow-up question, rewrite the question as a standalone search query that "
    "contains all necessary context. Return ONLY the rewritten query, nothing else."
)


async def rewrite_query(message: str, history: list, client) -> str:
    """Rewrite a follow-up query into a standalone search query using the LLM."""
    if not history:
        return message

    recent_user_msgs = [
        msg["content"] if isinstance(msg["content"], str)
        else next((p["text"] for p in msg["content"] if p.get("type") == "text"), "")
        for msg in history[-6:]
        if msg["role"] == "user"
    ]
    if not recent_user_msgs:
        return message

    context_block = "\n".join(f"- {m}" for m in recent_user_msgs)
    user_prompt = (
        f"Conversation history:\n{context_block}\n\n"
        f"Follow-up question: {message}\n\n"
        f"Standalone search query:"
    )

    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=PRIMARY_MODEL,
                messages=[
                    {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=50,
                temperature=0.2,
            ),
            timeout=5.0,
        )
        rewritten = response.choices[0].message.content.strip()
        if rewritten:
            logger.info(f"Query rewrite: '{message[:60]}' -> '{rewritten[:60]}'")
            print(f"[DOC_RAG] Query rewrite: '{message[:60]}' -> '{rewritten[:60]}'")
            return rewritten
    except Exception as e:
        logger.warning(f"Query rewrite failed, using original: {e}")

    return message


async def execute(
    token: str,
    user_id: str,
    message: str,
    history: list,
    retrieval_mode: str = "hybrid",
    target_user_id: str | None = None,
    images: list[str] | None = None,
) -> AsyncGenerator[dict, None]:
    yield {
        "type": "thought",
        "content": f"Searching documents ({retrieval_mode} mode)...",
        "action_type": "searching",
        "action_source": "doc_rag",
        "action_data": {"query": message, "mode": retrieval_mode},
    }

    client = get_llm_client()
    augmented_query = await rewrite_query(message, history, client)
    if augmented_query != message:
        yield {
            "type": "thought",
            "content": f"Expanded query: \"{augmented_query}\"",
            "action_type": "searching",
            "action_source": "doc_rag",
            "action_data": {"original_query": message, "expanded_query": augmented_query},
        }

    retrieval_result = await retrieve_context(token, user_id, augmented_query, mode=retrieval_mode, target_user_id=target_user_id)
    context_chunks = retrieval_result["chunks"]
    sources = retrieval_result["sources"]
    print(f"[DOC_RAG] Retrieved {len(context_chunks)} context chunks for user_id={user_id}")

    if not context_chunks:
        yield {
            "type": "thought",
            "content": "No matching content found in your documents.",
            "action_type": "no_results",
            "action_source": "doc_rag",
            "action_data": {"query": message},
        }
        yield {"type": "token", "content": "Thank you for your question. Unfortunately, I don't have the specific details needed to address this right now. Could you try rephrasing, or let me know if there's something else I can help with?"}
        return

    # Build content previews — show what the agent actually found
    content_previews = []
    for i, chunk in enumerate(context_chunks):
        preview = chunk[:200].strip()
        if len(chunk) > 200:
            preview += "..."
        content_previews.append(preview)

    # Build a short summary showing what was found
    found_summary = f"Found {len(context_chunks)} relevant section{'s' if len(context_chunks) != 1 else ''} from your documents."
    if content_previews:
        # Show a hint of the first match
        first_snippet = content_previews[0][:120]
        if len(content_previews[0]) > 120:
            first_snippet += "..."
        found_summary += f" Top match: \"{first_snippet}\""

    yield {
        "type": "thought",
        "content": found_summary,
        "action_type": "synthesizing",
        "action_source": "doc_rag",
        "action_data": {
            "chunk_count": len(context_chunks),
            "mode": retrieval_mode,
            "content_previews": content_previews,
        },
    }

    yield {
        "type": "thought",
        "content": "Generating answer from matched documents...",
        "action_type": "synthesizing",
        "action_source": "doc_rag",
        "action_data": {"stage": "llm_generation"},
    }

    async for chunk in generate_chat_response_stream(client, message, history, context_chunks, images=images, system_prompt=RAG_SYSTEM_PROMPT):
        yield {"type": "token", "content": chunk}
