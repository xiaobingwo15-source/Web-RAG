from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import Settings
from app.services.langfuse import configure_langfuse, get_langfuse
from app.routers import health, auth, chat, documents

settings = Settings()

# Configure Langfuse env vars before client init
configure_langfuse()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Flush pending Langfuse events on shutdown
    langfuse = get_langfuse()
    langfuse.flush()


app = FastAPI(title="Agentic RAG Masterclass API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
