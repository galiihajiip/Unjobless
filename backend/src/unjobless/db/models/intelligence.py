from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from unjobless.domain.enums import (
    Actor,
    DedupStatus,
    EmploymentType,
    FieldOrigin,
    FreshnessState,
    OpportunityClassification,
    PayPeriod,
    Seniority,
    Sentiment,
    SentimentTarget,
    SignalType,
    VerificationStatus,
    WorkArrangement,
)

from .base import Base, Timestamps, enum_col, pk


class Company(Base, Timestamps):
    __tablename__ = "companies"
    __table_args__ = (
        Index(
            "ix_companies_name_trgm",
            "normalized_name",
            postgresql_using="gin",
            postgresql_ops={"normalized_name": "gin_trgm_ops"},
        ),
    )
    id: Mapped[int] = pk()
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(300))
    website_domain: Mapped[str | None] = mapped_column(String(253), index=True)
    industry: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    manually_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    merged_into_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))


class CompanyAlias(Base):
    __tablename__ = "company_aliases"
    __table_args__ = (UniqueConstraint("company_id", "normalized_alias", name="uq_company_alias"),)
    id: Mapped[int] = pk()
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="system")


_SEARCH_EXPR = (
    "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('simple', coalesce(company_name, '')), 'A') || "
    "setweight(to_tsvector('simple', coalesce(location_text, '') || ' ' || coalesce(job_family, '') || ' ' || coalesce(industry, '')), 'B') || "
    "setweight(to_tsvector('simple', coalesce(skills_text, '')), 'B') || "
    "setweight(to_tsvector('simple', left(coalesce(description, ''), 20000)), 'C')"
)


class JobVacancy(Base, Timestamps):
    """Canonical vacancy. Typed columns for every filterable field; long tail in `details`."""

    __tablename__ = "job_vacancies"
    __table_args__ = (
        CheckConstraint("salary_min IS NULL OR salary_min >= 0", name="salary_min_nonneg"),
        CheckConstraint(
            "salary_max IS NULL OR salary_min IS NULL OR salary_max >= salary_min", name="salary_order"
        ),
        CheckConstraint(
            "data_confidence IS NULL OR (data_confidence >= 0 AND data_confidence <= 1)", name="conf_range"
        ),
        CheckConstraint("min_gpa IS NULL OR (min_gpa >= 0 AND min_gpa <= 4.0)", name="gpa_range"),
        CheckConstraint("openings_count IS NULL OR openings_count > 0", name="openings_pos"),
        Index("ix_vacancies_search", "search_vector", postgresql_using="gin"),
        Index(
            "ix_vacancies_title_trgm",
            "normalized_title",
            postgresql_using="gin",
            postgresql_ops={"normalized_title": "gin_trgm_ops"},
        ),
        Index("ix_vacancies_feed", "verification_status", "first_seen_at"),
        Index("ix_vacancies_deadline", "application_deadline"),
        Index("ix_vacancies_company", "company_id"),
        Index("ix_vacancies_filters", "employment_type", "work_arrangement"),
    )
    id: Mapped[int] = pk()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(300), nullable=False)
    alternative_title: Mapped[str | None] = mapped_column(String(300))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    company_name: Mapped[str | None] = mapped_column(String(300))
    classification: Mapped[OpportunityClassification] = mapped_column(
        enum_col(OpportunityClassification), nullable=False, default=OpportunityClassification.DIRECT_VACANCY
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        enum_col(VerificationStatus), nullable=False, default=VerificationStatus.NEW_UNREVIEWED
    )
    freshness: Mapped[FreshnessState] = mapped_column(
        enum_col(FreshnessState), nullable=False, default=FreshnessState.UNKNOWN
    )
    employment_type: Mapped[EmploymentType] = mapped_column(
        enum_col(EmploymentType), nullable=False, default=EmploymentType.UNKNOWN
    )
    seniority: Mapped[Seniority] = mapped_column(
        enum_col(Seniority), nullable=False, default=Seniority.UNKNOWN
    )
    work_arrangement: Mapped[WorkArrangement] = mapped_column(
        enum_col(WorkArrangement), nullable=False, default=WorkArrangement.UNKNOWN
    )
    remote_eligible_countries: Mapped[list[str] | None] = mapped_column(ARRAY(String(2)))
    location_text: Mapped[str | None] = mapped_column(String(300))
    job_family: Mapped[str | None] = mapped_column(String(120))
    industry: Mapped[str | None] = mapped_column(String(120))
    department: Mapped[str | None] = mapped_column(String(200))
    openings_count: Mapped[int | None] = mapped_column(Integer)
    internship_duration_months: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    contract_duration_months: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    recruitment_batch: Mapped[str | None] = mapped_column(String(120))
    application_url: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(Text, index=True)
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    pay_period: Mapped[PayPeriod | None] = mapped_column(enum_col(PayPeriod))
    compensation_type: Mapped[str | None] = mapped_column(String(40))
    is_paid: Mapped[bool | None] = mapped_column(Boolean)
    education_level: Mapped[str | None] = mapped_column(String(40))
    min_semester: Mapped[int | None] = mapped_column(Integer)
    min_gpa: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    experience_years_min: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    application_open_date: Mapped[date | None] = mapped_column(Date)
    application_deadline: Mapped[date | None] = mapped_column(Date)
    deadline_tz_uncertain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    start_date: Mapped[date | None] = mapped_column(Date)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_reason: Mapped[str | None] = mapped_column(Text)
    data_confidence: Mapped[float | None] = mapped_column(Float)
    description: Mapped[str | None] = mapped_column(Text)
    skills_text: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(12))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    field_meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    extraction_warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    merged_into_id: Mapped[int | None] = mapped_column(ForeignKey("job_vacancies.id", ondelete="SET NULL"))
    search_vector: Mapped[Any] = mapped_column(TSVECTOR, Computed(_SEARCH_EXPR, persisted=True))


