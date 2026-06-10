from __future__ import annotations

import asyncio
import io
import logging
import re
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Literal

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

PDFParserMode = Literal["auto", "pypdfium", "unstructured", "mineru", "ocr"]
PDF_PARSER_MODES: set[str] = {"auto", "pypdfium", "unstructured", "mineru", "ocr"}


class PDFParserUnavailable(RuntimeError):
    """Raised when a configured PDF parser cannot run in this environment."""


class PDFParserFailed(RuntimeError):
    """Raised when a PDF parser runs but cannot produce usable output."""


@dataclass
class PDFInspection:
    page_count: int = 0
    text: str = ""
    page_texts: list[str] = field(default_factory=list)
    text_page_count: int = 0
    char_count: int = 0
    has_cjk: bool = False
    table_like: bool = False
    formula_like: bool = False


@dataclass
class PDFExtractionResult:
    text: str
    parser: str
    requested_mode: str
    metadata: dict = field(default_factory=dict)


def normalize_pdf_parser_mode(mode: str | None) -> PDFParserMode:
    normalized = (mode or "auto").strip().lower()
    if normalized not in PDF_PARSER_MODES:
        return "auto"
    return normalized  # type: ignore[return-value]


async def extract_pdf(
    file_bytes: bytes,
    parser_mode: str | None = "auto",
    use_ocr: bool = False,
    filename: str | None = None,
) -> PDFExtractionResult:
    requested_mode = normalize_pdf_parser_mode(parser_mode)
    inspection = _inspect_pdf(file_bytes)
    planned_mode = "ocr" if use_ocr else _choose_mode(requested_mode, inspection)
    warnings: list[str] = []

    for mode in _candidate_modes(planned_mode):
        try:
            result = await _run_parser(mode, file_bytes, requested_mode, inspection, filename)
        except PDFParserUnavailable as exc:
            warnings.append(_parser_warning(mode, "unavailable", exc))
            continue
        except Exception as exc:
            warnings.append(_parser_warning(mode, "failed", exc))
            continue

        result.metadata = _build_metadata(
            result=result,
            inspection=inspection,
            requested_mode=requested_mode,
            planned_mode=planned_mode,
            warnings=warnings,
        )
        return result

    raise PDFParserFailed("No PDF parser produced text. " + " | ".join(warnings))


def _parser_warning(mode: str, status: str, exc: Exception) -> str:
    return f"{mode} {status}: {_friendly_parser_error(mode, exc)}"


def _friendly_parser_error(mode: str, exc: Exception) -> str:
    raw = " ".join(str(exc).split())
    lower = raw.lower()

    if mode == "ocr" and "no endpoints found" in lower:
        return "OCR model is unavailable; configure OCR_MODEL to a supported vision model"
    if "rate limit" in lower or "429" in lower:
        return "provider rate limit reached"
    if "api key" in lower or "401" in lower or "403" in lower:
        return "provider credentials are missing or invalid"
    if "timeout" in lower or "timed out" in lower:
        return "provider request timed out"
    if (
        "user_id" in lower
        or "{'error'" in lower
        or '{"error"' in lower
        or "error code:" in lower
    ):
        return "provider request failed"

    redacted = re.sub(r"user_[A-Za-z0-9]+", "[redacted]", raw)
    if len(redacted) > 220:
        return f"{redacted[:217].rstrip()}..."
    return redacted or exc.__class__.__name__


async def _run_parser(
    mode: str,
    file_bytes: bytes,
    requested_mode: str,
    inspection: PDFInspection,
    filename: str | None,
) -> PDFExtractionResult:
    if mode == "pypdfium":
        return _extract_pdf_pypdfium(inspection, requested_mode)
    if mode == "unstructured":
        return _extract_pdf_unstructured(file_bytes, requested_mode)
    if mode == "mineru":
        return await _extract_pdf_mineru(file_bytes, requested_mode, filename)
    if mode == "ocr":
        return await _extract_pdf_ocr(file_bytes, requested_mode)
    raise PDFParserUnavailable(f"unsupported parser mode: {mode}")


def _candidate_modes(planned_mode: str) -> list[str]:
    fallback_order = {
        "mineru": ["mineru", "unstructured", "pypdfium", "ocr"],
        "unstructured": ["unstructured", "pypdfium", "ocr"],
        "pypdfium": ["pypdfium", "ocr"],
        "ocr": ["ocr", "pypdfium"],
    }
    return fallback_order.get(planned_mode, ["pypdfium", "ocr"])


