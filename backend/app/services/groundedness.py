GROUNDEDNESS_THRESHOLD = 0.25


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
