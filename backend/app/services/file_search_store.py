import asyncio
import hashlib
import logging
from app.services.text_extractor import extract_text, extract_text_with_ocr
from app.services.chunker import chunk_text, create_parent_child_chunks
from app.services.embeddings import get_embedding_client, get_embeddings
from app.config import Settings
from app.services.metadata_extractor import extract_metadata
from app.services.document_enrichment import emphasize_document_text
from app.services.gemini import get_llm_client
from app.services.database import (
    insert_chunks_for_fts, update_document_status, update_document_hash,
    update_document_chunk_count, update_document_metadata,
)
from app.services.qdrant_db import insert_chunks, update_chunks_metadata

logger = logging.getLogger(__name__)


def compute_content_hash(file_bytes: bytes) -> str:
    return hashlib.md5(file_bytes).hexdigest()


async def process_document(
    access_token: str,
    user_id: str,
    document_id: str,
    file_bytes: bytes,
    mime_type: str,
    use_ocr: bool = False,
    tenant_id: str | None = None,
) -> dict:
    try:
        content_hash = compute_content_hash(file_bytes)
        update_document_hash(access_token, document_id, content_hash)

        logger.info(f"Processing document {document_id}: extracting text (ocr={use_ocr})")
        text = await extract_text_with_ocr(file_bytes, mime_type, use_ocr)

        if not text.strip():
            raise ValueError("No text content extracted from file")

        logger.info(f"Document {document_id}: extracting metadata")
        gemini_client = get_llm_client()
        metadata = await extract_metadata(gemini_client, text[:2000])
        update_document_metadata(access_token, document_id, metadata)
        logger.info(f"Document {document_id}: metadata extracted — {metadata}")

        text = emphasize_document_text(text, metadata)

        logger.info(f"Document {document_id}: chunking text ({len(text)} chars)")
        settings_chunk = Settings()
        if settings_chunk.semantic_chunking:
            logger.info(f"Document {document_id}: using semantic chunking (threshold={settings_chunk.semantic_similarity_threshold})")
            from app.services.chunker import create_parent_child_chunks_semantic
            embedding_client = get_embedding_client()

            async def embed_fn(texts: list[str]) -> list[list[float]]:
                return await get_embeddings(embedding_client, texts)

            hierarchy = await create_parent_child_chunks_semantic(
                text, embed_fn=embed_fn, threshold=settings_chunk.semantic_similarity_threshold,
            )
        else:
            hierarchy = create_parent_child_chunks(text)
        parents = hierarchy["parents"]
        children = hierarchy["children"]
        logger.info(f"Document {document_id}: created {len(parents)} parent chunks, {len(children)} child chunks")

        # Embed only child chunks (fine-grained, searchable)
        logger.info(f"Document {document_id}: generating embeddings for {len(children)} child chunks")
        client = get_embedding_client()
        child_texts = [c["text"] for c in children]
        embeddings = await get_embeddings(client, child_texts)

        # Build child chunk data with parent_id and chunk_type
        child_chunk_data = []
        for i, (child, embedding) in enumerate(zip(children, embeddings)):
            child_chunk_data.append({
                "content": child["text"],
                "embedding": embedding,
                "chunk_index": i,
                "parent_id": child["parent_id"],
                "chunk_type": "child",
            })

        # Build parent chunk data with zero-vector embeddings
        settings = Settings()
        zero_vector = [0.0] * settings.get_embedding_dimension
        parent_chunk_data = []
        for i, parent in enumerate(parents):
            parent_chunk_data.append({
                "content": parent["text"],
                "embedding": zero_vector,
                "chunk_index": len(children) + i,
                "chunk_type": "parent",
            })

        logger.info(f"Document {document_id}: storing {len(child_chunk_data)} child + {len(parent_chunk_data)} parent chunks")

        # Insert child chunks into Supabase FTS first to get canonical IDs
        child_fts_rows = await asyncio.to_thread(
            insert_chunks_for_fts, access_token, user_id, document_id, child_chunk_data, tenant_id
        )
        child_fts_ids = [str(row["id"]) for row in child_fts_rows]

        # Insert parent chunks into Supabase FTS to get their row IDs
        parent_fts_rows = await asyncio.to_thread(
            insert_chunks_for_fts, access_token, user_id, document_id, parent_chunk_data, tenant_id
        )
        parent_id_map = {}  # chunker UUID -> Supabase row ID
        for parent, row in zip(parents, parent_fts_rows):
            parent_id_map[parent["id"]] = str(row["id"])

        # Remap child parent_id references from chunker UUIDs to Supabase row IDs
        for ccd in child_chunk_data:
            old_pid = ccd.get("parent_id")
            if old_pid and old_pid in parent_id_map:
                ccd["parent_id"] = parent_id_map[old_pid]

        # Insert children into Qdrant (real embeddings, searchable)
        await insert_chunks(user_id, document_id, child_chunk_data, point_ids=child_fts_ids, tenant_id=tenant_id)

        # Insert parents into Qdrant (zero vectors, retrievable by ID only)
        parent_supabase_ids = [str(row["id"]) for row in parent_fts_rows]
        await insert_chunks(user_id, document_id, parent_chunk_data, point_ids=parent_supabase_ids, tenant_id=tenant_id)

        await update_chunks_metadata(document_id, metadata)

        total_chunks = len(child_chunk_data) + len(parent_chunk_data)
        update_document_chunk_count(access_token, document_id, total_chunks)
        update_document_status(access_token, document_id, "processed")
        return {"id": document_id, "status": "processed", "chunk_count": total_chunks}

    except Exception as e:
        logger.error(f"Document {document_id} processing failed: {e}")
        update_document_status(access_token, document_id, "failed", str(e))
        return {"id": document_id, "status": "failed", "error_message": str(e)}
