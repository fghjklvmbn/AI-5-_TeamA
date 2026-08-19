from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from .admin_schemas import (
    AdminAccountStatusResponse,
    AdminCorrelationResponse,
    AdminDeactivateRequest,
    AdminMeResponse,
    AdminOperationListResponse,
    AdminOverviewResponse,
    AdminTransactionListResponse,
    AdminTransitionListResponse,
    AdminSuspendRequest,
    AdminUserListResponse,
)
from .database import AccountStateTransitionError
from .dependencies import CurrentAdmin, get_current_admin


router = APIRouter(prefix="/v1/admin", tags=["admin"])
StatusFilter = Literal["queued", "running", "retrying", "succeeded", "failed", "cancelled"]
AccountStatusFilter = Literal["active", "suspended", "deactivated"]
Limit = Annotated[int, Query(ge=1, le=200)]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _time_window(
    from_at: datetime | None,
    to_at: datetime | None,
) -> tuple[str, str]:
    end = _as_utc(to_at) if to_at else datetime.now(UTC)
    start = _as_utc(from_at) if from_at else end - timedelta(hours=24)
    if start >= end:
        raise HTTPException(status_code=422, detail="from은 to보다 이전이어야 합니다.")
    if end - start > timedelta(days=31):
        raise HTTPException(status_code=422, detail="조회 기간은 최대 31일입니다.")
    return start.isoformat(), end.isoformat()


def _cursor(at: str, item_id: str) -> str:
    raw = json.dumps({"at": at, "id": item_id}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    if len(value) > 512:
        raise HTTPException(status_code=422, detail="잘못된 cursor입니다.")
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = json.loads(base64.b64decode(padded, altchars=b"-_", validate=True))
        at = _as_utc(datetime.fromisoformat(str(decoded["at"]))).isoformat()
        item_id = str(decoded["id"])
        if not item_id or len(item_id) > 128:
            raise ValueError
        return at, item_id
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="잘못된 cursor입니다.") from exc


def _rows(rows) -> list[dict]:
    return [
        {
            key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in dict(row).items()
        }
        for row in rows
    ]


@router.get("/me", response_model=AdminMeResponse)
def admin_me(admin: CurrentAdmin = Depends(get_current_admin)):
    return AdminMeResponse(
        user_id=admin.user_ref,
        authorization_source=admin.authorization_source,
    )


@router.get("/overview", response_model=AdminOverviewResponse)
def overview(
    request: Request,
    from_at: datetime | None = Query(default=None, alias="from"),
    to_at: datetime | None = Query(default=None, alias="to"),
    _admin: CurrentAdmin = Depends(get_current_admin),
):
    range_from, range_to = _time_window(from_at, to_at)
    result = request.app.state.db.admin_overview(
        occurred_from=range_from, occurred_to=range_to,
    )
    return {
        **result,
        "generated_at": datetime.now(UTC).isoformat(),
        "range_from": range_from,
        "range_to": range_to,
    }


@router.get("/services")
async def service_hardware_status(
    request: Request,
    history_limit: int = Query(default=100, ge=0, le=500),
    _admin: CurrentAdmin = Depends(get_current_admin),
):
    return await request.app.state.hardware_monitor.snapshot(history_limit)


@router.get("/transactions", response_model=AdminTransactionListResponse)
def transactions(
    request: Request,
    from_at: datetime | None = Query(default=None, alias="from"),
    to_at: datetime | None = Query(default=None, alias="to"),
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    user_id: str | None = Query(default=None, max_length=128),
    correlation_id: str | None = Query(default=None, min_length=8, max_length=128),
    event_type: str | None = Query(default=None, max_length=80),
    cursor: str | None = Query(default=None, max_length=512),
    limit: Limit = 50,
    _admin: CurrentAdmin = Depends(get_current_admin),
):
    range_from, range_to = _time_window(from_at, to_at)
    before, before_id = _decode_cursor(cursor)
    rows = request.app.state.db.list_admin_transactions(
        user_ref=user_id,
        status=status_filter,
        correlation_id=correlation_id,
        event_type=event_type,
        occurred_from=range_from,
        occurred_to=range_to,
        before=before,
        before_id=before_id,
        limit=limit,
    )
    items = _rows(rows)
    next_cursor = None
    if len(items) == limit:
        next_cursor = _cursor(items[-1]["occurred_at"], items[-1]["event_id"])
    return {
        "items": items,
        "next_cursor": next_cursor,
        "range_from": range_from,
        "range_to": range_to,
    }


