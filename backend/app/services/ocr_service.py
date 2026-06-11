import base64
import io
import logging
from openai import AsyncOpenAI
from langfuse import observe
from app.config import Settings

logger = logging.getLogger(__name__)

OCR_PROMPT = (
    "Extract ALL text from this page image. Preserve the original structure, "
    "including headings, paragraphs, lists, and table layouts. "
    "For tables, use markdown table format. "
    "Return only the extracted text, no commentary."
)


def _close_quietly(resource: object | None) -> None:
    close = getattr(resource, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            logger.debug("Failed to close OCR resource", exc_info=True)


@observe(name="ocr_with_llm", as_type="generation")
async def ocr_with_llm(client: AsyncOpenAI, file_bytes: bytes) -> str:
    import pypdfium2 as pdfium

    logger.info("Converting PDF pages to images for OCR")
    doc = pdfium.PdfDocument(file_bytes)
    ocr_model = Settings().get_ocr_model
    page_count = len(doc)
    logger.info(f"PDF has {page_count} pages, OCR model: {ocr_model}")

    all_text = []
    try:
        for i in range(page_count):
            logger.info(f"OCR processing page {i + 1}/{page_count}")

            page = None
            bitmap = None
            pil_image = None
            try:
                page = doc[i]
                bitmap = page.render(scale=2)  # 2x scale for good quality
                pil_image = bitmap.to_pil()

                with io.BytesIO() as buf:
                    pil_image.save(buf, format="PNG")
                    image_bytes = buf.getvalue()
                b64_image = base64.b64encode(image_bytes).decode("utf-8")
                del image_bytes

                response = await client.chat.completions.create(
                    model=ocr_model,
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
                del b64_image

                page_text = response.choices[0].message.content or ""
                all_text.append(page_text)
            finally:
                _close_quietly(pil_image)
                _close_quietly(bitmap)
                _close_quietly(page)
    finally:
        doc.close()

    return "\n\n--- Page Break ---\n\n".join(all_text)
