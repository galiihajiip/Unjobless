from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from unjobless.api.deps import DB
from unjobless.applications import export, tailoring, tracker
from unjobless.core.errors import NotFound
from unjobless.db.models import (
    ApplicationRecord,
    ApplicationStatusHistory,
    CoverLetter,
    ExportFile,
    JobVacancy,
    TailoredResume,
)
from unjobless.domain.enums import ApplicationStatus
from unjobless.ingestion.filestore import get_filestore

router = APIRouter(tags=["applications"])


def app_out(db: DB, r: ApplicationRecord, with_history: bool = False) -> dict[str, Any]:
    v = db.get(JobVacancy, r.vacancy_id)
    out = {
        "id": r.id,
        "vacancy_id": r.vacancy_id,
        "status": r.status.value,
        "applied_at": r.applied_at.isoformat() if r.applied_at else None,
        "follow_up_at": r.follow_up_at.isoformat() if r.follow_up_at else None,
        "deadline": r.deadline.isoformat() if r.deadline else None,
        "notes": r.notes,
        "contact_notes": r.contact_notes,
        "tailored_resume_id": r.tailored_resume_id,
        "cover_letter_id": r.cover_letter_id,
        "updated_at": r.updated_at.isoformat(),
        "vacancy": {
            "title": v.title,
            "company": v.company_name,
            "status": v.verification_status.value,
            "application_url": v.application_url,
            "location": v.location_text,
        }
        if v
        else None,
    }
    if with_history:
        out["history"] = [
            {
                "from": h.from_status.value if h.from_status else None,
                "to": h.to_status.value,
                "note": h.note,
                "at": h.at.isoformat(),
            }
            for h in db.execute(
                select(ApplicationStatusHistory)
                .where(ApplicationStatusHistory.application_id == r.id)
                .order_by(ApplicationStatusHistory.at.desc())
            ).scalars()
        ]
    return out


@router.get("/applications")
def list_apps(
    db: DB,
    status: list[ApplicationStatus] = Query(default=[]),
    q: str | None = None,
    due_within_days: int | None = None,
) -> list[dict[str, Any]]:
    query = select(ApplicationRecord).join(JobVacancy, JobVacancy.id == ApplicationRecord.vacancy_id)
    if status:
        query = query.where(ApplicationRecord.status.in_(status))
    if q:
        query = query.where(
            or_(
                JobVacancy.title.ilike(f"%{q}%"),
                JobVacancy.company_name.ilike(f"%{q}%"),
                ApplicationRecord.notes.ilike(f"%{q}%"),
            )
        )
    if due_within_days is not None:
        lim = date.today() + timedelta(days=due_within_days)
        query = query.where(or_(ApplicationRecord.deadline <= lim, ApplicationRecord.follow_up_at <= lim))
    return [app_out(db, r) for r in db.execute(query.order_by(ApplicationRecord.updated_at.desc())).scalars()]


@router.post("/applications/{vacancy_id}", status_code=201)
def track(vacancy_id: int, db: DB) -> dict[str, Any]:
    return app_out(db, tracker.get_or_create(db, vacancy_id), True)


@router.get("/applications/by-id/{app_id}")
def get_app(app_id: int, db: DB) -> dict[str, Any]:
    r = db.get(ApplicationRecord, app_id)
    if r is None:
        raise NotFound("Application not found.")
    return app_out(db, r, True)


class StatusIn(BaseModel):
    status: ApplicationStatus
    note: str | None = Field(default=None, max_length=2000)
    force: bool = Field(default=False, description="Allow corrections outside the normal flow (recorded).")
    applied_at: date | None = None


@router.post("/applications/by-id/{app_id}/status")
def app_status(app_id: int, body: StatusIn, db: DB) -> dict[str, Any]:
    r = db.get(ApplicationRecord, app_id)
    if r is None:
        raise NotFound("Application not found.")
    tracker.set_status(db, r, body.status, note=body.note, force=body.force, applied_at=body.applied_at)
    return app_out(db, r, True)


class AppPatch(BaseModel):
    follow_up_at: date | None = None
    deadline: date | None = None
    applied_at: date | None = None
    notes: str | None = Field(default=None, max_length=20000)
    contact_notes: str | None = Field(default=None, max_length=5000)
    tailored_resume_id: int | None = None
    cover_letter_id: int | None = None


@router.patch("/applications/by-id/{app_id}")
def patch_app(app_id: int, body: AppPatch, db: DB) -> dict[str, Any]:
    r = db.get(ApplicationRecord, app_id)
    if r is None:
        raise NotFound("Application not found.")
    tracker.update(db, r, body.model_dump(exclude_unset=True))
    return app_out(db, r, True)


@router.get("/vacancies/{vacancy_id}/apply-link")
def apply_link(vacancy_id: int, db: DB) -> dict[str, Any]:
    return tracker.apply_link(db, vacancy_id)


# ---------------------------------------------------------------- tailoring


class TailorIn(BaseModel):
    language: Literal["id", "en"] = "id"
    use_ai: bool = True


