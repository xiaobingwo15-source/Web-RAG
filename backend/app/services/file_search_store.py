import io
from google import genai
from google.genai import types
from app.services.database import (
    get_user_store,
    create_store,
    create_document,
    get_document,
    update_document_status,
)


async def get_or_create_store(client: genai.Client, access_token: str, user_id: str) -> str:
    existing = get_user_store(access_token, user_id)
    if existing:
        return existing["store_name"]

    store = await client.aio.file_search_stores.create(
        config=types.CreateFileSearchStoreConfig(
            display_name=f"user-{user_id[:8]}",
        )
    )
    create_store(access_token, user_id, store.name, f"user-{user_id[:8]}")
    return store.name


async def upload_document(
    client: genai.Client,
    access_token: str,
    user_id: str,
    store_name: str,
    filename: str,
    file_bytes: bytes,
    mime_type: str,
) -> dict:
    operation = await client.aio.file_search_stores.upload_to_file_search_store(
        file_search_store_name=store_name,
        file=io.BytesIO(file_bytes),
        config=types.UploadToFileSearchStoreConfig(
            mime_type=mime_type,
            display_name=filename,
        ),
    )

    store = get_user_store(access_token, user_id)
    doc = create_document(
        access_token,
        user_id,
        store["id"],
        filename,
        mime_type,
        operation.name,
    )
    return doc


async def poll_document_status(client: genai.Client, access_token: str, document_id: str) -> dict:
    doc = get_document(access_token, document_id)
    if not doc:
        return {"id": document_id, "status": "not_found", "error_message": "Document not found"}

    if doc["status"] != "pending":
        return doc

    operation = types.UploadToFileSearchStoreOperation(name=doc["operation_name"])
    result = await client.aio.operations.get(operation)

    if result.done:
        if result.error:
            update_document_status(access_token, document_id, "failed", str(result.error))
            doc["status"] = "failed"
            doc["error_message"] = str(result.error)
        else:
            update_document_status(access_token, document_id, "processed")
            doc["status"] = "processed"

    return doc
