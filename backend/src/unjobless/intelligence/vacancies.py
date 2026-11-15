"""Canonical vacancy creation/update from a validated extraction, with provenance and evidence."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from unjobless.ai.task_schemas import JobExtraction
from unjobless.core.time import utcnow
from unjobless.db.models import (
    JobBenefit,
    JobEvidence,
    JobLocation,
    JobRequirement,
    JobSkill,
    JobVacancy,
    JobVacancySource,
    RawSourceDocument,
    RawSourceVersion,
    Source,
    VacancyStatusHistory,
)
from unjobless.domain.enums import (
    Actor,
    EmploymentType,
    FieldOrigin,
    OpportunityClassification,
    PayPeriod,
    Seniority,
    WorkArrangement,
)
from unjobless.domain.enums import VerificationStatus as V
from unjobless.fetch.urls import canonicalize_url
from unjobless.intelligence import lifecycle
from unjobless.intelligence import normalize as N
from unjobless.intelligence.companies import resolve_company
from unjobless.intelligence.extraction import data_confidence
from unjobless.intelligence.text import find_span, normalize_key

SCALAR_FIELDS = {
    "alternative_title",
    "department",
    "job_family",
    "industry",
    "recruitment_batch",
    "education_level",
    "openings_count",
    "min_semester",
    "experience_years_min",
    "min_gpa",
    "internship_duration_months",
    "contract_duration_months",
    "salary_currency",
    "is_paid",
}
DETAIL_FIELDS = [
    "responsibilities",
    "deliverables",
    "selection_stages",
    "application_documents",
    "working_hours",
    "conversion_info",
    "reporting_line",
    "majors",
    "tools",
    "certifications",
    "legal_requirements",
    "soft_skills",
    "language_requirements",
    "application_email",
    "portfolio_required",
]


def _d(v: Any) -> Decimal | None:
    return Decimal(str(v)) if v is not None else None


def _date(v: str | None) -> date | None:
    return N.parse_iso_date(v)


def apply_extraction(
    db: Session,
    v: JobVacancy,
    x: JobExtraction,
    *,
    version: RawSourceVersion | None,
    source_text: str,
    origin_override: FieldOrigin | None = None,
) -> None:
    """Write typed columns + child tables + evidence from an extraction. Replaces previous derived children."""
    v.title = (x.title or v.title or "Untitled opportunity")[:300]
    v.normalized_title = normalize_key(v.title)[:300]
    if x.company:
        comp = resolve_company(db, x.company, website=x.application_url)
        v.company_id = comp.id if comp else None
        v.company_name = x.company[:300]
    v.employment_type = EmploymentType(x.employment_type)
    v.work_arrangement = WorkArrangement(x.work_arrangement)
    v.seniority = Seniority(x.seniority)
    v.pay_period = PayPeriod(x.pay_period) if x.pay_period != "UNKNOWN" or x.salary_min is not None else None
    for f in SCALAR_FIELDS:
        val = getattr(x, f)
        if f in ("min_gpa", "experience_years_min", "internship_duration_months", "contract_duration_months"):
            val = _d(val)
        setattr(v, f, val)
    v.salary_min, v.salary_max = _d(x.salary_min), _d(x.salary_max)
    if v.salary_min is not None and v.salary_max is not None and v.salary_max < v.salary_min:
        v.salary_min, v.salary_max = v.salary_max, v.salary_min
    v.application_deadline = _date(x.application_deadline)
    v.application_open_date = _date(x.application_open_date)
    v.start_date = _date(x.start_date)
    v.application_url = x.application_url
    v.remote_eligible_countries = [c[:2].upper() for c in x.remote_eligible_countries if c and len(c) >= 2][
        :20
    ] or None
    v.location_text = ", ".join(x.locations)[:300] or None
    v.language = x.language
    v.skills_text = " ".join(x.required_skills + x.preferred_skills + x.tools)[:5000] or None
    v.details = {f: getattr(x, f) for f in DETAIL_FIELDS if getattr(x, f) not in (None, [])}
    v.extraction_warnings = list(x.warnings)
    v.data_confidence = data_confidence(x)
    # per-field meta
    meta: dict[str, Any] = {}
    for e in x.evidence:
        key = e.field if e.field != "salary" else "salary_min"
        cur = meta.get(key)
        if cur is None or e.confidence > cur["confidence"]:
            meta[key] = {
                "origin": (origin_override.value if origin_override else e.origin),
                "confidence": e.confidence,
            }
    meta["evidenced_fields"] = sorted(
        {e.field if e.field != "salary" else "salary_min" for e in x.evidence if e.origin == "EXPLICIT"}
    )
    v.field_meta = meta
    db.flush()

    # children (replace)
    for model in (JobSkill, JobRequirement, JobBenefit, JobLocation):
        db.execute(delete(model).where(model.vacancy_id == v.id))
    db.execute(
        delete(JobEvidence).where(
            JobEvidence.vacancy_id == v.id, JobEvidence.raw_version_id == (version.id if version else None)
        )
    )
    seen = set()
    for name, req in [(s, True) for s in x.required_skills] + [
        (s, False) for s in x.preferred_skills + x.tools
    ]:
        key = N.normalized_skill_key(name)
        if key and key not in seen:
            seen.add(key)
            db.add(
                JobSkill(
                    vacancy_id=v.id,
                    skill=N.canonical_skill(name)[:200],
                    normalized_skill=key[:200],
                    required=req,
                )
            )
    for kind, values in (
        ("major", x.majors),
        ("language", x.language_requirements),
        ("certification", x.certifications),
        ("legal", x.legal_requirements),
        ("soft_skill", x.soft_skills),
        ("document", x.application_documents),
    ):
        for val in values:
            db.add(
                JobRequirement(
                    vacancy_id=v.id, kind=kind, value=val[:2000], normalized_value=normalize_key(val)[:300]
                )
            )
    if x.education_level:
        db.add(JobRequirement(vacancy_id=v.id, kind="education", value=x.education_level))
    if x.portfolio_required:
        db.add(JobRequirement(vacancy_id=v.id, kind="portfolio", value="Portfolio required"))
    for b in x.benefits:
        db.add(JobBenefit(vacancy_id=v.id, value=b[:2000], category=_benefit_category(b)))
    for raw in x.locations[:10]:
        loc = N.normalize_location(raw)
        db.add(
            JobLocation(
                vacancy_id=v.id,
                raw=raw[:300],
                city=loc.city,
                region=loc.region,
                country=loc.country,
                is_remote=loc.is_remote,
            )
        )
    if x.work_arrangement == "REMOTE" and not x.locations:
        db.add(JobLocation(vacancy_id=v.id, raw="Remote", is_remote=True))
    for e in x.evidence:
        span = find_span(source_text, e.excerpt) if not e.excerpt.startswith("[") else None
        db.add(
            JobEvidence(
                vacancy_id=v.id,
                raw_version_id=version.id if version else None,
                field_name=e.field[:80],
                excerpt=e.excerpt[:2000],
                start_offset=span[0] if span else None,
                end_offset=span[1] if span else None,
                origin=FieldOrigin(origin_override.value if origin_override else e.origin),
                confidence=e.confidence,
            )
        )
    db.flush()


def _benefit_category(text: str) -> str:
    t = text.lower()
    for cat, words in {
        "insurance": ("insurance", "asuransi", "bpjs", "health"),
        "allowance": ("allowance", "uang saku", "tunjangan", "stipend"),
        "meal_transport": ("meal", "makan", "transport", "transportasi"),
        "learning": ("training", "mentor", "learning", "pelatihan", "sertifikat", "certificate"),
        "equipment": ("laptop", "equipment", "device"),
        "flexibility": ("remote", "flexible", "wfh", "hybrid"),
    }.items():
        if any(w in t for w in words):
            return cat
    return "other"


def create_vacancy(
    db: Session,
    *,
    x: JobExtraction,
    source: Source,
    document: RawSourceDocument,
    version: RawSourceVersion,
    source_text: str,
    status: V,
    classification: OpportunityClassification = OpportunityClassification.DIRECT_VACANCY,
    actor: Actor = Actor.SYSTEM,
    reason: str,
) -> JobVacancy:
    now = utcnow()
    v = JobVacancy(
        title=(x.title or "Untitled opportunity")[:300],
        normalized_title=normalize_key(x.title or "untitled")[:300],
        classification=classification,
        verification_status=status,
        canonical_url=document.canonical_url,
        first_seen_at=document.first_collected_at or now,
        last_seen_at=now,
        last_checked_at=now,
        last_verified_at=now if status == V.VERIFIED_OPEN else None,
        source_published_at=version.source_published_at,
        description=source_text[:200_000],
    )
    db.add(v)
    db.flush()
    apply_extraction(db, v, x, version=version, source_text=source_text)
    link_source(db, v, source, document, version, primary=True, application_url=x.application_url)
    db.add(
        VacancyStatusHistory(
            vacancy_id=v.id, from_status=None, to_status=status, reason=reason, actor=actor, rule="created"
        )
    )
    lifecycle.apply_deadline_rule(db, v)
    v.freshness = lifecycle.compute_freshness(v)
    return v


def link_source(
    db: Session,
    v: JobVacancy,
    source: Source,
    document: RawSourceDocument,
    version: RawSourceVersion | None,
    *,
    primary: bool = False,
    application_url: str | None = None,
) -> JobVacancySource:
    link = db.execute(
        select(JobVacancySource).where(
            JobVacancySource.vacancy_id == v.id, JobVacancySource.raw_document_id == document.id
        )
    ).scalar_one_or_none()
    now = utcnow()
    if link is None:
        link = JobVacancySource(
            vacancy_id=v.id,
            raw_document_id=document.id,
            source_id=source.id,
            source_url=document.original_url or document.canonical_url,
            source_native_id=document.source_native_id,
            application_url=application_url,
            is_primary=primary,
            raw_version_id=version.id if version else None,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(link)
    else:
        link.last_seen_at = now
        if version:
            link.raw_version_id = version.id
        if application_url:
            link.application_url = application_url
    db.flush()
    return link


def vacancy_for_document(db: Session, document_id: int) -> JobVacancy | None:
    return (
        db.execute(
            select(JobVacancy)
            .join(JobVacancySource, JobVacancySource.vacancy_id == JobVacancy.id)
            .where(JobVacancySource.raw_document_id == document_id)
        )
        .scalars()
        .first()
    )


def canonical_vacancy(db: Session, v: JobVacancy) -> JobVacancy:
    while v.merged_into_id:
        nxt = db.get(JobVacancy, v.merged_into_id)
        if nxt is None:
            break
        v = nxt
    return v


def canonical_app_url(url: str | None) -> str | None:
    return canonicalize_url(url) if url and url.startswith("http") else None
