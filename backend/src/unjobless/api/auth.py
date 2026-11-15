"""Private single-owner authentication.

- No public sign-up. `/auth/bootstrap` works exactly once (DB singleton constraint + check).
- In production the bootstrap requires a setup token (env UNJOBLESS_BOOTSTRAP_TOKEN, or a random
  token written to <files_dir>/bootstrap-token.txt on first start).
- Server-side sessions; cookie holds an opaque token, DB stores a keyed hash.
- CSRF: double-submit token bound to the session (hash stored server-side).
- Login throttling per IP and globally.
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from unjobless.api.deps import CSRF_COOKIE, DB, SESSION_COOKIE, Owner, client_ip, current_session
from unjobless.core.audit import audit
from unjobless.core.config import get_settings
from unjobless.core.errors import Conflict, Forbidden, TooManyRequests, Unauthorized, ValidationFailed
from unjobless.core.logging import get_logger
from unjobless.core.security import (
    MIN_PASSWORD_LENGTH,
    hash_password,
    needs_rehash,
    new_token,
    safe_equals,
    token_hash,
    verify_password,
)
from unjobless.core.time import utcnow
from unjobless.db.models import LoginAttempt, OwnerAccount, OwnerSession

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger(__name__)

MAX_FAILURES_PER_IP = 5
MAX_FAILURES_GLOBAL = 30
THROTTLE_WINDOW = timedelta(minutes=15)


class AuthStateOut(BaseModel):
    bootstrapped: bool
    authenticated: bool
    setup_token_required: bool
    display_name: str | None = None


class BootstrapIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=1024)
    setup_token: str | None = None


class LoginIn(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=1024)


class SessionOut(BaseModel):
    id: int
    created_at: str
    last_seen_at: str
    user_agent: str | None
    current: bool


def _token_file() -> Path:
    return Path(get_settings().files_dir) / "bootstrap-token.txt"


def expected_setup_token() -> str | None:
    """Return the required setup token, or None when not required (development/test)."""
    settings = get_settings()
    import os

    env_token = os.environ.get("UNJOBLESS_BOOTSTRAP_TOKEN")
    if env_token:
        return env_token
    if not settings.is_production:
        return None
    path = _token_file()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_urlsafe(24))
        path.chmod(0o600)
        log.warning(
            "bootstrap_token_created", path=str(path), hint="read it with: docker compose exec api cat <path>"
        )
    return path.read_text().strip()


def _start_session(db: DB, response: Response, request: Request, owner: OwnerAccount) -> None:
    settings = get_settings()
    token, csrf = new_token(), new_token()
    db.add(
        OwnerSession(
            owner_id=owner.id,
            token_hash=token_hash(token),
            csrf_hash=token_hash(csrf),
            expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
            user_agent=(request.headers.get("user-agent") or "")[:300] or None,
            ip=client_ip(request),
        )
    )
    max_age = settings.session_ttl_hours * 3600
    secure = settings.is_production
    response.set_cookie(
        SESSION_COOKIE, token, max_age=max_age, httponly=True, secure=secure, samesite="lax", path="/"
    )
    # Readable by the SPA so it can echo it in the X-CSRF-Token header.
    response.set_cookie(
        CSRF_COOKIE, csrf, max_age=max_age, httponly=False, secure=secure, samesite="strict", path="/"
    )


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def _check_throttle(db: DB, ip: str | None) -> None:
    since = utcnow() - THROTTLE_WINDOW
    q = (
        select(func.count())
        .select_from(LoginAttempt)
        .where(LoginAttempt.success.is_(False), LoginAttempt.at > since)
    )
    if db.execute(q).scalar_one() >= MAX_FAILURES_GLOBAL:
        raise TooManyRequests("Too many failed sign-in attempts. Try again later.")
    if ip and db.execute(q.where(LoginAttempt.ip == ip)).scalar_one() >= MAX_FAILURES_PER_IP:
        raise TooManyRequests("Too many failed sign-in attempts from this address. Try again in 15 minutes.")


@router.get("/state", response_model=AuthStateOut)
def state(request: Request, db: DB) -> AuthStateOut:
    owner = db.execute(select(OwnerAccount)).scalar_one_or_none()
    sess = current_session(request, db) if owner else None
    return AuthStateOut(
        bootstrapped=owner is not None,
        authenticated=sess is not None,
        setup_token_required=owner is None and expected_setup_token() is not None,
        display_name=owner.display_name if (owner and sess) else None,
    )


@router.post("/bootstrap", status_code=201)
def bootstrap(body: BootstrapIn, request: Request, response: Response, db: DB) -> dict[str, str]:
    if db.execute(select(OwnerAccount)).scalar_one_or_none() is not None:
        raise Conflict(
            "This instance already has an owner. Bootstrap can only run once.", code="already_bootstrapped"
        )
    _check_throttle(db, client_ip(request))
    expected = expected_setup_token()
    if expected is not None and not safe_equals(body.setup_token or "", expected):
        db.add(LoginAttempt(ip=client_ip(request), success=False))
        db.commit()
        raise Forbidden("Invalid setup token.", code="invalid_setup_token")
    owner = OwnerAccount(display_name=body.display_name.strip(), password_hash=hash_password(body.password))
    db.add(owner)
    try:
        db.flush()
    except IntegrityError as exc:  # concurrent bootstrap lost the race
        db.rollback()
        raise Conflict("This instance already has an owner.", code="already_bootstrapped") from exc
    audit(db, "owner.bootstrap", target_type="owner", target_id=owner.id)
    _start_session(db, response, request, owner)
    if _token_file().exists():
        _token_file().unlink()
    return {"status": "created"}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: DB) -> dict[str, str]:
    ip = client_ip(request)
    _check_throttle(db, ip)
    owner = db.execute(select(OwnerAccount)).scalar_one_or_none()
    if owner is None or not verify_password(owner.password_hash, body.password):
        db.add(LoginAttempt(ip=ip, success=False))
        db.commit()
        raise Unauthorized("Incorrect password.", code="invalid_credentials")
    if needs_rehash(owner.password_hash):
        owner.password_hash = hash_password(body.password)
    db.add(LoginAttempt(ip=ip, success=True))
    _start_session(db, response, request, owner)
    audit(db, "owner.login", details={"ip": ip})
    return {"status": "ok"}


@router.post("/logout")
def logout(request: Request, response: Response, db: DB) -> dict[str, str]:
    s = current_session(request, db)
    if s is not None:
        s.revoked_at = utcnow()
    _clear_cookies(response)
    return {"status": "ok"}


@router.post("/logout-all")
def logout_all(owner: Owner, response: Response, db: DB) -> dict[str, str]:
    db.execute(update(OwnerSession).where(OwnerSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
    audit(db, "owner.logout_all")
    _clear_cookies(response)
    return {"status": "ok"}


@router.get("/sessions", response_model=list[SessionOut])
def sessions(owner: Owner, db: DB) -> list[SessionOut]:
    rows = db.execute(
        select(OwnerSession)
        .where(OwnerSession.revoked_at.is_(None), OwnerSession.expires_at > utcnow())
        .order_by(OwnerSession.last_seen_at.desc())
    ).scalars()
    return [
        SessionOut(
            id=s.id,
            created_at=s.created_at.isoformat(),
            last_seen_at=s.last_seen_at.isoformat(),
            user_agent=s.user_agent,
            current=s.id == owner.id,
        )
        for s in rows
    ]


@router.delete("/sessions/{session_id}")
def revoke_session(session_id: int, owner: Owner, db: DB) -> dict[str, str]:
    s = db.get(OwnerSession, session_id)
    if s is not None and s.revoked_at is None:
        s.revoked_at = utcnow()
        audit(db, "owner.session_revoked", target_type="session", target_id=session_id)
    return {"status": "ok"}


@router.post("/password")
def change_password(
    body: PasswordChangeIn, owner: Owner, request: Request, response: Response, db: DB
) -> dict[str, str]:
    acct = db.get(OwnerAccount, owner.owner_id)
    assert acct is not None
    if not verify_password(acct.password_hash, body.current_password):
        raise ValidationFailed("Current password is incorrect.", code="invalid_credentials")
    acct.password_hash = hash_password(body.new_password)
    acct.password_changed_at = utcnow()
    # Revoke every session (including this one) and start a fresh one.
    db.execute(update(OwnerSession).where(OwnerSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
    audit(db, "owner.password_changed")
    _start_session(db, response, request, acct)
    return {"status": "ok"}
