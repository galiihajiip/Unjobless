"""Password hashing, opaque tokens and constant-time comparisons."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from unjobless.core.config import get_settings

_ph = PasswordHasher()  # argon2id, library defaults (RFC 9106 low-memory profile)

MIN_PASSWORD_LENGTH = 12


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _ph.check_needs_rehash(password_hash)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def _secret() -> bytes:
    s = get_settings().session_secret
    if s is None:
        # Development fallback: per-process random secret (sessions reset on restart).
        global _DEV_SECRET
        return _DEV_SECRET
    return s.get_secret_value().encode()


_DEV_SECRET = secrets.token_bytes(32)


def token_hash(token: str) -> str:
    """Keyed hash so a database leak does not reveal usable session tokens."""
    return hmac.new(_secret(), token.encode(), hashlib.sha256).hexdigest()


def safe_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
