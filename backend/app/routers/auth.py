from fastapi import APIRouter, Depends, HTTPException, Request
from app.middleware.auth import get_current_user

router = APIRouter()


@router.get("/me")
async def get_me(user=Depends(get_current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "status": user.status,
    }


@router.get("/tenant/resolve")
async def resolve_tenant_from_origin(request: Request):
    """Public endpoint — auto-detect tenant from the browser's Origin header."""
    from app.services.database import get_tenant_by_origin
    origin = request.headers.get("origin") or request.headers.get("referer", "")
    if not origin:
        raise HTTPException(status_code=400, detail="Missing Origin header")
    # Extract just the origin (scheme + host) from the URL
    from urllib.parse import urlparse
    parsed = urlparse(origin)
    clean_origin = f"{parsed.scheme}://{parsed.netloc}"
    tenant = get_tenant_by_origin(clean_origin)
    if not tenant:
        raise HTTPException(status_code=404, detail="No tenant configured for this domain")
    return {"id": tenant["id"], "name": tenant["name"], "slug": tenant["slug"]}


@router.get("/tenant/{slug}")
async def get_tenant_info(slug: str):
    """Public endpoint — validate tenant slug before signup."""
    from app.services.database import get_tenant_by_slug
    tenant = get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(status_code=404, detail="Invalid or inactive tenant")
    return {"id": tenant["id"], "name": tenant["name"], "slug": tenant["slug"]}
