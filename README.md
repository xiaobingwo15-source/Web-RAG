# Claude Code Agentic RAG Masterclass

Collaborate with Claude Code to architect, verify, and launch a fully-managed Agentic RAG system entirely from scratch. Follow our structured video learning roadmap utilizing the precise operational criteria laid out across this directory.

## Core Application Overview

A production-optimized document processing engine featuring two decoupled, high-performance interfaces:
- **Interactive Chat Arena** — A threaded workspace running dialogue tracking, streaming tokens, multi-path tool calls, and sub-agent reasoning paths.
- **Managed Document Ingestion Hub** — A landing interface featuring smooth drag-and-drop file ingestion pipelines alongside live processing trackers.

This architecture completely removes the burden of writing manual, complex backend token splitters or managing custom vector index mathematics. Instead, chunk formatting, OCR parsing, semantic embedding mapping, and distance searches are offloaded directly onto Google's cloud infrastructure via the native Gemini File Search engine.

## Structural Technical Stack

| Architectural Layer | Selection Blueprint |
|---------------------|--------------------|
| Client Interface    | React + TypeScript + Vite + Tailwind + shadcn/ui |
| Backend API Engine  | Python 3 + FastAPI + Uvicorn Servers |
| Persistent Storage  | Supabase (Auth + Row-Level Security State Mapping) |
| Core AI Intelligence| `google-genai` Python SDK (Google ai studio API key) |
| Hosted RAG Engine   | Gemini Native File Search (Context Grounding Tool) |
| System Observability| LangSmith Telemetry Tracing |

## Embedding Provider Configuration

The backend supports two embedding providers:

- `EMBEDDING_PROVIDER=gemini` keeps the production/default Gemini path using `EMBEDDING_MODEL=gemini-embedding-001`.
- `EMBEDDING_PROVIDER=local_sentence_transformers` uses a local Hugging Face SentenceTransformers model for testing/offline ingestion with no hosted API quota.

Recommended local settings:

```env
EMBEDDING_PROVIDER=local_sentence_transformers
LOCAL_EMBEDDING_MODEL=intfloat/multilingual-e5-base
LOCAL_EMBEDDING_DEVICE=cpu
EMBEDDING_DIMENSION=768
```

`intfloat/multilingual-e5-base` is 768-dimensional, which matches the default Qdrant collection dimension. If you switch to a 384- or 1024-dimensional model, create or recreate the Qdrant collection with the same dimension before inserting chunks.

For CPU-only local testing, install the backend requirements first. If PyTorch is not installed by your package resolver, install the CPU wheel from the official PyTorch index:

```powershell
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r backend/requirements.txt
```

## The 8 Masterclass Modules

1. **Application Shell** — User authentication blocks, unified workspace templates, and live initialization links directly targeting Google ai studio API key.
2. **Managed Context Stores & Grounded Search** — File routing pipes deploying data straight into Gemini's `file_search_stores` with async operation tracking loops.
3. **Incremental Records Manager** — Automated content hash checksum validators guarding data indices against redundant file entries.
4. **Structured Metadata Extraction** — Programmatic metadata profiling using Pydantic tracking frames to enrich vector matching models.
5. **Multi-Format Processing Adapters** — Dynamic handling of PDF layouts, tables, Markdown, and TXT files, combined with database cascade loops.
6. **Hybrid Query Engines & Reranking** — Merging full-text search parameters with semantic matches alongside context validation scores to lower processing overhead.
7. **Advanced Dynamic Tool Routing** — Natural Language Text-to-SQL compile routes and live alternative Web Search tool fallbacks when data logs run dry.
8. **Context-Isolated Sub-Agents** — Delegated multi-turn analytical reasoning agents running sandboxed child routines with parent/child tracer interfaces.

## Getting Started Protocol

1. Clone this project repository down to your local developer machine.
2. Ensure you have installed [Claude Code](https://docs.anthropic.com/en/docs/claude-code) globally in your console.
3. Open this folder within your target IDE platform workspace (Cursor, VS Code, etc.).
4. Initialize a terminal shell path, activate your virtual environment, and launch `claude`.
5. Execute the `/onboard` command string to sync context maps instantly.

## Documentation Reference Guide

- [PRD.md](./PRD.md) — Feature matrix configurations across all 8 architectural modules.
- [CLAUDE.md](./CLAUDE.md) — System operating syntax, engineering constraints, and prompt formatting criteria.
- [PROGRESS.md](./PROGRESS.md) — Real-time ledger tracking active repository design milestones.
