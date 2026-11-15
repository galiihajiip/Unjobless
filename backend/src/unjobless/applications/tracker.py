"""Personal application tracker. Unjobless never submits applications; the owner marks status manually."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from unjobless.core.audit import audit
from unjobless.core.errors import NotFound, ValidationFailed
from unjobless.db.models import ApplicationRecord, ApplicationStatusHistory, JobVacancy
from unjobless.domain.enums import Actor, ApplicationStatus
from unjobless.domain.state_machines import APPLICATION
from unjobless.fetch.safe_fetch import validate_url
from unjobless.fetch.urls import host_of


def get_or_create(db: Session, vacancy_id: int) -> ApplicationRecord:
    v = db.get(JobVacancy, vacancy_id)
    if v is None:
        raise NotFound("Vacancy not found.")
    rec = db.execute(select(ApplicationRecord).where(ApplicationRecord.vacancy_id == vacancy_id)).scalar_one_or_none()
    if rec is None:
        rec = ApplicationRecord(vacancy_id=vacancy_id, status=ApplicationStatus.SAVED, deadline=v.application_deadline)
        db.add(rec)
        db.flush()
        db.add(ApplicationStatusHistory(application_id=rec.id, from_status=None, to_status=ApplicationStatus.SAVED, note="Tracked", actor=Actor.USER))
    return rec


def set_status(db: Session, rec: ApplicationRecord, to: ApplicationStatus, *, note: str | None = None, force: bool = False, applied_at: date | None = None) -> ApplicationRecord:
    if rec.status == to and to != ApplicationStatus.INTERVIEW:
        return rec
    if not force:
        APPLICATION.check(rec.status, to)
    db.add(ApplicationStatusHistory(application_id=rec.id, from_status=rec.status, to_status=to, note=note, actor=Actor.USER))
    rec.status = to
    if to == ApplicationStatus.APPLIED and rec.applied_at is None:
        rec.applied_at = applied_at or date.today()
    audit(db, "application.status", target_type="application", target_id=rec.id, details={"to": to.value, "forced": force})
    return rec


def update(db: Session, rec: ApplicationRecord, data: dict[str, Any]) -> ApplicationRecord:
    for f in ("follow_up_at", "deadline", "notes", "contact_notes", "applied_at", "tailored_resume_id", "cover_letter_id"):
        if f in data:
            setattr(rec, f, data[f])
    return rec


def apply_link(db: Session, vacancy_id: int) -> dict[str, Any]:
    """Validated original destination. The UI opens it in a new tab (rel=noopener noreferrer)."""
    v = db.get(JobVacancy, vacancy_id)
    if v is None:
        raise NotFound("Vacancy not found.")
    url = v.application_url
    if not url:
        email = (v.details or {}).get("application_email")
        if email:
            return {"kind": "email", "destination": email, "domain": email.split("@")[-1], "note": "This posting asks for applications by email."}
        raise ValidationFailed("No original application link is known for this vacancy.", code="no_apply_link")
    try:
        validate_url(url, resolve=False)
    except Exception as exc:
        raise ValidationFailed("The stored application link is not a safe web address.", code="unsafe_link") from exc
    return {"kind": "url", "destination": url, "domain": host_of(url), "note": "You will leave Unjobless and apply on the original site. Unjobless does not submit applications."}
