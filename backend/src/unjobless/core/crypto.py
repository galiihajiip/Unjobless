"""Encryption of stored secrets (AI provider keys, connector credentials).

AES-256-GCM with a key derived (HKDF-SHA256) from UNJOBLESS_MASTER_KEY. Ciphertext layout:
``b"v1" || nonce(12) || ciphertext+tag``. The master key never touches the database.
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from unjobless.core.config import get_settings
from unjobless.core.errors import AppError

_VERSION = b"v1"


class MasterKeyMissing(AppError):
    status_code = 503
    code = "master_key_missing"


def _key(purpose: str) -> bytes:
    mk = get_settings().master_key
    if mk is None:
        raise MasterKeyMissing("UNJOBLESS_MASTER_KEY is not configured; secrets cannot be stored or read.")
    raw = base64.urlsafe_b64decode(mk.get_secret_value() + "==")
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"unjobless-secrets", info=purpose.encode()).derive(raw)


def encrypt_secret(plaintext: str, purpose: str = "ai-provider-key") -> bytes:
    nonce = os.urandom(12)
    ct = AESGCM(_key(purpose)).encrypt(nonce, plaintext.encode(), _VERSION + purpose.encode())
    return _VERSION + nonce + ct


def decrypt_secret(blob: bytes, purpose: str = "ai-provider-key") -> str:
    if not blob.startswith(_VERSION):
        raise ValueError("unknown ciphertext version")
    nonce, ct = blob[2:14], blob[14:]
    return AESGCM(_key(purpose)).decrypt(nonce, ct, _VERSION + purpose.encode()).decode()


def fingerprint(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def mask_hint(secret: str) -> str:
    """Last four characters only, e.g. '…a1b2'. Never more."""
    return "…" + secret[-4:] if len(secret) >= 8 else "…"
