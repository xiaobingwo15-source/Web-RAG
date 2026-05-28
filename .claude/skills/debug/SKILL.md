---
name: debug
description: Systematic debugging workflow for RAG pipeline, LLM output, Supabase, Qdrant, and frontend issues. Use when the user reports a bug, error, or unexpected behavior.
argument-hint: "[description-of-issue]"
allowed-tools: Bash Read Grep Glob Agent Edit Write WebSearch
---

# Debug Skill — RAG Pipeline

You are debugging an Agentic RAG application (FastAPI + Supabase + Qdrant + Gemini/OpenRouter). Follow this systematic approach.

## Phase 1: Classify the Issue

Determine which layer is affected — this dictates your investigation path.

| Layer | Symptoms | Key Files |
|-------|----------|-----------|
| **RAG retrieval** | Empty results, wrong chunks, general knowledge instead of doc context | `retrieval.py`, `qdrant_db.py`, `database.py` |
| **Reranker** | `AttributeError` on dict/list, unexpected sort behavior | `reranker.py` |
| **LLM output** | JSON parse errors, unexpected response format, system prompt ignoring | `gemini.py`, `reranker.py`, `agents/*.py` |
| **Embeddings** | Similarity scores too low, embedding dimension mismatch | `embeddings.py` |
| **Document ingestion** | Chunks not stored, metadata missing, OCR failures | `text_extractor.py`, `chunker.py`, `ocr_service.py`, `metadata_extractor.py` |
| **Supabase** | RLS blocking reads, auth failures, RPC errors | `database.py`, `supabase.py`, `middleware/auth.py` |
| **Agent routing** | Wrong agent selected, fallback to general when should use RAG | `agent_supervisor.py` |
| **Frontend** | Build errors, API call failures, SSE stream issues | `frontend/src/` |

## Phase 2: Targeted Checks Per Layer

### RAG Retrieval Issues
1. Check Qdrant has data:
   ```python
   # In a Python shell or via /api/tools endpoint
   from qdrant_client import QdrantClient
   client = QdrantClient(url=..., api_key=...)
   client.count("document_chunks")  # Should be > 0
   ```
2. Check FTS has data: run `search_chunks_fts` RPC via Supabase MCP
3. Check retrieval logs for `[RETRIEVAL]` print statements
4. Verify `user_id` alignment — clients redirect to admin's knowledge base (`retrieval.py:22-33`)
5. Check similarity threshold in `qdrant_db.py` — default was lowered to 0.15

### Reranker Issues
1. **Always check `isinstance(parsed, dict)` after `json.loads()`** — LLM wraps arrays in objects unpredictably
2. Look at `reranker.py:49-62` — dict/list defensive handling
3. Check fallback behavior when JSON parse fails (returns default scoring)

### LLM Output Issues
1. Check `json.loads()` result type — `isinstance(dict, list)` before accessing
2. Check system prompt is being followed — LLMs may ignore instructions
3. Check response format parameter (`response_format={"type": "json_object"}`)
4. For agent routing: check `agent_supervisor.py` intent classification

### Supabase Issues
1. Check RLS policies — use `mcp__supabase__get_advisors("security")`
2. Check auth token validity — middleware extracts from `Authorization: Bearer <token>`
3. Check RPC existence — `search_chunks_fts` must be created as a Supabase function
4. Use `mcp__supabase__get_logs("postgres")` for DB errors

### Frontend Issues
1. `cd frontend && npm run build` — TypeScript + Vite compilation
2. `cd frontend && npm run lint` — ESLint
3. Check API client at `frontend/src/lib/api.ts`
4. Check SSE stream handling in chat hooks

## Phase 3: Common Pitfalls

| Pitfall | Fix |
|---------|-----|
| LLM returns `{"results": [...]}` instead of `[...]` | Check `isinstance(parsed, dict)` and extract list value |
| LLM ignores system prompt refusal | Use hardcoded programmatic refusal, don't trust LLM to refuse |
| FTS blocks async event loop | Wrap in `asyncio.to_thread()` |
| Similarity threshold too high | Lower to 0.15 in `qdrant_db.py` |
| Client user can't access admin docs | `retrieve_context` redirects to admin's `user_id` |
| Logging config order | Configure logging before importing service modules |

## Phase 4: Fix & Verify

1. **Minimal fix** — change only what's needed
2. **Verify with evidence:**
   - Backend running: `curl http://localhost:8000/api/health`
   - Chunks exist: check Qdrant count and Supabase FTS
   - End-to-end: send a test query and verify response contains document context
3. **Check for similar issues** in other services (same pattern may exist in `agents/*.py`)

## Output

Report:
- **Layer** — which component was affected
- **Root cause** — what actually broke
- **Fix** — what was changed and why
- **Evidence** — how you confirmed it's fixed
- **Risk** — same pattern elsewhere?
