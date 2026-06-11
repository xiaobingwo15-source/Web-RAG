"""
Chunked upload session endpoints.

Enables resilient file upload that survives page refreshes by splitting
files into small chunks, each uploaded as a separate request.
"""

import hashlib
import logging
import math
import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.middleware.auth import get_current_user
from app.models.documents import DocumentUploadResponse
from app.routers.documents import ALLOWED_MIME_TYPES, MAX_UPLOAD_BYTES, _verify_admin
from app.services.database import (
    create_document,
    create_upload_session,
    get_document_by_hash,
    get_upload_session,
    get_user_store,
    mark_document_retrying,
    update_upload_session,
    create_store,
)
from app.services.file_search_store import compute_content_hash
from app.services.ingestion_worker import process_document_async
from app.services.pdf_parser import normalize_pdf_parser_mode
from app.services.rate_limit import check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter()

CHUNK_DIR = Path(__file__).resolve().parent.parent.parent / "uploaded_chunks"

DEFAULT_CHUNK_SIZE = 2 * 1024 * 1024  # 2 MB


# --- Request / response models ---


class InitUploadRequest(BaseModel):
    filename: str
    mime_type: str
    total_size: int
    chunk_size: int = DEFAULT_CHUNK_SIZE
    use_ocr: bool = False
    pdf_parser_mode: str = "auto"


class InitUploadResponse(BaseModel):
    session_id: str
    total_chunks: int
    chunk_size: int


class ChunkUploadResponse(BaseModel):
    chunk_index: int
    uploaded_chunks: int
    total_chunks: int


class UploadSessionStatusResponse(BaseModel):
    session_id: str
    status: str
    uploaded_chunks: int
    total_chunks: int
    filename: str
    error_message: str | None = None


# --- Helpers ---


def _resolve_mime_type(filename: str, declared: str) -> str:
    """Validate and normalise the declared MIME type."""
    import mimetypes

    lower = filename.lower()
    if lower.endswith(".csv"):
        return "text/csv"
    if lower.endswith(".xlsx"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if lower.endswith(".xls"):
        return "application/vnd.ms-excel"
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith((".md", ".markdown")):
        return "text/markdown"
    if lower.endswith((".txt", ".text")):
        return "text/plain"

    if declared in ALLOWED_MIME_TYPES:
        return declared
    guessed, _ = mimetypes.guess_type(filename)
    if guessed in ALLOWED_MIME_TYPES:
        return guessed
    return "text/plain"


def _chunk_dir(session_id: str) -> Path:
    return CHUNK_DIR / session_id


def _verify_session_owner(session: dict, user) -> None:
    if str(session["user_id"]) != str(user.id):
        raise HTTPException(status_code=404, detail="Session not found")


# --- Endpoints ---


@router.post("/upload/init", response_model=InitUploadResponse)
async def init_upload(body: InitUploadRequest, user=Depends(get_current_user)):
    """Initialise a chunked upload session."""
    _verify_admin(user)
    check_rate_limit(f"upload:{user.id}", limit=10, window_seconds=60)

    mime_type = _resolve_mime_type(body.filename, body.mime_type)
    if body.total_size <= 0:
        raise HTTPException(status_code=400, detail="total_size must be positive")
    if body.total_size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large. Maximum upload size is 25 MB.")
    if body.chunk_size < 64 * 1024 or body.chunk_size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="chunk_size must be between 64 KB and 10 MB")

    total_chunks = math.ceil(body.total_size / body.chunk_size)
    parser_mode = normalize_pdf_parser_mode(body.pdf_parser_mode)

    session = create_upload_session(
        access_token=user.access_token,
        user_id=user.id,
        tenant_id=user.tenant_id,
        filename=body.filename,
        mime_type=mime_type,
        total_size=body.total_size,
        chunk_size=body.chunk_size,
        total_chunks=total_chunks,
        use_ocr=body.use_ocr,
        pdf_parser_mode=parser_mode,
    )

    # Create chunk directory on disk
    _chunk_dir(session["id"]).mkdir(parents=True, exist_ok=True)

    return InitUploadResponse(
        session_id=session["id"],
        total_chunks=total_chunks,
        chunk_size=body.chunk_size,
    )


