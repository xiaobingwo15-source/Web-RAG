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
