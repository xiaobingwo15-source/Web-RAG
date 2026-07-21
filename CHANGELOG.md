# Changelog — Staging → Master

All notable changes from **Staging** branch merged into **master** via PRs #20–#44.
Commits span **2026-06-09** to **2026-07-18**.

---

## July 2026

### ✨ New Features

| Commit | Date | Description |
|--------|------|-------------|
| `569df61` | 2026-07-18 | **feat(chat): stream recovery, pipeline timeout, and retry UI** — Pipeline survives client disconnects; timeout guards; retry button in UI |
| `e729889` | 2026-07-16 | **feat(rag): HTTP client pooling, exact-query cache, latency sample guard** — Reusable HTTP clients; exact-match query caching; latency sampling safeguards |
| `e134ee3` | 2026-07-14 | **feat(feedback): harden feedback pipeline with validation, error handling, and admin review** — Thread/message ownership validation; error propagation; 503 retryable responses |
| `7dbd4ff` | 2026-07-10 | **feat(admin): quality inbox, source inspector, feedback comments, and audit logs** — Quality feedback review UI; document source inspection; comment threads; audit trail |

### 🐛 Bug Fixes

| Commit | Date | Description |
|--------|------|-------------|
| `cd25f58` | 2026-07-06 | **fix(rag): meta-query false positive on content queries** — Queries like "assignment instructions" no longer misclassified as meta-queries |

### 📝 Documentation

| Commit | Date | Description |
|--------|------|-------------|
| `a95a4f0` | 2026-07-01 | **docs(readme): update project description** — README updated with current RAG architecture; score_family carried in quality loop |

### 🧪 Testing

| Commit | Date | Description |
|--------|------|-------------|
| `c459440` | 2026-07-11 | **Strengthen core RAG test coverage** — Expanded test coverage for core RAG pipeline |

---

## June 2026

### ✨ New Features

| Commit | Date | Description |
|--------|------|-------------|
| `1a33e3e` | 2026-06-27 | **feat(rag): score-family-aware quality signals + widget policy + channel breakdown** — Quality signals distinguish score families; widget policy violations tracked; per-channel retrieval breakdown |
| `9976f4d` | 2026-06-24 | **feat(rag): query clarification mechanism** — Meta-query detection (bilingual EN+ZH); document inventory responses instead of hard refusals |
| `50d3e22` | 2026-06-22 | **feat(rag): CoVe/HyDE retry logic + fail-neutral guardrails + persistent streaming** — Groundedness retry loop (max 2); fail-neutral when exhausted; persistent streaming hardening |
| `4b3d85d` | 2026-06-19 | **feat(rag): persistent pipeline + early exit + upload hardening** — Background task continues after SSE disconnect; early exit on low fused scores; upload validation |
| `1fa0a49` | 2026-06-18 | **feat(rag): multi-layer grounding verification** — Claim decomposition, per-claim verification, CoVe, confidence scoring/routing, citation enforcement |
| `19ab364` | 2026-06-15 | **feat(rag): structural metadata, DOCX support, tool registry, eval metrics, security hardening** — Structure-aware chunking; DOCX ingestion; tool-based retrieval; new eval metrics; audit logging |
| `e26f7ee` | 2026-06-13 | **feat(rag): typo tolerance + confirm delete & bulk select** — Typo-tolerant query prompts; admin bulk document selection with confirm-delete dialog |
| `1286d7e` | 2026-06-13 | **feat(rag): quality signal improvements** — Data staleness detection; per-stage latency tracking; archive cleanup |
| `fad04c2` | 2026-06-13 | **feat(rag): quality-loop signals, diagnostics, eval drafts, landing redesign** — 8 quality health signals; diagnostics payload; auto-draft eval cases; landing page redesign |
| `2eab202` | 2026-06-11 | **feat(rag): Tier 1 improvements — weighted RRF, RAG-fusion, query decomposition** — Keyword vs semantic query classification; adaptive RRF weights; multi-query RAG-fusion |
| `b884ed3` | 2026-06-11 | **feat(upload): resilient chunked upload with resume** — Chunked upload with resume support; PDF page limits |
| `a6aab2d` | 2026-06-10 | **feat(ocr): upgrade to gemini-2.5-flash-lite** — OCR model upgrade with alias normalization |
| `c66bb4f` | 2026-06-09 | **feat(embeddings): add Jina embedding provider** — Jina v5-text-small support alongside Gemini |
| `73b3af3` | 2026-06-09 | **feat(rag): RAG wiki improvement roadmap — 9 gaps closed** — 9 retrieval quality improvements from wiki audit |
| `500df75` | 2026-06-09 | **feat(embeddings): local SentenceTransformers provider** — Self-hosted embedding option with dimension validation |

### 🐛 Bug Fixes

| Commit | Date | Description |
|--------|------|-------------|
| `6e82b8f` | 2026-06-24 | **fix(frontend): add 'clarifying' to ACTION_ICONS** — Fixed TS2741 build error; missing icon mapping for clarification action |
| `a151b28` | 2026-06-17 | **fix(rag): streaming indicator stuck + abbreviation expansion** — Streaming spinner no longer hangs; abbreviation expansion in query rewrite |
| `bba4e70` | 2026-06-17 | **fix(rag): bilingual regex, chunker separator, polling cleanup, realtime filter** — Bilingual regex patterns; chunker separator; stale polling; realtime subscription filter |
| `4827178` | 2026-06-13 | **fix(frontend): remove unused useEffect import** — Fixed Vercel build failure from unused import |
| `e19b366` | 2026-06-12 | **fix(rag): sync context_sources after web augmentation** — Source citations correctly attributed after web search augmentation |
| `df86829` | 2026-06-12 | **fix(reranker): revert to rerank-v3.5** — v4 model unavailable on Cohere; reverted to stable v3.5 |
| `e7105e3` | 2026-06-10 | **fix(ocr): use vision-capable model for PDF OCR** — Was using text-only model for image-based PDFs |
| `8dc3cce` | 2026-06-09 | **fix(embeddings): include API key in client cache key** — API key rotation no longer serves stale cached embeddings |

### ♻️ Refactoring

| Commit | Date | Description |
|--------|------|-------------|
| `43f6558` | 2026-06-26 | **refactor(rag): hoist retrieval_log_ids declaration** — Variable declared before conditional branch to avoid undefined reference |

### 🧹 Housekeeping

| Commit | Date | Description |
|--------|------|-------------|
| `9a8cfc9` | 2026-06-13 | **chore: remove .tmp/ from tracking** — Temporary files removed from version control; added to .gitignore |

---

## Summary

| Category | June | July | Total |
|----------|------|------|-------|
| ✨ **New Features** | 15 | 4 | **19** |
| 🐛 **Bug Fixes** | 8 | 1 | **9** |
| ♻️ **Refactoring** | 1 | 0 | **1** |
| 📝 **Documentation** | 0 | 1 | **1** |
| 🧹 **Housekeeping** | 1 | 0 | **1** |
| 🧪 **Testing** | 0 | 1 | **1** |
| **Total** | **25** | **7** | **35** |

| Metric | Value |
|--------|-------|
| **PRs merged** | 25 (#20–#44) |
| **Date range** | 2026-06-09 → 2026-07-18 |
