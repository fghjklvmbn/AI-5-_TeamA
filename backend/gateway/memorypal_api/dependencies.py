from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .security import TokenError, decode_access_token


bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: str
    email: str
    display_name: str
    token_jti: str
    token_expires_at: int
    auth_version: int


@dataclass(frozen=True, slots=True)
class CurrentAdmin:
    id: str
    user_ref: str
    authorization_source: str
    auth_version: int


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(bearer),
) -> CurrentUser:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="로그인이 필요합니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    try:
        claims = decode_access_token(credentials.credentials, request.app.state.settings.jwt_secret)
    except TokenError as exc:
        unauthorized.detail = str(exc)
        raise unauthorized from exc
    db = request.app.state.db
    if db.is_token_revoked(claims.jti):
        unauthorized.detail = "로그아웃된 토큰입니다."
        raise unauthorized
    row = db.get_user_by_id(claims.user_id)
    if row is None:
        raise unauthorized
    if str(row["account_status"]) != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="현재 이용할 수 없는 계정입니다.",
        )
    if int(row["auth_version"]) != claims.auth_version:
        unauthorized.detail = "로그인 정보가 변경되었습니다. 다시 로그인해 주세요."
        raise unauthorized
    # The operation middleware reads this after the endpoint completes. Only
    # the stable user id is attached; credentials and token claims are excluded.
    request.state.user_id = str(row["id"])
    return CurrentUser(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        token_jti=claims.jti,
        token_expires_at=claims.expires_at,
        auth_version=claims.auth_version,
    )


def get_current_admin(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> CurrentAdmin:
    """Fail closed unless the current DB row or the server allowlist grants access."""
    row = request.app.state.db.get_user_by_id(user.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="인증이 필요합니다.")
    allowlisted = str(row["email"]).casefold() in request.app.state.settings.admin_emails
    database_admin = request.app.state.db.is_admin_user(user.id)
    if not allowlisted and not database_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="관리자 권한이 없습니다.")
    admin_ref = row["admin_ref"]
    if not admin_ref:
        # Missing migration state must never weaken authorization or expose the raw id.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="관리자 식별자 마이그레이션이 필요합니다.",
        )
    request.state.admin_id = user.id
    return CurrentAdmin(
        id=user.id,
        user_ref=str(admin_ref),
        authorization_source="database" if database_admin else "allowlist",
        auth_version=user.auth_version,
    )

