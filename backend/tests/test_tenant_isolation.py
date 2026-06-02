import unittest
from unittest.mock import Mock, patch

from app.services import database


class _Query:
    def __init__(self, data=None, count=None):
        self.data = data if data is not None else []
        self.count = count
        self.filters = []
        self.inserted = None

    def select(self, *args, **kwargs):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def is_(self, key, value):
        self.filters.append((key, value))
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def execute(self):
        return self

    def insert(self, payload):
        self.inserted = payload
        return self


class TenantIsolationTests(unittest.TestCase):
    def test_admin_thread_list_is_scoped_to_tenant(self):
        threads = _Query([
            {"id": "thread-a", "user_id": "client-a", "title": "A", "created_at": "now", "tenant_id": "tenant-a"},
        ])
        messages = _Query([{"thread_id": "thread-a"}])
        db = Mock()
        db.table.side_effect = lambda name: {"threads": threads, "messages": messages}[name]

        with patch.object(database, "get_db", return_value=db):
            clients = database.get_all_threads_grouped("tenant-a")

        self.assertEqual(clients[0]["threads"][0]["id"], "thread-a")
        self.assertIn(("tenant_id", "tenant-a"), threads.filters)
        self.assertIn(("tenant_id", "tenant-a"), messages.filters)

    def test_admin_thread_messages_are_scoped_to_tenant(self):
        messages = _Query([{"id": "msg-a", "thread_id": "thread-a", "tenant_id": "tenant-a"}])
        db = Mock()
        db.table.return_value = messages

        with patch.object(database, "get_db", return_value=db):
            result = database.get_thread_messages_admin("tenant-a", "thread-a")

        self.assertEqual(result, messages.data)
        self.assertIn(("thread_id", "thread-a"), messages.filters)
        self.assertIn(("tenant_id", "tenant-a"), messages.filters)

    def test_create_thread_persists_tenant_id(self):
        threads = _Query([{"id": "thread-a"}])
        db = Mock()
        db.table.return_value = threads

        with patch.object(database, "get_user_db", return_value=db):
            database.create_thread("token", "client-a", "thread-a", title="Hello", tenant_id="tenant-a")

        self.assertEqual(threads.inserted["tenant_id"], "tenant-a")


if __name__ == "__main__":
    unittest.main()
