from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

import httpx

from app.config import Settings, _get_cached_setting, tenant_settings_context


class _Response:
    def __init__(self, value: str):
        self._value = value

    def raise_for_status(self) -> None:
        return None

    def json(self) -> list[dict[str, str]]:
        return [{"value": self._value}]


def test_concurrent_tenants_resolve_and_cache_their_own_override(monkeypatch):
    _get_cached_setting.cache_clear()
    monkeypatch.setattr("app.config.time.time", lambda: 12340.0)
    barrier = Barrier(2)
    calls: list[tuple[str, str]] = []
    calls_lock = Lock()

    def fake_get(_url, *, headers, params, timeout):
        assert headers["Authorization"].startswith("Bearer ")
        assert timeout == 5.0
        tenant_id = params["tenant_id"].removeprefix("eq.")
        key = params["key"].removeprefix("eq.")
        with calls_lock:
            calls.append((tenant_id, key))
        barrier.wait(timeout=2)
        return _Response(f"{tenant_id}-model")

    monkeypatch.setattr(httpx, "get", fake_get)

    def resolve(tenant_id: str) -> tuple[str, str]:
        with tenant_settings_context(tenant_id):
            settings = Settings()
            return settings.get_openrouter_model, settings.get_openrouter_model

    with ThreadPoolExecutor(max_workers=2) as executor:
        tenant_a = executor.submit(resolve, "tenant-a")
        tenant_b = executor.submit(resolve, "tenant-b")

    assert tenant_a.result() == ("tenant-a-model", "tenant-a-model")
    assert tenant_b.result() == ("tenant-b-model", "tenant-b-model")
    assert sorted(calls) == [
        ("tenant-a", "OPENROUTER_MODEL"),
        ("tenant-b", "OPENROUTER_MODEL"),
    ]


def test_missing_tenant_context_cannot_read_tenant_overrides(monkeypatch):
    _get_cached_setting.cache_clear()

    def unexpected_get(*_args, **_kwargs):
        raise AssertionError("tenant settings lookup must not run without tenant identity")

    monkeypatch.setattr(httpx, "get", unexpected_get)

    settings = Settings(openrouter_model="environment-model")

    assert settings.get_openrouter_model == "environment-model"


def test_infrastructure_settings_remain_environment_owned(monkeypatch):
    _get_cached_setting.cache_clear()

    def unexpected_get(*_args, **_kwargs):
        raise AssertionError("infrastructure settings must not be loaded from tenant storage")

    monkeypatch.setattr(httpx, "get", unexpected_get)

    settings = Settings.for_tenant("tenant-a", qdrant_url="https://env-qdrant")

    assert settings.get_qdrant_url == "https://env-qdrant"
