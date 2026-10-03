"""Local researcher login, independent of evidence authorship and promotion.

Sessions stay in memory: restarting the server revokes every browser session.
Neither passwords nor bearer cookies belong in the graph or its event log.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import stat
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 5
COOKIE_NAME = "cohort_session"
MAX_LOGIN_BYTES = 4096


def _password_hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R,
                          p=SCRYPT_P, dklen=32, maxmem=64 * 1024 * 1024)


def credential_record(username: str, password: str) -> dict[str, Any]:
    """Return only salted verifier material for the interactive setup command."""
    if not username or len(username) > 128 or username != username.strip():
        raise ValueError("username must contain 1–128 characters without surrounding spaces")
    if len(password) < 12 or len(password.encode("utf-8")) > 1024:
        raise ValueError("password must contain at least 12 characters and at most 1024 bytes")
    salt = secrets.token_bytes(32)
    return {"version": 1, "username": username, "algorithm": "scrypt",
            "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P,
            "salt": salt.hex(), "hash": _password_hash(password, salt).hex()}


@dataclass
class Session:
    csrf_token: str
    created: float
    touched: float


class AuthManager:
    """One researcher account with bounded, thread-safe ephemeral state."""

    def __init__(self, username: str, salt: bytes, password_hash: bytes, *,
                 clock: Callable[[], float] = time.monotonic,
                 idle_seconds: float = 1800, absolute_seconds: float = 28800,
                 max_sessions: int = 64, max_attempts: int = 8,
                 retry_seconds: float = 60, allow_local_http: bool = False,
                 root_path: str = '', public_origin: str | None = None) -> None:
        from cohort.ui.hosting import HostingConfig, validate_public_origin

        HostingConfig(root_path=root_path)
        if public_origin is not None:
            validate_public_origin(public_origin)
        self.username = username
        self.allow_local_http = allow_local_http
        self.root_path = root_path
        self.public_origin = public_origin
        self._salt = salt
        self._hash = password_hash
        self.clock = clock
        self.idle_seconds = idle_seconds
        self.absolute_seconds = absolute_seconds
        self.max_sessions = max_sessions
        self.max_attempts = max_attempts
        self.retry_seconds = retry_seconds
        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._attempts: dict[str, tuple[float, int]] = {}
        self._global_attempts = (clock(), 0)
        self._lock = threading.Lock()

    @classmethod
    def from_file(cls, path: str | Path, *, allow_local_http: bool = False,
                  root_path: str = '', public_origin: str | None = None) -> AuthManager:
        """Reject symlinks, broad permissions and unbounded KDF parameters."""
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            info = os.fstat(handle.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o077):
                raise ValueError("credentials must be a regular owner-only file owned by this user")
            if info.st_size > MAX_LOGIN_BYTES:
                raise ValueError("invalid credentials file")
            try:
                record = json.load(handle)
                if (record["version"] != 1 or record["algorithm"] != "scrypt"
                        or (record["n"], record["r"], record["p"])
                        != (SCRYPT_N, SCRYPT_R, SCRYPT_P)):
                    raise ValueError("unsupported credentials format")
                username = record["username"]
                salt = bytes.fromhex(record["salt"])
                verifier = bytes.fromhex(record["hash"])
                if (not isinstance(username, str) or not username or len(username) > 128
                        or len(salt) != 32 or len(verifier) != 32):
                    raise ValueError("invalid credentials file")
            except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
                raise ValueError("invalid credentials file") from exc
        return cls(username, salt, verifier, allow_local_http=allow_local_http,
                   root_path=root_path, public_origin=public_origin)

    @property
    def cookie_name(self) -> str:
        return '__Secure-' + COOKIE_NAME if self.public_origin else COOKIE_NAME

    @property
    def cookie_path(self) -> str:
        return self.root_path + '/'

    def _prune(self, now: float) -> None:
        expired = [key for key, session in self._sessions.items()
                   if now - session.touched >= self.idle_seconds
                   or now - session.created >= self.absolute_seconds]
        for key in expired:
            del self._sessions[key]
        self._attempts = {key: value for key, value in self._attempts.items()
                          if now - value[0] < self.retry_seconds}

    def session(self, token: str | None) -> Session | None:
        with self._lock:
            now = self.clock()
            self._prune(now)
            session = self._sessions.get(token or "")
            if session:
                session.touched = now
                self._sessions.move_to_end(token or "")
            return session

    def revoke(self, token: str | None) -> None:
        with self._lock:
            self._sessions.pop(token or "", None)

    def login(self, username: str, password: str, client: str,
              old_token: str | None) -> tuple[str | None, Session | None, bool]:
        # Reserve an attempt before the expensive KDF. The global bound prevents
        # rotating client addresses from multiplying CPU work; no forwarded IPs.
        with self._lock:
            now = self.clock()
            self._prune(now)
            start, count = self._attempts.get(client, (now, 0))
            global_start, global_count = self._global_attempts
            if now - global_start >= self.retry_seconds:
                global_start, global_count = now, 0
            if (count >= self.max_attempts or global_count >= 32
                    or (client not in self._attempts and len(self._attempts) >= 128)):
                return None, None, True
            self._attempts[client] = start, count + 1
            self._global_attempts = global_start, global_count + 1
        candidate = _password_hash(password, self._salt)
        password_ok = hmac.compare_digest(candidate, self._hash)
        username_ok = hmac.compare_digest(username.encode("utf-8"), self.username.encode("utf-8"))
        if not (password_ok and username_ok):
            return None, None, False
        with self._lock:
            now = self.clock()
            self._prune(now)
            self._sessions.pop(old_token or "", None)
            while len(self._sessions) >= self.max_sessions:
                self._sessions.popitem(last=False)
            token = secrets.token_urlsafe(32)
            session = Session(secrets.token_urlsafe(32), now, now)
            self._sessions[token] = session
            return token, session, False


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"detail": {"code": code, "message": message}}, status_code=status,
                        headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY",
                                 "X-Content-Type-Options": "nosniff", "Referrer-Policy": "same-origin"})


def _same_origin(request: Request, public_origin: str | None = None) -> bool:
    if request.headers.get("sec-fetch-site") not in (None, "same-origin", "none"):
        return False
    origin = request.headers.get("origin")
    try:
        if public_origin is not None:
            configured, actual = urlsplit(public_origin), urlsplit(str(request.url))
            if (actual.scheme, actual.hostname, actual.port or 443) != (
                configured.scheme, configured.hostname, configured.port or 443
            ):
                return False
        if origin is None:
            return True  # Non-browser JSON clients have no ambient Origin.
        incoming, expected = urlsplit(origin), urlsplit(str(request.url))
        if incoming.username or incoming.password or incoming.path or incoming.query or incoming.fragment:
            return False
        return (incoming.scheme, incoming.hostname, incoming.port or (443 if incoming.scheme == "https" else 80)) == (
            expected.scheme, expected.hostname, expected.port or (443 if expected.scheme == "https" else 80))
    except ValueError:
        return False


def _session_json(manager: AuthManager | None, session: Session | None) -> dict[str, Any]:
    return {"enabled": manager is not None, "authenticated": manager is None or session is not None,
            "username": manager.username if manager and session else None,
            "csrf_token": session.csrf_token if session else None}


def mount_auth(app: FastAPI, manager: AuthManager | None) -> None:
    """Only the shell, bundled assets and three auth routes are public."""
    public = {"/api/auth/session", "/api/auth/login", "/api/auth/logout"}

    @app.middleware("http")
    async def session_boundary(request: Request, call_next):
        session = manager.session(request.cookies.get(manager.cookie_name)) if manager else None
        request.state.auth_session = session
        path = request.url.path
        # Uvicorn includes root_path in scope.path; stripped-prefix test clients
        # may not. Compare the same route path that the ASGI router receives.
        prefix = request.scope.get('root_path', '')
        if prefix and path.startswith(prefix + '/'):
            path = path[len(prefix):]
        elif prefix and path == prefix:
            path = '/'
        is_public = path in public or path == "/" or path.startswith("/assets/")
        if manager and not is_public and session is None:
            return _error(401, "authentication_required", "Sign in to continue.")
        if manager and request.method not in {"GET", "HEAD", "OPTIONS"} and path != "/api/auth/login":
            supplied = request.headers.get("x-csrf-token", "")
            if (session is None or not _same_origin(request, manager.public_origin)
                    or not hmac.compare_digest(supplied.encode(), session.csrf_token.encode())):
                return _error(403, "csrf_failed", "Session verification failed.")
        response = await call_next(request)
        if path.startswith("/api/") or path in {"/", "/docs", "/redoc", "/openapi.json"}:
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.get("/api/auth/session")
    def auth_session(request: Request) -> dict[str, Any]:
        return _session_json(manager, request.state.auth_session)

    @app.post("/api/auth/login")
    async def auth_login(request: Request):
        if manager is None:
            return JSONResponse(_session_json(None, None))
        if request.url.scheme != "https" and not (
            manager.allow_local_http and request.url.hostname in {"localhost", "127.0.0.1", "::1"}
        ):
            return _error(403, "secure_transport_required", "Login requires HTTPS or configured localhost HTTP.")
        if not _same_origin(request, manager.public_origin):
            return _error(403, "origin_failed", "Login origin was rejected.")
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            return _error(415, "json_required", "Login requires JSON.")
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_LOGIN_BYTES:
                return _error(413, "invalid_login", "Login request is too large.")
        try:
            body = json.loads(raw)
            username, password = body["username"], body["password"]
            if (not isinstance(username, str) or not isinstance(password, str)
                    or len(username.encode("utf-8")) > 512 or len(password.encode("utf-8")) > 1024):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return _error(400, "invalid_login", "Supply a username and password.")
        token, session, limited = await run_in_threadpool(
            manager.login, username, password,
            request.client.host if request.client else "local", request.cookies.get(manager.cookie_name),
        )
        if limited:
            response = _error(429, "rate_limited", "Too many login attempts. Try again shortly.")
            response.headers["Retry-After"] = str(int(manager.retry_seconds))
            return response
        if token is None:
            return _error(401, "invalid_credentials", "Username or password is incorrect.")
        response = JSONResponse(_session_json(manager, session))
        response.set_cookie(manager.cookie_name, token, max_age=int(manager.absolute_seconds), httponly=True,
                            secure=bool(manager.public_origin) or request.url.scheme == "https",
                            samesite="strict", path=manager.cookie_path)
        return response

    @app.post("/api/auth/logout")
    def auth_logout(request: Request):
        if manager:
            manager.revoke(request.cookies.get(manager.cookie_name))
        response = JSONResponse(_session_json(manager, None))
        response.delete_cookie(manager.cookie_name if manager else COOKIE_NAME, httponly=True,
                               secure=bool(manager and manager.public_origin) or request.url.scheme == "https",
                               samesite="strict", path=manager.cookie_path if manager else '/')
        return response
