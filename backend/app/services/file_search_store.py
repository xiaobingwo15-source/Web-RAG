import hashlib
import logging
from app.services.text_extractor import extract_text, extract_text_with_ocr
from app.services.chunker import chunk_text
from app.services.embeddings import get_embedding_client, get_embeddings
from app.services.metadata_extractor import extract_metadata
from app.services.gemini import get_gemini_client
from app.services.database import (
    insert_chunks, update_document_status, update_document_hash,
    update_document_chunk_count, update_document_metadata, update_chunks_metadata,
)

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
) -> dict:
    try:
        content_hash = compute_content_hash(file_bytes)
        update_document_hash(access_token, document_id, content_hash)

        logger.info(f"Processing document {document_id}: extracting text (ocr={use_ocr})")
        text = await extract_text_with_ocr(file_bytes, mime_type, use_ocr)

        if not text.strip():
            raise ValueError("No text content extracted from file")

        logger.info(f"Document {document_id}: extracting metadata")
        gemini_client = get_gemini_client()
        metadata = await extract_metadata(gemini_client, text[:2000])
        update_document_metadata(access_token, document_id, metadata)
        logger.info(f"Document {document_id}: metadata extracted — {metadata}")

        logger.info(f"Document {document_id}: chunking text ({len(text)} chars)")
        chunks = chunk_text(text)
        logger.info(f"Document {document_id}: created {len(chunks)} chunks")

        logger.info(f"Document {document_id}: generating embeddings")
        client = get_embedding_client()
        embeddings = await get_embeddings(client, chunks)

        chunk_data = [
            {"content": chunk, "embedding": embedding, "chunk_index": i}
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]

        logger.info(f"Document {document_id}: storing {len(chunk_data)} chunks")
        insert_chunks(access_token, user_id, document_id, chunk_data)
        update_chunks_metadata(access_token, document_id, metadata)

        update_document_chunk_count(access_token, document_id, len(chunk_data))
        update_document_status(access_token, document_id, "processed")
        return {"id": document_id, "status": "processed", "chunk_count": len(chunk_data)}

    except Exception as e:
        logger.error(f"Document {document_id} processing failed: {e}")
        update_document_status(access_token, document_id, "failed", str(e))
        return {"id": document_id, "status": "failed", "error_message": str(e)}
