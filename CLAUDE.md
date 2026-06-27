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

### RAG Readiness Gate
Run the live upload-to-answer readiness gate from the repository root, not from `backend/`, so it imports the repo-level `scripts/rag_readiness_check.py`:
```powershell
python scripts/rag_readiness_check.py --admin-token <token> --chat-token <token> --widget-tenant-slug <slug>
```
The readiness script intentionally does not delete or archive uploaded documents.

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

Latest migration: **036** — adds `status` column to `messages` table (`text NOT NULL DEFAULT 'complete'`). Used by persistent streaming to track in-flight responses (`status='streaming'` during generation, `'complete'` when done).

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
   - Structure-aware: parses headings, tables, code blocks, lists; never splits atomic blocks
   - Each chunk gets structural metadata: `heading`, `heading_level`, `structural_type`, `page_start`, `page_end`, `table_id`, `breadcrumb_path`
5. Embedding (`gemini-embedding-001`, 768-dim, configurable via env) → `backend/app/services/embeddings.py`
6. Store vectors in Qdrant → `backend/app/services/qdrant_db.py` (`insert_chunks`)
7. Store text in Supabase for FTS → `backend/app/services/database.py` (`insert_chunks_for_fts`)

### Query Retrieval Flow (default: hybrid mode)
1. User message → query rewriting (follow-up context) → multi-query expansion (2 variants, 3 total with original)
2. **Semantic cache check**: in-memory cache (`semantic_cache.py`, TTL 300s, max 256 entries) with cosine similarity threshold 0.95 — cache hit skips the entire retrieval pipeline. `invalidate_by_document()` clears entries on re-ingestion.
3. Dynamic top-k: `classify_query_complexity()` returns 3/5/8/10 chunks based on query complexity (bilingual EN+ZH)
4. Optional HyDE: generate hypothetical answer, embed it, search for similar chunks
5. **HyDE relevance backcheck**: re-verify HyDE chunks against original query embedding (threshold 0.3), reject off-topic chunks
6. Parallel search: Qdrant vector search + Supabase FTS (`search_chunks_fts` RPC, single version with `match_tenant_id`)
7. **Weighted RRF**: `_classify_query_type()` classifies queries as "keyword" or "semantic". Keyword queries (error codes, part numbers, quoted phrases) get weights 0.3 vector / 0.7 FTS; semantic queries get 0.7 vector / 0.3 FTS. RRF k=60, dedup by chunk content prefix (first 500 chars).
8. **MMR diversification**: `_mmr_diversify()` uses text-level Jaccard similarity (lambda=0.5) to balance relevance vs. diversity before reranking
9. Cohere reranker (`rerank-v3.5`) → `backend/app/services/reranker.py` (fallback: keyword overlap scorer)
10. **Reranker abstention**: if max reranker score < 0.25, return empty (refuse rather to hallucinate)
11. **Hard score threshold**: drop chunks with reranker score < 0.3
12. Parent resolution: child chunks replaced by their parent for broader context
13. **Lost-in-the-Middle reorder**: highest-scored chunks at position 0 and N-1 to maximize LLM attention
14. Chunks injected into prompt with filename metadata: `[N] (Source: filename) content...`

**Structural metadata carry-through**: Fields `heading`, `heading_level`, `structural_type`, `page_start`, `page_end`, `table_id`, `breadcrumb_path` are carried through the entire pipeline (RRF merge, parent resolution, source finalization) for citation enrichment with page numbers and section names.

### Agent Routing
- `backend/app/services/agent_supervisor.py` — Routes queries to doc_rag, sql, web_search, or general agent
- When `use_documents=True`, always routes to `doc_rag` first
- `backend/app/services/agents/doc_rag_agent.py` — Full RAG pipeline:
  - Multi-query expansion + HyDE + corrective RAG (web fallback when docs insufficient)
  - SQL delegation: `_check_delegation()` uses keyword pre-filter + LLM to route SQL queries
  - Web result relevance filtering: `_compute_keyword_overlap()` drops web results with < 10% keyword overlap
  - Hardcoded refusal when 0 chunks found (LLM cannot be trusted to refuse on its own)
  - **Early exit**: when top RRF fused score < 0.01 (all query variants retrieved near-random chunks), skips HyDE/CoVe/retries/web-fallback and returns fast refusal. Saves 10-15s on queries with no corpus coverage.
  - **Query clarification**: when retrieval fails or meta-queries detected, instead of refusing, lists available documents and asks user to narrow their question. See below.

