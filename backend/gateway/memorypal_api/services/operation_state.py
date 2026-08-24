from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Sequence

from fastapi import Request
from fastapi.concurrency import run_in_threadpool


logger = logging.getLogger(__name__)
TRACKING_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,128}$")
EXCLUDED_PATHS = {
    "/health",
    "/v1/health",
    "/v1/internal/ready",
    "/docs",
    "/openapi.json",
    "/redoc",
}
EXCLUDED_PREFIXES = ("/v1/admin",)
ACCOUNT_ACTIONS = {
    "/v1/auth/profile": "account_profile_update",
    "/v1/auth/password": "account_password_change",
    "/v1/auth/account": "account_deletion",
}


@dataclass(frozen=True, slots=True)
class RequestOperation:
    operation_request_id: str
    request_id: str
    correlation_id: str
    action: str
    started_monotonic: float


EventPublisher = Callable[[dict], Awaitable[None]]
AI_PIPELINE_STAGES = ("stt", "llm", "tts")


@dataclass(slots=True)
class AIPipelineOperation:
    manager: "OperationStateManager"
    request: Request
    operation_id: str
    user_id: str
    stages: tuple[str, ...]
    current_stage: str
    completed: bool = False

    async def complete_stage(self) -> None:
        if self.completed:
            return
        await self.manager.complete_pipeline_stage(self)
        self.completed = True

    async def fail(self, error_code: str = "pipeline_failed") -> None:
        await self.manager.fail_pipeline(self, error_code)

    def move_to(self, stage: str) -> None:
        if stage not in self.stages:
            raise ValueError(f"stage is not part of this pipeline: {stage}")
        self.current_stage = stage
        self.completed = False
        self.request.state.pipeline_stage = stage


def _tracking_id(value: str | None) -> str:
    candidate = (value or "").strip()
    return candidate if TRACKING_ID_RE.fullmatch(candidate) else str(uuid.uuid4())


