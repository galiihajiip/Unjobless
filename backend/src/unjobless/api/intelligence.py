"""Career Intelligence: evidence-linked company insights and recruitment/topic trends.

Every number is computed from stored rows and returned with sample size, time window and links to
the underlying records. Opinions are labelled as such; first-party and third-party content are kept
apart; small samples are flagged.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from unjobless.api.deps import DB
from unjobless.core.errors import NotFound
from unjobless.core.time import utcnow
from unjobless.db.models import (
    Company,
    JobSkill,
    JobVacancy,
    OpportunitySignal,
    RawSourceDocument,
    RawSourceVersion,
    SentimentAnalysis,
    Source,
    TopicObservation,
    TrendObservation,
)
from unjobless.intelligence.sentiment import MIN_SAMPLE, describe_change, refresh_trends

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


def _window(days: int) -> tuple[Any, Any]:
    end = utcnow()
    return end - timedelta(days=days), end


@router.get("/summary")
def summary(db: DB, days: int = Query(90, ge=7, le=730)) -> dict[str, Any]:
    start, end = _window(days)
    topics = db.execute(
        select(
            TopicObservation.topic,
            func.count(),
            func.count(func.distinct(TopicObservation.source_id)),
            func.count(func.distinct(TopicObservation.company_id)),
        )
        .where(TopicObservation.observed_at >= start)
        .group_by(TopicObservation.topic)
        .order_by(func.count().desc())
    ).all()
    sent = db.execute(
        select(SentimentAnalysis.target, SentimentAnalysis.polarity, func.count())
        .where(SentimentAnalysis.observed_at >= start, SentimentAnalysis.is_first_party.is_(False))
        .group_by(SentimentAnalysis.target, SentimentAnalysis.polarity)
    ).all()
    by_target: dict[str, dict[str, int]] = {}
    for t, p, c in sent:
        by_target.setdefault(t.value, {})[p.value] = c
    skills = db.execute(
        select(JobSkill.skill, func.count(func.distinct(JobSkill.vacancy_id)))
        .join(JobVacancy, JobVacancy.id == JobSkill.vacancy_id)
        .where(JobVacancy.first_seen_at >= start, JobVacancy.merged_into_id.is_(None))
        .group_by(JobSkill.skill)
        .order_by(func.count().desc())
        .limit(20)
    ).all()
    n_vac = db.execute(
        select(func.count())
        .select_from(JobVacancy)
        .where(JobVacancy.first_seen_at >= start, JobVacancy.merged_into_id.is_(None))
    ).scalar_one()
    top_companies = db.execute(
        select(Company.id, Company.name, func.count(JobVacancy.id))
        .join(JobVacancy, JobVacancy.company_id == Company.id)
        .where(JobVacancy.first_seen_at >= start, JobVacancy.merged_into_id.is_(None))
        .group_by(Company.id)
        .order_by(func.count(JobVacancy.id).desc())
        .limit(10)
    ).all()
    return {
        "window": {"start": start.date().isoformat(), "end": end.date().isoformat(), "days": days},
        "min_sample": MIN_SAMPLE,
        "topics": [
            {
                "topic": t,
                "count": c,
                "unique_sources": us,
                "unique_companies": uc,
                "low_sample": c < MIN_SAMPLE,
            }
            for t, c, us, uc in topics
        ],
        "sentiment_by_target": [
            {"target": t, "counts": v, "n": sum(v.values()), "low_sample": sum(v.values()) < MIN_SAMPLE}
            for t, v in sorted(by_target.items())
        ],
        "common_skills": [
            {"skill": s, "vacancies": n, "share": round(n / n_vac, 3) if n_vac else None} for s, n in skills
        ],
        "vacancies_in_window": n_vac,
        "top_hiring_companies": [{"id": i, "name": n, "vacancies": c} for i, n, c in top_companies],
        "caveat": "Public posts observed by your enabled sources and imports only. Not a representative sample of the market.",
    }


@router.get("/trends")
def trends(
    db: DB,
    metric: str = "topic_mentions",
    dimension: str | None = None,
    weeks: int = Query(12, ge=4, le=52),
    refresh: bool = False,
) -> dict[str, Any]:
    if refresh:
        refresh_trends(db, weeks=weeks)
    start = date.today() - timedelta(weeks=weeks)
    q = select(TrendObservation).where(
        TrendObservation.metric == metric, TrendObservation.window_start >= start
    )
    if dimension:
        q = q.where(TrendObservation.dimension == dimension)
    rows = db.execute(q.order_by(TrendObservation.window_start)).scalars().all()
    series: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        series.setdefault(r.dimension, []).append(
            {
                "week": r.window_start.isoformat(),
                "count": r.count,
                "unique_sources": r.unique_sources,
                "unique_companies": r.unique_companies,
            }
        )
    return {
        "metric": metric,
        "weeks": weeks,
        "series": [
            {
                "dimension": d,
                "points": pts,
                "change": describe_change([p["count"] for p in pts]),
                "total": sum(p["count"] for p in pts),
            }
            for d, pts in series.items()
        ],
        "note": "Changes are only described as increases/decreases when both halves of the window have enough observations.",
    }


@router.get("/companies/{company_id}")
def company(company_id: int, db: DB, days: int = Query(365, ge=30, le=1825)) -> dict[str, Any]:
    c = db.get(Company, company_id)
    if c is None:
        raise NotFound("Company not found.")
    start, _end = _window(days)
    vacs = (
        db.execute(
            select(JobVacancy)
            .where(JobVacancy.company_id == c.id, JobVacancy.merged_into_id.is_(None))
            .order_by(JobVacancy.first_seen_at.desc())
        )
        .scalars()
        .all()
    )
    by_month: dict[str, int] = {}
    for v in vacs:
        by_month[v.first_seen_at.strftime("%Y-%m")] = by_month.get(v.first_seen_at.strftime("%Y-%m"), 0) + 1
    intern_months = sorted(
        {v.first_seen_at.strftime("%m") for v in vacs if v.employment_type.value == "INTERNSHIP"}
    )
    sents = db.execute(
        select(SentimentAnalysis, RawSourceVersion, RawSourceDocument, Source)
        .join(RawSourceVersion, RawSourceVersion.id == SentimentAnalysis.raw_version_id)
        .join(RawSourceDocument, RawSourceDocument.id == RawSourceVersion.document_id)
        .join(Source, Source.id == RawSourceDocument.source_id)
        .where(SentimentAnalysis.company_id == c.id, SentimentAnalysis.observed_at >= start)
        .order_by(SentimentAnalysis.observed_at.desc())
    ).all()
    agg: dict[str, dict[str, int]] = {}
    for s, *_ in sents:
        if not s.is_first_party:
            agg.setdefault(s.target.value, {}).setdefault(s.polarity.value, 0)
            agg[s.target.value][s.polarity.value] += 1
    skills = db.execute(
        select(JobSkill.skill, func.count())
        .join(JobVacancy, JobVacancy.id == JobSkill.vacancy_id)
        .where(JobVacancy.company_id == c.id)
        .group_by(JobSkill.skill)
        .order_by(func.count().desc())
        .limit(15)
    ).all()
    signals = db.execute(
        select(OpportunitySignal)
        .where(OpportunitySignal.company_id == c.id)
        .order_by(OpportunitySignal.observed_at.desc())
        .limit(20)
    ).scalars()
    from unjobless.db.models import JobVacancySource

    sources = {s.id for *_x, s in sents} | set(
        db.execute(
            select(func.distinct(JobVacancySource.source_id))
            .join(JobVacancy, JobVacancy.id == JobVacancySource.vacancy_id)
            .where(JobVacancy.company_id == c.id)
        ).scalars()
    )
    third_party_n = sum(sum(v.values()) for v in agg.values())
    return {
        "company": {
            "id": c.id,
            "name": c.name,
            "website_domain": c.website_domain,
            "industry": c.industry,
            "verified": c.manually_verified,
        },
        "window_days": days,
        "vacancy_activity": {
            "total": len(vacs),
            "by_month": dict(sorted(by_month.items())),
            "internship_months_observed": intern_months,
            "recurring_internships": len(intern_months) >= 2
            and len({v.first_seen_at.year for v in vacs if v.employment_type.value == "INTERNSHIP"}) >= 2,
            "recent": [
                {
                    "id": v.id,
                    "title": v.title,
                    "status": v.verification_status.value,
                    "first_seen_at": v.first_seen_at.isoformat(),
                }
                for v in vacs[:15]
            ],
        },
        "common_skills": [{"skill": s, "count": n} for s, n in skills],
        "public_sentiment": {
            "label": "Sampled public discussions (third-party opinions, not facts about the company).",
            "n": third_party_n,
            "low_sample": third_party_n < MIN_SAMPLE,
            "by_target": agg,
            "observations": [
                {
                    "target": s.target.value,
                    "polarity": s.polarity.value,
                    "confidence": s.confidence,
                    "sarcasm_uncertain": s.sarcasm_uncertain,
                    "first_party": s.is_first_party,
                    "excerpt": s.evidence_excerpt,
                    "observed_at": s.observed_at.isoformat(),
                    "source": src.name,
                    "url": doc.original_url,
                    "raw_version_id": rv.id,
                }
                for s, rv, doc, src in sents[:30]
            ],
        },
        "signals": [
            {
                "id": s.id,
                "classification": s.primary_classification.value,
                "status": s.status.value,
                "summary": (s.summary or "")[:200],
                "observed_at": s.observed_at.isoformat(),
            }
            for s in signals
        ],
        "source_count": len(sources),
    }
