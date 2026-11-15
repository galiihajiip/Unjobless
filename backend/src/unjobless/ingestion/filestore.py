"""Private content-addressed file store on the `files` volume. Files are never served without auth."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from unjobless.core.config import get_settings


class FileStore:
    def __init__(self, root: str | None = None):
        self.root = Path(root or get_settings().files_dir).resolve()

    def _path(self, ref: str) -> Path:
        if not ref or "/" not in ref or ".." in ref or ref.startswith("/"):
            raise ValueError("invalid blob ref")
        p = (self.root / ref).resolve()
        if self.root not in p.parents:
            raise ValueError("blob ref escapes store")
        return p

    def put(self, data: bytes, *, namespace: str, suffix: str = "") -> tuple[str, str]:
        """Store bytes; returns (blob_ref, sha256). Idempotent for identical content."""
        digest = hashlib.sha256(data).hexdigest()
        safe_suffix = "".join(c for c in suffix if c.isalnum() or c == ".")[:10]
        ref = f"{namespace}/{digest[:2]}/{digest}{safe_suffix}"
        path = self._path(ref)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_bytes(data)
            os.chmod(tmp, 0o600)
            tmp.replace(path)
        return ref, digest

    def get(self, ref: str) -> bytes:
        return self._path(ref).read_bytes()

    def exists(self, ref: str) -> bool:
        try:
            return self._path(ref).exists()
        except ValueError:
            return False

    def delete(self, ref: str) -> None:
        p = self._path(ref)
        if p.exists():
            p.unlink()


def get_filestore() -> FileStore:
    return FileStore()