class JobVacancySource(Base):
    __tablename__ = "job_vacancy_sources"
    __table_args__ = (UniqueConstraint("vacancy_id", "raw_document_id", name="uq_vacancy_source_doc"),)
    id: Mapped[int] = pk()
    vacancy_id: Mapped[int] = mapped_column(
        ForeignKey("job_vacancies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw_document_id: Mapped[int] = mapped_column(
        ForeignKey("raw_source_documents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    raw_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_source_versions.id", ondelete="SET NULL")
    )
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    application_url: Mapped[str | None] = mapped_column(Text)
    source_native_id: Mapped[str | None] = mapped_column(String(300))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class JobRequirement(Base):
    __tablename__ = "job_requirements"
    id: Mapped[int] = pk()
    vacancy_id: Mapped[int] = mapped_column(
        ForeignKey("job_vacancies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[str | None] = mapped_column(String(300))
    origin: Mapped[FieldOrigin] = mapped_column(
        enum_col(FieldOrigin), nullable=False, default=FieldOrigin.EXPLICIT
    )
    evidence_id: Mapped[int | None] = mapped_column(ForeignKey("job_evidence.id", ondelete="SET NULL"))


class JobSkill(Base):
    __tablename__ = "job_skills"
    __table_args__ = (UniqueConstraint("vacancy_id", "normalized_skill", name="uq_job_skill"),)
    id: Mapped[int] = pk()
    vacancy_id: Mapped[int] = mapped_column(
        ForeignKey("job_vacancies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_skill: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    origin: Mapped[FieldOrigin] = mapped_column(
        enum_col(FieldOrigin), nullable=False, default=FieldOrigin.EXPLICIT
    )


class JobBenefit(Base):
    __tablename__ = "job_benefits"
    id: Mapped[int] = pk()
    vacancy_id: Mapped[int] = mapped_column(
        ForeignKey("job_vacancies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="other")
    value: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[FieldOrigin] = mapped_column(
        enum_col(FieldOrigin), nullable=False, default=FieldOrigin.EXPLICIT
    )


class JobLocation(Base):
    __tablename__ = "job_locations"
    id: Mapped[int] = pk()
    vacancy_id: Mapped[int] = mapped_column(
        ForeignKey("job_vacancies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw: Mapped[str] = mapped_column(String(300), nullable=False)
    city: Mapped[str | None] = mapped_column(String(120), index=True)
    region: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(2))
    is_remote: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class JobEvidence(Base):
    __tablename__ = "job_evidence"
    __table_args__ = (
        CheckConstraint("vacancy_id IS NOT NULL OR signal_id IS NOT NULL", name="has_owner"),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="conf_range"),
    )
    id: Mapped[int] = pk()
    vacancy_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_vacancies.id", ondelete="CASCADE"), index=True
    )
    signal_id: Mapped[int | None] = mapped_column(
        ForeignKey("opportunity_signals.id", ondelete="CASCADE"), index=True
    )
    raw_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_source_versions.id", ondelete="SET NULL")
    )
    field_name: Mapped[str] = mapped_column(String(80), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    origin: Mapped[FieldOrigin] = mapped_column(enum_col(FieldOrigin), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)


class VacancyStatusHistory(Base):
    __tablename__ = "vacancy_status_history"
    id: Mapped[int] = pk()
    vacancy_id: Mapped[int] = mapped_column(
        ForeignKey("job_vacancies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[VerificationStatus | None] = mapped_column(enum_col(VerificationStatus))
    to_status: Mapped[VerificationStatus] = mapped_column(enum_col(VerificationStatus), nullable=False)
    freshness: Mapped[FreshnessState | None] = mapped_column(enum_col(FreshnessState))
    reason: Mapped[str | None] = mapped_column(Text)
    rule: Mapped[str | None] = mapped_column(String(80))
    actor: Mapped[Actor] = mapped_column(enum_col(Actor), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OpportunitySignal(Base, Timestamps):
    __tablename__ = "opportunity_signals"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="conf_range"),
        Index("ix_signals_feed", "status", "created_at"),
        Index("ix_signals_search", "search_vector", postgresql_using="gin"),
    )
    id: Mapped[int] = pk()
    raw_version_id: Mapped[int] = mapped_column(
        ForeignKey("raw_source_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    primary_classification: Mapped[OpportunityClassification] = mapped_column(
        enum_col(OpportunityClassification), nullable=False
    )
    secondary_classifications: Mapped[list[str]] = mapped_column(
        ARRAY(String(40)), nullable=False, default=list
    )
    signal_type: Mapped[SignalType] = mapped_column(enum_col(SignalType), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    verification_recommendation: Mapped[VerificationStatus] = mapped_column(
        enum_col(VerificationStatus), nullable=False
    )
    status: Mapped[VerificationStatus] = mapped_column(
        enum_col(VerificationStatus), nullable=False, default=VerificationStatus.POTENTIAL_LEAD
    )
    reason: Mapped[str | None] = mapped_column(Text)
    ambiguity_flags: Mapped[list[str]] = mapped_column(ARRAY(String(60)), nullable=False, default=list)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )
    company_text: Mapped[str | None] = mapped_column(String(300))
    role_text: Mapped[str | None] = mapped_column(String(300))
    location_text: Mapped[str | None] = mapped_column(String(300))
    application_url: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(12))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    promoted_vacancy_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_vacancies.id", ondelete="SET NULL")
    )
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', coalesce(role_text,'') || ' ' || coalesce(company_text,'') || ' ' || coalesce(summary,''))",
            persisted=True,
        ),
    )


class SignalEntity(Base):
    __tablename__ = "signal_entities"
    id: Mapped[int] = pk()
    signal_id: Mapped[int] = mapped_column(
        ForeignKey("opportunity_signals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[FieldOrigin] = mapped_column(enum_col(FieldOrigin), nullable=False)
    evidence_excerpt: Mapped[str | None] = mapped_column(Text)


class SentimentAnalysis(Base):
    __tablename__ = "sentiment_analyses"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="conf_range"),
        Index("ix_sentiment_company_time", "company_id", "observed_at"),
    )
    id: Mapped[int] = pk()
    raw_version_id: Mapped[int] = mapped_column(
        ForeignKey("raw_source_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    target: Mapped[SentimentTarget] = mapped_column(enum_col(SentimentTarget), nullable=False)
    polarity: Mapped[Sentiment] = mapped_column(enum_col(Sentiment), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    sarcasm_uncertain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_first_party: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    language: Mapped[str | None] = mapped_column(String(12))
    evidence_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(String(40), nullable=False, default="rules")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TopicObservation(Base):
    __tablename__ = "topic_observations"
    __table_args__ = (
        UniqueConstraint("raw_version_id", "topic", name="uq_topic_obs"),
        Index("ix_topic_time", "topic", "observed_at"),
    )
    id: Mapped[int] = pk()
    raw_version_id: Mapped[int] = mapped_column(
        ForeignKey("raw_source_versions.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    topic: Mapped[str] = mapped_column(String(60), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_excerpt: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrendObservation(Base):
    """Materialised aggregate, reproducible from topic/sentiment/vacancy rows."""

    __tablename__ = "trend_observations"
    __table_args__ = (
        UniqueConstraint("metric", "dimension", "company_id", "window_start", "window_end", name="uq_trend"),
    )
    id: Mapped[int] = pk()
    metric: Mapped[str] = mapped_column(String(60), nullable=False)
    dimension: Mapped[str] = mapped_column(String(80), nullable=False, default="all")
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    unique_sources: Mapped[int] = mapped_column(Integer, nullable=False)
    unique_companies: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeduplicationCandidate(Base, Timestamps):
    __tablename__ = "deduplication_candidates"
    __table_args__ = (
        UniqueConstraint("vacancy_a_id", "vacancy_b_id", name="uq_dedup_pair"),
        CheckConstraint("vacancy_a_id < vacancy_b_id", name="ordered_pair"),
    )
    id: Mapped[int] = pk()
    vacancy_a_id: Mapped[int] = mapped_column(
        ForeignKey("job_vacancies.id", ondelete="CASCADE"), nullable=False
    )
    vacancy_b_id: Mapped[int] = mapped_column(
        ForeignKey("job_vacancies.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    signals: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[DedupStatus] = mapped_column(
        enum_col(DedupStatus), nullable=False, default=DedupStatus.PENDING
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    undo_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
