# RAG System Comprehensive Enhancement Plan

## Context

Based on a full-pipeline audit against the "正确四步法" framework, the RAG system scored:
- Step 1 Parsing: **70%** — PDF strong, missing DOCX/images
- Step 2 Structure: **35%** — **Biggest gap** — chunker metadata discarded before storage
- Step 3 Chunking+Index: **90%** — Industry-leading, minor tweaks only
- Step 4 Agent Tools: **45%** — Fixed pipeline, not true tool dispatch
- Closing Loop: **55%** — Good monitoring, missing citation/table eval

This plan covers **all dimensions** — not just code, but architecture, infrastructure, process, governance, and tooling.

---

## Phase 1: Foundation — Fix the Structural Metadata Leak (Step 2: 35% → 75%)

**Goal**: Stop throwing away what the chunker already computes.

### 1.1 Per-Chunk Metadata Persistence
- **What**: Extend `file_search_store.py` to pass `ChunkMetadata.heading`, `heading_level`, `chunk_type` (text/table/code/list) into both Supabase and Qdrant payloads.
- **Why**: The chunker computes all of this — it's just not stored. One fix unlocks page citation, table filtering, section-aware retrieval.
- **DB changes**: Add `heading TEXT`, `heading_level INT`, `structural_type TEXT` columns to `document_chunks` (Supabase migration). Add same fields to Qdrant payload schema.
- **Verification**: After ingestion, query Supabase for a chunk and confirm `heading` and `structural_type` are populated.

### 1.2 Page Number Extraction & Storage
- **What**: Parse `## Page N` markers during chunking to extract per-chunk page ranges. Store as `page_start INT`, `page_end INT` on each chunk.
- **Why**: Currently page info is baked into text but not queryable. This enables "what does page 5 say?" queries and page-level citations.
- **Implementation**: In `_parse_blocks`, detect `## Page N` heading pattern, track current page number, attach to subsequent chunks until next page marker.
- **Verification**: Query a chunk and confirm page range is correct by manual spot-check against the PDF.

### 1.3 Table ID Assignment
- **What**: Assign sequential `table_id` (e.g., `doc_abc_table_1`) to each table-type chunk during chunking.
- **Why**: Enables "retrieve all chunks from Table 3" queries and table-specific evaluation.
- **Verification**: Ingest a document with 3 tables, query Qdrant for `structural_type=table`, confirm 3 distinct table_ids.

### 1.4 Breadcrumb as Structured Field (Not Just Text)
- **What**: Keep the text-based breadcrumb for embedding quality, but also store `breadcrumb_path` as a structured JSON array `["Doc Title", "Chapter 2", "Section 2.3"]` in chunk metadata.
- **Why**: Enables section-filtered retrieval and structured citation generation.
- **Verification**: Query chunk metadata, confirm breadcrumb array is correct.

---

## Phase 2: Parsing Expansion (Step 1: 70% → 90%)

**Goal**: Cover the most common business document types.

