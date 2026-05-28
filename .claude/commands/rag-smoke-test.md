---
description: End-to-end RAG pipeline smoke test — verifies health, Qdrant chunks, FTS, and query quality
---

# RAG Smoke Test

Run a quick end-to-end verification of the RAG pipeline. Report pass/fail with evidence for each step.

## Step 1: Backend Health

```bash
curl -s http://localhost:8000/api/health
```

Expected: `{"status":"ok","service":"agentic-rag-masterclass"}`

If this fails, the backend is not running. Start it with:
```bash
cd backend && uvicorn app.main:app --reload
```

## Step 2: Qdrant Vector Store

Use the Qdrant client to check `document_chunks` collection has data:

```bash
cd backend && python -c "
import asyncio
from app.services.qdrant_db import get_qdrant_client
async def check():
    client = await get_qdrant_client()
    info = await client.get_collection('document_chunks')
    print(f'Chunks: {info.points_count}')
    print(f'Vector size: {info.config.params.vectors.size}')
    print(f'Distance: {info.config.params.vectors.distance}')
asyncio.run(check())
"
```

Expected: `Chunks: > 0`, `Vector size: 768`, `Distance: Distance.COSINE`

If chunks = 0, documents have not been ingested. Upload a document via `/api/documents` or the admin UI.

## Step 3: Supabase FTS

Check that the FTS RPC function exists and returns data:

Use Supabase MCP `execute_sql` to query the `document_chunks` table:
```sql
SELECT count(*) FROM document_chunks;
```

Expected: count > 0

If 0, the FTS side has no data. Check `database.py` → `insert_chunks_for_fts` is being called during ingestion.

## Step 4: End-to-End Query

Send a test chat query and verify the response references document content:

```bash
cd backend && python -c "
import asyncio
from app.services.retrieval import retrieve_context

async def test():
    # Use a dummy token — replace with real one if auth blocks
    chunks = await retrieve_context(
        token='',
        user_id='test',
        message='What products does the company offer?',
        mode='hybrid',
        match_count=3
    )
    print(f'Retrieved {len(chunks)} chunks')
    for i, c in enumerate(chunks):
        print(f'  [{i}] {c[:120]}...')

asyncio.run(test())
"
```

Expected: 1-5 chunks returned with content from uploaded documents.

If 0 chunks: check user_id alignment (clients redirect to admin knowledge base in `retrieval.py:22-33`), similarity threshold (should be ~0.15), and that documents are in `processed` status.

## Step 5: Report

Summarize results in a table:

| Step | Status | Evidence |
|------|--------|----------|
| Backend health | PASS/FAIL | Response from /api/health |
| Qdrant chunks | PASS/FAIL (N chunks) | Collection info |
| Supabase FTS | PASS/FAIL (N rows) | Row count |
| End-to-end query | PASS/FAIL (N chunks) | Retrieved content |

If all PASS, the RAG pipeline is operational. If any FAIL, use `/debug` with the specific failure to investigate.
