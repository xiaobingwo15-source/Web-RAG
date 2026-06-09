import asyncio
import logging
import math
import re
from dataclasses import dataclass
from typing import Any

import httpx
from google import genai

from app.config import Settings

logger = logging.getLogger(__name__)

GEMINI_PROVIDER = "gemini"
LOCAL_SENTENCE_TRANSFORMERS_PROVIDER = "local_sentence_transformers"
JINA_PROVIDER = "jina"
GEMINI_EMBEDDING_MAX_BATCH_SIZE = 100
JINA_API_URL = "https://api.jina.ai/v1/embeddings"
JINA_MAX_BATCH_SIZE = 100

_embedding_client: object | None = None
_embedding_client_key: tuple[str, str, str | None, str | None] | None = None


@dataclass
class LocalSentenceTransformersClient:
    model_name: str
    device: str
    _model: Any | None = None

    def encode(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=False,
        )
        return [_normalize_vector(_coerce_vector(vector)) for vector in vectors]

    def _load_model(self) -> Any:
        if self._model is None:
            try:
                sentence_transformer_cls = _get_sentence_transformer_cls()
            except ImportError as exc:
                raise RuntimeError(
                    "EMBEDDING_PROVIDER=local_sentence_transformers requires the "
                    "sentence-transformers package. Install backend requirements "
                    "or switch EMBEDDING_PROVIDER back to gemini."
                ) from exc
            self._model = sentence_transformer_cls(self.model_name, device=self.device)
        return self._model


