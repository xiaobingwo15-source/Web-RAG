import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.routers import health
from app.services.runtime_health import (
    mark_startup_complete,
    mark_startup_started,
    record_startup_check,
    reset_startup_diagnostics_for_tests,
)


class HealthRouteTests(unittest.TestCase):
    def setUp(self):
        reset_startup_diagnostics_for_tests()
        app = FastAPI()
        app.include_router(health.router, prefix="/api")
        self.client = TestClient(app)

    def test_health_get_is_dependency_free(self):
        with patch("app.config._get_cached_setting") as dynamic_setting:
            response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["service"], "agentic-rag-masterclass")
        self.assertGreater(payload["process"]["pid"], 0)
        self.assertIn(payload["startup"]["phase"], {"starting", "maintenance", "ready", "degraded"})
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-web-rag-pid"], str(payload["process"]["pid"]))
        dynamic_setting.assert_not_called()

    def test_health_head_is_allowed_for_uptimerobot(self):
        response = self.client.head("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_readiness_reports_startup_failure_without_breaking_liveness(self):
        mark_startup_started()
        record_startup_check(
            "qdrant",
            status="failed",
            duration_ms=15000,
            detail="TimeoutError",
        )
        mark_startup_complete()

        readiness = self.client.get("/api/health/ready")
        liveness = self.client.get("/api/health")

        self.assertEqual(readiness.status_code, 503)
        self.assertEqual(readiness.json()["status"], "not_ready")
        self.assertEqual(readiness.json()["startup"]["phase"], "degraded")
        self.assertEqual(liveness.status_code, 200)
        self.assertEqual(liveness.json()["status"], "ok")


if __name__ == "__main__":
    unittest.main()
