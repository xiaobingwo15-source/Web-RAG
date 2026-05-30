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


if __name__ == "__main__":
    unittest.main()
