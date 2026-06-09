"""Generate a golden evaluation test set from the document corpus.

Fetches all document chunks from Supabase, generates Q&A pairs via LLM,
and saves the result as a version-controlled JSON file for human validation.

Usage (from backend/ directory):
    python -m scripts.generate_golden_test_set [--num-questions 3] [--max-chunks 50]
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure the backend root is on sys.path so `app.*` imports resolve.
_backend_root = str(Path(__file__).resolve().parent.parent)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from app.services.database import get_db
from app.services.eval_pipeline import create_golden_test_set

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("generate_golden_test_set")

# Output path: backend/tests/fixtures/golden_test_set.json
FIXTURE_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "golden_test_set.json"


def fetch_all_chunks(max_chunks: int = 200) -> list[dict]:
    """Fetch document chunks from Supabase using the service-role client.

    Returns a list of dicts with at least 'content' and 'id' keys.
    """
    db = get_db()
    result = (
        db.table("document_chunks")
        .select("id, content, document_id, chunk_index, chunk_type")
        .order("chunk_index")
        .limit(max_chunks)
        .execute()
    )
    chunks = result.data or []
    logger.info("Fetched %d chunks from Supabase", len(chunks))
    return chunks


def build_golden_json(test_cases, num_questions: int) -> dict:
    """Wrap EvalTestCase list into the version-controlled JSON schema."""
    cases = []
    for tc in test_cases:
        cases.append({
            "question": tc.question,
            "expected_answer": tc.expected_answer,
            "context": tc.context,
            "tags": list(tc.tags) if tc.tags else ["factual", "auto-generated"],
            "validated": False,
        })
    return {
        "version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "total_cases": len(cases),
        "num_questions_per_chunk": num_questions,
        "test_cases": cases,
    }


async def main(num_questions: int = 3, max_chunks: int = 50) -> None:
    """Entry point: fetch chunks, generate Q&A, save JSON."""
    # 1. Fetch chunks
    chunks = fetch_all_chunks(max_chunks=max_chunks)
    if not chunks:
        logger.error("No document chunks found in Supabase. Ingest documents first.")
        sys.exit(1)

    # Filter to chunks with meaningful content (at least 50 chars)
    substantive = [c for c in chunks if c.get("content") and len(c["content"].strip()) >= 50]
    logger.info(
        "Using %d substantive chunks out of %d fetched (skipped %d short chunks)",
        len(substantive),
        len(chunks),
        len(chunks) - len(substantive),
    )
    if not substantive:
        logger.error("No chunks with sufficient content found.")
        sys.exit(1)

    # 2. Generate Q&A pairs
    logger.info(
        "Generating Q&A pairs (target: %d questions per chunk from %d chunks)...",
        num_questions,
        len(substantive),
    )
    test_cases = await create_golden_test_set(
        chunks=substantive,
        num_questions_per_chunk=num_questions,
    )
    if not test_cases:
        logger.error("LLM failed to generate any Q&A pairs. Check API key and model.")
        sys.exit(1)

    # 3. Build and save JSON
    golden_json = build_golden_json(test_cases, num_questions)

    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(
        json.dumps(golden_json, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "Saved %d test cases to %s",
        golden_json["total_cases"],
        FIXTURE_PATH,
    )
    print(f"\nGolden test set saved to: {FIXTURE_PATH}")
    print(f"Total cases: {golden_json['total_cases']}")
    print(f"All cases start with 'validated: false' — review and flip to 'true' after validation.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a golden evaluation test set.")
    parser.add_argument(
        "--num-questions",
        type=int,
        default=3,
        help="Number of Q&A pairs per chunk (default: 3)",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=50,
        help="Maximum number of chunks to process (default: 50)",
    )
    args = parser.parse_args()
    asyncio.run(main(num_questions=args.num_questions, max_chunks=args.max_chunks))