### 2.1 DOCX Support
- **What**: Add `python-docx` extractor to `text_extractor.py`. Parse paragraphs, headings, tables (to markdown), and images (extract and store for potential OCR).
- **Why**: DOCX is the #1 business document format. Currently rejected with HTTP 415.
- **MIME**: `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- **Verification**: Upload a DOCX with headings, tables, and images. Confirm headings preserved, tables in markdown, text searchable.

### 2.2 Standalone Image OCR
- **What**: Allow PNG/JPG/TIFF upload. Route directly to the existing Gemini vision OCR service (bypass PDF rendering since image is already an image).
- **Why**: The OCR infrastructure exists — it's just not reachable for non-PDF inputs. Users photograph whiteboards, receipts, handwritten notes.
- **Verification**: Upload a PNG with text, confirm extracted text is searchable in Qdrant.

### 2.3 PPTX Support (Optional)
- **What**: Add `python-pptx` extractor. Extract slide text, notes, and table data.
- **Why**: Presentations are common in enterprise. Lower priority than DOCX/images.
- **Verification**: Upload a PPTX, confirm slide text is searchable.

### 2.4 Non-PDF Metadata Enrichment
- **What**: Return `TextExtractionResult.metadata` for all file types (not just PDF). For CSV: row count, column names. For Excel: sheet names, row counts. For DOCX: paragraph count, heading count.
- **Why**: Enables better document management in the admin UI.
- **Verification**: Upload CSV, check `metadata` dict is non-empty.

---

## Phase 3: Agent Architecture Overhaul (Step 4: 45% → 80%)

**Goal**: Move from fixed pipeline to true tool-based dispatch.

### 3.1 Formalize Tool Registry
- **What**: Extract the doc_rag_agent's inline capabilities into discrete, callable tools:
  - `search_chunks(query, filters)` — hybrid retrieval
  - `read_page(document_id, page_number)` — full page text retrieval
  - `extract_table(document_id, table_id)` — structured table data
  - `search_web(query)` — external web search
  - `get_document_metadata(document_id)` — doc-level info
- **Why**: Currently the agent always runs the full 12-step pipeline regardless of query type. Tool-based architecture lets the LLM choose only what's needed.
- **Verification**: A "what's in table 3?" query should call `extract_table` without running HyDE or web search.

### 3.2 Upgrade React Agent as Primary
- **What**: The `react_agent.py` already implements true tool-based reasoning (retrieve/web_search/generate/done). Promote it to the primary doc_rag route, with the current pipeline as a fallback.
- **Why**: The react agent lets the LLM reason about which tool to call at each step — this IS the "工具分工" pattern.
- **Router change**: Add `react` to the LLM classifier's known categories in `agent_supervisor.py`.
- **Verification**: Complex multi-hop query should show the agent calling search_chunks multiple times with refined queries.

### 3.3 Page-Level Retrieval Tool
- **What**: New tool that retrieves all chunks from a specific page of a document and assembles them in order.
- **Why**: Enables "read page 5" queries and precise page-level citations.
- **Prerequisite**: Phase 1.2 (page numbers stored per chunk).
- **Verification**: Ask "what's on page 3?", get coherent page content.

### 3.4 Table Extraction Tool
- **What**: New tool that retrieves all chunks belonging to a specific table_id and reconstructs the table structure.
- **Why**: Tables are currently scattered across chunks with no way to reassemble them.
- **Prerequisite**: Phase 1.3 (table IDs assigned).
- **Verification**: Ask "show me the sales table", get the full table in markdown.

### 3.5 Image Extraction Tool (Optional)
- **What**: During ingestion, extract images from PDFs/DOCX and store them separately. Tool retrieves images by page/document.
- **Why**: "Show me the diagram on page 3" is a valid query pattern.
- **Verification**: Upload a PDF with images, ask about a diagram, get the image.

---

## Phase 4: Citation & Evaluation Overhaul (Closing Loop: 55% → 85%)

**Goal**: Close the loop with precise citations and multi-dimensional evaluation.

### 4.1 Structured Citation Generation
- **What**: Instead of relying solely on the LLM to generate [1], [2] citations, build a post-processing step that:
  1. Parses the LLM's inline citations
  2. Maps each [N] to the actual source chunk
  3. Enriches with page number, section heading, table_id (from Phase 1 metadata)
  4. Returns structured citation objects: `{text: "...", source: "file.pdf", page: 5, section: "2.3 Revenue"}`
- **Why**: LLMs hallucinate citation mappings. Programmatic verification ensures accuracy.
- **Verification**: Ask a question, check that every [N] in the response maps to a real chunk with correct page/section.

### 4.2 Citation Accuracy Metric in Eval Pipeline
- **What**: New eval dimension: for each [N] in the generated answer, verify that the referenced chunk actually supports the claim. Score: % of citations correctly mapped.
- **Why**: Currently faithfulness checks grounding broadly but not per-citation correctness.
- **Verification**: Run eval suite, confirm citation_accuracy score appears in results.

### 4.3 Table Parsing Accuracy Metric
- **What**: New eval dimension: for questions about table data, compare extracted values against expected values. Score numerical accuracy, column/row correctness.
- **Why**: Tables are the highest-risk data type for hallucination (numbers get invented).
- **Verification**: Create eval cases with table-specific expected_facts, run eval, confirm table_accuracy score.

### 4.4 Deterministic Retrieval Recall
- **What**: Use `expected_document_id` (already in the eval model schema but unused) to compute recall@k: did the system retrieve the correct document?
- **Why**: LLM-judged context_recall is subjective. Deterministic recall@k is ground truth.
- **Verification**: Run eval with cases that have expected_document_id, confirm recall@k metric appears.

### 4.5 Per-Citation Page Reference in Answers
- **What**: System prompt change: instead of just `[1] (Source: filename.pdf)`, instruct LLM to generate `[1] (Source: filename.pdf, p.5, §2.3)` using the metadata now available from Phase 1.
- **Why**: Users need to verify claims against the original document. Page + section is the minimum viable citation.
- **Verification**: Ask a question about a specific section, confirm answer includes page/section references.

---

## Phase 5: Infrastructure & Performance

### 5.1 Semantic Cache with Invalidation
- **What**: The semantic cache exists but has no invalidation. Add document-level cache invalidation: when a document is re-ingested, purge all cached queries whose results included chunks from that document.
- **Why**: Stale cache returns outdated answers after document updates.
- **Verification**: Ingest doc A, query and cache result, re-ingest doc A with changes, query again, confirm fresh results.

### 5.2 Retrieval Latency Budget
- **What**: Set hard latency budgets per retrieval stage: embedding (500ms), Qdrant (300ms), FTS (300ms), rerank (500ms). Emit Langfuse spans for each. Alert when budget exceeded.
- **Why**: The quality signals track P95 latency but there's no per-stage breakdown or alerting.
- **Verification**: Run a query, check Langfuse traces show per-stage timing.

### 5.3 OCR Parallelization
- **What**: Process OCR pages concurrently (asyncio semaphore, max 5 concurrent). Currently sequential.
- **Why**: A 20-page scanned PDF takes 20× the single-page latency.
- **Verification**: Time a 10-page scanned PDF before and after, confirm speedup.

### 5.4 Embedding Batch Optimization
- **What**: Batch embedding requests (current `get_embeddings` already batches, but verify batch size aligns with API limits). Add retry with exponential backoff for rate limits.
- **Why**: Large document ingestion can hit Gemini rate limits.
- **Verification**: Ingest a 100-chunk document, confirm no rate limit errors.

---

## Phase 6: Governance & Process

### 6.1 Document Quality Scoring
- **What**: During ingestion, compute a quality score for each document: text extraction confidence, table detection count, OCR usage flag, page count, chunk count. Store on the `documents` row.
- **Why**: Admins need to know which documents are well-ingested vs problematic. A scanned PDF with poor OCR is lower quality than a native digital PDF.
- **Verification**: Upload mix of native/scanned PDFs, check quality scores differ appropriately.

### 6.2 Ingestion Health Dashboard
- **What**: Admin view showing: total documents, quality distribution, OCR usage rate, average chunks per doc, failed ingestions, stale documents (not updated in N days).
- **Why**: Currently no visibility into ingestion health across the tenant.
- **Verification**: Load admin page, see dashboard with real data.

### 6.3 Retrieval Quality Monitoring Dashboard
- **What**: Extend the existing quality signals into a visual dashboard: groundedness trend over time, zero-source rate, weak-source rate, latency P95, feedback ratio.
- **Why**: The 6 quality signals exist in code but have no visual representation.
- **Verification**: Load dashboard, see trend charts for each signal.

### 6.4 Eval Cadence Automation
- **What**: Scheduled eval run (weekly or after each document ingestion batch) that runs the eval suite and compares to baseline. Auto-alert if any metric drops >10%.
- **Why**: Currently eval is manual. Quality degrades silently as documents change.
- **Verification**: Trigger a scheduled eval, confirm results logged and comparison shown.

### 6.5 Document Re-Ingestion Workflow
- **What**: Admin can trigger re-ingestion of a document (e.g., after fixing OCR issues or updating the chunking strategy). Old chunks are replaced atomically.
- **Why**: Currently there's no way to re-process a document without deleting and re-uploading.
- **Verification**: Upload doc, trigger re-ingestion with different settings, confirm old chunks replaced.

---

## Phase 7: Advanced Capabilities (Future)

### 7.1 Multi-Modal RAG
- **What**: Extract images/charts from PDFs during ingestion, store them separately, embed image descriptions, enable "show me the chart" queries.
- **Why**: Manufacturing/technical docs are heavily visual. Current system is text-only.
- **Effort**: High — requires image storage, description generation, multi-modal retrieval.

### 7.2 Knowledge Graph Layer
- **What**: Extract entities and relationships from documents during ingestion. Store in a graph structure. Enable relationship queries ("what products use material X?").
- **Why**: Graph queries complement vector search for relationship-heavy domains.
- **Effort**: High — requires NER, relationship extraction, graph DB integration.

### 7.3 Conversational Memory with Document Awareness
- **What**: Track which documents/chunks were cited in a conversation. Use this to bias subsequent retrievals toward the same documents.
- **Why**: Follow-up queries often need the same document set. Current system re-retrieves from scratch.
- **Effort**: Medium — requires conversation-level document tracking in session state.

### 7.4 Self-Improving Retrieval Loop
- **What**: Use thumbs-up/thumbs-down feedback to fine-tune retrieval weights (RRF weights, reranker threshold, chunk size). Auto-adjust based on signal trends.
- **Why**: Currently feedback is collected but not used to improve retrieval.
- **Effort**: Medium — requires feedback signal → weight adjustment pipeline.

---

## Execution Priority Matrix

| Phase | Impact | Effort | Priority | Dependencies |
|-------|--------|--------|----------|--------------|
| 1.1 Per-Chunk Metadata | 🔴 Critical | Small | **P0** | None |
| 1.2 Page Numbers | 🔴 Critical | Small | **P0** | None |
| 1.3 Table IDs | 🟡 High | Small | **P0** | None |
| 1.4 Breadcrumb Structure | 🟡 High | Small | **P1** | None |
| 2.1 DOCX Support | 🟡 High | Medium | **P1** | None |
| 2.2 Image OCR | 🟡 High | Medium | **P1** | None |
| 4.1 Structured Citations | 🟡 High | Medium | **P1** | Phase 1 |
| 4.5 Page References in Answers | 🟡 High | Small | **P1** | Phase 1.2 |
| 3.1 Tool Registry | 🟡 High | Large | **P2** | None |
| 3.2 React Agent Upgrade | 🟡 High | Medium | **P2** | 3.1 |
| 3.3 Page-Level Retrieval | 🟡 High | Medium | **P2** | 1.2 |
| 3.4 Table Extraction Tool | 🟡 High | Medium | **P2** | 1.3 |
| 4.2 Citation Accuracy Eval | 🟡 High | Medium | **P2** | 4.1 |
| 4.3 Table Accuracy Eval | 🟡 High | Medium | **P2** | 1.3 |
| 4.4 Deterministic Recall | 🟢 Medium | Small | **P2** | None |
| 5.1 Cache Invalidation | 🟢 Medium | Medium | **P2** | None |
| 5.3 OCR Parallelization | 🟢 Medium | Small | **P2** | None |
| 6.1 Document Quality Score | 🟢 Medium | Small | **P2** | None |
| 6.4 Eval Automation | 🟢 Medium | Medium | **P3** | 4.2, 4.3 |
| 6.5 Re-Ingestion Workflow | 🟢 Medium | Medium | **P3** | None |
| 2.3 PPTX Support | 🟢 Low | Medium | **P3** | None |
| 3.5 Image Extraction | 🟢 Low | Large | **P3** | None |
| 7.x Advanced | Future | Large | **P4** | All above |

---

## Verification Plan

Each phase has inline verification steps. After each phase:
1. Run the full eval suite (`POST /api/eval/run`) to confirm no regression
2. Run the 6 quality signals check to confirm no new warnings
3. Manual spot-check: ingest a test document, query it, verify citations include page/section
4. Update the RAG wiki (`.agent/plans/rag-wiki.md`) with new capabilities

---

## Quick Wins (Can Do Today, < 2 hours each)

1. **Phase 1.1** — Pass `ChunkMetadata` to storage (10 lines in `file_search_store.py`)
2. **Phase 1.2** — Parse `## Page N` in chunker (20 lines in `chunker.py`)
3. **Phase 1.3** — Assign table_id (5 lines in `chunker.py`)
4. **Phase 4.5** — Update system prompt with page/section instruction (3 lines in `gemini.py`)

These 4 changes alone would move Step 2 from 35% → ~65% and Closing Loop from 55% → ~65%.