@dataclass
class JinaClient:
    api_key: str
    model: str
    dimension: int

    def embed(self, texts: list[str], task: str) -> list[list[float]]:
        task_type = "retrieval.query" if task == "query" else "retrieval.passage"
        response = httpx.post(
            JINA_API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            json={
                "model": self.model,
                "task": task_type,
                "normalized": True,
                "dimensions": self.dimension,
                "input": texts,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in data["data"]]


def _get_sentence_transformer_cls() -> Any:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer


def get_embedding_client() -> object:
    global _embedding_client, _embedding_client_key

    settings = Settings()
    info = get_embedding_info(settings)
    provider_key: str | None = None
    if info["provider"] == GEMINI_PROVIDER:
        provider_key = settings.get_google_api_key
    elif info["provider"] == JINA_PROVIDER:
        provider_key = settings.get_jina_api_key
    key = (
        info["provider"],
        info["model"],
        info.get("device"),
        provider_key,
    )
    if _embedding_client is not None and _embedding_client_key == key:
        return _embedding_client

    if info["provider"] == LOCAL_SENTENCE_TRANSFORMERS_PROVIDER:
        _embedding_client = LocalSentenceTransformersClient(
            model_name=info["model"],
            device=info.get("device") or "cpu",
        )
    elif info["provider"] == JINA_PROVIDER:
        _embedding_client = JinaClient(
            api_key=settings.get_jina_api_key,
            model=info["model"],
            dimension=info["dimension"],
        )
    else:
        _embedding_client = genai.Client(api_key=settings.get_google_api_key)

    _embedding_client_key = key
    return _embedding_client


def get_embedding_info(settings: Settings | None = None) -> dict[str, str | int | None]:
    settings = settings or Settings()
    provider = settings.get_embedding_provider
    if provider == LOCAL_SENTENCE_TRANSFORMERS_PROVIDER:
        return {
            "provider": provider,
            "model": settings.get_local_embedding_model,
            "dimension": settings.get_embedding_dimension,
            "device": settings.get_local_embedding_device,
        }
    if provider == JINA_PROVIDER:
        return {
            "provider": provider,
            "model": settings.get_jina_embedding_model,
            "dimension": settings.get_embedding_dimension,
            "device": None,
        }
    return {
        "provider": GEMINI_PROVIDER,
        "model": settings.get_embedding_model,
        "dimension": settings.get_embedding_dimension,
        "device": None,
    }


async def get_embedding(client: object, text: str, max_retries: int = 2) -> list[float]:
    """Embed a single query string."""
    if isinstance(client, LocalSentenceTransformersClient):
        prefixed = _prefix_local_text(client.model_name, text, task="query")
        vectors = await asyncio.to_thread(client.encode, [prefixed])
        return validate_embedding_vector_length(vectors[0], context="query embedding")

    if isinstance(client, JinaClient):
        for attempt in range(max_retries + 1):
            try:
                vectors = await asyncio.to_thread(client.embed, [text], "query")
                return validate_embedding_vector_length(vectors[0], context="query embedding")
            except Exception as exc:
                if attempt < max_retries:
                    delay = _extract_embedding_retry_delay(exc, default=1.0 * (2 ** attempt))
                    logger.warning(
                        "Jina embedding attempt %d failed: %s, retrying in %.0fs",
                        attempt + 1,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    raise

    return await _get_gemini_embedding(
        client=client,
        contents=text,
        task_type="RETRIEVAL_QUERY",
        max_retries=max_retries,
        context="query embedding",
    )


async def get_embeddings(client: object, texts: list[str]) -> list[list[float]]:
    """Embed a batch of document strings."""
    if not texts:
        return []

    if isinstance(client, LocalSentenceTransformersClient):
        prefixed = [
            _prefix_local_text(client.model_name, text, task="document")
            for text in texts
        ]
        vectors = await asyncio.to_thread(client.encode, prefixed)
        return [
            validate_embedding_vector_length(vector, context=f"document embedding {index}")
            for index, vector in enumerate(vectors)
        ]

    if isinstance(client, JinaClient):
        vectors: list[list[float]] = []
        for start in range(0, len(texts), JINA_MAX_BATCH_SIZE):
            batch = texts[start:start + JINA_MAX_BATCH_SIZE]
            for attempt in range(3):
                try:
                    batch_vectors = await asyncio.to_thread(client.embed, batch, "document")
                    vectors.extend(
                        validate_embedding_vector_length(vector, context=f"document embedding {start + i}")
                        for i, vector in enumerate(batch_vectors)
                    )
                    break
                except Exception as exc:
                    if attempt < 2:
                        delay = _extract_embedding_retry_delay(exc, default=1.0 * (2 ** attempt))
                        logger.warning(
                            "Jina batch embedding attempt %d failed: %s, retrying in %.0fs",
                            attempt + 1,
                            exc,
                            delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        raise
        return vectors

    vectors: list[list[float]] = []
    for start in range(0, len(texts), GEMINI_EMBEDDING_MAX_BATCH_SIZE):
        batch = texts[start:start + GEMINI_EMBEDDING_MAX_BATCH_SIZE]
        batch_vectors = await _get_gemini_embedding(
            client=client,
            contents=batch,
            task_type="RETRIEVAL_DOCUMENT",
            max_retries=2,
            context="document embeddings",
        )
        vectors.extend(batch_vectors)  # type: ignore[arg-type]
    return vectors


async def validate_embedding_configuration(client: object | None = None) -> dict[str, str | int | None]:
    info = get_embedding_info()
    probe_client = client or get_embedding_client()
    vector = await get_embedding(probe_client, "embedding dimension probe", max_retries=0)
    expected_dimension = info["dimension"]
    actual_dimension = len(vector)
    if actual_dimension != expected_dimension:
        raise RuntimeError(
            "Embedding dimension mismatch during startup validation: "
            f"provider={info['provider']} model={info['model']} returned "
            f"{actual_dimension} dimensions, but EMBEDDING_DIMENSION is "
            f"{expected_dimension}. Use a matching model or recreate the Qdrant collection."
        )
    return info


def validate_embedding_vector_length(vector: list[float], context: str = "embedding") -> list[float]:
    settings = Settings()
    info = get_embedding_info(settings)
    expected_dimension = settings.get_embedding_dimension
    actual_dimension = len(vector)
    if actual_dimension != expected_dimension:
        raise RuntimeError(
            f"Embedding dimension mismatch for {context}: provider={info['provider']} "
            f"model={info['model']} returned {actual_dimension} dimensions, but "
            f"EMBEDDING_DIMENSION is {expected_dimension}. Use a matching model or "
            "recreate the Qdrant collection before inserting vectors."
        )
    return vector


async def _get_gemini_embedding(
    client: object,
    contents: str | list[str],
    task_type: str,
    max_retries: int,
    context: str,
) -> list[float] | list[list[float]]:
    settings = Settings()
    model = settings.get_embedding_model
    dimension = settings.get_embedding_dimension

    for attempt in range(max_retries + 1):
        try:
            result = await client.aio.models.embed_content(
                model=model,
                contents=contents,
                config={
                    "output_dimensionality": dimension,
                    "task_type": task_type,
                },
            )
            vectors = [list(embedding.values) for embedding in result.embeddings]
            if isinstance(contents, str):
                return validate_embedding_vector_length(vectors[0], context=context)
            return [
                validate_embedding_vector_length(vector, context=f"{context} {index}")
                for index, vector in enumerate(vectors)
            ]
        except Exception as exc:
            if attempt < max_retries:
                delay = _extract_embedding_retry_delay(exc, default=1.0 * (2 ** attempt))
                logger.warning(
                    "Embedding attempt %d failed: %s, retrying in %.0fs",
                    attempt + 1,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                raise

    raise RuntimeError("Embedding generation failed unexpectedly")


def _extract_embedding_retry_delay(error: Exception, default: float) -> float:
    message = str(error)
    retry_info = re.search(r"retryDelay['\"]?:\s*['\"]?([0-9.]+)s", message)
    if retry_info:
        return float(retry_info.group(1))
    retry_hint = re.search(r"retry in ([0-9.]+)s", message, flags=re.IGNORECASE)
    if retry_hint:
        return float(retry_hint.group(1))
    return default


def _prefix_local_text(model_name: str, text: str, task: str) -> str:
    if not _uses_e5_prompt_format(model_name):
        return text

    stripped = text.lstrip()
    lower = stripped.lower()
    if lower.startswith("query: ") or lower.startswith("passage: "):
        return stripped

    prefix = "query: " if task == "query" else "passage: "
    return f"{prefix}{stripped}"


def _uses_e5_prompt_format(model_name: str) -> bool:
    return "e5" in model_name.lower()


def _coerce_vector(vector: Any) -> list[float]:
    if hasattr(vector, "detach"):
        vector = vector.detach()
    if hasattr(vector, "cpu"):
        vector = vector.cpu()
    if hasattr(vector, "tolist"):
        vector = vector.tolist()
    return [float(value) for value in vector]


def _normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]