### Query Clarification Mechanism
When the RAG pipeline would normally refuse ("I don't have that information"), it first checks if documents exist in the DB and generates a clarifying response listing available topics.

**Meta-query detection** (`_is_meta_query()`): Regex-based (bilingual EN+ZH) detection of queries about the knowledge base itself — "what documents do you have?", "有什么资料?", etc. Short-circuits expensive retrieval for pure meta-queries.

**Clarification flow** (`_try_clarification()`): Fetches document metadata via `get_user_document_summaries()` (lightweight query: id, filename, title, summary, tags), then uses LLM to generate a friendly response listing available documents and asking the user to narrow their question.

**Integration points** (3 refusal-point interceptors in `doc_rag_agent.py`):
1. **Meta-query pre-check** (after query rewrite): Short-circuits retrieval for short meta-queries
2. **Early exit** (top RRF fused score < 0.01): Tries clarification before refusing
3. **Zero-chunk / low-quality paths**: Tries clarification when no docs found or quality is low with web fallback disabled

**Key functions**: `_is_meta_query()`, `_generate_clarification()`, `_try_clarification()` in `doc_rag_agent.py`; `get_user_document_summaries()` in `database.py`

### Persistent Chat Streaming
The RAG pipeline survives client disconnects (navigation, refresh, tab close):

1. `save_message_streaming()` creates a placeholder assistant message with `status='streaming'` before the pipeline starts
2. Pipeline runs as a background `asyncio.Task` feeding events into an `asyncio.Queue`
3. SSE generator reads from queue and streams to client
4. On client disconnect: SSE generator gets `CancelledError` and returns; **background task continues**
5. When pipeline finishes: `update_message_content()` writes the full answer and sets `status='complete'`
6. Frontend `loadThread()` detects pending responses (last message is `role='user'`) and polls every 3s

Key functions: `save_message_streaming()`, `save_widget_message_streaming()`, `update_message_content()` in `database.py`

### Groundedness & Faithfulness (`backend/app/services/groundedness.py`)
Multi-layer verification to ensure answers are grounded in retrieved context:

1. **Token-overlap check**: `check_groundedness()` — fraction of answer tokens found in context (threshold: 0.5)
2. **LLM groundedness check**: `check_groundedness_with_llm()` — always runs (fast-path disabled at 0.0)
   - `web_mode=True`: verifies claims against DOCUMENT chunks specifically, not `[Web]`-tagged content
   - `use_claim_verification=True`: uses claim-level decomposition instead of token-overlap
3. **Claim decomposition**: `decompose_into_claims()` — breaks answer into atomic factual claims via LLM
4. **Per-claim verification**: `verify_claims_against_context()` — parallel LLM verification of each claim
5. **Sentence attribution**: `sentence_level_attribution()` — maps each sentence to its best supporting chunk
6. **Chain-of-Verification (CoVe)**: `chain_of_verification()` — generates up to 8 fact-checking questions, verifies each independently against context (not the draft answer), flags if > 30% unsupported
7. **Confidence scoring**: `compute_confidence_score()` — fuses retrieval (25%), reranker (25%), groundedness (35%), coverage (15%) into a single score
8. **Confidence routing**: HIGH (>0.8) → return with citations; MEDIUM (0.5-0.8) → log warning; LOW (≤0.5) → uncertainty disclaimer
9. **Citation verification**: `verify_citations()` — validates `[N]` markers map to real chunks with matching content

**Groundedness retry loop** (max 2 retries):
- Retry 1: Query reformulation based on weak answer's unsupported claims
- Retry 2: HyDE-based retrieval using refined hypothetical answer from draft

**Key constants**: `GROUNDEDNESS_THRESHOLD = 0.5`, `GROUNDEDNESS_LLM_HIGH = 0.0`, `RERANK_ABSTENTION_THRESHOLD = 0.25`, `RERANK_SCORE_THRESHOLD = 0.3`, `_WEB_RELEVANCE_THRESHOLD = 0.10`, `VECTOR_SIMILARITY_THRESHOLD = 0.1`, `MMR_LAMBDA = 0.5`, `EARLY_EXIT_FUSED_THRESHOLD = 0.01`, `HYDE_RELEVANCE_THRESHOLD = 0.3`, `VECTOR_SCORE_LOW_THRESHOLD = 0.5`, `VECTOR_SCORE_MIN_THRESHOLD = 0.4`

