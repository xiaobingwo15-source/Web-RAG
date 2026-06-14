import threading
from unittest.mock import AsyncMock, patch

from app.services import database


class _Query:
    def __init__(self, data=None):
        self.data = data or []
        self.updated = None
        self.deleted = False
        self.filters = []

    def update(self, payload):
        self.updated = payload
        return self

    def delete(self):
        self.deleted = True
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def execute(self):
        return self


class _FakeDb:
    def __init__(self):
        self.tables = {
            "documents": _Query([{"id": "doc-1", "filename": "guide.pdf"}]),
            "document_chunks": _Query([]),
        }

    def table(self, name):
        return self.tables[name]


def test_archive_document_cleans_qdrant_vectors_from_worker_thread(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(database, "get_user_db", lambda _token: fake_db)

    cleanup = AsyncMock(return_value=3)
    result_holder = {}

    def run_archive():
        result_holder["doc"] = database.archive_document("token-1", "doc-1")

    with patch("app.services.qdrant_db.delete_chunks_by_document", new=cleanup):
        worker = threading.Thread(target=run_archive)
        worker.start()
        worker.join()

    assert result_holder["doc"]["id"] == "doc-1"
    cleanup.assert_awaited_once_with("doc-1")
    assert fake_db.tables["document_chunks"].deleted is True
