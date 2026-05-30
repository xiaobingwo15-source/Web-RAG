from datetime import UTC, datetime, timedelta
import re
from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field
from app.config import Settings
from app.services.database import create_tenant, create_tenant_admin_invite, delete_tenant, get_tenant_by_slug
from app.services.widget_tokens import hash_token, new_invite_token

router = APIRouter()


class CreateTenantRequest(BaseModel):
    name: str = Field(min_length=1)
    slug: str = Field(min_length=2, max_length=64)
    admin_email: str = Field(min_length=3)
    allowed_origins: list[str] = Field(min_length=1)


def _verify_owner(x_owner_key: str | None) -> None:
    expected = Settings().owner_api_key
    if not expected or x_owner_key != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required")


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
