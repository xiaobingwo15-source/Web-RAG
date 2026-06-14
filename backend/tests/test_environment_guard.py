from types import SimpleNamespace

import pytest

from app.services.environment_guard import effective_project_ref, validate_environment_isolation


def _settings(**overrides):
    values = {
        "app_env": "local",
        "supabase_url": "https://local-ref.supabase.co",
        "supabase_project_ref": "local-ref",
        "production_supabase_project_ref": "prod-ref",
        "allow_nonprod_production_supabase": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_local_refuses_production_project_ref():
    with pytest.raises(RuntimeError, match="Refusing to start"):
        validate_environment_isolation(
            _settings(supabase_project_ref="prod-ref")
        )


def test_staging_allows_distinct_project_ref():
    validate_environment_isolation(
        _settings(app_env="staging", supabase_project_ref="staging-ref")
    )


def test_test_override_allows_nonprod_production_ref():
    validate_environment_isolation(
        _settings(
            supabase_project_ref="prod-ref",
            allow_nonprod_production_supabase=True,
        )
    )


def test_invalid_app_env_fails():
    with pytest.raises(RuntimeError, match="APP_ENV"):
        validate_environment_isolation(_settings(app_env="dev"))


def test_project_ref_can_be_derived_from_supabase_url():
    settings = _settings(supabase_project_ref="", supabase_url="https://abc123.supabase.co")

    assert effective_project_ref(settings) == "abc123"