@router.get("/operations", response_model=AdminOperationListResponse)
def operations(
    request: Request,
    from_at: datetime | None = Query(default=None, alias="from"),
    to_at: datetime | None = Query(default=None, alias="to"),
    status_filter: StatusFilter | None = Query(default=None, alias="status"),
    user_id: str | None = Query(default=None, max_length=128),
    correlation_id: str | None = Query(default=None, min_length=8, max_length=128),
    operation_type: str | None = Query(default=None, max_length=80),
    cursor: str | None = Query(default=None, max_length=512),
    limit: Limit = 50,
    _admin: CurrentAdmin = Depends(get_current_admin),
):
    range_from, range_to = _time_window(from_at, to_at)
    before, before_id = _decode_cursor(cursor)
    rows = request.app.state.db.list_admin_operations(
        user_ref=user_id,
        status=status_filter,
        correlation_id=correlation_id,
        operation_type=operation_type,
        occurred_from=range_from,
        occurred_to=range_to,
        before=before,
        before_id=before_id,
        limit=limit,
    )
    items = _rows(rows)
    next_cursor = None
    if len(items) == limit:
        next_cursor = _cursor(items[-1]["updated_at"], items[-1]["id"])
    return {
        "items": items,
        "next_cursor": next_cursor,
        "range_from": range_from,
        "range_to": range_to,
    }


@router.get(
    "/operations/{operation_id}/transitions",
    response_model=AdminTransitionListResponse,
)
def operation_transitions(
    request: Request,
    operation_id: str = Path(min_length=8, max_length=128),
    limit: Limit = 100,
    _admin: CurrentAdmin = Depends(get_current_admin),
):
    if request.app.state.db.get_operation(operation_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="작업을 찾을 수 없습니다.")
    rows = request.app.state.db.list_admin_operation_transitions(
        operation_id, limit=limit,
    )
    return {"items": _rows(rows)}


@router.get("/correlations/{correlation_id}", response_model=AdminCorrelationResponse)
def correlation(
    request: Request,
    correlation_id: str = Path(min_length=8, max_length=128),
    from_at: datetime | None = Query(default=None, alias="from"),
    to_at: datetime | None = Query(default=None, alias="to"),
    _admin: CurrentAdmin = Depends(get_current_admin),
):
    range_from, range_to = _time_window(from_at, to_at)
    transactions = request.app.state.db.list_admin_transactions(
        correlation_id=correlation_id,
        occurred_from=range_from,
        occurred_to=range_to,
        limit=200,
    )
    operations = request.app.state.db.list_admin_operations(
        correlation_id=correlation_id,
        occurred_from=range_from,
        occurred_to=range_to,
        limit=200,
    )
    if not transactions and not operations:
        raise HTTPException(status_code=404, detail="상관관계 추적 기록을 찾을 수 없습니다.")
    return {
        "correlation_id": correlation_id,
        "transactions": _rows(transactions),
        "operations": _rows(operations),
    }


