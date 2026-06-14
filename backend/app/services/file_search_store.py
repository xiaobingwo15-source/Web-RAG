import asyncio
import hashlib
import logging
import time
from app.services.text_extractor import extract_text_with_metadata
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
from app.services.contextual_retrieval import add_contextual_prefixes
from app.services.semantic_cache import clear_semantic_cache, invalidate_cache_for_document

logger = logging.getLogger(__name__)


def _compute_quality_score(
    extraction_meta: dict,
    doc_meta: dict,
    text_length: int,
    chunk_count: int,
) -> float:
    """Compute a 0.0-1.0 quality score for an ingested document.

    Phase 6.1: Document quality scoring during ingestion.

    Factors:
    - Text extraction confidence (length vs expected)
    - Table detection (presence of structured data)
    - OCR usage flag (scanned docs are lower quality)
    - Page count (more pages = more content)
    - Chunk count relative to content
    """
    score = 0.5  # base score

    # Text length bonus (more extracted text = better extraction)
    if text_length > 10000:
        score += 0.15
    elif text_length > 3000:
        score += 0.10
    elif text_length > 1000:
        score += 0.05
    elif text_length < 100:
        score -= 0.20  # very little text extracted = bad

    # Table detection bonus
    tables_detected = extraction_meta.get("tables_detected", 0)
    if tables_detected and tables_detected > 0:
        score += 0.10

    # OCR penalty (scanned docs have lower extraction quality)
    ocr_used = extraction_meta.get("ocr_used", False)
    if ocr_used:
        score -= 0.10

    # Page count bonus (more content)
    page_count = extraction_meta.get("pdf_page_count", 0)
    if page_count and page_count > 5:
        score += 0.05

    # Chunk density (reasonable number of chunks relative to text)
    if text_length > 0 and chunk_count > 0:
        avg_chunk_size = text_length / chunk_count
        if 200 <= avg_chunk_size <= 2000:
            score += 0.10  # good chunk density
        elif avg_chunk_size < 100:
            score -= 0.05  # too fragmented

    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, round(score, 2)))


def _log_document_stage(
    document_id: str,
    stage: str,
    event: str,
    **fields: object,
) -> None:
    details = " ".join(
        f"{key}={value}"
        for key, value in fields.items()
        if value is not None
    )
    logger.info(
        "Document %s: stage=%s event=%s%s",
        document_id,
        stage,
        event,
        f" {details}" if details else "",
    )


def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def compute_content_hash(file_bytes: bytes) -> str:
    return hashlib.md5(file_bytes).hexdigest()


