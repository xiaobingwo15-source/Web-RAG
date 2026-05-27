# CLAUDE.md

Fully-managed Agentic RAG application. Features a clean client-facing chat layout and an automated file ingestion deck. System operates without complex admin panels and is driven via environment variables.

## Technical Stack
- Frontend: React + TypeScript + Vite + Tailwind + shadcn/ui
- Backend: Python 3 + FastAPI + Uvicorn
- Database/State: Supabase (Auth, Session Store, Thread Logs, Full-Text Search)
- Vector Storage: **Qdrant** (cloud-hosted, `document_chunks` collection, 768-dim cosine vectors)
- Chat LLM: **OpenRouter** (DeepSeek model via `openai`-compatible SDK at `https://openrouter.ai/api/v1`)
- Embeddings: `google-genai` SDK (`gemini-embedding-001`, 768 dimensions)
- Observability: Langfuse Tracing (free tier: 50k observations/month)

## RAG Pipeline Architecture

### Document Ingestion Flow
1. Upload (PDF/Excel/CSV/TXT/MD) → `backend/app/services/text_extractor.py`
2. Optional OCR via Gemini multimodal → `backend/app/services/ocr_service.py`
3. Metadata extraction (title, summary, tags, language) → `backend/app/services/metadata_extractor.py`
4. Chunking (1000 chars, 200 overlap) → `backend/app/services/chunker.py`
5. Embedding (`gemini-embedding-001`, 768-dim) → `backend/app/services/embeddings.py`
6. Store vectors in Qdrant → `backend/app/services/qdrant_db.py` (`insert_chunks`)
7. Store text in Supabase for FTS → `backend/app/services/database.py` (`insert_chunks_for_fts`)

### Query Retrieval Flow (default: hybrid mode)
1. User message → embedded via `gemini-embedding-001`
2. Parallel search: Qdrant vector search + Supabase FTS (`search_chunks_fts` RPC)
3. Merge via Reciprocal Rank Fusion (RRF, k=60)
4. LLM-based reranking → `backend/app/services/reranker.py`
5. Top chunks injected into prompt with `RAG_SYSTEM_PROMPT`

### Agent Routing
- `backend/app/services/agent_supervisor.py` — Routes queries to doc_rag, sql, web_search, or general agent
- When `use_documents=True`, always routes to `doc_rag` first
- `backend/app/services/agents/doc_rag_agent.py` — Calls `retrieve_context()` then streams LLM response
- Hardcoded refusal when 0 chunks found (LLM cannot be trusted to refuse on its own)

## Rules
- Backend runs on Python + FastAPI with Uvicorn servers.
- Strictly call the direct `google-genai` SDK — zero third-party orchestrators (No LangChain/LlamaIndex).
- Use Pydantic models for structural model responses.
- Enforce strict Row-Level Security (RLS) on Supabase session state layers — users only read their own logs.
- Deliver streaming conversations over fast Server-Sent Events (SSE).
- Rely on Gemini's native long-running operations polling to update client file indexing states.
- Manage context states using Gemini's native persistent conversation parameters.

## Planning
- Save all structural execution plans into the `.agent/plans/` folder.
- Naming convention: `{sequence_number}.{plan_name}.md` (e.g., `1.auth-setup.md`, `2.gemini-file-store.md`).
- Each objective must have an isolated, concrete verification benchmark.
- Top-level plan complexity designations:
  - ✅ **Simple** — Executable in one turn, zero infrastructural risks.
  - ⚠️ **Medium** — Involves cloud synchronization polling loops, minor iterations expected.
  - 🔴 **Complex** — Large structural updates; requires branching into sub-plans.

## Skill-First Workflow
Before planning, implementing, debugging, reviewing, or executing any task — **always check for a matching skill first**. Skills encode proven workflows and domain knowledge that improve quality and consistency.

- **Mandatory trigger**: When given a task, scan the available skills list and invoke the most relevant one using the `Skill` tool before doing anything else.
- **Match criteria**: Look for skills that cover the task type (e.g., `debug` for bugs, `feature-dev` for new features, `review` for code review, `writing-plans` for planning, `research-first` for external tech decisions, `brainstorming` for creative work).
- **Multiple matches**: If multiple skills seem relevant, pick the one most specific to the immediate task. Skills can be chained — e.g., `research-first` then `writing-plans` then `feature-dev`.
- **No match**: If no skill fits, proceed with the standard development workflow below.
- **Never skip**: Do not plan, write code, debug, or review without first checking if a skill applies. This is not optional.

## Development Workflow
1. **Skill Check** — Find and invoke the relevant skill(s) for the task.
2. **Planning** — Generate an implementation roadmap inside `.agent/plans/`.
3. **Building** — Execute sequential blocks to deploy the structural logic.
4. **Verification** — Run network, API hook, and UI sanity tests.
5. **Iteration** — Tweak code configurations based on performance verification feedback.

## Progress
Reference `PROGRESS.md` to see exactly which module layers are locked in or currently under active development.