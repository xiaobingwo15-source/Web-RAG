# RAG Pipeline Debugging

Systematic workflow for debugging RAG retrieval issues — wrong chunks, missing context, mixed topics, or hallucinated answers.

## When to Use
- User reports the chatbot answered from general knowledge instead of documents
- Response contains content from wrong/unrelated documents
- Follow-up questions get irrelevant results
- "I couldn't find relevant information" when documents are uploaded
- Reranker errors or retrieval returning 0 results

## Step 1: Check Backend Logs

Look for these log prefixes in the terminal running the backend:

| Prefix | What it tells you |
|--------|-------------------|
| `[RETRIEVAL]` | Query text, mode (hybrid/fts/vector), result counts |
| `[QDRANT]` | Vector search scores and count |
| `[DOC_RAG]` | Final chunk count passed to LLM |
| `[AGENT]` | Which agent was routed to |

**Red flags:**
- Scores all below 0.5 → weak matches, likely wrong documents
- `fts=0` on hybrid mode → FTS not finding anything (check if text is indexed)
- `0 results` from Qdrant → documents not indexed or wrong `target_user_id`
- `Cohere rerank failed` → reranker not working, falling back to positional ordering

## Step 2: Score Interpretation

| Score Range | Meaning | Action |
|-------------|---------|--------|
| > 0.70 | Strong match | Good — should be correct |
| 0.60 - 0.70 | Moderate match | Probably fine, verify content |
| 0.50 - 0.60 | Weak match | May be wrong topic — check content |
| < 0.50 | Noise | Almost certainly irrelevant |

## Step 3: Trace the Pipeline

Follow the data flow to find where context is lost:

```
User message
  → doc_rag_agent.execute()     # Is history used for query augmentation?
    → retrieve_context()         # Is the query contextualized?
      → get_embedding()          # What text is being embedded?
      → search_similar_chunks()  # What's the similarity_threshold?
      → search_chunks_fts()      # Is FTS returning results?
      → RRF merge                # How are vector + FTS combined?
      → rerank_with_cohere()     # Is Cohere working or falling back?
    → context_chunks             # Final chunks sent to LLM
  → generate_chat_response_stream()  # LLM sees chunks + history
```

## Step 4: Common Fixes

### Follow-up queries returning wrong topics
**Symptom:** "i want more details" in a badminton conversation retrieves AI tool chunks
**Root cause:** Raw message embedded without conversation context
**Fix:** `_build_augmented_query()` in `doc_rag_agent.py` — prepend recent user messages before retrieval

### Weak matches polluting results
**Symptom:** Vector scores 0.50-0.55, unrelated chunks mixed in
**Root cause:** `similarity_threshold` too low (default 0.1)
**Fix:** Raise to 0.5 in `retrieval.py` calls to `search_similar_chunks()`

### Reranker not filtering
**Symptom:** `Cohere rerank failed` in logs, results returned in positional order
**Root cause:** `COHERE_API_KEY` not set
**Fix:** Set the API key, or ensure `_keyword_overlap_score()` fallback is in place in `reranker.py`

### LLM ignoring retrieved context
**Symptom:** Correct chunks retrieved but LLM answers from general knowledge
**Root cause:** Weak model ignoring system prompt
**Fix:** Hardcoded refusal in `doc_rag_agent.py` when 0 chunks; stronger `RAG_SYSTEM_PROMPT` in `gemini.py`

### Client users getting wrong documents
**Symptom:** Client sees admin's documents on first request, then own (empty) on subsequent requests
**Root cause:** `target_user_id` resolution only running on first request
**Fix:** Ensure `_resolve_target_user_id` runs unconditionally in `agent_supervisor.py`

## Step 5: Verify Fix

1. Restart backend
2. Start a new conversation, ask about a known document topic
3. Ask a follow-up ("tell me more", "clarify that")
4. Check logs: scores should be >0.60, chunks should be on-topic
5. Response should reference document content, not general knowledge

## Key Files
- `backend/app/services/agents/doc_rag_agent.py` — query augmentation, hardcoded refusal
- `backend/app/services/retrieval.py` — hybrid/vector/FTS retrieval, similarity threshold
- `backend/app/services/qdrant_db.py` — vector search with score_threshold
- `backend/app/services/reranker.py` — Cohere rerank + keyword fallback
- `backend/app/services/gemini.py` — RAG_SYSTEM_PROMPT, LLM streaming
- `backend/app/services/agent_supervisor.py` — agent routing, target_user_id resolution
- `backend/app/routers/chat.py` — history reconstruction, endpoint logic