### SQL Tool (`backend/app/services/sql_engine.py`)
- Gated by `SQL_TOOLS_ENABLED` env var (default: false) — also gates web search tool endpoint
- Table allowlist: `ALLOWED_TABLES = {"ie_sales", "ie_employees"}` — adding new tables requires a code change
- Validation: `TABLE_REF_RE` regex extracts `FROM`/`JOIN` table refs, `BLOCKED_KEYWORDS` regex blocks DML
- **Known gap**: regex only captures `FROM`/`JOIN` — subqueries, CTEs, and UNION can reference disallowed tables
- Executes via Supabase RPC `exec_readonly_sql` (PL/pgSQL function with its own validation layer)

### Retrieval Tools (`backend/app/services/agents/tools.py`)
- `get_chunks_by_page()` — Fetches chunks for a specific page number using `page_start`/`page_end` range queries with fallbacks
- `get_chunks_by_table_id()` — Fetches chunks belonging to a specific table by `table_id` and `structural_type='table'`
- `get_document_info()` — Fetches document-level metadata for the info tool

### System Prompts (all language-aware)
- `RAG_SYSTEM_PROMPT` — Standard doc RAG (in `gemini.py`)
- `CORRECTIVE_RAG_SYSTEM_PROMPT` — When web search supplements documents (in `doc_rag_agent.py`)
- `HYBRID_SYSTEM_PROMPT` — When external context needed mid-answer (in `doc_rag_agent.py`)
- All prompts instruct: match user's language, don't fabricate translations, label translated content

### Evaluation Pipeline
Two evaluation frameworks + production quality monitoring:

**RAGAS-style LLM-as-Judge** (`eval_pipeline.py`): 4 metrics scored 1-5 — faithfulness, answer_relevance, context_precision, context_recall. Runs in parallel via `asyncio.gather`.

**Deterministic fact-based** (`rag_eval.py`): substring matching against expected facts — answer_relevance, context_relevance, groundedness (measures answer hits, not source hits), citation_accuracy, recall@k. Pass thresholds: groundedness >= 0.5, answer_relevance >= 0.5, citation_accuracy >= 0.8.

**Golden test set** (`backend/tests/fixtures/golden_test_set.json`): 25 validated test cases across 5 categories: simple_factual, multi_doc, paraphrased, edge_case, follow_up.

**CI runner** (`scripts/run_eval_ci.py`): Compares eval results against baseline (`tests/fixtures/eval_baseline.json`). Regression threshold configurable via `EVAL_REGRESSION_THRESHOLD` env var (default: 0.5). Exits code 1 when golden test set missing.

**Quality signals** (`rag_quality_policy.py`): 8 production health signals from retrieval logs and feedback — zero_sources, weak_sources, groundedness, completion_latency, negative_feedback, web_fallback, widget_policy_violation, data_staleness. Retrieval diagnostics include `score_family`, channel breakdowns, stage timings, and `top_fused_score` so signal thresholds compare like-for-like score families.

**Quality loop** (`rag_quality_loop.py`): Auto-drafts eval cases from thumbs-down feedback and web-fallback patterns. Auto-promotes cases with >= 2 negative signals. Skips duplicate queries.

## Rules
- Write generated review and diff dumps under the repo-relative `.tmp/` directory (for example, `.tmp/rag_review.diff`). Do not use `/tmp`, shell-specific environment-variable syntax, or absolute Windows paths from Bash; those paths are not portable and can create malformed files in the repository root.
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
- Groundedness verification must always run the LLM check (fast-path disabled) — token overlap alone is unreliable.
- Web-fallback answers must be verified against DOCUMENT chunks specifically, not just web-sourced content.

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

## Custom Agents (`.claude/agents/`)
Pre-built agent definitions for common diagnostic tasks:
- `rag-diagnose` — RAG pipeline health check: backend, routes, DB, Qdrant, embeddings
- `rls-debug` — Debug Supabase RLS policy violations (42501 errors, NULL tenant_id, missing profiles)
- `rag-retrieval-test` — Test retrieval quality for a specific query: chunk count, scores, relevance, diagnosis
- `db-analyst` — Read-only database analyst for production data: stats, trends, anomalies, error rates

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
Reference `PROGRESS.md` to see exactly which module layers are locked in or currently under active development. Module 10 (Landing Page + RAG Chat Widget) is complete.

## Performance Tracking
`backend/app/services/performance.py` provides latency tracking throughout the pipeline via `elapsed_ms()`, `log_latency()`, `monotonic_ms()`. Key tracked operations: `llm.query_rewrite`, `llm.query_expansion`, `llm.hyde_generation`, `llm.first_token`, `llm.completion`, `llm.cove`, `retrieval.web_search`, `retrieval.retry_hyde`.
