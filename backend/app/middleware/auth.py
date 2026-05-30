from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.supabase import get_supabase_client

security = HTTPBearer()


class AuthenticatedUser:
    """Wraps the Supabase user object and includes the raw access token."""
    def __init__(self, user, access_token: str, role: str = "client", tenant_id: str | None = None, status: str = "approved"):
        self.id = user.id
        self.email = user.email
        self.access_token = access_token
        self.role = role
        self.tenant_id = tenant_id
        self.status = status
        self._user = user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthenticatedUser:
    supabase = get_supabase_client()
    try:
        user_response = supabase.auth.get_user(credentials.credentials)
        user = user_response.user
        
        # Look up tenant role from public.profiles using the user's token so RLS applies.
        from app.services.database import get_user_db
        db = get_user_db(credentials.credentials)
        role = "client"
        tenant_id = None
        try:
            profile_response = db.table("profiles").select("role, tenant_id, status").eq("id", user.id).execute()
            if profile_response.data and len(profile_response.data) > 0:
                profile = profile_response.data[0]
                role = profile.get("role", "client")
                tenant_id = profile.get("tenant_id")
                user_status = profile.get("status", "approved")
        except Exception:
            role = "client"
            user_status = "approved"

        return AuthenticatedUser(user, credentials.credentials, role, tenant_id, user_status)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
