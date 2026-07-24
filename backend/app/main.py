import asyncio
import logging
import time
from contextlib import asynccontextmanager
from contextlib import suppress
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request
from scalar_fastapi import get_scalar_api_reference
from fastapi.middleware.cors import CORSMiddleware
from app.config import Settings
from app.services.environment_guard import validate_environment_isolation
from app.services.langfuse import configure_langfuse, get_langfuse
from app.services.qdrant_db import ensure_collection
from app.services.runtime_health import (
    mark_startup_complete,
    mark_startup_started,
    process_snapshot,
    record_startup_check,
)
from app.routers import health, auth, chat, documents, tools, admin, owner, widget, eval, upload_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class _SuppressProactorWarning(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "_ProactorSocketTransport" not in record.getMessage()


logging.getLogger("asyncio").addFilter(_SuppressProactorWarning())

settings = Settings()

# Configure Langfuse env vars before client init
configure_langfuse()


async def _run_startup_check(
    name: str,
    operation: Callable[[], Awaitable[Any]],
) -> None:
    started = time.monotonic()
    try:
        result = await operation()
    except Exception as exc:
        duration_ms = round((time.monotonic() - started) * 1000)
        record_startup_check(
            name,
            status="failed",
            duration_ms=duration_ms,
            detail=type(exc).__name__,
        )
        logging.getLogger(__name__).warning(
            "Startup maintenance check %s failed after %dms (%s)",
            name,
            duration_ms,
            type(exc).__name__,
        )
        return

    duration_ms = round((time.monotonic() - started) * 1000)
    if result is False:
        record_startup_check(
            name,
            status="failed",
            duration_ms=duration_ms,
            detail="dependency_unavailable",
        )
        logging.getLogger(__name__).warning(
            "Startup maintenance check %s reported unavailable after %dms",
            name,
            duration_ms,
        )
        return

    detail = f"affected={result}" if isinstance(result, int) and result else None
    record_startup_check(name, status="ok", duration_ms=duration_ms, detail=detail)
    logging.getLogger(__name__).info(
        "Startup maintenance check %s completed in %dms%s",
        name,
        duration_ms,
        f" ({detail})" if detail else "",
    )


async def run_startup_maintenance() -> None:
    """Run dependency checks after the ASGI server becomes live."""
    mark_startup_started()
    process = process_snapshot()
    logging.getLogger(__name__).info(
        "Process booted pid=%s peak_rss_mb=%s; startup maintenance is asynchronous",
        process["pid"],
        process.get("peak_rss_mb", "unavailable"),
    )

    from app.services.database import (
        expire_stale_streaming_messages,
        expire_stale_upload_sessions,
    )

    await _run_startup_check("qdrant", ensure_collection)
    await _run_startup_check(
        "stale_upload_sessions",
        lambda: asyncio.to_thread(expire_stale_upload_sessions),
    )
    await _run_startup_check(
        "stale_streaming_messages",
        lambda: asyncio.to_thread(
            expire_stale_streaming_messages,
            max_age_seconds=settings.chat_pipeline_timeout_seconds + 15,
        ),
    )
    mark_startup_complete()


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_environment_isolation(settings)
    startup_task = asyncio.create_task(
        run_startup_maintenance(),
        name="startup-maintenance",
    )
    app.state.startup_maintenance_task = startup_task
    try:
        yield
    finally:
        if not startup_task.done():
            startup_task.cancel()
        with suppress(asyncio.CancelledError):
            await startup_task

        # Cancel and await detached pipelines so their cancellation handlers
        # persist a terminal status before the process exits.
        from app.services.streaming_tasks import shutdown_streaming_tasks
        await shutdown_streaming_tasks()
        # Flush pending Langfuse events on shutdown
        langfuse = get_langfuse()
        langfuse.flush()


app = FastAPI(
    title="Agentic RAG Masterclass API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if settings.is_production:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(upload_session.router, prefix="/api/documents", tags=["upload"])
app.include_router(tools.router, prefix="/api/tools", tags=["tools"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(owner.router, prefix="/api/owner", tags=["owner"])
app.include_router(widget.router, prefix="/api/widget", tags=["widget"])
app.include_router(eval.router, prefix="/api/eval", tags=["eval"])


if settings.enable_api_docs:
    @app.get("/scalar", include_in_schema=False)
    async def scalar_html():
        return get_scalar_api_reference(
            openapi_url=app.openapi_url,
            title=app.title,
        )
