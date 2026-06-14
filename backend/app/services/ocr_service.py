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


async def _ocr_single_page(client: AsyncOpenAI, ocr_model: str, page, page_num: int) -> str:
    """OCR a single PDF page. Extracted for parallel execution."""
    import pypdfium2 as pdfium

    bitmap = None
    pil_image = None
    try:
        bitmap = page.render(scale=2)
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
        logger.info(f"OCR page {page_num}: extracted {len(page_text)} chars")
        return page_text
    finally:
        _close_quietly(pil_image)
        _close_quietly(bitmap)


# Phase 5.3: Max concurrent OCR pages to avoid rate limits
OCR_MAX_CONCURRENT = 5


@observe(name="ocr_with_llm", as_type="generation")
async def ocr_with_llm(client: AsyncOpenAI, file_bytes: bytes) -> str:
    """OCR all pages of a PDF using Gemini vision.

    Phase 5.3: Pages are processed concurrently (up to OCR_MAX_CONCURRENT)
    instead of sequentially, reducing latency for multi-page documents.
    """
    import asyncio
    import pypdfium2 as pdfium

    logger.info("Converting PDF pages to images for OCR")
    doc = pdfium.PdfDocument(file_bytes)
    ocr_model = Settings().get_ocr_model
    page_count = len(doc)
    logger.info(f"PDF has {page_count} pages, OCR model: {ocr_model}")

    semaphore = asyncio.Semaphore(OCR_MAX_CONCURRENT)

    async def _ocr_with_limit(page_idx: int) -> tuple[int, str]:
        async with semaphore:
            page = doc[page_idx]
            try:
                text = await _ocr_single_page(client, ocr_model, page, page_idx + 1)
                return page_idx, text
            finally:
                _close_quietly(page)

    try:
        if page_count == 1:
            # Single page: no parallelism needed
            page = doc[0]
            try:
                text = await _ocr_single_page(client, ocr_model, page, 1)
                return text
            finally:
                _close_quietly(page)
        else:
            # Multi-page: run concurrently with semaphore
            tasks = [_ocr_with_limit(i) for i in range(page_count)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Sort by page index, handle errors
            all_text = [""] * page_count
            for result in results:
                if isinstance(result, Exception):
                    logger.error("OCR page failed: %s", result)
                    continue
                idx, text = result
                all_text[idx] = text

            # Log summary
            success_count = sum(1 for t in all_text if t)
            logger.info(f"OCR completed: {success_count}/{page_count} pages extracted")
            return "\n\n--- Page Break ---\n\n".join(all_text)
    finally:
        doc.close()


IMAGE_OCR_PROMPT = (
    "Extract ALL text from this image. Preserve the original structure, "
    "including headings, paragraphs, lists, and table layouts. "
    "For tables, use markdown table format. "
    "Return only the extracted text, no commentary."
)


@observe(name="ocr_image_with_gemini", as_type="generation")
async def ocr_image_with_gemini(file_bytes: bytes, mime_type: str) -> str:
    """Run OCR on a standalone image file using Gemini vision.

    Args:
        file_bytes: Raw image bytes.
        mime_type: MIME type of the image (image/png, image/jpeg, etc.)

    Returns:
        Extracted text from the image.
    """
    from app.services.gemini import get_llm_client

    client = get_llm_client()
    ocr_model = Settings().get_ocr_model

    b64_image = base64.b64encode(file_bytes).decode("utf-8")

    logger.info("Running image OCR with model %s (%s, %d bytes)", ocr_model, mime_type, len(file_bytes))

    response = await client.chat.completions.create(
        model=ocr_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64_image}"},
                    },
                    {"type": "text", "text": IMAGE_OCR_PROMPT},
                ],
            },
        ],
        temperature=0.1,
        max_tokens=4096,
    )

    text = response.choices[0].message.content or ""
    logger.info("Image OCR extracted %d characters", len(text))
    return text