@router.get("/users", response_model=AdminUserListResponse)
def users(
    request: Request,
    from_at: datetime | None = Query(default=None, alias="from"),
    to_at: datetime | None = Query(default=None, alias="to"),
    status_filter: AccountStatusFilter | None = Query(default=None, alias="status"),
    cursor: str | None = Query(default=None, max_length=512),
    limit: Limit = 50,
    _admin: CurrentAdmin = Depends(get_current_admin),
):
    range_from, range_to = _time_window(from_at, to_at)
    before, before_id = _decode_cursor(cursor)
    rows = request.app.state.db.list_admin_users(
        account_status=status_filter,
        occurred_from=range_from,
        occurred_to=range_to,
        before=before,
        before_id=before_id,
        limit=limit + 1,
    )
    protected_emails = set(request.app.state.settings.admin_emails)
    all_items = []
    for item in _rows(rows):
        item["protected"] = bool(item.pop("_is_admin")) or str(
            item.pop("_admin_email")
        ).casefold() in protected_emails
        all_items.append(item)
    has_more = len(all_items) > limit
    items = all_items[:limit]
    next_cursor = (
        _cursor(items[-1]["created_at"], items[-1]["user_id"])
        if has_more and items else None
    )
    return {
        "items": items,
        "next_cursor": next_cursor,
        "range_from": range_from,
        "range_to": range_to,
    }


def _account_status_response(row) -> dict:
    return {
        "user_id": str(row["admin_ref"]),
        "account_status": str(row["account_status"]),
        "status_version": int(row["status_version"]),
        "status_changed_at": row["status_changed_at"],
        "suspended_at": row["suspended_at"],
        "deactivated_at": row["deactivated_at"],
    }


def _transition_admin_user(
    request: Request,
    admin: CurrentAdmin,
    target_ref: str,
    action: str,
    expected_version: int,
):
    request.state.admin_action = action
    request.state.admin_target_ref = target_ref
    try:
        row, _changed, before_status = request.app.state.db.transition_admin_account_status(
            actor_user_id=admin.id,
            actor_admin_ref=admin.user_ref,
            actor_expected_auth_version=admin.auth_version,
            target_admin_ref=target_ref,
            action=action,
            expected_version=expected_version,
            protected_admin_emails=request.app.state.settings.admin_emails,
            request_id=str(request.state.request_id),
            correlation_id=str(request.state.correlation_id),
        )
    except AccountStateTransitionError as exc:
        if exc.code == "target_not_found":
            raise HTTPException(status_code=404, detail="대상 계정을 찾을 수 없습니다.") from exc
        if exc.code in {"self_target", "protected_admin", "actor_forbidden"}:
            raise HTTPException(
                status_code=403,
                detail="해당 계정의 상태를 변경할 권한이 없습니다.",
            ) from exc
        raise HTTPException(
            status_code=409,
            detail="허용되지 않는 계정 상태 전이입니다.",
        ) from exc
    request.state.admin_before_status = before_status
    request.state.admin_after_status = str(row["account_status"])
    return row


@router.post(
    "/users/{user_ref}/suspend",
    response_model=AdminAccountStatusResponse,
)
def suspend_user(
    payload: AdminSuspendRequest,
    request: Request,
    user_ref: str = Path(min_length=8, max_length=128),
    admin: CurrentAdmin = Depends(get_current_admin),
):
    return _account_status_response(
        _transition_admin_user(
            request, admin, user_ref, "admin_user_suspend", payload.expected_version,
        )
    )


@router.post(
    "/users/{user_ref}/unsuspend",
    response_model=AdminAccountStatusResponse,
)
def unsuspend_user(
    payload: AdminSuspendRequest,
    request: Request,
    user_ref: str = Path(min_length=8, max_length=128),
    admin: CurrentAdmin = Depends(get_current_admin),
):
    return _account_status_response(
        _transition_admin_user(
            request, admin, user_ref, "admin_user_unsuspend", payload.expected_version,
        )
    )


@router.delete(
    "/users/{user_ref}",
    response_model=AdminAccountStatusResponse,
)
def deactivate_user(
    payload: AdminDeactivateRequest,
    request: Request,
    user_ref: str = Path(min_length=8, max_length=128),
    admin: CurrentAdmin = Depends(get_current_admin),
):
    return _account_status_response(
        _transition_admin_user(
            request, admin, user_ref, "admin_user_deactivate", payload.expected_version,
        )
    )
