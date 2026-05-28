import asyncio
import logging
from google import genai
from app.config import Settings

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSION = 768

_embedding_client: genai.Client | None = None


def get_embedding_client() -> genai.Client:
    global _embedding_client
    if _embedding_client is None:
        settings = Settings()
        _embedding_client = genai.Client(api_key=settings.get_google_api_key)
    return _embedding_client


async def get_embedding(client: genai.Client, text: str, max_retries: int = 2) -> list[float]:
    for attempt in range(max_retries + 1):
        try:
            result = await client.aio.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=text,
                config={"output_dimensionality": EMBEDDING_DIMENSION},
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
    if not texts:
        return []
    result = await client.aio.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texts,
        config={"output_dimensionality": EMBEDDING_DIMENSION},
    )
    return [e.values for e in result.embeddings]
