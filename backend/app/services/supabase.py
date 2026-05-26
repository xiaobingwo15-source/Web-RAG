from supabase import create_client, Client
from app.config import Settings


def get_supabase_client() -> Client:
    settings = Settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def get_supabase_client_with_token(access_token: str) -> Client:
    """Create a Supabase client authenticated with the user's JWT token.
    This ensures RLS policies (e.g. auth.uid() = user_id) work correctly."""
    settings = Settings()
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(access_token)
    return client
