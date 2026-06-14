import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.routers import documents


class CheckQdrantEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_check_qdrant_filters_by_document_id(self):
        user = SimpleNamespace(id="admin-a", tenant_id="tenant-a", role="admin", status="approved")

        with (
            patch("app.services.qdrant_db.count_user_chunks", new=AsyncMock(return_value=1)) as count,
            patch(
                "app.services.qdrant_db.get_sample_chunks",
                new=AsyncMock(return_value=[{
                    "document_id": "doc-a",
                    "content": "verification passphrase",
                    "chunk_type": "child",
                    "parent_id": "parent-a",
                    "metadata": {
                        "pdf_parser": "pypdfium",
                        "pdf_parser_planned": "unstructured",
                        "extraction_quality_warning": "unstructured unavailable",
                    },
                }]),
            ) as samples,
        ):
            result = await documents.check_qdrant(user=user, document_id="doc-a")

        self.assertEqual(result["document_id"], "doc-a")
        self.assertEqual(result["samples"][0]["chunk_type"], "child")
        self.assertEqual(result["samples"][0]["parent_id"], "parent-a")
        self.assertEqual(result["samples"][0]["metadata"]["pdf_parser"], "pypdfium")
        self.assertEqual(result["samples"][0]["metadata"]["pdf_parser_planned"], "unstructured")
        self.assertIn("unstructured unavailable", result["samples"][0]["metadata"]["extraction_quality_warning"])
        count.assert_awaited_once_with("admin-a", tenant_id="tenant-a", document_id="doc-a")
        samples.assert_awaited_once_with("admin-a", limit=3, tenant_id="tenant-a", document_id="doc-a")


if __name__ == "__main__":
    unittest.main()
