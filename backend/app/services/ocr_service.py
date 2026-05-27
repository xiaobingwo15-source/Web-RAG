import base64
import io
import logging
from openai import AsyncOpenAI
from langfuse import observe
from app.services.gemini import PRIMARY_MODEL

logger = logging.getLogger(__name__)

OCR_PROMPT = (
    "Extract ALL text from this page image. Preserve the original structure, "
    "including headings, paragraphs, lists, and table layouts. "
    "For tables, use markdown table format. "
    "Return only the extracted text, no commentary."
)


@observe(name="ocr_with_llm", as_type="generation")
async def ocr_with_llm(client: AsyncOpenAI, file_bytes: bytes) -> str:
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
        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        response = await client.chat.completions.create(
            model=PRIMARY_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64_image}"},
                        },
                        {"type": "text", "text": OCR_PROMPT},
                    ],
                },
            ],
            temperature=0.1,
            max_tokens=4096,
        )

        page_text = response.choices[0].message.content or ""
        all_text.append(page_text)

    doc.close()
    return "\n\n--- Page Break ---\n\n".join(all_text)
