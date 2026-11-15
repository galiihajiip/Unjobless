import pytest
from fastapi.testclient import TestClient

from unjobless.api.app import create_app
from unjobless.api.router import build_private_router

pytestmark = pytest.mark.db

PW = "correct horse battery staple"


@pytest.fixture
def client(engine, clean_db):
    return TestClient(create_app(), client=("203.0.113.5", 50000))


def bootstrap(client, **kw):
    return client.post("/api/auth/bootstrap", json={"display_name": "Owner", "password": PW, **kw})


def csrf(client):
    return {"X-CSRF-Token": client.cookies.get("uj_csrf")}


def test_state_before_bootstrap(client):
    r = client.get("/api/auth/state")
    assert r.json() == {"bootstrapped": False, "authenticated": False, "setup_token_required": False, "display_name": None}


def test_bootstrap_once_then_rejected(client):
    assert bootstrap(client).status_code == 201
    assert client.get("/api/auth/state").json()["authenticated"] is True
    fresh = TestClient(client.app, client=("203.0.113.6", 50000))
    r = bootstrap(fresh)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "already_bootstrapped"


def test_bootstrap_requires_setup_token_when_configured(client, monkeypatch):
    monkeypatch.setenv("UNJOBLESS_BOOTSTRAP_TOKEN", "letmein-token")
    assert client.get("/api/auth/state").json()["setup_token_required"] is True
    assert bootstrap(client, setup_token="wrong").status_code == 403
    assert bootstrap(client, setup_token="letmein-token").status_code == 201


def test_weak_password_rejected(client):
    r = client.post("/api/auth/bootstrap", json={"display_name": "O", "password": "short"})
    assert r.status_code == 422


def test_session_cookie_flags(client):
    r = bootstrap(client)
    cookies = r.headers.get_list("set-cookie")
    session = next(c for c in cookies if c.startswith("uj_session="))
    assert "HttpOnly" in session and "SameSite=lax" in session
    csrf_c = next(c for c in cookies if c.startswith("uj_csrf="))
    assert "HttpOnly" not in csrf_c


def test_login_logout_flow(client):
    bootstrap(client)
    client.post("/api/auth/logout")
    assert client.get("/api/auth/state").json()["authenticated"] is False
    assert client.post("/api/auth/login", json={"password": "wrong password"}).status_code == 401
    assert client.post("/api/auth/login", json={"password": PW}).status_code == 200
    assert client.get("/api/auth/state").json()["authenticated"] is True


def test_login_throttled_after_failures(client):
    bootstrap(client)
    client.post("/api/auth/logout")
    for _ in range(5):
        assert client.post("/api/auth/login", json={"password": "nope nope"}).status_code == 401
    r = client.post("/api/auth/login", json={"password": PW})
    assert r.status_code == 429


def test_private_routes_require_auth_and_csrf(client):
    bootstrap(client)
    # authenticated GET works
    assert client.get("/api/auth/sessions").status_code == 200
    # unsafe method without CSRF header is rejected
    assert client.post("/api/auth/logout-all").status_code == 403
    assert client.post("/api/auth/logout-all", headers=csrf(client)).status_code == 200
    # after logout-all, private routes are unauthorized
    assert client.get("/api/auth/sessions").status_code == 401


PUBLIC_PATHS = {"/api/health/live", "/api/health/ready", "/api/auth/state", "/api/auth/bootstrap", "/api/auth/login", "/api/auth/logout"}


def test_every_private_route_rejects_anonymous(client):
    """Every route outside the explicit public allowlist must return 401 without a session."""
    anon = TestClient(client.app, client=("203.0.113.9", 50000))
    paths = client.app.openapi()["paths"]
    checked = 0
    for path, methods in paths.items():
        if path in PUBLIC_PATHS:
            continue
        concrete = path
        import re

        concrete = re.sub(r"\{[^}]+\}", "1", concrete)
        for method in methods:
            r = anon.request(method.upper(), concrete, json={})
            assert r.status_code == 401, f"{method.upper()} {path} returned {r.status_code}"
            checked += 1
    assert checked > 10


def test_password_change_revokes_sessions(client):
    bootstrap(client)
    other = TestClient(client.app, client=("203.0.113.6", 50000))
    other.post("/api/auth/login", json={"password": PW})
    r = client.post("/api/auth/password", json={"current_password": PW, "new_password": "another long passphrase"}, headers=csrf(client))
    assert r.status_code == 200
    assert other.get("/api/auth/sessions").status_code == 401
    assert client.get("/api/auth/sessions").status_code == 200


def test_security_headers(client):
    r = client.get("/api/health/live")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in r.headers["content-security-policy"]
