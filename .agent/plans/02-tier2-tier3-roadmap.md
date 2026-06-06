# Tier 2 & Tier 3: Answer Quality & Agent Evolution Roadmap

> **Status:** Planned (Tier 1 completed 2026-06-04)
> **Tier 1 delivered:** Source citations, context token budget, LLM-based groundedness, groundedness retry loop

---

## Tier 2: Medium Impact, Lower Effort

### 2.1 — Better Prompt Engineering

**Goal:** Make answers more structured, safer, and consistent across all agents.

**Current gaps:**
- `RAG_SYSTEM_PROMPT` has no explicit refusal phrasing like *"If the reference information does not contain the answer, say 'I don't have that information'"*
- No answer structure guidance (e.g., "direct answer first, then supporting details")
- `web_search_agent.py` and `sql_sub_agent.py` send synthesis prompts as raw user messages with **no system prompt** — the LLM has no persona, tone, or constraint instructions

**Files to modify:**
| File | Change |
|------|--------|
| `backend/app/services/gemini.py` | Strengthen `RAG_SYSTEM_PROMPT` refusal + structure |
| `backend/app/services/agents/doc_rag_agent.py` | Update `CORRECTIVE_RAG_SYSTEM_PROMPT`, `HYBRID_SYSTEM_PROMPT` |
| `backend/app/services/agents/web_search_agent.py` | Add a proper system prompt for web synthesis |
| `backend/app/services/agents/sql_sub_agent.py` | Add a proper system prompt for SQL result summarization |

**Prompt additions for RAG_SYSTEM_PROMPT:**
```
"If the reference information does not contain the answer, say
'I don't have that information in my knowledge base' — do not guess.

Structure your answer:
1. A brief direct answer (1-2 sentences)
2. Supporting details with source references
3. Sources section"
```

**New system prompt for web_search_agent.py:**
```python
WEB_SEARCH_SYSTEM_PROMPT = (
    "You are a knowledgeable assistant answering questions using web search results. "
    "Be conversational, warm, and direct.\n\n"
    "When citing information, naturally mention the source by title "
    "(e.g., 'According to [Source Title]...'). "
    "If the search results don't fully answer the question, say so honestly. "
    "Do not make up information.\n\n"
    "Use natural Markdown formatting (headings, bullet points, bold). "
    "At the end, include a 'Sources' section with URLs."
)
```

**New system prompt for sql_sub_agent.py:**
```python
SQL_SUMMARY_SYSTEM_PROMPT = (
    "You are a data analyst assistant. Summarize database query results "
    "in clear, natural language.\n\n"
    "Be conversational and direct. Highlight key numbers and trends. "
    "If the data is empty or inconclusive, say so honestly.\n\n"
    "Use natural Markdown formatting. Include a brief data table if appropriate."
)
```

**Verification:** Chat with web_search route → answer should cite sources by URL. Chat with SQL route → answer should be structured and natural.

---

### 2.2 — Query Rewriting Should Include Assistant Messages

**Goal:** Better standalone queries for follow-up questions by including the last assistant response as context.

**Current behavior:** `rewrite_query()` in `doc_rag_agent.py` (line 72) only extracts **user messages** from history. The assistant's previous answer — which often contains the key terms the follow-up refers to — is ignored.

**File to modify:** `backend/app/services/agents/doc_rag_agent.py`

**Change:** In `rewrite_query()`, modify the history extraction (lines 77-82):

```python
# CURRENT — only user messages
recent_user_msgs = [
    msg["content"] if isinstance(msg["content"], str)
    else next((p["text"] for p in msg["content"] if p.get("type") == "text"), "")
    for msg in history[-6:]
    if msg["role"] == "user"
]

# NEW — include last assistant message for context
recent_context = []
for msg in history[-6:]:
    content = msg["content"] if isinstance(msg["content"], str) else next((p["text"] for p in msg["content"] if p.get("type") == "text"), "")
    if msg["role"] == "user":
        recent_context.append(f"User: {content}")
    elif msg["role"] == "assistant":
        recent_context.append(f"Assistant: {content[:200]}")  # Truncate long answers
```

