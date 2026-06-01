import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.routers import admin, documents, owner
from app.services import database


class _Query:
    def __init__(self, data=None, count=None):
        self.data = data if data is not None else []
        self.count = count if count is not None else len(self.data)
        self.filters = []
        self.selected = None
        self.updated = None
        self.range_args = None
        self.order_args = None

    def select(self, *args, **kwargs):
        self.selected = (args, kwargs)
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def update(self, payload):
        self.updated = payload
        return self

    def order(self, *args, **kwargs):
        self.order_args = (args, kwargs)
        return self

    def range(self, start, end):
        self.range_args = (start, end)
        return self

    def execute(self):
        return self


class OwnerAdminApprovalTests(unittest.IsolatedAsyncioTestCase):
    async def test_owner_admin_list_requires_owner_key(self):
        with patch.object(owner, "Settings", return_value=SimpleNamespace(owner_api_key="expected")):
            with self.assertRaises(HTTPException) as ctx:
                await owner.list_admins_endpoint(x_owner_key="wrong")

        self.assertEqual(ctx.exception.status_code, 403)

    def test_owner_admin_list_filters_and_paginates_admin_profiles(self):
        rows = [
            {
                "id": "admin-a",
                "email": "a@example.com",
                "role": "admin",
                "status": "pending",
                "tenant_id": "tenant-a",
                "created_at": "2026-01-01T00:00:00Z",
                "tenant": {"id": "tenant-a", "name": "Tenant A", "slug": "tenant-a", "status": "active"},
            }
        ]
        profiles = _Query(rows, count=51)
        db = Mock()
        db.table.return_value = profiles

        with patch.object(database, "get_db", return_value=db):
            result = database.list_owner_admins(status_filter="pending", page=2, limit=25)

        self.assertEqual(result["page"], 2)
        self.assertEqual(result["limit"], 25)
        self.assertEqual(result["total"], 51)
        self.assertEqual(result["admins"][0]["tenant"]["slug"], "tenant-a")
        self.assertIn(("role", "admin"), profiles.filters)
        self.assertIn(("status", "pending"), profiles.filters)
        self.assertEqual(profiles.range_args, (25, 49))

    def test_approve_owner_admin_updates_only_admin_profile(self):
        profiles = _Query([{"id": "admin-a", "role": "admin", "status": "approved"}])
        db = Mock()
        db.table.return_value = profiles

        with patch.object(database, "get_db", return_value=db):
            result = database.approve_owner_admin("admin-a")

        self.assertEqual(result["status"], "approved")
        self.assertEqual(profiles.updated, {"status": "approved"})
        self.assertIn(("id", "admin-a"), profiles.filters)
        self.assertIn(("role", "admin"), profiles.filters)

    def test_reject_owner_admin_demotes_admin_and_suspends_profile(self):
        profiles = _Query([{"id": "admin-a", "role": "client", "status": "suspended"}])
        db = Mock()
        db.table.return_value = profiles

        with patch.object(database, "get_db", return_value=db):
            result = database.reject_owner_admin("admin-a")

        self.assertEqual(result["role"], "client")
        self.assertEqual(result["status"], "suspended")
        self.assertEqual(profiles.updated, {"role": "client", "status": "suspended"})
        self.assertIn(("id", "admin-a"), profiles.filters)
        self.assertIn(("role", "admin"), profiles.filters)

    def test_accept_invite_creates_pending_admin(self):
        profile_query = _Query([{"id": "admin-a", "role": "admin", "status": "pending"}])
        invite_query = _Query([{"id": "invite-a"}])
        table_queries = {"profiles": profile_query, "tenant_admin_invites": invite_query}
        db = Mock()
        db.table.side_effect = lambda name: table_queries[name]

        with patch.object(database, "get_db", return_value=db):
            profile = database.accept_tenant_admin_invite("invite-a", "tenant-a", "admin-a", "a@example.com")

        self.assertEqual(profile["status"], "pending")
        self.assertEqual(profile_query.updated["role"], "admin")
        self.assertEqual(profile_query.updated["status"], "pending")
        self.assertEqual(invite_query.updated, {"accepted_at": "now()"})

    def test_pending_admin_cannot_access_admin_or_document_admin_endpoints(self):
        user = SimpleNamespace(role="admin", tenant_id="tenant-a", status="pending")

        with self.assertRaises(HTTPException) as admin_ctx:
            admin._verify_admin(user)
        with self.assertRaises(HTTPException) as docs_ctx:
            documents._verify_admin(user)

        self.assertEqual(admin_ctx.exception.status_code, 403)
        self.assertEqual(docs_ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
