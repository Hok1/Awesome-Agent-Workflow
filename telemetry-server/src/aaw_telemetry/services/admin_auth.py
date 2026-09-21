from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import Request, Response

from ..config import Settings
from ..errors import ApiError

ADMIN_COOKIE = "aaw_admin_session"


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True)
class AdminContext:
    actor: str
    csrf_token: str
    expires_at: int


class AdminLoginLimiter:
    """Small in-process limiter; reverse proxy remains the outer production limit."""

    def __init__(self, *, attempts: int = 8, window_seconds: int = 300):
        self.attempts = attempts
        self.window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, client: str, now: float) -> None:
        with self._lock:
            entries = self._failures[client]
            while entries and entries[0] <= now - self.window_seconds:
                entries.popleft()
            if len(entries) >= self.attempts:
                raise ApiError(429, "ADMIN_LOGIN_RATE_LIMITED", "管理员密码尝试过多，请稍后再试")

    def failed(self, client: str, now: float) -> None:
        with self._lock:
            self._failures[client].append(now)

    def succeeded(self, client: str) -> None:
        with self._lock:
            self._failures.pop(client, None)


class AdminAuth:
    def __init__(self, settings: Settings):
        self.settings = settings
        password = settings.admin_password.get_secret_value().encode("utf-8")
        self._key = hashlib.sha256(b"aaw-admin-session-v1\0" + password).digest()
        self._limiter = AdminLoginLimiter()

    @staticmethod
    def _client(request: Request) -> str:
        return request.headers.get("x-real-ip") or (
            request.client.host if request.client else "unknown"
        )

    def login(self, request: Request, response: Response, password: str) -> AdminContext:
        client = self._client(request)
        now = time.time()
        self._limiter.check(client, now)
        expected = self.settings.admin_password.get_secret_value()
        if not hmac.compare_digest(password, expected):
            self._limiter.failed(client, now)
            raise ApiError(401, "ADMIN_PASSWORD_INVALID", "系统管理员密码错误")
        self._limiter.succeeded(client)
        expires_at = int(now) + self.settings.admin_session_seconds
        context = AdminContext(
            actor="系统管理员",
            csrf_token=secrets.token_urlsafe(24),
            expires_at=expires_at,
        )
        response.set_cookie(
            ADMIN_COOKIE,
            self._encode(context),
            max_age=self.settings.admin_session_seconds,
            httponly=True,
            secure=self.settings.admin_cookie_secure,
            samesite="strict",
            path="/",
        )
        return context

    def logout(self, response: Response) -> None:
        response.delete_cookie(ADMIN_COOKIE, path="/")

    def require(self, request: Request, *, csrf: bool = False) -> AdminContext:
        token = request.cookies.get(ADMIN_COOKIE)
        if not token:
            raise ApiError(401, "ADMIN_AUTH_REQUIRED", "请先验证系统管理员密码")
        context = self._decode(token)
        if context.expires_at <= int(time.time()):
            raise ApiError(401, "ADMIN_SESSION_EXPIRED", "管理员会话已过期，请重新验证")
        if csrf and not hmac.compare_digest(
            request.headers.get("x-csrf-token", ""), context.csrf_token
        ):
            raise ApiError(403, "ADMIN_CSRF_INVALID", "管理员写操作校验失败，请刷新后重试")
        return context

    def _encode(self, context: AdminContext) -> str:
        body = json.dumps(
            {
                "actor": context.actor,
                "csrf": context.csrf_token,
                "exp": context.expires_at,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        encoded = _b64encode(body)
        signature = _b64encode(
            hmac.new(self._key, encoded.encode("ascii"), hashlib.sha256).digest()
        )
        return f"{encoded}.{signature}"

    def _decode(self, token: str) -> AdminContext:
        try:
            encoded, supplied = token.split(".", 1)
            expected = _b64encode(
                hmac.new(self._key, encoded.encode("ascii"), hashlib.sha256).digest()
            )
            if not hmac.compare_digest(supplied, expected):
                raise ValueError("bad signature")
            payload = json.loads(_b64decode(encoded))
            return AdminContext(
                actor=str(payload["actor"]),
                csrf_token=str(payload["csrf"]),
                expires_at=int(payload["exp"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ApiError(401, "ADMIN_SESSION_INVALID", "管理员会话无效，请重新验证") from exc
