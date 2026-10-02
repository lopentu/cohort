"""The browser session boundary protects research without changing graph identity."""
from __future__ import annotations

import json
import os
import runpy
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi", reason="the `ui` extra is not installed")
from fastapi.testclient import TestClient  # noqa: E402 — optional UI extra checked above

from cohort.graph import Graph  # noqa: E402 — optional UI extra checked above
from cohort.ui.api import create_app  # noqa: E402 — optional UI extra checked above


def test_auth_session_is_public_in_explicit_programmatic_development_mode(tmp_path):
    db = tmp_path / "g.sqlite"
    Graph(db).close()
    client = TestClient(create_app(db))
    assert client.get("/api/auth/session").json() == {
        "enabled": False, "authenticated": True, "username": None, "csrf_token": None,
    }


@pytest.fixture
def protected(tmp_path):
    from cohort.ui.auth import AuthManager, credential_record

    path = tmp_path / "auth.json"
    path.write_text(json.dumps(credential_record("researcher", "synthetic-test-password")))
    path.chmod(0o600)
    manager = AuthManager.from_file(path, allow_local_http=True)
    db = tmp_path / "g.sqlite"
    Graph(db).close()
    return TestClient(create_app(db, auth=manager, allow_writes=True), base_url="http://localhost"), manager


def login(client, **kwargs):
    return client.post("/api/auth/login", json={
        "username": "researcher", "password": "synthetic-test-password",
    }, **kwargs)


def test_research_and_documentation_require_login(protected):
    client, _ = protected
    for path in ("/api/graph", "/api/health", "/docs", "/redoc", "/openapi.json"):
        response = client.get(path)
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "authentication_required"
    assert client.get("/api/auth/session").json()["authenticated"] is False
    assert client.get("/").status_code != 401


def test_login_cookie_csrf_and_logout(protected):
    client, _ = protected
    response = login(client)
    assert response.status_code == 200
    session = response.json()
    assert session["username"] == "researcher" and session["csrf_token"]
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "Secure" not in cookie
    assert client.get("/api/graph").status_code == 200
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/accept", json={}).json()["detail"]["code"] == "csrf_failed"
    assert client.post("/api/auth/logout", headers={
        "X-CSRF-Token": session["csrf_token"],
    }).status_code == 200
    assert client.get("/api/graph").status_code == 401


@pytest.mark.parametrize("headers", [
    {"Origin": "https://evil.example"}, {"Origin": "null"},
    {"Sec-Fetch-Site": "cross-site"}, {"Origin": "http://localhost:81"},
])
def test_login_rejects_cross_origin(protected, headers):
    client, _ = protected
    assert login(client, headers=headers).status_code == 403


def test_json_only_login_and_uniform_bad_credentials(protected):
    client, _ = protected
    assert client.post("/api/auth/login", content="username=researcher").status_code == 415
    bodies = [client.post("/api/auth/login", json={"username": name, "password": "bad"}).json()
              for name in ("researcher", "unknown")]
    assert bodies[0] == bodies[1]
    assert "synthetic" not in str(bodies)


def test_login_retry_limit_is_bounded(protected):
    client, manager = protected
    for _ in range(manager.max_attempts):
        assert client.post("/api/auth/login", json={
            "username": "unknown", "password": "bad",
        }).status_code == 401
    assert login(client).status_code == 429


