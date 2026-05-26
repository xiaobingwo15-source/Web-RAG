from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.supabase import get_supabase_client

security = HTTPBearer()


class AuthenticatedUser:
    """Wraps the Supabase user object and includes the raw access token."""
    def __init__(self, user, access_token: str):
        self.id = user.id
        self.email = user.email
        self.access_token = access_token
        self._user = user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthenticatedUser:
    supabase = get_supabase_client()
    try:
        user_response = supabase.auth.get_user(credentials.credentials)
        return AuthenticatedUser(user_response.user, credentials.credentials)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