def _choose_mode(requested_mode: str, inspection: PDFInspection) -> str:
    if requested_mode != "auto":
        return requested_mode
    if inspection.has_cjk and (inspection.table_like or inspection.formula_like):
        return "mineru"
    if inspection.table_like:
        return "unstructured"
    if inspection.char_count < 80 or inspection.text_page_count == 0:
        return "ocr"
    return "pypdfium"


def _inspect_pdf(file_bytes: bytes) -> PDFInspection:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(file_bytes)
    try:
        page_texts: list[str] = []
        for page in doc:
            textpage = page.get_textpage()
            page_texts.append(textpage.get_text_range() or "")
    finally:
        page_count = len(doc)
        doc.close()

    text = "\n\n".join(page_texts)
    return PDFInspection(
        page_count=page_count,
        text=text,
        page_texts=page_texts,
        text_page_count=sum(1 for page_text in page_texts if page_text.strip()),
        char_count=len(text.strip()),
        has_cjk=bool(re.search(r"[\u3400-\u9fff]", text)),
        table_like=_looks_table_like(text),
        formula_like=_looks_formula_like(text),
    )


def _looks_table_like(text: str) -> bool:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if any("|" in line and line.count("|") >= 2 for line in lines):
        return True
    structured_rows = 0
    for line in lines:
        if "\t" in line and len([cell for cell in line.split("\t") if cell.strip()]) >= 3:
            structured_rows += 1
        elif len(re.split(r"\s{2,}", line.strip())) >= 3:
            structured_rows += 1
    return structured_rows >= 3


def _looks_formula_like(text: str) -> bool:
    return bool(re.search(r"(?:[=∑√∞≤≥≈∫]|\\frac|\\sum|\\begin\{equation\})", text))


def _extract_pdf_pypdfium(
    inspection: PDFInspection,
    requested_mode: str,
) -> PDFExtractionResult:
    pages = []
    for index, page_text in enumerate(inspection.page_texts, start=1):
        if page_text.strip():
            pages.append(f"## Page {index}\n\n{page_text.strip()}")
    text = "\n\n".join(pages).strip()
    if not text:
        raise PDFParserFailed("pypdfium extracted no text")
    return PDFExtractionResult(
        text=text,
        parser="pypdfium",
        requested_mode=requested_mode,
        metadata={"tables_detected": int(inspection.table_like)},
    )


def _extract_pdf_unstructured(file_bytes: bytes, requested_mode: str) -> PDFExtractionResult:
    try:
        from unstructured.partition.pdf import partition_pdf
    except ImportError as exc:
        raise PDFParserUnavailable("install unstructured[pdf] to enable this parser") from exc

    elements = partition_pdf(
        file=io.BytesIO(file_bytes),
        strategy="hi_res",
        infer_table_structure=True,
    )
    text, tables_detected, page_numbers = _elements_to_markdown(elements)
    if not text.strip():
        raise PDFParserFailed("unstructured extracted no text")
    return PDFExtractionResult(
        text=text,
        parser="unstructured",
        requested_mode=requested_mode,
        metadata={
            "tables_detected": tables_detected,
            "page_numbers": page_numbers,
        },
    )


