import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from scalar_fastapi import get_scalar_api_reference
from fastapi.middleware.cors import CORSMiddleware
from app.config import Settings
from app.services.langfuse import configure_langfuse, get_langfuse
from app.services.qdrant_db import ensure_collection
from app.routers import health, auth, chat, documents, tools, admin

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await ensure_collection()
    except Exception as e:
        logging.getLogger(__name__).warning(
            "Startup: Qdrant init failed (%s) — running in degraded mode", e
        )
    yield
    # Flush pending Langfuse events on shutdown
    langfuse = get_langfuse()
    langfuse.flush()


app = FastAPI(title="Agentic RAG Masterclass API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(tools.router, prefix="/api/tools", tags=["tools"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])


@app.get("/scalar", include_in_schema=False)
async def scalar_html():
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )
