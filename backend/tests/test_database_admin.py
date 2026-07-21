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

    def lt(self, key, value):
        self.rows = [row for row in self.rows if row.get(key) is not None and row.get(key) < value]
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

    def test_clear_attention_flag_scopes_to_tenant_and_flagged_messages(self):
        service_db = Mock()
        table = service_db.table.return_value
        update_query = table.update.return_value
        update_query.eq.return_value = update_query
        update_query.or_.return_value = update_query
        update_query.execute.return_value.data = [{
            "id": "message-a",
            "tenant_id": "tenant-a",
            "attention_status": "dismissed",
            "needs_attention": False,
        }]

        with patch.object(database, "get_db", return_value=service_db):
            dismissed = database.clear_attention_flag("tenant-a", "message-a")

        self.assertEqual(dismissed["attention_status"], "dismissed")
        service_db.table.assert_called_once_with("messages")
        table.update.assert_called_once_with({"needs_attention": False, "attention_status": "dismissed"})
        self.assertEqual(update_query.eq.call_args_list[0].args, ("id", "message-a"))
        self.assertEqual(update_query.eq.call_args_list[1].args, ("tenant_id", "tenant-a"))
        update_query.or_.assert_called_once_with("attention_status.eq.needs_admin,needs_attention.eq.true")

    def test_list_operation_audit_logs_applies_filters_and_bounds_limit(self):
        service_db = Mock()
        table = service_db.table.return_value
        query = table.select.return_value
        query.eq.return_value = query
        query.order.return_value = query
        query.limit.return_value = query
        query.execute.return_value.data = [{"id": "audit-a"}]

        with patch.object(database, "get_db", return_value=service_db):
            rows = database.list_operation_audit_logs(
                "tenant-a",
                limit=999,
                action="flagged_message.dismiss",
                resource_type="message",
                resource_id="message-a",
            )

        self.assertEqual(rows, [{"id": "audit-a"}])
        service_db.table.assert_called_once_with("operation_audit_logs")
        selected_columns = table.select.call_args.args[0]
        self.assertIn("actor_email", selected_columns)
        self.assertNotIn("before_snapshot", selected_columns)
        self.assertNotIn("after_snapshot", selected_columns)
        self.assertNotIn("ip_address", selected_columns)
        self.assertNotIn("user_agent", selected_columns)
        self.assertEqual(query.eq.call_args_list[0].args, ("tenant_id", "tenant-a"))
        self.assertEqual(query.eq.call_args_list[1].args, ("action", "flagged_message.dismiss"))
        self.assertEqual(query.eq.call_args_list[2].args, ("resource_type", "message"))
        self.assertEqual(query.eq.call_args_list[3].args, ("resource_id", "message-a"))
        query.order.assert_called_once_with("created_at", desc=True)
        query.limit.assert_called_once_with(200)

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

    def test_list_rag_quality_feedback_returns_orphan_when_answer_is_missing(self):
        missing_answer_id = "22222222-2222-4222-8222-222222222222"
        fake_db = FakeDb({
            "message_feedback": [{
                "id": "feedback-a",
                "tenant_id": "tenant-a",
                "thread_id": "thread-a",
                "message_id": missing_answer_id,
                "rating": -1,
                "comment": "The answer was wrong",
                "created_at": "2026-06-01T00:02:00Z",
                "client_session_id": "session-a",
                "user_id": None,
            }],
            "messages": [{
                "id": "question-a",
                "tenant_id": "tenant-a",
                "thread_id": "thread-a",
                "role": "user",
                "content": "What is the refund window?",
                "created_at": "2026-06-01T00:00:00Z",
            }],
            "threads": [{
                "id": "thread-a",
                "tenant_id": "tenant-a",
                "title": "Refund policy",
                "user_id": None,
                "client_session_id": "session-a",
                "created_at": "2026-06-01T00:00:00Z",
            }],
            "retrieval_logs": [{
                "id": "log-a",
                "tenant_id": "tenant-a",
                "thread_id": "thread-a",
                "query": "What is the refund window?",
                "retrieval_mode": "hybrid",
                "chunk_count": 2,
                "source_count": 1,
                "top_score": 0.9,
                "groundedness_score": None,
                "created_at": "2026-06-01T00:01:00Z",
            }],
        })

        with patch.object(database, "get_db", return_value=fake_db):
            items = database.list_rag_quality_feedback("tenant-a")

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertTrue(item["orphaned"])
        self.assertEqual(item["orphan_reason"], "answer_message_missing")
        self.assertEqual(item["message_id"], missing_answer_id)
        self.assertIsNone(item["resolved_message_id"])
        self.assertEqual(item["thread_id"], "thread-a")
        self.assertEqual(item["thread_title"], "Refund policy")
        self.assertEqual(item["question"], "What is the refund window?")
        self.assertEqual(item["question_message_id"], "question-a")
        self.assertEqual(item["answer"], "")
        self.assertEqual(item["summary"]["retrieval_count"], 1)

    def test_list_rag_quality_feedback_keeps_answer_when_retrieval_log_is_missing(self):
        answer_id = "33333333-3333-4333-8333-333333333333"
        fake_db = FakeDb({
            "message_feedback": [{
                "id": "feedback-b",
                "tenant_id": "tenant-a",
                "thread_id": "thread-b",
                "message_id": answer_id,
                "rating": 1,
                "comment": None,
                "created_at": "2026-06-01T00:02:00Z",
                "client_session_id": "session-b",
                "user_id": None,
            }],
            "messages": [
                {
                    "id": "question-b",
                    "tenant_id": "tenant-a",
                    "thread_id": "thread-b",
                    "role": "user",
                    "content": "Which documents are required?",
                    "created_at": "2026-06-01T00:00:00Z",
                },
                {
                    "id": answer_id,
                    "tenant_id": "tenant-a",
                    "thread_id": "thread-b",
                    "role": "assistant",
                    "content": "Bring the original invoice.",
                    "created_at": "2026-06-01T00:01:00Z",
                },
            ],
            "threads": [{
                "id": "thread-b",
                "tenant_id": "tenant-a",
                "title": "Required documents",
                "user_id": None,
                "client_session_id": "session-b",
                "created_at": "2026-06-01T00:00:00Z",
            }],
            "retrieval_logs": [],
        })

        with patch.object(database, "get_db", return_value=fake_db):
            items = database.list_rag_quality_feedback("tenant-a")

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertFalse(item["orphaned"])
        self.assertIsNone(item["orphan_reason"])
        self.assertEqual(item["resolved_message_id"], answer_id)
        self.assertEqual(item["answer"], "Bring the original invoice.")
        self.assertEqual(item["retrieval_logs"], [])
        self.assertEqual(item["summary"]["retrieval_count"], 0)
        self.assertEqual(item["summary"]["source_count"], 0)
        self.assertFalse(item["summary"]["zero_source"])


if __name__ == "__main__":
    unittest.main()
