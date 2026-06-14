# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Fully-managed Agentic RAG application. Features a clean client-facing chat layout and an automated file ingestion deck. System operates without complex admin panels and is driven via environment variables.

## Development Commands

### Backend (Python / FastAPI)
```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# Run dev server (from project root)
uvicorn app.main:app --reload --port 8000   # from backend/

# Run tests
pytest tests/ -v                             # all tests
pytest tests/test_admin_settings.py -v       # single file
pytest tests/test_admin_settings.py::test_fn -k "test_name"  # single test
```

### Frontend (React / Vite)
```powershell
cd frontend
npm install
npm run dev        # dev server on :5173
npm run build      # production build (tsc -b && vite build)
npm run lint       # eslint
```

**Windows gotcha**: VS Code injects `NODE_ENV=production` at the process level, causing `npm` to skip devDependencies (vite not found). Always clear it before npm commands:
```powershell
$env:NODE_ENV = ""; npm run dev
```

### Supabase Migrations
Migrations live in `backend/supabase/migrations/`. Apply via Supabase MCP (`mcp__supabase__apply_migration`) or the Supabase dashboard. The project uses Supabase MCP for all project management when 2FA dashboard lockout is active.

## Technical Stack
- Frontend: React + TypeScript + Vite + Tailwind + shadcn/ui
- Backend: Python 3 + FastAPI + Uvicorn
- Database/State: Supabase (Auth, Session Store, Thread Logs, Full-Text Search)
- Vector Storage: **Qdrant** (cloud-hosted, `document_chunks` collection, 768-dim cosine vectors)
- Chat LLM: **OpenRouter** (DeepSeek model via `openai`-compatible SDK at `https://openrouter.ai/api/v1`)
- Embeddings: `google-genai` SDK (`gemini-embedding-001`, 768 dimensions)
- Observability: Langfuse Tracing (free tier: 50k observations/month)

## Multi-Tenant Auth Model

Three roles with distinct access patterns:

| Role | Identified By | Access Scope |
|------|--------------|--------------|
| **Owner** | `OWNER_USER_EMAILS` env var (comma-separated) | Cross-tenant: approve/reject admins, create/disable tenants. Uses service-role client (bypasses RLS). |
| **Admin** | `profiles.role='admin'` + `status='approved'` | Tenant-scoped: manage documents, run evals, view conversations, use SQL/web-search tools. |
| **Client** | `profiles.role='client'` + `status='approved'` | Tenant-scoped: chat only. New signups require admin approval. |

Key auth files:
- `backend/app/middleware/auth.py` — `get_current_user` dependency (JWT → profile lookup)
- `backend/app/routers/owner.py` — `_verify_owner` checks email allowlist
- `backend/app/routers/admin.py` — `_verify_admin` checks role + status
- `backend/app/routers/chat.py` — `_is_approved_admin` gates tool access

**Known gap**: `disable_tenant` sets `tenants.status='disabled'` but no RLS policy or middleware checks tenant status. Disabled-tenant users retain full access.

## Security Hardening

New in migration 033 — `backend/app/services/environment_guard.py`, `audit.py`, `upload_validation.py`:

- **Environment guard**: `validate_environment_isolation()` runs at startup. Prevents non-production from pointing at production Supabase. Requires `SUPABASE_PROJECT_REF` and `PRODUCTION_SUPABASE_PROJECT_REF` env vars.
- **Audit logging**: `log_operation()` in `audit.py` records admin actions (settings changes, user approvals, eval runs, tool usage). Silently catches failures to avoid crashing on audit issues.
- **Upload validation**: `sanitize_upload_filename()` + `resolve_upload_mime_type()` + `validate_upload_bytes()` in `upload_validation.py`. Enforces filename safety, MIME type allowlist, and file signature checks.
- **CORS**: Restricted to `["GET", "POST", "PATCH", "DELETE", "OPTIONS"]` methods and `["Authorization", "Content-Type"]` headers.
- **Security headers**: HSTS (production only), X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy.
- **API docs toggle**: `ENABLE_API_DOCS=false` (default) hides `/docs`, `/scalar`, `/openapi.json`.

## RAG Pipeline Architecture

### Document Ingestion Flow
1. Upload (PDF/Excel/CSV/TXT/MD) → `backend/app/services/text_extractor.py`
2. Optional OCR via Gemini multimodal → `backend/app/services/ocr_service.py`
3. Metadata extraction (title, summary, tags, language) → `backend/app/services/metadata_extractor.py`
4. Chunking (parent-child: 1500/500 chars, 50 overlap) → `backend/app/services/chunker.py`
5. Embedding (`gemini-embedding-001`, 768-dim, configurable via env) → `backend/app/services/embeddings.py`
6. Store vectors in Qdrant → `backend/app/services/qdrant_db.py` (`insert_chunks`)
7. Store text in Supabase for FTS → `backend/app/services/database.py` (`insert_chunks_for_fts`)

