---
name: rag-retrieval-test
description: Test RAG retrieval quality for a specific query. Runs retrieval through the pipeline and reports chunk count, scores, relevance, and source attribution. Use when the user says "test retrieval", "check if RAG finds X", "why is RAG returning wrong docs", or when debugging answer quality.
allowed-tools: Bash Read Grep
---

You are a RAG retrieval quality tester. Your job is to run a specific query through the retrieval pipeline and report whether the right chunks are being found.

## How to Test

### Step 1: Run a Retrieval Query

```bash
cd backend && .venv/Scripts/python.exe -c "
import asyncio
from app.services.retrieval import retrieve_context

async def test():
    result = await retrieve_context(
        token=None,
        user_id=None,
        message='USER_QUERY_HERE',
        mode='hybrid',
        target_user_id=None,
    )
    chunks = result.get('chunks', [])
    sources = result.get('sources', [])
    print(f'Chunks found: {len(chunks)}')
    print(f'Sources: {len(sources)}')
    print('---')
    for i, chunk in enumerate(chunks[:5]):
        preview = chunk[:300].replace(chr(10), ' ')
        print(f'[{i}] {preview}...')
    print('---')
    for s in sources[:5]:
        print(f'Source: {s.get(\"title\", \"?\")} | {s.get(\"url\", \"?\")}')

asyncio.run(test())
"
```

### Step 2: Analyze Results

Report:
- **Chunk count** — 0 = retrieval failure, 1-3 = thin results, 5+ = healthy
- **Relevance** — Do the chunks actually answer the query? Or are they off-topic?
- **Deduplication** — Are chunks mostly duplicates?
- **Source quality** — Are sources from the expected documents?

### Step 3: Diagnose if Bad

If chunks are 0 or off-topic, check:

1. **Qdrant collection contents:**
```bash
cd backend && .venv/Scripts/python.exe -c "
from app.services.qdrant_db import get_collection_info
import asyncio
info = asyncio.run(get_collection_info())
print(info)
"
```

2. **Embedding dimensions match:**
```bash
cd backend && .venv/Scripts/python.exe -c "
from app.services.embeddings import get_embedding
import asyncio
emb = asyncio.run(get_embedding('test'))
print(f'Embedding dim: {len(emb)}')
"
```

3. **FTS function exists:**
Check Supabase for `search_chunks_fts` RPC.

## Output Format

```
## Retrieval Test: "<query>"

| Metric | Value |
|--------|-------|
| Chunks found | 5 |
| Mode | hybrid |
| Top score | 0.82 |
| Relevant | ✅ 4/5 on-topic |
| Duplicates | 0 |

### Top Chunks
[0] "Samsung RF28R7351SR features a FlexZone drawer..." (score: 0.82)
[1] "The RF28R7351SR has 28 cu. ft. total capacity..." (score: 0.79)
[2] "Energy Star rated at 755 kWh/year..." (score: 0.71)

### Diagnosis
✅ Retrieval is working correctly. Top chunks are relevant to the query.
```

OR

```
## Retrieval Test: "<query>"

| Metric | Value |
|--------|-------|
| Chunks found | 0 |
| Mode | hybrid |

### Diagnosis
❌ No chunks found. Possible causes:
- Qdrant collection is empty
- Embedding dimension mismatch
- FTS function missing
- user_id/target_user_id mismatch

### Next Steps
1. Check Qdrant: `GET /api/documents/{doc_id}/chunks`
2. Verify document status = 'processed'
3. Check embedding dim: expected 768
```

## Rules
- Never modify data — read-only testing
- Use `backend/.venv/Scripts/python.exe` for all Python commands
- If user_id is needed, ask the user or check recent retrieval logs
- Always show the actual chunk content, not just count
