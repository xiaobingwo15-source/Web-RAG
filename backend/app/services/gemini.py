import asyncio
import logging
import httpx
from openai import AsyncOpenAI, APIError, RateLimitError
from langfuse import observe, get_client
from app.config import Settings
from app.services.circuit_breaker import circuit_breaker, CircuitBreakerOpenError

logger = logging.getLogger(__name__)

_settings = Settings()
PRIMARY_MODEL = _settings.openrouter_model
FALLBACK_MODEL = _settings.openrouter_fallback_model

MAX_RETRIES = 2
BACKOFF_BASE = 1.0
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MISTRAL_BASE_URL = "https://api.mistral.ai/v1"

_llm_clients: dict[tuple[str, str, str], AsyncOpenAI] = {}

RAG_SYSTEM_PROMPT = (
    "You are a knowledgeable assistant with access to a curated knowledge base. "
    "Answer questions using the reference information provided below. "
    "Be conversational, warm, and direct — like a knowledgeable friend, not a corporate FAQ.\n\n"
    "If the reference information does not contain the answer, say "
    "\"I don't have that information in my knowledge base\" — do not guess or fabricate.\n\n"
    "If the reference information doesn't fully cover the question, acknowledge what you do know "
    "and be honest about the gaps. Do not make up information.\n\n"
    "IMPORTANT — Language handling:\n"
    "- Match the user's language. If they write in Chinese, respond in Chinese. If in English, respond in English.\n"
    "- If the user asks for content in a language that is NOT present in the reference material, "
    "answer using the available source language and clearly note: \"The knowledge base currently only contains "
    "[language] content, so I cannot provide an official [requested language] version from the documents.\"\n"
    "- Do NOT fabricate or hallucinate translations as if they were sourced from documents.\n"
    "- If you provide a translation for convenience, clearly label it as \"(translated for reference)\" "
    "and do NOT cite document sources for the translated portions.\n\n"
    "Structure your answer:\n"
    "1. A brief direct answer (1-2 sentences)\n"
    "2. Supporting details with source references\n"
    "3. Sources section\n\n"
    "Do not mention \"documents\", \"uploaded files\", or \"retrieval\" — speak naturally.\n\n"
    "When making claims, reference which source supports them using [1], [2], etc. "
    "At the end of your answer, include a 'Sources' section listing each reference you used.\n\n"
    "Use natural Markdown formatting as appropriate (headings, bullet points, bold for emphasis). "
    "Keep answers well-structured but not overly rigid."
)


def strip_importance_markers(text: str) -> str:
    return text.replace("**", "")


class ImportanceMarkerStripper:
    def __init__(self) -> None:
        self._pending_star = False

    def feed(self, text: str) -> str:
        if not text:
            return ""

        combined = ("*" if self._pending_star else "") + text
        self._pending_star = combined.endswith("*")
        if self._pending_star:
            combined = combined[:-1]

        return strip_importance_markers(combined)

    def flush(self) -> str:
        if not self._pending_star:
            return ""
        self._pending_star = False
        return "*"


def get_model_provider() -> str:
    return Settings().get_model_provider


def get_primary_model() -> str:
    settings = Settings()
    if settings.get_model_provider == "mistral":
        return settings.get_mistral_model
    return settings.get_openrouter_model


def get_llm_client() -> AsyncOpenAI:
    settings = Settings()
    provider = settings.get_model_provider
    if provider == "mistral":
        api_key = settings.get_mistral_api_key
        if not api_key:
            raise RuntimeError("MISTRAL_API_KEY is not configured")
        base_url = MISTRAL_BASE_URL
        headers = None
    else:
        api_key = settings.get_openrouter_api_key
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")
        base_url = OPENROUTER_BASE_URL
        headers = {
            "HTTP-Referer": settings.frontend_url,
            "X-Title": "Web-RAG",
        }

    cache_key = (provider, base_url, api_key)
    if cache_key not in _llm_clients:
        kwargs = {
            "api_key": api_key,
            "base_url": base_url,
            "timeout": httpx.Timeout(timeout=60.0, connect=10.0),
        }
        if headers:
            kwargs["default_headers"] = headers
        _llm_clients[cache_key] = AsyncOpenAI(**kwargs)
    return _llm_clients[cache_key]


MAX_CONTEXT_TOKENS_DEFAULT = 6000


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return len(text) // 4


