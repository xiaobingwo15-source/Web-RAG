import asyncio
import logging
from google import genai
from google.genai import types
from google.genai.errors import ServerError, ClientError
from langfuse import observe, get_client
from app.config import Settings

logger = logging.getLogger(__name__)

_settings = Settings()
PRIMARY_MODEL = _settings.gemini_primary_model
FALLBACK_MODEL = _settings.gemini_fallback_model

MAX_RETRIES = 2
BACKOFF_BASE = 1.0
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

RAG_SYSTEM_PROMPT = (
    "You are a helpful assistant that answers questions based on the provided reference documents. "
    "Only use information from the reference context to answer questions. "
    "If the reference documents do not contain enough information to answer the question, "
    "say \"I don't have enough information in the uploaded documents to answer that question.\" "
    "Do not make up or infer information that is not explicitly stated in the documents. "
    "When referencing information, mention which document it came from if possible."
)


def get_gemini_client() -> genai.Client:
    settings = Settings()
    return genai.Client(api_key=settings.google_api_key)


def _build_config(use_rag: bool = False) -> types.GenerateContentConfig:
    config = types.GenerateContentConfig(
        temperature=0.7,
        max_output_tokens=2048,
    )
    if use_rag:
        config.system_instruction = RAG_SYSTEM_PROMPT
    return config


def _build_context_message(chunks: list[str], user_message: str) -> str:
    context = "\n---\n".join(chunks)
    return (
        f"Use the following reference information to answer the question:\n\n"
        f"---\n{context}\n---\n\n"
        f"Question: {user_message}"
    )


def _is_retryable(error) -> bool:
    return getattr(error, "code", None) in RETRYABLE_STATUS_CODES


def _extract_retry_delay(error) -> float:
    """Extract retry delay in seconds from Gemini error response, falls back to 60s."""
    try:
        details = error.details or {}
        error_body = details.get("error", details)
        retry_info = error_body.get("details", [])
        for detail in retry_info:
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


@observe(name="gemini_chat", as_type="generation")
async def generate_chat_response(
    client: genai.Client,
    message: str,
    history: list[types.Content] | None = None,
    context_chunks: list[str] | None = None,
) -> str:
    langfuse = get_client()
    langfuse.update_current_generation(
        model=PRIMARY_MODEL,
        input={"message": message},
    )

    contents = history or []

    use_rag = bool(context_chunks)
    prompt_text = _build_context_message(context_chunks, message) if use_rag else message

    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=prompt_text)],
    ))

    logger.info(f"Generating chat response with {len(context_chunks or [])} context chunks")

    last_error = None
    for model_name in _models_to_try():
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Calling {model_name} (attempt {attempt + 1})")
                langfuse.update_current_generation(model=model_name)

                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=_build_config(use_rag),
                )

                candidate = response.candidates[0]
                output = "".join(
                    part.text for part in candidate.content.parts if part.text
                )
                langfuse.update_current_generation(output={"response": output})
                return output

            except (ServerError, ClientError) as e:
                last_error = e
                if not _is_retryable(e):
                    raise
                delay = _extract_retry_delay(e) if getattr(e, "code", None) == 429 else BACKOFF_BASE * (2 ** attempt)
                logger.warning(f"{model_name} attempt {attempt + 1} failed: {getattr(e, 'code', '?')} {getattr(e, 'status', '?')}, retrying in {delay:.0f}s")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(delay)

    raise last_error


@observe(name="gemini_chat_stream", as_type="generation")
async def generate_chat_response_stream(
    client: genai.Client,
    message: str,
    history: list[types.Content] | None = None,
    context_chunks: list[str] | None = None,
):
    langfuse = get_client()
    langfuse.update_current_generation(
        model=PRIMARY_MODEL,
        input={"message": message},
    )

    contents = history or []

    use_rag = bool(context_chunks)
    prompt_text = _build_context_message(context_chunks, message) if use_rag else message

    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=prompt_text)],
    ))

    logger.info(f"Generating streaming chat response with {len(context_chunks or [])} context chunks")

    last_error = None
    tokens_yielded = False

    for model_name in _models_to_try():
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Streaming from {model_name} (attempt {attempt + 1})")
                langfuse.update_current_generation(model=model_name)

                response_stream = await client.aio.models.generate_content_stream(
                    model=model_name,
                    contents=contents,
                    config=_build_config(use_rag),
                )

                full_response = ""
                async for chunk in response_stream:
                    if chunk.candidates and chunk.candidates[0].content.parts:
                        for part in chunk.candidates[0].content.parts:
                            if part.text:
                                full_response += part.text
                                tokens_yielded = True
                                yield part.text

                langfuse.update_current_generation(output={"response": full_response})
                return

            except (ServerError, ClientError) as e:
                last_error = e
                if not _is_retryable(e):
                    raise
                if tokens_yielded:
                    logger.error(f"Mid-stream failure on {model_name}: {e}")
                    raise
                delay = _extract_retry_delay(e) if getattr(e, "code", None) == 429 else BACKOFF_BASE * (2 ** attempt)
                logger.warning(f"Pre-stream {model_name} attempt {attempt + 1} failed: {getattr(e, 'code', '?')} {getattr(e, 'status', '?')}, retrying in {delay:.0f}s")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(delay)

    raise last_error
