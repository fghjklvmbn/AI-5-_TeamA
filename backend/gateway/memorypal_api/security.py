from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any


class TokenError(ValueError):
    pass


def _b64_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    if len(password) < 8:
        raise ValueError("비밀번호는 8자 이상이어야 합니다.")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return _b64_encode(digest), _b64_encode(salt)


def verify_password(password: str, encoded_hash: str, encoded_salt: str) -> bool:
    try:
        actual, _ = hash_password(password, _b64_decode(encoded_salt))
        return hmac.compare_digest(actual, encoded_hash)
    except (ValueError, binascii.Error):
        return False


@dataclass(frozen=True, slots=True)
class TokenClaims:
    user_id: str
    email: str
    jti: str
    expires_at: int
    auth_version: int


def create_access_token(
    user_id: str,
    email: str,
    secret: str,
    ttl_minutes: int,
    auth_version: int = 1,
) -> tuple[str, TokenClaims]:
    now = int(time.time())
    claims = TokenClaims(
        user_id=user_id,
        email=email,
        jti=str(uuid.uuid4()),
        expires_at=now + ttl_minutes * 60,
        auth_version=max(1, int(auth_version)),
    )
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": claims.user_id,
        "email": claims.email,
        "jti": claims.jti,
        "iat": now,
        "exp": claims.expires_at,
        "ver": claims.auth_version,
        "iss": "memorypal",
        "aud": "memorypal-mobile",
    }
    signing_input = ".".join(
        _b64_encode(json.dumps(part, separators=(",", ":")).encode("utf-8"))
        for part in (header, payload)
    )
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256)
    return f"{signing_input}.{_b64_encode(signature.digest())}", claims


def decode_access_token(token: str, secret: str, now: int | None = None) -> TokenClaims:
    try:
        header_part, payload_part, signature_part = token.split(".")
        header: dict[str, Any] = json.loads(_b64_decode(header_part))
        payload: dict[str, Any] = json.loads(_b64_decode(payload_part))
    except (ValueError, binascii.Error, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TokenError("잘못된 토큰 형식입니다.") from exc

    if header.get("alg") != "HS256" or header.get("typ") != "JWT":
        raise TokenError("지원하지 않는 토큰입니다.")

    signing_input = f"{header_part}.{payload_part}"
    expected = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256)
    try:
        signature = _b64_decode(signature_part)
    except (ValueError, binascii.Error) as exc:
        raise TokenError("토큰 서명이 올바르지 않습니다.") from exc
    if not hmac.compare_digest(expected.digest(), signature):
        raise TokenError("토큰 서명이 올바르지 않습니다.")

    required = ("sub", "email", "jti", "exp")
    if payload.get("iss") != "memorypal" or payload.get("aud") != "memorypal-mobile":
        raise TokenError("토큰 발급 정보가 올바르지 않습니다.")
    if not all(payload.get(field) for field in required):
        raise TokenError("필수 토큰 정보가 없습니다.")
    if int(payload["exp"]) <= (int(time.time()) if now is None else now):
        raise TokenError("로그인이 만료되었습니다.")

    try:
        auth_version = int(payload.get("ver", 1))
    except (TypeError, ValueError) as exc:
        raise TokenError("유효하지 않은 인증 버전입니다.") from exc
    if auth_version < 1:
        raise TokenError("유효하지 않은 인증 버전입니다.")
    return TokenClaims(
        user_id=str(payload["sub"]),
        email=str(payload["email"]),
        jti=str(payload["jti"]),
        expires_at=int(payload["exp"]),
        auth_version=auth_version,
    )
