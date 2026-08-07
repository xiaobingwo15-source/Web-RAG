from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import DEFAULT_OCR_MODEL
from app.middleware.auth import get_current_user
from app.routers import admin


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeTable:
    def __init__(self, db):
        self.db = db
        self.payload = None

    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def upsert(self, payload):
        self.payload = payload
        return self

    def execute(self):
        if self.payload is not None:
            self.db.settings[self.payload["key"]] = self.payload["value"]
            self.db.upserts.append(self.payload)
            return FakeResult([self.payload])
        rows = [{"key": key, "value": value} for key, value in self.db.settings.items()]
        return FakeResult(rows)


class FakeDb:
    def __init__(self, settings):
        self.settings = dict(settings)
        self.upserts = []

    def table(self, name):
        assert name == "system_settings"
        return FakeTable(self)


def _client(monkeypatch, fake_db):
    user = SimpleNamespace(
        id="admin-1",
        access_token="token-1",
        role="admin",
        status="approved",
        tenant_id="tenant-1",
    )
    monkeypatch.setattr("app.services.database.get_user_db", lambda _token: fake_db)
    monkeypatch.setattr(admin, "log_operation", lambda **_kwargs: None)

    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: user
    app.include_router(admin.router, prefix="/api/admin")
    return TestClient(app)


def test_admin_settings_returns_normalized_ocr_model(monkeypatch):
    fake_db = FakeDb({"OCR_MODEL": "google/gemini-2.0-flash-001"})
    client = _client(monkeypatch, fake_db)

    response = client.get("/api/admin/settings")

    assert response.status_code == 200
    assert response.json()["OCR_MODEL"] == DEFAULT_OCR_MODEL


def test_admin_settings_saves_normalized_ocr_model(monkeypatch):
    fake_db = FakeDb({})
    client = _client(monkeypatch, fake_db)

    response = client.post(
        "/api/admin/settings",
        json={"OCR_MODEL": "google/gemini-2.0-flash-001"},
    )

    assert response.status_code == 200
    assert fake_db.settings["OCR_MODEL"] == DEFAULT_OCR_MODEL


def test_admin_settings_returns_pdf_page_limits(monkeypatch):
    fake_db = FakeDb({"PDF_OCR_MAX_PAGES": "12", "PDF_LAYOUT_MAX_PAGES": "18"})
    client = _client(monkeypatch, fake_db)

    response = client.get("/api/admin/settings")

    assert response.status_code == 200
    assert response.json()["PDF_OCR_MAX_PAGES"] == "12"
    assert response.json()["PDF_LAYOUT_MAX_PAGES"] == "18"


def test_admin_settings_never_returns_any_secret_value_characters(monkeypatch):
    fake_db = FakeDb({
        "OPENROUTER_API_KEY": "tenant-secret-prefix-and-suffix",
        "LANGFUSE_SECRET_KEY": "langfuse-secret-value",
    })
    client = _client(monkeypatch, fake_db)

    response = client.get("/api/admin/settings")

    assert response.status_code == 200
    assert response.json()["OPENROUTER_API_KEY"] == "[redacted]"
    assert response.json()["LANGFUSE_SECRET_KEY"] == "[redacted]"
    assert "tenant-secret" not in response.text
    assert "langfuse-secret" not in response.text


def test_admin_settings_does_not_persist_environment_owned_infrastructure(monkeypatch):
    fake_db = FakeDb({})
    client = _client(monkeypatch, fake_db)

    response = client.post(
        "/api/admin/settings",
        json={
            "GOOGLE_API_KEY": "tenant-google-key",
            "QDRANT_URL": "https://tenant-qdrant.invalid",
            "QDRANT_API_KEY": "tenant-qdrant-key",
        },
    )

    assert response.status_code == 200
    assert fake_db.upserts == []


def test_admin_settings_failure_diagnostics_do_not_echo_secret_values(
    monkeypatch,
    caplog,
):
    fake_db = FakeDb({})

    class FailingTable(FakeTable):
        def upsert(self, payload):
            raise RuntimeError(f"database rejected {payload['value']}")

    monkeypatch.setattr(
        fake_db,
        "table",
        lambda name: FailingTable(fake_db),
    )
    client = _client(monkeypatch, fake_db)

    response = client.post(
        "/api/admin/settings",
        json={"OPENROUTER_API_KEY": "tenant-secret-value"},
    )

    assert response.status_code == 500
    assert "tenant-secret-value" not in response.text
    assert "tenant-secret-value" not in caplog.text


def test_admin_settings_saves_pdf_page_limits(monkeypatch):
    fake_db = FakeDb({})
    client = _client(monkeypatch, fake_db)

    response = client.post(
        "/api/admin/settings",
        json={"PDF_OCR_MAX_PAGES": "7", "PDF_LAYOUT_MAX_PAGES": "11"},
    )

    assert response.status_code == 200
    assert fake_db.settings["PDF_OCR_MAX_PAGES"] == "7"
    assert fake_db.settings["PDF_LAYOUT_MAX_PAGES"] == "11"


def test_admin_settings_rejects_invalid_pdf_page_limit(monkeypatch):
    fake_db = FakeDb({})
    client = _client(monkeypatch, fake_db)

    response = client.post(
        "/api/admin/settings",
        json={"PDF_OCR_MAX_PAGES": "-1"},
    )

    assert response.status_code == 400
