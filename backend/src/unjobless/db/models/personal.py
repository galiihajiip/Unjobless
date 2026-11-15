from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from unjobless.domain.enums import (
    Actor,
    AITaskStatus,
    ApplicationStatus,
    ProfileVersionStatus,
    SavedState,
)

from .base import Base, Timestamps, enum_col, pk

# ---------------------------------------------------------------- profile


class ResumeDocument(Base):
    """Original uploaded CV; immutable."""

    __tablename__ = "resume_documents"
    id: Mapped[int] = pk()
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime: Mapped[str] = mapped_column(String(100), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    blob_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    label: Mapped[str | None] = mapped_column(String(120))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResumeExtraction(Base):
    __tablename__ = "resume_extractions"
    id: Mapped[int] = pk()
    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resume_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sections: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    method: Mapped[str] = mapped_column(String(40), nullable=False)
    ai_task_run_id: Mapped[int | None] = mapped_column(ForeignKey("ai_task_runs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CandidateProfile(Base, Timestamps):
    __tablename__ = "candidate_profiles"
    __table_args__ = (CheckConstraint("singleton = 1", name="single_profile"),)
    id: Mapped[int] = pk()
    singleton: Mapped[int] = mapped_column(Integer, nullable=False, default=1, unique=True)
    active_version_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "candidate_profile_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_profile_active_version",
        )
    )


class CandidateProfileVersion(Base):
    __tablename__ = "candidate_profile_versions"
    __table_args__ = (UniqueConstraint("profile_id", "version_no", name="uq_profile_version_no"),)
    id: Mapped[int] = pk()
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ProfileVersionStatus] = mapped_column(enum_col(ProfileVersionStatus), nullable=False)
    source_resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("resume_documents.id", ondelete="SET NULL")
    )
    extraction_id: Mapped[int | None] = mapped_column(
        ForeignKey("resume_extractions.id", ondelete="SET NULL")
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CandidateSkill(Base):
    """Denormalised skill index of the active confirmed profile (rebuilt on confirm) for matching queries."""

    __tablename__ = "candidate_skills"
    __table_args__ = (UniqueConstraint("profile_version_id", "normalized_skill", name="uq_candidate_skill"),)
    id: Mapped[int] = pk()
    profile_version_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_profile_versions.id", ondelete="CASCADE"), nullable=False
    )
    skill: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_skill: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    evidence_refs: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class CareerPreferences(Base, Timestamps):
    __tablename__ = "career_preferences"
    __table_args__ = (CheckConstraint("singleton = 1", name="single_prefs"),)
    id: Mapped[int] = pk()
    singleton: Mapped[int] = mapped_column(Integer, nullable=False, default=1, unique=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


# ---------------------------------------------------------------- decisioning


class MatchAnalysis(Base):
    __tablename__ = "match_analyses"
    __table_args__ = (
        UniqueConstraint(
            "vacancy_id", "profile_version_id", "preferences_hash", "algorithm_version", name="uq_match"
        ),
        CheckConstraint(
            "candidate_fit_score IS NULL OR candidate_fit_score BETWEEN 0 AND 1", name="cfit_range"
        ),
        CheckConstraint(
            "preference_fit_score IS NULL OR preference_fit_score BETWEEN 0 AND 1", name="pfit_range"
        ),
        CheckConstraint("data_confidence_score BETWEEN 0 AND 1", name="dconf_range"),
        Index("ix_match_vacancy_current", "vacancy_id", "is_current"),
    )
    id: Mapped[int] = pk()
    vacancy_id: Mapped[int] = mapped_column(
        ForeignKey("job_vacancies.id", ondelete="CASCADE"), nullable=False
    )
    profile_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidate_profile_versions.id", ondelete="CASCADE")
    )
    preferences_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(20), nullable=False)
    candidate_fit_score: Mapped[float | None] = mapped_column(Float)
    preference_fit_score: Mapped[float | None] = mapped_column(Float)
    data_confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    overall_score: Mapped[float | None] = mapped_column(Float)
    eligible: Mapped[bool | None] = mapped_column()
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_current: Mapped[bool] = mapped_column(nullable=False, default=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ComparisonWeights(Base, Timestamps):
    __tablename__ = "comparison_weights"
    id: Mapped[int] = pk()
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    weights: Mapped[dict[str, float]] = mapped_column(JSONB, nullable=False)


class JobComparison(Base):
    __tablename__ = "job_comparisons"
    id: Mapped[int] = pk()
    weights: Mapped[dict[str, float]] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    profile_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidate_profile_versions.id", ondelete="SET NULL")
    )
    algorithm_version: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobComparisonItem(Base):
    """Hard maximum of two: position ∈ {1,2}, unique per comparison, distinct vacancies."""

    __tablename__ = "job_comparison_items"
    __table_args__ = (
        CheckConstraint("position IN (1, 2)", name="max_two"),
        UniqueConstraint("comparison_id", "position", name="uq_cmp_position"),
        UniqueConstraint("comparison_id", "vacancy_id", name="uq_cmp_vacancy"),
    )
    id: Mapped[int] = pk()
    comparison_id: Mapped[int] = mapped_column(
        ForeignKey("job_comparisons.id", ondelete="CASCADE"), nullable=False
    )
    vacancy_id: Mapped[int] = mapped_column(
        ForeignKey("job_vacancies.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class SavedOpportunity(Base, Timestamps):
    __tablename__ = "saved_opportunities"
    __table_args__ = (
        CheckConstraint("(vacancy_id IS NOT NULL) <> (signal_id IS NOT NULL)", name="one_target"),
        Index("uq_saved_vacancy", "vacancy_id", unique=True, postgresql_where=text("vacancy_id IS NOT NULL")),
        Index("uq_saved_signal", "signal_id", unique=True, postgresql_where=text("signal_id IS NOT NULL")),
    )
    id: Mapped[int] = pk()
    vacancy_id: Mapped[int | None] = mapped_column(ForeignKey("job_vacancies.id", ondelete="CASCADE"))
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("opportunity_signals.id", ondelete="CASCADE"))
    state: Mapped[SavedState] = mapped_column(enum_col(SavedState), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)


class TailoredResume(Base):
    """Immutable tailored output; never mutates the master profile."""

    __tablename__ = "tailored_resumes"
    id: Mapped[int] = pk()
    vacancy_id: Mapped[int] = mapped_column(
        ForeignKey("job_vacancies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profile_version_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_profile_versions.id", ondelete="RESTRICT"), nullable=False
    )
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("tailored_resumes.id", ondelete="SET NULL"))
    language: Mapped[str] = mapped_column(String(5), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    generation_settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    ai_task_run_id: Mapped[int | None] = mapped_column(ForeignKey("ai_task_runs.id", ondelete="SET NULL"))
    finalized: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CoverLetter(Base):
    __tablename__ = "cover_letters"
    id: Mapped[int] = pk()
    vacancy_id: Mapped[int] = mapped_column(
        ForeignKey("job_vacancies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profile_version_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_profile_versions.id", ondelete="RESTRICT"), nullable=False
    )
    tailored_resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("tailored_resumes.id", ondelete="SET NULL")
    )
    language: Mapped[str] = mapped_column(String(5), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    claims: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    ai_task_run_id: Mapped[int | None] = mapped_column(ForeignKey("ai_task_runs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExportFile(Base):
    __tablename__ = "export_files"
    id: Mapped[int] = pk()
    tailored_resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("tailored_resumes.id", ondelete="CASCADE")
    )
    cover_letter_id: Mapped[int | None] = mapped_column(ForeignKey("cover_letters.id", ondelete="CASCADE"))
    profile_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidate_profile_versions.id", ondelete="SET NULL")
    )
    vacancy_id: Mapped[int | None] = mapped_column(ForeignKey("job_vacancies.id", ondelete="SET NULL"))
    format: Mapped[str] = mapped_column(String(8), nullable=False)
    template: Mapped[str] = mapped_column(String(40), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    blob_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApplicationRecord(Base, Timestamps):
    __tablename__ = "application_records"
    __table_args__ = (UniqueConstraint("vacancy_id", name="uq_application_vacancy"),)
    id: Mapped[int] = pk()
    vacancy_id: Mapped[int] = mapped_column(
        ForeignKey("job_vacancies.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ApplicationStatus] = mapped_column(enum_col(ApplicationStatus), nullable=False, index=True)
    applied_at: Mapped[date | None] = mapped_column(Date)
    follow_up_at: Mapped[date | None] = mapped_column(Date)
    deadline: Mapped[date | None] = mapped_column(Date)
    tailored_resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("tailored_resumes.id", ondelete="SET NULL")
    )
    cover_letter_id: Mapped[int | None] = mapped_column(ForeignKey("cover_letters.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    contact_notes: Mapped[str | None] = mapped_column(Text)


class ApplicationStatusHistory(Base):
    __tablename__ = "application_status_history"
    id: Mapped[int] = pk()
    application_id: Mapped[int] = mapped_column(
        ForeignKey("application_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[ApplicationStatus | None] = mapped_column(enum_col(ApplicationStatus))
    to_status: Mapped[ApplicationStatus] = mapped_column(enum_col(ApplicationStatus), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[Actor] = mapped_column(enum_col(Actor), nullable=False, default=Actor.USER)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------- AI


class AIProviderConfig(Base, Timestamps):
    __tablename__ = "ai_provider_configs"
    __table_args__ = (Index("uq_ai_default", "is_default", unique=True, postgresql_where=text("is_default")),)
    id: Mapped[int] = pk()
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text)
    encrypted_api_key: Mapped[bytes | None] = mapped_column(LargeBinary)
    key_fingerprint: Mapped[str | None] = mapped_column(String(64))
    key_hint: Mapped[str | None] = mapped_column(String(16))
    default_model: Mapped[str | None] = mapped_column(String(120))
    is_default: Mapped[bool] = mapped_column(nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    allow_as_fallback: Mapped[bool] = mapped_column(nullable=False, default=False)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AIModelConfig(Base, Timestamps):
    __tablename__ = "ai_model_configs"
    __table_args__ = (UniqueConstraint("provider_id", "model", name="uq_ai_model"),)
    id: Mapped[int] = pk()
    provider_id: Mapped[int] = mapped_column(
        ForeignKey("ai_provider_configs.id", ondelete="CASCADE"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    input_price_per_mtok: Mapped[float | None] = mapped_column(Float)
    output_price_per_mtok: Mapped[float | None] = mapped_column(Float)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer)


class AIPromptVersion(Base):
    __tablename__ = "ai_prompt_versions"
    __table_args__ = (UniqueConstraint("task", "version", name="uq_prompt_version"),)
    id: Mapped[int] = pk()
    task: Mapped[str] = mapped_column(String(60), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    template_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AITaskRun(Base):
    __tablename__ = "ai_task_runs"
    id: Mapped[int] = pk()
    task: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    status: Mapped[AITaskStatus] = mapped_column(enum_col(AITaskStatus), nullable=False)
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("ai_provider_configs.id", ondelete="SET NULL"))
    provider_kind: Mapped[str | None] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    input_ref: Mapped[str | None] = mapped_column(String(120))
    input_hash: Mapped[str | None] = mapped_column(String(64))
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AIUsageEvent(Base):
    __tablename__ = "ai_usage_events"
    id: Mapped[int] = pk()
    task_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_task_runs.id", ondelete="SET NULL"), index=True
    )
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("ai_provider_configs.id", ondelete="SET NULL"))
    model: Mapped[str | None] = mapped_column(String(120))
    task: Mapped[str] = mapped_column(String(60), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_estimate: Mapped[float | None] = mapped_column(Float)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class BackupRecord(Base):
    __tablename__ = "backup_records"
    id: Mapped[int] = pk()
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    actor: Mapped[Actor] = mapped_column(enum_col(Actor), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
