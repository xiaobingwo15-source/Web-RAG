import os
from langfuse import get_client
from app.config import Settings


def configure_langfuse():
    """Set Langfuse env vars from Settings before client initialization."""
    settings = Settings()
    pub = settings.get_langfuse_public_key
    sec = settings.get_langfuse_secret_key
    host = settings.get_langfuse_host
    if pub and sec:
        os.environ["LANGFUSE_PUBLIC_KEY"] = pub
        os.environ["LANGFUSE_SECRET_KEY"] = sec
        os.environ["LANGFUSE_HOST"] = host


def get_langfuse():
    """Return the Langfuse singleton client. Must call configure_langfuse() first."""
    return get_client()
