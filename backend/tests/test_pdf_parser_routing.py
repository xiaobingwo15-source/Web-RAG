import asyncio
import sys
from types import SimpleNamespace

import pytest

import app.services.pdf_parser as pdf_parser
from app.services.pdf_parser import PDFExtractionResult, PDFInspection


def _inspection(
    text: str,
    *,
    has_cjk: bool = False,
    table_like: bool = False,
    formula_like: bool = False,
    page_count: int = 1,
    text_page_count: int | None = None,
) -> PDFInspection:
    page_texts = [text] * page_count
    full_text = "\n\n".join(page_texts)
    return PDFInspection(
        page_count=page_count,
        text=full_text,
        page_texts=page_texts,
        text_page_count=(
            text_page_count
            if text_page_count is not None
            else sum(1 for page_text in page_texts if page_text.strip())
        ),
        char_count=len(full_text.strip()),
        has_cjk=has_cjk,
        table_like=table_like,
        formula_like=formula_like,
    )


def test_auto_routes_clean_digital_pdf_to_pypdfium(monkeypatch):
    monkeypatch.setattr(pdf_parser, "_inspect_pdf", lambda _: _inspection("A clean digital PDF " * 20))

    def fake_pypdfium(inspection, requested_mode):
        return PDFExtractionResult("clean text", "pypdfium", requested_mode)

    monkeypatch.setattr(pdf_parser, "_extract_pdf_pypdfium", fake_pypdfium)

    result = asyncio.run(pdf_parser.extract_pdf(b"%PDF", parser_mode="auto"))

    assert result.parser == "pypdfium"
    assert result.metadata["pdf_parser"] == "pypdfium"


def test_auto_routes_table_layout_pdf_to_unstructured(monkeypatch):
    monkeypatch.setattr(
        pdf_parser,
        "_inspect_pdf",
        lambda _: _inspection("Name  Qty  Price\nA     2    10\nB     4    20", table_like=True),
    )

    def fake_unstructured(file_bytes, requested_mode):
        return PDFExtractionResult("| Name | Qty |\n| --- | --- |\n| A | 2 |", "unstructured", requested_mode)

    monkeypatch.setattr(pdf_parser, "_extract_pdf_unstructured", fake_unstructured)

    result = asyncio.run(pdf_parser.extract_pdf(b"%PDF", parser_mode="auto"))

    assert result.parser == "unstructured"
    assert result.metadata["pdf_parser_planned"] == "unstructured"


def test_auto_routes_complex_chinese_pdf_to_mineru(monkeypatch):
    monkeypatch.setattr(
        pdf_parser,
        "_inspect_pdf",
        lambda _: _inspection("复杂表格  数量  公式\n项目A  2  x=1", has_cjk=True, table_like=True, formula_like=True),
    )

    async def fake_mineru(file_bytes, requested_mode, filename):
        return PDFExtractionResult("## 表格\n\n| 项目 | 数量 |", "mineru", requested_mode)

    monkeypatch.setattr(pdf_parser, "_extract_pdf_mineru", fake_mineru)

    result = asyncio.run(pdf_parser.extract_pdf(b"%PDF", parser_mode="auto", filename="cn.pdf"))

    assert result.parser == "mineru"
    assert result.metadata["pdf_parser_planned"] == "mineru"


def test_auto_routes_image_only_pdf_to_ocr(monkeypatch):
    monkeypatch.setattr(pdf_parser, "_inspect_pdf", lambda _: _inspection(""))

    async def fake_ocr(file_bytes, requested_mode):
        return PDFExtractionResult("OCR text", "ocr", requested_mode)

    monkeypatch.setattr(pdf_parser, "_extract_pdf_ocr", fake_ocr)

    result = asyncio.run(pdf_parser.extract_pdf(b"%PDF", parser_mode="auto"))

    assert result.parser == "ocr"
    assert result.metadata["pdf_parser_planned"] == "ocr"


