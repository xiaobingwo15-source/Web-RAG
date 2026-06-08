import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.routers import health


class HealthRouteTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(health.router, prefix="/api")
        self.client = TestClient(app)

    def test_health_get_returns_status_payload(self):
        embedding_info = {
            "provider": "gemini",
            "model": "gemini-embedding-001",
            "dimension": 768,
            "device": None,
        }
        with patch.object(health, "get_embedding_info", return_value=embedding_info):
            response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "service": "agentic-rag-masterclass",
                "embedding": embedding_info,
            },
        )

    def test_health_head_is_allowed_for_uptimerobot(self):
        response = self.client.head("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")


if __name__ == "__main__":
    unittest.main()