def _truncate_context(chunks: list[str], max_tokens: int = MAX_CONTEXT_TOKENS_DEFAULT) -> list[str]:
    """Truncate context chunks to fit within token budget.

    Chunks are assumed to be ordered by relevance (highest first).
    Keeps as many top-ranked chunks as possible, truncating or dropping the rest.
    """
    if not chunks:
        return chunks

    total = sum(_estimate_tokens(c) for c in chunks)
    if total <= max_tokens:
        return chunks

    logger.info(f"Context truncation: {total} estimated tokens > {max_tokens} budget, {len(chunks)} chunks")

    kept = []
    used = 0
    for chunk in chunks:
        chunk_tokens = _estimate_tokens(chunk)
        if used + chunk_tokens <= max_tokens:
            kept.append(chunk)
            used += chunk_tokens
        else:
            # Try to fit a truncated version of this chunk
            remaining = max_tokens - used
            if remaining > 100:  # Only include if we can fit at least 100 tokens
                char_budget = remaining * 4
                kept.append(chunk[:char_budget].rstrip() + "...")
                logger.info(f"Truncated last chunk to {char_budget} chars")
            break

    logger.info(f"Context after truncation: {len(kept)} chunks, ~{used} tokens")
    return kept


def _trim_history(history: list[dict], max_messages: int = 10) -> list[dict]:
    """Keep the last N messages to prevent context window overflow.

    If the history exceeds max_messages, keep the most recent messages.
    """
    if not history or len(history) <= max_messages:
        return history

    return history[-max_messages:]


def _build_messages(
    message: str,
    history: list[dict] | None = None,
    context_chunks: list[str] | None = None,
    system_prompt: str | None = None,
    images: list[str] | None = None,
    context_sources: list[dict] | None = None,
) -> list[dict]:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    if history:
        max_hist = _settings.max_history_messages
        history = _trim_history(history, max_hist)
        messages.extend(history)

    use_rag = bool(context_chunks)
    if use_rag:
        max_tok = _settings.max_context_tokens
        bounded_chunks = _truncate_context(context_chunks, max_tok)
        # Build numbered context with optional filename tags for source attribution
        numbered_chunks = []
        for i, chunk in enumerate(bounded_chunks):
            prefix = f"[{i+1}]"
            # If we have source metadata, include the filename so the LLM can cite by document name
            if context_sources and i < len(context_sources):
                filename = context_sources[i].get("filename") or context_sources[i].get("title") or ""
                if filename:
                    prefix = f"[{i+1}] (Source: {filename})"
            numbered_chunks.append(f"{prefix} {chunk}")
        context = "\n\n".join(numbered_chunks)
        prompt_text = (
            f"Use the following reference information to answer the question:\n\n"
            f"{context}\n\n"
            f"Question: {message}"
        )
    else:
        prompt_text = message

    if images:
        content_parts = [{"type": "text", "text": prompt_text}]
        for img_url in images:
            content_parts.append({"type": "image_url", "image_url": {"url": img_url}})
        messages.append({"role": "user", "content": content_parts})
    else:
        messages.append({"role": "user", "content": prompt_text})
    return messages


def _is_retryable(error: APIError) -> bool:
    status = getattr(error, "status_code", None)
    return status in RETRYABLE_STATUS_CODES


def _extract_retry_delay(error: APIError) -> float:
    """Extract retry delay in seconds from error response, falls back to 60s."""
    try:
        response = getattr(error, "response", None)
        if response is not None:
            body = response.json() if hasattr(response, "json") else {}
            details = body.get("error", body).get("details", [])
            for detail in details:
                if detail.get("@type") == "type.googleapis.com/google.rpc.RetryInfo":
                    delay_str = detail.get("retryDelay", "60s")
                    return float(delay_str.rstrip("s"))
    except (AttributeError, ValueError, KeyError):
        pass
    return 60.0


def _models_to_try() -> list[str]:
    settings = Settings()
    if settings.get_model_provider == "mistral":
        return [settings.get_mistral_model]

    primary_model = settings.get_openrouter_model
    fallback_model = settings.get_openrouter_fallback_model
    models = [primary_model]
    if fallback_model and fallback_model != primary_model:
        models.append(fallback_model)
    return models


