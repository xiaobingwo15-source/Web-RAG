import json
import logging
from openai import AsyncOpenAI
from langfuse import observe
from app.services.gemini import PRIMARY_MODEL

logger = logging.getLogger(__name__)

METADATA_PROMPT = (
    "Analyze the following document text and extract metadata. "
    "Return a JSON object with these fields:\n"
    "- title: the document title or a concise descriptive title if none exists\n"
    "- summary: a 1-2 sentence summary of the document content\n"
    "- tags: a list of 3-6 relevant topic tags\n"
    "- language: the ISO 639-1 language code (e.g., 'en', 'zh', 'es')\n\n"
    "Return ONLY valid JSON, no other text."
)


@observe(name="extract_metadata", as_type="generation")
async def extract_metadata(client: AsyncOpenAI, text: str) -> dict:
    truncated = text[:2000]

    response = await client.chat.completions.create(
        model=PRIMARY_MODEL,
        messages=[
            {"role": "system", "content": METADATA_PROMPT},
            {"role": "user", "content": truncated},
        ],
        temperature=0.2,
        max_tokens=512,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    try:
        metadata = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse metadata JSON: {raw}")
        metadata = {}

    return {
        "title": metadata.get("title", ""),
        "summary": metadata.get("summary", ""),
        "tags": metadata.get("tags", []),
        "language": metadata.get("language", "en"),
    }
