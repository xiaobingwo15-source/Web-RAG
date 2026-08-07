from contextlib import contextmanager
from contextvars import ContextVar
import functools
import time
from collections.abc import Iterator
from typing import Any

from pydantic import Field, PrivateAttr
from pydantic_settings import BaseSettings


DEFAULT_OCR_MODEL = "google/gemini-2.5-flash-lite"
OCR_MODEL_ALIASES = {
    "google/gemini-2.0-flash-001": DEFAULT_OCR_MODEL,
}

TENANT_OVERRIDABLE_SETTING_KEYS = frozenset({
    "MODEL_PROVIDER",
    "OPENROUTER_API_KEY",
    "OPENROUTER_MODEL",
    "OPENROUTER_FALLBACK_MODEL",
    "OCR_MODEL",
    "PDF_OCR_MAX_PAGES",
    "PDF_LAYOUT_MAX_PAGES",
    "MISTRAL_API_KEY",
    "MISTRAL_MODEL",
    "TAVLY_API_KEY",
    "COHERE_API_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_BASE_URL",
    "CONTEXTUAL_RETRIEVAL",
    "CONTEXTUAL_RETRIEVAL_BATCH_SIZE",
})

_current_tenant_id: ContextVar[str | None] = ContextVar(
    "runtime_settings_tenant_id",
    default=None,
)


def normalize_ocr_model(model: str | None) -> str:
    normalized = (model or DEFAULT_OCR_MODEL).strip()
    if not normalized:
        return DEFAULT_OCR_MODEL
    return OCR_MODEL_ALIASES.get(normalized, normalized)


def _nonnegative_int_setting(value: str | None, default: int) -> int:
    if value is None or not str(value).strip():
        return default
    try:
        parsed = int(str(value).strip())
    except ValueError:
        return default
    return parsed if parsed >= 0 else default