@router.post("/upload/{session_id}/chunk/{chunk_index}", response_model=ChunkUploadResponse)
async def upload_chunk(
    session_id: str,
    chunk_index: int,
    checksum: str = Form(...),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """Receive a single chunk of a file upload."""
    session = get_upload_session(user.access_token, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    _verify_session_owner(session, user)

    if session["status"] != "uploading":
        raise HTTPException(status_code=409, detail=f"Session is '{session['status']}', not 'uploading'")
    if chunk_index < 0 or chunk_index >= session["total_chunks"]:
        raise HTTPException(status_code=400, detail=f"chunk_index must be 0..{session['total_chunks'] - 1}")

    chunk_bytes = await file.read()
    max_chunk = session["chunk_size"] + 1024  # small tolerance
    if len(chunk_bytes) > max_chunk:
        raise HTTPException(status_code=413, detail=f"Chunk too large (max {max_chunk} bytes)")

    # Verify integrity
    actual_hash = hashlib.sha256(chunk_bytes).hexdigest()
    if actual_hash != checksum.lower().strip():
        raise HTTPException(status_code=422, detail="Chunk checksum mismatch")

    # Write chunk to disk
    chunk_path = _chunk_dir(session_id) / f"{chunk_index:06d}"
    chunk_path.write_bytes(chunk_bytes)

    # Update counter
    # Count actual files on disk for robustness
    actual_count = len(list(_chunk_dir(session_id).iterdir()))
    update_upload_session(user.access_token, session_id, uploaded_chunks=actual_count)

    return ChunkUploadResponse(
        chunk_index=chunk_index,
        uploaded_chunks=actual_count,
        total_chunks=session["total_chunks"],
    )


@router.post("/upload/{session_id}/complete", response_model=DocumentUploadResponse)
async def complete_upload(
    session_id: str,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
):
    """Merge uploaded chunks and kick off document ingestion."""
    session = get_upload_session(user.access_token, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    _verify_session_owner(session, user)

    if session["status"] != "uploading":
        raise HTTPException(status_code=409, detail=f"Session is '{session['status']}', not 'uploading'")

    chunk_dir = _chunk_dir(session_id)
    total = session["total_chunks"]

    # Verify all chunks exist
    missing = []
    for i in range(total):
        if not (chunk_dir / f"{i:06d}").exists():
            missing.append(i)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing chunks: {missing[:10]}{'...' if len(missing) > 10 else ''}",
        )

    # Mark as completing
    update_upload_session(user.access_token, session_id, status="completing")

    try:
        # Merge chunks
        merged = bytearray()
        for i in range(total):
            merged.extend((chunk_dir / f"{i:06d}").read_bytes())
        file_bytes = bytes(merged)

        # Duplicate detection
        content_hash = compute_content_hash(file_bytes)
        existing = get_document_by_hash(
            user.access_token, user.id, content_hash, tenant_id=user.tenant_id,
        )
        if existing and existing["status"] != "failed":
            update_upload_session(
                user.access_token, session_id,
                status="failed",
                error_message=f"Duplicate of '{existing['filename']}'",
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "duplicate",
                    "message": f"Document already uploaded as '{existing['filename']}'",
                    "existing_document_id": existing["id"],
                },
            )

        # Ensure store exists
        token = user.access_token
        store = get_user_store(token, user.id, tenant_id=user.tenant_id)
        if not store:
            store = create_store(token, user.id, "", "local-qdrant", tenant_id=user.tenant_id)

        # Create or retry document
        if existing:
            doc = mark_document_retrying(token, existing["id"], session["filename"], session["mime_type"])
        else:
            doc = create_document(
                token, user.id, store["id"],
                session["filename"], session["mime_type"], "",
                tenant_id=user.tenant_id,
            )

        # Link session to document
        update_upload_session(
            user.access_token, session_id,
            status="completed",
            document_id=doc["id"],
        )

        # Kick off ingestion
        background_tasks.add_task(
            process_document_async,
            token, user.id, doc["id"], file_bytes, session["mime_type"],
            use_ocr=session["use_ocr"],
            pdf_parser_mode=session["pdf_parser_mode"],
            filename=session["filename"],
            tenant_id=user.tenant_id,
        )

        return DocumentUploadResponse(id=doc["id"], filename=doc["filename"], status="pending")

    finally:
        # Clean up chunk directory
        try:
            if chunk_dir.exists():
                shutil.rmtree(chunk_dir)
        except Exception as exc:
            logger.warning("Failed to clean up chunk dir %s: %s", chunk_dir, exc)


@router.get("/upload/{session_id}/status", response_model=UploadSessionStatusResponse)
async def upload_session_status(session_id: str, user=Depends(get_current_user)):
    """Return the current state of a chunked upload session."""
    session = get_upload_session(user.access_token, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    _verify_session_owner(session, user)

    # Verify actual chunk files on disk
    chunk_dir = _chunk_dir(session_id)
    actual_chunks = len(list(chunk_dir.glob("*"))) if chunk_dir.exists() else 0
    reported = min(session["uploaded_chunks"], actual_chunks)

    return UploadSessionStatusResponse(
        session_id=session_id,
        status=session["status"],
        uploaded_chunks=reported,
        total_chunks=session["total_chunks"],
        filename=session["filename"],
        error_message=session.get("error_message"),
    )


@router.delete("/upload/{session_id}")
async def cancel_upload(session_id: str, user=Depends(get_current_user)):
    """Cancel an in-progress upload session and clean up chunks."""
    session = get_upload_session(user.access_token, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    _verify_session_owner(session, user)

    if session["status"] not in ("uploading", "completing"):
        raise HTTPException(status_code=409, detail=f"Session is '{session['status']}', cannot cancel")

    update_upload_session(
        user.access_token, session_id,
        status="failed",
        error_message="Cancelled by user",
    )

    # Clean up chunks
    chunk_dir = _chunk_dir(session_id)
    try:
        if chunk_dir.exists():
            shutil.rmtree(chunk_dir)
    except Exception as exc:
        logger.warning("Failed to clean up chunk dir %s: %s", chunk_dir, exc)

    return {"message": "Upload cancelled", "session_id": session_id}
