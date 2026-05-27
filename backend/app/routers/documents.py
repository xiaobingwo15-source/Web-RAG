import mimetypes
import uuid
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from app.middleware.auth import get_current_user
from app.models.documents import DocumentUploadResponse, DocumentStatus, DocumentListResponse, DocumentMetadataResponse
from app.services.file_search_store import process_document, compute_content_hash
from app.services.database import (
    create_document, get_user_documents, get_document, get_user_store, create_store,
    get_document_by_hash, get_user_document_metadata,
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
    if existing:
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
        store = create_store(token, user.id, "", "local-pgvector")

    doc = create_document(
        token, user.id, store["id"],
        file.filename or "unnamed", mime_type, "",
    )

    await process_document(token, user.id, doc["id"], file_bytes, mime_type, use_ocr=use_ocr)

    return DocumentUploadResponse(id=doc["id"], filename=doc["filename"], status="processed")


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


@router.get("/", response_model=DocumentListResponse)
async def list_documents(user=Depends(get_current_user)):
    docs = get_user_documents(user.access_token, user.id)
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
    data = get_user_document_metadata(user.access_token, user.id)
    return DocumentMetadataResponse(tags=data["tags"], languages=data["languages"])
