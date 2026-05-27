from supabase import Client
from app.services.supabase import get_supabase_client, get_supabase_client_with_token


def get_db() -> Client:
    return get_supabase_client()


def get_user_db(access_token: str) -> Client:
    """Get a Supabase client authenticated as the given user (for RLS)."""
    return get_supabase_client_with_token(access_token)


def create_thread(access_token: str, user_id: str, thread_id: str, title: str = "New Chat") -> dict:
    db = get_user_db(access_token)
    result = (
        db.table("threads")
        .insert({"id": thread_id, "user_id": user_id, "title": title})
        .execute()
    )
    return result.data[0]


def get_thread(access_token: str, thread_id: str) -> dict | None:
    db = get_user_db(access_token)
    result = (
        db.table("threads")
        .select("*")
        .eq("id", thread_id)
        .execute()
    )
    return result.data[0] if result.data else None


def save_message(access_token: str, user_id: str, thread_id: str, role: str, content: str) -> dict:
    db = get_user_db(access_token)
    result = (
        db.table("messages")
        .insert({
            "thread_id": thread_id,
            "user_id": user_id,
            "role": role,
            "content": content,
        })
        .execute()
    )
    return result.data[0]


def get_thread_messages(access_token: str, thread_id: str) -> list[dict]:
    db = get_user_db(access_token)
    result = (
        db.table("messages")
        .select("*")
        .eq("thread_id", thread_id)
        .order("created_at")
        .execute()
    )
    return result.data


