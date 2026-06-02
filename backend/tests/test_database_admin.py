import unittest
from unittest.mock import Mock, patch

from app.services import database


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


if __name__ == "__main__":
    unittest.main()
