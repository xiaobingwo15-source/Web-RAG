import mimetypes
import uuid
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from app.middleware.auth import get_current_user
from app.models.documents import DocumentUploadResponse, DocumentStatus, DocumentListResponse, DocumentMetadataResponse
from app.services.file_search_store import process_document, compute_content_hash
from app.services.database import (
    create_document, get_user_documents, get_document, get_user_store, create_store,
    get_document_by_hash, get_user_document_metadata, delete_document,
    get_document_chunks, mark_document_retrying,
)

router = APIRouter()

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload(
    file: UploadFile = File(...),
    use_ocr: bool = False,
    user=Depends(get_current_user),
):
    token = user.access_token

    filename_lower = (file.filename or "").lower()
    if filename_lower.endswith(".csv"):
        mime_type = "text/csv"
    elif filename_lower.endswith(".xlsx"):
        mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif filename_lower.endswith(".xls"):
        mime_type = "application/vnd.ms-excel"
    elif filename_lower.endswith(".pdf"):
        mime_type = "application/pdf"
    elif filename_lower.endswith((".md", ".markdown")):
        mime_type = "text/markdown"
    elif filename_lower.endswith((".txt", ".text")):
        mime_type = "text/plain"
    else:
        mime_type = file.content_type or "text/plain"
        if mime_type not in ALLOWED_MIME_TYPES:
            guessed, _ = mimetypes.guess_type(file.filename or "")
            if guessed in ALLOWED_MIME_TYPES:
                mime_type = guessed
            else:
                mime_type = "text/plain"

    file_bytes = await file.read()

    content_hash = compute_content_hash(file_bytes)
    existing = get_document_by_hash(token, user.id, content_hash)
    if existing and existing["status"] != "failed":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "duplicate",
                "message": f"Document already uploaded as '{existing['filename']}'",
                "existing_document_id": existing["id"],
            },
        )

    store = get_user_store(token, user.id)
    if not store:
        store = create_store(token, user.id, "", "local-qdrant")

    if existing:
        doc = mark_document_retrying(token, existing["id"], file.filename or "unnamed", mime_type)
    else:
        doc = create_document(
            token, user.id, store["id"],
            file.filename or "unnamed", mime_type, "",
        )

    process_result = await process_document(token, user.id, doc["id"], file_bytes, mime_type, use_ocr=use_ocr)

    return DocumentUploadResponse(id=doc["id"], filename=doc["filename"], status=process_result["status"])


@router.get("/status/{document_id}", response_model=DocumentStatus)
async def status(document_id: str, user=Depends(get_current_user)):
    doc = get_document(user.access_token, document_id)
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
    target_user_id = user.id
    if user.role == "client":
        from app.services.database import get_admin_user_id
        admin_id = get_admin_user_id(user.access_token)
        if admin_id:
            target_user_id = admin_id

    docs = get_user_documents(user.access_token, target_user_id)
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
    target_user_id = user.id
    if user.role == "client":
        from app.services.database import get_admin_user_id
        admin_id = get_admin_user_id(user.access_token)
        if admin_id:
            target_user_id = admin_id

    data = get_user_document_metadata(user.access_token, target_user_id)
    return DocumentMetadataResponse(tags=data["tags"], languages=data["languages"])


@router.get("/check-qdrant")
async def check_qdrant(user=Depends(get_current_user)):
    from app.services.qdrant_db import count_user_chunks, get_sample_chunks
    target_user_id = user.id
    if user.role == "client":
        from app.services.database import get_admin_user_id
        admin_id = get_admin_user_id(user.access_token)
        if admin_id:
            target_user_id = admin_id

    chunk_count = await count_user_chunks(target_user_id)
    samples = await get_sample_chunks(target_user_id, limit=3)
    print(f"[DEBUG] check-qdrant: user_id={target_user_id}, chunks={chunk_count}")
    return {
        "user_id": target_user_id,
        "chunk_count": chunk_count,
        "samples": samples,
    }


@router.get("/{document_id}/chunks")
async def get_chunks(document_id: str, user=Depends(get_current_user)):
    """Return all text chunks for a document (admin only). Used for document preview."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    doc = get_document(user.access_token, document_id)
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
async def delete_document_endpoint(document_id: str, user=Depends(get_current_user)):
    """Delete a document and all its chunks (admin only)."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    doc = get_document(user.access_token, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete vectors from Qdrant
    from app.services.qdrant_db import delete_document_chunks as qdrant_delete
    await qdrant_delete(document_id)

    # Delete from Supabase (chunks + document row)
    deleted = delete_document(user.access_token, document_id)
    filename = deleted["filename"] if deleted else doc["filename"]

    return {"message": f"Document '{filename}' deleted", "filename": filename}
