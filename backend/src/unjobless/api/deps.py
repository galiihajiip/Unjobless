"""Request dependencies: DB session, owner authentication, CSRF."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from unjobless.core.config import get_settings
from unjobless.core.errors import Forbidden, Unauthorized
from unjobless.core.security import safe_equals, token_hash
from unjobless.core.time import utcnow
from unjobless.db.models import OwnerSession
from unjobless.db.session import get_sessionmaker

SESSION_COOKIE = "uj_session"
CSRF_COOKIE = "uj_csrf"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_db() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# scope="function": commit when the endpoint returns, *before* the response is sent. Otherwise a client
# can receive e.g. its new session cookie and send the next request before the login is committed (401).
DB = Annotated[Session, Depends(get_db, scope="function")]


def current_session(request: Request, db: DB) -> OwnerSession | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    s = db.execute(
        select(OwnerSession).where(OwnerSession.token_hash == token_hash(token))
    ).scalar_one_or_none()
    if s is None or s.revoked_at is not None:
        return None
    now = utcnow()
    settings = get_settings()
    if s.expires_at <= now or s.last_seen_at + timedelta(hours=settings.session_idle_hours) <= now:
        return None
    if now - s.last_seen_at > timedelta(minutes=5):
        s.last_seen_at = now
    return s


def require_owner(request: Request, db: DB) -> OwnerSession:
    s = current_session(request, db)
    if s is None:
        raise Unauthorized("Sign in required.")
    if request.method not in SAFE_METHODS:
        header = request.headers.get(CSRF_HEADER, "")
        if not header or not safe_equals(token_hash(header), s.csrf_hash):
            raise Forbidden("Missing or invalid CSRF token.", code="csrf_failed")
    request.state.owner_session = s
    return s


Owner = Annotated[OwnerSession, Depends(require_owner)]


def client_ip(request: Request) -> str | None:
    """Client IP as seen by the app (uvicorn applies X-Forwarded-For only from trusted proxies)."""
    import ipaddress

    host = request.client.host if request.client else None
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None
