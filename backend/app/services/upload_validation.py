import mimetypes
import re
from pathlib import PurePath
from typing import Protocol

from fastapi import HTTPException

from app.config import Settings

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
PDF_MIME_TYPE = "application/pdf"

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    # Phase 2.1: DOCX support
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    # Phase 2.2: Standalone image OCR
    "image/png",
    "image/jpeg",
    "image/tiff",
    "image/webp",
}

EXTENSION_MIME_TYPES = {
    ".csv": "text/csv",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".pdf": "application/pdf",
    ".text": "text/plain",
    ".txt": "text/plain",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    # Phase 2.1: DOCX support
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    # Phase 2.2: Standalone image OCR
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".webp": "image/webp",
    ".json": "text/plain",
    ".xml": "text/plain",
    ".html": "text/plain",
    ".htm": "text/plain",
    ".log": "text/plain",
    ".sql": "text/plain",
    ".yaml": "text/plain",
    ".yml": "text/plain",
}

OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


class AsyncUpload(Protocol):
    size: int | None

    async def read(self, size: int = -1) -> bytes: ...


def max_upload_bytes_for_mime(mime_type: str) -> int:
    if mime_type == PDF_MIME_TYPE:
        return Settings().pdf_max_bytes
    return MAX_UPLOAD_BYTES


def _size_limit_detail(mime_type: str, limit: int) -> str:
    size_mb = limit // (1024 * 1024)
    file_label = "PDF" if mime_type == PDF_MIME_TYPE else "File"
    return f"{file_label} is too large. Maximum upload size is {size_mb} MB."


def validate_upload_size(size: int, mime_type: str) -> None:
    limit = max_upload_bytes_for_mime(mime_type)
    if size > limit:
        raise HTTPException(status_code=413, detail=_size_limit_detail(mime_type, limit))


async def read_upload_bytes(file: AsyncUpload, mime_type: str) -> bytes:
    """Read no more than one byte past the applicable upload limit."""
    limit = max_upload_bytes_for_mime(mime_type)
    declared_size = getattr(file, "size", None)
    if declared_size is not None:
        validate_upload_size(int(declared_size), mime_type)

    file_bytes = await file.read(limit + 1)
    validate_upload_bytes(file_bytes, mime_type)
    return file_bytes


def sanitize_upload_filename(filename: str | None) -> str:
    name = PurePath(filename or "unnamed").name.strip()
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    name = name.replace("\\", "_").replace("/", "_").strip()
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Filename is required")
    if filename and name != filename:
        raise HTTPException(status_code=400, detail="Filename must not contain path components")
    return name


def resolve_upload_mime_type(filename: str, declared: str | None) -> str:
    safe_name = sanitize_upload_filename(filename)
    suffix = PurePath(safe_name).suffix.lower()
    if suffix in EXTENSION_MIME_TYPES:
        return EXTENSION_MIME_TYPES[suffix]

    declared_type = (declared or "").split(";", 1)[0].strip().lower()
    guessed, _ = mimetypes.guess_type(safe_name)
    if declared_type in ALLOWED_MIME_TYPES and guessed == declared_type:
        return declared_type
    raise HTTPException(status_code=415, detail="Unsupported file type")


def validate_upload_bytes(file_bytes: bytes, mime_type: str) -> None:
    validate_upload_size(len(file_bytes), mime_type)
    if mime_type == PDF_MIME_TYPE and not file_bytes.startswith(b"%PDF"):
        raise HTTPException(status_code=422, detail="PDF signature mismatch")
    if mime_type == PDF_MIME_TYPE:
        page_count = _pdf_page_count(file_bytes)
        max_pages = Settings().pdf_max_pages
        if page_count <= 0:
            raise HTTPException(status_code=422, detail="PDF contains no pages")
        if page_count > max_pages:
            raise HTTPException(
                status_code=422,
                detail=f"PDF has {page_count} pages, exceeding the {max_pages}-page limit.",
            )
    if mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" and not file_bytes.startswith(b"PK\x03\x04"):
        raise HTTPException(status_code=422, detail="XLSX signature mismatch")
    if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" and not file_bytes.startswith(b"PK\x03\x04"):
        raise HTTPException(status_code=422, detail="DOCX signature mismatch")
    if mime_type == "application/vnd.ms-excel" and not file_bytes.startswith(OLE_SIGNATURE):
        raise HTTPException(status_code=422, detail="XLS signature mismatch")
    # Image signature checks
    if mime_type == "image/png" and not file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(status_code=422, detail="PNG signature mismatch")
    if mime_type == "image/jpeg" and not file_bytes.startswith(b"\xff\xd8\xff"):
        raise HTTPException(status_code=422, detail="JPEG signature mismatch")
    if mime_type == "image/tiff" and not (file_bytes.startswith(b"II\x2a\x00") or file_bytes.startswith(b"MM\x00\x2a")):
        raise HTTPException(status_code=422, detail="TIFF signature mismatch")
    if mime_type == "image/webp" and not file_bytes.startswith(b"RIFF"):
        raise HTTPException(status_code=422, detail="WebP signature mismatch")
    if mime_type in {"text/plain", "text/markdown", "text/csv"}:
        if b"\x00" in file_bytes[:4096]:
            raise HTTPException(status_code=422, detail="Text file contains binary data")
        try:
            file_bytes[:4096].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=422, detail="Text file must be UTF-8 encoded") from exc


def _pdf_page_count(file_bytes: bytes) -> int:
    import pypdfium2 as pdfium

    doc = None
    try:
        doc = pdfium.PdfDocument(file_bytes)
        return len(doc)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="PDF is invalid or unreadable") from exc
    finally:
        if doc is not None:
            doc.close()

