"""Cross-source vacancy deduplication.

Auto-merge only on strong identity evidence (same canonical/application URL, or same company +
near-identical title + compatible location/level + very similar description). Ambiguous pairs
go to a review queue. Different locations/levels/employment types never merge automatically.
Merges keep every source reference and raw document, write status history and an undo payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from unjobless.core.audit import audit
from unjobless.core.errors import NotFound, ValidationFailed
from unjobless.core.time import utcnow
from unjobless.db.models import (
    DeduplicationCandidate,
    JobLocation,
    JobVacancy,
    JobVacancySource,
    VacancyStatusHistory,
)
from unjobless.domain.enums import Actor, DedupStatus
from unjobless.intelligence.vacancies import canonical_app_url

AUTO_MERGE = 0.92
REVIEW = 0.72


@dataclass
class PairScore:
    score: float
    signals: dict[str, Any]
    blockers: list[str]
    strong: bool


def _cities(db: Session, v: JobVacancy) -> set[str]:
    return {
        c
        for (c,) in db.execute(
            select(JobLocation.city).where(JobLocation.vacancy_id == v.id, JobLocation.city.is_not(None))
        )
    }


def score_pair(db: Session, a: JobVacancy, b: JobVacancy) -> PairScore:
    s: dict[str, Any] = {}
    blockers: list[str] = []
    strong = False
    if a.canonical_url and a.canonical_url == b.canonical_url:
        s["canonical_url"] = True
        strong = True
    ua, ub = canonical_app_url(a.application_url), canonical_app_url(b.application_url)
    if ua and ua == ub:
        s["application_url"] = True
        strong = True
    same_company = a.company_id is not None and a.company_id == b.company_id
    s["same_company"] = same_company
    title_sim = fuzz.token_set_ratio(a.normalized_title, b.normalized_title) / 100
    s["title_similarity"] = round(title_sim, 3)
    desc_sim = (
        fuzz.ratio((a.description or "")[:3000], (b.description or "")[:3000]) / 100
        if a.description and b.description
        else None
    )
    s["description_similarity"] = round(desc_sim, 3) if desc_sim is not None else None
    ca, cb = _cities(db, a), _cities(db, b)
    if ca and cb and not (ca & cb):
        blockers.append("different_location")
    for f in ("seniority", "employment_type", "work_arrangement"):
        va, vb = str(getattr(a, f) or "UNKNOWN"), str(getattr(b, f) or "UNKNOWN")
        if va != "UNKNOWN" and vb != "UNKNOWN" and va != vb and "FLEXIBLE" not in (va, vb):
            blockers.append(f"different_{f}")
    if a.recruitment_batch and b.recruitment_batch and a.recruitment_batch != b.recruitment_batch:
        blockers.append("different_batch")
    if a.first_seen_at and b.first_seen_at and abs(a.first_seen_at - b.first_seen_at) > timedelta(days=120):
        blockers.append("far_apart_in_time")
    if strong:
        score = 0.97
    elif same_company:
        score = 0.55 * title_sim + 0.3 * (desc_sim if desc_sim is not None else title_sim * 0.8) + 0.15
    else:
        score = 0.5 * title_sim * (desc_sim or 0) if desc_sim and desc_sim > 0.9 else 0.0
    if blockers:
        score = min(score, REVIEW - 0.01) if not strong else min(score, AUTO_MERGE - 0.01)
    return PairScore(round(score, 3), s, blockers, strong)


def candidates_for(db: Session, v: JobVacancy, limit: int = 20) -> list[JobVacancy]:
    conds = []
    if v.canonical_url:
        conds.append(JobVacancy.canonical_url == v.canonical_url)
    if v.application_url:
        conds.append(JobVacancy.application_url == v.application_url)
    if v.company_id:
        conds.append(
            (JobVacancy.company_id == v.company_id) & JobVacancy.normalized_title.op("%")(v.normalized_title)
        )
    if not conds:
        return []
    return list(
        db.execute(
            select(JobVacancy)
            .where(JobVacancy.id != v.id, JobVacancy.merged_into_id.is_(None), or_(*conds))
            .limit(limit)
        ).scalars()
    )


def process_new_vacancy(db: Session, v: JobVacancy) -> JobVacancy:
    """Check a new/changed vacancy for duplicates. Returns the canonical vacancy (possibly another one)."""
    best: tuple[PairScore, JobVacancy] | None = None
    for other in candidates_for(db, v):
        ps = score_pair(db, v, other)
        if ps.score >= REVIEW:
            lo, hi = sorted((v.id, other.id))
            existing = db.execute(
                select(DeduplicationCandidate).where(
                    DeduplicationCandidate.vacancy_a_id == lo, DeduplicationCandidate.vacancy_b_id == hi
                )
            ).scalar_one_or_none()
            if existing is None:
                existing = DeduplicationCandidate(
                    vacancy_a_id=lo,
                    vacancy_b_id=hi,
                    score=ps.score,
                    signals={**ps.signals, "blockers": ps.blockers},
                )
                db.add(existing)
                db.flush()
            if best is None or ps.score > best[0].score:
                best = (ps, other)
    if best and best[0].score >= AUTO_MERGE and not best[0].blockers:
        keep = best[1] if best[1].first_seen_at <= v.first_seen_at else v
        dup = v if keep is best[1] else best[1]
        cand = _candidate(db, keep.id, dup.id)
        merge(db, cand, keep_id=keep.id, actor=Actor.SYSTEM, auto=True)
        return keep
    return v


def _candidate(db: Session, a: int, b: int) -> DeduplicationCandidate:
    lo, hi = sorted((a, b))
    c = db.execute(
        select(DeduplicationCandidate).where(
            DeduplicationCandidate.vacancy_a_id == lo, DeduplicationCandidate.vacancy_b_id == hi
        )
    ).scalar_one_or_none()
    if c is None:
        c = DeduplicationCandidate(vacancy_a_id=lo, vacancy_b_id=hi, score=1.0, signals={"manual": True})
        db.add(c)
        db.flush()
    return c


def merge(
    db: Session, cand: DeduplicationCandidate, *, keep_id: int, actor: Actor = Actor.USER, auto: bool = False
) -> JobVacancy:
    if keep_id not in (cand.vacancy_a_id, cand.vacancy_b_id):
        raise ValidationFailed("keep_id must be one of the pair.")
    if cand.status in (DedupStatus.MERGED, DedupStatus.AUTO_MERGED):
        raise ValidationFailed("This pair is already merged.")
    dup_id = cand.vacancy_b_id if keep_id == cand.vacancy_a_id else cand.vacancy_a_id
    keep, dup = db.get(JobVacancy, keep_id), db.get(JobVacancy, dup_id)
    if keep is None or dup is None:
        raise NotFound("Vacancy not found.")
    moved = []
    for link in db.execute(select(JobVacancySource).where(JobVacancySource.vacancy_id == dup.id)).scalars():
        exists = db.execute(
            select(JobVacancySource.id).where(
                JobVacancySource.vacancy_id == keep.id,
                JobVacancySource.raw_document_id == link.raw_document_id,
            )
        ).first()
        if exists:
            continue
        link.vacancy_id = keep.id
        link.is_primary = False
        moved.append(link.id)
    cand.undo_payload = {"dup_id": dup.id, "moved_links": moved, "dup_status": dup.verification_status.value}
    dup.merged_into_id = keep.id
    keep.last_seen_at = max(keep.last_seen_at, dup.last_seen_at)
    keep.first_seen_at = min(keep.first_seen_at, dup.first_seen_at)
    for fld in (
        "salary_min",
        "salary_max",
        "salary_currency",
        "application_deadline",
        "application_url",
        "location_text",
    ):
        if getattr(keep, fld) is None and getattr(dup, fld) is not None:
            setattr(keep, fld, getattr(dup, fld))
    db.add(
        VacancyStatusHistory(
            vacancy_id=dup.id,
            from_status=dup.verification_status,
            to_status=dup.verification_status,
            reason=f"Merged into vacancy {keep.id}",
            rule="dedup_merge",
            actor=actor,
        )
    )
    cand.status = DedupStatus.AUTO_MERGED if auto else DedupStatus.MERGED
    cand.decided_at = utcnow()
    audit(
        db,
        "vacancy.merged",
        actor=actor,
        target_type="vacancy",
        target_id=keep.id,
        details={"dup": dup.id, "auto": auto, "score": cand.score},
    )
    db.flush()
    return keep


def undo_merge(db: Session, cand: DeduplicationCandidate) -> None:
    if cand.status not in (DedupStatus.MERGED, DedupStatus.AUTO_MERGED) or not cand.undo_payload:
        raise ValidationFailed("Nothing to undo for this pair.")
    p = cand.undo_payload
    dup = db.get(JobVacancy, p["dup_id"])
    if dup is None:
        raise NotFound("Vacancy not found.")
    for link_id in p.get("moved_links", []):
        link = db.get(JobVacancySource, link_id)
        if link:
            link.vacancy_id = dup.id
    dup.merged_into_id = None
    db.add(
        VacancyStatusHistory(
            vacancy_id=dup.id,
            from_status=dup.verification_status,
            to_status=dup.verification_status,
            reason="Merge undone",
            rule="dedup_undo",
            actor=Actor.USER,
        )
    )
    cand.status = DedupStatus.UNDONE
    cand.decided_at = utcnow()
    audit(db, "vacancy.merge_undone", target_type="vacancy", target_id=dup.id)
    db.flush()


def reject(db: Session, cand: DeduplicationCandidate) -> None:
    cand.status = DedupStatus.REJECTED
    cand.decided_at = utcnow()
    audit(db, "vacancy.dedup_rejected", target_type="dedup", target_id=cand.id)
