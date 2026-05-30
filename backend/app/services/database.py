import logging
from supabase import Client
from app.services.supabase import get_supabase_client, get_supabase_client_with_token

logger = logging.getLogger(__name__)


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


def mark_document_retrying(access_token: str, document_id: str, filename: str, mime_type: str) -> dict:
    db = get_user_db(access_token)
    result = (
        db.table("documents")
        .update({
            "filename": filename,
            "mime_type": mime_type,
            "status": "pending",
            "error_message": None,
        })
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


def insert_chunks_for_fts(access_token: str, user_id: str, document_id: str, chunks: list[dict]) -> list[dict]:
    """Insert chunk content into Supabase for full-text search (no embeddings)."""
    db = get_user_db(access_token)
    rows = [
        {
            "user_id": user_id,
            "document_id": document_id,
            "content": chunk["content"],
            "chunk_index": chunk["chunk_index"],
        }
        for chunk in chunks
    ]
    result = db.table("document_chunks").insert(rows).execute()
    return result.data


def get_document_chunks(access_token: str, document_id: str) -> list[dict]:
    """Fetch all text chunks for a document, ordered by chunk_index."""
    db = get_user_db(access_token)
    result = (
        db.table("document_chunks")
        .select("content, chunk_index")
        .eq("document_id", document_id)
        .order("chunk_index")
        .execute()
    )
    return result.data or []


def delete_document_chunks(access_token: str, document_id: str) -> None:
    db = get_user_db(access_token)
    db.table("document_chunks").delete().eq("document_id", document_id).execute()


def delete_document(access_token: str, document_id: str) -> dict | None:
    """Delete a document and its chunks from Supabase. Returns the deleted document info."""
    db = get_user_db(access_token)
    # Fetch first so we can return info after deletion
    doc = db.table("documents").select("id, filename, user_id").eq("id", document_id).execute()
    if not doc.data:
        return None
    doc_info = doc.data[0]
    # Delete chunks first (explicit, even though FK cascade exists)
    db.table("document_chunks").delete().eq("document_id", document_id).execute()
    # Delete the document row
    db.table("documents").delete().eq("id", document_id).execute()
    return doc_info


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


# --- Admin functions ---

def get_all_threads_grouped(access_token: str) -> list[dict]:
    """Fetch all threads across all users, grouped by user email.
    Note: This requires RLS policies that allow the admin to read all threads,
    OR a properly configured service_role_key. If RLS blocks access,
    only the admin's own threads will be returned.
    Returns: [{ email, user_id, threads: [{ id, title, created_at, message_count }] }]
    """
    # Try service role first, fall back to user token
    db = get_db()
    used_service_role = True
    try:
        threads_result = (
            db.table("threads")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        logger.info("Service role query succeeded, found %d threads", len(threads_result.data))
    except Exception as e:
        logger.warning("Service role query failed, falling back to user token: %s", e)
        used_service_role = False
        db = get_user_db(access_token)
        threads_result = (
            db.table("threads")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        logger.info("User token query found %d threads", len(threads_result.data))

    # Group threads by user_id
    user_threads: dict[str, list[dict]] = {}
    user_ids: set[str] = set()
    for t in threads_result.data:
        uid = t["user_id"]
        user_ids.add(uid)
        if uid not in user_threads:
            user_threads[uid] = []
        user_threads[uid].append({
            "id": t["id"],
            "title": t["title"],
            "created_at": t["created_at"],
        })

    # Fetch message counts per thread
    try:
        messages_result = db.table("messages").select("thread_id").execute()
        logger.info("Found %d messages for thread count", len(messages_result.data))
    except Exception as e:
        logger.warning("Failed to fetch message counts: %s", e)
        messages_result = type('obj', (object,), {'data': []})()

    thread_msg_count: dict[str, int] = {}
    for m in messages_result.data:
        tid = m["thread_id"]
        thread_msg_count[tid] = thread_msg_count.get(tid, 0) + 1

    # Add message count to each thread
    for uid, threads in user_threads.items():
        for t in threads:
            t["message_count"] = thread_msg_count.get(t["id"], 0)

    # Look up user emails via Supabase Auth admin API
    user_emails: dict[str, str] = {}
    try:
        for uid in user_ids:
            user_resp = db.auth.admin.get_user_by_id(uid)
            if user_resp and user_resp.user:
                user_emails[uid] = user_resp.user.email or uid
            else:
                user_emails[uid] = uid
    except Exception:
        # Fallback: use shortened user_id as identifier
        for uid in user_ids:
            user_emails[uid] = f"user-{uid[:8]}"

    # Build grouped result
    clients = []
    for uid, threads in user_threads.items():
        clients.append({
            "email": user_emails.get(uid, uid),
            "user_id": uid,
            "threads": threads,
        })

    # Sort by email
    clients.sort(key=lambda c: c["email"])
    return clients


def get_thread_messages_admin(access_token: str, thread_id: str) -> list[dict]:
    """Fetch all messages for a thread. Tries service role first, falls back to user token."""
    db = get_db()
    try:
        result = (
            db.table("messages")
            .select("*")
            .eq("thread_id", thread_id)
            .order("created_at")
            .execute()
        )
    except Exception as e:
        logger.warning("Service role query failed for messages, falling back to user token: %s", e)
        db = get_user_db(access_token)
        result = (
            db.table("messages")
            .select("*")
            .eq("thread_id", thread_id)
            .order("created_at")
            .execute()
        )
    return result.data


def get_admin_user_id(access_token: str | None = None) -> str | None:
    """Find the shared admin user ID using the service role client."""
    db = get_db()
    try:
        result = db.table("profiles").select("id").eq("role", "admin").limit(1).execute()
        if result.data:
            return result.data[0]["id"]
    except Exception as e:
        logger.warning("Failed to fetch admin user_id from profiles: %s", e)
    return None


# --- Admin Manual Answer functions ---

def save_admin_message(thread_id: str, admin_user_id: str, client_user_id: str, content: str) -> dict:
    """Insert an admin response into a client's thread.

    Uses service-role client (bypasses RLS). Sets user_id to the client's ID
    so the client's RLS policy (user_id = auth.uid()) allows them to read it.
    """
    db = get_db()
    result = (
        db.table("messages")
        .insert({
            "thread_id": thread_id,
            "user_id": client_user_id,
            "role": "admin",
            "content": content,
        })
        .execute()
    )
    return result.data[0]


def get_flagged_messages() -> list[dict]:
    """Return all messages flagged as needing admin attention, with thread context."""
    db = get_db()
    result = (
        db.table("messages")
        .select("*, threads(id, title, user_id)")
        .eq("needs_attention", True)
        .order("created_at", desc=True)
        .execute()
    )

    flagged = []
    user_emails: dict[str, str] = {}
    for msg in result.data:
        thread = msg.get("threads", {})
        client_user_id = thread.get("user_id") if thread else None
        if not client_user_id:
            continue

        # Resolve email (cache to avoid repeated lookups)
        if client_user_id not in user_emails:
            try:
                user_resp = db.auth.admin.get_user_by_id(client_user_id)
                user_emails[client_user_id] = user_resp.user.email if user_resp and user_resp.user else client_user_id
            except Exception:
                user_emails[client_user_id] = f"user-{client_user_id[:8]}"

        # Check if an admin response already exists after this message
        admin_after = (
            db.table("messages")
            .select("id")
            .eq("thread_id", msg["thread_id"])
            .eq("role", "admin")
            .gt("created_at", msg["created_at"])
            .limit(1)
            .execute()
        )

        flagged.append({
            "message_id": msg["id"],
            "thread_id": msg["thread_id"],
            "thread_title": thread.get("title", "Untitled") if thread else "Untitled",
            "client_email": user_emails[client_user_id],
            "client_user_id": client_user_id,
            "content": msg["content"],
            "created_at": msg["created_at"],
            "has_admin_response": len(admin_after.data) > 0,
        })

    return flagged


def get_flagged_count() -> int:
    """Return the count of flagged messages for the badge counter."""
    db = get_db()
    result = (
        db.table("messages")
        .select("id", count="exact")
        .eq("needs_attention", True)
        .execute()
    )
    return result.count or 0


def clear_attention_flag(message_id: str) -> dict:
    """Clear the needs_attention flag on a message."""
    db = get_db()
    result = (
        db.table("messages")
        .update({"needs_attention": False})
        .eq("id", message_id)
        .execute()
    )
    return result.data[0] if result.data else {}


def clear_thread_attention_flags(thread_id: str) -> None:
    """Clear all needs_attention flags in a thread."""
    db = get_db()
    db.table("messages").update({"needs_attention": False}).eq("thread_id", thread_id).eq("needs_attention", True).execute()
