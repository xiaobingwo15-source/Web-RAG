from types import SimpleNamespace

from app.services import database


class _Query:
    def __init__(self, data=None):
        self.data = data or []
        self.inserted = None
        self.updated = None
        self.filters = []

    def insert(self, payload):
        self.inserted = payload
        self.data = [payload]
        return self

    def update(self, payload):
        self.updated = payload
        self.data = [payload]
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def in_(self, key, value):
        self.filters.append((key, tuple(value)))
        return self

    def execute(self):
        return self


class _FakeDb:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        self.tables.setdefault(name, _Query())
        return self.tables[name]


def test_rag_eval_result_writes_explicit_result_status(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(database, "get_db", lambda: fake_db)

    result = database.insert_rag_eval_result(
        tenant_id="tenant-1",
        run_id="run-1",
        case={"id": "case-1", "question": "Q", "expected_facts": ["fact"]},
        answer="A",
        sources=[],
        score=SimpleNamespace(
            context_relevance_score=1.0,
            groundedness_score=1.0,
            answer_relevance_score=1.0,
            passed=True,
            failure_reason=None,
            citation_accuracy_score=None,
            recall_at_k=None,
        ),
    )

    assert result["passed"] is True
    assert result["result_status"] == "passed"


def test_retrieval_log_update_writes_grounding_status(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(database, "get_db", lambda: fake_db)

    database.update_retrieval_logs_for_answer(
        tenant_id="tenant-1",
        retrieval_log_ids=["log-1"],
        answer_message_id="msg-1",
        groundedness_score=0.2,
        groundedness_flag=True,
    )

    updated = fake_db.tables["retrieval_logs"].updated
    assert updated["groundedness_flag"] is True
    assert updated["grounding_status"] == "ungrounded"

