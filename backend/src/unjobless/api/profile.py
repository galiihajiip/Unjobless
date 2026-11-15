from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select

from unjobless.api.deps import DB
from unjobless.core.audit import audit
from unjobless.core.errors import NotFound
from unjobless.db.models import CandidateProfileVersion, CareerPreferences, ResumeDocument, ResumeExtraction
from unjobless.ingestion.filestore import get_filestore
from unjobless.jobs.queue import defer
from unjobless.profile import cv
from unjobless.profile.schemas import CareerPreferencesData, ProfileData

router = APIRouter(prefix="/profile", tags=["profile"])


def version_out(v: CandidateProfileVersion) -> dict[str, Any]:
    return {
        "id": v.id, "version_no": v.version_no, "status": v.status.value, "source_resume_id": v.source_resume_id, "note": v.note,
        "created_at": v.created_at.isoformat(), "confirmed_at": v.confirmed_at.isoformat() if v.confirmed_at else None, "data": v.data,
    }


@router.get("")
def overview(db: DB) -> dict[str, Any]:
    prof = cv.get_profile(db)
    versions = db.execute(select(CandidateProfileVersion).where(CandidateProfileVersion.profile_id == prof.id).order_by(CandidateProfileVersion.version_no.desc())).scalars().all()
    resumes = db.execute(select(ResumeDocument).order_by(ResumeDocument.uploaded_at.desc())).scalars().all()
    active = next((v for v in versions if v.id == prof.active_version_id), None)
    return {
        "active": version_out(active) if active else None,
        "versions": [{k: x for k, x in version_out(v).items() if k != "data"} for v in versions],
        "resumes": [{"id": r.id, "filename": r.filename, "mime": r.mime, "byte_size": r.byte_size, "uploaded_at": r.uploaded_at.isoformat(), "label": r.label} for r in resumes],
        "latest_draft": next((version_out(v) for v in versions if v.status.value == "DRAFT"), None),
    }


@router.post("/resumes", status_code=202)
async def upload(db: DB, file: UploadFile = File(...), label: str | None = Form(default=None)) -> dict[str, Any]:
    data = await file.read(cv.get_settings().max_upload_bytes + 1)
    doc = cv.upload_resume(db, data, file.filename or "cv", label)
    db.commit()
    defer("process_resume", queueing_lock=f"resume-{doc.id}", resume_id=doc.id)
    return {"resume_id": doc.id}


@router.get("/resumes/{resume_id}/file")
def download(resume_id: int, db: DB) -> Response:
    doc = db.get(ResumeDocument, resume_id)
    if doc is None:
        raise NotFound("CV not found.")
    return Response(get_filestore().get(doc.blob_ref), media_type=doc.mime, headers={"Content-Disposition": f'attachment; filename="{doc.filename}"', "Cache-Control": "no-store"})


@router.get("/resumes/{resume_id}/extraction")
def extraction(resume_id: int, db: DB) -> dict[str, Any]:
    ext = db.execute(select(ResumeExtraction).where(ResumeExtraction.resume_id == resume_id).order_by(ResumeExtraction.created_at.desc())).scalars().first()
    if ext is None:
        return {"status": "processing"}
    return {"status": "done", "method": ext.method, "warnings": ext.warnings, "text": ext.text[:100_000], "sections": list(ext.sections)}


@router.post("/resumes/{resume_id}/reprocess", status_code=202)
def reprocess(resume_id: int, db: DB) -> dict[str, Any]:
    if db.get(ResumeDocument, resume_id) is None:
        raise NotFound("CV not found.")
    defer("process_resume", queueing_lock=f"resume-{resume_id}", resume_id=resume_id)
    return {"status": "queued"}


@router.get("/versions/{version_id}")
def get_version(version_id: int, db: DB) -> dict[str, Any]:
    return version_out(cv.get_version(db, version_id))


@router.put("/versions/{version_id}")
def edit(version_id: int, body: ProfileData, db: DB) -> dict[str, Any]:
    v = cv.update_draft(db, cv.get_version(db, version_id), body.model_dump(mode="json"))
    return version_out(v)


@router.post("/drafts")
def blank_or_copy(db: DB) -> dict[str, Any]:
    """Start a new draft from the active version (or empty, for manual entry)."""
    active = cv.active_version(db)
    data = ProfileData.model_validate(active.data) if active else ProfileData()
    return version_out(cv.new_draft(db, data, note="Manual edit"))


@router.post("/versions/{version_id}/confirm")
def confirm(version_id: int, db: DB) -> dict[str, Any]:
    v = cv.confirm(db, cv.get_version(db, version_id))
    db.commit()
    defer("recompute_matches", queueing_lock="recompute_matches")
    return version_out(v)


@router.get("/preferences")
def get_prefs(db: DB) -> dict[str, Any]:
    row = db.execute(select(CareerPreferences)).scalar_one_or_none()
    return CareerPreferencesData.model_validate(row.data if row else {}).model_dump(mode="json")


@router.put("/preferences")
def put_prefs(body: CareerPreferencesData, db: DB) -> dict[str, Any]:
    row = db.execute(select(CareerPreferences)).scalar_one_or_none()
    if row is None:
        db.add(CareerPreferences(data=body.model_dump(mode="json")))
    else:
        row.data = body.model_dump(mode="json")
    audit(db, "preferences.updated")
    db.commit()
    defer("recompute_matches", queueing_lock="recompute_matches")
    return body.model_dump(mode="json")


class RecomputeOut(BaseModel):
    updated: int


@router.post("/matches/recompute")
def recompute(db: DB) -> RecomputeOut:
    from unjobless.profile.matching import recompute_all

    return RecomputeOut(updated=recompute_all(db))
