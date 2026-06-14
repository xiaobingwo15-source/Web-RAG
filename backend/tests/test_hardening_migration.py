from pathlib import Path


def test_hardening_migration_adds_audits_status_backfills_and_sql_guard():
    migration = (
        Path(__file__).resolve().parents[1]
        / "supabase"
        / "migrations"
        / "033_commercial_database_hardening.sql"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS public.operation_audit_logs" in migration
    assert "ADD COLUMN IF NOT EXISTS attention_status" in migration
    assert "ADD COLUMN IF NOT EXISTS grounding_status" in migration
    assert "ADD COLUMN IF NOT EXISTS result_status" in migration
    assert "SET attention_status = CASE WHEN needs_attention" in migration
    assert "SET grounding_status = CASE" in migration
    assert "SET result_status = CASE WHEN passed" in migration
    assert "CREATE OR REPLACE FUNCTION public.exec_readonly_sql" in migration
    assert "normalized_ref NOT IN ('ie_sales', 'ie_employees')" in migration

