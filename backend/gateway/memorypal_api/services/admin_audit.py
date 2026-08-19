from __future__ import annotations

import logging
import re
import time
import uuid

from fastapi import Request
from fastapi.concurrency import run_in_threadpool


logger = logging.getLogger(__name__)
TRACKING_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,128}$")
ADMIN_USER_MUTATION_RE = re.compile(
    r"^/v1/admin/users/[^/]+(?:/(?:suspend|unsuspend))?$"
)


def _tracking_id(value: str | None) -> str:
    candidate = (value or "").strip()
    return candidate if TRACKING_ID_RE.fullmatch(candidate) else str(uuid.uuid4())


def install_admin_audit_middleware(app) -> None:
    """Audit admin access separately so dashboard polling cannot alter product metrics."""

    @app.middleware("http")
    async def admin_access_audit(request: Request, call_next):
        if not request.url.path.startswith("/v1/admin"):
            return await call_next(request)

        started = time.monotonic()
        is_account_mutation = (
            request.method in {"POST", "DELETE"}
            and ADMIN_USER_MUTATION_RE.fullmatch(request.url.path) is not None
        )
        if is_account_mutation:
            request_id = str(uuid.uuid4())
            correlation_id = str(uuid.uuid4())
        else:
            request_id = _tracking_id(request.headers.get("X-Request-ID"))
            correlation_id = _tracking_id(request.headers.get("X-Correlation-ID"))
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Correlation-ID"] = correlation_id
            return response
        finally:
            latency_ms = max(0, round((time.monotonic() - started) * 1000))
            route = request.scope.get("route")
            normalized_path = str(getattr(route, "path", request.url.path))
            admin_ref = None
            user_id = getattr(request.state, "user_id", None)
            # Invalid/missing credentials are attacker-controlled traffic, not
            # an admin action. Persisting each anonymous 4xx would allow an
            # unauthenticated caller to grow the audit table without bound.
            if status_code < 400 or user_id:
                try:
                    if user_id:
                        row = await run_in_threadpool(
                            request.app.state.db.get_user_by_id, user_id,
                        )
                        if row is not None and row["admin_ref"]:
                            admin_ref = str(row["admin_ref"])
                    await run_in_threadpool(
                        request.app.state.db.record_admin_audit_event,
                        admin_ref=admin_ref,
                        request_id=request_id,
                        correlation_id=correlation_id,
                        http_method=request.method,
                        http_path=normalized_path,
                        http_status=status_code,
                        latency_ms=latency_ms,
                        action=getattr(request.state, "admin_action", None),
                        target_admin_ref=getattr(request.state, "admin_target_ref", None),
                        before_status=getattr(request.state, "admin_before_status", None),
                        after_status=getattr(request.state, "admin_after_status", None),
                    )
                except Exception:
                    # Audit persistence must not replace an otherwise valid API response.
                    logger.exception("Failed to persist admin access audit event")
