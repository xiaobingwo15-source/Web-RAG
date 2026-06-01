from datetime import UTC, datetime, timedelta
import re
from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from app.config import Settings
from app.services.database import (
    approve_owner_admin,
    create_tenant,
    create_tenant_admin_invite,
    delete_tenant,
    list_owner_admins,
    reject_owner_admin,
)
from app.services.widget_tokens import hash_token, new_invite_token

router = APIRouter()


class CreateTenantRequest(BaseModel):
    name: str = Field(min_length=1)
    slug: str = Field(min_length=2, max_length=64)
    admin_email: str = Field(min_length=3)
    allowed_origins: list[str] = Field(min_length=1)


class OwnerAdminListResponse(BaseModel):
    admins: list[dict]
    page: int
    limit: int
    total: int


def _verify_owner(x_owner_key: str | None) -> None:
    expected = Settings().owner_api_key
    if not expected or x_owner_key != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required")


@router.get("/admins", response_model=OwnerAdminListResponse)
async def list_admins_endpoint(
    status_filter: str = Query(default="pending", alias="status", pattern="^(pending|approved|suspended|all)$"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    x_owner_key: str | None = Header(default=None),
):
    _verify_owner(x_owner_key)
    return list_owner_admins(status_filter=status_filter, page=page, limit=limit)


@router.post("/admins/{user_id}/approve")
async def approve_admin_endpoint(user_id: str, x_owner_key: str | None = Header(default=None)):
    _verify_owner(x_owner_key)
    updated = approve_owner_admin(user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Admin profile not found")
    return {"status": "approved", "admin": updated}


@router.post("/admins/{user_id}/reject")
async def reject_admin_endpoint(user_id: str, x_owner_key: str | None = Header(default=None)):
    _verify_owner(x_owner_key)
    updated = reject_owner_admin(user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Admin profile not found")
    return {"status": "suspended", "admin": updated}


@router.post("/tenants")
async def create_tenant_endpoint(request: CreateTenantRequest, x_owner_key: str | None = Header(default=None)):
    _verify_owner(x_owner_key)
    slug = request.slug.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", slug):
        raise HTTPException(status_code=400, detail="Tenant slug must use lowercase letters, numbers, and hyphens")

    origins = [origin.rstrip("/") for origin in request.allowed_origins]
    tenant = create_tenant(request.name.strip(), slug, origins)

    invite_token = new_invite_token()
    expires_at = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    invite = create_tenant_admin_invite(
        tenant["id"],
        request.admin_email.strip().lower(),
        hash_token(invite_token),
        expires_at,
    )

    return {
        "tenant": tenant,
        "invite": {
            "id": invite["id"],
            "email": invite["email"],
            "token": invite_token,
            "expires_at": invite["expires_at"],
        },
    }


@router.delete("/tenants/{tenant_id}")
async def delete_tenant_endpoint(tenant_id: str, x_owner_key: str | None = Header(default=None)):
    _verify_owner(x_owner_key)
    deleted = delete_tenant(tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"status": "deleted", "tenant_id": tenant_id}
