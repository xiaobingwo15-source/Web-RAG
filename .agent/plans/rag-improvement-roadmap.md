# RAG System Improvement Roadmap (2026-06-11)

> Synthesized from 6 parallel research agents covering: agentic patterns, chunking, reranking, query understanding, evaluation, and production hardening.

---

## Executive Summary

Your system is already **well above average** — hybrid retrieval, HyDE, corrective RAG, multi-query expansion, groundedness checks, parent-child chunks, contextual retrieval, ReAct + plan-and-execute agents, Langfuse tracing, and RAGAS eval are all in place. The improvements below are ordered by **impact × (1/effort)** — the highest-ROI items first.

---

## Tier 1: High Impact, Low Effort (Do This Week)

### 1. Upgrade Cohere Rerank v3.5 → v4
- **What**: Drop-in replacement, same API, better accuracy
- **Why**: Direct quality improvement with zero code changes beyond model name
- **Files**: `backend/app/services/reranker.py`
- **Verification**: Run RAGAS eval before/after on golden dataset

### 2. Weighted RRF with Query Classification
- **What**: Replace equal-weight RRF with dynamic weights based on query type
  - Keyword queries (codes, error messages): `w_fts=0.7, w_vector=0.3`
  - Semantic queries (paraphrased questions): `w_vector=0.7, w_fts=0.3`
- **Why**: Current equal weighting underperforms for both extremes
- **Files**: `backend/app/services/retrieval.py`
- **Implementation**: Add lightweight query classifier (OOV ratio, length, exact-match indicators), parameterize RRF weights
- **Verification**: A/B test via Langfuse experiments on retrieval hit rate and MRR

### 3. RAG-Fusion Across Query Variants
- **What**: Apply RRF to merge results from multi-query expansion variants (currently just deduplicates)
- **Why**: Documents appearing in multiple variant result sets should rank higher
- **Files**: `backend/app/services/agents/doc_rag_agent.py`
- **Implementation**: After multi-query retrieval, apply RRF merge across variant results before dedup
- **Verification**: Compare retrieval quality with/without fusion on benchmark queries

### 4. Query Decomposition for Comparative Queries
- **What**: For "Compare X and Y" queries, decompose into separate sub-queries instead of just paraphrasing
- **Why**: Paraphrasing misses the decomposition opportunity; sub-queries retrieve more targeted context
- **Files**: `backend/app/services/agents/doc_rag_agent.py`
- **Implementation**: Extend multi-query expansion to detect comparative intent and generate decomposed sub-queries
- **Verification**: Test on comparative query examples from production logs

---

## Tier 2: High Impact, Medium Effort (Do This Month)

### 5. Redis Semantic Cache
- **What**: Replace in-memory dict with Redis Stack vector search
- **Why**: Current cache lost on restart, not shared across workers, uses crude MD5 bucket keys
- **Implementation**: Redis HNSW index on 768-dim embeddings, KNN 1 with cosine threshold 0.1-0.2, per-tenant scoping via payload filter
- **Config**: `M=16, EF_CONSTRUCTION=200, EF_RUNTIME=10-50, DIM=768`
- **Verification**: Cache hit rate, latency reduction, process restart survival

### 6. Step-Back Prompting in Query Expansion
- **What**: Add a "step-back" variant to expansion that generates a broader question for foundational context
- **Why**: Tested gains on reasoning tasks across GPT-4, PaLM, Llama2
- **Files**: `backend/app/services/agents/doc_rag_agent.py`
- **Implementation**: Add step-back prompt to expansion: "Before answering X, what broader context would help?"
- **Verification**: Compare answer quality on analytical/multi-hop queries

### 7. LLM-Based Complexity Classification
- **What**: Replace regex-based `classify_query_complexity` with LLM classifier
- **Why**: Regex is fast but limited; LLM can learn from retrieval performance data
- **Files**: `backend/app/services/agents/doc_rag_agent.py`
- **Implementation**: Use structured output (Pydantic) with DeepSeek to classify: simple/moderate/complex, route to appropriate retrieval depth
- **Verification**: Compare classification accuracy and end-to-end latency

### 8. Gemini Batch API for Ingestion Embeddings
- **What**: Use Google Batch API for document ingestion embeddings at 50% cost
- **Why**: Ingestion is async, batch fits naturally; query embeddings stay real-time
- **Files**: `backend/app/services/embeddings.py`, `backend/app/services/ingestion_worker.py`
- **Verification**: Cost comparison on same document set

### 9. Redis-Backed Circuit Breaker
- **What**: Move circuit breaker state to Redis for cross-process coordination
- **Why**: Current per-process state means one worker can't see another's failures
- **Files**: `backend/app/services/circuit_breaker.py`
- **Implementation**: `pybreaker` with `CircuitRedisStorage`, or custom Redis extension
- **Verification**: Trip breaker in one worker, verify others respect it

---

## Tier 3: Medium Impact, Medium Effort (Next Quarter)

### 10. Proposition-Based Child Chunks
- **What**: Decompose child chunks into atomic, self-contained factual propositions
- **Why**: Each proposition = one discrete fact with resolved references; significantly better retrieval precision
- **Files**: `backend/app/services/chunker.py`
- **Implementation**: LLM pass per child chunk to extract propositions, maintain parent-proposition mapping
- **Cost**: ~$1.02 per million tokens (one-time, during ingestion)
- **Verification**: RAGAS context precision/recall before/after

