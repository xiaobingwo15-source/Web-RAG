from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, File, Form, HTTPException, Request
from app.middleware.auth import get_current_user
from app.models.documents import DocumentUploadResponse, DocumentStatus, DocumentListResponse, DocumentMetadataResponse
from app.services.file_search_store import compute_content_hash
from app.services.ingestion_worker import process_document_async
from app.services.audit import log_operation
from app.services.database import (
    create_document, get_user_documents, get_document, get_user_store, create_store,
    get_document_by_hash, get_user_document_metadata, archive_document,
    get_document_chunks, mark_document_retrying,
)
from app.services.rate_limit import check_rate_limit
from app.services.pdf_parser import normalize_pdf_parser_mode
from app.services.upload_validation import (
    resolve_upload_mime_type,
    sanitize_upload_filename,
    validate_upload_bytes,
)

router = APIRouter()


def _verify_admin(user) -> None:
    if user.role != "admin" or not user.tenant_id or user.status != "approved":
        raise HTTPException(status_code=403, detail="Admin access required")


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
    use_ocr: bool = Form(False),
    pdf_parser_mode: str = Form("auto"),
    user=Depends(get_current_user),
):
    _verify_admin(user)
    check_rate_limit(f"upload:{user.id}", limit=10, window_seconds=60)
    token = user.access_token
    parser_mode = normalize_pdf_parser_mode(pdf_parser_mode)
    safe_filename = sanitize_upload_filename(file.filename)
    mime_type = resolve_upload_mime_type(safe_filename, file.content_type)

    file_bytes = await file.read()
    validate_upload_bytes(file_bytes, mime_type)

    content_hash = compute_content_hash(file_bytes)
    existing = get_document_by_hash(token, user.id, content_hash, tenant_id=user.tenant_id)
    if existing and existing["status"] != "failed":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "duplicate",
                "message": f"Document already uploaded as '{existing['filename']}'",
                "existing_document_id": existing["id"],
            },
        )

    store = get_user_store(token, user.id, tenant_id=user.tenant_id)
    if not store:
        store = create_store(token, user.id, "", "local-qdrant", tenant_id=user.tenant_id)

    if existing:
        doc = mark_document_retrying(token, existing["id"], safe_filename, mime_type)
    else:
        doc = create_document(
            token, user.id, store["id"],
            safe_filename, mime_type, "", tenant_id=user.tenant_id,
        )
    log_operation(
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        actor_email=getattr(user, "email", None),
        actor_role=user.role,
        action="document.upload",
        resource_type="document",
        resource_id=doc["id"],
        after={"filename": safe_filename, "mime_type": mime_type, "status": doc.get("status", "pending")},
        metadata={"use_ocr": use_ocr, "pdf_parser_mode": parser_mode, "size_bytes": len(file_bytes)},
        request=request,
    )

    # Kick off processing in background and return immediately
    background_tasks.add_task(
        process_document_async,
        token, user.id, doc["id"], file_bytes, mime_type,
        use_ocr=use_ocr,
        pdf_parser_mode=parser_mode,
        filename=safe_filename,
        tenant_id=user.tenant_id,
    )

    return DocumentUploadResponse(id=doc["id"], filename=doc["filename"], status="pending")


@router.get("/status/{document_id}", response_model=DocumentStatus)
async def status(document_id: str, user=Depends(get_current_user)):
    doc = get_document(user.access_token, document_id, tenant_id=user.tenant_id)
    if not doc:
        return DocumentStatus(id=document_id, filename="", status="not_found")
    return DocumentStatus(
        id=doc["id"],
        filename=doc["filename"],
        status=doc["status"],
        error_message=doc.get("error_message"),
    )


@router.get("", response_model=DocumentListResponse)
@router.get("/", response_model=DocumentListResponse, include_in_schema=False)
async def list_documents(user=Depends(get_current_user)):
    docs = get_user_documents(user.access_token, tenant_id=user.tenant_id)
    result = [
        DocumentStatus(
            id=doc["id"],
            filename=doc["filename"],
            status=doc["status"],
            error_message=doc.get("error_message"),
            metadata=doc.get("metadata"),
        )
        for doc in docs
    ]
    return DocumentListResponse(documents=result)


@router.get("/metadata", response_model=DocumentMetadataResponse)
async def get_metadata(user=Depends(get_current_user)):
    data = get_user_document_metadata(user.access_token, tenant_id=user.tenant_id)
    return DocumentMetadataResponse(tags=data["tags"], languages=data["languages"])


@router.get("/check-qdrant")
async def check_qdrant(document_id: str | None = None, user=Depends(get_current_user)):
    _verify_admin(user)
    from app.services.qdrant_db import count_user_chunks, get_sample_chunks
    target_user_id = user.id

    chunk_count = await count_user_chunks(target_user_id, tenant_id=user.tenant_id, document_id=document_id)
    samples = await get_sample_chunks(target_user_id, limit=3, tenant_id=user.tenant_id, document_id=document_id)
    return {
        "user_id": target_user_id,
        "document_id": document_id,
        "chunk_count": chunk_count,
        "samples": samples,
    }


@router.get("/{document_id}/chunks")
async def get_chunks(document_id: str, user=Depends(get_current_user)):
    """Return all text chunks for a document (admin only). Used for document preview."""
    _verify_admin(user)

    doc = get_document(user.access_token, document_id, tenant_id=user.tenant_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks = get_document_chunks(user.access_token, document_id)
    full_text = "\n\n".join(chunk["content"] for chunk in chunks)

    return {
        "document_id": document_id,
        "filename": doc["filename"],
        "metadata": doc.get("metadata"),
        "chunk_count": len(chunks),
        "full_text": full_text,
    }


@router.delete("/{document_id}")
async def delete_document_endpoint(document_id: str, request: Request, user=Depends(get_current_user)):
    """Archive a document without deleting stored chunks or uploaded records."""
    _verify_admin(user)

    doc = get_document(user.access_token, document_id, tenant_id=user.tenant_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    archived = archive_document(user.access_token, document_id)
    filename = archived["filename"] if archived else doc["filename"]
    from app.services.semantic_cache import clear_semantic_cache
    clear_semantic_cache(f"document archived {document_id}")
    log_operation(
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        actor_email=getattr(user, "email", None),
        actor_role=user.role,
        action="document.archive",
        resource_type="document",
        resource_id=document_id,
        before=doc,
        after=archived or {"status": "archived"},
        request=request,
    )

    return {"message": f"Document '{filename}' archived", "filename": filename}
