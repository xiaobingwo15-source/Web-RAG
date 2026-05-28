---
name: backend
description: Backend service work — FastAPI routers, Supabase operations, Qdrant vector storage, RAG pipeline services, and API integration.
argument-hint: "[what-to-work-on]"
allowed-tools: Bash Read Grep Glob Edit Write Agent WebSearch
---

# Backend Skill

You are working on the backend of an Agentic RAG application built with FastAPI + Supabase + Qdrant.

## Architecture Overview

- **Framework:** FastAPI + Uvicorn (Python 3)
- **Database:** Supabase (Auth, FTS, session state, RLS)
- **Vector store:** Qdrant (`document_chunks` collection, 768-dim cosine)
- **LLM:** OpenRouter (DeepSeek) via `openai`-compatible SDK
- **Embeddings:** `google-genai` SDK (`gemini-embedding-001`, 768-dim)
- **Observability:** Langfuse tracing

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI app, CORS, lifespan, router registration |
| `backend/app/config.py` | Pydantic Settings (env + DB-backed config) |
| `backend/app/routers/*.py` | API route handlers (health, auth, chat, documents, tools, admin) |
| `backend/app/services/*.py` | Core business logic (16 service modules) |
| `backend/app/models/*.py` | Pydantic data models (auth, chat, documents, tools) |
| `backend/app/middleware/auth.py` | Authentication middleware |

## Service Layer Map

| Service | Role |
|---------|------|
| `agent_supervisor.py` | Routes queries to doc_rag, sql, web_search, or general agent |
| `retrieval.py` | Hybrid search: Qdrant vector + Supabase FTS + RRF merge |
| `reranker.py` | LLM-based reranking of retrieved chunks |
| `qdrant_db.py` | Qdrant vector operations (insert, search, collection management) |
| `database.py` | Supabase FTS operations (`search_chunks_fts` RPC) |
| `embeddings.py` | Gemini embedding client (768-dim) |
| `chunker.py` | Text chunking (1000 chars, 200 overlap) |
| `text_extractor.py` | PDF/Excel/CSV/TXT/MD extraction |
| `ocr_service.py` | Gemini multimodal OCR for scanned PDFs |
| `metadata_extractor.py` | Title, summary, tags, language extraction |
| `gemini.py` | LLM client (OpenRouter/DeepSeek) |
| `agents/doc_rag_agent.py` | Document RAG sub-agent |
| `agents/sql_sub_agent.py` | Natural language to SQL sub-agent |
| `agents/web_search_agent.py` | Web search sub-agent |

## Conventions

1. **Pydantic models** for all request/response structures (`backend/app/models/`).
2. **SSE streaming** for chat responses — use `StreamingResponse` with `text/event-stream`.
3. **Async everywhere** — use `async def` for all route handlers and service functions.
4. **`asyncio.to_thread`** for blocking calls (Supabase sync client, FTS RPCs).
5. **No LangChain/LlamaIndex** — call `google-genai` SDK directly.
6. **RLS enforced** — users only read their own data. Admin can read all.
7. **Hardcoded refusal** when 0 chunks retrieved — LLM cannot be trusted to refuse on its own.
8. **Defensive JSON parsing** — always check `isinstance(dict/list)` after `json.loads()` on LLM responses.

## RAG Pipeline Flow

```
Upload → text_extractor → ocr_service → metadata_extractor → chunker → embeddings → qdrant_db + database (FTS)
Query  → embeddings → parallel(Qdrant vector search, Supabase FTS) → RRF merge → reranker → LLM prompt
```

## Common Tasks

### Adding a new router
1. Create `backend/app/routers/new_router.py` with `APIRouter()`
2. Register in `backend/app/main.py`: `app.include_router(new_router.router, prefix="/api/new", tags=["new"])`

### Adding a new service
1. Create `backend/app/services/new_service.py`
2. Use async functions, Pydantic models for data shapes
3. Add logging via `logging.getLogger(__name__)`

### Modifying retrieval
- Vector search: `backend/app/services/qdrant_db.py` (`search_similar_chunks`)
- FTS: `backend/app/services/database.py` (`search_chunks_fts`)
- Merge: `backend/app/services/retrieval.py` (`retrieve_context`, RRF k=60)
- Reranker: `backend/app/services/reranker.py` (`rerank_with_llm`)

### Supabase migrations
- SQL files in `backend/supabase/migrations/`
- Apply via Supabase MCP `apply_migration` tool or copy-paste into dashboard

## Verification

After backend changes:
```bash
cd backend && python -m py_compile app/main.py    # Syntax check
cd backend && python -c "from app.main import app" # Import check
curl http://localhost:8000/api/health              # Runtime check
```