async def _extract_pdf_mineru(
    file_bytes: bytes,
    requested_mode: str,
    filename: str | None,
) -> PDFExtractionResult:
    settings = Settings()
    if not settings.mineru_agent_enabled:
        raise PDFParserUnavailable("MINERU_AGENT_ENABLED is not true")
    if len(file_bytes) > settings.mineru_agent_max_bytes:
        raise PDFParserUnavailable("file is larger than the MinerU agent limit")

    base_url = settings.mineru_agent_base_url.rstrip("/")
    task_payload = {
        "file_name": filename or "document.pdf",
        "language": settings.mineru_language,
        "enable_table": True,
        "enable_formula": True,
        "is_ocr": False,
    }
    timeout = httpx.Timeout(timeout=60.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        task_resp = await client.post(f"{base_url}/parse/file", json=task_payload)
        task_resp.raise_for_status()
        task_data = task_resp.json()
        if task_data.get("code") != 0:
            raise PDFParserFailed(task_data.get("msg") or "MinerU task creation failed")

        data = task_data.get("data") or {}
        task_id = data.get("task_id")
        file_url = data.get("file_url")
        if not task_id or not file_url:
            raise PDFParserFailed("MinerU did not return task_id and file_url")

        upload_resp = await client.put(file_url, content=file_bytes)
        if upload_resp.status_code not in (200, 201):
            raise PDFParserFailed(f"MinerU upload failed: HTTP {upload_resp.status_code}")

        markdown = await _poll_mineru_markdown(client, base_url, task_id, settings)

    if not markdown.strip():
        raise PDFParserFailed("MinerU returned empty Markdown")
    return PDFExtractionResult(
        text=markdown.strip(),
        parser="mineru",
        requested_mode=requested_mode,
        metadata={"tables_detected": int(_looks_table_like(markdown))},
    )


async def _poll_mineru_markdown(
    client: httpx.AsyncClient,
    base_url: str,
    task_id: str,
    settings: Settings,
) -> str:
    start = time.monotonic()
    while time.monotonic() - start < settings.mineru_poll_timeout_seconds:
        result_resp = await client.get(f"{base_url}/parse/{task_id}")
        result_resp.raise_for_status()
        result = result_resp.json()
        data = result.get("data") or {}
        state = data.get("state")
        if state == "done":
            markdown_url = data.get("markdown_url")
            if not markdown_url:
                raise PDFParserFailed("MinerU completed without markdown_url")
            markdown_resp = await client.get(markdown_url)
            markdown_resp.raise_for_status()
            return markdown_resp.text
        if state == "failed":
            raise PDFParserFailed(data.get("err_msg") or "MinerU parsing failed")
        await asyncio.sleep(settings.mineru_poll_interval_seconds)
    raise PDFParserFailed("MinerU polling timed out")


async def _extract_pdf_ocr(file_bytes: bytes, requested_mode: str) -> PDFExtractionResult:
    from app.services.gemini import get_llm_client
    from app.services.ocr_service import ocr_with_llm

    client = get_llm_client()
    text = await ocr_with_llm(client, file_bytes)
    if not text.strip():
        raise PDFParserFailed("OCR extracted no text")
    return PDFExtractionResult(
        text=text,
        parser="ocr",
        requested_mode=requested_mode,
        metadata={"tables_detected": int(_looks_table_like(text))},
    )


def _elements_to_markdown(elements: list[object]) -> tuple[str, int, list[int]]:
    parts: list[str] = []
    current_page: int | None = None
    tables_detected = 0
    page_numbers: list[int] = []

    for element in elements:
        metadata = getattr(element, "metadata", None)
        page_number = int(getattr(metadata, "page_number", 0) or 0)
        if page_number and page_number != current_page:
            current_page = page_number
            page_numbers.append(page_number)
            parts.append(f"## Page {page_number}")

        category = str(getattr(element, "category", "") or "").lower()
        raw_text = str(element).strip()
        if not raw_text and category != "table":
            continue

        if category == "table":
            tables_detected += 1
            html = str(getattr(metadata, "text_as_html", "") or "")
            table_text = _html_table_to_markdown(html) if html else raw_text
            if table_text.strip():
                parts.append(table_text.strip())
            continue

        if category in {"title", "header"}:
            parts.append(f"### {raw_text}")
        elif category == "listitem":
            parts.append(f"- {raw_text}")
        else:
            parts.append(raw_text)

    return "\n\n".join(part for part in parts if part.strip()).strip(), tables_detected, page_numbers


class _SimpleTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._current_row = []
        elif tag in {"td", "th"} and self._current_row is not None:
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._current_cell is not None and self._current_row is not None:
            cell_text = " ".join("".join(self._current_cell).split())
            self._current_row.append(cell_text)
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            if any(cell.strip() for cell in self._current_row):
                self.rows.append(self._current_row)
            self._current_row = None


def _html_table_to_markdown(html: str) -> str:
    parser = _SimpleTableParser()
    parser.feed(html)
    rows = parser.rows
    if not rows:
        return ""
    column_count = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (column_count - len(row)) for row in rows]
    header = normalized_rows[0]
    separator = ["---"] * column_count
    markdown_rows = [header, separator, *normalized_rows[1:]]
    return "\n".join("| " + " | ".join(row) + " |" for row in markdown_rows)


def _build_metadata(
    result: PDFExtractionResult,
    inspection: PDFInspection,
    requested_mode: str,
    planned_mode: str,
    warnings: list[str],
) -> dict:
    text = result.text or ""
    parser_warnings = list(warnings)
    if result.parser == "pypdfium" and inspection.table_like:
        parser_warnings.append("tables may be flattened; try unstructured or mineru for better layout preservation")

    metadata = {
        "pdf_parser": result.parser,
        "pdf_parser_requested": requested_mode,
        "pdf_parser_planned": planned_mode,
        "pdf_page_count": inspection.page_count,
        "pdf_text_page_count": inspection.text_page_count,
        "extracted_char_count": len(text),
        "tables_detected": int(result.metadata.get("tables_detected", 0)),
    }
    if result.metadata.get("page_numbers"):
        metadata["page_numbers"] = result.metadata["page_numbers"]
    if parser_warnings:
        metadata["extraction_quality_warning"] = "; ".join(parser_warnings)
    return metadata