### 11. Cohere Rerank 4 + Cascade Reranking
- **What**: Add a second-stage reranker after Cohere for critical queries
- **Why**: Progressive refinement — Cohere for broad filtering, then deeper reranking on top-N
- **Files**: `backend/app/services/reranker.py`
- **Implementation**: Cohere v4 → top 10 → secondary reranker (Jina v3 or RankGPT) → top 3
- **Verification**: Compare answer quality on complex queries

### 12. Langfuse Online Evaluators
- **What**: Auto-score production traces for faithfulness and response relevancy (referenceless metrics)
- **Why**: Catches hallucination trends before users report them
- **Implementation**: Configure LLM-as-judge evaluators in Langfuse, sample N% of production traces
- **Verification**: Trend faithfulness scores over time, alert on drops

### 13. Feedback-Driven Test Case Promotion
- **What**: Negative feedback queries automatically enter RAGAS eval dataset
- **Why**: Creates a self-improving evaluation loop from real user failures
- **Files**: New service or hook on feedback endpoint
- **Verification**: Eval dataset grows from production failures, regression tests catch repeated issues

### 14. Qdrant Binary Quantization
- **What**: Enable binary quantization for 32x memory reduction, 40x speed
- **Why**: Free performance upgrade, no re-embedding needed
- **Implementation**: Add `on_disk=true` for originals, binary quantization for candidates, rescoring
- **Verification**: Latency and memory benchmarks before/after

---

## Tier 4: High Impact, High Effort (Strategic)

### 15. LightRAG / Knowledge Graph Integration
- **What**: Add entity-relationship extraction during ingestion, build lightweight KG alongside Qdrant vectors
- **Why**: Enables multi-hop reasoning, entity-centric queries, relationship queries across documents
- **Implementation**: LightRAG library with Qdrant backend, incremental updates via set merging
- **Verification**: Test on cross-document reasoning queries

### 16. Speculative RAG
- **What**: Small model generates multiple draft answers from different document subsets, large model verifies
- **Why**: 50% latency reduction, 13% accuracy improvement on benchmarks (ICLR 2025)
- **Verification**: Latency and accuracy comparison

### 17. Structured Document Partitioning (Docling)
- **What**: Replace plain text extraction with Docling for PDF processing
- **Why**: Preserves table structure, reading order, document hierarchy as lossless JSON
- **Files**: `backend/app/services/text_extractor.py`, `backend/app/services/pdf_parser.py`
- **Verification**: Test on PDFs with tables, compare chunk quality

### 18. Retrieval Quality Dashboard
- **What**: Query Supabase retrieval logs for avg chunk scores, hit rate, zero-result rate, fallback rate
- **Why**: Visibility into retrieval health over time
- **Implementation**: Admin page addition or separate dashboard
- **Verification**: Dashboard shows actionable metrics

---

## Already Implemented (No Action Needed)

| Capability | Status |
|-----------|--------|
| Contextual retrieval (breadcrumb prefixes) | ✅ Done |
| Parent-child chunk hierarchy | ✅ Done |
| Structure-aware + semantic chunking | ✅ Done |
| HyDE (Hypothetical Document Embeddings) | ✅ Done |
| Corrective RAG with web fallback | ✅ Done |
| Multi-query expansion (2 variants) | ✅ Done |
| Groundedness checks with retry | ✅ Done |
| Lost-in-the-middle chunk reordering | ✅ Done |
| LLM-based intent routing | ✅ Done |
| Conversational query rewriting | ✅ Done |
| Hybrid retrieval (vector + FTS + RRF) | ✅ Done |
| MMR diversification | ✅ Done |
| Circuit breaker with retry | ✅ Done |
| Langfuse tracing | ✅ Done |
| RAGAS eval pipeline | ✅ Done |
| User feedback collection | ✅ Done |

---

## Key Sources

- [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)
- [Adaptive-RAG (NAACL 2024)](https://arxiv.org/abs/2403.14403)
- [RAG-Fusion](https://arxiv.org/abs/2402.03367)
- [Speculative RAG (ICLR 2025)](https://arxiv.org/abs/2407.08223)
- [Dense X Retrieval (Propositions)](https://arxiv.org/abs/2312.06648)
- [LightRAG](https://github.com/HKUDS/LightRAG)
- [Cohere Rerank 4](https://cohere.com/blog/rerank-4)
- [Jina Reranker v3](https://jina.ai/reranker/)
- [Qdrant Hybrid Search](https://qdrant.tech/articles/hybrid-search/)
- [Qdrant Quantization](https://qdrant.tech/documentation/guides/quantization/)
- [Redis Vector Search](https://redis.io/docs/latest/develop/interact/search-and-query/advanced-concepts/vectors/)
- [Chroma Chunking Benchmarks](https://www.trychroma.com/research/evaluating-chunking)
- [RAGAS Documentation](https://docs.ragas.io/)
- [Langfuse Experiments](https://langfuse.com/docs/datasets)
