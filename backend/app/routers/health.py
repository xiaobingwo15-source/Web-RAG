from fastapi import APIRouter, Response

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "agentic-rag-masterclass"}


@router.head("/health", include_in_schema=False)
async def health_check_head():
    return Response(status_code=200)
