from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.auth import get_current_user
from app.routers import documents


def test_upload_form_options_reach_ingestion_worker(monkeypatch):
    captured = {}

    async def fake_process_document_async(
        access_token,
        user_id,
        document_id,
        file_bytes,
        mime_type,
        use_ocr=False,
        pdf_parser_mode="auto",
        filename=None,
        tenant_id=None,
    ):
        captured.update(
            {
                "use_ocr": use_ocr,
                "pdf_parser_mode": pdf_parser_mode,
                "filename": filename,
                "mime_type": mime_type,
                "tenant_id": tenant_id,
            }
        )

    monkeypatch.setattr(documents, "check_rate_limit", lambda *args, **kwargs: None)

    async def fake_read_upload_bytes(file, _mime_type):
        return await file.read()

    monkeypatch.setattr(documents, "read_upload_bytes", fake_read_upload_bytes)
    monkeypatch.setattr(documents, "compute_content_hash", lambda file_bytes: "hash-1")
    monkeypatch.setattr(documents, "get_document_by_hash", lambda *args, **kwargs: None)
    monkeypatch.setattr(documents, "get_user_store", lambda *args, **kwargs: {"id": "store-1"})
    monkeypatch.setattr(documents, "log_operation", lambda **_kwargs: None)
    monkeypatch.setattr(
        documents,
        "create_document",
        lambda token, user_id, store_id, filename, mime_type, operation_name, tenant_id=None: {
            "id": "doc-1",
            "filename": filename,
        },
    )
    monkeypatch.setattr(documents, "process_document_async", fake_process_document_async)

    user = SimpleNamespace(
        id="user-1",
        access_token="token-1",
        role="admin",
        status="approved",
        tenant_id="tenant-1",
    )

    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: user
    app.include_router(documents.router, prefix="/api/documents")
    client = TestClient(app)

    response = client.post(
        "/api/documents/upload",
        data={"use_ocr": "true", "pdf_parser_mode": "unstructured"},
        files={"file": ("sample.pdf", b"%PDF-1.4\ncontent", "application/pdf")},
    )

    assert response.status_code == 200
    assert captured["use_ocr"] is True
    assert captured["pdf_parser_mode"] == "unstructured"
    assert captured["filename"] == "sample.pdf"
    assert captured["mime_type"] == "application/pdf"
    assert captured["tenant_id"] == "tenant-1"


def test_direct_upload_rejects_pdf_over_10_mb_before_database_work(monkeypatch):
    monkeypatch.setattr(documents, "check_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        documents,
        "compute_content_hash",
        lambda _payload: (_ for _ in ()).throw(AssertionError("oversized upload reached database work")),
    )
    user = SimpleNamespace(
        id="user-1",
        access_token="token-1",
        role="admin",
        status="approved",
        tenant_id="tenant-1",
    )
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: user
    app.include_router(documents.router, prefix="/api/documents")

    response = TestClient(app).post(
        "/api/documents/upload",
        files={
            "file": (
                "oversized.pdf",
                b"%PDF-1.4\n" + (b"x" * (10 * 1024 * 1024)),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 413
    assert "10 MB" in response.json()["detail"]
