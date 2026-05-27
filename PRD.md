Here is the completely revised, production-ready **PRD markdown layout**. You can copy this block wholesale and overwrite the existing PRD file in your workspace to give your coding assistant full context on all 8 modules.

---

```markdown
# Agentic RAG Masterclass - Complete Product Requirements Document (PRD)

## What We Are Building

A decoupled, multi-tenant, production-optimized Agentic RAG engine serving exactly two user surfaces:
1. **Chat Interaction Pane** — A dynamic workspace delivering context-grounded conversational messaging blocks alongside real-time multi-agent reasoning trace blocks.
2. **Data Processing Panel** — An administrative dashboard workspace to drag-and-drop source data assets (PDFs, Markdown, text sheets, CSV data) directly into multi-tenant Postgres vector storage buckets.

This platform utilizes an advanced multi-agent orchestrator setup. Instead of relying on rigid, single-vector indexing pipelines, text parsing, structural visual chunk parsing, dynamic metadata classification, hybrid lexical/vector searching, and relational Text-to-SQL workflows are handled by specialized sub-agents coordinating through a centralized system registry.

---

## Technical Stack Architecture

| System Layer | Selected Technology |
|--------------|---------------------|
| Client App   | React + TypeScript + Vite + Tailwind CSS + shadcn/ui |
| Backend Core | Python + FastAPI + Uvicorn |
| Data Anchor  | Supabase (Auth + PostgreSQL + pgvector + RLS Security Mapping Tables, Client Mapping Tables) |
| Core AI SDK  | OpenRouter API (Accessing Gemini 2.5 Flash and etc.) |
| Visual Parse | Mistral OCR API Layer |
| Re-ranking   | Cohere Rerank API Layer |
| Web Intake   | Tavly Search API Layer |
| Observability| Langfuse SDK Tracing |

---

## Technical Scope

### In Scope
- ✅ Multi-Tenant Identity isolation managed rigidly via Supabase Row-Level Security (RLS).
- ✅ Asynchronous, fluent Server-Sent Events (SSE) streaming capable of pulsing both system `"thought"` steps and final content tokens down to the UI chat pane.
- ✅ Automated layout-aware text/visual transformation using Mistral OCR API for image heavy or visual PDFs.
- ✅ Smart De-duplication and delta tracking lifecycle pipelines using content-hash indexing.
- ✅ Automatic structural meta-tag extraction using structured LLM outputs mapped directly to JSONB criteria.
- ✅ Double-Pass Hybrid Retrieval matching Vector Cosine distances and Lexical Keyword lookups normalized by a Cohere Rerank layer.
- ✅ Specialized Text-to-SQL dynamic sub-agent tooling to interact safely with relational customer tables.
- ✅ Adaptive live internet search fallback triggers via Tavly API when local vector knowledge is verified absent.

### Out of Scope
- ❌ Hardcoded local indexing matrix math libraries running on CPU/GPU clusters locally.
- ❌ Independent standalone vector database instances external to the master Supabase stack (e.g., standalone Pinecone, Weaviate setups).
- ❌ Continuous third-party background cloud workspace integration scripts (Google Drive, Dropbox background polling watches).
- ❌ Subscription payment collection systems or access token metric usage-billing meters.

---

## Core System Constraints

- Handle API structures natively using clean Pydantic V2 schemas and runtime structures.
- Restrict folder structure blueprints to clear separation between client layout trees and service engine modules to preserve workspace scannability.
- All requests entering the database layer must pass through auth context filters verifying the active `user_id`.

---

## Core System Modules

### Module 1: Application Frame & Workspace Configuration
- **Deliverables:** Basic authenticated account setup frames via Supabase Auth client, core layout foundations, and clean configurations initializing global Async Client parameters.
- **Learning Focus:** Setting up asynchronous FastAPI routers, handling hidden environmental variables, and establishing structural instrumentation pipelines to Langfuse tracing layers.

### Module 2: Base Retrieval & Context Chat Foundations
- **Deliverables:** Primitive drag-and-drop file configuration card structures, local standard text layout ingesters, vector generation mechanisms via text-embedding engines, and strict ground instruction systemic layers.
- **Learning Focus:** Managing standard pgvector ingestion hooks, mapping database vector arrays, and coding basic vector similarity search queries.

### Module 3: Document Lifecycle & Hash Sync (去重與更新)
- **Deliverables:** Backend hash evaluation interceptors, clean file sync status dashboards, and automated pruning tasks.
- **Implementation:** Calculate an MD5 hash sequence from incoming data payloads. Check storage indexes for matches against `user_id` and `content_hash`. If a match hits, reject the upload or prune associated sub-chunks safely to avoid vector storage inflation.

### Module 4: Metadata Structure & Structural Auto-Filtering (元數據自動提取)
- **Deliverables:** Dropdown configuration panels in document UI interfaces, Pydantic extraction workflows, and dynamic metadata JSONB integration hooks.
- **Implementation:** Extract structural classification descriptors (title, summary, tags, language) automatically using structured LLM call patterns during processing. Save elements within chunk records to support multi-faceted targeted semantic filter hooks during chat.

### Module 5: Layout-Aware Ingestion via Mistral OCR (多格式解析)
- **Deliverables:** Dynamic document distribution channels to parse raw standard data vs unstructured binary formats like complex, visually heavy PDFs, charts, or images.
- **Implementation:** Process document visual formats through the Mistral OCR API layer to retain structural tables and layouts before layout splitting pipelines execute.

### Module 6: Hybrid Retrieval Matrix & Cohere Reranking (混合檢索與重排序)
- **Deliverables:** Advanced hybrid database search configurations combined via Reciprocal Rank Fusion (RRF), configuration toggle elements in client settings panels, and Cohere Rerank API processors.
- **Implementation:** Conduct double-pass queries: select candidate blocks via overlapping structural search metrics, run candidate texts through Cohere Rerank, and inject only the highest-scoring sections into the context sequence window.

### Module 7: Text-to-SQL Capabilities & Tavly Web Search (附加工具層)
- **Deliverables:** Relational customer mock tables, a read-only secure SQL parsing and isolation engine, and internet search tool routers.
- **Implementation:** Build secondary query execution structures allowing agents to safely query numbers from tables like `mock_sales`. If vector evaluation checks find context scarcity (distance scores < 0.3), switch execution routes automatically to Tavly Web Search.

### Module 8: Hierarchical Multi-Agent Orchestration & SSE Streams (子代理架構)
- **Deliverables:** An asynchronous Agent Supervisor state layer, nested reasoning visual component elements inside the chat interface pane, and SSE streaming pipeline routes.
- **Implementation:** Convert monolithic chat endpoints into an orchestrator design pattern where a supervisor evaluates requests and coordinates specialized tools (SQL Sub-Agent, Doc-RAG Sub-Agent, Search Sub-Agent). Reason traces are streamed as distinct `{"thought": "..."}` steps alongside output response tokens.

---

## Definition of Project Success

- ✅ responsive client interface panel updating real-time agent workflow status states fluently.
- ✅ Complete protection against document visibility bleed across separate identities.
- ✅ Zero dependency footprint wasted on complex monolithic framework abstractions.
- ✅ Clean execution proving proper code separation across all 8 modular targets.