import functools
import time
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_provider: str = "openrouter"
    openrouter_api_key: str = ""
    openrouter_model: str = "deepseek/deepseek-v4-flash"
    openrouter_fallback_model: str = "deepseek/deepseek-v4-flash:free"
    mistral_api_key: str = ""
    mistral_model: str = "mistral-large-latest"
    google_api_key: str = ""  # kept for embeddings only
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = Field(
        default="https://jp.cloud.langfuse.com",
        alias="LANGFUSE_BASE_URL",
    )
    tavly_api_key: str = ""
    cohere_api_key: str = ""
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    backend_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"
    owner_api_key: str = ""
    widget_token_secret: str = ""

    # Rate limiting
    rate_limit_chat_requests: int = 30
    rate_limit_chat_window: int = 60
    rate_limit_widget_requests: int = 20
    rate_limit_widget_window: int = 60

    # Chunking
    chunk_size: int = 800
    chunk_overlap: int = 50
    structure_aware_chunking: bool = True
    parent_chunk_size: int = 1500
    child_chunk_size: int = 500

    @property
    def cors_origins(self) -> list[str]:
        """Parse comma-separated FRONTEND_URL into a list of allowed origins."""
        return [o.strip() for o in self.frontend_url.split(",") if o.strip()]

    model_config = {
        "env_file": "../.env",
        "env_file_encoding": "utf-8",
        "populate_by_name": True,
        "extra": "ignore",
    }

    # Custom dynamic lookups that check database and fallback to env
    def _get_db_setting(self, key: str) -> str | None:
        try:
            # Avoid infinite recursion if fetching database configuration keys
            if key in ["supabase_url", "supabase_service_role_key", "supabase_anon_key"]:
                return None
            
            # Caching mechanism using 10-second blocks to avoid high database load
            expiry_time = time.time() // 10
            return _get_cached_setting(key, expiry_time)
        except Exception:
            return None

    @property
    def get_model_provider(self) -> str:
        val = self._get_db_setting("MODEL_PROVIDER")
        provider = (val if val else self.model_provider).strip().lower()
        return provider if provider in {"openrouter", "mistral"} else "openrouter"

    @property
    def get_openrouter_api_key(self) -> str:
        val = self._get_db_setting("OPENROUTER_API_KEY")
        return val if val else self.openrouter_api_key

    @property
    def get_mistral_api_key(self) -> str:
        val = self._get_db_setting("MISTRAL_API_KEY")
        return val if val else self.mistral_api_key

    @property
    def get_mistral_model(self) -> str:
        val = self._get_db_setting("MISTRAL_MODEL")
        return val if val else self.mistral_model

    @property
    def get_openrouter_model(self) -> str:
        val = self._get_db_setting("OPENROUTER_MODEL")
        return val if val else self.openrouter_model

    @property
    def get_openrouter_fallback_model(self) -> str:
        val = self._get_db_setting("OPENROUTER_FALLBACK_MODEL")
        return val if val else self.openrouter_fallback_model

    @property
    def get_google_api_key(self) -> str:
        val = self._get_db_setting("GOOGLE_API_KEY")
        return val if val else self.google_api_key

    @property
    def get_tavly_api_key(self) -> str:
        val = self._get_db_setting("TAVLY_API_KEY")
        return val if val else self.tavly_api_key

    @property
    def get_cohere_api_key(self) -> str:
        val = self._get_db_setting("COHERE_API_KEY")
        return val if val else self.cohere_api_key

    @property
    def get_langfuse_public_key(self) -> str:
        val = self._get_db_setting("LANGFUSE_PUBLIC_KEY")
        return val if val else self.langfuse_public_key

    @property
    def get_langfuse_secret_key(self) -> str:
        val = self._get_db_setting("LANGFUSE_SECRET_KEY")
        return val if val else self.langfuse_secret_key

    @property
    def get_langfuse_host(self) -> str:
        val = self._get_db_setting("LANGFUSE_BASE_URL")
        return val if val else self.langfuse_host

    @property
    def get_qdrant_url(self) -> str:
        val = self._get_db_setting("QDRANT_URL")
        return val if val else self.qdrant_url

    @property
    def get_qdrant_api_key(self) -> str:
        val = self._get_db_setting("QDRANT_API_KEY")
        return val if val else self.qdrant_api_key


@functools.lru_cache(maxsize=128)
def _get_cached_setting(key_name: str, expiry_time: float) -> str | None:
    try:
        import httpx
        settings = Settings()
        url = f"{settings.supabase_url}/rest/v1/system_settings"
        headers = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
        }
        resp = httpx.get(
            url,
            headers=headers,
            params={"select": "value", "key": f"eq.{key_name}"},
            timeout=5.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if data and len(data) > 0:
            return data[0]["value"]
    except Exception:
        pass
    return None
