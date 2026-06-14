from types import SimpleNamespace

from app.services import supabase as supabase_service


def test_service_role_client_is_reused(monkeypatch):
    created = []

    def fake_create_client(url, key):
        client = {"url": url, "key": key, "idx": len(created)}
        created.append(client)
        return client

    monkeypatch.setattr(
        supabase_service,
        "Settings",
        lambda: SimpleNamespace(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-key",
            supabase_anon_key="anon-key",
        ),
    )
    monkeypatch.setattr(supabase_service, "create_client", fake_create_client)
    supabase_service.clear_supabase_client_cache()

    first = supabase_service.get_supabase_client()
    second = supabase_service.get_supabase_client()

    assert first is second
    assert len(created) == 1
    assert created[0]["key"] == "service-key"


def test_anon_client_is_reused_separately(monkeypatch):
    created = []

    def fake_create_client(url, key):
        client = {"url": url, "key": key, "idx": len(created)}
        created.append(client)
        return client

    monkeypatch.setattr(
        supabase_service,
        "Settings",
        lambda: SimpleNamespace(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-key",
            supabase_anon_key="anon-key",
        ),
    )
    monkeypatch.setattr(supabase_service, "create_client", fake_create_client)
    supabase_service.clear_supabase_client_cache()

    first = supabase_service.get_supabase_anon_client()
    second = supabase_service.get_supabase_anon_client()

    assert first is second
    assert len(created) == 1
    assert created[0]["key"] == "anon-key"

