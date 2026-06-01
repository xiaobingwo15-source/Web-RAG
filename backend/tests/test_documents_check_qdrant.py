import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.routers import documents


class CheckQdrantEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_check_qdrant_filters_by_document_id(self):
        user = SimpleNamespace(id="admin-a", tenant_id="tenant-a")

        with (
            patch("app.services.qdrant_db.count_user_chunks", new=AsyncMock(return_value=1)) as count,
            patch(
                "app.services.qdrant_db.get_sample_chunks",
                new=AsyncMock(return_value=[{"document_id": "doc-a", "content": "verification passphrase"}]),
            ) as samples,
        ):
            result = await documents.check_qdrant(user=user, document_id="doc-a")

        self.assertEqual(result["document_id"], "doc-a")
        count.assert_awaited_once_with("admin-a", tenant_id="tenant-a", document_id="doc-a")
        samples.assert_awaited_once_with("admin-a", limit=3, tenant_id="tenant-a", document_id="doc-a")


if __name__ == "__main__":
    unittest.main()
