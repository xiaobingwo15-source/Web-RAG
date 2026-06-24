import logging
import re
import asyncio
from datetime import UTC, datetime, timedelta
from collections.abc import Coroutine
from typing import Any
from supabase import Client
from app.services.supabase import get_supabase_client, get_supabase_client_with_token

logger = logging.getLogger(__name__)


def _run_async_cleanup(coro: Coroutine[Any, Any, Any]) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return
    task = loop.create_task(coro)
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)


def get_db() -> Client:
    return get_supabase_client()


def get_user_db(access_token: str) -> Client:
    """Get a Supabase client authenticated as the given user (for RLS)."""
    return get_supabase_client_with_token(access_token)


def get_tenant_by_slug(slug: str) -> dict | None:
    db = get_db()
    result = (
        db.table("tenants")
        .select("*")
        .eq("slug", slug)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def get_tenant_by_origin(origin: str) -> dict | None:
    """Find a tenant whose allowed_origins contains the given origin."""
    db = get_db()
    # Get all active tenants and match in Python since allowed_origins
    # may store full URLs (e.g. with path) while we pass clean origins
    result = (
        db.table("tenants")
        .select("*")
        .eq("status", "active")
        .execute()
    )
    for tenant in result.data:
        for allowed in (tenant.get("allowed_origins") or []):
            if allowed.startswith(origin) or origin.startswith(allowed):
                return tenant
    return None


def create_tenant(name: str, slug: str, allowed_origins: list[str]) -> dict:
    db = get_db()
    result = (
        db.table("tenants")
        .insert({
            "name": name,
            "slug": slug,
            "allowed_origins": allowed_origins,
            "status": "active",
        })
        .execute()
    )
    return result.data[0]


def disable_tenant(tenant_id: str) -> bool:
    """Soft-disable a tenant without deleting its records."""
    db = get_db()
    result = (
        db.table("tenants")
        .update({"status": "disabled"})
        .eq("id", tenant_id)
        .neq("status", "disabled")
        .execute()
    )
    return len(result.data) > 0


def delete_tenant(tenant_id: str) -> bool:
    """Deprecated compatibility wrapper. Use disable_tenant for soft disables."""
    return disable_tenant(tenant_id)


def create_tenant_admin_invite(tenant_id: str, email: str, token_hash: str, expires_at: str) -> dict:
    db = get_db()
    result = (
        db.table("tenant_admin_invites")
        .insert({
            "tenant_id": tenant_id,
            "email": email,
            "token_hash": token_hash,
            "expires_at": expires_at,
        })
        .execute()
    )
    return result.data[0]


def get_tenant_admin_invite(token_hash: str) -> dict | None:
    db = get_db()
    result = (
        db.table("tenant_admin_invites")
        .select("*")
        .eq("token_hash", token_hash)
        .is_("accepted_at", "null")
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def accept_tenant_admin_invite(invite_id: str, tenant_id: str, user_id: str, email: str) -> dict:
    db = get_db()
    profile = (
        db.table("profiles")
        .update({"tenant_id": tenant_id, "role": "admin", "email": email, "status": "pending"})
        .eq("id", user_id)
        .execute()
    )
    db.table("tenant_admin_invites").update({"accepted_at": "now()"}).eq("id", invite_id).execute()
    return profile.data[0] if profile.data else {}


def list_owner_admins(status_filter: str = "pending", page: int = 1, limit: int = 50) -> dict:
    """List tenant admin profiles for owner approval workflows."""
    db = get_db()
    page = max(page, 1)
    limit = min(max(limit, 1), 200)
    start = (page - 1) * limit
    end = start + limit - 1

    query = (
        db.table("profiles")
        .select("id, email, role, status, tenant_id, created_at, tenant:tenants(id, name, slug, status)", count="exact")
        .eq("role", "admin")
    )
    if status_filter != "all":
        query = query.eq("status", status_filter)

    result = query.order("created_at", desc=True).range(start, end).execute()
    admins = []
    for row in result.data or []:
        tenant = row.get("tenant") or row.get("tenants") or {}
        admins.append({
            "id": row.get("id"),
            "email": row.get("email"),
            "role": row.get("role"),
            "status": row.get("status"),
            "tenant_id": row.get("tenant_id"),
            "created_at": row.get("created_at"),
            "tenant": tenant,
        })

    return {"admins": admins, "page": page, "limit": limit, "total": result.count or 0}


def approve_owner_admin(user_id: str) -> dict | None:
    """Approve a profile only if it is still an admin candidate."""
    db = get_db()
    result = (
        db.table("profiles")
        .update({"status": "approved"})
        .eq("id", user_id)
        .eq("role", "admin")
        .execute()
    )
    return result.data[0] if result.data else None


def reject_owner_admin(user_id: str) -> dict | None:
    """Reject or revoke admin access without deleting the user account."""
    db = get_db()
    result = (
        db.table("profiles")
        .update({"role": "client", "status": "suspended"})
        .eq("id", user_id)
        .eq("role", "admin")
        .execute()
    )
    return result.data[0] if result.data else None


def get_tenant_users(tenant_id: str) -> list[dict]:
    """Fetch all profiles for a tenant."""
    db = get_db()
    result = (
        db.table("profiles")
        .select("id, email, role, status, created_at")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


def update_user_status(tenant_id: str, user_id: str, new_status: str) -> dict | None:
    """Update a user's status within a tenant. Returns updated profile or None."""
    db = get_db()
    result = (
        db.table("profiles")
        .update({"status": new_status})
        .eq("id", user_id)
        .eq("tenant_id", tenant_id)
        .execute()
    )
    return result.data[0] if result.data else None


def _apply_tenant(query, tenant_id: str | None):
    return query.eq("tenant_id", tenant_id) if tenant_id else query


def _tenant_payload(tenant_id: str | None) -> dict:
    return {"tenant_id": tenant_id} if tenant_id else {}


def create_thread(access_token: str, user_id: str, thread_id: str, title: str = "New Chat", tenant_id: str | None = None) -> dict:
    db = get_user_db(access_token)
    result = (
        db.table("threads")
        .insert({"id": thread_id, "user_id": user_id, "title": title, **_tenant_payload(tenant_id)})
        .execute()
    )
    return result.data[0]


def create_widget_thread(tenant_id: str, client_session_id: str, thread_id: str, title: str = "New Chat") -> dict:
    db = get_db()
    result = (
        db.table("threads")
        .insert({
            "id": thread_id,
            "tenant_id": tenant_id,
            "client_session_id": client_session_id,
            "title": title,
        })
        .execute()
    )
    return result.data[0]


def get_thread(access_token: str, thread_id: str, tenant_id: str | None = None) -> dict | None:
    db = get_user_db(access_token)
    query = db.table("threads").select("*").eq("id", thread_id).is_("archived_at", "null")
    result = _apply_tenant(query, tenant_id).execute()
    return result.data[0] if result.data else None


def get_thread_service(tenant_id: str, thread_id: str) -> dict | None:
    db = get_db()
    result = (
        db.table("threads")
        .select("*")
        .eq("id", thread_id)
        .eq("tenant_id", tenant_id)
        .is_("archived_at", "null")
        .execute()
    )
    return result.data[0] if result.data else None


def save_message(access_token: str, user_id: str, thread_id: str, role: str, content: str, tenant_id: str | None = None, reply_to: str | None = None) -> dict:
    db = get_user_db(access_token)
    row = {
        "thread_id": thread_id,
        "user_id": user_id,
        "role": role,
        "content": content,
        **_tenant_payload(tenant_id),
    }
    if reply_to is not None:
        row["reply_to"] = reply_to
    result = (
        db.table("messages")
        .insert(row)
        .execute()
    )
    return result.data[0]


def save_widget_message(tenant_id: str, client_session_id: str, thread_id: str, role: str, content: str, reply_to: str | None = None) -> dict:
    db = get_db()
    row = {
        "tenant_id": tenant_id,
        "client_session_id": client_session_id,
        "thread_id": thread_id,
        "role": role,
        "content": content,
    }
    if reply_to is not None:
        row["reply_to"] = reply_to
    result = (
        db.table("messages")
        .insert(row)
        .execute()
    )
    return result.data[0]


def save_message_streaming(access_token: str, user_id: str, thread_id: str, tenant_id: str | None = None) -> dict:
    """Insert a placeholder assistant message with status='streaming'.

    The RAG pipeline runs in a background task and writes the final content
    via ``update_message_content`` when generation completes — even if the
    client has already disconnected.
    """
    db = get_user_db(access_token)
    row = {
        "thread_id": thread_id,
        "user_id": user_id,
        "role": "assistant",
        "content": "",
        "status": "streaming",
        **_tenant_payload(tenant_id),
    }
    result = db.table("messages").insert(row).execute()
    return result.data[0]


def save_widget_message_streaming(tenant_id: str, client_session_id: str, thread_id: str) -> dict:
    """Widget variant of ``save_message_streaming`` (uses service-role client)."""
    db = get_db()
    row = {
        "tenant_id": tenant_id,
        "client_session_id": client_session_id,
        "thread_id": thread_id,
        "role": "assistant",
        "content": "",
        "status": "streaming",
    }
    result = db.table("messages").insert(row).execute()
    return result.data[0]


def update_message_content(message_id: str, content: str, status: str = "complete") -> dict:
    """Update a message's content and status.

    Called by the background pipeline task when generation finishes (or fails).
    """
    db = get_db()
    result = (
        db.table("messages")
        .update({"content": content, "status": status})
        .eq("id", message_id)
        .execute()
    )
    return result.data[0] if result.data else {}


def get_thread_messages(access_token: str, thread_id: str, tenant_id: str | None = None) -> list[dict]:
    db = get_user_db(access_token)
    query = db.table("messages").select("*").eq("thread_id", thread_id)
    result = _apply_tenant(query, tenant_id).order("created_at").execute()
    return result.data


def get_thread_messages_service(tenant_id: str, thread_id: str) -> list[dict]:
    db = get_db()
    result = (
        db.table("messages")
        .select("*")
        .eq("thread_id", thread_id)
        .eq("tenant_id", tenant_id)
        .order("created_at")
        .execute()
    )
    return result.data


def get_user_threads(access_token: str, user_id: str, tenant_id: str | None = None) -> list[dict]:
    db = get_user_db(access_token)
    query = db.table("threads").select("*").eq("user_id", user_id).is_("archived_at", "null")
    result = _apply_tenant(query, tenant_id).order("created_at", desc=True).execute()
    return result.data


def delete_thread(access_token: str, thread_id: str, tenant_id: str | None = None) -> None:
    db = get_user_db(access_token)
    archived_at = datetime.now(UTC).isoformat()
    _apply_tenant(
        db.table("threads").update({"archived_at": archived_at}).eq("id", thread_id),
        tenant_id,
    ).execute()


# --- File Search Store functions ---

def get_user_store(access_token: str, user_id: str, tenant_id: str | None = None) -> dict | None:
    db = get_user_db(access_token)
    query = db.table("file_search_stores").select("*").eq("user_id", user_id)
    result = _apply_tenant(query, tenant_id).execute()
    return result.data[0] if result.data else None


def create_store(access_token: str, user_id: str, store_name: str, display_name: str, tenant_id: str | None = None) -> dict:
    db = get_user_db(access_token)
    result = (
        db.table("file_search_stores")
        .insert({"user_id": user_id, "store_name": store_name, "display_name": display_name, **_tenant_payload(tenant_id)})
        .execute()
    )
    return result.data[0]


# --- Document functions ---

def create_document(access_token: str, user_id: str, store_id: str, filename: str, mime_type: str, operation_name: str, tenant_id: str | None = None) -> dict:
    db = get_user_db(access_token)
    result = (
        db.table("documents")
        .insert({
            "user_id": user_id,
            "store_id": store_id,
            "filename": filename,
            "mime_type": mime_type,
            "operation_name": operation_name,
            **_tenant_payload(tenant_id),
        })
        .execute()
    )
    return result.data[0]


def get_document(access_token: str, document_id: str, tenant_id: str | None = None) -> dict | None:
    db = get_user_db(access_token)
    query = db.table("documents").select("*").eq("id", document_id)
    result = _apply_tenant(query, tenant_id).execute()
    return result.data[0] if result.data else None


def get_documents_by_ids(access_token: str | None, document_ids: list[str], tenant_id: str | None = None) -> dict[str, dict]:
    if not document_ids:
        return {}
    db = get_user_db(access_token) if access_token else get_db()
    query = db.table("documents").select("id, filename, metadata, status").in_("id", list(set(document_ids)))
    result = _apply_tenant(query, tenant_id).execute()
    return {str(doc["id"]): doc for doc in (result.data or [])}


def get_user_documents(access_token: str, user_id: str | None = None, tenant_id: str | None = None) -> list[dict]:
    db = get_user_db(access_token)
    query = db.table("documents").select("*").neq("status", "archived")
    if user_id:
        query = query.eq("user_id", user_id)
    result = _apply_tenant(query, tenant_id).order("created_at", desc=True).execute()
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


def get_document_by_hash(access_token: str, user_id: str, content_hash: str, tenant_id: str | None = None) -> dict | None:
    db = get_user_db(access_token)
    query = db.table("documents").select("*").eq("user_id", user_id).eq("content_hash", content_hash).neq("status", "archived")
    result = _apply_tenant(query, tenant_id).execute()
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


def get_user_document_metadata(access_token: str, user_id: str | None = None, tenant_id: str | None = None) -> dict:
    db = get_user_db(access_token)
    query = db.table("documents").select("metadata")
    if user_id:
        query = query.eq("user_id", user_id)
    result = _apply_tenant(query, tenant_id).execute()
    all_tags: set[str] = set()
    all_languages: set[str] = set()
    for doc in result.data:
        meta = doc.get("metadata", {})
        all_tags.update(meta.get("tags", []))
        lang = meta.get("language")
        if lang:
            all_languages.add(lang)
    return {"tags": sorted(all_tags), "languages": sorted(all_languages)}


def get_user_document_summaries(
    access_token: str | None,
    user_id: str | None = None,
    tenant_id: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Return lightweight document inventory for clarification responses.

    Returns list of {id, filename, title, summary, tags} for non-archived docs.
    Uses the service-role client (no access_token) when access_token is None
    to support widget/anonymous callers.
    """
    db = get_user_db(access_token) if access_token else get_db()
    query = db.table("documents").select("id, filename, metadata").neq("status", "archived").limit(limit)
    if user_id:
        query = query.eq("user_id", user_id)
    result = _apply_tenant(query, tenant_id).order("created_at", desc=True).execute()
    summaries: list[dict] = []
    for doc in (result.data or []):
        meta = doc.get("metadata") or {}
        summaries.append({
            "id": doc["id"],
            "filename": doc.get("filename", "Unknown"),
            "title": meta.get("title") or doc.get("filename", "Unknown"),
            "summary": meta.get("summary", ""),
            "tags": meta.get("tags", []),
        })
    return summaries


def search_chunks_fts(access_token: str | None, user_id: str | None, query_text: str, match_count: int = 10, tenant_id: str | None = None) -> list[dict]:
    db = get_user_db(access_token) if access_token else get_db()
    params = {
        "search_query": query_text,
        "match_user_id": user_id,
        "match_count": match_count,
    }
    if tenant_id:
        params["match_tenant_id"] = tenant_id
    result = db.rpc(
        "search_chunks_fts",
        params,
    ).execute()
    return result.data


def insert_chunks_for_fts(access_token: str, user_id: str, document_id: str, chunks: list[dict], tenant_id: str | None = None) -> list[dict]:
    """Insert chunk content into Supabase for full-text search (no embeddings)."""
    db = get_user_db(access_token)
    rows = []
    for chunk in chunks:
        row: dict = {
            "user_id": user_id,
            "document_id": document_id,
            "content": chunk["content"],
            "chunk_index": chunk["chunk_index"],
            **_tenant_payload(tenant_id),
        }
        if chunk.get("parent_id"):
            row["parent_id"] = chunk["parent_id"]
        if chunk.get("chunk_type"):
            row["chunk_type"] = chunk["chunk_type"]
        if chunk.get("metadata"):
            row["metadata"] = chunk["metadata"]
        # Phase 1: per-chunk structural metadata
        if chunk.get("heading"):
            row["heading"] = chunk["heading"]
        if chunk.get("heading_level") is not None:
            row["heading_level"] = chunk["heading_level"]
        if chunk.get("structural_type"):
            row["structural_type"] = chunk["structural_type"]
        if chunk.get("page_start") is not None:
            row["page_start"] = chunk["page_start"]
        if chunk.get("page_end") is not None:
            row["page_end"] = chunk["page_end"]
        if chunk.get("table_id"):
            row["table_id"] = chunk["table_id"]
        if chunk.get("breadcrumb_path"):
            row["breadcrumb_path"] = chunk["breadcrumb_path"]
        rows.append(row)
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


def get_chunks_by_page(access_token: str, document_id: str, page_number: int) -> list[dict]:
    """Fetch all chunks for a specific page of a document, ordered by chunk_index.

    Phase 3.3: Page-level retrieval tool support.
    """
    db = get_user_db(access_token)
    result = (
        db.table("document_chunks")
        .select("content, chunk_index, heading, structural_type, page_start, page_end, breadcrumb_path")
        .eq("document_id", document_id)
        .lte("page_start", page_number)
        .gte("page_end", page_number)
        .order("chunk_index")
        .execute()
    )
    # Also include chunks where page_start matches exactly
    if not result.data:
        result = (
            db.table("document_chunks")
            .select("content, chunk_index, heading, structural_type, page_start, page_end, breadcrumb_path")
            .eq("document_id", document_id)
            .eq("page_start", page_number)
            .order("chunk_index")
            .execute()
        )
    # Final fallback: return chunks with NULL page metadata (unstructured docs)
    if not result.data:
        result = (
            db.table("document_chunks")
            .select("content, chunk_index, heading, structural_type, page_start, page_end, breadcrumb_path")
            .eq("document_id", document_id)
            .is_("page_start", "null")
            .order("chunk_index")
            .limit(50)
            .execute()
        )
    return result.data or []


def get_chunks_by_table_id(access_token: str, document_id: str, table_id: str) -> list[dict]:
    """Fetch all chunks belonging to a specific table, ordered by chunk_index.

    Phase 3.4: Table extraction tool support.
    """
    db = get_user_db(access_token)
    result = (
        db.table("document_chunks")
        .select("content, chunk_index, heading, page_start, breadcrumb_path")
        .eq("document_id", document_id)
        .eq("table_id", table_id)
        .eq("structural_type", "table")
        .order("chunk_index")
        .execute()
    )
    return result.data or []


def get_document_info(access_token: str, document_id: str) -> dict | None:
    """Fetch document-level metadata for the info tool."""
    db = get_user_db(access_token)
    result = (
        db.table("documents")
        .select("id, filename, mime_type, status, chunk_count, metadata, created_at")
        .eq("id", document_id)
        .execute()
    )
    return result.data[0] if result.data else None


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


def archive_document(access_token: str, document_id: str) -> dict | None:
    db = get_user_db(access_token)
    result = (
        db.table("documents")
        .update({"status": "archived"})
        .eq("id", document_id)
        .execute()
    )
    doc = result.data[0] if result.data else None
    if doc:
        # Clean up Qdrant vectors for archived document (fire-and-forget)
        try:
            from app.services.qdrant_db import delete_chunks_by_document
            _run_async_cleanup(delete_chunks_by_document(document_id))
        except Exception as e:
            logger.warning("Failed to clean up Qdrant vectors for archived document %s: %s", document_id, e)
        # Clean up FTS chunks for archived document
        try:
            db.table("document_chunks").delete().eq("document_id", document_id).execute()
            logger.info("Cleaned up document_chunks for archived document %s", document_id)
        except Exception as e:
            logger.warning("Failed to clean up document_chunks for archived document %s: %s", document_id, e)
    return doc


# --- Upload session functions ---

def create_upload_session(
    access_token: str,
    user_id: str,
    tenant_id: str | None,
    filename: str,
    mime_type: str,
    total_size: int,
    chunk_size: int,
    total_chunks: int,
    use_ocr: bool = False,
    pdf_parser_mode: str = "auto",
) -> dict:
    db = get_user_db(access_token)
    result = (
        db.table("upload_sessions")
        .insert({
            "user_id": user_id,
            "filename": filename,
            "mime_type": mime_type,
            "total_size": total_size,
            "chunk_size": chunk_size,
            "total_chunks": total_chunks,
            "use_ocr": use_ocr,
            "pdf_parser_mode": pdf_parser_mode,
            **_tenant_payload(tenant_id),
        })
        .execute()
    )
    return result.data[0]


def get_upload_session(access_token: str, session_id: str) -> dict | None:
    db = get_user_db(access_token)
    result = db.table("upload_sessions").select("*").eq("id", session_id).execute()
    return result.data[0] if result.data else None


def update_upload_session(
    access_token: str,
    session_id: str,
    status: str | None = None,
    uploaded_chunks: int | None = None,
    document_id: str | None = None,
    error_message: str | None = None,
) -> dict:
    db = get_user_db(access_token)
    updates: dict = {}
    if status is not None:
        updates["status"] = status
    if uploaded_chunks is not None:
        updates["uploaded_chunks"] = uploaded_chunks
    if document_id is not None:
        updates["document_id"] = document_id
    if error_message is not None:
        updates["error_message"] = error_message
    if not updates:
        return {}
    result = (
        db.table("upload_sessions")
        .update(updates)
        .eq("id", session_id)
        .execute()
    )
    return result.data[0] if result.data else {}


def expire_stale_upload_sessions() -> int:
    """Expire upload sessions older than 24 hours. Returns count expired."""
    from datetime import timedelta
    db = get_db()
    cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    result = (
        db.table("upload_sessions")
        .update({"status": "expired", "error_message": "Session expired after 24 hours"})
        .eq("status", "uploading")
        .lt("created_at", cutoff)
        .execute()
    )
    return len(result.data) if result.data else 0


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
    tenant_id: str | None = None,
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
        **_tenant_payload(tenant_id),
    }).execute()
    return result.data[0]


def get_agent_traces(access_token: str, thread_id: str, tenant_id: str | None = None) -> list[dict]:
    db = get_user_db(access_token)
    query = db.table("agent_traces").select("*").eq("thread_id", thread_id)
    result = _apply_tenant(query, tenant_id).order("created_at").execute()
    return result.data


# --- Admin functions ---

def get_all_threads_grouped(tenant_id: str) -> list[dict]:
    """Fetch threads for one tenant, grouped by user or widget session.

    Returns: [{ email, user_id, threads: [{ id, title, created_at, message_count }] }]
    """
    db = get_db()
    threads_result = (
        db.table("threads")
        .select("*")
        .eq("tenant_id", tenant_id)
        .is_("archived_at", "null")
        .order("created_at", desc=True)
        .execute()
    )
    logger.info("Tenant-scoped admin query found %d threads", len(threads_result.data))

    # Group threads by user_id
    user_threads: dict[str, list[dict]] = {}
    user_ids: set[str] = set()
    for t in threads_result.data:
        uid = t.get("user_id") or t.get("client_session_id") or "unknown"
        if t.get("user_id"):
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
        messages_result = db.table("messages").select("thread_id").eq("tenant_id", tenant_id).execute()
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
        label = user_emails.get(uid)
        if not label:
            label = f"visitor-{uid[:8]}" if uid != "unknown" else "unknown visitor"
        clients.append({
            "email": label,
            "user_id": uid,
            "threads": threads,
        })

    # Sort by email
    clients.sort(key=lambda c: c["email"])
    return clients


def get_thread_messages_admin(tenant_id: str, thread_id: str) -> list[dict]:
    """Fetch messages for a tenant-owned thread."""
    db = get_db()
    result = (
        db.table("messages")
        .select("*")
        .eq("thread_id", thread_id)
        .eq("tenant_id", tenant_id)
        .order("created_at")
        .execute()
    )
    return result.data


def get_tenant_admin_user_id(tenant_id: str) -> str | None:
    """Find the single admin user ID for a tenant."""
    db = get_db()
    try:
        result = (
            db.table("profiles")
            .select("id")
            .eq("role", "admin")
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]["id"]
    except Exception as e:
        logger.warning("Failed to fetch tenant admin user_id from profiles: %s", e)
    return None


# --- RAG evaluation functions ---

def get_or_create_default_eval_suite(tenant_id: str) -> dict:
    db = get_db()
    existing = (
        db.table("rag_eval_suites")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("created_at")
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0]

    result = (
        db.table("rag_eval_suites")
        .insert({
            "tenant_id": tenant_id,
            "name": "Default RAG Eval Suite",
            "description": "Internal document-grounded RAG quality checks",
        })
        .execute()
    )
    return result.data[0]


def list_rag_eval_cases(tenant_id: str, enabled_only: bool = False) -> list[dict]:
    db = get_db()
    query = (
        db.table("rag_eval_cases")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
    )
    if enabled_only:
        query = query.eq("enabled", True).eq("status", "active")
    rows = query.execute().data or []
    if enabled_only:
        return [row for row in rows if row.get("expected_facts")]
    return rows


def create_rag_eval_case(tenant_id: str, payload: dict) -> dict:
    db = get_db()
    suite = get_or_create_default_eval_suite(tenant_id)
    status = payload.get("status") or "active"
    row = {
        "tenant_id": tenant_id,
        "suite_id": suite["id"],
        "question": payload["question"],
        "expected_facts": payload.get("expected_facts") or [],
        "expected_answer": payload.get("expected_answer"),
        "expected_document_id": payload.get("expected_document_id") or None,
        "tags": payload.get("tags") or [],
        "enabled": payload.get("enabled", status != "draft"),
        "status": status,
        "source_type": payload.get("source_type") or None,
        "source_ref_id": payload.get("source_ref_id") or None,
        "retrieval_metadata": payload.get("retrieval_metadata") or {},
    }
    result = db.table("rag_eval_cases").insert(row).execute()
    return result.data[0]


def update_rag_eval_case(tenant_id: str, case_id: str, payload: dict) -> dict | None:
    db = get_db()
    allowed = {
        "question",
        "expected_facts",
        "expected_answer",
        "expected_document_id",
        "tags",
        "enabled",
        "status",
        "source_type",
        "source_ref_id",
        "retrieval_metadata",
    }
    updates = {key: value for key, value in payload.items() if key in allowed}
    if not updates:
        return None
    updates["updated_at"] = datetime.now(UTC).isoformat()
    result = (
        db.table("rag_eval_cases")
        .update(updates)
        .eq("tenant_id", tenant_id)
        .eq("id", case_id)
        .execute()
    )
    return result.data[0] if result.data else None


def create_rag_eval_run(
    tenant_id: str,
    suite_id: str | None,
    retrieval_mode: str,
    model_provider: str,
    model_name: str,
    total_cases: int,
) -> dict:
    db = get_db()
    result = (
        db.table("rag_eval_runs")
        .insert({
            "tenant_id": tenant_id,
            "suite_id": suite_id,
            "status": "running",
            "retrieval_mode": retrieval_mode,
            "model_provider": model_provider,
            "model_name": model_name,
            "total_cases": total_cases,
            "started_at": datetime.now(UTC).isoformat(),
        })
        .execute()
    )
    return result.data[0]


def update_rag_eval_run(tenant_id: str, run_id: str, updates: dict) -> dict:
    db = get_db()
    result = (
        db.table("rag_eval_runs")
        .update(updates)
        .eq("tenant_id", tenant_id)
        .eq("id", run_id)
        .execute()
    )
    return result.data[0] if result.data else {}


def insert_rag_eval_result(
    tenant_id: str,
    run_id: str,
    case: dict,
    answer: str,
    sources: list[dict],
    score,
) -> dict:
    db = get_db()
    result_status = "passed" if bool(score.passed) else "failed"
    row = {
        "tenant_id": tenant_id,
        "run_id": run_id,
        "case_id": case.get("id"),
        "question": case["question"],
        "expected_facts": case.get("expected_facts") or [],
        "answer": answer,
        "sources": sources,
        "context_relevance_score": score.context_relevance_score,
        "groundedness_score": score.groundedness_score,
        "answer_relevance_score": score.answer_relevance_score,
        "passed": score.passed,
        "result_status": result_status,
        "failure_reason": score.failure_reason,
    }
    # Phase 4.2/4.4: New metrics
    if score.citation_accuracy_score is not None:
        row["citation_accuracy_score"] = score.citation_accuracy_score
    if score.recall_at_k is not None:
        row["recall_at_k"] = score.recall_at_k
    result = db.table("rag_eval_results").insert(row).execute()
    return result.data[0]


def list_rag_eval_runs(tenant_id: str, limit: int = 20) -> list[dict]:
    db = get_db()
    return (
        db.table("rag_eval_runs")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )


def get_rag_eval_run(tenant_id: str, run_id: str) -> dict | None:
    db = get_db()
    result = (
        db.table("rag_eval_runs")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("id", run_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def list_rag_eval_results(tenant_id: str, run_id: str) -> list[dict]:
    db = get_db()
    return (
        db.table("rag_eval_results")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("run_id", run_id)
        .order("created_at")
        .execute()
        .data
    )


# --- Admin Manual Answer functions ---

def save_admin_message(tenant_id: str, thread_id: str, admin_user_id: str, client_user_id: str | None, content: str) -> dict:
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
            "tenant_id": tenant_id,
        })
        .execute()
    )
    return result.data[0]


def get_flagged_messages(tenant_id: str) -> list[dict]:
    """Return all messages flagged as needing admin attention, with thread context."""
    db = get_db()
    result = (
        db.table("messages")
        .select("*, threads(id, title, user_id)")
        .eq("tenant_id", tenant_id)
        .or_("attention_status.eq.needs_admin,needs_attention.eq.true")
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
            .eq("tenant_id", tenant_id)
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


def get_flagged_count(tenant_id: str) -> int:
    """Return the count of flagged messages for the badge counter."""
    db = get_db()
    result = (
        db.table("messages")
        .select("id", count="exact")
        .eq("tenant_id", tenant_id)
        .or_("attention_status.eq.needs_admin,needs_attention.eq.true")
        .execute()
    )
    return result.count or 0


def clear_attention_flag(message_id: str) -> dict:
    """Clear the admin-attention status on a message."""
    db = get_db()
    result = (
        db.table("messages")
        .update({"needs_attention": False, "attention_status": "dismissed"})
        .eq("id", message_id)
        .execute()
    )
    return result.data[0] if result.data else {}


def clear_thread_attention_flags(tenant_id: str, thread_id: str) -> None:
    """Clear all admin-attention statuses in a thread after an admin response."""
    db = get_db()
    (
        db.table("messages")
        .update({"needs_attention": False, "attention_status": "responded"})
        .eq("thread_id", thread_id)
        .eq("tenant_id", tenant_id)
        .or_("attention_status.eq.needs_admin,needs_attention.eq.true")
        .execute()
    )


# --- Retrieval logging ---

def _grounding_status_from_result(
    groundedness_score: float | None,
    groundedness_flag: bool,
) -> str:
    if groundedness_flag:
        return "ungrounded"
    if groundedness_score is None:
        return "not_checked"
    if groundedness_score < 0.7:
        return "low_confidence"
    return "ok"


def log_retrieval(
    query: str,
    retrieval_mode: str,
    chunk_count: int,
    source_count: int = 0,
    top_score: float | None = None,
    duration_ms: int | None = None,
    user_id: str | None = None,
    tenant_id: str | None = None,
    thread_id: str | None = None,
    sources: list[dict] | None = None,
    chunks: list[str] | None = None,
    retrieval_quality: str | None = None,
    diagnostics: dict | None = None,
) -> dict | None:
    """Log a retrieval request for analytics. Fire-and-forget — returns None on error."""
    try:
        db = get_db()
        row = {
            "query": query[:1000],
            "retrieval_mode": retrieval_mode,
            "chunk_count": chunk_count,
            "source_count": source_count,
            "sources": sources or [],
            "chunks": chunks or [],
            "diagnostics": diagnostics or {},
            "grounding_status": "not_checked",
            **({"top_score": top_score} if top_score is not None else {}),
            **({"duration_ms": duration_ms} if duration_ms is not None else {}),
            **({"user_id": user_id} if user_id else {}),
            **({"tenant_id": tenant_id} if tenant_id else {}),
            **({"thread_id": thread_id} if thread_id else {}),
            **({"retrieval_quality": retrieval_quality} if retrieval_quality else {}),
        }
        result = db.table("retrieval_logs").insert(row).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.warning("Failed to log retrieval: %s", e)
        return None


def get_retrieval_logs(
    tenant_id: str,
    zero_chunks_only: bool = False,
    limit: int = 50,
) -> list[dict]:
    """Fetch retrieval logs for admin review."""
    db = get_db()
    query = (
        db.table("retrieval_logs")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if zero_chunks_only:
        query = query.eq("chunk_count", 0)
    return query.execute().data


def list_recent_retrieval_logs(
    tenant_id: str,
    window_hours: int = 168,
    limit: int = 200,
) -> list[dict]:
    """Fetch recent retrieval logs for quality-loop promotion."""
    db = get_db()
    window_hours = min(max(int(window_hours or 168), 1), 24 * 30)
    limit = min(max(int(limit or 200), 1), 500)
    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
    cutoff_iso = cutoff.isoformat().replace("+00:00", "Z")
    return (
        db.table("retrieval_logs")
        .select("*")
        .eq("tenant_id", tenant_id)
        .gte("created_at", cutoff_iso)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )


def update_retrieval_logs_for_answer(
    tenant_id: str,
    retrieval_log_ids: list[str],
    answer_message_id: str,
    groundedness_score: float | None = None,
    groundedness_flag: bool = False,
    retrieval_quality: str | None = None,
    diagnostics: dict | None = None,
) -> None:
    """Attach retrieval evidence rows to the saved assistant message."""
    ids = [log_id for log_id in retrieval_log_ids if log_id]
    if not ids:
        return
    grounding_status = _grounding_status_from_result(groundedness_score, groundedness_flag)
    updates: dict = {
        "answer_message_id": answer_message_id,
        "groundedness_flag": groundedness_flag,
        "grounding_status": grounding_status,
    }
    if groundedness_score is not None:
        updates["groundedness_score"] = groundedness_score
    if retrieval_quality:
        updates["retrieval_quality"] = retrieval_quality
    if diagnostics is not None:
        updates["diagnostics"] = diagnostics
    try:
        db = get_db()
        if diagnostics is None:
            (
                db.table("retrieval_logs")
                .update(updates)
                .eq("tenant_id", tenant_id)
                .in_("id", ids)
                .execute()
            )
            return

        existing_rows = (
            db.table("retrieval_logs")
            .select("id, diagnostics")
            .eq("tenant_id", tenant_id)
            .in_("id", ids)
            .execute()
            .data
            or []
        )
        for row in existing_rows:
            merged = {
                **(row.get("diagnostics") or {}),
                **diagnostics,
            }
            (
                db.table("retrieval_logs")
                .update({**updates, "diagnostics": merged})
                .eq("tenant_id", tenant_id)
                .eq("id", row["id"])
                .execute()
            )
    except Exception as e:
        logger.warning("Failed to attach retrieval logs to answer: %s", e)


def list_rag_quality_signals(
    tenant_id: str,
    window_hours: int = 168,
    limit: int = 50,
) -> dict:
    """Aggregate recent retrieval and feedback evidence into quality signals."""
    from app.services.rag_quality_policy import build_rag_quality_signals

    db = get_db()
    window_hours = min(max(int(window_hours or 168), 1), 24 * 30)
    limit = min(max(int(limit or 50), 1), 200)
    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
    cutoff_iso = cutoff.isoformat().replace("+00:00", "Z")

    retrieval_logs = (
        db.table("retrieval_logs")
        .select("*")
        .eq("tenant_id", tenant_id)
        .gte("created_at", cutoff_iso)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    feedback_rows = (
        db.table("message_feedback")
        .select("id, thread_id, message_id, rating, comment, created_at, client_session_id, user_id")
        .eq("tenant_id", tenant_id)
        .gte("created_at", cutoff_iso)
        .order("created_at", desc=True)
        .limit(max(limit, 50))
        .execute()
        .data
        or []
    )

    return build_rag_quality_signals(
        retrieval_logs=retrieval_logs,
        feedback_rows=feedback_rows,
        window_hours=window_hours,
        limit=limit,
    )


def _resolve_feedback_answer_message(db, tenant_id: str, feedback: dict) -> dict | None:
    message_id = str(feedback.get("message_id") or "")
    thread_id = feedback.get("thread_id")
    if not thread_id or not message_id:
        return None

    if re.fullmatch(r"[0-9a-fA-F-]{36}", message_id):
        result = (
            db.table("messages")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("thread_id", thread_id)
            .eq("id", message_id)
            .eq("role", "assistant")
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    legacy = re.fullmatch(r"msg-(\d+)", message_id)
    if not legacy:
        return None

    display_index = int(legacy.group(1))
    messages = (
        db.table("messages")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("thread_id", thread_id)
        .neq("role", "admin")
        .order("created_at")
        .execute()
        .data
        or []
    )
    if 0 <= display_index < len(messages) and messages[display_index].get("role") == "assistant":
        return messages[display_index]
    return None


def _previous_user_question(db, tenant_id: str, thread_id: str, before_created_at: str) -> dict | None:
    result = (
        db.table("messages")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("thread_id", thread_id)
        .eq("role", "user")
        .lt("created_at", before_created_at)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _thread_retrieval_logs(db, tenant_id: str, thread_id: str, answer_message_id: str | None) -> list[dict]:
    if answer_message_id:
        direct = (
            db.table("retrieval_logs")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("answer_message_id", answer_message_id)
            .order("created_at", desc=True)
            .limit(10)
            .execute()
            .data
            or []
        )
        if direct:
            return direct

    return (
        db.table("retrieval_logs")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("thread_id", thread_id)
        .order("created_at", desc=True)
        .limit(10)
        .execute()
        .data
        or []
    )


def list_rag_quality_thumbs_down(tenant_id: str, limit: int = 50) -> list[dict]:
    """Return recent negative feedback with answer and retrieval evidence."""
    db = get_db()
    limit = min(max(limit, 1), 100)
    feedback_rows = (
        db.table("message_feedback")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("rating", -1)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )

    items = []
    user_emails: dict[str, str] = {}
    for feedback in feedback_rows:
        answer = _resolve_feedback_answer_message(db, tenant_id, feedback)
        if not answer:
            continue

        thread_id = answer["thread_id"]
        thread_result = (
            db.table("threads")
            .select("id, title, user_id, client_session_id, created_at")
            .eq("tenant_id", tenant_id)
            .eq("id", thread_id)
            .limit(1)
            .execute()
        )
        thread = thread_result.data[0] if thread_result.data else {}
        client_user_id = thread.get("user_id") or answer.get("user_id") or feedback.get("user_id")

        client_email = None
        if client_user_id:
            if client_user_id not in user_emails:
                try:
                    user_resp = db.auth.admin.get_user_by_id(client_user_id)
                    user_emails[client_user_id] = user_resp.user.email if user_resp and user_resp.user else client_user_id
                except Exception:
                    user_emails[client_user_id] = f"user-{str(client_user_id)[:8]}"
            client_email = user_emails[client_user_id]
        if not client_email:
            client_email = f"visitor-{str(thread.get('client_session_id') or 'unknown')[:8]}"

        question = _previous_user_question(db, tenant_id, thread_id, answer["created_at"])
        logs = _thread_retrieval_logs(db, tenant_id, thread_id, answer.get("id"))
        grounded_scores = [
            float(log["groundedness_score"])
            for log in logs
            if log.get("groundedness_score") is not None
        ]
        top_scores = [float(log["top_score"]) for log in logs if log.get("top_score") is not None]

        items.append({
            "feedback_id": feedback["id"],
            "feedback_created_at": feedback["created_at"],
            "feedback_comment": feedback.get("comment"),
            "rating": feedback["rating"],
            "message_id": feedback.get("message_id"),
            "resolved_message_id": answer.get("id"),
            "thread_id": thread_id,
            "thread_title": thread.get("title") or "Untitled",
            "client_user_id": client_user_id,
            "client_email": client_email,
            "question": question.get("content") if question else "",
            "question_message_id": question.get("id") if question else None,
            "answer": answer.get("content") or "",
            "answer_created_at": answer.get("created_at"),
            "retrieval_logs": logs,
            "summary": {
                "retrieval_count": len(logs),
                "chunk_count": sum(int(log.get("chunk_count") or 0) for log in logs),
                "source_count": sum(int(log.get("source_count") or 0) for log in logs),
                "top_score": max(top_scores) if top_scores else None,
                "groundedness_score": min(grounded_scores) if grounded_scores else None,
                "groundedness_flag": any(
                    bool(log.get("groundedness_flag"))
                    or log.get("grounding_status") in {"low_confidence", "ungrounded"}
                    for log in logs
                ),
                "zero_source": any(int(log.get("source_count") or 0) == 0 for log in logs),
            },
        })

    return items


# --- Message feedback ---

def save_message_feedback(
    user_id: str,
    thread_id: str,
    message_id: str,
    rating: int,
    comment: str | None = None,
    tenant_id: str | None = None,
) -> dict | None:
    """Save thumbs up (1) or thumbs down (-1) feedback for a message."""
    try:
        db = get_db()
        row = {
            "user_id": user_id,
            "thread_id": thread_id,
            "message_id": message_id,
            "rating": rating,
            **({"comment": comment} if comment else {}),
            **({"tenant_id": tenant_id} if tenant_id else {}),
        }
        result = (
            db.table("message_feedback")
            .upsert(row, on_conflict="user_id,thread_id,message_id")
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        logger.warning("Failed to save message feedback: %s", e)
        return None


def save_widget_feedback(
    client_session_id: str,
    thread_id: str,
    message_id: str,
    rating: int,
    comment: str | None = None,
    tenant_id: str | None = None,
) -> dict | None:
    """Save feedback for an anonymous widget message. Uses service-role (bypasses RLS)."""
    try:
        db = get_db()
        row = {
            "client_session_id": client_session_id,
            "thread_id": thread_id,
            "message_id": message_id,
            "rating": rating,
            **({"comment": comment} if comment else {}),
            **({"tenant_id": tenant_id} if tenant_id else {}),
        }
        result = (
            db.table("message_feedback")
            .upsert(row, on_conflict="client_session_id,thread_id,message_id")
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        logger.warning("Failed to save widget feedback: %s", e)
        return None


def get_message_feedback(
    user_id: str,
    thread_id: str,
) -> list[dict]:
    """Get all feedback a user gave in a thread."""
    db = get_db()
    result = (
        db.table("message_feedback")
        .select("message_id, rating")
        .eq("user_id", user_id)
        .eq("thread_id", thread_id)
        .execute()
    )
    return result.data or []
