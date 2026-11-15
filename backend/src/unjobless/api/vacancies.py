"""Discover feed, vacancy detail, opportunity signals, owner actions, dedup review, companies."""

from __future__ import annotations

import base64
import json
from datetime import date, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import aliased

from unjobless.api.deps import DB
from unjobless.core.audit import audit
from unjobless.core.errors import NotFound, ValidationFailed
from unjobless.core.time import utcnow
from unjobless.db.models import (
    ApplicationRecord,
    Company,
    DeduplicationCandidate,
    JobBenefit,
    JobEvidence,
    JobLocation,
    JobRequirement,
    JobSkill,
    JobVacancy,
    JobVacancySource,
    MatchAnalysis,
    OpportunitySignal,
    RawSourceDocument,
    RawSourceVersion,
    SavedOpportunity,
    SignalEntity,
    Source,
    VacancyStatusHistory,
)
from unjobless.domain.enums import Actor, DedupStatus, SavedState
from unjobless.domain.enums import VerificationStatus as V
from unjobless.domain.state_machines import OPEN_STATUSES
from unjobless.fetch.urls import host_of
from unjobless.intelligence import dedup, lifecycle
from unjobless.intelligence.companies import merge_companies
from unjobless.intelligence.normalize import normalized_skill_key

router = APIRouter(tags=["discover"])

HIDDEN_BY_DEFAULT = (V.REJECTED_AS_IRRELEVANT,)
SORTS = {"newest", "best_fit", "preference_fit", "deadline", "confidence", "relevance"}


