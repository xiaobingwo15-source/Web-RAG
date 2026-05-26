from pydantic import BaseModel
from typing import Optional


class DocumentUploadResponse(BaseModel):
    id: str
    filename: str
    status: str


class DocumentStatus(BaseModel):
    id: str
    filename: str
    status: str
    error_message: Optional[str] = None


class DocumentListResponse(BaseModel):
    documents: list[DocumentStatus]
