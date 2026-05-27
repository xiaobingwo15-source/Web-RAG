import logging
from google import genai
from app.config import Settings

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSION = 768


def get_embedding_client() -> genai.Client:
    settings = Settings()
    return genai.Client(api_key=settings.google_api_key)


async def get_embedding(client: genai.Client, text: str) -> list[float]:
    result = await client.aio.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config={"output_dimensionality": EMBEDDING_DIMENSION},
    )
    return result.embeddings[0].values


async def get_embeddings(client: genai.Client, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    result = await client.aio.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texts,
        config={"output_dimensionality": EMBEDDING_DIMENSION},
    )
    return [e.values for e in result.embeddings]