def _cursor_encode(vals: list[Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(vals, default=str).encode()).decode()


def _cursor_decode(c: str) -> list[Any]:
    try:
        return json.loads(base64.urlsafe_b64decode(c.encode()))
    except Exception as exc:
        raise ValidationFailed("Invalid cursor.") from exc


def vacancy_card(
    v: JobVacancy,
    m: MatchAnalysis | None,
    saved: SavedOpportunity | None,
    sources: list[dict[str, Any]],
    app: ApplicationRecord | None,
) -> dict[str, Any]:
    return {
        "id": v.id,
        "title": v.title,
        "company": v.company_name,
        "company_id": v.company_id,
        "classification": v.classification.value,
        "verification_status": v.verification_status.value,
        "freshness": v.freshness.value,
        "status_reason": v.status_reason,
        "employment_type": v.employment_type.value,
        "work_arrangement": v.work_arrangement.value,
        "seniority": v.seniority.value,
        "location": v.location_text,
        "salary_min": float(v.salary_min) if v.salary_min is not None else None,
        "salary_max": float(v.salary_max) if v.salary_max is not None else None,
        "salary_currency": v.salary_currency,
        "pay_period": v.pay_period.value if v.pay_period else None,
        "is_paid": v.is_paid,
        "application_deadline": v.application_deadline.isoformat() if v.application_deadline else None,
        "application_url": v.application_url,
        "application_domain": host_of(v.application_url) if v.application_url else None,
        "first_seen_at": v.first_seen_at.isoformat(),
        "last_seen_at": v.last_seen_at.isoformat(),
        "last_checked_at": v.last_checked_at.isoformat() if v.last_checked_at else None,
        "last_verified_at": v.last_verified_at.isoformat() if v.last_verified_at else None,
        "source_published_at": v.source_published_at.isoformat() if v.source_published_at else None,
        "data_confidence": v.data_confidence,
        "candidate_fit_score": m.candidate_fit_score if m else None,
        "preference_fit_score": m.preference_fit_score if m else None,
        "overall_score": m.overall_score if m else None,
        "eligible": m.eligible if m else None,
        "saved_state": saved.state.value if saved else None,
        "application_status": app.status.value if app else None,
        "sources": sources,
        "skills_preview": (v.skills_text or "").split(" ")[:8] if v.skills_text else [],
        "warnings": v.extraction_warnings[:3],
    }


def _sources_for(db: DB, ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    rows = db.execute(
        select(
            JobVacancySource.vacancy_id,
            Source.name,
            Source.category,
            JobVacancySource.source_url,
            JobVacancySource.last_seen_at,
        )
        .join(Source, Source.id == JobVacancySource.source_id)
        .where(JobVacancySource.vacancy_id.in_(ids))
    ).all()
    out: dict[int, list[dict[str, Any]]] = {}
    for vid, name, cat, url, seen in rows:
        out.setdefault(vid, []).append(
            {
                "name": name,
                "category": cat.value,
                "url": url,
                "domain": host_of(url) if url else None,
                "last_seen_at": seen.isoformat(),
            }
        )
    return out


@router.get("/vacancies")
def feed(
    db: DB,
    q: str | None = None,
    status: list[str] = Query(default=[]),
    freshness: list[str] = Query(default=[]),
    employment_type: list[str] = Query(default=[]),
    work_arrangement: list[str] = Query(default=[]),
    seniority: list[str] = Query(default=[]),
    city: list[str] = Query(default=[]),
    skill: list[str] = Query(default=[]),
    company: str | None = None,
    industry: str | None = None,
    source_id: int | None = None,
    education: str | None = None,
    min_salary: float | None = None,
    deadline_before: date | None = None,
    found_since: date | None = None,
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    min_fit: float | None = Query(default=None, ge=0, le=1),
    saved: Literal["saved", "interesting", "dismissed", "any", "hide_dismissed"] = "hide_dismissed",
    include_closed: bool = False,
    sort: str = "newest",
    limit: int = Query(25, ge=1, le=100),
    cursor: str | None = None,
) -> dict[str, Any]:
    if sort not in SORTS:
        raise ValidationFailed(f"sort must be one of {sorted(SORTS)}")
    m = aliased(MatchAnalysis)
    s = aliased(SavedOpportunity)
    query = (
        select(JobVacancy, m, s)
        .outerjoin(m, and_(m.vacancy_id == JobVacancy.id, m.is_current.is_(True)))
        .outerjoin(s, s.vacancy_id == JobVacancy.id)
        .where(JobVacancy.merged_into_id.is_(None))
    )
    conds: list[Any] = []
    if status:
        conds.append(JobVacancy.verification_status.in_([V(x) for x in status]))
    elif not include_closed:
        conds.append(JobVacancy.verification_status.not_in([V.REJECTED_AS_IRRELEVANT, V.CLOSED, V.EXPIRED]))
    else:
        conds.append(JobVacancy.verification_status.not_in(HIDDEN_BY_DEFAULT))
    if freshness:
        conds.append(JobVacancy.freshness.in_(freshness))
    if employment_type:
        conds.append(JobVacancy.employment_type.in_(employment_type))
    if work_arrangement:
        conds.append(JobVacancy.work_arrangement.in_(work_arrangement))
    if seniority:
        conds.append(JobVacancy.seniority.in_(seniority))
    if city:
        conds.append(
            exists().where(
                JobLocation.vacancy_id == JobVacancy.id,
                or_(
                    *[func.lower(JobLocation.city) == c.lower() for c in city],
                    JobLocation.is_remote.is_(True) if "remote" in [c.lower() for c in city] else False,
                ),
            )
        )
    for sk in skill:
        conds.append(
            exists().where(
                JobSkill.vacancy_id == JobVacancy.id, JobSkill.normalized_skill == normalized_skill_key(sk)
            )
        )
    if company:
        conds.append(JobVacancy.company_name.ilike(f"%{company}%"))
    if industry:
        conds.append(JobVacancy.industry.ilike(f"%{industry}%"))
    if source_id:
        conds.append(
            exists().where(
                JobVacancySource.vacancy_id == JobVacancy.id, JobVacancySource.source_id == source_id
            )
        )
    if education:
        conds.append(or_(JobVacancy.education_level == education, JobVacancy.education_level.is_(None)))
    if min_salary is not None:
        conds.append(func.coalesce(JobVacancy.salary_max, JobVacancy.salary_min) >= min_salary)
    if deadline_before:
        conds.append(JobVacancy.application_deadline <= deadline_before)
    if found_since:
        conds.append(JobVacancy.first_seen_at >= found_since)
    if min_confidence is not None:
        conds.append(JobVacancy.data_confidence >= min_confidence)
    if min_fit is not None:
        conds.append(m.candidate_fit_score >= min_fit)
    if saved == "saved":
        conds.append(s.state == SavedState.SAVED)
    elif saved == "interesting":
        conds.append(s.state == SavedState.INTERESTING)
    elif saved == "dismissed":
        conds.append(s.state == SavedState.DISMISSED)
    elif saved == "hide_dismissed":
        conds.append(or_(s.state.is_(None), s.state != SavedState.DISMISSED))
    rank: Any = None
    if q:
        tsq = func.websearch_to_tsquery("simple", q)
        conds.append(JobVacancy.search_vector.op("@@")(tsq))
        rank = func.ts_rank(JobVacancy.search_vector, tsq)
    query = query.where(*conds)
    total = db.execute(
        select(func.count()).select_from(query.with_only_columns(JobVacancy.id).subquery())
    ).scalar_one()

    # Keyset pagination: (sort_key, id) — stable across pages.
    key: Any
    if sort == "best_fit":
        key, desc = func.coalesce(m.candidate_fit_score, -1.0), True
    elif sort == "preference_fit":
        key, desc = func.coalesce(m.preference_fit_score, -1.0), True
    elif sort == "deadline":
        key, desc = func.coalesce(JobVacancy.application_deadline, date(9999, 12, 31)), False
    elif sort == "confidence":
        key, desc = func.coalesce(JobVacancy.data_confidence, -1.0), True
    elif sort == "relevance" and rank is not None:
        key, desc = rank, True
    else:
        key, desc = JobVacancy.first_seen_at, True
    if cursor:
        kv, kid = _cursor_decode(cursor)
        if sort == "deadline":
            kv = date.fromisoformat(kv)
        elif sort == "newest" or (sort == "relevance" and rank is None):
            from datetime import datetime

            kv = datetime.fromisoformat(kv)
        query = (
            query.where((key < kv) | ((key == kv) & (JobVacancy.id < kid)))
            if desc
            else query.where((key > kv) | ((key == kv) & (JobVacancy.id < kid)))
        )
    query = (
        query.add_columns(key.label("k"))
        .order_by(key.desc() if desc else key.asc(), JobVacancy.id.desc())
        .limit(limit + 1)
    )
    rows: list[Any] = list(db.execute(query).all())
    more = len(rows) > limit
    rows = rows[:limit]
    ids = [r[0].id for r in rows]
    srcs = _sources_for(db, ids)
    apps = (
        {
            a.vacancy_id: a
            for a in db.execute(
                select(ApplicationRecord).where(ApplicationRecord.vacancy_id.in_(ids))
            ).scalars()
        }
        if ids
        else {}
    )
    items = [vacancy_card(v, mm, ss, srcs.get(v.id, []), apps.get(v.id)) for v, mm, ss, _k in rows]
    next_cursor = _cursor_encode([rows[-1][3], rows[-1][0].id]) if more and rows else None
    return {"items": items, "total": total, "next_cursor": next_cursor}


@router.get("/vacancies/facets")
def facets(db: DB) -> dict[str, Any]:
    base = (
        select(JobVacancy)
        .where(
            JobVacancy.merged_into_id.is_(None),
            JobVacancy.verification_status.not_in([V.REJECTED_AS_IRRELEVANT]),
        )
        .subquery()
    )

    def counts(col: Any) -> dict[str, int]:
        return {
            str(k.value if hasattr(k, "value") else k): c
            for k, c in db.execute(select(col, func.count()).select_from(base).group_by(col)).all()
            if k is not None
        }

    cities = db.execute(
        select(JobLocation.city, func.count())
        .where(JobLocation.city.is_not(None))
        .group_by(JobLocation.city)
        .order_by(func.count().desc())
        .limit(30)
    ).all()
    skills = db.execute(
        select(JobSkill.skill, func.count()).group_by(JobSkill.skill).order_by(func.count().desc()).limit(40)
    ).all()
    return {
        "status": counts(base.c.verification_status),
        "freshness": counts(base.c.freshness),
        "employment_type": counts(base.c.employment_type),
        "work_arrangement": counts(base.c.work_arrangement),
        "cities": [{"city": c, "count": n} for c, n in cities],
        "skills": [{"skill": s, "count": n} for s, n in skills],
        "sources": [
            {"id": i, "name": n}
            for i, n in db.execute(select(Source.id, Source.name).order_by(Source.name)).all()
        ],
    }


@router.get("/vacancies/{vacancy_id}")
def detail(vacancy_id: int, db: DB) -> dict[str, Any]:
    v = db.get(JobVacancy, vacancy_id)
    if v is None:
        raise NotFound("Vacancy not found.")
    redirected_from = None
    if v.merged_into_id:
        redirected_from = v.id
        v = db.get(JobVacancy, v.merged_into_id) or v
    m = db.execute(
        select(MatchAnalysis).where(MatchAnalysis.vacancy_id == v.id, MatchAnalysis.is_current.is_(True))
    ).scalar_one_or_none()
    saved = db.execute(
        select(SavedOpportunity).where(SavedOpportunity.vacancy_id == v.id)
    ).scalar_one_or_none()
    app = db.execute(
        select(ApplicationRecord).where(ApplicationRecord.vacancy_id == v.id)
    ).scalar_one_or_none()
    card = vacancy_card(v, m, saved, _sources_for(db, [v.id]).get(v.id, []), app)
    links = db.execute(
        select(JobVacancySource, Source, RawSourceDocument)
        .join(Source, Source.id == JobVacancySource.source_id)
        .join(RawSourceDocument, RawSourceDocument.id == JobVacancySource.raw_document_id)
        .where(JobVacancySource.vacancy_id == v.id)
    ).all()
    evidence = db.execute(
        select(JobEvidence).where(JobEvidence.vacancy_id == v.id).order_by(JobEvidence.field_name)
    ).scalars()
    history = db.execute(
        select(VacancyStatusHistory)
        .where(VacancyStatusHistory.vacancy_id == v.id)
        .order_by(VacancyStatusHistory.at.desc())
    ).scalars()
    unknown = [
        f
        for f, val in {
            "salary": v.salary_min,
            "deadline": v.application_deadline,
            "location": v.location_text,
            "employment type": None if v.employment_type.value == "UNKNOWN" else 1,
            "work arrangement": None if v.work_arrangement.value == "UNKNOWN" else 1,
            "application link": v.application_url or (v.details or {}).get("application_email"),
            "company": v.company_name,
        }.items()
        if val is None
    ]
    dups = (
        db.execute(
            select(DeduplicationCandidate).where(
                or_(DeduplicationCandidate.vacancy_a_id == v.id, DeduplicationCandidate.vacancy_b_id == v.id),
                DeduplicationCandidate.status == DedupStatus.PENDING,
            )
        )
        .scalars()
        .all()
    )
    return {
        **card,
        "redirected_from": redirected_from,
        "alternative_title": v.alternative_title,
        "department": v.department,
        "job_family": v.job_family,
        "industry": v.industry,
        "openings_count": v.openings_count,
        "recruitment_batch": v.recruitment_batch,
        "internship_duration_months": float(v.internship_duration_months)
        if v.internship_duration_months is not None
        else None,
        "education_level": v.education_level,
        "min_semester": v.min_semester,
        "min_gpa": float(v.min_gpa) if v.min_gpa is not None else None,
        "experience_years_min": float(v.experience_years_min) if v.experience_years_min is not None else None,
        "start_date": v.start_date.isoformat() if v.start_date else None,
        "description": v.description,
        "details": v.details,
        "field_meta": v.field_meta,
        "language": v.language,
        "remote_eligible_countries": v.remote_eligible_countries,
        "skills": [
            {"skill": s.skill, "required": s.required}
            for s in db.execute(select(JobSkill).where(JobSkill.vacancy_id == v.id)).scalars()
        ],
        "requirements": [
            {"kind": r.kind, "value": r.value}
            for r in db.execute(select(JobRequirement).where(JobRequirement.vacancy_id == v.id)).scalars()
        ],
        "benefits": [
            {"category": b.category, "value": b.value}
            for b in db.execute(select(JobBenefit).where(JobBenefit.vacancy_id == v.id)).scalars()
        ],
        "locations": [
            {
                "raw": loc.raw,
                "city": loc.city,
                "region": loc.region,
                "country": loc.country,
                "is_remote": loc.is_remote,
            }
            for loc in db.execute(select(JobLocation).where(JobLocation.vacancy_id == v.id)).scalars()
        ],
        "source_links": [
            {
                "source": src.name,
                "category": src.category.value,
                "collection_method": src.collection_method.value,
                "url": link.source_url,
                "application_url": link.application_url,
                "native_id": link.source_native_id,
                "first_seen_at": link.first_seen_at.isoformat(),
                "last_seen_at": link.last_seen_at.isoformat(),
                "raw_document_id": doc.id,
                "raw_version_id": link.raw_version_id,
                "gone_at": doc.gone_at.isoformat() if doc.gone_at else None,
            }
            for link, src, doc in links
        ],
        "evidence": [
            {
                "field": e.field_name,
                "excerpt": e.excerpt,
                "origin": e.origin.value,
                "confidence": e.confidence,
                "raw_version_id": e.raw_version_id,
                "start": e.start_offset,
                "end": e.end_offset,
            }
            for e in evidence
        ],
        "history": [
            {
                "from": h.from_status.value if h.from_status else None,
                "to": h.to_status.value,
                "reason": h.reason,
                "rule": h.rule,
                "actor": h.actor.value,
                "at": h.at.isoformat(),
            }
            for h in history
        ],
        "match": {
            "breakdown": m.breakdown,
            "weights": m.weights,
            "algorithm_version": m.algorithm_version,
            "computed_at": m.computed_at.isoformat(),
        }
        if m
        else None,
        "unknown_fields": unknown,
        "duplicate_candidates": [
            {
                "id": d.id,
                "other_id": d.vacancy_b_id if d.vacancy_a_id == v.id else d.vacancy_a_id,
                "score": d.score,
                "signals": d.signals,
            }
            for d in dups
        ],
        "saved_note": saved.note if saved else None,
    }


@router.get("/raw-versions/{version_id}")
def raw_version(version_id: int, db: DB) -> dict[str, Any]:
    from unjobless.intelligence.pipeline import version_text

    rv = db.get(RawSourceVersion, version_id)
    if rv is None:
        raise NotFound("Raw version not found.")
    doc = db.get(RawSourceDocument, rv.document_id)
    return {
        "id": rv.id,
        "document_id": rv.document_id,
        "url": doc.original_url if doc else None,
        "content_type": rv.content_type,
        "collected_at": rv.collected_at.isoformat(),
        "content_hash": rv.content_hash,
        "truncated": rv.truncated,
        "title": rv.title,
        "metadata": rv.metadata_,
        "text": version_text(rv)[:100_000],
        "classification": rv.classification_detail,
    }


class SaveIn(BaseModel):
    state: SavedState | None
    note: str | None = Field(default=None, max_length=5000)


@router.put("/vacancies/{vacancy_id}/saved")
def set_saved(vacancy_id: int, body: SaveIn, db: DB) -> dict[str, Any]:
    if db.get(JobVacancy, vacancy_id) is None:
        raise NotFound("Vacancy not found.")
    row = db.execute(
        select(SavedOpportunity).where(SavedOpportunity.vacancy_id == vacancy_id)
    ).scalar_one_or_none()
    if body.state is None:
        if row:
            db.delete(row)
        return {"state": None}
    if row is None:
        row = SavedOpportunity(vacancy_id=vacancy_id, state=body.state)
        db.add(row)
    row.state, row.note = body.state, body.note if body.note is not None else row.note
    if body.state == SavedState.REPORTED:
        audit(
            db,
            "vacancy.reported_incorrect",
            target_type="vacancy",
            target_id=vacancy_id,
            details={"note": (body.note or "")[:500]},
        )
    return {"state": row.state.value, "note": row.note}


class StatusIn(BaseModel):
    status: V
    reason: str = Field(min_length=3, max_length=1000)


@router.post("/vacancies/{vacancy_id}/status")
def correct_status(vacancy_id: int, body: StatusIn, db: DB) -> dict[str, Any]:
    v = db.get(JobVacancy, vacancy_id)
    if v is None:
        raise NotFound("Vacancy not found.")
    lifecycle.set_status(db, v, body.status, reason=body.reason, rule="owner_correction", actor=Actor.USER)
    return {"status": v.verification_status.value, "freshness": v.freshness.value}


# ---------------------------------------------------------------- signals


@router.get("/signals")
def signals(
    db: DB,
    q: str | None = None,
    classification: list[str] = Query(default=[]),
    status: list[str] = Query(default=[]),
    include_rejected: bool = False,
    limit: int = Query(25, ge=1, le=100),
    offset: int = 0,
) -> dict[str, Any]:
    query = (
        select(OpportunitySignal, RawSourceVersion, RawSourceDocument, Source)
        .join(RawSourceVersion, RawSourceVersion.id == OpportunitySignal.raw_version_id)
        .join(RawSourceDocument, RawSourceDocument.id == RawSourceVersion.document_id)
        .join(Source, Source.id == RawSourceDocument.source_id)
    )
    if classification:
        query = query.where(OpportunitySignal.primary_classification.in_(classification))
    if status:
        query = query.where(OpportunitySignal.status.in_(status))
    elif not include_rejected:
        query = query.where(OpportunitySignal.status.not_in([V.REJECTED_AS_IRRELEVANT]))
    if q:
        query = query.where(OpportunitySignal.search_vector.op("@@")(func.websearch_to_tsquery("simple", q)))
    total = db.execute(
        select(func.count()).select_from(query.with_only_columns(OpportunitySignal.id).subquery())
    ).scalar_one()
    rows = db.execute(
        query.order_by(OpportunitySignal.observed_at.desc(), OpportunitySignal.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    items = []
    for s, rv, doc, src in rows:
        ents = db.execute(select(SignalEntity).where(SignalEntity.signal_id == s.id)).scalars()
        items.append(
            {
                "id": s.id,
                "classification": s.primary_classification.value,
                "secondary": s.secondary_classifications,
                "signal_type": s.signal_type.value,
                "confidence": s.confidence,
                "status": s.status.value,
                "recommendation": s.verification_recommendation.value,
                "reason": s.reason,
                "ambiguity_flags": s.ambiguity_flags,
                "company": s.company_text,
                "role": s.role_text,
                "location": s.location_text,
                "application_url": s.application_url,
                "summary": s.summary,
                "observed_at": s.observed_at.isoformat(),
                "promoted_vacancy_id": s.promoted_vacancy_id,
                "source": {
                    "name": src.name,
                    "category": src.category.value,
                    "url": doc.original_url,
                    "author_label": (rv.metadata_ or {}).get("author_label"),
                },
                "entities": [
                    {
                        "kind": e.kind,
                        "value": e.value,
                        "origin": e.origin.value,
                        "excerpt": e.evidence_excerpt,
                    }
                    for e in ents
                ],
                "evidence": (s.detail or {}).get("evidence", []),
                "raw_version_id": rv.id,
            }
        )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


class SignalStatusIn(BaseModel):
    status: Literal["POTENTIAL_LEAD", "REJECTED_AS_IRRELEVANT", "EXPIRED", "NEEDS_REVIEW"]
    reason: str | None = None


@router.post("/signals/{signal_id}/status")
def signal_status(signal_id: int, body: SignalStatusIn, db: DB) -> dict[str, Any]:
    s = db.get(OpportunitySignal, signal_id)
    if s is None:
        raise NotFound("Signal not found.")
    s.status = V(body.status)
    audit(
        db,
        "signal.status",
        target_type="signal",
        target_id=s.id,
        details={"to": body.status, "reason": body.reason},
    )
    return {"status": s.status.value}


class PromoteIn(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    company: str | None = None
    application_url: str | None = None
    confirm_open: bool = Field(description="Owner explicitly confirms the opening is real and open.")


@router.post("/signals/{signal_id}/promote")
def promote(signal_id: int, body: PromoteIn, db: DB) -> dict[str, Any]:
    """Explicit owner action: promote an unverified lead to a vacancy with evidence of the original signal."""
    from unjobless.ai.task_schemas import JobExtraction
    from unjobless.intelligence.extraction import empty_extraction, rules_extract
    from unjobless.intelligence.pipeline import version_text
    from unjobless.intelligence.vacancies import create_vacancy

    if not body.confirm_open:
        raise ValidationFailed("Confirm that you verified the opening before promoting a lead.")
    s = db.get(OpportunitySignal, signal_id)
    if s is None:
        raise NotFound("Signal not found.")
    if s.promoted_vacancy_id:
        return {"vacancy_id": s.promoted_vacancy_id}
    rv = db.get(RawSourceVersion, s.raw_version_id)
    doc = db.get(RawSourceDocument, rv.document_id) if rv else None
    src = db.get(Source, doc.source_id) if doc else None
    if rv is None or doc is None or src is None:
        raise NotFound("Signal source missing.")
    text = version_text(rv)
    data = {**empty_extraction(), **rules_extract(text, title=body.title)}
    data.update(
        title=body.title,
        company=body.company or s.company_text,
        application_url=body.application_url or s.application_url,
        is_job_posting=True,
    )
    x = JobExtraction.model_validate(data)
    v = create_vacancy(
        db,
        x=x,
        source=src,
        document=doc,
        version=rv,
        source_text=text,
        status=V.VERIFIED_OPEN,
        actor=Actor.USER,
        reason="Lead promoted after the owner verified the opening.",
    )
    s.promoted_vacancy_id = v.id
    audit(db, "signal.promoted", target_type="signal", target_id=s.id, details={"vacancy_id": v.id})
    return {"vacancy_id": v.id}


# ---------------------------------------------------------------- dedup review & companies


@router.get("/dedup/candidates")
def dedup_candidates(db: DB, status: DedupStatus = DedupStatus.PENDING) -> list[dict[str, Any]]:
    rows = db.execute(
        select(DeduplicationCandidate)
        .where(DeduplicationCandidate.status == status)
        .order_by(DeduplicationCandidate.score.desc())
        .limit(100)
    ).scalars()
    out = []
    for c in rows:
        a, b = db.get(JobVacancy, c.vacancy_a_id), db.get(JobVacancy, c.vacancy_b_id)
        if a is None or b is None:
            continue
        out.append(
            {
                "id": c.id,
                "score": c.score,
                "signals": c.signals,
                "status": c.status.value,
                "a": {
                    "id": a.id,
                    "title": a.title,
                    "company": a.company_name,
                    "location": a.location_text,
                    "url": a.canonical_url,
                },
                "b": {
                    "id": b.id,
                    "title": b.title,
                    "company": b.company_name,
                    "location": b.location_text,
                    "url": b.canonical_url,
                },
            }
        )
    return out


class DedupDecision(BaseModel):
    action: Literal["merge", "reject", "undo"]
    keep_id: int | None = None


@router.post("/dedup/candidates/{cand_id}")
def dedup_decide(cand_id: int, body: DedupDecision, db: DB) -> dict[str, Any]:
    c = db.get(DeduplicationCandidate, cand_id)
    if c is None:
        raise NotFound("Candidate not found.")
    if body.action == "merge":
        dedup.merge(db, c, keep_id=body.keep_id or c.vacancy_a_id)
    elif body.action == "reject":
        dedup.reject(db, c)
    else:
        dedup.undo_merge(db, c)
    return {"status": c.status.value}


@router.post("/vacancies/{a_id}/merge/{b_id}")
def manual_merge(a_id: int, b_id: int, db: DB) -> dict[str, Any]:
    c = dedup._candidate(db, a_id, b_id)
    v = dedup.merge(db, c, keep_id=a_id)
    return {"vacancy_id": v.id, "candidate_id": c.id}


@router.get("/companies")
def companies(db: DB, q: str | None = None, limit: int = Query(50, le=200)) -> list[dict[str, Any]]:
    query = (
        select(Company, func.count(JobVacancy.id))
        .outerjoin(JobVacancy, and_(JobVacancy.company_id == Company.id, JobVacancy.merged_into_id.is_(None)))
        .where(Company.merged_into_id.is_(None))
        .group_by(Company.id)
    )
    if q:
        query = query.where(Company.name.ilike(f"%{q}%"))
    rows = db.execute(query.order_by(func.count(JobVacancy.id).desc()).limit(limit)).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "website_domain": c.website_domain,
            "industry": c.industry,
            "vacancies": n,
            "verified": c.manually_verified,
        }
        for c, n in rows
    ]


class CompanyMergeIn(BaseModel):
    keep_id: int
    merge_id: int


@router.post("/companies/merge")
def company_merge(body: CompanyMergeIn, db: DB) -> dict[str, Any]:
    c = merge_companies(db, body.keep_id, body.merge_id)
    return {"id": c.id, "name": c.name}


@router.get("/overview")
def overview(db: DB) -> dict[str, Any]:
    from unjobless.db.models import ImportItem, SourceRun
    from unjobless.domain.enums import ImportItemStatus, SourceHealth, SourceState

    week = utcnow() - timedelta(days=7)
    open_q = (
        select(func.count())
        .select_from(JobVacancy)
        .where(JobVacancy.merged_into_id.is_(None), JobVacancy.verification_status.in_(OPEN_STATUSES))
    )
    new_q = (
        select(func.count())
        .select_from(JobVacancy)
        .where(JobVacancy.merged_into_id.is_(None), JobVacancy.first_seen_at >= week)
    )
    closing = (
        select(func.count())
        .select_from(JobVacancy)
        .where(
            JobVacancy.merged_into_id.is_(None),
            JobVacancy.application_deadline.between(date.today(), date.today() + timedelta(days=7)),
            JobVacancy.verification_status.in_(OPEN_STATUSES),
        )
    )
    leads = (
        select(func.count())
        .select_from(OpportunitySignal)
        .where(OpportunitySignal.status == V.POTENTIAL_LEAD)
    )
    review = (
        select(func.count()).select_from(ImportItem).where(ImportItem.status == ImportItemStatus.NEEDS_REVIEW)
    )
    srcs = db.execute(select(Source).where(Source.is_system.is_(False))).scalars().all()
    top = db.execute(
        select(JobVacancy, MatchAnalysis)
        .join(
            MatchAnalysis, and_(MatchAnalysis.vacancy_id == JobVacancy.id, MatchAnalysis.is_current.is_(True))
        )
        .where(
            JobVacancy.merged_into_id.is_(None),
            JobVacancy.verification_status.in_(OPEN_STATUSES),
            MatchAnalysis.overall_score.is_not(None),
        )
        .order_by(MatchAnalysis.overall_score.desc())
        .limit(5)
    ).all()
    last_run = db.execute(select(func.max(SourceRun.finished_at))).scalar()
    return {
        "counts": {
            "open_vacancies": db.execute(open_q).scalar_one(),
            "new_this_week": db.execute(new_q).scalar_one(),
            "closing_soon": db.execute(closing).scalar_one(),
            "potential_leads": db.execute(leads).scalar_one(),
            "needs_review": db.execute(review).scalar_one(),
        },
        "sources": {
            "total": len(srcs),
            "enabled": sum(s.state == SourceState.ENABLED for s in srcs),
            "failing": sum(s.health in (SourceHealth.FAILING, SourceHealth.UNAVAILABLE) for s in srcs),
            "rate_limited": sum(s.health == SourceHealth.RATE_LIMITED for s in srcs),
            "last_run_at": last_run.isoformat() if last_run else None,
        },
        "top_matches": [
            {
                "id": v.id,
                "title": v.title,
                "company": v.company_name,
                "overall_score": mm.overall_score,
                "candidate_fit_score": mm.candidate_fit_score,
                "preference_fit_score": mm.preference_fit_score,
            }
            for v, mm in top
        ],
    }
