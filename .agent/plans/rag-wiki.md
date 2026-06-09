# RAG Engineering Wiki

A practical reference guide for building, evaluating, and operating production RAG systems.

---

## Table of Contents

1. [Seven Principles](#seven-principles)
2. [Recommended Pipeline Architecture](#recommended-pipeline-architecture)
3. [Evaluation Framework](#evaluation-framework)
4. [Chunking Best Practices](#chunking-best-practices)
5. [Retrieval Optimization](#retrieval-optimization)
6. [Production Engineering](#production-engineering)
7. [Anti-Patterns](#anti-patterns)
8. [Gap Analysis: Web-RAG System](#gap-analysis-web-rag-system)

---

## Seven Principles

### 1. 评测先行 (Evaluation First)

**"1 day labeling 30 eval samples > 1 week tuning parameters"** -- Hamel Husain

#### Why It Matters

Without ground-truth labels, you cannot distinguish signal from noise when changing chunk sizes, embedding models, or prompts. 30 well-labeled samples surface more actionable insights than weeks of vibes-based iteration.

The bottleneck is labeling, not tooling. Most teams spend 90% of effort on pipeline engineering and 10% on evaluation. Inverting this ratio produces compounding returns.

#### How to Implement

1. Generate synthetic Q&A from your corpus (RAGAS `TestsetGenerator` or DeepEval `Synthesizer`)
2. Domain expert validates and corrects 30-50 samples -- this is the "1 day" investment
3. Diversify question types: 50% simple factual, 25% reasoning, 25% multi-context
4. Store the eval set in version control (JSON/CSV) alongside code
5. Run the eval set before and after every pipeline change
6. Target: 50-100 samples minimum for statistical meaning; 200+ for production

#### Common Mistakes

- Testing on 10 queries (high variance, unreliable metrics)
- Only testing "happy path" queries (missing edge cases, typos, multilingual)
- Not separating retrieval and generation evaluation
- Changing multiple variables at once between eval runs
- Not feeding production failures back into the eval set as regression cases

#### Our System Status

Partially addressed. We have retrieval logging infrastructure and thumbs up/down feedback collection. We do NOT have a golden test set or automated eval pipeline. This is the highest-priority gap.

---

### 2. 从简单开始 (Start Simple)

Build a working baseline before adding sophistication. Each layer adds latency, cost, and failure surface.

#### Why It Matters

If basic vector search returns garbage, no amount of reranking will fix it. The progression order matters because each layer depends on the one before it.

**Progression order:**
1. Naive vector search with a single embedding model
2. Tune chunk size and overlap (often the biggest single improvement)
3. Add BM25/keyword search alongside vector search (hybrid retrieval)
4. Implement RRF to merge vector + keyword results
5. Add a cross-encoder reranker as a second stage
6. Layer query rewriting (multi-query, HyDE, follow-up context)
7. Add corrective RAG (retrieval grading + web search fallback)
8. Implement groundedness checking and self-correction loops

#### How to Implement

Before adding any new layer, measure recall@5 and precision@5 on a 20-query eval set. If the new layer does not improve those numbers (or a downstream metric like faithfulness), remove it.

#### Common Mistakes

- Adding HyDE + multi-query + reranking + corrective RAG all at once on an untested baseline
- Chasing model upgrades when retrieval is broken (the model is rarely the bottleneck)
- Building elaborate agentic orchestration before basic retrieval works

#### Our System Status

We built up incrementally (vector search -> hybrid -> RRF -> reranker -> HyDE -> corrective RAG), which is the right approach. However, we added layers without measuring each one's individual contribution. We lack baseline metrics to know which layers are actually helping.

---

### 3. 保留结构信息 (Preserve Structure)

Naive fixed-size splitting destroys semantic signals. Documents have logical structure -- headings, tables, code blocks, lists -- that carries meaning.

#### Why It Matters

- **Semantic fragmentation**: "Revenue grew 3%" without specifying which company or quarter is both hard to retrieve and useless when retrieved
- **Cross-reference breakage**: Pronouns and references ("it", "the above section", "as shown in Table 3") lose their antecedents
- **Heading misattribution**: A chunk about "exception handling" under "Database Layer" means something different than under "API Layer"
- **Table destruction**: Rows separated from headers become meaningless number grids

#### How to Implement

**Structure-aware splitting (baseline):**
- Parse document into structural blocks (headings, tables, code, lists, text)
- Never split atomic blocks (tables, code) mid-block
- New heading always starts a new chunk
- Text blocks use sliding-window with paragraph/sentence boundary detection

**Breadcrumb path augmentation:**
- Prefix each chunk with its full heading hierarchy: `Document > Chapter 3 > Section 3.2`
- Prepend inline before embedding so the vector carries structural context
- Benchmark: 35% reduction in retrieval failure rate (Anthropic contextual embeddings)

**Parent-child chunking:**
- Small child chunks (500 chars) for retrieval precision
- Large parent chunks (1500 chars) for context breadth
- Retrieve against children, return parents to LLM

#### Common Mistakes

- Splitting tables across chunks (numeric data becomes meaningless)
- Splitting code blocks mid-function
- Losing heading context in downstream chunks
- Using chunk-level dedup that collapses useful distinct chunks from the same parent

#### Our System Status

Well implemented. We have structure-aware splitting (`_parse_blocks`, `_chunk_blocks`), semantic chunking (`semantic_chunk_text`), and parent-child chunking (`create_parent_child_chunks`, 1500/500 chars). Heading metadata is tracked but not prepended inline before embedding (a potential improvement).

---

### 4. 双通道互补 (Dual-Channel Complementary)

Dense (vector) and sparse (BM25/FTS) retrieval have uncorrelated failure patterns. Combining them recovers documents that either channel alone would miss.

#### Why It Matters

| Aspect | Sparse (BM25/FTS) | Dense (Vector) |
|---|---|---|
| Excels at | Exact keywords, rare terms, acronyms, product codes | Semantic similarity, paraphrases, synonyms |
| Fails on | Vocabulary mismatch, synonymy | Rare/out-of-domain terms, proper nouns, misspellings |

The dual-channel complementary principle: because the two channels project into orthogonal signal spaces, 1 + 1 > 1 in hybrid retrieval.

**Benchmarks:**
- MS MARCO: +10-30% MAP improvement over either method alone
- Typical production RAG: BM25-only ~70-75% hit rate, Vector-only ~75-80%, Hybrid ~85-90%
- Adding a cross-encoder reranker after hybrid provides an additional +5-10%

#### How to Implement

**Parallel search (critical for latency):**
```python
import concurrent.futures

def hybrid_search(query: str, top_k: int = 50):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        fts_future = executor.submit(fts_search, query, top_k)
        vector_future = executor.submit(vector_search, query, top_k)
        fts_results = fts_future.result()
        vector_results = vector_future.result()
    return reciprocal_rank_fusion([fts_results, vector_results], k=60)
```

Latency = max(FTS_latency, vector_latency), not the sum.

**RRF formula:**
```
RRF_score(d) = sum over all sources i of: 1 / (k + rank_i(d))
```
k=60 is the de facto industry standard (Cormack et al., SIGIR 2009).

#### Common Mistakes

- Averaging raw scores from BM25 and vector search (scale mismatch)
- Running retrievers sequentially instead of in parallel (doubles latency)
- Deduplicating before fusion (loses the signal that both channels ranked a doc highly)
- Not tracking retrieval provenance (cannot debug which channel contributed what)

#### Our System Status

Fully implemented. We run parallel Qdrant vector search + Supabase FTS, merged via RRF with k=60. Deduplication uses content-prefix matching (first 200 chars) after fusion. This is the industry-standard pattern.

---

### 5. Rerank 是性价比最高的优化 (Rerank = Highest ROI)

Cross-encoder reranking is the single highest-ROI quality improvement after basic hybrid retrieval is in place.

#### Why It Matters

Cross-encoders process query + document as a single input with deep token-level interaction, unlike bi-encoders that encode them independently. This gives superior precision at the cost of speed.

**Benchmark ranges:**
- Weak baseline (naive vector search): +10-15% MRR@10
- Moderate baseline (hybrid search, good embeddings): +5-8% MRR@10
- Strong baseline (fine-tuned embeddings, hybrid+RRF): +2-5% MRR@10

**Anthropic's Contextual Retrieval finding:** Adding reranking on top of contextual embeddings + contextual BM25 achieved a 67% reduction in retrieval failure rate (5.7% to 1.9%).

The standard 2025 pipeline: BM25 + Vector -> RRF -> Top-K -> Reranker -> LLM context.

#### How to Implement

**Position in pipeline:** After hybrid retrieval merge, before final context assembly. Operates on the merged candidate set (20-100 chunks), reorders by true semantic relevance, returns top-N to LLM.

**Candidate count sweet spot:** Rerank 30-50, return top 5-10. Beyond 50 candidates, latency grows linearly but accuracy gains plateau.

**Model options:**

| Model | Type | Multilingual | Latency (top-20) | Cost |
|---|---|---|---|---|
| Cohere rerank-v3.5 | API | 100+ languages | 50-200ms | ~$0.002-0.004/query |
| bge-reranker-v2-m3 | Local | 100+ languages | 50-150ms (GPU) | GPU compute only |
| ms-marco-MiniLM-L-12-v2 | Local | English-focused | 20-50ms (GPU) | GPU compute only |

**Fallback when reranker unavailable:**
- Current: keyword overlap scorer (stop-word removal + term overlap ratio)
- Better: re-sort by original Qdrant vector similarity scores (already available but may not be passed through pipeline)

#### Common Mistakes

- Not having a fallback when the reranker API is down
- Reranking too few candidates (top-5 -> top-5 is pointless)
- Reranking too many candidates (top-200 adds latency with minimal gain)
- Applying reranking before parent resolution (should be after)

#### Our System Status

Fully implemented. We use Cohere rerank-v3.5 with keyword-overlap fallback. The pipeline correctly positions reranking after RRF merge and before parent resolution.

---

### 6. 少即是多 (Less Is More)

More retrieved candidates and more context often degrade answer quality. Precision matters more than recall.

#### Why It Matters

**Lost in the Middle (Liu et al., 2023):** LLMs pay more attention to information at the beginning and end of context, underweighting the middle. More chunks means more critical information buried where the LLM ignores it.

**Diminishing returns:** After 3-5 well-chosen chunks, additional content adds noise rather than signal. Context window size does not equal context utilization -- a 128K window does not mean 128K tokens of effective attention.

#### How to Implement

- Start with top-k = 5. Only increase if eval shows improvement.
- After reranking, keep only the top 3-5 results for the LLM context.
- Use similarity score thresholds to filter low-quality matches.
- If context window is more than 50% full with retrieved content, you are probably stuffing too much.
- Place most relevant chunks at the beginning and end of the injected context (mitigates Lost-in-the-Middle).

**Optimal pipeline:**
```
Retrieve broadly (top 20-50 candidates)
  -> Rerank (cross-encoder, top 50 -> top 20)
    -> Parent resolution (replace children with parents)
      -> Inject top 3-5 highest-quality parent chunks into LLM
```

#### Common Mistakes

- Cramming 15-20 chunks into the context window
- Increasing top-k without measuring impact on faithfulness
- Not using similarity thresholds to filter low-quality matches
- Assuming a larger context window solves the problem

#### Our System Status

Partially addressed. We retrieve broadly and rerank, but we do not explicitly implement Lost-in-the-Middle mitigation (ordering chunks by relevance at start/end). We also lack dynamic top-k -- the number of chunks injected may not be optimized per query type.

---

### 7. 记录每一次实验 (Record Every Experiment)

RAG systems have many tunable parameters. Without systematic tracking, you cannot reproduce successes or learn from failures.

#### Why It Matters

Knowing that "increasing top-k from 5 to 15 reduced faithfulness by 12%" is as valuable as knowing that "adding a reranker improved it by 8%." Negative results prevent repeating failed experiments.

#### How to Implement

**What to version:**
- Chunking strategy (size, overlap, method)
- Embedding model and dimensions
- Retrieval parameters (top-k, similarity threshold, hybrid weights)
- Reranker model and configuration
- Prompt templates (exact text, not just "the RAG prompt")
- LLM model and temperature
- Evaluation dataset (the exact queries used for benchmarking)

**How to record:**
- Every experiment gets a unique ID tied to a git commit hash
- Log: experiment ID, parameters changed, eval metrics before and after, qualitative notes
- Use structured experiment tracking (W&B, MLflow, LangSmith, or a markdown table in the repo)
- Keep a "changelog of improvements" -- what worked, what did not, and why

#### Common Mistakes

- Changing a parameter, seeing no improvement, and not recording it
- Changing the prompt in production without versioning it
- Not tying experiments to specific git commits
- Only recording positive results

#### Our System Status

Not implemented. We have no experiment tracking infrastructure. Changes are made ad-hoc without systematic measurement or recording. This is a significant gap.

---

## Recommended Pipeline Architecture

### Standard Production RAG Pipeline (2025)

```
                                    +-----------------+
                                    |   User Query    |
                                    +--------+--------+
                                             |
                                    +--------v--------+
                                    | Query Rewriting  |
                                    | (follow-up ctx)  |
                                    +--------+--------+
                                             |
                                    +--------v--------+
                                    | Multi-Query      |
                                    | Expansion (3x)   |
                                    +--------+--------+
                                             |
                              +--------------+--------------+
                              |                             |
                     +--------v--------+           +-------v---------+
                     | Qdrant Vector    |           | Supabase FTS    |
                     | Search (dense)   |           | (sparse/BM25)   |
                     +--------+--------+           +-------+---------+
                              |                             |
                              +--------------+--------------+
                                             |
                                    +--------v--------+
                                    | Reciprocal Rank  |
                                    | Fusion (k=60)    |
                                    +--------+--------+
                                             |
                                    +--------v--------+
                                    | Cross-Encoder    |
                                    | Reranker         |
                                    | (Cohere v3.5)    |
                                    +--------+--------+
                                             |
                                    +--------v--------+
                                    | Parent Resolution|
                                    | (child -> parent)|
                                    +--------+--------+
                                             |
                                    +--------v--------+
                                    | Context Assembly |
                                    | (top 3-5 chunks) |
                                    +--------+--------+
                                             |
                                    +--------v--------+
                                    | LLM Generation   |
                                    | (with citations) |
                                    +--------+--------+
                                             |
                              +--------------+--------------+
                              |                             |
                     +--------v--------+           +-------v---------+
                     | Groundedness     |           | Return Answer   |
                     | Check            |           | + Sources       |
                     +--------+--------+           +-----------------+
                              |
                     +--------v--------+
                     | Retry or Refuse  |
                     +-----------------+
```

### With Corrective RAG (Web Fallback)

```
After retrieval grading:
  -> Relevant docs found: proceed with standard pipeline
  -> No relevant docs: trigger web search fallback
  -> Ambiguous: augment docs with web search results
  -> Generate with CORRECTIVE_RAG_SYSTEM_PROMPT
  -> Groundedness check -> retry if low score -> refuse if still low
```

---

## Evaluation Framework

### Metrics

#### Retrieval Metrics (did we fetch the right chunks?)

| Metric | Definition | When to Use |
|--------|-----------|-------------|
| **Recall@K** | Fraction of relevant documents retrieved in top-K | Core metric for "are we missing things?" |
| **Precision@K** | Fraction of retrieved documents that are relevant | Measures noise in retrieved set |
| **MRR** | Average of 1/rank of first relevant result | When position of first correct result matters |
| **NDCG@K** | Ranking quality with graded relevance | When relevance is not binary |

#### Generation Metrics (did the LLM use the context correctly?)

| Metric | Definition | Framework |
|--------|-----------|-----------|
| **Faithfulness** | Every claim grounded in retrieved context? | RAGAS, DeepEval |
| **Answer Relevancy** | Does the answer address the question? | RAGAS |
| **Context Precision** | Are retrieved chunks mostly relevant? | RAGAS |
| **Context Recall** | Did retrieval capture all needed information? | RAGAS |
| **Hallucination Rate** | % of claims unsupported by context | DeepEval, TruLens |

#### The Diagnostic Decision Tree

```
Poor Answer Quality
+-- Low Context Recall/Precision --> RETRIEVAL problem
|   +-- Improve chunking strategy
|   +-- Tune embedding model
|   +-- Add metadata filtering
|   +-- Hybrid search (dense + sparse)
|   +-- Re-ranking
|
+-- High Context Recall, Low Faithfulness --> GENERATION problem
    +-- Better prompting (instructions, few-shot)
    +-- Smaller context windows (reduce noise)
    +-- Citation enforcement
    +-- Use a stronger LLM
```

### Building Evaluation Datasets

**Phase 1: Synthetic Generation**
- Use RAGAS `TestsetGenerator` to auto-generate questions from your corpus
- Diversify: simple factual (50%), reasoning (25%), multi-context (25%)

**Phase 2: Human Validation (critical)**
- Domain expert reviews and corrects synthetic Q&A pairs
- Fix wrong ground-truth answers, remove trivial questions, add edge cases
- 30 validated samples beat 300 unvalidated ones

**Phase 3: Living Dataset**
- Version-controlled alongside code
- Add regression cases from every production failure
- Segment by difficulty: easy/factual, moderate/reasoning, hard/multi-hop

### Evaluation Workflow

```
1. BUILD EVAL SET (Week 1)
   +-- Generate synthetic Q&A from corpus
   +-- Domain expert validates 30-50 samples
   +-- Store in version control

2. BASELINE MEASUREMENT
   +-- Run eval set against current pipeline
   +-- Record all metrics
   +-- This is your baseline

3. DIAGNOSE
   +-- Low retrieval metrics --> retrieval optimization
   +-- Low generation metrics --> generation optimization
   +-- Low both --> retrieval first

4. ITERATE
   +-- Change ONE thing
   +-- Run eval set again
   +-- Compare to baseline
   +-- Keep if improved, revert if not

5. AUTOMATE
   +-- Integrate eval into CI/CD
   +-- Run eval set on every pipeline change
   +-- Alert on metric regressions
```

### Framework Comparison

| Framework | Strengths | Weaknesses |
|-----------|-----------|------------|
| **RAGAS** | Standard metrics, synthetic testset generation, LLM-agnostic | API changes frequently |
| **DeepEval** | CI/CD native (pytest integration), 14+ metrics | Newer, smaller community |
| **LangSmith** | End-to-end tracing + eval | Proprietary, vendor lock-in |
| **TruLens** | "RAG triad" feedback functions | Less synthetic data support |

**Recommendation:** RAGAS aligns with this project's no-vendor-lock-in philosophy.

---

## Chunking Best Practices

### Strategy Ranking (by sophistication)

**Level 1: Structure-Aware Splitting (Baseline)**
- Parse into structural blocks, never split atomic blocks (tables, code)
- New heading starts new chunk
- Text blocks use sliding-window with boundary detection

**Level 2: Breadcrumb Path Augmentation**
- Prefix each chunk with heading hierarchy before embedding
- `Financial Report > Q3 2024 > Revenue Analysis: Revenue grew 3%`
- 35% reduction in retrieval failure rate (Anthropic)

**Level 3: Semantic Chunking**
- Use embedding similarity between consecutive sentences to detect topic shifts
- Break where cosine similarity drops below threshold (e.g., 0.75)

**Level 4: Parent-Child (Hierarchical)**
- Small children (500 chars) for retrieval precision
- Large parents (1500 chars) for context breadth
- Retrieve against children, return parents to LLM

**Level 5: Late Chunking (Jina AI)**
- Embed full document first, then apply chunk boundaries
- Each chunk embedding conditioned on full document context
- Requires long-context embedding models (8K+ tokens)
- Benchmark: 23.46% -> 29.98% on NFCorpus

### Chunk Injection Guidelines

- **Ordering:** Place most relevant chunks at beginning and end (mitigates Lost-in-the-Middle)
- **Formatting:** Prefix each chunk with source metadata: `[1] (filename.pdf) content...`
- **Volume:** 3-5 chunks for factual queries, up to 10-15 for comparative queries
- **Deduplication:** By content prefix (first 200 chars), after fusion, not before

---

## Retrieval Optimization

### Hybrid Search + RRF

The default for production RAG. Use when queries mix natural language with specific terms.

```
RRF_score(d) = sum over all sources i of: 1 / (k + rank_i(d))
```

k=60 is the industry standard. Robust in range 30-100.

**Weighted variant** for domain-specific tuning:
```
Weighted_RRF_score(d) = w_fts / (k + rank_fts(d)) + w_vector / (k + rank_vector(d))
```

### Query Expansion Techniques

**Multi-query expansion:**
- Generate 2-3 reformulations of the original query
- Retrieve for each variant, merge with RRF
- Captures different phrasings and sub-questions
- Always safe, low risk, moderate improvement

**HyDE (Hypothetical Document Embeddings):**
- Generate a hypothetical answer, embed that for retrieval
- The hypothetical document is closer in embedding space to actual documents
- Strong for factual queries, risky for ambiguous queries
- Adds one LLM call per query

**Follow-up context rewriting:**
- Rewrite follow-up queries to be self-contained
- "What about pricing?" becomes "What is the pricing for [product discussed]?"
- Essential for any multi-turn chat system

### Reranking Configuration

**Optimal candidate count:** Rerank 30-50, return top 5-10.

**When reranking helps most:**
- Large corpus (100K+ documents)
- Ambiguous, multi-faceted queries
- Domain requires high precision (legal, medical, financial)
- General-purpose embeddings (not domain-tuned)

**When reranking is redundant:**
- Small corpus (few hundred documents)
- Domain-specific fine-tuned embeddings
- First-stage recall@10 already >90%
- Extremely tight latency budget (<200ms total)

---

## Production Engineering

### Observability Checklist

#### Per-Query Logging

| Category | What to Log | Why |
|---|---|---|
| **Input** | Original query, rewritten queries, conversation history | Debug retrieval misses |
| **Retrieval** | Candidate count, similarity scores, source documents | Assess retrieval quality |
| **Reranking** | Pre/post rerank order, reranker scores | Verify reranker value |
| **Context** | Final chunks sent to LLM, total token count | Detect context stuffing |
| **Generation** | Full response, model, temperature, token counts | Reproduce outputs |
| **Groundedness** | Score, flagged unsupported claims | Monitor hallucination |
| **Routing** | Agent/tool used, fallback triggers | Understand behavior |
| **Feedback** | Thumbs up/down, corrections | Ground truth |
| **Latency** | Time per stage (embedding, retrieval, reranking, generation) | Find bottlenecks |

#### Aggregate Metrics (Weekly Review)

| Metric | Target | Action if Below |
|---|---|---|
| Retrieval hit rate (relevant in top-5) | >80% | Tune chunking, embeddings, hybrid search |
| Groundedness score (average) | >0.85 | Improve prompts, add groundedness retry |
| User satisfaction (thumbs up rate) | >75% | Analyze negative cases |
| P95 latency | <5s | Optimize slowest stage |
| Hallucination rate | <5% | Strengthen groundedness checks |
| Fallback rate (web search triggered) | <20% | If too high, corpus coverage insufficient |

### Cost Optimization

**Per-query cost breakdown (typical production RAG):**
1. Query rewriting (1 LLM call)
2. Multi-query expansion (1 LLM call)
3. HyDE (1 LLM call, optional)
4. Embedding generation (1-4 calls)
5. Vector search + FTS (2 DB queries)
6. Reranking (1 API call)
7. Answer generation (1 LLM call)

Total: 4-7 API calls per query.

**Biggest savings:**
- Eliminate HyDE for simple queries (save 1 LLM call)
- Cache embeddings for repeated queries
- Use local embedding models (eliminate embedding API calls)
- Query routing to skip unnecessary steps
- Prompt caching (Anthropic/Google cache repeated prefixes)

### Scaling Considerations

**At 10K+ documents:** Need structured retrieval (metadata filters, document hierarchies). Embedding costs become noticeable.

**At 100K+ documents:** HNSW index recall degrades without tuning. Memory: 768-dim x 100K docs = ~300MB RAM. Index staleness becomes real.

**At 1M+ documents:** Re-embedding entire corpus for model upgrade is prohibitively expensive. Plan for embedding versioning. Metadata filtering + vector search can degrade to brute-force.

### Multi-Tenant Isolation

**Qdrant patterns:**
- Payload-based filtering: add `tenant_id` to each point's payload, filter at query time
- Collection-per-tenant: strongest isolation, highest overhead
- Hybrid: shared collection for small tenants, dedicated for large ones

**Critical:** Missing a tenant filter once means cross-tenant data leakage. Use middleware that auto-injects filters.

---

## Anti-Patterns

### Over-Chunking
Breaking documents into too-small chunks (under 200 chars) loses semantic coherence. A chunk that says "The voltage is" without the value is useless.

### Context Stuffing
Cramming 15-20 chunks into the context window. The LLM will ignore most of them (lost in the middle) or synthesize across irrelevant chunks.

### Blind Retrieval Trust
Passing retrieved documents directly to the LLM without any relevance check. If 3 of 5 documents are irrelevant, the LLM will still try to use them.

### Static-Only Retrieval
Relying exclusively on a fixed corpus without external augmentation. Real-world queries often need information not in your documents.

### Prompt Template Drift
Changing the prompt in production without versioning it. If performance degrades, you cannot roll back.

### No Evaluation Dataset
Optimizing retrieval or generation without a fixed set of test queries. Without this, you are guessing.

### Over-Reliance on Embedding Similarity
Assuming high cosine similarity means high relevance. A chunk about "bank interest rates" may score highly against a query about "river bank erosion." Reranking exists because embedding similarity alone is insufficient.

### Changing Multiple Variables
When optimizing, change one thing per eval run. Otherwise you cannot attribute metric changes to specific modifications.

### Ignoring Negative Results
Not recording experiments that failed. Two months later, someone makes the same change and wastes the same time.

---

## Gap Analysis: Web-RAG System

### What We Already Do Well

| Feature | Status | Notes |
|---|---|---|
| Hybrid retrieval (vector + FTS) | Implemented | Qdrant + Supabase FTS, parallel execution |
| RRF fusion (k=60) | Implemented | Industry-standard configuration |
| Cross-encoder reranking | Implemented | Cohere rerank-v3.5 with keyword-overlap fallback |
| Parent-child chunking | Implemented | 1500-char parents, 500-char children |
| Structure-aware splitting | Implemented | `_parse_blocks`, `_chunk_blocks` in chunker.py |
| Semantic chunking | Implemented | `semantic_chunk_text` with embedding similarity |
| Multi-query expansion | Implemented | 3 query variants |
| HyDE | Implemented | Hypothetical document embeddings |
| Corrective RAG | Implemented | Web search fallback when docs insufficient |
| Query rewriting | Implemented | Follow-up context for multi-turn |
| Metadata extraction | Implemented | Title, summary, tags, language |
| Language-aware prompts | Implemented | Match user language, no fabricated translations |
| Source citation | Implemented | `[N] (Source: filename) content...` format |
| Retrieval logging | Implemented | Supabase logs + thumbs up/down feedback |
| Observability | Implemented | Langfuse tracing |

### What We Should Improve (Priority-Ordered)

| Priority | Gap | Impact | Effort |
|---|---|---|---|
| **1** | Golden evaluation dataset (30-50 validated samples) | Enables all subsequent optimization | 1 day |
| **2** | Automated eval pipeline (RAGAS metrics in CI/CD) | Catches regressions before deployment | 2-3 days |
| **3** | Experiment tracking (versioned parameters + metrics) | Reproducibility, prevents repeated failures | 1-2 days |
| **4** | Breadcrumb path augmentation (prepend heading hierarchy before embedding) | 35% retrieval failure reduction per Anthropic | 1 day |
| **5** | Lost-in-the-Middle mitigation (chunk ordering by relevance) | Better LLM attention to critical chunks | 0.5 days |
| **6** | Dynamic top-k (fewer chunks for simple queries) | Reduced noise, lower cost | 1 day |
| **7** | Reranker fallback improvement (vector score re-sort vs keyword overlap) | Better quality when Cohere is unavailable | 0.5 days |
| **8** | Per-query latency logging by stage | Identify bottlenecks systematically | 1 day |
| **9** | Semantic caching for repeated queries | Cost reduction for similar queries | 2-3 days |
| **10** | Contextual retrieval (LLM-generated context prefix per chunk) | Further retrieval improvement beyond breadcrumbs | 2-3 days |

### Pre-Work Verification Checklist

**Before starting any improvement, verify the current state.** Many features partially exist or were added after this wiki was written. Don't rebuild what's already there.

#### How to Use This Checklist

For each gap you plan to work on, run through the verification steps below. If the feature already exists, mark it as ✅ and skip or adjust scope. If partial, note what's missing and only build the delta.

---

#### Gap 1: Golden Evaluation Dataset

| Check | File/Location | What to Look For |
|---|---|---|
| Eval test set exists? | `backend/app/services/eval_pipeline.py` | `EvalTestSet` dataclass, `create_golden_test_set()` function |
| Eval API endpoints? | `backend/app/routers/eval.py` | `POST /api/eval/generate-test-set`, `POST /api/eval/run` |
| Eval persistence? | `backend/app/services/eval_pipeline.py` | `save_eval_run()`, `save_eval_test_set()`, `list_eval_runs()` |
| Supabase tables? | Supabase MCP → `list_tables` | `eval_runs`, `eval_results`, `eval_test_sets` tables |
| Manual test cases? | `backend/app/services/rag_eval.py` | `run_rag_eval()` with `EvalScore` dataclass |

**Status:** Eval infrastructure EXISTS (LLM-as-judge with 4 RAGAS-style metrics, API endpoints, persistence). What's MISSING is a validated golden test set — the `create_golden_test_set()` generates synthetic Q&A but no human-validated set is stored. **Action: generate + validate 30-50 samples, store in version control.**

---

#### Gap 2: Automated Eval Pipeline (CI/CD)

| Check | File/Location | What to Look For |
|---|---|---|
| Eval run endpoint? | `backend/app/routers/eval.py` | `POST /api/eval/run` accepts `EvalRunCreate` |
| Metric calculation? | `backend/app/services/eval_pipeline.py` | `evaluate_query()` runs 4 judges in parallel |
| Result storage? | `backend/app/services/eval_pipeline.py` | `save_eval_run()` persists `metrics_json` |
| CI integration? | `.github/workflows/` | Any workflow calling eval endpoints |
| Regression detection? | Anywhere | Logic comparing current run vs baseline |

**Status:** Eval API exists and can be called programmatically. What's MISSING is CI/CD integration (no GitHub Action runs eval on PR) and regression detection (no baseline comparison). **Action: create a GitHub Action that runs eval suite on PR, compares to baseline, fails on regression.**

---

#### Gap 3: Experiment Tracking

| Check | File/Location | What to Look For |
|---|---|---|
| Retrieval logging? | `backend/app/services/database.py` | `log_retrieval()` persists query, scores, sources |
| Latency logging? | `backend/app/services/performance.py` | `log_latency()` for each pipeline stage |
| Eval run tracking? | `backend/app/services/eval_pipeline.py` | `save_eval_run()` with `metrics_json` |
| Feedback collection? | `backend/app/services/database.py` | `save_message_feedback()` thumbs up/down |
| Parameter versioning? | Anywhere | Git-commit-tied experiment records |
| Langfuse tracing? | `backend/app/services/langfuse.py` | `@observe` decorators on reranker, metadata |

**Status:** Per-query logging EXISTS (retrieval logs, latency, feedback, Langfuse traces). What's MISSING is structured experiment tracking — no way to compare "experiment A (chunk_size=500, model=X) scored 0.82 vs experiment B (chunk_size=1000, model=Y) scored 0.79". **Action: create an `experiments` table or markdown log that ties git commit + parameters + eval metrics together.**

---

#### Gap 4: Breadcrumb Path Augmentation

| Check | File/Location | What to Look For |
|---|---|---|
| Heading tracking in chunker? | `backend/app/services/chunker.py` | `ChunkMetadata.heading` field |
| Document enrichment? | `backend/app/services/document_enrichment.py` | `emphasize_document_text()` prepends title/summary/tags |
| Heading detection? | `backend/app/services/document_enrichment.py` | `_looks_like_heading()` recognizes markdown headings |
| Breadcrumb prepending? | `backend/app/services/chunker.py` | Look for heading hierarchy concatenation before embedding |
| How chunks are embedded? | `backend/app/services/file_search_store.py` | Check if `ChunkMetadata.heading` is prepended to chunk text |

**Status:** Document-level enrichment EXISTS (title/summary/tags header prepended to entire doc before chunking). Heading tracking EXISTS in `ChunkMetadata.heading`. What's MISSING is per-chunk breadcrumb prepending — the `heading` metadata is stored as payload but NOT concatenated into the chunk text before embedding. Each chunk only gets the document-level header, not its own heading hierarchy path. **Action: in `_chunk_blocks()` or `file_search_store.py`, prepend `ChunkMetadata.heading` hierarchy to each chunk's text before calling the embedding function.**

---

#### Gap 5: Lost-in-the-Middle Mitigation

| Check | File/Location | What to Look For |
|---|---|---|
| Chunk ordering logic? | `backend/app/services/retrieval.py` | Look for sort/reorder before context assembly |
| Context assembly? | `backend/app/services/agents/doc_rag_agent.py` | How chunks are ordered in the prompt |
| Prompt template? | `backend/app/services/gemini.py` | `RAG_SYSTEM_PROMPT` chunk injection order |
| Relevance-based ordering? | Anywhere | Sort by score before injecting into prompt |

**Status:** Chunks are merged via RRF and reranked, but the final ordering in the LLM prompt follows retrieval order, not deliberate relevance-based placement at start/end. **Action: after reranking, reorder chunks so the most relevant are at position 1 and position N (last), with less relevant in the middle.**

---

#### Gap 6: Dynamic Top-K

| Check | File/Location | What to Look For |
|---|---|---|
| Query complexity detection? | `backend/app/services/agents/doc_rag_agent.py` | `_is_hyde_eligible()`, `_needs_external_context()` |
| Top-k configuration? | `backend/app/services/retrieval.py` | Hardcoded vs dynamic `top_k` parameter |
| Chunk count in prompt? | `backend/app/services/agents/doc_rag_agent.py` | How many chunks are selected for context |

**Status:** Some query classification EXISTS (HyDE eligibility, external context detection). Top-k is likely hardcoded. **Action: add a lightweight query classifier that returns `top_k` (3 for simple factual, 5-7 for comparative, 10+ for multi-context).**

---

#### Gap 7: Reranker Fallback Improvement

| Check | File/Location | What to Look For |
|---|---|---|
| Current fallback? | `backend/app/services/reranker.py` | `_keyword_overlap_score()` on Cohere failure |
| Vector scores available? | `backend/app/services/retrieval.py` | Are Qdrant similarity scores passed through to reranker? |
| Fallback trigger? | `backend/app/services/reranker.py` | Exception handling around `rerank_with_cohere()` |

**Status:** Fallback EXISTS but uses keyword overlap (crude). Vector similarity scores from Qdrant are available in the retrieval results but may not be passed to the reranker fallback. **Action: on Cohere failure, re-sort by Qdrant vector similarity score instead of keyword overlap.**

---

#### Gap 8: Per-Query Latency Logging by Stage

| Check | File/Location | What to Look For |
|---|---|---|
| Latency instrumentation? | `backend/app/services/performance.py` | `log_latency()`, `timed_stage()`, `timed_async()` |
| Retrieval stages? | `backend/app/services/retrieval.py` | `retrieval.embedding`, `retrieval.fts`, `retrieval.qdrant_vector`, `retrieval.rerank` |
| LLM stages? | `backend/app/services/agents/doc_rag_agent.py` | `llm.first_token`, `llm.completion` |
| Storage/persistence? | Anywhere | Where do latency logs go? Console? Supabase? Langfuse? |
| Dashboard? | Anywhere | Latency visualization or aggregation |

**Status:** Per-stage latency logging FULLY EXISTS via `performance.py`. Every pipeline stage is instrumented. What may be MISSING is persistence (console logs vs stored for analysis) and a dashboard. **Action: verify logs reach Langfuse or Supabase; if only console, add persistence. Build a simple latency breakdown view.**

---

#### Gap 9: Semantic Caching

| Check | File/Location | What to Look For |
|---|---|---|
| Cache implementation? | `backend/app/services/semantic_cache.py` | `SemanticCache` class with `lookup()`, `store()` |
| Integration point? | `backend/app/services/retrieval.py` | Cache check before retrieval, store after |
| Similarity threshold? | `backend/app/services/semantic_cache.py` | Default 0.95 cosine threshold |
| TTL? | `backend/app/services/semantic_cache.py` | Default 300s |
| Persistence? | `backend/app/services/semantic_cache.py` | In-memory only vs Redis/DB |

**Status:** Semantic cache FULLY EXISTS — in-memory with TTL, cosine similarity lookup, integrated into retrieval. **Action: likely already done. Verify it's active in production. If needed, upgrade from in-memory to Redis for multi-instance deployments.**

---

#### Gap 10: Contextual Retrieval (LLM-Generated Chunk Prefixes)

| Check | File/Location | What to Look For |
|---|---|---|
| Document enrichment? | `backend/app/services/document_enrichment.py` | `emphasize_document_text()` prepends title/summary/tags |
| Per-chunk context? | `backend/app/services/chunker.py` | LLM-generated context summary per chunk |
| Anthropic-style context? | Anywhere | "This chunk is from [doc] section [X] about [Y]" prefix |

**Status:** Document-level enrichment EXISTS (title/summary/tags). Per-chunk LLM-generated context does NOT exist. This is a more advanced version of Gap 4 — instead of just prepending heading hierarchy, use an LLM to generate a contextual summary for each chunk. **Action: implement after Gap 4 (breadcrumbs are the prerequisite). Add a lightweight LLM call per chunk during ingestion to generate a 1-sentence context prefix.**

---

### Summary: What Actually Needs Work

| Gap | Existing Infrastructure | Remaining Work |
|---|---|---|
| 1. Golden eval dataset | ✅ Full eval framework + API + persistence | Generate + human-validate 30-50 samples |
| 2. CI/CD eval | ✅ Eval API callable | GitHub Action + regression detection |
| 3. Experiment tracking | ✅ Per-query logging + Langfuse | Structured experiment records (commit + params + metrics) |
| 4. Breadcrumb augmentation | ✅ Heading metadata tracked, doc-level enrichment | Prepend heading hierarchy to chunk text before embedding |
| 5. Lost-in-the-Middle | ✅ Reranking orders by relevance | Reorder for LLM attention (best at start/end) |
| 6. Dynamic top-k | ⚠️ Partial (HyDE/external context checks) | Query complexity → top_k mapping |
| 7. Reranker fallback | ✅ Fallback exists (keyword overlap) | Use vector scores instead of keyword overlap |
| 8. Latency logging | ✅ Fully instrumented | Verify persistence + build dashboard |
| 9. Semantic caching | ✅ Fully implemented | Verify active; consider Redis for scaling |
| 10. Contextual retrieval | ✅ Document-level enrichment | Per-chunk LLM context prefix (after Gap 4) |

**Key insight:** Most gaps are NOT "build from scratch" — they're "extend existing infrastructure." Verify what's there first, then build only the delta.

---

### Improvement Roadmap

**Phase 1: Measurement Foundation (Week 1)**
- Build golden test set (30-50 samples)
- Establish baseline metrics (RAGAS: faithfulness, context precision, context recall, answer relevancy)
- Add experiment tracking (even a markdown table is fine to start)

**Phase 2: Quick Wins (Week 2)**
- Breadcrumb path augmentation in chunker
- Lost-in-the-Middle chunk ordering
- Improved reranker fallback (vector score re-sort)

**Phase 3: Automation (Week 3)**
- RAGAS eval pipeline integrated into PR workflow
- Per-stage latency logging
- Metric regression alerts

**Phase 4: Advanced (Week 4+)**
- Dynamic top-k based on query complexity
- Semantic caching
- Contextual retrieval (LLM-generated chunk prefixes)
- Production monitoring dashboard (weekly metric review)

---

## Key Sources

- [RAGAS Documentation](https://docs.ragas.io/)
- [Anthropic -- Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval)
- [Jina AI -- Late Chunking](https://jina.ai/news/late-chunking-in-long-context-embedding-models/)
- [Lost in the Middle (Liu et al., 2023)](https://arxiv.org/abs/2307.03172)
- [Cormack et al. -- Reciprocal Rank Fusion (SIGIR 2009)](https://dl.acm.org/doi/10.1145/1571941.1572114)
- [CRAG Paper](https://arxiv.org/abs/2401.15884)
- [HyDE (Gao et al., 2022)](https://arxiv.org/abs/2212.10496)
- [RAPTOR Paper](https://arxiv.org/abs/2401.18059)
- [Microsoft GraphRAG](https://microsoft.github.io/graphrag/)
- [Qdrant Hybrid Search](https://qdrant.tech/documentation/hybrid-search/)
- [Cohere Rerank API](https://cohere.com/rerank)
- [Hamel Husain's Blog](https://hamel.dev)
