from pydantic import BaseModel
from typing import Optional


class UserInfo(BaseModel):
    id: str
    email: Optional[str] = None
