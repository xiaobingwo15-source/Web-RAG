"""
Async document ingestion worker.

Runs via FastAPI BackgroundTasks after the upload response is sent.
Handles: extract -> chunk -> embed -> store, with status tracking and retry logic.
"""

import asyncio
import logging
from app.services.file_search_store import process_document
from app.services.database import update_document_status

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAY_SECONDS = 3


def _is_transient(error: Exception) -> bool:
    """Determine if an error is transient and worth retrying."""
    transient_types = (
        ConnectionError,
        TimeoutError,
        OSError,
    )
    if isinstance(error, transient_types):
        return True

    msg = str(error).lower()
    transient_keywords = [
        "timeout",
        "rate limit",
        "429",
        "503",
        "502",
        "connection reset",
        "connection refused",
        "temporarily unavailable",
        "deadline exceeded",
    ]
    return any(kw in msg for kw in transient_keywords)


async def process_document_async(
    access_token: str,
    user_id: str,
    document_id: str,
    file_bytes: bytes,
    mime_type: str,
    use_ocr: bool = False,
    pdf_parser_mode: str = "auto",
    filename: str | None = None,
    tenant_id: str | None = None,
) -> None:
    """
    Background task: process a document with retry logic.

    Updates document status through lifecycle:
      pending -> processing -> processed
      pending -> processing -> failed (after retries exhausted)
    """
    update_document_status(access_token, document_id, "processing")
    logger.info(f"Document {document_id}: background processing started")

    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await process_document(
                access_token, user_id, document_id,
                file_bytes, mime_type,
                use_ocr=use_ocr,
                pdf_parser_mode=pdf_parser_mode,
                filename=filename,
                tenant_id=tenant_id,
            )

            if result["status"] == "processed":
                logger.info(
                    f"Document {document_id}: processed successfully "
                    f"(attempt {attempt}, {result.get('chunk_count', '?')} chunks)"
                )
                return

            # process_document caught its own exception and set status to "failed"
            error_msg = result.get("error_message", "Unknown error")
            raise RuntimeError(error_msg)

        except Exception as e:
            last_error = e
            logger.warning(
                f"Document {document_id}: attempt {attempt}/{MAX_RETRIES} failed: {e}"
            )

            if attempt < MAX_RETRIES and _is_transient(e):
                logger.info(
                    f"Document {document_id}: transient error, "
                    f"retrying in {RETRY_DELAY_SECONDS}s..."
                )
                update_document_status(
                    access_token, document_id, "pending",
                    f"Attempt {attempt} failed, retrying... ({e})",
                )
                await asyncio.sleep(RETRY_DELAY_SECONDS)
            else:
                break

    # All retries exhausted or non-transient error
    error_msg = str(last_error) if last_error else "Unknown processing error"
    logger.error(
        f"Document {document_id}: permanently failed after "
        f"{MAX_RETRIES} attempts: {error_msg}"
    )
    update_document_status(access_token, document_id, "failed", error_msg)
