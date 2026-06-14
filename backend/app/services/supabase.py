from functools import lru_cache

from supabase import create_client, Client
from app.config import Settings


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Return the shared service-role Supabase client."""
    settings = Settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


@lru_cache(maxsize=1)
def get_supabase_anon_client() -> Client:
    """Return the shared anonymous Supabase client for non-user-scoped calls."""
    settings = Settings()
    return create_client(settings.supabase_url, settings.supabase_anon_key)


def get_supabase_client_with_token(access_token: str) -> Client:
    """Create a Supabase client authenticated with the user's JWT token.
    This ensures RLS policies (e.g. auth.uid() = user_id) work correctly."""
    settings = Settings()
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(access_token)
    return client


def clear_supabase_client_cache() -> None:
    """Clear shared client caches after tests or runtime credential changes."""
    get_supabase_client.cache_clear()
    get_supabase_anon_client.cache_clear()
