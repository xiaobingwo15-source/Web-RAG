import asyncio
import logging

logger = logging.getLogger(__name__)

GROUNDEDNESS_THRESHOLD = 0.25
GROUNDEDNESS_LLM_HIGH = 0.5   # Above this: skip LLM check (clearly grounded)
GROUNDEDNESS_LLM_LOW = 0.25   # Below this: call LLM to confirm

GROUNDEDNESS_CHECK_PROMPT = (
    "You are a fact-checker. Compare the ANSWER against the REFERENCE CONTEXT. "
    "Does the answer contain any major claims that are NOT directly supported by the reference context? "
    "Minor rewording and paraphrasing are acceptable. "
    "Reply with ONLY 'yes' (contains ungrounded claims) or 'no' (fully grounded)."
)


def check_groundedness(answer: str, context_chunks: list[str]) -> float:
    """Return the fraction of meaningful answer tokens found in retrieved context."""
    if not context_chunks or not answer:
        return 0.0

    context_text = " ".join(context_chunks).lower()
    answer_lower = answer.lower()

    context_tokens = {token for token in context_text.split() if len(token) > 3}
    answer_tokens = {token for token in answer_lower.split() if len(token) > 3}

    if not answer_tokens:
        return 0.0

    return len(answer_tokens & context_tokens) / len(answer_tokens)


async def check_groundedness_with_llm(
    answer: str,
    context_chunks: list[str],
    client,
    model: str,
) -> tuple[float, bool]:
    """Two-stage groundedness check: token-overlap pre-check + LLM verification.

    Returns:
        (score, is_grounded) — score is the token-overlap ratio, is_grounded is the final verdict.
    """
    score = check_groundedness(answer, context_chunks)

    # Fast path: clearly grounded
    if score >= GROUNDEDNESS_LLM_HIGH:
        return score, True

    # Clearly ungrounded by token overlap — still verify with LLM to handle paraphrasing
    # Borderline zone (0.25-0.5) — use LLM to decide
    try:
        context_preview = "\n\n".join(c[:500] for c in context_chunks[:5])
        user_msg = (
            f"REFERENCE CONTEXT:\n{context_preview}\n\n"
            f"ANSWER:\n{answer[:2000]}\n\n"
            f"Is the answer grounded in the context? Reply ONLY 'yes' or 'no'."
        )
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": GROUNDEDNESS_CHECK_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=5,
                temperature=0,
            ),
            timeout=5.0,
        )
        raw = (response.choices[0].message.content or "").strip().lower()
        is_grounded = raw.startswith("no")  # "no" = no ungrounded claims = grounded
        logger.info(f"LLM groundedness check: score={score:.3f}, llm_raw='{raw}', is_grounded={is_grounded}")
        return score, is_grounded
    except Exception as e:
        logger.warning(f"LLM groundedness check failed, falling back to token-overlap: {e}")
        return score, score >= GROUNDEDNESS_THRESHOLD