def test_ocr_failure_falls_back_to_pypdfium_with_sanitized_warning(monkeypatch):
    monkeypatch.setattr(pdf_parser, "_inspect_pdf", lambda _: _inspection("Digital fallback text"))

    async def fake_ocr(file_bytes, requested_mode):
        raise RuntimeError(
            "Error code: 404 - {'error': {'message': 'No endpoints found for "
            "google/gemini-2.0-flash-001.'}, 'user_id': 'user_secret'}"
        )

    def fake_pypdfium(inspection, requested_mode):
        return PDFExtractionResult("Digital fallback text", "pypdfium", requested_mode)

    monkeypatch.setattr(pdf_parser, "_extract_pdf_ocr", fake_ocr)
    monkeypatch.setattr(pdf_parser, "_extract_pdf_pypdfium", fake_pypdfium)

    result = asyncio.run(pdf_parser.extract_pdf(b"%PDF", parser_mode="auto", use_ocr=True))

    assert result.parser == "pypdfium"
    warning = result.metadata["extraction_quality_warning"]
    assert "OCR model is unavailable" in warning
    assert "No endpoints found" not in warning
    assert "user_id" not in warning
    assert "user_secret" not in warning


def test_large_text_pdf_forced_ocr_uses_pypdfium_with_warning(monkeypatch):
    monkeypatch.setenv("PDF_OCR_MAX_PAGES", "20")
    monkeypatch.setattr(
        pdf_parser,
        "_inspect_pdf",
        lambda *_args, **_kwargs: _inspection("Digital text page", page_count=80),
    )

    async def fake_ocr(file_bytes, requested_mode):
        raise AssertionError("OCR should not render over-limit text PDFs")

    def fake_pypdfium(inspection, requested_mode):
        return PDFExtractionResult("Digital text page", "pypdfium", requested_mode)

    monkeypatch.setattr(pdf_parser, "_extract_pdf_ocr", fake_ocr)
    monkeypatch.setattr(pdf_parser, "_extract_pdf_pypdfium", fake_pypdfium)

    result = asyncio.run(pdf_parser.extract_pdf(b"%PDF", parser_mode="auto", use_ocr=True))

    assert result.parser == "pypdfium"
    assert result.metadata["pdf_parser_planned"] == "pypdfium"
    assert "PDF OCR skipped" in result.metadata["extraction_quality_warning"]


def test_large_image_only_pdf_over_ocr_limit_fails_before_ocr(monkeypatch):
    monkeypatch.setenv("PDF_OCR_MAX_PAGES", "20")
    monkeypatch.setattr(
        pdf_parser,
        "_inspect_pdf",
        lambda _: _inspection("", page_count=21),
    )

    async def fake_ocr(file_bytes, requested_mode):
        raise AssertionError("OCR should not render over-limit image-only PDFs")

    monkeypatch.setattr(pdf_parser, "_extract_pdf_ocr", fake_ocr)

    with pytest.raises(pdf_parser.PDFParserFailed, match="too many pages"):
        asyncio.run(pdf_parser.extract_pdf(b"%PDF", parser_mode="auto", use_ocr=True))


def test_large_unstructured_pdf_falls_back_to_pypdfium(monkeypatch):
    monkeypatch.setenv("PDF_LAYOUT_MAX_PAGES", "30")
    monkeypatch.setattr(
        pdf_parser,
        "_inspect_pdf",
        lambda _: _inspection(
            "Name  Qty  Price\nA     2    10",
            table_like=True,
            page_count=31,
        ),
    )

    def fake_unstructured(file_bytes, requested_mode):
        raise AssertionError("unstructured should not run over the layout page limit")

    def fake_pypdfium(inspection, requested_mode):
        return PDFExtractionResult("Name Qty Price\nA 2 10", "pypdfium", requested_mode)

    monkeypatch.setattr(pdf_parser, "_extract_pdf_unstructured", fake_unstructured)
    monkeypatch.setattr(pdf_parser, "_extract_pdf_pypdfium", fake_pypdfium)

    result = asyncio.run(pdf_parser.extract_pdf(b"%PDF", parser_mode="unstructured"))

    assert result.parser == "pypdfium"
    assert result.metadata["pdf_parser_planned"] == "pypdfium"
    assert "layout parser skipped" in result.metadata["extraction_quality_warning"]


