---
description: Diagnose 0-chunk retrieval — checks document status, chunk stores, user alignment, and retrieval pipeline
---

# RAG Debug: 0-Chunk Diagnosis

Systematic diagnosis for "I couldn't find relevant information" or empty retrieval results. Run each step and report findings.

## Step 1: Document Status

Check if documents are uploaded and in `processed` status.

Use Supabase MCP `execute_sql`:
```sql
SELECT id, filename, status, error_message, user_id, created_at
FROM documents
ORDER BY created_at DESC
LIMIT 10;
```

If status is not `processed`, the ingestion pipeline failed. Check `error_message` column and backend logs.

## Step 2: Chunk Counts — Supabase

```sql
SELECT document_id, count(*) as chunk_count
FROM document_chunks
GROUP BY document_id
ORDER BY chunk_count DESC;
```

If 0 rows total, `insert_chunks_for_fts` was never called. Check `file_search_store.py`.

If a document has 0 chunks but status is `processed`, the FTS insert silently failed.

## Step 3: Chunk Counts — Qdrant

```bash
cd backend && python -c "
import asyncio
from app.services.qdrant_db import get_qdrant_client
async def check():
    client = await get_qdrant_client()
    info = await client.get_collection('document_chunks')
    print(f'Total vectors: {info.points_count}')
asyncio.run(check())
"
```

Compare with Supabase chunk count. If Qdrant has chunks but Supabase doesn't (or vice versa), the parallel insert in `file_search_store.py` had a partial failure.

## Step 4: User ID Alignment

Client users must search the **admin's** knowledge base, not their own. Check the redirect logic:

```bash
cd backend && python -c "
from app.services.database import get_admin_user_id
import asyncio
async def check():
    admin_id = await get_admin_user_id('<supabase_service_role_token>')
    print(f'Admin user_id: {admin_id}')
asyncio.run(check())
"
```

Then verify chunks exist under the admin's user_id:
```sql
SELECT user_id, count(*) FROM document_chunks GROUP BY user_id;
```

If client's user_id has chunks but admin's doesn't, the redirect in `retrieval.py:22-33` is broken or `get_admin_user_id` returns wrong ID.

## Step 5: FTS Function Exists

```sql
SELECT routine_name FROM information_schema.routines
WHERE routine_name = 'search_chunks_fts';
```

If missing, the FTS RPC was never created. Check Supabase migrations for the function definition.

## Step 6: Backend Logs

Check recent backend output for `[RETRIEVAL]` print statements:

```bash
# If running with --reload, check the terminal output
# Look for lines like:
# [RETRIEVAL] hybrid mode: X vector + Y FTS results
# [RETRIEVAL] After RRF merge: Z chunks
# [RETRIEVAL] After reranker: W chunks
```

Key things to look for:
- `0 vector results` → embedding or Qdrant issue
- `0 FTS results` → Supabase FTS issue or empty query
- `After RRF merge: 0` → both sources returned nothing
- `After reranker: 0` → reranker filtered everything out (check threshold)

## Step 7: Quick Retrieval Test

```bash
cd backend && python -c "
import asyncio
from app.services.retrieval import retrieve_context

async def test():
    chunks = await retrieve_context(
        token='<service_role_token>',
        user_id='<admin_user_id>',
        message='test query about your documents',
        mode='hybrid',
        match_count=5
    )
    print(f'Results: {len(chunks)}')
    for i, c in enumerate(chunks[:3]):
        print(f'  [{i}] {c[:150]}...')

asyncio.run(test())
"
```

Replace `<service_role_token>` and `<admin_user_id>` with real values from steps 4-5.

## Step 8: Report

| Check | Status | Finding |
|-------|--------|---------|
| Documents processed | PASS/FAIL | N documents, statuses |
| Supabase chunks | PASS/FAIL (N rows) | Per-document counts |
| Qdrant vectors | PASS/FAIL (N vectors) | Collection count |
| User alignment | PASS/FAIL | Admin ID vs chunk owner |
| FTS function | PASS/FAIL | Exists or missing |
| Backend logs | PASS/FAIL | Key error patterns |
| Retrieval test | PASS/FAIL (N chunks) | Direct test result |

**Root cause patterns:**
- Chunks in Qdrant but not Supabase → FTS insert failed, vector insert succeeded
- Chunks under client user_id, not admin → `get_admin_user_id` returning wrong ID
- FTS function missing → migration not applied
- Documents stuck in `processing` → ingestion crash, check `error_message`
- Reranker returns 0 → LLM reranker filtering too aggressively, check `reranker.py` fallback