async def process_document(
    access_token: str,
    user_id: str,
    document_id: str,
    file_bytes: bytes,
    mime_type: str,
    use_ocr: bool = False,
    pdf_parser_mode: str = "auto",
    filename: str | None = None,
    tenant_id: str | None = None,
) -> dict:
    process_started_at = time.perf_counter()
    try:
        content_hash = compute_content_hash(file_bytes)
        update_document_hash(access_token, document_id, content_hash)

        _log_document_stage(
            document_id,
            "inspect",
            "started",
            mime_type=mime_type,
            bytes=len(file_bytes),
            ocr=use_ocr,
            pdf_parser_mode=pdf_parser_mode,
        )
        parse_started_at = time.perf_counter()
        _log_document_stage(document_id, "parse", "started")
        extraction = await extract_text_with_metadata(
            file_bytes,
            mime_type,
            use_ocr=use_ocr,
            pdf_parser_mode=pdf_parser_mode,
            filename=filename,
        )
        text = extraction.text
        _log_document_stage(
            document_id,
            "inspect",
            "completed",
            pages=extraction.metadata.get("pdf_page_count"),
            text_pages=extraction.metadata.get("pdf_text_page_count"),
            extracted_chars=extraction.metadata.get("extracted_char_count"),
        )
        _log_document_stage(
            document_id,
            "parse",
            "completed",
            elapsed_ms=_elapsed_ms(parse_started_at),
            chars=len(text),
            parser=extraction.metadata.get("pdf_parser"),
            pages=extraction.metadata.get("pdf_page_count"),
        )

        if not text.strip():
            raise ValueError("No text content extracted from file")

        metadata_started_at = time.perf_counter()
        _log_document_stage(document_id, "metadata", "started")
        gemini_client = get_llm_client()
        metadata = await extract_metadata(gemini_client, text[:2000])
        metadata = {**metadata, **extraction.metadata}
        update_document_metadata(access_token, document_id, metadata)
        _log_document_stage(
            document_id,
            "metadata",
            "completed",
            elapsed_ms=_elapsed_ms(metadata_started_at),
            title=bool(metadata.get("title")),
            tags=len(metadata.get("tags", [])) if isinstance(metadata.get("tags"), list) else 0,
            language=metadata.get("language"),
        )

        text = emphasize_document_text(text, metadata)

        settings_chunk = Settings()
        chunk_started_at = time.perf_counter()
        _log_document_stage(
            document_id,
            "chunk",
            "started",
            chars=len(text),
            semantic=settings_chunk.semantic_chunking,
        )
        doc_title = metadata.get("title", "")
        if settings_chunk.semantic_chunking:
            logger.info(f"Document {document_id}: using semantic chunking (threshold={settings_chunk.semantic_similarity_threshold})")
            from app.services.chunker import create_parent_child_chunks_semantic
            embedding_client = get_embedding_client()

            async def embed_fn(texts: list[str]) -> list[list[float]]:
                return await get_embeddings(embedding_client, texts)

            hierarchy = await create_parent_child_chunks_semantic(
                text, embed_fn=embed_fn, threshold=settings_chunk.semantic_similarity_threshold,
                doc_title=doc_title,
            )
        else:
            hierarchy = create_parent_child_chunks(text, doc_title=doc_title)
        parents = hierarchy["parents"]
        children = hierarchy["children"]
        _log_document_stage(
            document_id,
            "chunk",
            "completed",
            elapsed_ms=_elapsed_ms(chunk_started_at),
            parent_chunks=len(parents),
            child_chunks=len(children),
        )

        # Optional: add LLM-generated context prefixes to child chunks
        settings = Settings()
        if settings.get_contextual_retrieval:
            logger.info(f"Document {document_id}: adding contextual prefixes (enabled)")
            doc_summary = metadata.get("summary", "")
            try:
                children = await add_contextual_prefixes(
                    children, doc_title=doc_title, doc_summary=doc_summary,
                )
            except Exception as ctx_err:
                logger.warning(f"Document {document_id}: contextual retrieval failed, continuing without: {ctx_err}")

        # Embed only child chunks (fine-grained, searchable)
        embed_started_at = time.perf_counter()
        _log_document_stage(document_id, "embed", "started", child_chunks=len(children))
        client = get_embedding_client()
        child_texts = [c["text"] for c in children]
        embeddings = await get_embeddings(client, child_texts)
        _log_document_stage(
            document_id,
            "embed",
            "completed",
            elapsed_ms=_elapsed_ms(embed_started_at),
            embeddings=len(embeddings),
        )

        # Build child chunk data with parent_id, chunk_type, and structural metadata
        child_chunk_data = []
        for i, (child, embedding) in enumerate(zip(children, embeddings)):
            child_chunk_data.append({
                "content": child["text"],
                "embedding": embedding,
                "chunk_index": i,
                "parent_id": child["parent_id"],
                "chunk_type": "child",
                "metadata": metadata,
                # Phase 1: per-chunk structural metadata
                "heading": child.get("heading", ""),
                "heading_level": child.get("heading_level", 0),
                "structural_type": child.get("structural_type", "text"),
                "page_start": child.get("page_start"),
                "page_end": child.get("page_end"),
                "table_id": child.get("table_id"),
                "breadcrumb_path": child.get("breadcrumb_path", []),
            })

        # Build parent chunk data with zero-vector embeddings
        zero_vector = [0.0] * settings.get_embedding_dimension
        parent_chunk_data = []
        for i, parent in enumerate(parents):
            parent_chunk_data.append({
                "content": parent["text"],
                "embedding": zero_vector,
                "chunk_index": len(children) + i,
                "chunk_type": "parent",
                "metadata": metadata,
                # Phase 1: per-chunk structural metadata
                "heading": parent.get("heading", ""),
                "heading_level": parent.get("heading_level", 0),
                "structural_type": parent.get("structural_type", "text"),
                "page_start": parent.get("page_start"),
                "page_end": parent.get("page_end"),
                "table_id": parent.get("table_id"),
                "breadcrumb_path": parent.get("breadcrumb_path", []),
            })

        store_started_at = time.perf_counter()
        _log_document_stage(
            document_id,
            "store",
            "started",
            child_chunks=len(child_chunk_data),
            parent_chunks=len(parent_chunk_data),
        )

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

        # Phase 6.1: Compute document quality score
        quality_score = _compute_quality_score(
            extraction.metadata, metadata, len(text), total_chunks,
        )
        metadata["quality_score"] = quality_score
        update_document_metadata(access_token, document_id, {"quality_score": quality_score})
        _log_document_stage(
            document_id,
            "quality",
            "scored",
            quality_score=quality_score,
        )

        update_document_status(access_token, document_id, "processed")
        # Phase 5.1: Targeted invalidation instead of full cache clear
        invalidated = invalidate_cache_for_document(document_id)
        if invalidated:
            _log_document_stage(document_id, "cache", "invalidated", entries=invalidated)
        _log_document_stage(
            document_id,
            "store",
            "completed",
            elapsed_ms=_elapsed_ms(store_started_at),
            total_chunks=total_chunks,
        )
        _log_document_stage(
            document_id,
            "ingest",
            "completed",
            elapsed_ms=_elapsed_ms(process_started_at),
        )
        return {"id": document_id, "status": "processed", "chunk_count": total_chunks}

    except Exception as e:
        _log_document_stage(
            document_id,
            "ingest",
            "failed",
            elapsed_ms=_elapsed_ms(process_started_at),
            error_type=e.__class__.__name__,
        )
        logger.error(f"Document {document_id} processing failed: {e}")
        update_document_status(access_token, document_id, "failed", str(e))
        return {"id": document_id, "status": "failed", "error_message": str(e)}
