import unittest
from unittest.mock import Mock, patch

from app.services import database


class FakeQuery:
    def __init__(self, rows):
        self.rows = list(rows)

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, key, value):
        self.rows = [row for row in self.rows if row.get(key) == value]
        return self

    def neq(self, key, value):
        self.rows = [row for row in self.rows if row.get(key) != value]
        return self

    def order(self, key, desc=False):
        self.rows = sorted(self.rows, key=lambda row: row.get(key) or "", reverse=desc)
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    def execute(self):
        return type("Result", (), {"data": self.rows})()


class FakeDb:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return FakeQuery(self.tables[name])


class AdminDatabaseTests(unittest.TestCase):
    def test_get_tenant_admin_user_id_uses_service_role_client_and_tenant_scope(self):
        service_db = Mock()
        profiles = service_db.table.return_value
        profiles.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"id": "admin-user-id"}
        ]

        with patch.object(database, "get_db", return_value=service_db) as get_db, patch.object(
            database, "get_user_db"
        ) as get_user_db:
            admin_id = database.get_tenant_admin_user_id("tenant-a")

        self.assertEqual(admin_id, "admin-user-id")
        get_db.assert_called_once_with()
        get_user_db.assert_not_called()
        service_db.table.assert_called_once_with("profiles")

    def test_update_rag_eval_case_uses_tenant_and_case_scope(self):
        service_db = Mock()
        table = service_db.table.return_value
        update_query = table.update.return_value
        update_query.eq.return_value = update_query
        update_query.execute.return_value.data = [{
            "id": "case-a",
            "tenant_id": "tenant-a",
            "question": "Updated",
            "expected_facts": ["fact-a"],
            "tags": [],
            "enabled": False,
            "created_at": "now",
            "updated_at": "now",
        }]

        with patch.object(database, "get_db", return_value=service_db):
            updated = database.update_rag_eval_case(
                "tenant-a",
                "case-a",
                {"question": "Updated", "enabled": False, "ignored": "value"},
            )

        self.assertEqual(updated["question"], "Updated")
        service_db.table.assert_called_once_with("rag_eval_cases")
        table.update.assert_called_once()
        update_payload = table.update.call_args.args[0]
        self.assertEqual(update_payload["question"], "Updated")
        self.assertEqual(update_payload["enabled"], False)
        self.assertNotIn("ignored", update_payload)
        self.assertEqual(update_query.eq.call_args_list[0].args, ("tenant_id", "tenant-a"))
        self.assertEqual(update_query.eq.call_args_list[1].args, ("id", "case-a"))

    def test_resolve_feedback_answer_message_accepts_real_message_id(self):
        answer_id = "11111111-1111-4111-8111-111111111111"
        fake_db = FakeDb({
            "messages": [
                {
                    "id": answer_id,
                    "tenant_id": "tenant-a",
                    "thread_id": "thread-a",
                    "role": "assistant",
                    "content": "Answer",
                    "created_at": "2026-06-01T00:01:00Z",
                }
            ]
        })

        resolved = database._resolve_feedback_answer_message(
            fake_db,
            "tenant-a",
            {"thread_id": "thread-a", "message_id": answer_id},
        )

        self.assertEqual(resolved["id"], answer_id)

    def test_resolve_feedback_answer_message_accepts_legacy_display_index(self):
        fake_db = FakeDb({
            "messages": [
                {
                    "id": "user-a",
                    "tenant_id": "tenant-a",
                    "thread_id": "thread-a",
                    "role": "user",
                    "content": "Question",
                    "created_at": "2026-06-01T00:00:00Z",
                },
                {
                    "id": "answer-a",
                    "tenant_id": "tenant-a",
                    "thread_id": "thread-a",
                    "role": "assistant",
                    "content": "Answer",
                    "created_at": "2026-06-01T00:01:00Z",
                },
                {
                    "id": "admin-a",
                    "tenant_id": "tenant-a",
                    "thread_id": "thread-a",
                    "role": "admin",
                    "content": "Admin note",
                    "created_at": "2026-06-01T00:02:00Z",
                },
            ]
        })

        resolved = database._resolve_feedback_answer_message(
            fake_db,
            "tenant-a",
            {"thread_id": "thread-a", "message_id": "msg-1"},
        )

        self.assertEqual(resolved["id"], "answer-a")


if __name__ == "__main__":
    unittest.main()
