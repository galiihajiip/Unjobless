from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from unjobless.api.deps import DB
from unjobless.core.audit import audit
from unjobless.core.config import get_settings
from unjobless.core.errors import AppError
from unjobless.db.models import (
    ApplicationRecord,
    ApplicationStatusHistory,
    AppSettings,
    AuditEvent,
    CandidateProfileVersion,
    CareerPreferences,
    JobComparison,
    JobVacancy,
    JobVacancySource,
    Source,
)

router = APIRouter(prefix="/settings", tags=["settings"])


class AppPrefs(BaseModel):
    theme: Literal["light", "dark", "system"] = "light"
    language: Literal["id", "en"] = "en"
    raw_retention_days: int | None = Field(
        default=None, ge=30, le=3650, description="Delete uncited raw documents after N days (null = keep)."
    )
    notify_in_app: bool = True
    notify_deadline_days: int = Field(default=3, ge=1, le=30)
    backup_keep: int = Field(default=7, ge=1, le=90)


def load_prefs(db: DB) -> AppPrefs:
    row = db.get(AppSettings, "app")
    return AppPrefs.model_validate(row.value if row else {})


@router.get("")
def get_settings_(db: DB) -> dict[str, Any]:
    s = get_settings()
    return {
        "app": load_prefs(db).model_dump(),
        "limits": {
            "max_urls_per_batch": s.max_urls_per_batch,
            "fetch_max_bytes": s.fetch_max_bytes,
            "max_upload_bytes": s.max_upload_bytes,
            "max_paste_chars": s.max_paste_chars,
            "global_worker_concurrency": s.global_worker_concurrency,
            "fetch_total_timeout": s.fetch_total_timeout,
            "min_source_interval_seconds": 300,
        },
        "environment": {
            "env": s.env,
            "master_key_configured": s.master_key is not None,
            "user_agent": s.user_agent,
        },
    }


@router.put("")
def put_settings(body: AppPrefs, db: DB) -> dict[str, Any]:
    row = db.get(AppSettings, "app")
    if row is None:
        db.add(AppSettings(key="app", value=body.model_dump()))
    else:
        row.value = body.model_dump()
    audit(db, "settings.updated", details={"fields": list(body.model_dump())})
    return body.model_dump()


@router.get("/audit")
def audit_log(db: DB) -> list[dict[str, Any]]:
    rows = db.execute(select(AuditEvent).order_by(AuditEvent.at.desc()).limit(200)).scalars()
    return [
        {
            "action": r.action,
            "actor": r.actor.value,
            "target": f"{r.target_type or ''}:{r.target_id or ''}".strip(":"),
            "details": r.details,
            "at": r.at.isoformat(),
        }
        for r in rows
    ]


# ---------------------------------------------------------------- backup


class BackupUnavailable(AppError):
    status_code = 503
    code = "backup_unavailable"


@router.get("/backups")
def backups() -> list[dict[str, Any]]:
    from unjobless.ops.backup import list_backups

    return list_backups()


@router.post("/backups", status_code=201)
def make_backup(db: DB) -> dict[str, Any]:
    from unjobless.ops.backup import create_backup

    try:
        res = create_backup(keep=load_prefs(db).backup_keep)
    except Exception as exc:
        raise BackupUnavailable(str(exc)) from exc
    audit(db, "backup.created", details={"path": res["path"]})
    return {
        "name": res["path"].rsplit("/", 1)[-1],
        "created_at": res["created_at"],
        "row_counts": res["row_counts"],
    }


# ---------------------------------------------------------------- personal data export (no secrets)


def _export(db: DB) -> dict[str, Any]:
    prefs = db.execute(select(CareerPreferences)).scalar_one_or_none()
    return {
        "exported_at": datetime.now().isoformat(),
        "profile_versions": [
            {
                "version_no": v.version_no,
                "status": v.status.value,
                "confirmed_at": v.confirmed_at.isoformat() if v.confirmed_at else None,
                "data": v.data,
            }
            for v in db.execute(
                select(CandidateProfileVersion).order_by(CandidateProfileVersion.version_no)
            ).scalars()
        ],
        "preferences": prefs.data if prefs else None,
        "vacancies": [
            {
                "id": v.id,
                "title": v.title,
                "company": v.company_name,
                "status": v.verification_status.value,
                "location": v.location_text,
                "employment_type": v.employment_type.value,
                "work_arrangement": v.work_arrangement.value,
                "application_url": v.application_url,
                "deadline": v.application_deadline.isoformat() if v.application_deadline else None,
                "first_seen_at": v.first_seen_at.isoformat(),
                "sources": [
                    s.source_url
                    for s in db.execute(
                        select(JobVacancySource).where(JobVacancySource.vacancy_id == v.id)
                    ).scalars()
                ],
            }
            for v in db.execute(select(JobVacancy).where(JobVacancy.merged_into_id.is_(None))).scalars()
        ],
        "applications": [
            {
                "vacancy_id": a.vacancy_id,
                "status": a.status.value,
                "applied_at": a.applied_at.isoformat() if a.applied_at else None,
                "notes": a.notes,
                "history": [
                    {"to": h.to_status.value, "at": h.at.isoformat(), "note": h.note}
                    for h in db.execute(
                        select(ApplicationStatusHistory).where(
                            ApplicationStatusHistory.application_id == a.id
                        )
                    ).scalars()
                ],
            }
            for a in db.execute(select(ApplicationRecord)).scalars()
        ],
        "comparisons": [
            {"id": c.id, "created_at": c.created_at.isoformat(), "result": c.result}
            for c in db.execute(select(JobComparison)).scalars()
        ],
        "sources": [
            {
                "key": s.key,
                "name": s.name,
                "domain": s.domain,
                "connector_type": s.connector_type,
                "policy_status": s.policy_status.value,
                "state": s.state.value,
                "config": s.config,
                "has_secret": s.secret_id is not None,
            }
            for s in db.execute(select(Source)).scalars()
        ],
        "note": "No API keys, session data or passwords are included.",
    }


@router.get("/export")
def export_json(
    db: DB, kind: Literal["all", "profile", "vacancies", "applications", "sources"] = "all"
) -> Response:
    data = _export(db)
    if kind != "all":
        keys = {
            "profile": ["profile_versions", "preferences"],
            "vacancies": ["vacancies"],
            "applications": ["applications", "comparisons"],
            "sources": ["sources"],
        }[kind]
        data = {k: data[k] for k in [*keys, "exported_at", "note"]}
    audit(db, "data.exported", details={"kind": kind})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"unjobless-{kind}.json", json.dumps(data, ensure_ascii=False, indent=1, default=str))
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="unjobless-export-{kind}-{datetime.now():%Y%m%d}.zip"',
            "Cache-Control": "no-store",
        },
    )