def get_user_threads(access_token: str, user_id: str) -> list[dict]:
    db = get_user_db(access_token)
    result = (
        db.table("threads")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


def delete_thread(access_token: str, thread_id: str) -> None:
    db = get_user_db(access_token)
    db.table("messages").delete().eq("thread_id", thread_id).execute()
    db.table("threads").delete().eq("id", thread_id).execute()


# --- File Search Store functions ---

def get_user_store(access_token: str, user_id: str) -> dict | None:
    db = get_user_db(access_token)
    result = (
        db.table("file_search_stores")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    return result.data[0] if result.data else None


def create_store(access_token: str, user_id: str, store_name: str, display_name: str) -> dict:
    db = get_user_db(access_token)
    result = (
        db.table("file_search_stores")
        .insert({"user_id": user_id, "store_name": store_name, "display_name": display_name})
        .execute()
    )
    return result.data[0]


# --- Document functions ---

def create_document(access_token: str, user_id: str, store_id: str, filename: str, mime_type: str, operation_name: str) -> dict:
    db = get_user_db(access_token)
    result = (
        db.table("documents")
        .insert({
            "user_id": user_id,
            "store_id": store_id,
            "filename": filename,
            "mime_type": mime_type,
            "operation_name": operation_name,
        })
        .execute()
    )
    return result.data[0]


def get_document(access_token: str, document_id: str) -> dict | None:
    db = get_user_db(access_token)
    result = (
        db.table("documents")
        .select("*")
        .eq("id", document_id)
        .execute()
    )
    return result.data[0] if result.data else None


def get_user_documents(access_token: str, user_id: str) -> list[dict]:
    db = get_user_db(access_token)
    result = (
        db.table("documents")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


def update_document_status(access_token: str, document_id: str, status: str, error_message: str | None = None) -> dict:
    db = get_user_db(access_token)
    update_data: dict = {"status": status}
    if error_message is not None:
        update_data["error_message"] = error_message
    result = (
        db.table("documents")
        .update(update_data)
        .eq("id", document_id)
        .execute()
    )
    return result.data[0]


def get_document_by_hash(access_token: str, user_id: str, content_hash: str) -> dict | None:
    db = get_user_db(access_token)
    result = (
        db.table("documents")
        .select("*")
        .eq("user_id", user_id)
        .eq("content_hash", content_hash)
        .execute()
    )
    return result.data[0] if result.data else None


def update_document_hash(access_token: str, document_id: str, content_hash: str) -> dict:
    db = get_user_db(access_token)
    result = (
        db.table("documents")
        .update({"content_hash": content_hash})
        .eq("id", document_id)
        .execute()
    )
    return result.data[0]


def update_document_chunk_count(access_token: str, document_id: str, count: int) -> dict:
    db = get_user_db(access_token)
    result = (
        db.table("documents")
        .update({"chunk_count": count})
        .eq("id", document_id)
        .execute()
    )
    return result.data[0]


def update_document_metadata(access_token: str, document_id: str, metadata: dict) -> dict:
    db = get_user_db(access_token)
    result = (
        db.table("documents")
        .update({"metadata": metadata})
        .eq("id", document_id)
        .execute()
    )
    return result.data[0]


def update_chunks_metadata(access_token: str, document_id: str, metadata: dict) -> None:
    db = get_user_db(access_token)
    db.table("document_chunks").update({"metadata": metadata}).eq("document_id", document_id).execute()


# --- Document chunk functions (pgvector RAG) ---

def insert_chunks(access_token: str, user_id: str, document_id: str, chunks: list[dict]) -> list[dict]:
    db = get_user_db(access_token)
    rows = [
        {
            "user_id": user_id,
            "document_id": document_id,
            "content": chunk["content"],
            "embedding": chunk["embedding"],
            "chunk_index": chunk["chunk_index"],
        }
        for chunk in chunks
    ]
    result = db.table("document_chunks").insert(rows).execute()
    return result.data


def search_similar_chunks(access_token: str, user_id: str, query_embedding: list[float], match_count: int = 5) -> list[dict]:
    db = get_user_db(access_token)
    result = db.rpc(
        "match_documents",
        {
            "query_embedding": query_embedding,
            "match_user_id": user_id,
            "match_count": match_count,
        },
    ).execute()
    return result.data


def search_similar_chunks_filtered(
    access_token: str,
    user_id: str,
    query_embedding: list[float],
    match_count: int = 5,
    filter_tags: list[str] | None = None,
    filter_language: str | None = None,
) -> list[dict]:
    db = get_user_db(access_token)
    params: dict = {
        "query_embedding": query_embedding,
        "match_user_id": user_id,
        "match_count": match_count,
    }
    if filter_tags:
        params["filter_tags"] = filter_tags
    if filter_language:
        params["filter_language"] = filter_language
    result = db.rpc("match_documents_filtered", params).execute()
    return result.data


def get_user_document_metadata(access_token: str, user_id: str) -> dict:
    db = get_user_db(access_token)
    result = (
        db.table("documents")
        .select("metadata")
        .eq("user_id", user_id)
        .execute()
    )
    all_tags: set[str] = set()
    all_languages: set[str] = set()
    for doc in result.data:
        meta = doc.get("metadata", {})
        all_tags.update(meta.get("tags", []))
        lang = meta.get("language")
        if lang:
            all_languages.add(lang)
    return {"tags": sorted(all_tags), "languages": sorted(all_languages)}


def search_chunks_fts(access_token: str, user_id: str, query_text: str, match_count: int = 10) -> list[dict]:
    db = get_user_db(access_token)
    result = db.rpc(
        "search_chunks_fts",
        {
            "search_query": query_text,
            "match_user_id": user_id,
            "match_count": match_count,
        },
    ).execute()
    return result.data


def hybrid_search(
    access_token: str,
    user_id: str,
    query_embedding: list[float],
    query_text: str,
    match_count: int = 10,
) -> list[dict]:
    db = get_user_db(access_token)
    result = db.rpc(
        "hybrid_search",
        {
            "query_embedding": query_embedding,
            "search_query": query_text,
            "match_user_id": user_id,
            "match_count": match_count,
        },
    ).execute()
    return result.data


def delete_document_chunks(access_token: str, document_id: str) -> None:
    db = get_user_db(access_token)
    db.table("document_chunks").delete().eq("document_id", document_id).execute()


# --- Agent trace functions ---

def save_agent_trace(
    access_token: str,
    user_id: str,
    thread_id: str,
    agent_name: str,
    thought: str,
    tool_used: str | None = None,
    tool_input: str | None = None,
    tool_output: str | None = None,
) -> dict:
    db = get_user_db(access_token)
    result = db.table("agent_traces").insert({
        "thread_id": thread_id,
        "user_id": user_id,
        "agent_name": agent_name,
        "thought": thought,
        "tool_used": tool_used,
        "tool_input": tool_input,
        "tool_output": tool_output,
    }).execute()
    return result.data[0]


def get_agent_traces(access_token: str, thread_id: str) -> list[dict]:
    db = get_user_db(access_token)
    result = (
        db.table("agent_traces")
        .select("*")
        .eq("thread_id", thread_id)
        .order("created_at")
        .execute()
    )
    return result.data
