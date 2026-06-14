from datetime import UTC, datetime, timedelta
import re
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from app.config import Settings
from app.middleware.auth import get_current_user
from app.services.audit import log_operation
from app.services.database import (
    approve_owner_admin,
    create_tenant,
    create_tenant_admin_invite,
    disable_tenant,
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


def _verify_owner(user) -> None:
    owner_emails = Settings().owner_email_set
    user_email = (getattr(user, "email", "") or "").lower()
    if not owner_emails or user_email not in owner_emails:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required")


@router.get("/admins", response_model=OwnerAdminListResponse)
async def list_admins_endpoint(
    status_filter: str = Query(default="pending", alias="status", pattern="^(pending|approved|suspended|all)$"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    user=Depends(get_current_user),
):
    _verify_owner(user)
    return list_owner_admins(status_filter=status_filter, page=page, limit=limit)


@router.post("/admins/{user_id}/approve")
async def approve_admin_endpoint(user_id: str, request: Request, user=Depends(get_current_user)):
    _verify_owner(user)
    updated = approve_owner_admin(user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Admin profile not found")
    log_operation(
        tenant_id=updated.get("tenant_id"),
        actor_user_id=user.id,
        actor_email=getattr(user, "email", None),
        actor_role=user.role,
        action="owner_admin.approve",
        resource_type="profile",
        resource_id=user_id,
        after=updated,
        request=request,
    )
    return {"status": "approved", "admin": updated}


@router.post("/admins/{user_id}/reject")
async def reject_admin_endpoint(user_id: str, request: Request, user=Depends(get_current_user)):
    _verify_owner(user)
    updated = reject_owner_admin(user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Admin profile not found")
    log_operation(
        tenant_id=updated.get("tenant_id"),
        actor_user_id=user.id,
        actor_email=getattr(user, "email", None),
        actor_role=user.role,
        action="owner_admin.reject",
        resource_type="profile",
        resource_id=user_id,
        after=updated,
        request=request,
    )
    return {"status": "suspended", "admin": updated}


@router.post("/tenants")
async def create_tenant_endpoint(body: CreateTenantRequest, request: Request, user=Depends(get_current_user)):
    _verify_owner(user)
    slug = body.slug.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", slug):
        raise HTTPException(status_code=400, detail="Tenant slug must use lowercase letters, numbers, and hyphens")

    origins = [origin.rstrip("/") for origin in body.allowed_origins]
    tenant = create_tenant(body.name.strip(), slug, origins)

    invite_token = new_invite_token()
    expires_at = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    invite = create_tenant_admin_invite(
        tenant["id"],
        body.admin_email.strip().lower(),
        hash_token(invite_token),
        expires_at,
    )
    log_operation(
        tenant_id=tenant.get("id"),
        actor_user_id=user.id,
        actor_email=getattr(user, "email", None),
        actor_role=user.role,
        action="tenant.create",
        resource_type="tenant",
        resource_id=tenant.get("id"),
        after=tenant,
        metadata={"admin_email": invite["email"], "invite_id": invite["id"]},
        request=request,
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


@router.post("/tenants/{tenant_id}/disable")
async def disable_tenant_endpoint(tenant_id: str, request: Request, user=Depends(get_current_user)):
    _verify_owner(user)
    disabled = disable_tenant(tenant_id)
    if not disabled:
        raise HTTPException(status_code=404, detail="Tenant not found")
    log_operation(
        tenant_id=tenant_id,
        actor_user_id=user.id,
        actor_email=getattr(user, "email", None),
        actor_role=user.role,
        action="tenant.disable",
        resource_type="tenant",
        resource_id=tenant_id,
        after={"status": "disabled"},
        request=request,
    )
    return {"status": "disabled", "tenant_id": tenant_id}
