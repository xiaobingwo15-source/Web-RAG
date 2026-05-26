import mimetypes
from fastapi import APIRouter, Depends, UploadFile, File
from app.middleware.auth import get_current_user
from app.models.documents import DocumentUploadResponse, DocumentStatus, DocumentListResponse
from app.services.gemini import get_gemini_client
from app.services.file_search_store import get_or_create_store, upload_document, poll_document_status
from app.services.database import get_user_documents

router = APIRouter()

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
}


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload(file: UploadFile = File(...), user=Depends(get_current_user)):
    client = get_gemini_client()
    token = user.access_token

    mime_type = file.content_type or "text/plain"
    if mime_type not in ALLOWED_MIME_TYPES:
        guessed, _ = mimetypes.guess_type(file.filename or "")
        if guessed in ALLOWED_MIME_TYPES:
            mime_type = guessed
        else:
            mime_type = "text/plain"

    file_bytes = await file.read()
    store_name = await get_or_create_store(client, token, user.id)

    doc = await upload_document(
        client, token, user.id, store_name,
        file.filename or "unnamed", file_bytes, mime_type,
    )

    return DocumentUploadResponse(id=doc["id"], filename=doc["filename"], status=doc["status"])


@router.get("/status/{document_id}", response_model=DocumentStatus)
async def status(document_id: str, user=Depends(get_current_user)):
    client = get_gemini_client()
    doc = await poll_document_status(client, user.access_token, document_id)
    return DocumentStatus(
        id=doc["id"],
        filename=doc["filename"],
        status=doc["status"],
        error_message=doc.get("error_message"),
    )


@router.get("/", response_model=DocumentListResponse)
async def list_documents(user=Depends(get_current_user)):
    client = get_gemini_client()
    token = user.access_token
    docs = get_user_documents(token, user.id)

    result = []
    for doc in docs:
        if doc["status"] == "pending":
            doc = await poll_document_status(client, token, doc["id"])
        result.append(DocumentStatus(
            id=doc["id"],
            filename=doc["filename"],
            status=doc["status"],
            error_message=doc.get("error_message"),
        ))

    return DocumentListResponse(documents=result)
