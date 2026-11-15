"""Vacancy freshness and lifecycle (docs/domain/STATE_MACHINES.md §5–6).

Deterministic rules:
- explicit past deadline (evidence-backed) → EXPIRED (rule `deadline_passed`);
- a failed fetch / item missing from a partial listing → at most STATUS_UNKNOWN (never CLOSED);
- missing from a *complete* listing of an approved API/ATS source twice → STATUS_UNKNOWN, then
  SOURCE_UNAVAILABLE after 7 days; closure requires explicit evidence or the owner;
- seen again in a live listing of an approved ATS/API source → VERIFIED_OPEN (re-confirmation);
- old publication date alone never expires a vacancy;
- owner corrections are always allowed and recorded with actor=USER.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from unjobless.core.time import utcnow
from unjobless.db.models import JobVacancy, JobVacancySource, RawSourceDocument, Source, VacancyStatusHistory
from unjobless.domain.enums import Actor, CollectionMethod, FreshnessState, PolicyStatus
from unjobless.domain.enums import VerificationStatus as V
from unjobless.domain.state_machines import VERIFICATION

CLOSING_SOON_DAYS = 7
NEW_DAYS = 3
ACTIVE_DAYS = 14
STALE_DAYS = 30
TRUSTED_METHODS = {CollectionMethod.ATS_PUBLIC_API, CollectionMethod.OFFICIAL_API}


def set_status(
    db: Session,
    v: JobVacancy,
    to: V,
    *,
    reason: str,
    rule: str | None = None,
    actor: Actor = Actor.SYSTEM,
    at: datetime | None = None,
) -> bool:
    if v.verification_status == to:
        return False
    if actor == Actor.SYSTEM:
        VERIFICATION.check(v.verification_status, to)
    db.add(
        VacancyStatusHistory(
            vacancy_id=v.id,
            from_status=v.verification_status,
            to_status=to,
            reason=reason,
            rule=rule,
            actor=actor,
        )
    )
    v.verification_status = to
    v.status_reason = reason
    now = at or utcnow()
    if to in (V.CLOSED, V.EXPIRED) and v.closed_at is None:
        v.closed_at = now
    if to == V.VERIFIED_OPEN:
        v.last_verified_at = now
        v.closed_at = None
    v.freshness = compute_freshness(v, today=now.date())
    return True


def compute_freshness(v: JobVacancy, *, today: date | None = None) -> FreshnessState:
    today = today or utcnow().date()
    now = datetime.combine(today, datetime.min.time()).astimezone()
    if v.verification_status in (V.EXPIRED, V.CLOSED):
        return FreshnessState.EXPIRED
    if v.application_deadline and v.application_deadline < today:
        return FreshnessState.EXPIRED
    if v.application_deadline and (v.application_deadline - today).days <= CLOSING_SOON_DAYS:
        return FreshnessState.CLOSING_SOON
    if v.verification_status in (V.STATUS_UNKNOWN, V.SOURCE_UNAVAILABLE):
        return FreshnessState.UNKNOWN
    if v.first_seen_at and (now - v.first_seen_at) < timedelta(days=NEW_DAYS):
        return FreshnessState.NEW
    ref = v.last_verified_at or v.last_seen_at
    if ref and (now - ref) < timedelta(days=ACTIVE_DAYS):
        return FreshnessState.ACTIVE
    if ref and (now - ref) >= timedelta(days=STALE_DAYS):
        return FreshnessState.STALE
    return FreshnessState.UNKNOWN


def apply_deadline_rule(db: Session, v: JobVacancy, *, today: date | None = None) -> None:
    today = today or utcnow().date()
    has_evidence = any(f == "application_deadline" for f in (v.field_meta or {}).get("evidenced_fields", []))
    if (
        v.application_deadline
        and v.application_deadline < today
        and v.verification_status not in (V.EXPIRED, V.CLOSED, V.REJECTED_AS_IRRELEVANT)
    ):
        if has_evidence or (v.field_meta or {}).get("application_deadline", {}).get("origin") == "EXPLICIT":
            if VERIFICATION.allowed(v.verification_status, V.EXPIRED):
                set_status(
                    db,
                    v,
                    V.EXPIRED,
                    reason=f"Explicit application deadline {v.application_deadline.isoformat()} has passed.",
                    rule="deadline_passed",
                )


def confirm_seen_in_trusted_listing(db: Session, v: JobVacancy, source: Source) -> None:
    v.last_seen_at = v.last_checked_at = utcnow()
    if source.collection_method in TRUSTED_METHODS and source.policy_status == PolicyStatus.APPROVED:
        if v.verification_status in (
            V.NEW_UNREVIEWED,
            V.LIKELY_OPEN,
            V.STATUS_UNKNOWN,
            V.SOURCE_UNAVAILABLE,
            V.VERIFIED_OPEN,
        ):
            if v.verification_status != V.VERIFIED_OPEN:
                set_status(
                    db,
                    v,
                    V.VERIFIED_OPEN,
                    reason=f"Live in the {source.name} listing.",
                    rule="live_in_trusted_listing",
                )
            else:
                v.last_verified_at = utcnow()
    v.freshness = compute_freshness(v)


def mark_missing_from_complete_listing(db: Session, source: Source, seen_doc_ids: set[int]) -> int:
    """After a *complete* listing run: vacancies whose source doc was not listed become uncertain."""
    if source.collection_method not in TRUSTED_METHODS:
        return 0
    rows = db.execute(
        select(JobVacancy, RawSourceDocument)
        .join(JobVacancySource, JobVacancySource.vacancy_id == JobVacancy.id)
        .join(RawSourceDocument, RawSourceDocument.id == JobVacancySource.raw_document_id)
        .where(JobVacancySource.source_id == source.id)
    ).all()
    n = 0
    now = utcnow()
    for v, doc in rows:
        if doc.id in seen_doc_ids:
            continue
        doc.gone_at = doc.gone_at or now
        v.last_checked_at = now
        if v.verification_status in (V.VERIFIED_OPEN, V.LIKELY_OPEN):
            set_status(
                db,
                v,
                V.STATUS_UNKNOWN,
                reason=f"No longer in the {source.name} listing; may be closed, hidden or moved.",
                rule="missing_from_listing",
            )
            n += 1
        elif (
            v.verification_status == V.STATUS_UNKNOWN
            and doc.gone_at
            and now - doc.gone_at > timedelta(days=7)
        ):
            set_status(
                db,
                v,
                V.SOURCE_UNAVAILABLE,
                reason="Missing from the source listing for over 7 days.",
                rule="missing_7_days",
            )
            n += 1
    return n


def recheck_all(db: Session, *, today: date | None = None) -> int:
    """Daily: deadline rule + freshness recompute for every non-terminal vacancy."""
    n = 0
    for v in db.execute(select(JobVacancy).where(JobVacancy.merged_into_id.is_(None))).scalars():
        before = (v.verification_status, v.freshness)
        apply_deadline_rule(db, v, today=today)
        v.freshness = compute_freshness(v, today=today)
        n += int(before != (v.verification_status, v.freshness))
    return n