class OperationStateManager:
    """Durable request state plus a sanitized event stream for future admin analytics."""

    def __init__(self, db, event_publisher: EventPublisher | None = None):
        self.db = db
        self.event_publisher = event_publisher
        self.publisher_id = f"gateway-{uuid.uuid4()}"

    @staticmethod
    def _pipeline_stages(request: Request, default_stages: Sequence[str]) -> tuple[str, ...]:
        requested = tuple(
            item.strip().lower()
            for item in request.headers.get("X-AI-Pipeline-Stages", "").split(",")
            if item.strip()
        )
        stages = requested or tuple(default_stages)
        if (
            not stages
            or len(stages) > len(AI_PIPELINE_STAGES)
            or len(set(stages)) != len(stages)
            or any(stage not in AI_PIPELINE_STAGES for stage in stages)
            or tuple(sorted(stages, key=AI_PIPELINE_STAGES.index)) != stages
        ):
            return tuple(default_stages)
        return stages

    async def start_pipeline(
        self,
        request: Request,
        user_id: str,
        current_stage: str,
        default_stages: Sequence[str],
    ) -> AIPipelineOperation:
        """Join or create one durable operation shared by STT -> LLM/RAG -> TTS."""
        stages = self._pipeline_stages(request, default_stages)
        if current_stage not in stages:
            stages = tuple(default_stages)
        correlation_id = str(request.state.correlation_id)
        row = await run_in_threadpool(
            self.db.begin_operation,
            "ai_pipeline",
            f"pipeline-{user_id}-{correlation_id}",
            correlation_id,
            user_id=user_id,
            resource_id=" -> ".join(stage.upper() for stage in stages),
            status="running",
            metadata={
                "service": "gateway",
                "stages": list(stages),
                "stage_count": len(stages),
                "progress_unit": 100 / len(stages),
            },
        )
        operation_id = str(row["id"])
        request.state.pipeline_operation_id = operation_id
        request.state.pipeline_stage = current_stage
        return AIPipelineOperation(self, request, operation_id, user_id, stages, current_stage)

    async def complete_pipeline_stage(self, pipeline: AIPipelineOperation) -> None:
        stage_number = pipeline.stages.index(pipeline.current_stage) + 1
        progress = round(stage_number * 100 / len(pipeline.stages))
        if stage_number == len(pipeline.stages):
            operation = pipeline.request.state.request_operation
            await run_in_threadpool(
                self.db.finish_operation_with_event,
                operation_id=pipeline.operation_id,
                user_id=pipeline.user_id,
                request_id=operation.request_id,
                correlation_id=operation.correlation_id,
                status="succeeded",
                error_code=None,
                event_type="ai_pipeline",
                http_method=pipeline.request.method,
                http_path=pipeline.request.url.path,
                http_status=200,
                latency_ms=None,
                metadata={
                    "service": "gateway",
                    "stages": list(pipeline.stages),
                    "completed_stage": pipeline.current_stage,
                },
            )
        else:
            await run_in_threadpool(
                self.db.transition_operation,
                pipeline.operation_id,
                "running",
                progress_percent=progress,
                user_id=pipeline.user_id,
                reason=f"stage_completed:{pipeline.current_stage}:{stage_number}/{len(pipeline.stages)}",
            )

    async def fail_pipeline(self, pipeline: AIPipelineOperation, error_code: str) -> None:
        row = await run_in_threadpool(self.db.get_operation, pipeline.operation_id)
        if row is None or str(row["status"]) in {"succeeded", "failed", "cancelled"}:
            return
        operation = pipeline.request.state.request_operation
        await run_in_threadpool(
            self.db.finish_operation_with_event,
            operation_id=pipeline.operation_id,
            user_id=pipeline.user_id,
            request_id=operation.request_id,
            correlation_id=operation.correlation_id,
            status="failed",
            error_code=error_code[:100],
            event_type="ai_pipeline",
            http_method=pipeline.request.method,
            http_path=pipeline.request.url.path,
            http_status=500,
            latency_ms=None,
            metadata={
                "service": "gateway",
                "stages": list(pipeline.stages),
                "failed_stage": pipeline.current_stage,
            },
        )

    async def begin_request(self, request: Request) -> RequestOperation | None:
        if (
            request.method == "OPTIONS"
            or request.url.path in EXCLUDED_PATHS
            or request.url.path.startswith(EXCLUDED_PREFIXES)
        ):
            return None
        action = ACCOUNT_ACTIONS.get(request.url.path, "http_request")
        if action in ACCOUNT_ACTIONS.values():
            # Sensitive account endpoints never trust client trace headers;
            # those values could themselves contain a nickname or password.
            request_id = str(uuid.uuid4())
            correlation_id = str(uuid.uuid4())
        else:
            request_id = _tracking_id(request.headers.get("X-Request-ID"))
            correlation_id = _tracking_id(request.headers.get("X-Correlation-ID"))
        # Generate trace context before routing, but delay durable persistence
        # until authentication and the response status are known. Otherwise an
        # attacker can fill several telemetry tables with unauthenticated 4xxs.
        operation = RequestOperation(
            operation_request_id=f"http-{uuid.uuid4()}",
            request_id=request_id,
            correlation_id=correlation_id,
            action=action,
            started_monotonic=time.monotonic(),
        )
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        request.state.request_operation = operation
        return operation

    async def finish_request(
        self,
        request: Request,
        operation: RequestOperation | None,
        status_code: int,
    ) -> None:
        if operation is None:
            return
        pipeline_operation_id = getattr(request.state, "pipeline_operation_id", None)
        if pipeline_operation_id is not None:
            # Pipeline routes own their multi-request lifecycle. In particular, a
            # streaming response returns its headers before LLM generation ends,
            # so this middleware must not mark the shared operation complete.
            if status_code >= 400:
                row = await run_in_threadpool(self.db.get_operation, pipeline_operation_id)
                if row is not None and str(row["status"]) not in {"succeeded", "failed", "cancelled"}:
                    await run_in_threadpool(
                        self.db.transition_operation,
                        pipeline_operation_id,
                        "failed",
                        user_id=getattr(request.state, "user_id", None),
                        error_code=f"http_{status_code}",
                        reason=f"stage_failed:{getattr(request.state, 'pipeline_stage', 'unknown')}",
                    )
            return
        latency_ms = max(0, round((time.monotonic() - operation.started_monotonic) * 1000))
        # Credential/profile payloads are never recorded. A successful account
        # deletion explicitly clears request.state.user_id in the route, leaving
        # its final action/status event anonymous. Anonymous failures are not
        # durable telemetry because they are attacker-controlled and unbounded.
        user_id = getattr(request.state, "user_id", None)
        if status_code >= 400 and user_id is None:
            return
        terminal_status = "succeeded" if status_code < 400 else "failed"
        error_code = None if status_code < 400 else f"http_{status_code}"
        route = request.scope.get("route")
        normalized_path = str(getattr(route, "path", request.url.path))
        try:
            row = await run_in_threadpool(
                self.db.begin_operation,
                operation.action,
                operation.operation_request_id,
                operation.correlation_id,
                user_id=user_id,
                resource_id=f"{request.method} {normalized_path}",
                status="running",
                metadata={"service": "gateway"},
            )
            operation_id = str(row["id"])
            request.state.operation_id = operation_id
            _updated, event_id = await run_in_threadpool(
                self.db.finish_operation_with_event,
                operation_id=operation_id,
                user_id=user_id,
                request_id=operation.request_id,
                correlation_id=operation.correlation_id,
                status=terminal_status,
                error_code=error_code,
                event_type=operation.action,
                http_method=request.method,
                http_path=normalized_path,
                http_status=status_code,
                latency_ms=latency_ms,
                metadata={"service": "gateway"},
            )
            if self.event_publisher is not None:
                claimed = await run_in_threadpool(
                    self.db.claim_outbox_event,
                    event_id,
                    self.publisher_id,
                )
                if claimed:
                    try:
                        await self.event_publisher({
                            "event_id": event_id,
                            "operation_id": operation_id,
                            "request_id": operation.request_id,
                            "correlation_id": operation.correlation_id,
                            "user_id": user_id,
                            "event_type": operation.action,
                            "status": terminal_status,
                            "http_method": request.method,
                            "http_path": normalized_path,
                            "http_status": status_code,
                            "latency_ms": latency_ms,
                        })
                    except Exception:
                        await run_in_threadpool(
                            self.db.mark_outbox_failed,
                            event_id,
                            self.publisher_id,
                        )
                        raise
                    await run_in_threadpool(
                        self.db.mark_outbox_published,
                        event_id,
                        self.publisher_id,
                    )
        except Exception:
            # Telemetry failures must not replace a successful user response.
            logger.exception("Failed to finalize request operation state")


def install_operation_middleware(app) -> None:
    @app.middleware("http")
    async def operation_tracking(request: Request, call_next):
        manager: OperationStateManager = request.app.state.operation_state_manager
        operation = await manager.begin_request(request)
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            if operation is not None:
                response.headers["X-Request-ID"] = operation.request_id
                response.headers["X-Correlation-ID"] = operation.correlation_id
            return response
        finally:
            await manager.finish_request(request, operation, status_code)
