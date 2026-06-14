from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import tools
from app.services.sql_engine import execute_readonly_sql


def test_tool_access_requires_approved_admin(monkeypatch):
    monkeypatch.setattr(tools, "Settings", lambda: SimpleNamespace(sql_tools_enabled=True))

    with pytest.raises(HTTPException) as ctx:
        tools._verify_admin_tool_access(
            SimpleNamespace(role="client", tenant_id="tenant-1", status="approved")
        )

    assert ctx.value.status_code == 403


def test_tool_access_disabled_by_default():
    with pytest.raises(HTTPException) as ctx:
        tools._verify_admin_tool_access(
            SimpleNamespace(role="admin", tenant_id="tenant-1", status="approved")
        )

    assert ctx.value.status_code == 403
    assert ctx.value.detail == "Admin tools are disabled"


def test_sql_validator_blocks_disallowed_tables():
    with pytest.raises(ValueError, match="disallowed"):
        execute_readonly_sql("SELECT * FROM profiles")


def test_sql_validator_blocks_multiple_statements():
    with pytest.raises(ValueError, match="single SELECT"):
        execute_readonly_sql("SELECT * FROM ie_sales; SELECT * FROM ie_employees")

