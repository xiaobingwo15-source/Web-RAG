from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import upload_session
from app.services.upload_validation import (
    resolve_upload_mime_type,
    sanitize_upload_filename,
    validate_upload_bytes,
)


class _FakeUpload:
    def __init__(self, payload: bytes):
        self.payload = payload

    async def read(self):
        return self.payload


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

    with pytest.raises(HTTPException) as ctx:
        await upload_session.upload_chunk(
            "11111111-1111-1111-1111-111111111111",
            0,
            checksum="0" * 64,
            file=_FakeUpload(b"x" * 1026),
            user=SimpleNamespace(id="user-1", access_token="token-1"),
        )

    assert ctx.value.status_code == 413