def test_session_idle_and_absolute_expiry(protected):
    client, manager = protected
    now = [100.0]
    manager.clock = lambda: now[0]
    login(client)
    now[0] += manager.idle_seconds + 1
    assert client.get("/api/graph").status_code == 401
    login(client)
    for _ in range(int(manager.absolute_seconds // (manager.idle_seconds / 2)) + 1):
        now[0] += manager.idle_seconds / 2
        response = client.get("/api/auth/session")
    assert response.json()["authenticated"] is False


def test_relogin_revokes_previous_cookie_and_https_is_secure(protected):
    client, manager = protected
    login(client)
    old = client.cookies.get("cohort_session")
    login(client)
    assert client.cookies.get("cohort_session") != old
    client.cookies.set("cohort_session", old, domain="localhost.local", path="/")
    assert client.get("/api/graph").status_code == 401
    secure = TestClient(create_app("unused.sqlite", auth=manager), base_url="https://testserver")
    assert "Secure" in login(secure).headers["set-cookie"]


def test_credentials_require_owner_only_file(protected, tmp_path):
    from cohort.ui.auth import AuthManager, credential_record

    path = tmp_path / "unsafe.json"
    path.write_text(json.dumps(credential_record("researcher", "synthetic-password")))
    os.chmod(path, 0o644)
    with pytest.raises(ValueError, match="owner"):
        AuthManager.from_file(path)


def test_interactive_setup_writes_owner_only_and_refuses_overwrite(tmp_path, monkeypatch):
    main = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/setup_ui_auth.py"))["main"]

    path = tmp_path / "account.json"
    monkeypatch.setattr("builtins.input", lambda prompt: "researcher")
    monkeypatch.setattr("getpass.getpass", lambda prompt: "synthetic-setup-password")
    main(["--credentials", str(path)])
    assert path.stat().st_mode & 0o777 == 0o600
    original = path.read_bytes()
    with pytest.raises(SystemExit):
        main(["--credentials", str(path)])
    assert path.read_bytes() == original
    main(["--credentials", str(path), "--overwrite"])
    assert path.read_bytes() != original
    assert b"synthetic-setup-password" not in path.read_bytes()


def test_http_login_requires_explicit_local_transport_setting(protected):
    client, manager = protected
    remote = TestClient(create_app("unused.sqlite", auth=manager), base_url="http://evil.example")
    assert login(remote).status_code == 403
    manager.allow_local_http = False
    assert login(client).status_code == 403


def test_session_capacity_evicts_oldest_and_retry_window_recovers(protected):
    client, manager = protected
    manager.max_sessions = 2
    tokens = []
    for _ in range(3):
        client.cookies.clear()
        assert login(client).status_code == 200
        tokens.append(client.cookies.get("cohort_session"))
    assert manager.session(tokens[0]) is None
    assert manager.session(tokens[1]) is not None
    assert manager.session(tokens[2]) is not None
    now = [manager.clock()]
    manager.clock = lambda: now[0]
    for _ in range(manager.max_attempts - 3):
        login(client)
    assert login(client).status_code == 429
    now[0] += manager.retry_seconds + 1
    assert login(client).status_code == 200


def test_csrf_rejects_foreign_origin_even_with_valid_token(protected):
    client, _ = protected
    token = login(client).json()["csrf_token"]
    response = client.post("/api/auth/logout", headers={
        "Origin": "https://evil.example", "X-CSRF-Token": token,
    })
    assert response.status_code == 403
    assert client.get("/api/graph").status_code == 200


def test_forwarded_headers_do_not_make_http_secure(protected):
    client, manager = protected
    manager.allow_local_http = False
    assert login(client, headers={"X-Forwarded-Proto": "https"}).status_code == 403


@pytest.mark.parametrize("body", [None, [], {}, {"username": "\ud800", "password": "x"}])
def test_malformed_login_is_safe(protected, body):
    client, _ = protected
    response = client.post("/api/auth/login", content=json.dumps(body),
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_login"


@pytest.mark.parametrize("args", [["--host", "0.0.0.0", "--no-auth"], []])
def test_serve_rejects_public_binding_or_missing_credentials(tmp_path, monkeypatch, args):
    main = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/serve_ui.py"))["main"]
    monkeypatch.setattr("sys.argv", ["serve_ui.py", "--auth-file", str(tmp_path / "missing.json"), *args])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


def test_shell_and_session_cannot_be_framed_or_cached(protected):
    client, _ = protected
    for path in ("/", "/api/auth/session", "/api/graph"):
        response = client.get(path)
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("contents", ["null", "[]", '"text"', "{", '{"username":"secret-value"}'])
def test_malformed_credentials_are_rejected_without_contents(tmp_path, contents):
    from cohort.ui.auth import AuthManager

    path = tmp_path / "malformed.json"
    path.write_text(contents)
    path.chmod(0o600)
    with pytest.raises(ValueError, match=r"^invalid credentials file$"):
        AuthManager.from_file(path)
