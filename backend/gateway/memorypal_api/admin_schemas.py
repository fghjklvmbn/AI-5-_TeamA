from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


OperationStatus = Literal[
    "queued", "running", "retrying", "succeeded", "failed", "cancelled",
]
AccountStatus = Literal["active", "suspended", "deactivated"]


class AdminMeResponse(BaseModel):
    user_id: str
    role: Literal["admin"] = "admin"
    authorization_source: Literal["allowlist", "database"]


class AdminMetricRow(BaseModel):
    event_type: str
    status: str
    http_path: str
    transaction_count: int = Field(ge=0)
    user_count: int = Field(ge=0)
    average_latency_ms: float = Field(ge=0)
    maximum_latency_ms: int = Field(ge=0)


class AdminOverviewResponse(BaseModel):
    generated_at: str
    range_from: str
    range_to: str
    total_user_count: int = Field(ge=0)
    active_user_count: int = Field(ge=0)
    transaction_count: int = Field(ge=0)
    succeeded_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    average_latency_ms: float = Field(ge=0)
    maximum_latency_ms: int = Field(ge=0)
    operations: dict[str, int]
    outbox: dict[str, int]
    routes: list[AdminMetricRow]


class AdminTransactionItem(BaseModel):
    event_id: str
    user_id: str | None = None
    operation_id: str | None = None
    request_id: str
    correlation_id: str
    event_type: str
    status: str
    http_method: str | None = None
    http_path: str | None = None
    http_status: int | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    occurred_at: str


class AdminTransactionListResponse(BaseModel):
    items: list[AdminTransactionItem]
    next_cursor: str | None = None
    range_from: str
    range_to: str


class AdminOperationItem(BaseModel):
    id: str
    user_id: str | None = None
    request_id: str
    correlation_id: str
    operation_type: str
    status: OperationStatus
    progress_percent: int = Field(ge=0, le=100)
    version: int = Field(ge=1)
    error_code: str | None = None
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None


class AdminOperationListResponse(BaseModel):
    items: list[AdminOperationItem]
    next_cursor: str | None = None
    range_from: str
    range_to: str


class AdminTransitionItem(BaseModel):
    id: str
    operation_id: str
    from_status: OperationStatus | None = None
    to_status: OperationStatus
    version: int = Field(ge=1)
    progress_percent: int = Field(ge=0, le=100)
    occurred_at: str


class AdminTransitionListResponse(BaseModel):
    items: list[AdminTransitionItem]


class AdminCorrelationResponse(BaseModel):
    correlation_id: str
    transactions: list[AdminTransactionItem]
    operations: list[AdminOperationItem]


class AdminUserItem(BaseModel):
    # This is users.admin_ref, never the authentication/user primary key.
    user_id: str
    created_at: str
    account_status: AccountStatus
    status_version: int = Field(ge=1)
    status_changed_at: datetime
    suspended_at: datetime | None = None
    deactivated_at: datetime | None = None
    protected: bool
    session_count: int = Field(ge=0)
    message_count: int = Field(ge=0)
    memory_count: int = Field(ge=0)
    transaction_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    last_seen_at: str | None = None


class AdminUserListResponse(BaseModel):
    items: list[AdminUserItem]
    next_cursor: str | None = None
    range_from: str
    range_to: str


class AdminSuspendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class AdminDeactivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: Literal["DEACTIVATE"]
    expected_version: int = Field(ge=1)


class AdminAccountStatusResponse(BaseModel):
    user_id: str
    account_status: AccountStatus
    status_version: int = Field(ge=1)
    status_changed_at: datetime
    suspended_at: datetime | None = None
    deactivated_at: datetime | None = None
