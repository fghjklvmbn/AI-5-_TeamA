from __future__ import annotations

import asyncio
import uuid
import weakref
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .admin_routes import router as admin_router
from .model_routes import router as model_router
from .mcp_routes import router as mcp_router
from .config import Settings, load_settings  # Workers read deployment endpoints at startup.
from .database import AccountAccessFenceError
from .database_factory import create_database
from .routes import dispatch_portrait_task, portrait_operation_for, router
from .services.document_engine import DocumentEngine
from .services.admin_audit import install_admin_audit_middleware
from .services.archive_cleanup import (
    archive_cleanup_loop,
    legacy_voice_reconciliation_loop,
)
from .services.agent_loop import AgentLoop
from .services.memory_engine import MemoryEngine
from .services.model_manager import ModelManager
from .services.semantic_rag import SemanticRagEngine
from .services.operation_state import OperationStateManager, install_operation_middleware
from .services.pipeline import ModelPipeline
from .services.portrait_engine import PortraitEngine
from .services.task_queue import create_task_queue
from .services.tool_registry import GatewayToolRegistry
from .services.web_search import WebSearchEngine
from .services.hardware_monitor import HardwareMonitorHub


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or load_settings()
    db = create_database(resolved)
    if resolved.task_queue_mode not in {"local", "redis"}:
        raise ValueError("MEMORYPAL_TASK_QUEUE_MODE must be 'local' or 'redis'")
    if resolved.task_queue_mode == "redis" and not resolved.redis_url:
        raise ValueError("Redis queue mode requires MEMORYPAL_REDIS_URL")
    task_queue = create_task_queue(
        resolved.redis_url if resolved.task_queue_mode == "redis" else "",
        namespace=resolved.redis_prefix,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.initialize()
        cleanup_worker = asyncio.create_task(
            archive_cleanup_loop(app, f"gateway-{uuid.uuid4()}")
        )
        legacy_voice_worker = asyncio.create_task(
            legacy_voice_reconciliation_loop(app)
        )
        hardware_monitor_worker = asyncio.create_task(app.state.hardware_monitor.run())
        # Durable queued/analyzing jobs survive an unclean restart. The lease in
        # PortraitEngine ensures only one app worker can actually resume each job.
        for row in db.list_active_portraits():
            operation = portrait_operation_for(
                db, row["user_id"], row["generation_id"],
            )
            await dispatch_portrait_task(
                app, row["user_id"], row["generation_id"], row["persona"], operation,
            )
        try:
            yield
        finally:
            cleanup_worker.cancel()
            legacy_voice_worker.cancel()
            hardware_monitor_worker.cancel()
            tasks = list(app.state.portrait_tasks.values())
            tasks.extend(app.state.archive_cleanup_tasks)
            tasks.extend(app.state.chat_postprocess_tasks)
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.gather(cleanup_worker, return_exceptions=True)
            await asyncio.gather(legacy_voice_worker, return_exceptions=True)
            await asyncio.gather(hardware_monitor_worker, return_exceptions=True)
            queue_client = getattr(task_queue, "client", None)
            if queue_client is not None:
                await asyncio.to_thread(queue_client.close)
            db.close()

    app = FastAPI(
        title="MemoryPal API",
        version="0.1.0",
        description="JWT 인증, 사용자 개인화 기억, AI 파이프라인 게이트웨이 서버",
        root_path=resolved.root_path,
        lifespan=lifespan,
    )

    @app.exception_handler(RequestValidationError)
    async def sanitized_validation_error(_request: Request, exc: RequestValidationError):
        errors = []
        for raw_error in exc.errors():
            error = dict(raw_error)
            if any(
                any(marker in str(part).casefold() for marker in ("password", "reason"))
                for part in error.get("loc", ())
            ):
                error.pop("input", None)
            errors.append(error)
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder({"detail": errors}),
        )

    @app.exception_handler(AccountAccessFenceError)
    async def account_access_fence_error(_request: Request, _exc: AccountAccessFenceError):
        return JSONResponse(
            status_code=403,
            content={"detail": "계정 상태 또는 인증 정보가 변경되어 결과를 저장하지 않았습니다."},
        )
    app.state.settings = resolved
    app.state.db = db
    app.state.memory_engine = MemoryEngine(db)
    app.state.document_engine = DocumentEngine(db)
    app.state.web_search_engine = WebSearchEngine(resolved.web_search_max_results)
    app.state.tool_registry = GatewayToolRegistry(
        app.state.memory_engine, app.state.document_engine, app.state.web_search_engine,
    )
    app.state.pipeline = ModelPipeline(resolved)
    app.state.model_manager = ModelManager(resolved)
    app.state.hardware_monitor = HardwareMonitorHub(resolved)
    app.state.semantic_rag = SemanticRagEngine(
        db, app.state.pipeline, app.state.document_engine,
    )
    app.state.agent_loop = AgentLoop(
        app.state.pipeline, semantic_rag=app.state.semantic_rag,
        tool_registry=app.state.tool_registry,
    )
    app.state.task_queue = task_queue
    app.state.portrait_engine = PortraitEngine(db)
    app.state.portrait_tasks = {}
    app.state.archive_cleanup_tasks = set()
    app.state.chat_postprocess_tasks = set()
    # The deployment uses a single modest GPU. Serialize portrait jobs so two
    # persona models are never asked to occupy VRAM at the same time.
    app.state.portrait_generation_semaphore = asyncio.Semaphore(1)
    async def publish_operation_event(event: dict) -> None:
        analytics = {"duration_ms": int(event.get("latency_ms") or 0)}
        if event.get("status") == "failed":
            analytics["error_code"] = f"http_{event.get('http_status') or 500}"
        await asyncio.to_thread(
            task_queue.publish_event,
            # Database event_id is the stable idempotency key. Redis may assign
            # different stream IDs after an at-least-once redelivery.
            task_id=str(event["event_id"]),
            request_id=str(event["request_id"]),
            correlation_id=str(event["correlation_id"]),
            queue="http",
            state=str(event["status"]),
            attempt=1,
            analytics=analytics,
        )

    app.state.operation_state_manager = OperationStateManager(
        db, event_publisher=publish_operation_event,
    )
    app.state.message_audio_locks = weakref.WeakValueDictionary()
    install_operation_middleware(app)
    install_admin_audit_middleware(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.include_router(mcp_router)
    app.include_router(model_router)
    app.include_router(admin_router)
    return app


app = create_app()
