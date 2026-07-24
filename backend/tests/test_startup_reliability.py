import asyncio
import time

import pytest

from app.services.runtime_health import (
    reset_startup_diagnostics_for_tests,
    startup_snapshot,
)


@pytest.mark.asyncio
async def test_startup_maintenance_does_not_delay_lifespan(monkeypatch):
    from app import main

    dependency_release = asyncio.Event()

    async def slow_startup_maintenance():
        await dependency_release.wait()

    async def no_streaming_tasks():
        return None

    class NoOpLangfuse:
        def flush(self):
            return None

    reset_startup_diagnostics_for_tests()
    monkeypatch.setattr(main, "validate_environment_isolation", lambda settings: None)
    monkeypatch.setattr(main, "run_startup_maintenance", slow_startup_maintenance)
    monkeypatch.setattr(
        "app.services.streaming_tasks.shutdown_streaming_tasks",
        no_streaming_tasks,
    )
    monkeypatch.setattr(main, "get_langfuse", lambda: NoOpLangfuse())

    started = time.monotonic()
    async with main.lifespan(main.app):
        elapsed = time.monotonic() - started
        assert elapsed < 0.1
        assert not dependency_release.is_set()


@pytest.mark.asyncio
async def test_startup_maintenance_records_failures_and_continues(monkeypatch):
    from app import main
    from app.services import database

    async def qdrant_failure():
        raise TimeoutError("simulated dependency timeout")

    monkeypatch.setattr(main, "ensure_collection", qdrant_failure)
    monkeypatch.setattr(database, "expire_stale_upload_sessions", lambda: 2)
    monkeypatch.setattr(database, "expire_stale_streaming_messages", lambda **kwargs: 1)
    reset_startup_diagnostics_for_tests()

    await main.run_startup_maintenance()

    startup = startup_snapshot()
    assert startup["phase"] == "degraded"
    assert startup["checks"]["qdrant"]["status"] == "failed"
    assert startup["checks"]["qdrant"]["detail"] == "TimeoutError"
    assert startup["checks"]["stale_upload_sessions"]["status"] == "ok"
    assert startup["checks"]["stale_upload_sessions"]["detail"] == "affected=2"
    assert startup["checks"]["stale_streaming_messages"]["status"] == "ok"
    assert startup["checks"]["stale_streaming_messages"]["detail"] == "affected=1"


@pytest.mark.asyncio
async def test_startup_maintenance_marks_soft_dependency_failure_degraded(monkeypatch):
    from app import main
    from app.services import database

    async def unavailable_qdrant():
        return False

    monkeypatch.setattr(main, "ensure_collection", unavailable_qdrant)
    monkeypatch.setattr(database, "expire_stale_upload_sessions", lambda: 0)
    monkeypatch.setattr(database, "expire_stale_streaming_messages", lambda **kwargs: 0)
    reset_startup_diagnostics_for_tests()

    await main.run_startup_maintenance()

    qdrant = startup_snapshot()["checks"]["qdrant"]
    assert qdrant["status"] == "failed"
    assert qdrant["detail"] == "dependency_unavailable"
