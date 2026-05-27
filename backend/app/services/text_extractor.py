import csv
import io
import logging

logger = logging.getLogger(__name__)

HEADER_REPEAT_ROWS = 20


def extract_text(file_bytes: bytes, mime_type: str) -> str:
    if mime_type == "application/pdf":
        return _extract_pdf(file_bytes)
    elif mime_type in ("text/plain", "text/markdown"):
        return _extract_text(file_bytes)
    elif mime_type == "text/csv":
        return _extract_csv(file_bytes)
    elif mime_type in (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    ):
        return _extract_excel(file_bytes)
    else:
        logger.warning(f"Unsupported mime type {mime_type}, treating as text")
        return _extract_text(file_bytes)


async def extract_text_with_ocr(file_bytes: bytes, mime_type: str, use_ocr: bool = False) -> str:
    if use_ocr and mime_type == "application/pdf":
        from app.services.ocr_service import ocr_with_llm
        from app.services.gemini import get_llm_client
        client = get_llm_client()
        return await ocr_with_llm(client, file_bytes)
    return extract_text(file_bytes, mime_type)


def _extract_text(file_bytes: bytes) -> str:
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1")


def _extract_csv(file_bytes: bytes) -> str:
    text = _extract_text(file_bytes)
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return ""

    header = rows[0]
    header_line = "\t".join(header)
    lines = [header_line]

    for i, row in enumerate(rows[1:], 1):
        lines.append("\t".join(row))
        if i % HEADER_REPEAT_ROWS == 0:
            lines.append("")
            lines.append(header_line)

    return "\n".join(lines)


def _extract_excel(file_bytes: bytes) -> str:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    all_text = []

    for sheet in wb.sheetnames:
        ws = wb[sheet]
        all_text.append(f"=== Sheet: {sheet} ===")

        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append([str(cell) if cell is not None else "" for cell in row])

        if not rows:
            continue

        header = rows[0]
        header_line = "\t".join(header)
        all_text.append(header_line)

        for i, row in enumerate(rows[1:], 1):
            all_text.append("\t".join(row))
            if i % HEADER_REPEAT_ROWS == 0:
                all_text.append("")
                all_text.append(header_line)

    wb.close()
    return "\n".join(all_text)


def _extract_pdf(file_bytes: bytes) -> str:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(file_bytes)
    pages = []
    for page in doc:
        textpage = page.get_textpage()
        text = textpage.get_text_range()
        if text.strip():
            pages.append(text)
    doc.close()
    return "\n\n".join(pages)
