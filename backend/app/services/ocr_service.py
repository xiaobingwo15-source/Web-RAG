import io
import logging
from google import genai
from google.genai import types
from langfuse import observe
from app.services.gemini import PRIMARY_MODEL

logger = logging.getLogger(__name__)

OCR_PROMPT = (
    "Extract ALL text from this page image. Preserve the original structure, "
    "including headings, paragraphs, lists, and table layouts. "
    "For tables, use markdown table format. "
    "Return only the extracted text, no commentary."
)


@observe(name="ocr_with_gemini", as_type="generation")
async def ocr_with_gemini(client: genai.Client, file_bytes: bytes) -> str:
    import pypdfium2 as pdfium

    logger.info("Converting PDF pages to images for OCR")
    doc = pdfium.PdfDocument(file_bytes)
    logger.info(f"PDF has {len(doc)} pages")

    all_text = []
    for i in range(len(doc)):
        logger.info(f"OCR processing page {i + 1}/{len(doc)}")

        page = doc[i]
        bitmap = page.render(scale=2)  # 2x scale for good quality
        pil_image = bitmap.to_pil()

        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        response = await client.aio.models.generate_content(
            model=PRIMARY_MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                OCR_PROMPT,
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=4096,
            ),
        )

        page_text = response.candidates[0].content.parts[0].text
        all_text.append(page_text)

    doc.close()
    return "\n\n--- Page Break ---\n\n".join(all_text)
