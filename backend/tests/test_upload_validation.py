from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import upload_session
from app.services import upload_validation
from app.services.upload_validation import (
    resolve_upload_mime_type,
    sanitize_upload_filename,
    validate_upload_bytes,
)


class _FakeUpload:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.read_sizes: list[int] = []

    async def read(self, size: int = -1):
        self.read_sizes.append(size)
        return self.payload if size < 0 else self.payload[:size]


def test_unsupported_file_type_fails():
    with pytest.raises(HTTPException) as ctx:
        resolve_upload_mime_type("payload.exe", "application/octet-stream")

    assert ctx.value.status_code == 415


def test_path_component_filename_fails():
    with pytest.raises(HTTPException) as ctx:
        sanitize_upload_filename("../secret.pdf")

    assert ctx.value.status_code == 400


def test_pdf_signature_mismatch_fails():
    with pytest.raises(HTTPException) as ctx:
        validate_upload_bytes(b"not a pdf", "application/pdf")

    assert ctx.value.status_code == 422


def test_pdf_upload_over_10_mb_fails_before_page_inspection(monkeypatch):
    monkeypatch.setattr(
        upload_validation,
        "_pdf_page_count",
        lambda _payload: pytest.fail("oversized PDFs must fail before parsing"),
        raising=False,
    )

    with pytest.raises(HTTPException) as ctx:
        validate_upload_bytes(
            b"%PDF-1.4\n" + (b"x" * (10 * 1024 * 1024)),
            "application/pdf",
        )

    assert ctx.value.status_code == 413
    assert "10 MB" in ctx.value.detail


def test_pdf_over_global_page_limit_fails_validation(monkeypatch):
    monkeypatch.setenv("PDF_MAX_PAGES", "100")
    monkeypatch.setattr(upload_validation, "_pdf_page_count", lambda _payload: 101, raising=False)

    with pytest.raises(HTTPException) as ctx:
        validate_upload_bytes(b"%PDF-1.4\n", "application/pdf")

    assert ctx.value.status_code == 422
    assert "101 pages" in ctx.value.detail
    assert "100-page limit" in ctx.value.detail


@pytest.mark.asyncio
async def test_upload_reader_never_buffers_more_than_pdf_limit():
    upload = _FakeUpload(b"%PDF-1.4\n" + (b"x" * (10 * 1024 * 1024)))

    with pytest.raises(HTTPException) as ctx:
        await upload_validation.read_upload_bytes(upload, "application/pdf")

    assert ctx.value.status_code == 413
    assert upload.read_sizes == [(10 * 1024 * 1024) + 1]


@pytest.mark.asyncio
async def test_chunk_checksum_mismatch_fails(monkeypatch):
    session = {
        "user_id": "user-1",
        "status": "uploading",
        "total_chunks": 1,
        "chunk_size": 1024,
    }
    monkeypatch.setattr(upload_session, "get_upload_session", lambda *_args: session)

    with pytest.raises(HTTPException) as ctx:
        await upload_session.upload_chunk(
            "11111111-1111-1111-1111-111111111111",
            0,
            checksum="0" * 64,
            file=_FakeUpload(b"abc"),
            user=SimpleNamespace(id="user-1", access_token="token-1"),
        )

    assert ctx.value.status_code == 422


@pytest.mark.asyncio
async def test_oversized_chunk_fails(monkeypatch):
    session = {
        "user_id": "user-1",
        "status": "uploading",
        "total_chunks": 1,
        "chunk_size": 1,
    }
    monkeypatch.setattr(upload_session, "get_upload_session", lambda *_args: session)

    upload = _FakeUpload(b"x" * 1026)
    with pytest.raises(HTTPException) as ctx:
        await upload_session.upload_chunk(
            "11111111-1111-1111-1111-111111111111",
            0,
            checksum="0" * 64,
            file=upload,
            user=SimpleNamespace(id="user-1", access_token="token-1"),
        )

    assert ctx.value.status_code == 413
    assert upload.read_sizes == [1026]


@pytest.mark.asyncio
async def test_chunked_pdf_session_rejects_over_10_mb_before_creation(monkeypatch):
    monkeypatch.setattr(upload_session, "check_rate_limit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        upload_session,
        "create_upload_session",
        lambda **_kwargs: pytest.fail("oversized PDF session must not be created"),
    )
    user = SimpleNamespace(
        id="user-1",
        access_token="token-1",
        role="admin",
        status="approved",
        tenant_id="tenant-1",
    )
    body = upload_session.InitUploadRequest(
        filename="oversized.pdf",
        mime_type="application/pdf",
        total_size=(10 * 1024 * 1024) + 1,
    )

    with pytest.raises(HTTPException) as ctx:
        await upload_session.init_upload(body, user=user)

    assert ctx.value.status_code == 413
    assert "10 MB" in ctx.value.detail