Update the prompt block to use `recent_context` instead of `recent_user_msgs`.

**Verification:** Ask "What about the pricing?" after a document discussion → rewritten query should include pricing context from the previous answer.

---

### 2.3 — History Window / Summarization

**Goal:** Prevent context window exhaustion in long conversations by summarizing or truncating old history.

**Current behavior:** `_build_messages()` in `gemini.py` passes **all** history without truncation. A 20-message conversation could consume most of the context window, leaving little room for retrieved chunks.

**Files to modify:**
| File | Change |
|------|--------|
| `backend/app/services/gemini.py` | Add `_trim_history()` function |
| `backend/app/config.py` | Add `max_history_messages` setting (default: 10) |

**Implementation:**

```python
def _trim_history(history: list[dict], max_messages: int = 10) -> list[dict]:
    """Keep the last N messages to prevent context window overflow.

    If the history exceeds max_messages, keep the first message (for context)
    and the most recent (max_messages - 1) messages.
    """
    if not history or len(history) <= max_messages:
        return history

    # Keep first message + last (max_messages - 1)
    return [history[0]] + history[-(max_messages - 1):]
```

Wire into `_build_messages()`:
```python
if history:
    from app.config import Settings as _Settings
    max_hist = _Settings().max_history_messages
    history = _trim_history(history, max_hist)
    messages.extend(history)
```

**Future enhancement:** Replace truncation with LLM-based summarization of old messages (compress 10 old messages into a 2-sentence summary).

**Verification:** Have a 20+ message conversation → no context overflow errors, answer quality stays consistent.

---

## Tier 3: True Agent Features (Higher Effort)

### 3.1 — Plan-and-Execute Pattern

**Goal:** Decompose complex multi-part questions into sub-tasks and execute them sequentially.

**Current behavior:** A question like *"Compare our pricing with Competitor X and summarize the differences"* gets one retrieval pass — it can't separately search for internal pricing AND external competitor data.

**Concept:**
```
User: "Compare our pricing with Competitor X and summarize the differences"

Plan:
  1. Search documents for our pricing → get internal data
  2. Search web for Competitor X pricing → get external data
  3. Compare and synthesize → structured comparison answer
```

**File to create:** `backend/app/services/agents/plan_executor.py`

**Architecture:**
1. Add a **planning step** before retrieval that uses the LLM to decompose the query:
   ```python
   PLANNING_PROMPT = (
       "Given a user question, decompose it into 1-3 sub-tasks. "
       "Each sub-task should be a standalone search query. "
       "Return a JSON array of objects with 'query' and 'source' "
       "('document', 'web', or 'auto') fields."
   )
   ```
2. Execute each sub-task in parallel (document retrieval or web search)
3. Merge all results into a unified context
4. Generate a single synthesized answer

**Integration point:** Insert between the routing decision (supervisor) and the retrieval pipeline. The planner replaces the current single-query flow.

**Estimated effort:** 2-3 sessions. Requires careful prompt engineering for the planner and robust merging logic.

---

### 3.2 — ReAct Loop for doc_rag

**Goal:** Replace the fixed DAG pipeline with a dynamic reasoning loop where the LLM decides at each step what to do next.

**Current pipeline (fixed):**
```
query → rewrite → expand → retrieve → HyDE → grade → [maybe web] → generate → check → done
```

**ReAct pipeline (dynamic):**
```
query → think("what do I need?") → retrieve → evaluate("good enough?")
  → NO → think("try different strategy") → re-retrieve → evaluate
  → YES → generate → verify("is this grounded?") → NO → regenerate → done
```

**Key difference:** The LLM, not hard-coded logic, decides when to stop retrieving, when to try web search, and when the answer is good enough.