class Settings(BaseSettings):
    _tenant_id: str | None = PrivateAttr(default=None)

    model_provider: str = "openrouter"
    openrouter_api_key: str = ""
    openrouter_model: str = "deepseek/deepseek-v4-flash"
    openrouter_fallback_model: str = "deepseek/deepseek-v4-flash:free"
    ocr_model: str = DEFAULT_OCR_MODEL
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
    owner_user_emails: str = ""
    widget_token_secret: str = ""
    app_env: str = "local"
    supabase_project_ref: str = ""
    production_supabase_project_ref: str = ""
    allow_nonprod_production_supabase: bool = False
    sql_tools_enabled: bool = False
    enable_api_docs: bool = False

    # Optional MinerU agent parser for complex PDF layout/table/formula extraction.
    mineru_agent_enabled: bool = False
    mineru_agent_base_url: str = "https://mineru.net/api/v1/agent"
    mineru_agent_max_bytes: int = 10 * 1024 * 1024
    mineru_poll_timeout_seconds: int = 300
    mineru_poll_interval_seconds: int = 3
    mineru_language: str = "ch"

    # Free-tier PDF safety limits. OCR and high-res layout parsing can exceed
    # Render's 512 MB free instance memory on high-page PDFs.
    pdf_max_bytes: int = 10 * 1024 * 1024
    pdf_max_pages: int = 100
    pdf_ocr_max_pages: int = 20
    pdf_layout_max_pages: int = 30

    # Rate limiting
    rate_limit_chat_requests: int = 30
    rate_limit_chat_window: int = 60
    rate_limit_widget_requests: int = 20
    rate_limit_widget_window: int = 60

    # Maximum wall-clock time for a complete chat/RAG pipeline.
    chat_pipeline_timeout_seconds: int = 120

    # Free tier: max questions anonymous visitors can ask before sign-up
    widget_free_tier_limit: int = 5

    # Chunking
    chunk_size: int = 800
    chunk_overlap: int = 50
    structure_aware_chunking: bool = True
    parent_chunk_size: int = 1500
    child_chunk_size: int = 500
    semantic_chunking: bool = False
    semantic_similarity_threshold: float = 0.75

    # Contextual retrieval (Anthropic-style LLM-generated chunk prefixes)
    contextual_retrieval: bool = False
    contextual_retrieval_batch_size: int = 10

    # Embeddings
    embedding_provider: str = "gemini"
    embedding_model: str = "gemini-embedding-001"
    embedding_dimension: int = 768
    local_embedding_model: str = "intfloat/multilingual-e5-base"
    local_embedding_device: str = "cpu"
    jina_api_key: str = ""
    jina_embedding_model: str = "jina-embeddings-v5-text-small"

    # Context budget
    max_context_tokens: int = 6000

    # History window
    max_history_messages: int = 10

    @property
    def cors_origins(self) -> list[str]:
        """Parse comma-separated FRONTEND_URL into a list of allowed origins."""
        return [o.strip() for o in self.frontend_url.split(",") if o.strip()]

    @property
    def owner_email_set(self) -> set[str]:
        """Lowercased owner allowlist parsed from OWNER_USER_EMAILS."""
        return {
            email.strip().lower()
            for email in self.owner_user_emails.split(",")
            if email.strip()
        }

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    model_config = {
        "env_file": "../.env",
        "env_file_encoding": "utf-8",
        "populate_by_name": True,
        "extra": "ignore",
    }

    @classmethod
    def for_tenant(cls, tenant_id: str, **values: Any) -> "Settings":
        """Create runtime settings bound to exactly one tenant."""
        normalized_tenant_id = str(tenant_id or "").strip()
        if not normalized_tenant_id:
            raise ValueError("tenant_id is required for tenant-overridable settings")
        settings = cls(**values)
        settings._tenant_id = normalized_tenant_id
        return settings

    # Custom dynamic lookups that check database and fallback to env
    def _get_db_setting(self, key: str) -> str | None:
        if key not in TENANT_OVERRIDABLE_SETTING_KEYS:
            return None

        tenant_id = self._tenant_id or _current_tenant_id.get()
        if not tenant_id:
            return None

        try:
            # Caching mechanism using 10-second blocks to avoid high database load
            expiry_time = time.time() // 10
            return _get_cached_setting(tenant_id, key, expiry_time)
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
    def get_ocr_model(self) -> str:
        val = self._get_db_setting("OCR_MODEL")
        return normalize_ocr_model(val if val else self.ocr_model)

    @property
    def get_pdf_ocr_max_pages(self) -> int:
        val = self._get_db_setting("PDF_OCR_MAX_PAGES")
        return _nonnegative_int_setting(val, self.pdf_ocr_max_pages)

    @property
    def get_pdf_layout_max_pages(self) -> int:
        val = self._get_db_setting("PDF_LAYOUT_MAX_PAGES")
        return _nonnegative_int_setting(val, self.pdf_layout_max_pages)

    @property
    def get_google_api_key(self) -> str:
        return self.google_api_key

    @property
    def get_embedding_provider(self) -> str:
        provider = self.embedding_provider.strip().lower()
        allowed = {"gemini", "local_sentence_transformers", "jina"}
        return provider if provider in allowed else "gemini"

    @property
    def get_embedding_model(self) -> str:
        return self.embedding_model

    @property
    def get_embedding_dimension(self) -> int:
        return self.embedding_dimension

    @property
    def get_local_embedding_model(self) -> str:
        return self.local_embedding_model

    @property
    def get_local_embedding_device(self) -> str:
        device = self.local_embedding_device.strip().lower()
        return device if device in {"cpu", "cuda"} else "cpu"

    @property
    def get_jina_api_key(self) -> str:
        return self.jina_api_key

    @property
    def get_jina_embedding_model(self) -> str:
        return self.jina_embedding_model

    @property
    def get_contextual_retrieval(self) -> bool:
        val = self._get_db_setting("CONTEXTUAL_RETRIEVAL")
        if val is not None:
            return val.strip().lower() in {"true", "1", "yes"}
        return self.contextual_retrieval

    @property
    def get_contextual_retrieval_batch_size(self) -> int:
        val = self._get_db_setting("CONTEXTUAL_RETRIEVAL_BATCH_SIZE")
        return int(val) if val else self.contextual_retrieval_batch_size

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
        return self.qdrant_url

    @property
    def get_qdrant_api_key(self) -> str:
        return self.qdrant_api_key


@functools.lru_cache(maxsize=128)
def _get_cached_setting(
    tenant_id: str,
    key_name: str,
    expiry_time: float,
) -> str | None:
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
            params={
                "select": "value",
                "tenant_id": f"eq.{tenant_id}",
                "key": f"eq.{key_name}",
            },
            timeout=5.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if data and len(data) > 0:
            return data[0]["value"]
    except Exception:
        pass
    return None


@contextmanager
def tenant_settings_context(tenant_id: str | None) -> Iterator[None]:
    """Bind tenant settings to the current async/thread execution context."""
    normalized_tenant_id = str(tenant_id or "").strip() or None
    token = _current_tenant_id.set(normalized_tenant_id)
    try:
        yield
    finally:
        _current_tenant_id.reset(token)
