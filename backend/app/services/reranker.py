import json
import logging
from google import genai
from google.genai import types
from langfuse import observe
from app.services.gemini import PRIMARY_MODEL

logger = logging.getLogger(__name__)

RERANK_PROMPT = (
    "You are a relevance scoring engine. Given a user query and a list of document passages, "
    "score each passage from 0 to 1 based on how relevant it is to answering the query.\n\n"
    "Return a JSON array of objects with fields: index (0-based), score (float 0-1), reason (brief).\n"
    "Order from most to least relevant.\n\n"
    "Return ONLY valid JSON array, no other text."
)


@observe(name="rerank_with_gemini", as_type="generation")
async def rerank_with_gemini(
    client: genai.Client,
    query: str,
    documents: list[str],
    top_n: int = 5,
) -> list[dict]:
    if not documents:
        return []

    doc_list = "\n".join(f"[{i}] {doc[:500]}" for i, doc in enumerate(documents))
    prompt = f"Query: {query}\n\nPassages:\n{doc_list}"

    response = await client.aio.models.generate_content(
        model=PRIMARY_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=1024,
            response_mime_type="application/json",
            system_instruction=RERANK_PROMPT,
        ),
    )

    raw = response.candidates[0].content.parts[0].text
    try:
        scored = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse reranker JSON: {raw}")
        return [{"index": i, "score": 1.0 - i * 0.1} for i in range(min(top_n, len(documents)))]

    scored.sort(key=lambda x: x.get("score", 0), reverse=True)
    return scored[:top_n]