@circuit_breaker("llm", failure_threshold=5, recovery_timeout=30.0)
@observe(name="llm_chat", as_type="generation")
async def generate_chat_response(
    client: AsyncOpenAI,
    message: str,
    history: list[dict] | None = None,
    context_chunks: list[str] | None = None,
    images: list[str] | None = None,
    context_sources: list[dict] | None = None,
) -> str:
    langfuse = get_client()
    langfuse.update_current_generation(
        model=get_primary_model(),
        input={"message": message},
    )

    messages = _build_messages(message, history, context_chunks, RAG_SYSTEM_PROMPT if context_chunks else None, images=images, context_sources=context_sources)
    logger.info(f"Generating chat response with {len(context_chunks or [])} context chunks")

    last_error = None
    for model_name in _models_to_try():
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Calling {model_name} (attempt {attempt + 1})")
                langfuse.update_current_generation(model=model_name)

                response = await client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=2048,
                )

                output = strip_importance_markers(response.choices[0].message.content or "")
                langfuse.update_current_generation(output={"response": output})
                return output

            except RateLimitError as e:
                last_error = e
                logger.warning(f"{model_name} rate limited (429), switching to next model")
                break
            except APIError as e:
                last_error = e
                if not _is_retryable(e):
                    raise
                delay = BACKOFF_BASE * (2 ** attempt)
                logger.warning(f"{model_name} attempt {attempt + 1} failed: {getattr(e, 'status_code', '?')}, retrying in {delay:.0f}s")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(delay)

    raise last_error


@observe(name="llm_chat_stream", as_type="generation")
async def generate_chat_response_stream(  # noqa: C901
    client: AsyncOpenAI,
    message: str,
    history: list[dict] | None = None,
    context_chunks: list[str] | None = None,
    images: list[str] | None = None,
    system_prompt: str | None = None,
    context_sources: list[dict] | None = None,
):
    langfuse = get_client()
    langfuse.update_current_generation(
        model=get_primary_model(),
        input={"message": message},
    )

    effective_system_prompt = system_prompt if system_prompt else (RAG_SYSTEM_PROMPT if context_chunks else None)
    messages = _build_messages(message, history, context_chunks, effective_system_prompt, images=images, context_sources=context_sources)
    logger.info(f"Generating streaming chat response with {len(context_chunks or [])} context chunks")

    # Check circuit breaker state before attempting the call
    from app.services.circuit_breaker import get_circuit_breaker
    llm_breaker = get_circuit_breaker("llm", failure_threshold=5, recovery_timeout=30.0)
    if llm_breaker.state == "open":
        logger.warning("LLM circuit breaker is open, rejecting stream call")
        raise CircuitBreakerOpenError("llm", llm_breaker.recovery_timeout)

    last_error = None
    tokens_yielded = False
    marker_stripper = ImportanceMarkerStripper()

    for model_name in _models_to_try():
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Streaming from {model_name} (attempt {attempt + 1})")
                langfuse.update_current_generation(model=model_name)

                stream = await client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=2048,
                    stream=True,
                )

                full_response = ""
                try:
                    async with asyncio.timeout(120):
                        async for chunk in stream:
                            if chunk.choices and chunk.choices[0].delta.content:
                                text = marker_stripper.feed(chunk.choices[0].delta.content)
                                if not text:
                                    continue
                                full_response += text
                                tokens_yielded = True
                                yield text
                except TimeoutError:
                    logger.error(f"Stream timeout on {model_name} after 120s (tokens_yielded={tokens_yielded})")
                    if not tokens_yielded:
                        raise  # retry with next model
                    # Partial response — end gracefully
                    tail = marker_stripper.flush()
                    if tail:
                        full_response += tail
                        yield tail
                    langfuse.update_current_generation(output={"response": full_response})
                    return

                tail = marker_stripper.flush()
                if tail:
                    full_response += tail
                    yield tail

                langfuse.update_current_generation(output={"response": full_response})
                return

            except RateLimitError as e:
                last_error = e
                if tokens_yielded:
                    logger.error(f"Mid-stream rate limit on {model_name}: {e}")
                    raise
                logger.warning(f"{model_name} rate limited (429), switching to next model")
                break
            except APIError as e:
                last_error = e
                if not _is_retryable(e):
                    raise
                if tokens_yielded:
                    logger.error(f"Mid-stream failure on {model_name}: {e}")
                    raise
                delay = BACKOFF_BASE * (2 ** attempt)
                logger.warning(f"Pre-stream {model_name} attempt {attempt + 1} failed: {getattr(e, 'status_code', '?')}, retrying in {delay:.0f}s")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(delay)

    # Record failure in circuit breaker before raising
    llm_breaker._record_failure()
    raise last_error
