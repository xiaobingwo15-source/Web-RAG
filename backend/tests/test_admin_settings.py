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
