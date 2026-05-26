# CLAUDE.md

Fully-managed Agentic RAG application utilizing Gemini 2.5 Flash. Features a clean client-facing chat layout and an automated file ingestion deck. System operates without complex admin panels and is driven via environment variables.

## Technical Stack
- Frontend: React + TypeScript + Vite + Tailwind + shadcn/ui
- Backend: Python 3 + FastAPI + Uvicorn
- Database/State: Supabase (Auth, Session Store, Thread Logs)
- AI Ecosystem: `google-genai` Python SDK (Gemini 2.5 Flash + Native File Search Engine)
- Observability: Langfuse Tracing (free tier: 50k observations/month)

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

## Development Workflow
1. **Planning** — Generate an implementation roadmap inside `.agent/plans/`.
2. **Building** — Execute sequential blocks to deploy the structural logic.
3. **Verification** — Run network, API hook, and UI sanity tests.
4. **Iteration** — Tweak code configurations based on performance verification feedback.

## Progress
Reference `PROGRESS.md` to see exactly which module layers are locked in or currently under active development.