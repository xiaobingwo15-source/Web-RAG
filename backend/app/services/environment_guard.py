import logging
import re

from app.config import Settings

logger = logging.getLogger(__name__)

ALLOWED_APP_ENVS = {"local", "staging", "production"}
SUPABASE_REF_RE = re.compile(r"https://([a-z0-9-]+)\.supabase\.co", re.IGNORECASE)


def _project_ref_from_url(supabase_url: str) -> str:
    match = SUPABASE_REF_RE.match((supabase_url or "").strip())
    return match.group(1) if match else ""


def effective_project_ref(settings: Settings) -> str:
    return (settings.supabase_project_ref or _project_ref_from_url(settings.supabase_url)).strip()


def validate_environment_isolation(settings: Settings | None = None) -> None:
    """Fail fast when a non-production app points at the production Supabase project."""
    settings = settings or Settings()
    app_env = settings.app_env.strip().lower()
    if app_env not in ALLOWED_APP_ENVS:
        raise RuntimeError(
            "APP_ENV must be one of local, staging, or production; "
            f"got {settings.app_env!r}"
        )

    project_ref = effective_project_ref(settings)
    prod_ref = settings.production_supabase_project_ref.strip()
    if not project_ref or not prod_ref:
        logger.warning(
            "Environment isolation guard is running without both SUPABASE_PROJECT_REF "
            "and PRODUCTION_SUPABASE_PROJECT_REF configured"
        )
        return

    if (
        app_env != "production"
        and project_ref == prod_ref
        and not settings.allow_nonprod_production_supabase
    ):
        raise RuntimeError(
            f"Refusing to start APP_ENV={app_env} against production Supabase project "
            f"{prod_ref}. Set ALLOW_NONPROD_PRODUCTION_SUPABASE=true only in isolated tests."
        )

