from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request, Security, status
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
    return CurrentUser(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        token_jti=claims.jti,
        token_expires_at=claims.expires_at,
    )

