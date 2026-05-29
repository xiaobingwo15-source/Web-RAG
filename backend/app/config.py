import functools
import time
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openrouter_api_key: str = ""
    openrouter_model: str = "deepseek/deepseek-v4-flash"
    openrouter_fallback_model: str = "deepseek/deepseek-v4-flash:free"
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
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    backend_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"

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
    def get_openrouter_api_key(self) -> str:
        val = self._get_db_setting("OPENROUTER_API_KEY")
        return val if val else self.openrouter_api_key

    @property
    def get_google_api_key(self) -> str:
        val = self._get_db_setting("GOOGLE_API_KEY")
        return val if val else self.google_api_key

    @property
    def get_tavly_api_key(self) -> str:
        val = self._get_db_setting("TAVLY_API_KEY")
        return val if val else self.tavly_api_key

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