def tr_out(db: DB, tr: TailoredResume) -> dict[str, Any]:
    return {
        "id": tr.id,
        "vacancy_id": tr.vacancy_id,
        "profile_version_id": tr.profile_version_id,
        "parent_id": tr.parent_id,
        "language": tr.language,
        "content": tr.content,
        "finalized": tr.finalized,
        "template": tr.template,
        "created_at": tr.created_at.isoformat(),
        "preview": tailoring.resolved_document(db, tr),
        "sections": [
            {"title": t, "items": i} for t, i in export.sections(tailoring.resolved_document(db, tr))
        ],
        "exports": [
            {
                "id": e.id,
                "format": e.format,
                "template": e.template,
                "filename": e.filename,
                "created_at": e.created_at.isoformat(),
            }
            for e in db.execute(select(ExportFile).where(ExportFile.tailored_resume_id == tr.id)).scalars()
        ],
    }


@router.post("/vacancies/{vacancy_id}/tailor", status_code=201)
def tailor(vacancy_id: int, body: TailorIn, db: DB) -> dict[str, Any]:
    return tr_out(db, tailoring.generate(db, vacancy_id, language=body.language, use_ai=body.use_ai))


@router.get("/vacancies/{vacancy_id}/tailored")
def tailored_list(vacancy_id: int, db: DB) -> list[dict[str, Any]]:
    rows = db.execute(
        select(TailoredResume)
        .where(TailoredResume.vacancy_id == vacancy_id)
        .order_by(TailoredResume.created_at.desc())
    ).scalars()
    return [
        {
            "id": t.id,
            "parent_id": t.parent_id,
            "language": t.language,
            "finalized": t.finalized,
            "created_at": t.created_at.isoformat(),
            "method": t.content.get("method"),
        }
        for t in rows
    ]


@router.get("/tailored/{tr_id}")
def tailored_get(tr_id: int, db: DB) -> dict[str, Any]:
    tr = db.get(TailoredResume, tr_id)
    if tr is None:
        raise NotFound("Tailored CV not found.")
    return tr_out(db, tr)


class DecideIn(BaseModel):
    decisions: dict[str, bool | None] = Field(default_factory=dict)
    edits: dict[str, str] = Field(default_factory=dict)
    finalize: bool = False
    template: Literal["ats_classic", "modern_professional"] | None = None


@router.post("/tailored/{tr_id}/decisions", status_code=201)
def decide(tr_id: int, body: DecideIn, db: DB) -> dict[str, Any]:
    tr = db.get(TailoredResume, tr_id)
    if tr is None:
        raise NotFound("Tailored CV not found.")
    return tr_out(
        db,
        tailoring.decide(
            db, tr, body.decisions, edits=body.edits, finalize=body.finalize, template=body.template
        ),
    )


class ExportIn(BaseModel):
    format: Literal["pdf", "docx"]
    template: Literal["ats_classic", "modern_professional"] = "ats_classic"


@router.post("/tailored/{tr_id}/export", status_code=201)
def export_cv(tr_id: int, body: ExportIn, db: DB) -> dict[str, Any]:
    tr = db.get(TailoredResume, tr_id)
    if tr is None:
        raise NotFound("Tailored CV not found.")
    ef = export.export_resume(db, tr, body.format, body.template)
    return {"id": ef.id, "filename": ef.filename}


@router.get("/exports/{export_id}")
def download_export(export_id: int, db: DB) -> Response:
    ef = db.get(ExportFile, export_id)
    if ef is None:
        raise NotFound("Export not found.")
    mime = (
        "application/pdf"
        if ef.format == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return Response(
        get_filestore().get(ef.blob_ref),
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{ef.filename}"', "Cache-Control": "no-store"},
    )


class LetterIn(BaseModel):
    language: Literal["id", "en"] = "id"
    tailored_resume_id: int | None = None
    use_ai: bool = True


@router.post("/vacancies/{vacancy_id}/cover-letters", status_code=201)
def letter(vacancy_id: int, body: LetterIn, db: DB) -> dict[str, Any]:
    cl = tailoring.cover_letter(
        db, vacancy_id, language=body.language, tailored_resume_id=body.tailored_resume_id, use_ai=body.use_ai
    )
    return {"id": cl.id, "body": cl.body, "claims": cl.claims, "language": cl.language}


@router.get("/vacancies/{vacancy_id}/cover-letters")
def letters(vacancy_id: int, db: DB) -> list[dict[str, Any]]:
    rows = db.execute(
        select(CoverLetter)
        .where(CoverLetter.vacancy_id == vacancy_id)
        .order_by(CoverLetter.created_at.desc())
    ).scalars()
    return [
        {
            "id": c.id,
            "body": c.body,
            "claims": c.claims,
            "language": c.language,
            "created_at": c.created_at.isoformat(),
        }
        for c in rows
    ]


class LetterExportIn(BaseModel):
    format: Literal["pdf", "docx"]


@router.post("/cover-letters/{cl_id}/export", status_code=201)
def export_letter(cl_id: int, body: LetterExportIn, db: DB) -> dict[str, Any]:
    cl = db.get(CoverLetter, cl_id)
    if cl is None:
        raise NotFound("Cover letter not found.")
    ef = export.export_letter(db, cl, body.format)
    return {"id": ef.id, "filename": ef.filename}
