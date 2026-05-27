from fastapi import APIRouter, Depends
from app.middleware.auth import get_current_user

router = APIRouter()


@router.get("/me")
async def get_me(user=Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "role": user.role}

