import asyncio
import logging
from google import genai
from app.config import Settings

logger = logging.getLogger(__name__)

_embedding_client: genai.Client | None = None


def get_embedding_client() -> genai.Client:
    global _embedding_client
    if _embedding_client is None:
        settings = Settings()
        _embedding_client = genai.Client(api_key=settings.get_google_api_key)
    return _embedding_client


async def get_embedding(client: genai.Client, text: str, max_retries: int = 2) -> list[float]:
    """Embed a single query string. Uses RETRIEVAL_QUERY task type."""
    settings = Settings()
    model = settings.get_embedding_model
    dimension = settings.get_embedding_dimension

    for attempt in range(max_retries + 1):
        try:
            result = await client.aio.models.embed_content(
                model=model,
                contents=text,
                config={
                    "output_dimensionality": dimension,
                    "task_type": "RETRIEVAL_QUERY",
                },
            )
            return result.embeddings[0].values
        except Exception as e:
            if attempt < max_retries:
                delay = 1.0 * (2 ** attempt)
                logger.warning(f"Embedding attempt {attempt + 1} failed: {e}, retrying in {delay:.0f}s")
                await asyncio.sleep(delay)
            else:
                raise


async def get_embeddings(client: genai.Client, texts: list[str]) -> list[list[float]]:
    """Embed a batch of document strings. Uses RETRIEVAL_DOCUMENT task type."""
    if not texts:
        return []

    settings = Settings()
    model = settings.get_embedding_model
    dimension = settings.get_embedding_dimension

    result = await client.aio.models.embed_content(
        model=model,
        contents=texts,
        config={
            "output_dimensionality": dimension,
            "task_type": "RETRIEVAL_DOCUMENT",
        },
    )
    return [e.values for e in result.embeddings]
