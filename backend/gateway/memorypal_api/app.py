from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, load_settings
from .database import Database
from .routes import router
from .services.memory_engine import MemoryEngine
from .services.pipeline import ModelPipeline


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or load_settings()
    db = Database(resolved.database_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.initialize()
        yield

    app = FastAPI(
        title="MemoryPal API",
        version="0.1.0",
        description="JWT authentication, user memory, and Qwen voice pipeline gateway",
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.state.db = db
    app.state.memory_engine = MemoryEngine(db)
    app.state.pipeline = ModelPipeline(resolved)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()

