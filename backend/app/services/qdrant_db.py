import asyncio
import logging
import uuid
import time
from qdrant_client import AsyncQdrantClient, models
from app.config import Settings
from app.services.embeddings import (
    validate_embedding_configuration,
    validate_embedding_vector_length,
)

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
    settings = Settings()
    embedding_info = await validate_embedding_configuration()
    client = await get_qdrant_client()
    collections = await client.get_collections()
    names = [c.name for c in collections.collections]
    if COLLECTION_NAME not in names:
        await client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=settings.get_embedding_dimension,
                distance=models.Distance.COSINE,
            ),
        )
        await client.create_payload_index(
            COLLECTION_NAME, field_name="user_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        await client.create_payload_index(
            COLLECTION_NAME, field_name="tenant_id",
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
        await client.create_payload_index(
            COLLECTION_NAME, field_name="chunk_type",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        logger.info("Created Qdrant collection '%s' with payload indexes", COLLECTION_NAME)
    else:
        await _validate_collection_dimension(client, settings.get_embedding_dimension)
        try:
            await client.create_payload_index(
                COLLECTION_NAME, field_name="tenant_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass
        logger.info(
            "Qdrant collection '%s' already exists; embedding provider=%s model=%s dimension=%s",
            COLLECTION_NAME,
            embedding_info["provider"],
            embedding_info["model"],
            embedding_info["dimension"],
        )


async def _validate_collection_dimension(client: AsyncQdrantClient, expected_dimension: int) -> None:
    collection = await client.get_collection(COLLECTION_NAME)
    vectors_config = collection.config.params.vectors
    actual_dimension = getattr(vectors_config, "size", None)
    if actual_dimension is None and isinstance(vectors_config, dict):
        first_vector = next(iter(vectors_config.values()), None)
        actual_dimension = getattr(first_vector, "size", None)
    if actual_dimension is not None and actual_dimension != expected_dimension:
        raise RuntimeError(
            f"Qdrant collection '{COLLECTION_NAME}' has vector dimension {actual_dimension}, "
            f"but EMBEDDING_DIMENSION is {expected_dimension}. Use a matching embedding "
            "model or recreate/use a separate collection before ingesting documents."
        )


async def ensure_collection():
    try:
        await asyncio.wait_for(_ensure_collection_inner(), timeout=15)
    except asyncio.TimeoutError:
        logger.warning("RAG startup check timed out - server starting in degraded mode")
    except Exception as e:
        logger.warning("RAG startup check failed: %s - server starting in degraded mode", e)


async def insert_chunks(
    user_id: str,
    document_id: str,
    chunks: list[dict],
    point_ids: list[str] | None = None,
    tenant_id: str | None = None,
) -> list[str]:
    client = await get_qdrant_client()
    if point_ids is None:
        point_ids = [str(uuid.uuid4()) for _ in chunks]
    points = []
    for i, chunk in enumerate(chunks):
        embedding = validate_embedding_vector_length(
            chunk["embedding"],
            context=f"chunk {i} for document {document_id}",
        )
        payload: dict = {
            "user_id": user_id,
            **({"tenant_id": tenant_id} if tenant_id else {}),
            "document_id": document_id,
            "content": chunk["content"],
            "chunk_index": chunk["chunk_index"],
            "created_at": time.time(),
        }
        if chunk.get("parent_id"):
            payload["parent_id"] = chunk["parent_id"]
        if chunk.get("chunk_type"):
            payload["chunk_type"] = chunk["chunk_type"]
        if chunk.get("metadata"):
            payload["metadata"] = chunk["metadata"]
        points.append(
            models.PointStruct(id=point_ids[i], vector=embedding, payload=payload)
        )
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
    tenant_id: str | None = None,
) -> list[dict]:
    client = await get_qdrant_client()
    filter_key = "tenant_id" if tenant_id else "user_id"
    filter_value = tenant_id or user_id
    results = await client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding,
        query_filter=models.Filter(
            must=[models.FieldCondition(
                key=filter_key,
                match=models.MatchValue(value=filter_value),
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
            "metadata": r.payload.get("metadata", {}),
            **({"parent_id": r.payload["parent_id"]} if r.payload.get("parent_id") else {}),
        }
        for r in results.points
    ]
    if hits:
        scores = [f"{h['similarity']:.4f}" for h in hits]
        print(f"[QDRANT] Vector search: {len(hits)} results, scores=[{', '.join(scores)}], threshold={similarity_threshold}")
        logger.info(f"Qdrant vector search: {len(hits)} results, scores=[{', '.join(scores)}], threshold={similarity_threshold}")
    else:
        print(f"[QDRANT] Vector search: 0 results (threshold={similarity_threshold}, {filter_key}={filter_value})")
        logger.warning(f"Qdrant vector search: 0 results (threshold={similarity_threshold}, {filter_key}={filter_value})")
    return hits


async def get_parent_chunks_by_ids(parent_ids: list[str]) -> dict[str, dict]:
    """Batch-fetch parent chunks by their Qdrant point IDs.

    Returns:
        Dict mapping parent_id -> {"content": str, "document_id": str, "metadata": dict}
    """
    if not parent_ids:
        return {}
    client = await get_qdrant_client()
    results = await client.retrieve(
        collection_name=COLLECTION_NAME,
        ids=parent_ids,
        with_payload=True,
        with_vectors=False,
    )
    return {
        str(point.id): {
            "content": point.payload.get("content", ""),
            "document_id": point.payload.get("document_id", ""),
            "metadata": point.payload.get("metadata", {}),
        }
        for point in results
    }


async def search_similar_chunks_filtered(
    user_id: str,
    query_embedding: list[float],
    match_count: int = 5,
    similarity_threshold: float = 0.1,
    filter_tags: list[str] | None = None,
    filter_language: str | None = None,
    tenant_id: str | None = None,
) -> list[dict]:
    client = await get_qdrant_client()
    filter_key = "tenant_id" if tenant_id else "user_id"
    filter_value = tenant_id or user_id
    must_conditions = [
        models.FieldCondition(
            key=filter_key,
            match=models.MatchValue(value=filter_value),
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


async def count_user_chunks(
    user_id: str,
    tenant_id: str | None = None,
    document_id: str | None = None,
) -> int:
    client = await get_qdrant_client()
    filter_key = "tenant_id" if tenant_id else "user_id"
    filter_value = tenant_id or user_id
    must_conditions = [
        models.FieldCondition(
            key=filter_key,
            match=models.MatchValue(value=filter_value),
        )
    ]
    if document_id:
        must_conditions.append(
            models.FieldCondition(
                key="document_id",
                match=models.MatchValue(value=document_id),
            )
        )
    count_result = await client.count(
        collection_name=COLLECTION_NAME,
        count_filter=models.Filter(must=must_conditions),
    )
    return count_result.count


async def get_sample_chunks(
    user_id: str,
    limit: int = 3,
    tenant_id: str | None = None,
    document_id: str | None = None,
) -> list[dict]:
    client = await get_qdrant_client()
    filter_key = "tenant_id" if tenant_id else "user_id"
    filter_value = tenant_id or user_id
    must_conditions = [
        models.FieldCondition(
            key=filter_key,
            match=models.MatchValue(value=filter_value),
        )
    ]
    if document_id:
        must_conditions.append(
            models.FieldCondition(
                key="document_id",
                match=models.MatchValue(value=document_id),
            )
        )
    results, _ = await client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=models.Filter(must=must_conditions),
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
            "chunk_type": point.payload.get("chunk_type"),
            "parent_id": point.payload.get("parent_id"),
            "metadata": point.payload.get("metadata", {}),
        }
        for point in results
    ]
