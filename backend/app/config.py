from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    google_api_key: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = Field(
        default="https://jp.cloud.langfuse.com",
        alias="LANGFUSE_BASE_URL",
    )
    backend_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"

    model_config = {
        "env_file": "../.env",
        "env_file_encoding": "utf-8",
        "populate_by_name": True,
        "extra": "ignore",
    }
