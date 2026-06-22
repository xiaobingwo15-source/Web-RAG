# RAG Quality Signals Skill

Run the 6 RAG quality health signals via Supabase MCP. Replaces the manual SQL-query workflow that was repeated 3+ times per session.

## When to Use

- User says "check signals", "rag signals", "quality check", "health check"
- `/rag-signals`
- Before and after deploying RAG pipeline changes
- As part of a `/loop` for continuous monitoring

## Steps

### 1. Query Retrieval Logs (7-day window)

```sql
SELECT id, query, top_score, source_count, chunk_count, duration_ms,
       groundedness_score, groundedness_flag, retrieval_quality,
       answer_message_id, created_at
FROM retrieval_logs
WHERE created_at > NOW() - INTERVAL '7 days'
ORDER BY created_at DESC LIMIT 50
```

### 2. Query Thumbs-Down Feedback

```sql
SELECT id, message_id, rating, comment, created_at
FROM message_feedback
WHERE created_at > NOW() - INTERVAL '30 days' AND rating = -1
ORDER BY created_at DESC LIMIT 50
```

Note: `rating` is `smallint` (-1 = thumbs down, 1 = thumbs up), NOT text.

### 3. Compute the 6 Signals

From the query results, compute:

| Signal | Condition | Warn | Critical |
|--------|-----------|------|----------|
| **No Sources** | `source_count == 0` or `chunk_count == 0` | ≥10% | ≥25% |
| **Weak Sources** | `top_score < 0.40` (near-random: `< 0.15`) | ≥10% | ≥25% |
| **Grounding** | `groundedness_flag == true` or low confidence | ≥10% | ≥25% |
| **Completion Latency** | `duration_ms >= 3000`; p95 | p95≥3000ms | p95≥6000ms |
| **Feedback & Fallback** | max(thumbs_down_rate, fallback_rate) | ≥10% | ≥25% |
| **Data Staleness** | recent_avg/older_avg < 0.50 (≥10 scored logs) | ratio<0.50 | ratio<0.50 & avg<0.30 |

Fallback detection: `retrieval_quality` contains "fallback" OR `diagnostics.fallback_reason` set OR `web_result_count > 0`.

### 4. Output Format

```markdown
## RAG Quality Signals — {date}

| # | Signal | Status | Rate / Value | Detail |
|---|--------|--------|-------------|--------|
| 1 | No Sources | ✅/🟡/🔴 | X% (N/total) | brief detail |
| 2 | Weak Sources | ... | ... | ... |
| 3 | Grounding | ... | ... | ... |
| 4 | Completion Latency | ... | p95=Xms | ... |
| 5 | Feedback & Fallback | ... | ... | ... |
| 6 | Data Staleness | ... | ratio=X | ... |

### Diagnosis
{1-3 sentences on the most critical signal}

### Recommended Actions
1. {action for worst signal}
2. {action for second worst}
```

### 5. Compare with Previous (optional)

If running in a loop, compare with previous check:
- "No new data since last check" if total count unchanged
- Note any deltas in rates or new critical signals

## Rules

- Always query both tables (retrieval_logs + feedback) even if one returns empty
- Compute p95 by sorting duration_ms values and taking the 95th percentile
- For staleness: split scored logs into recent/older halves by created_at
- Status levels: `ok` (below warn), `watch` (at or above warn), `critical` (at or above critical threshold)
- Keep output concise — one table, one diagnosis, one action list
