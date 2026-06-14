"""Formalized tool registry for the RAG agent system.

Phase 3.1: Extracts inline agent capabilities into discrete, callable tools
that the LLM can reason about and invoke selectively.

Each tool is an async function with a consistent interface:
    async def tool(params: dict, context: ToolContext) -> ToolResult
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    """Shared context passed to all tools during execution."""
    token: str | None = None
    user_id: str | None = None
    target_user_id: str | None = None
    tenant_id: str | None = None
    thread_id: str | None = None


@dataclass
class ToolResult:
    """Standardized result from a tool invocation."""
    success: bool
    chunks: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    data: dict | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Tool: search_chunks — Hybrid retrieval from knowledge base
# ---------------------------------------------------------------------------

async def search_chunks(params: dict, context: ToolContext) -> ToolResult:
    """Search the document knowledge base using hybrid retrieval.

    Params:
        query (str, required): The search query.
        mode (str, optional): "hybrid", "vector", or "fts". Default: "hybrid".
    """
    from app.services.retrieval import retrieve_context

    query = params.get("query", "")
    if not query:
        return ToolResult(success=False, error="query is required")

    mode = params.get("mode", "hybrid")

    try:
        result = await retrieve_context(
            context.token, context.user_id, query, mode=mode,
            target_user_id=context.target_user_id,
            tenant_id=context.tenant_id,
            thread_id=context.thread_id,
        )
        return ToolResult(
            success=True,
            chunks=result.get("chunks", []),
            sources=result.get("sources", []),
        )
    except Exception as e:
        logger.warning("search_chunks failed: %s", e)
        return ToolResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# Tool: read_page — Retrieve all chunks from a specific page
# ---------------------------------------------------------------------------

async def read_page(params: dict, context: ToolContext) -> ToolResult:
    """Retrieve all chunks from a specific page of a document.

    Params:
        document_id (str, required): The document ID.
        page_number (int, required): The page number to retrieve.
    """
    from app.services.database import get_chunks_by_page

    document_id = params.get("document_id", "")
    page_number = params.get("page_number")

    if not document_id:
        return ToolResult(success=False, error="document_id is required")
    if page_number is None:
        return ToolResult(success=False, error="page_number is required")

    try:
        chunks = get_chunks_by_page(context.token, document_id, int(page_number))
        if not chunks:
            return ToolResult(
                success=True,
                chunks=[],
                data={"message": f"No chunks found for page {page_number} in document {document_id}"},
            )

        # Assemble page content in order
        page_text = "\n\n".join(c["content"] for c in chunks)
        sources = [{
            "document_id": document_id,
            "page_number": page_number,
            "chunk_count": len(chunks),
            "heading": chunks[0].get("heading", ""),
        }]

        return ToolResult(
            success=True,
            chunks=[page_text],
            sources=sources,
            data={"page_number": page_number, "chunk_count": len(chunks)},
        )
    except Exception as e:
        logger.warning("read_page failed: %s", e)
        return ToolResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# Tool: extract_table — Retrieve and reconstruct a table by table_id
# ---------------------------------------------------------------------------

async def extract_table(params: dict, context: ToolContext) -> ToolResult:
    """Retrieve all chunks belonging to a specific table and reconstruct it.

    Params:
        document_id (str, required): The document ID.
        table_id (str, required): The table identifier (e.g., "table_1").
    """
    from app.services.database import get_chunks_by_table_id

    document_id = params.get("document_id", "")
    table_id = params.get("table_id", "")

    if not document_id:
        return ToolResult(success=False, error="document_id is required")
    if not table_id:
        return ToolResult(success=False, error="table_id is required")

    try:
        chunks = get_chunks_by_table_id(context.token, document_id, table_id)
        if not chunks:
            return ToolResult(
                success=True,
                chunks=[],
                data={"message": f"Table '{table_id}' not found in document {document_id}"},
            )

        # Reconstruct table from chunks
        table_text = "\n\n".join(c["content"] for c in chunks)
        sources = [{
            "document_id": document_id,
            "table_id": table_id,
            "chunk_count": len(chunks),
            "page_start": chunks[0].get("page_start"),
        }]

        return ToolResult(
            success=True,
            chunks=[table_text],
            sources=sources,
            data={"table_id": table_id, "chunk_count": len(chunks)},
        )
    except Exception as e:
        logger.warning("extract_table failed: %s", e)
        return ToolResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# Tool: search_web — Search the web for supplementary information
# ---------------------------------------------------------------------------

async def search_web_tool(params: dict, context: ToolContext) -> ToolResult:
    """Search the web for information not in the knowledge base.

    Params:
        query (str, required): The search query.
        max_results (int, optional): Max results to return. Default: 3.
    """
    from app.services.web_search import search_web

    query = params.get("query", "")
    if not query:
        return ToolResult(success=False, error="query is required")

    max_results = params.get("max_results", 3)

    try:
        results = await search_web(query, max_results=max_results)
        chunks = []
        sources = []
        for r in results:
            content = f"[Web] {r['title']}: {r['content'][:500]}"
            chunks.append(content)
            sources.append({
                "id": f"web_{r['url']}",
                "document_id": "web_search",
                "content": content,
                "score": 0.0,
                "title": r["title"],
                "url": r["url"],
            })
        return ToolResult(success=True, chunks=chunks, sources=sources)
    except Exception as e:
        logger.warning("search_web failed: %s", e)
        return ToolResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# Tool: get_document_metadata — Retrieve document-level information
# ---------------------------------------------------------------------------

async def get_document_metadata(params: dict, context: ToolContext) -> ToolResult:
    """Retrieve metadata about a specific document.

    Params:
        document_id (str, required): The document ID.
    """
    from app.services.database import get_document_info

    document_id = params.get("document_id", "")
    if not document_id:
        return ToolResult(success=False, error="document_id is required")

    try:
        info = get_document_info(context.token, document_id)
        if not info:
            return ToolResult(success=False, error=f"Document {document_id} not found")

        return ToolResult(
            success=True,
            data={
                "document_id": info["id"],
                "filename": info.get("filename"),
                "mime_type": info.get("mime_type"),
                "status": info.get("status"),
                "chunk_count": info.get("chunk_count"),
                "created_at": str(info.get("created_at", "")),
                "metadata": info.get("metadata", {}),
            },
        )
    except Exception as e:
        logger.warning("get_document_metadata failed: %s", e)
        return ToolResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "search_chunks": {
        "fn": search_chunks,
        "description": "Search the document knowledge base using hybrid retrieval. Use for general questions about document content.",
        "params": {
            "query": {"type": "string", "required": True, "description": "The search query"},
            "mode": {"type": "string", "required": False, "description": "Retrieval mode: hybrid, vector, or fts"},
        },
    },
    "read_page": {
        "fn": read_page,
        "description": "Retrieve all content from a specific page of a document. Use when the user asks about a specific page number.",
        "params": {
            "document_id": {"type": "string", "required": True, "description": "The document ID"},
            "page_number": {"type": "integer", "required": True, "description": "The page number to read"},
        },
    },
    "extract_table": {
        "fn": extract_table,
        "description": "Retrieve and reconstruct a specific table from a document. Use when the user asks about table data.",
        "params": {
            "document_id": {"type": "string", "required": True, "description": "The document ID"},
            "table_id": {"type": "string", "required": True, "description": "The table identifier (e.g., table_1)"},
        },
    },
    "search_web": {
        "fn": search_web_tool,
        "description": "Search the web for information not in the knowledge base. Use when documents don't contain the answer.",
        "params": {
            "query": {"type": "string", "required": True, "description": "The search query"},
            "max_results": {"type": "integer", "required": False, "description": "Max results (default 3)"},
        },
    },
    "get_document_metadata": {
        "fn": get_document_metadata,
        "description": "Get metadata about a document (filename, status, chunk count). Use to check document details.",
        "params": {
            "document_id": {"type": "string", "required": True, "description": "The document ID"},
        },
    },
}


def get_tool_descriptions() -> str:
    """Generate a formatted string of all available tools for the LLM system prompt."""
    lines = ["Available tools:\n"]
    for name, tool in TOOL_REGISTRY.items():
        lines.append(f"- **{name}**: {tool['description']}")
        params = tool.get("params", {})
        if params:
            for pname, pinfo in params.items():
                req = "required" if pinfo.get("required") else "optional"
                lines.append(f"  - {pname} ({pinfo['type']}, {req}): {pinfo.get('description', '')}")
    return "\n".join(lines)


async def execute_tool(name: str, params: dict, context: ToolContext) -> ToolResult:
    """Execute a tool by name with the given parameters."""
    if name not in TOOL_REGISTRY:
        return ToolResult(success=False, error=f"Unknown tool: {name}")

    fn = TOOL_REGISTRY[name]["fn"]
    try:
        return await fn(params, context)
    except Exception as e:
        logger.error("Tool %s execution failed: %s", name, e)
        return ToolResult(success=False, error=str(e))
