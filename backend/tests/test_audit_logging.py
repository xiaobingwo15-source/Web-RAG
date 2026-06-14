from app.services import audit


class _FakeResult:
    data = [{"id": "audit-1"}]


class _FakeTable:
    def __init__(self):
        self.inserted = None

    def insert(self, payload):
        self.inserted = payload
        return self

    def execute(self):
        return _FakeResult()


class _FakeDb:
    def __init__(self):
        self.audit_table = _FakeTable()

    def table(self, name):
        assert name == "operation_audit_logs"
        return self.audit_table


def test_log_operation_redacts_sensitive_snapshots(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr("app.services.database.get_db", lambda: fake_db)

    audit.log_operation(
        tenant_id="tenant-1",
        actor_user_id="user-1",
        actor_email="admin@example.com",
        actor_role="admin",
        action="system_settings.update",
        resource_type="system_settings",
        resource_id="tenant-1",
        after={
            "OPENROUTER_API_KEY": "secret",
            "nested": {"access_token": "token"},
            "safe": "visible",
        },
        metadata={"raw_secret": "hidden", "safe": "ok"},
    )

    inserted = fake_db.audit_table.inserted
    assert inserted["after_snapshot"]["OPENROUTER_API_KEY"] == "[redacted]"
    assert inserted["after_snapshot"]["nested"]["access_token"] == "[redacted]"
    assert inserted["after_snapshot"]["safe"] == "visible"
    assert inserted["metadata"]["raw_secret"] == "[redacted]"
    assert inserted["metadata"]["safe"] == "ok"

