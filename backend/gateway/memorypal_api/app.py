from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, load_settings  # Workers read deployment endpoints at startup.
from .database import Database
from .routes import router
from .services.document_engine import DocumentEngine
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
        description="JWT 인증, 사용자 개인화 기억, AI 파이프라인 게이트웨이 서버",
        root_path=resolved.root_path,
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.state.db = db
    app.state.memory_engine = MemoryEngine(db)
    app.state.document_engine = DocumentEngine(db)
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

