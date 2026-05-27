from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.supabase import get_supabase_client

security = HTTPBearer()


class AuthenticatedUser:
    """Wraps the Supabase user object and includes the raw access token."""
    def __init__(self, user, access_token: str, role: str = "client"):
        self.id = user.id
        self.email = user.email
        self.access_token = access_token
        self.role = role
        self._user = user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthenticatedUser:
    supabase = get_supabase_client()
    try:
        user_response = supabase.auth.get_user(credentials.credentials)
        user = user_response.user
        
        # Look up role from public.profiles using their authenticated client to enforce RLS
        from app.services.database import get_user_db
        db = get_user_db(credentials.credentials)
        role = "client"
        try:
            profile_response = db.table("profiles").select("role").eq("id", user.id).execute()
            if profile_response.data and len(profile_response.data) > 0:
                role = profile_response.data[0].get("role", "client")
        except Exception:
            # Graceful fallback: before SQL migration is run, fallback to hardcoded admin email
            if user.email and user.email.lower() == "admin@example.com":
                role = "admin"
        
        return AuthenticatedUser(user, credentials.credentials, role)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

