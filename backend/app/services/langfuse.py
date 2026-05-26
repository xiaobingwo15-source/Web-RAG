import os
from langfuse import get_client
from app.config import Settings


def configure_langfuse():
    """Set Langfuse env vars from Settings before client initialization."""
    settings = Settings()
    if settings.langfuse_public_key and settings.langfuse_secret_key:
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
        os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
        os.environ["LANGFUSE_HOST"] = settings.langfuse_host


def get_langfuse():
    """Return the Langfuse singleton client. Must call configure_langfuse() first."""
    return get_client()
