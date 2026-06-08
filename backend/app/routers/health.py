from fastapi import APIRouter, Response
from app.services.embeddings import get_embedding_info

router = APIRouter()


@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "agentic-rag-masterclass",
        "embedding": get_embedding_info(),
    }


@router.head("/health", include_in_schema=False)
async def health_check_head():
    return Response(status_code=200)
