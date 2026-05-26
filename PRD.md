# Agentic RAG Masterclass - Product Requirements Document (PRD)

## What We Are Building

A decoupled, production-optimized RAG engine serving exactly two user surfaces:
1. **Chat Interaction Pane** (Default) — A clean workspace delivering context-grounded conversational messaging blocks.
2. **Data Processing Panel** — A workspace to drag-and-drop source knowledge data assets (PDFs, Markdown, text sheets) directly into cloud indexing zones.

This platform sidesteps complicated backend vector alignment frameworks. Instead, text chunk parsing, visual page ingestion, embedding transformation logic, and matching calculations are offloaded entirely to Google's cloud vector environments via the native Gemini File Search tool.

## Technical Scope

### In Scope
- ✅ Seamless upload pipelines feeding file inputs directly to Gemini File Search Stores
- ✅ Automated native text/visual extraction (Zero-setup scanning of visual content in PDFs)
- ✅ Standard text conversational completion mapping running over Google ai studio API key
- ✅ Strict context verification instruction layers (Anti-hallucination protective boundaries)
- ✅ Conversational log auditing and session management
- ✅ Multi-tenant identity security protected by Supabase Row-Level Security (RLS)
- ✅ Highly fluid, asynchronous Server-Sent Events (SSE) streaming chat lines
- ✅ Unified project folder distribution matching Python backend parameters with Vite client layouts

### Out of Scope
- ❌ Hardcoded local indexing vector math engines / manual character calculators
- ❌ Standalone data cluster indexes (Pinecone, Weaviate, or independent pgvector configuration)
- ❌ Continuous external automation fetch scripts (Google Workspace / Dropbox monitors)
- ❌ Cloud payment gateway or metric access metering layers

## Technical Stack Architecture

| System Layer | Selected Technology |
|--------------|---------------------|
| Client App   | React + TypeScript + Vite + Tailwind + shadcn/ui |
| Backend Core | Python + FastAPI + Uvicorn |
| Data Anchor  | Supabase (Auth + Client Mapping Tables) |
| Core AI Engine| `google-genai` Python library (Google ai studio API key) |
| Managed RAG  | Gemini Native File Search |
| Observability| LangSmith SDK Tracing |

## Core System Constraints

- No auxiliary framework structures. Handle interface data bindings natively using clean Pydantic routing.
- Lock all Supabase configurations down using multi-tenant user Row-Level Security parameters.
- Restrict folder file footprints to a clean structure to preserve workspace readability in any modern IDE platform.

---

## Module 1: Application Frame & Workspace Configuration

**Deliverables:** Basic authenticated account setup frames, clean frontend Chat View layouts, and live implementation routes initializing standard `genai.Client` references over FastAPI frameworks.

**Learning Focus:** Asynchronous FastAPI endpoint building, strict routing parameters for secret variables, and piping telemetry tracing layers to LangSmith.

---

## Module 2: Managed Cloud File Indexing & Grounded Chat

**Deliverables:** Drag-and-drop layout cards, backend handlers to route local incoming files into Gemini `file_search_stores`, asynchronous polling workers tracking document verification updates, and prompt configs embedding `file_search` parameters natively within conversational queries.

**Learning Focus:** Evaluating cloud-abstracted semantic indexing zones, processing mixed visual tabular data inside rich PDFs, and setting up strict programmatic fallbacks when source files do not contain an answer.

---

## Definition of Project Success

- ✅ A fully responsive, cohesive codebase integrating Python FastAPI with Google ai studio API key.
- ✅ Zero engineering debt spent optimizing matrix chunk offsets or running compute-expensive indexing routines locally.
- ✅ Impeccable verification layer execution ensuring user interactions are strictly limited to their own private knowledge stores.
- ✅ High competency instructing background developers to assemble, run, and optimize modern async network pipelines.