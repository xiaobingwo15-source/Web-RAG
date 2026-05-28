# Masterclass Architecture Tracking Ledger

Use this progressive check-matrix to guide your technical environment helper assets as you assemble the FastAPI and Google ai studio API key layers.

## Tracking Key
- `[ ]` = Feature block unstarted
- `[-]` = Engine segment under construction / refactoring branch active
- `[x]` = Feature layer production-verified and running without exceptions

## Execution Modules Matrix

### Module 1: Frame Architecture & API Infrastructure Setup
- [x] Deploy client login configurations and tenant token capture steps using Supabase Auth
- [x] Build a sleek React dialogue grid layer utilizing Tailwind and shadcn/ui layouts
- [x] Initialize your async Python FastAPI backend environment running clean Pydantic parameter schemas
- [x] Wire core runtime model endpoint processors directly into Langfuse tracing tracks

### Module 2: Gemini Context Stores & Grounded Search Routing
- [x] Build file collection drop cards inside the client React dashboard space (DocumentUpload component with drag-and-drop)
- [x] Implement local pgvector RAG pipeline (text extraction, chunking, embedding, storage, similarity search)
- [x] Connect chat routes to inject retrieved context chunks during execution when RAG mode enabled
- [x] Thread management: sidebar thread list, CRUD endpoints, thread switching

### Module 3: Document Lifecycle & Hash Sync
- [x] MD5 content hash on upload to detect and reject duplicate documents (409 Conflict)
- [x] Sync status and chunk count tracking on document records
- [x] Migration 004: content_hash, sync_status, chunk_count columns

### Module 4: Metadata Auto-Extraction
- [x] Gemini-powered metadata extraction (title, summary, tags, language) during ingestion
- [x] JSONB metadata storage on documents and document_chunks tables
- [x] Filtered similarity search RPC with tag/language filters
- [x] Metadata display in document upload panel (tags, language badges)
- [x] Migration 005: metadata columns, GIN index, match_documents_filtered RPC

### Module 5: Layout-Aware Ingestion via Gemini Multimodal OCR
- [x] Gemini multimodal OCR service (PDF page images sent to Gemini for text extraction)
- [x] OCR routing in text_extractor (use_ocr flag)
- [x] OCR toggle checkbox in document upload UI
- [x] pdf2image dependency for PDF-to-image conversion

### Module 6: Hybrid Retrieval & Gemini Reranking
- [x] PostgreSQL full-text search (tsvector column, GIN index, search_chunks_fts RPC)
- [x] Hybrid search with Reciprocal Rank Fusion (hybrid_search RPC combining vector + FTS)
- [x] Gemini-based reranker service (structured output scoring)
- [x] Retrieval service with three modes: vector, fts, hybrid
- [x] Retrieval mode toggle in chat input UI
- [x] Migration 006: fts column, triggers, search_chunks_fts, hybrid_search RPCs

### Module 7: Text-to-SQL & Tavly Web Search
- [x] Mock sales data table with seed data
- [x] Read-only SQL execution engine with SELECT-only validation
- [x] Gemini-powered SQL generation from natural language
- [x] Tavly web search API integration
- [x] Tools router with /sql and /search endpoints
- [x] Migration 007: mock_sales table, table_schema_info view, exec_readonly_sql function

### Module 8: Hierarchical Multi-Agent Orchestration & SSE Streams
- [x] Agent Supervisor with intent routing (doc_rag, sql, web_search, general)
- [x] Doc-RAG sub-agent (wraps retrieval + Gemini chat)
- [x] SQL sub-agent (wraps SQL engine + Gemini summarization)
- [x] Web Search sub-agent (wraps Tavly + Gemini synthesis)
- [x] Thought-trace SSE streaming (type: thought/token/done events)
- [x] ThoughtTrace UI component (collapsible reasoning steps)
- [x] Agent traces table for persistence
- [x] Migration 008: agent_traces table with RLS

### Module 9: Qdrant Vector Migration & RAG Pipeline Fixes
- [x] Migrate from pgvector to Qdrant for vector storage (migration 015)
- [x] Qdrant client setup with `document_chunks` collection (768-dim, cosine)
- [x] Embedding via `gemini-embedding-001` (google-genai SDK)
- [x] Hybrid retrieval: Qdrant vector + Supabase FTS with RRF merge
- [x] LLM-based reranker service
- [x] Fix: Agent routing respects `use_documents` flag (doc_rag prioritized when enabled)
- [x] Fix: Hardcoded refusal when retrieval returns 0 chunks (LLM ignores system prompt)
- [x] Fix: Lowered similarity threshold from 0.3 to 0.1
- [x] Fix: Added diagnostic logging (print + logger) throughout retrieval pipeline
- [x] Fix: Stronger RAG system prompt for model compliance
- [x] Debug endpoint: `GET /api/documents/check-qdrant` to verify Qdrant indexing
- [ ] **NEXT: Verify retrieval actually returns chunks (check-qdrant endpoint)**
- [ ] **NEXT: End-to-end test — upload doc, ask question, confirm answer from document**

### Module 10: Public Landing Page & RAG Chat Widget
- [x] Landing page at `/` (public, no auth) with dark industrial PCB/manufacturing theme
- [x] Routing: `/` → LandingPage, `/dashboard` → ProtectedRoute + RoleRedirect (preserves old behavior)
- [x] Navbar: sticky nav with smooth-scroll anchor links (Solutions, Capabilities, Compliance, Support)
- [x] HeroSection: hero banner with "View Catalog" → #solutions, "Technical Specs" → #capabilities
- [x] ServicesSection: two PCBA product cards (Large Machine, Small Machine) with "Configure Component" and "Request Prototype" → #contact
- [x] CapabilitiesSection: technical capabilities showcase
- [x] ComplianceSection: certifications and standards
- [x] Footer: company info, navigation links, contact details with `id="contact"` anchor target
- [x] ChatWidget: floating FAB (bottom-right) → expandable chat panel with RAG streaming
- [x] Anonymous auth: `supabase.auth.signInAnonymously()` on first message, fallback to "Sign in to chat"
- [x] All non-functional buttons wired up: navbar links, hero CTAs, service buttons, footer anchors
- [x] Material Design 3 dark theme with crosshair-corner decorations and dot-grid background