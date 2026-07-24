from fastapi import APIRouter, Response, status

from app.services.runtime_health import liveness_payload, startup_snapshot

router = APIRouter()


@router.get("/health")
async def health_check(response: Response):
    """Dependency-free liveness check used by Render and UptimeRobot."""
    payload = liveness_payload()
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Web-Rag-Pid"] = str(payload["process"]["pid"])
    return payload


@router.head("/health", include_in_schema=False)
async def health_check_head():
    return Response(status_code=200, headers={"Cache-Control": "no-store"})


@router.get("/health/ready", include_in_schema=False)
async def readiness_check(response: Response):
    """Expose background startup state without making liveness depend on it."""
    startup = startup_snapshot()
    ready = startup["phase"] == "ready"
    response.status_code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
    response.headers["Cache-Control"] = "no-store"
    return {
        "status": "ready" if ready else "not_ready",
        "startup": startup,
    }
