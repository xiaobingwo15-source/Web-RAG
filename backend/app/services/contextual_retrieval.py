"""Contextual Retrieval: LLM-generated chunk prefixes (Anthropic approach).

During ingestion, each child chunk gets a 1-sentence context prefix that
describes what the chunk is about in the context of the full document.
This prefix is prepended to the chunk text before embedding, improving
retrieval quality by giving the embedding model more context.

Chunks are batched (default 10 per LLM call) to keep costs reasonable.
On LLM failure, chunks are returned unchanged — ingestion never fails
due to contextual retrieval errors.
"""

import logging
import re

from openai import AsyncOpenAI
from app.config import Settings
from app.services.gemini import get_llm_client

logger = logging.getLogger(__name__)

CONTEXT_PREFIX_PROMPT = (
    "Given the document title and a set of text chunks, generate a single "
    "concise sentence (max 30 words) for each chunk that describes what the "
    "chunk is about in the context of the document. "
    "Return one sentence per line, in the same order as the input chunks. "
    "Do NOT number the lines. Do NOT add any other text.\n\n"
    "Document: {doc_title}\n"
    "Summary: {doc_summary}\n\n"
    "Chunks:\n{chunks_text}"
)


def _format_chunks_for_prompt(chunks: list[str], max_chars: int = 300) -> str:
    """Format chunk texts for the LLM prompt, truncating to max_chars each."""
    lines = []
    for i, chunk in enumerate(chunks, start=1):
        truncated = chunk[:max_chars]
        lines.append(f"{i}. {truncated}")
    return "\n".join(lines)


def _parse_context_sentences(raw: str, expected_count: int) -> list[str]:
    """Parse LLM output into a list of context sentences.

    Handles common LLM quirks:
    - Strips numbering ("1. ", "1) ")
    - Strips blank lines
    - Pads with empty strings if LLM returned fewer lines than expected
    """
    lines = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # Strip common numbering patterns: "1. ", "1) ", "- "
        cleaned = re.sub(r"^\d+[\.\)]\s*", "", line)
        cleaned = cleaned.lstrip("- ").strip()
        if cleaned:
            lines.append(cleaned)

    # Pad with empty strings if LLM returned fewer lines
    while len(lines) < expected_count:
        lines.append("")

    return lines[:expected_count]


async def _generate_batch_context(
    client: AsyncOpenAI,
    chunks: list[str],
    doc_title: str,
    doc_summary: str,
) -> list[str]:
    """Generate context sentences for a batch of chunks via LLM.

    Returns a list of context sentences (one per chunk).
    On failure, returns empty strings for all chunks.
    """
    from app.services.gemini import generate_chat_response

    chunks_text = _format_chunks_for_prompt(chunks)
    prompt = CONTEXT_PREFIX_PROMPT.format(
        doc_title=doc_title or "Unknown",
        doc_summary=doc_summary or "No summary available",
        chunks_text=chunks_text,
    )

    try:
        response = await generate_chat_response(
            client,
            message=prompt,
            context_chunks=None,  # no RAG context needed
        )
        return _parse_context_sentences(response, len(chunks))
    except Exception as e:
        logger.warning(f"Contextual retrieval batch failed: {e}")
        return [""] * len(chunks)


def _prepend_context_to_chunk(chunk_text: str, context_sentence: str) -> str:
    """Prepend a context sentence to chunk text.

    Format: "[Context sentence]. Original chunk text"
    If context_sentence is empty, returns chunk_text unchanged.
    """
    if not context_sentence:
        return chunk_text
    # Ensure context ends with a period
    context = context_sentence.rstrip(".")
    return f"{context}. {chunk_text}"


async def add_contextual_prefixes(
    children: list[dict],
    doc_title: str = "",
    doc_summary: str = "",
    batch_size: int | None = None,
) -> list[dict]:
    """Add LLM-generated context prefixes to child chunks.

    For each batch of chunks, calls the LLM to generate a 1-sentence
    context prefix, then prepends it to the chunk text.

    On LLM failure, chunks are returned unchanged (ingestion continues).

    Args:
        children: List of child chunk dicts with at least a "text" key.
        doc_title: Document title for context.
        doc_summary: Document summary for context.
        batch_size: Number of chunks per LLM call (default from settings).

    Returns:
        The same children list with context prefixes prepended to text.
    """
    settings = Settings()
    if batch_size is None:
        batch_size = settings.get_contextual_retrieval_batch_size

    if not children:
        return children

    client = get_llm_client()
    total = len(children)

    logger.info(f"Adding contextual prefixes to {total} chunks (batch_size={batch_size})")

    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch = children[start:end]
        batch_texts = [c["text"] for c in batch]

        context_sentences = await _generate_batch_context(
            client, batch_texts, doc_title, doc_summary,
        )

        for child, context in zip(batch, context_sentences):
            if context:
                child["text"] = _prepend_context_to_chunk(child["text"], context)

        logger.info(f"Contextual prefixes: processed {end}/{total} chunks")

    return children