### Query Retrieval Flow (default: hybrid mode)
1. User message → query rewriting (follow-up context) → multi-query expansion (3 variants)
2. Optional HyDE: generate hypothetical answer, embed it, search for similar chunks
3. Parallel search: Qdrant vector search + Supabase FTS (`search_chunks_fts` RPC, single version with `match_tenant_id`)
4. Merge via Reciprocal Rank Fusion (RRF, k=60), dedup by chunk content prefix (first 200 chars)
5. Cohere reranker (`rerank-v3.5`) → `backend/app/services/reranker.py` (fallback: keyword overlap scorer)
6. Parent resolution: child chunks replaced by their parent for broader context
7. Chunks injected into prompt with filename metadata: `[N] (Source: filename) content...`

### Agent Routing
- `backend/app/services/agent_supervisor.py` — Routes queries to doc_rag, sql, web_search, or general agent
- When `use_documents=True`, always routes to `doc_rag` first
- `backend/app/services/agents/doc_rag_agent.py` — Full RAG pipeline:
  - Multi-query expansion + HyDE + corrective RAG (web fallback when docs insufficient)
  - Groundedness check (token-overlap + LLM) with retry on low scores
  - Source dedup uses separate tracking sets for chunks vs sources (aligned 1:1 via `context_sources`)
- Hardcoded refusal when 0 chunks found (LLM cannot be trusted to refuse on its own)

### SQL Tool (`backend/app/services/sql_engine.py`)
- Gated by `SQL_TOOLS_ENABLED` env var (default: false) — also gates web search tool endpoint
- Table allowlist: `ALLOWED_TABLES = {"ie_sales", "ie_employees"}` — adding new tables requires a code change
- Validation: `TABLE_REF_RE` regex extracts `FROM`/`JOIN` table refs, `BLOCKED_KEYWORDS` regex blocks DML
- **Known gap**: regex only captures `FROM`/`JOIN` — subqueries, CTEs, and UNION can reference disallowed tables
- Executes via Supabase RPC `exec_readonly_sql` (PL/pgSQL function with its own validation layer)

### System Prompts (all language-aware)
- `RAG_SYSTEM_PROMPT` — Standard doc RAG (in `gemini.py`)
- `CORRECTIVE_RAG_SYSTEM_PROMPT` — When web search supplements documents (in `doc_rag_agent.py`)
- `HYBRID_SYSTEM_PROMPT` — When external context needed mid-answer (in `doc_rag_agent.py`)
- All prompts instruct: match user's language, don't fabricate translations, label translated content

## Rules
- Backend runs on Python + FastAPI with Uvicorn servers.
- Strictly call the direct `google-genai` SDK — zero third-party orchestrators (No LangChain/LlamaIndex).
- Use Pydantic models for structural model responses.
- Enforce strict Row-Level Security (RLS) on Supabase session state layers — users only read their own logs.
- Deliver streaming conversations over fast Server-Sent Events (SSE).
- Rely on Gemini's native long-running operations polling to update client file indexing states.
- Manage context states using Gemini's native persistent conversation parameters.
- LLM context chunks always include source filename metadata for proper citation attribution.
- Source dedup must use separate tracking sets for chunks and sources — never share a single `seen` set.
- System prompts must be language-aware: match user language, never fabricate translations from monolingual source docs.

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

## Frontend Routing
| Path | Component | Auth | Notes |
|------|-----------|------|-------|
| `/` | `LandingPage` | None | Public landing page with embedded chat widget |
| `/login` | `LoginPage` | None | Email/password sign in |
| `/dashboard` | `RoleRedirect` | Required | Redirects admin → `/admin`, client → `/chat` |
| `/admin` | `AdminPage` | Required + Admin | Document upload, conversation viewer, API settings |
| `/chat` | `ChatPage` | Required | Client-facing RAG chat interface |

## Landing Page Architecture
- **Theme**: Dark industrial PCB/manufacturing aesthetic (Material Design 3 tokens in `index.css`)
- **Sections**: Navbar → HeroSection → ServicesSection → CapabilitiesSection → ComplianceSection → Footer
- **Chat Widget**: Floating FAB at bottom-right, uses `useAnonymousChat` hook with Supabase anonymous sign-in
- **Design tokens**: `--color-surface`, `--color-on-surface`, `--color-secondary` (#ffb77d), `--color-primary` (#9fcaff)
- **Custom CSS**: `.crosshair-corner` class for technical bracket decorations on cards

## Progress
Reference `PROGRESS.md` to see exactly which module layers are locked in or currently under active development.