def test_global_page_limit_fails_before_any_page_text_is_loaded(monkeypatch):
    instances = []

    class FakePdfDocument:
        def __init__(self, _payload):
            self.closed = False
            instances.append(self)

        def __len__(self):
            return 101

        def __iter__(self):
            raise AssertionError("page text must not be loaded after the count exceeds the limit")

        def close(self):
            self.closed = True

    monkeypatch.setenv("PDF_MAX_PAGES", "100")
    monkeypatch.setitem(sys.modules, "pypdfium2", SimpleNamespace(PdfDocument=FakePdfDocument))

    with pytest.raises(pdf_parser.PDFParserFailed, match=r"101 pages.*100-page limit"):
        asyncio.run(pdf_parser.extract_pdf(b"%PDF-1.4\n"))

    assert instances[0].closed is True


def test_pdf_inspection_closes_each_native_page_resource(monkeypatch):
    instances = []

    class FakeTextPage:
        closed = False

        def get_text_range(self):
            return "safe page text"

        def close(self):
            self.closed = True

    class FakePage:
        closed = False

        def __init__(self):
            self.text_page = FakeTextPage()

        def get_textpage(self):
            return self.text_page

        def close(self):
            self.closed = True

    class FakePdfDocument:
        closed = False

        def __init__(self, _payload):
            self.page = FakePage()
            instances.append(self)

        def __len__(self):
            return 1

        def __iter__(self):
            yield self.page

        def close(self):
            self.closed = True

    monkeypatch.setenv("PDF_MAX_PAGES", "100")
    monkeypatch.setitem(sys.modules, "pypdfium2", SimpleNamespace(PdfDocument=FakePdfDocument))

    inspection = pdf_parser._inspect_pdf(b"%PDF-1.4\n")

    assert inspection.page_count == 1
    assert inspection.page_texts == ["safe page text"]
    assert inspection.text == ""
    assert instances[0].page.text_page.closed is True
    assert instances[0].page.closed is True
    assert instances[0].closed is True


def test_high_page_fallback_never_enters_layout_or_ocr_parsers(monkeypatch):
    monkeypatch.setenv("PDF_MAX_PAGES", "100")
    monkeypatch.setenv("PDF_OCR_MAX_PAGES", "20")
    monkeypatch.setenv("PDF_LAYOUT_MAX_PAGES", "30")
    monkeypatch.setattr(
        pdf_parser,
        "_inspect_pdf",
        lambda *_args, **_kwargs: _inspection(
            "复杂表格  数量  公式\n项目A  2  x=1",
            has_cjk=True,
            table_like=True,
            formula_like=True,
            page_count=40,
        ),
    )
    attempted = []

    async def fake_mineru(file_bytes, requested_mode, filename):
        attempted.append("mineru")
        raise pdf_parser.PDFParserUnavailable("disabled")

    def fake_unstructured(file_bytes, requested_mode):
        attempted.append("unstructured")
        raise pdf_parser.PDFParserUnavailable("must be page-guarded")

    def fake_pypdfium(inspection, requested_mode):
        attempted.append("pypdfium")
        return PDFExtractionResult("safe text", "pypdfium", requested_mode)

    async def fake_ocr(file_bytes, requested_mode):
        attempted.append("ocr")
        return PDFExtractionResult("unsafe OCR", "ocr", requested_mode)

    monkeypatch.setattr(pdf_parser, "_extract_pdf_mineru", fake_mineru)
    monkeypatch.setattr(pdf_parser, "_extract_pdf_unstructured", fake_unstructured)
    monkeypatch.setattr(pdf_parser, "_extract_pdf_pypdfium", fake_pypdfium)
    monkeypatch.setattr(pdf_parser, "_extract_pdf_ocr", fake_ocr)

    result = asyncio.run(pdf_parser.extract_pdf(b"%PDF", parser_mode="auto"))

    assert result.parser == "pypdfium"
    assert attempted == ["mineru", "pypdfium"]
    assert "layout parser skipped" in result.metadata["extraction_quality_warning"]