**File to create:** `backend/app/services/agents/react_agent.py`

**Architecture:**
```python
class ReActAgent:
    """Dynamic reasoning loop for RAG."""

    MAX_ITERATIONS = 5

    async def execute(self, query, context_chunks, sources):
        for i in range(self.MAX_ITERATIONS):
            # Think: what should I do next?
            action = await self._think(query, context_chunks, sources)

            if action["type"] == "retrieve":
                new_chunks = await self._retrieve(action["query"])
                context_chunks.extend(new_chunks)
            elif action["type"] == "web_search":
                web_results = await self._search_web(action["query"])
                context_chunks.extend(web_results)
            elif action["type"] == "generate":
                answer = await self._generate(query, context_chunks)
                if await self._verify(answer, context_chunks):
                    return answer
                # If not grounded, loop back to think
            elif action["type"] == "done":
                break

        # Final fallback: generate with what we have
        return await self._generate(query, context_chunks)
```

**Trade-offs:**
- (+) Much more flexible — can handle novel query patterns
- (+) Self-correcting at every step
- (-) Higher latency (multiple LLM calls per query)
- (-) Higher cost (more API calls)
- (-) Harder to debug and predict behavior

**Estimated effort:** 3-4 sessions. Requires a robust action parser and fallback logic.

---

### 3.3 — Inter-Agent Delegation

**Goal:** Allow agents to delegate to each other when they detect the query would be better handled by a different agent.

**Current behavior:** The supervisor picks ONE agent at routing time. The doc_rag agent can't ask the SQL agent for data, and the SQL agent can't ask doc_rag for context.

**Concept:**
```
User: "What were our Q1 sales and how do they compare to our pricing document?"

Supervisor → doc_rag (has pricing documents)
  doc_rag detects: "Q1 sales" needs database query
    → delegates to sql_agent for Q1 sales data
    → merges SQL results with document context
    → synthesizes unified answer
```

**File to modify:** `backend/app/services/agents/doc_rag_agent.py`

**Architecture:**
1. Add a **delegation classifier** that checks if part of the query needs a different agent:
   ```python
   DELEGATION_PROMPT = (
       "Given a user query, does any part of it require database/data queries "
       "(e.g., sales numbers, counts, metrics) that can't be answered from documents? "
       "Reply with 'sql' if yes, 'none' if no."
   )
   ```
2. If delegation is needed, call the target agent's function directly (not via HTTP)
3. Merge delegated results into the context before generation

**Key implementation detail:** The delegated agent should be called as a Python function, not via HTTP. The SQL agent's `generate_sql` + `execute_readonly_sql` can be called directly.

**Estimated effort:** 2 sessions. Requires careful prompt engineering for delegation detection and robust result merging.

---

## Implementation Priority

```
Tier 2 (do next):
  2.1 Prompt Engineering     ← Highest ROI, pure prompt changes
  2.2 Query Rewrite Fix      ← Small code change, noticeable quality gain
  2.3 History Window         ← Safety net for long conversations

Tier 3 (do when Tier 2 is stable):
  3.1 Plan-and-Execute       ← Biggest architectural leap
  3.2 ReAct Loop             ← Most flexible, highest effort
  3.3 Inter-Agent Delegation ← Enables multi-tool queries
```

## Dependencies

```
2.1 (Prompts)      ← independent
2.2 (Query Rewrite) ← independent
2.3 (History)       ← independent
3.1 (Plan-Execute)  ← builds on 2.1
3.2 (ReAct)         ← builds on 3.1
3.3 (Delegation)    ← builds on 3.1
```

## Session Notes

- All changes are in `backend/app/services/` — no frontend changes needed for Tier 2
- Tier 3 changes may require frontend updates to display planning/delegation thoughts
- Test each change independently before combining
- Use the `rag-retrieval-test` agent to verify retrieval quality after changes
- Use Langfuse traces to measure latency impact of each change
