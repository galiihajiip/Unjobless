"""Portable backup / restore.

A backup is a directory `<backups>/unjobless-<UTC timestamp>/` containing:
- `database.dump`  — `pg_dump --format=custom` of the whole database (data + queue tables);
- `files.tar.gz`   — the private file volume (CVs, raw blobs, media, exports);
- `manifest.json`  — app version, Alembic revision, sizes, SHA-256 checksums, notes.

Secrets are NOT included in plaintext: AI keys are stored encrypted in the database and can only be
decrypted with UNJOBLESS_MASTER_KEY, which must be backed up separately (password manager / sealed
offline copy). Restoring without the same master key works, but stored AI keys must be re-entered.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import text

from unjobless.core.config import get_settings
from unjobless.core.logging import get_logger

log = get_logger(__name__)
FORMAT_VERSION = 1


def _pg_env() -> tuple[list[str], dict[str, str]]:
    u = urlsplit(get_settings().database_url.replace("postgresql+psycopg://", "postgresql://"))
    env = {**os.environ, "PGPASSWORD": u.password or ""}
    args = [
        "-h",
        u.hostname or "localhost",
        "-p",
        str(u.port or 5432),
        "-U",
        u.username or "postgres",
        "-d",
        (u.path or "/").lstrip("/"),
    ]
    return args, env


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def backups_dir() -> Path:
    return Path(os.environ.get("UNJOBLESS_BACKUP_DIR", "./var/backups")).resolve()


def create_backup(*, keep: int = 7) -> dict[str, Any]:
    if not shutil.which("pg_dump"):
        raise RuntimeError(
            "pg_dump is not installed in this environment (it is included in the Docker image)."
        )
    from unjobless.db.session import get_engine

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = backups_dir() / f"unjobless-{stamp}"
    out.mkdir(parents=True, exist_ok=False)
    os.chmod(out, 0o700)
    args, env = _pg_env()
    dump = out / "database.dump"
    subprocess.run(
        ["pg_dump", "--format=custom", "--no-owner", "--no-privileges", "-f", str(dump), *args],
        env=env,
        check=True,
        capture_output=True,
        timeout=3600,
    )
    files_root = Path(get_settings().files_dir).resolve()
    tar_path = out / "files.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        if files_root.exists():
            for p in sorted(files_root.rglob("*")):
                if p.is_file() and not p.name.endswith(".tmp") and p.name != "bootstrap-token.txt":
                    tar.add(p, arcname=str(p.relative_to(files_root)))
    with get_engine().connect() as c:
        rev = c.execute(text("select version_num from alembic_version")).scalar()
        counts = {
            t: c.execute(text(f"select count(*) from {t}")).scalar()
            for t in (
                "job_vacancies",
                "raw_source_documents",
                "candidate_profile_versions",
                "application_records",
                "resume_documents",
            )
        }
    manifest = {
        "format_version": FORMAT_VERSION,
        "app": "unjobless",
        "created_at": stamp,
        "alembic_revision": rev,
        "row_counts": counts,
        "files": {p.name: {"bytes": p.stat().st_size, "sha256": _sha256(p)} for p in (dump, tar_path)},
        "secrets": "AI provider keys are encrypted in the dump; restore UNJOBLESS_MASTER_KEY separately to keep them usable.",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    for p in out.iterdir():
        os.chmod(p, 0o600)
    prune(keep)
    log.info("backup_created", path=str(out))
    return {"path": str(out), **manifest}


def prune(keep: int) -> list[str]:
    dirs = sorted(d for d in backups_dir().glob("unjobless-*") if d.is_dir())
    removed = []
    for d in dirs[:-keep] if keep > 0 else []:
        shutil.rmtree(d)
        removed.append(d.name)
    return removed


def list_backups() -> list[dict[str, Any]]:
    out = []
    for d in sorted(backups_dir().glob("unjobless-*"), reverse=True):
        m = d / "manifest.json"
        if m.exists():
            man = json.loads(m.read_text())
            out.append(
                {
                    "name": d.name,
                    "created_at": man.get("created_at"),
                    "alembic_revision": man.get("alembic_revision"),
                    "bytes": sum(f["bytes"] for f in man.get("files", {}).values()),
                    "row_counts": man.get("row_counts"),
                }
            )
    return out


def verify(path: Path) -> dict[str, Any]:
    man = json.loads((path / "manifest.json").read_text())
    problems = []
    for name, meta in man["files"].items():
        p = path / name
        if not p.exists():
            problems.append(f"missing {name}")
        elif _sha256(p) != meta["sha256"]:
            problems.append(f"checksum mismatch for {name}")
    return {"ok": not problems, "problems": problems, "manifest": man}


def restore(path: Path, *, confirm: bool = False) -> dict[str, Any]:
    """Restore into the configured database + files dir (intended for a clean deployment)."""
    if not confirm:
        raise RuntimeError("Restore overwrites the current database and files. Re-run with --yes to confirm.")
    check = verify(path)
    if not check["ok"]:
        raise RuntimeError("Backup verification failed: " + "; ".join(check["problems"]))
    if not shutil.which("pg_restore"):
        raise RuntimeError("pg_restore is not installed in this environment.")
    args, env = _pg_env()
    subprocess.run(
        [
            "pg_restore",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            "--single-transaction",
            *args,
            str(path / "database.dump"),
        ],
        env=env,
        check=True,
        capture_output=True,
        timeout=3600,
    )
    files_root = Path(get_settings().files_dir).resolve()
    files_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path / "files.tar.gz", "r:gz") as tar:
        tar.extractall(files_root, filter="data")  # rejects absolute paths, links outside, device files
    from unjobless.db.migrate import upgrade_head

    upgrade_head()  # brings an older backup's schema up to the current version
    return {"restored_from": path.name, "integrity": integrity_check()}


def integrity_check() -> dict[str, Any]:
    """Post-restore checks: every stored blob reference exists on disk; key tables readable."""
    from unjobless.db.session import get_engine
    from unjobless.ingestion.filestore import get_filestore

    fs = get_filestore()
    missing = []
    with get_engine().connect() as c:
        for table, col in (
            ("resume_documents", "blob_ref"),
            ("raw_source_versions", "blob_ref"),
            ("source_media_assets", "blob_ref"),
            ("export_files", "blob_ref"),
        ):
            for (ref,) in c.execute(text(f"select {col} from {table} where {col} is not null")):
                if not fs.exists(ref):
                    missing.append(f"{table}:{ref}")
        counts = {
            t: c.execute(text(f"select count(*) from {t}")).scalar()
            for t in ("job_vacancies", "raw_source_documents", "candidate_profile_versions")
        }
        enc = c.execute(
            text("select count(*) from ai_provider_configs where encrypted_api_key is not null")
        ).scalar()
    keys_ok = None
    if enc:
        from unjobless.core.crypto import decrypt_secret

        with get_engine().connect() as c:
            blob = c.execute(
                text(
                    "select encrypted_api_key from ai_provider_configs where encrypted_api_key is not null limit 1"
                )
            ).scalar()
        try:
            decrypt_secret(bytes(blob or b""))
            keys_ok = True
        except Exception:
            keys_ok = False
    return {
        "missing_files": missing[:50],
        "missing_count": len(missing),
        "row_counts": counts,
        "encrypted_keys": enc,
        "master_key_matches": keys_ok,
    }
