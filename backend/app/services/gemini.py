import asyncio
import logging
import httpx
from openai import AsyncOpenAI, APIError, RateLimitError
from langfuse import observe, get_client
from app.config import Settings

logger = logging.getLogger(__name__)

_settings = Settings()
PRIMARY_MODEL = _settings.openrouter_model
FALLBACK_MODEL = _settings.openrouter_fallback_model

MAX_RETRIES = 2
BACKOFF_BASE = 1.0
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_llm_client: AsyncOpenAI | None = None

RAG_SYSTEM_PROMPT = (
    "You are an expert retrieval assistant. You MUST ONLY answer using the reference "
    "documents provided below. If the documents do not contain enough information to "
    "answer the question, respond professionally and warmly, as a knowledgeable representative "
    "would. Acknowledge the question, explain that you don't have that specific information "
    "available, and offer to help with anything else. Do NOT mention \"documents\", \"uploaded "
    "files\", or \"retrieval\" — speak naturally as a person would.\n\n"
    "DO NOT use your training data, general knowledge, or external information. "
    "DO NOT make up or infer information that is not explicitly stated in the documents.\n\n"
    "You must always structure your output using clean, well-spaced Markdown. Adhere "
    "strictly to the following formatting rules:\n\n"
    "1. **Context Grounding**: Begin your answer by explicitly stating the document "
    "domain context found in the retrieved chunks (e.g., \"In the context of basketball...\"). "
    "When referencing information, mention which document it came from.\n\n"
    "2. **Typography Hierarchy**:\n"
    "   - Use `### 1. Major Point Title` for primary categorized sections.\n"
    "   - Use standard paragraphs for core descriptions.\n"
    "   - Use bullet points (`-`) to isolate specific parameters, conditions, or penalties.\n\n"
    "3. **Visual Highlights**:\n"
    "   - Wrap general industry-specific nomenclature or roles in single quotes (e.g., 'offensive player', 'the paint').\n"
    "   - Wrap critical constraints, absolute limits, and negative rules in double asterisks for bold emphasis (e.g., **not allowed to remain for more than three seconds**, **loss of the ball**).\n\n"
    "4. **Disambiguation Guardrails**: If a query matches multiple completely separate "
    "contexts across the documents, list them cleanly using `###` headers for each domain, "
    "append a `**Note:**` callout for critical warnings, and end with an explicit "
    "clarification question using a `####` header asking the user which context they meant."
)


def get_llm_client() -> AsyncOpenAI:
    global _llm_client
    if _llm_client is None:
        settings = Settings()
        _llm_client = AsyncOpenAI(
            api_key=settings.get_openrouter_api_key,
            base_url=OPENROUTER_BASE_URL,
            default_headers={
                "HTTP-Referer": settings.frontend_url,
                "X-Title": "Web-RAG",
            },
            timeout=httpx.Timeout(timeout=60.0, connect=10.0),
        )
    return _llm_client


def _build_messages(
    message: str,
    history: list[dict] | None = None,
    context_chunks: list[str] | None = None,
    system_prompt: str | None = None,
    images: list[str] | None = None,
) -> list[dict]:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    if history:
        messages.extend(history)

    use_rag = bool(context_chunks)
    if use_rag:
        context = "\n---\n".join(context_chunks)
        prompt_text = (
            f"Use the following reference information to answer the question:\n\n"
            f"---\n{context}\n---\n\n"
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
    models = [PRIMARY_MODEL]
    if FALLBACK_MODEL and FALLBACK_MODEL != PRIMARY_MODEL:
        models.append(FALLBACK_MODEL)
    return models


@observe(name="llm_chat", as_type="generation")
async def generate_chat_response(
    client: AsyncOpenAI,
    message: str,
    history: list[dict] | None = None,
    context_chunks: list[str] | None = None,
    images: list[str] | None = None,
) -> str:
    langfuse = get_client()
    langfuse.update_current_generation(
        model=PRIMARY_MODEL,
        input={"message": message},
    )

    messages = _build_messages(message, history, context_chunks, RAG_SYSTEM_PROMPT if context_chunks else None, images=images)
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

                output = response.choices[0].message.content or ""
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
async def generate_chat_response_stream(
    client: AsyncOpenAI,
    message: str,
    history: list[dict] | None = None,
    context_chunks: list[str] | None = None,
    images: list[str] | None = None,
    system_prompt: str | None = None,
):
    langfuse = get_client()
    langfuse.update_current_generation(
        model=PRIMARY_MODEL,
        input={"message": message},
    )

    effective_system_prompt = system_prompt if system_prompt else (RAG_SYSTEM_PROMPT if context_chunks else None)
    messages = _build_messages(message, history, context_chunks, effective_system_prompt, images=images)
    logger.info(f"Generating streaming chat response with {len(context_chunks or [])} context chunks")

    last_error = None
    tokens_yielded = False

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
                                text = chunk.choices[0].delta.content
                                full_response += text
                                tokens_yielded = True
                                yield text
                except TimeoutError:
                    logger.error(f"Stream timeout on {model_name} after 120s (tokens_yielded={tokens_yielded})")
                    if not tokens_yielded:
                        raise  # retry with next model
                    # Partial response — end gracefully
                    langfuse.update_current_generation(output={"response": full_response})
                    return

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

    raise last_error
