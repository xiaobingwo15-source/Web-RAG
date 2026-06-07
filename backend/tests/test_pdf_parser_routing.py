import asyncio

import app.services.pdf_parser as pdf_parser
from app.services.pdf_parser import PDFExtractionResult, PDFInspection


def _inspection(
    text: str,
    *,
    has_cjk: bool = False,
    table_like: bool = False,
    formula_like: bool = False,
) -> PDFInspection:
    return PDFInspection(
        page_count=1,
        text=text,
        page_texts=[text],
        text_page_count=1 if text.strip() else 0,
        char_count=len(text.strip()),
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
