# Eval Runner Skill

Run RAG evaluation suite, compare to baseline, update baselines.

## When to Use

- User says "run eval", "test RAG quality", "check metrics", "update baseline"
- After pipeline changes to verify no regression
- Before/after experiments to measure impact

## Prerequisites

- Golden test set exists at `backend/tests/fixtures/golden_test_set.json`
- If missing, generate: `cd backend && python -m scripts.generate_golden_test_set`
- Backend env vars configured (SUPABASE_URL, GOOGLE_API_KEY, QDRANT_URL, etc.)

## Steps

### 1. Run Eval Suite

```bash
cd D:\RAG\Web-RAG\backend
python -m scripts.run_eval_ci
```

This will:
- Load golden test set from `tests/fixtures/golden_test_set.json`
- Run hybrid retrieval + LLM-as-judge scoring (4 RAGAS metrics)
- Compare against baseline in `tests/fixtures/eval_baseline.json`
- Print metric comparison table
- Exit 0 (pass) or 1 (regression detected)

### 2. Run with Custom Config

```bash
# Test with specific retrieval mode
python -c "
import asyncio
from app.services.eval_pipeline import load_golden_test_set, run_eval_suite

async def main():
    cases = load_golden_test_set()
    result = await run_eval_suite(cases, retrieval_mode='vector')
    print(f'Overall: {result.avg_overall:.2f}')

asyncio.run(main())
"
```

### 3. Update Baseline

After a good run, update the baseline:

```bash
python -m scripts.run_eval_ci --update-baseline
```

Or manually edit `tests/fixtures/eval_baseline.json`:
```json
{
  "faithfulness": 4.2,
  "answer_relevance": 4.0,
  "context_precision": 3.8,
  "context_recall": 4.1,
  "overall": 4.0
}
```

### 4. Generate Fresh Test Set

```bash
cd D:\RAG\Web-RAG\backend
python -m scripts.generate_golden_test_set --num-questions 3 --max-chunks 50
```

Then review `tests/fixtures/golden_test_set.json` and set `validated: true` on reviewed items.

## API-Based Eval

```bash
# Run eval via API (requires auth token)
curl -X POST http://localhost:8000/api/eval/run \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "retrieval_mode": "hybrid",
    "chunk_size": 500,
    "top_k": 8,
    "notes": "testing after breadcrumb augmentation"
  }'

# List recent runs
curl http://localhost:8000/api/eval/runs \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Metrics Reference

| Metric | Scale | Target | What It Measures |
|--------|-------|--------|-----------------|
| Faithfulness | 1-5 | ≥4.0 | Answer grounded in context |
| Answer Relevance | 1-5 | ≥4.0 | Answer addresses the question |
| Context Precision | 1-5 | ≥3.5 | Retrieved chunks are relevant |
| Context Recall | 1-5 | ≥3.5 | Retrieved all needed info |
| Overall | 1-5 | ≥3.8 | Average of above |

## Common Issues

**"Cannot load golden test set"**
- Generate it: `python -m scripts.generate_golden_test_set`

**"No documents found" in CI**
- CI runs without auth — vector search needs seeded data with `user_id=""`
- FTS path works with service-role client

**Metrics all 0.0**
- Check LLM API key is configured
- Check Supabase connection
- Check Qdrant has documents
