import json
import logging
from google import genai
from google.genai import types
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
async def extract_metadata(client: genai.Client, text: str) -> dict:
    truncated = text[:2000]

    response = await client.aio.models.generate_content(
        model=PRIMARY_MODEL,
        contents=truncated,
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=512,
            response_mime_type="application/json",
            system_instruction=METADATA_PROMPT,
        ),
    )

    raw = response.candidates[0].content.parts[0].text
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
