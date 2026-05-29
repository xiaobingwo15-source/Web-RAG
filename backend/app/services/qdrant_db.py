import asyncio
import logging
import uuid
import time
from qdrant_client import AsyncQdrantClient, models
from app.config import Settings
from app.services.embeddings import EMBEDDING_DIMENSION

logger = logging.getLogger(__name__)

COLLECTION_NAME = "document_chunks"

_client: AsyncQdrantClient | None = None


async def get_qdrant_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        settings = Settings()
        _client = AsyncQdrantClient(
            url=settings.get_qdrant_url,
            api_key=settings.get_qdrant_api_key or None,
            timeout=10,
        )
    return _client


async def _ensure_collection_inner():
    client = await get_qdrant_client()
    collections = await client.get_collections()
    names = [c.name for c in collections.collections]
    if COLLECTION_NAME not in names:
        await client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=EMBEDDING_DIMENSION,
                distance=models.Distance.COSINE,
            ),
        )
        await client.create_payload_index(
            COLLECTION_NAME, field_name="user_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        await client.create_payload_index(
            COLLECTION_NAME, field_name="document_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        await client.create_payload_index(
            COLLECTION_NAME, field_name="metadata.tags",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        await client.create_payload_index(
            COLLECTION_NAME, field_name="metadata.language",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        logger.info("Created Qdrant collection '%s' with payload indexes", COLLECTION_NAME)
    else:
        logger.info("Qdrant collection '%s' already exists", COLLECTION_NAME)


async def ensure_collection():
    try:
        await asyncio.wait_for(_ensure_collection_inner(), timeout=15)
    except asyncio.TimeoutError:
        logger.warning("Qdrant connection timed out — server starting in degraded mode")
    except Exception as e:
        logger.warning("Qdrant unavailable: %s — server starting in degraded mode", e)


async def insert_chunks(
    user_id: str,
    document_id: str,
    chunks: list[dict],
) -> list[str]:
    client = await get_qdrant_client()
    point_ids = [str(uuid.uuid4()) for _ in chunks]
    points = [
        models.PointStruct(
            id=point_ids[i],
            vector=chunk["embedding"],
            payload={
                "user_id": user_id,
                "document_id": document_id,
                "content": chunk["content"],
                "chunk_index": chunk["chunk_index"],
                "created_at": time.time(),
            },
        )
        for i, chunk in enumerate(chunks)
    ]
    await client.upsert(collection_name=COLLECTION_NAME, points=points)
    logger.info("Inserted %d chunks for document %s", len(points), document_id)
    return point_ids


async def update_chunks_metadata(document_id: str, metadata: dict) -> None:
    client = await get_qdrant_client()
    # Scroll to find all points for this document
    results, _ = await client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=models.Filter(
            must=[models.FieldCondition(
                key="document_id",
                match=models.MatchValue(value=document_id),
            )]
        ),
        limit=1000,
        with_payload=False,
        with_vectors=False,
    )
    if not results:
        return
    point_ids = [point.id for point in results]
    await client.set_payload(
        collection_name=COLLECTION_NAME,
        payload={"metadata": metadata},
        points=point_ids,
    )
    logger.info("Updated metadata for %d chunks of document %s", len(point_ids), document_id)


async def search_similar_chunks(
    user_id: str,
    query_embedding: list[float],
    match_count: int = 5,
    similarity_threshold: float = 0.1,
) -> list[dict]:
    client = await get_qdrant_client()
    results = await client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding,
        query_filter=models.Filter(
            must=[models.FieldCondition(
                key="user_id",
                match=models.MatchValue(value=user_id),
            )]
        ),
        limit=match_count,
        score_threshold=similarity_threshold,
        with_payload=True,
    )
    hits = [
        {
            "id": str(r.id),
            "document_id": r.payload.get("document_id"),
            "content": r.payload.get("content"),
            "similarity": r.score,
        }
        for r in results.points
    ]
    if hits:
        scores = [f"{h['similarity']:.4f}" for h in hits]
        print(f"[QDRANT] Vector search: {len(hits)} results, scores=[{', '.join(scores)}], threshold={similarity_threshold}")
        logger.info(f"Qdrant vector search: {len(hits)} results, scores=[{', '.join(scores)}], threshold={similarity_threshold}")
    else:
        print(f"[QDRANT] Vector search: 0 results (threshold={similarity_threshold}, user_id={user_id})")
        logger.warning(f"Qdrant vector search: 0 results (threshold={similarity_threshold}, user_id={user_id})")
    return hits


async def search_similar_chunks_filtered(
    user_id: str,
    query_embedding: list[float],
    match_count: int = 5,
    similarity_threshold: float = 0.1,
    filter_tags: list[str] | None = None,
    filter_language: str | None = None,
) -> list[dict]:
    client = await get_qdrant_client()
    must_conditions = [
        models.FieldCondition(
            key="user_id",
            match=models.MatchValue(value=user_id),
        )
    ]
    if filter_tags:
        must_conditions.append(
            models.FieldCondition(
                key="metadata.tags",
                match=models.MatchAny(any=filter_tags),
            )
        )
    if filter_language:
        must_conditions.append(
            models.FieldCondition(
                key="metadata.language",
                match=models.MatchValue(value=filter_language),
            )
        )
    results = await client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding,
        query_filter=models.Filter(must=must_conditions),
        limit=match_count,
        score_threshold=similarity_threshold,
        with_payload=True,
    )
    return [
        {
            "id": str(r.id),
            "document_id": r.payload.get("document_id"),
            "content": r.payload.get("content"),
            "similarity": r.score,
            "metadata": r.payload.get("metadata", {}),
        }
        for r in results.points
    ]


async def delete_document_chunks(document_id: str) -> None:
    client = await get_qdrant_client()
    await client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=document_id),
                )]
            )
        ),
    )
    logger.info("Deleted chunks for document %s from Qdrant", document_id)


async def count_user_chunks(user_id: str) -> int:
    client = await get_qdrant_client()
    count_result = await client.count(
        collection_name=COLLECTION_NAME,
        count_filter=models.Filter(
            must=[models.FieldCondition(
                key="user_id",
                match=models.MatchValue(value=user_id),
            )]
        ),
    )
    return count_result.count


async def get_sample_chunks(user_id: str, limit: int = 3) -> list[dict]:
    client = await get_qdrant_client()
    results, _ = await client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=models.Filter(
            must=[models.FieldCondition(
                key="user_id",
                match=models.MatchValue(value=user_id),
            )]
        ),
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
    return [
        {
            "id": str(point.id),
            "document_id": point.payload.get("document_id"),
            "content": point.payload.get("content", "")[:200],
            "chunk_index": point.payload.get("chunk_index"),
        }
        for point in results
    ]
