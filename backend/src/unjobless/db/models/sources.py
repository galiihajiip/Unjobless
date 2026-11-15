from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
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
    CollectionMethod,
    PolicyStatus,
    RunItemOutcome,
    RunStatus,
    RunTrigger,
    SourceCategory,
    SourceHealth,
    SourceState,
)

from .base import Base, Timestamps, enum_col, pk


class EncryptedSecret(Base, Timestamps):
    """Generic encrypted secret (connector credentials). Ciphertext only; never returned to clients."""

    __tablename__ = "encrypted_secrets"
    id: Mapped[int] = pk()
    purpose: Mapped[str] = mapped_column(String(80), nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    hint: Mapped[str] = mapped_column(String(16), nullable=False)


class Source(Base, Timestamps):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint(
            "schedule_interval_seconds IS NULL OR schedule_interval_seconds >= 300", name="min_interval"
        ),
        CheckConstraint("max_concurrency BETWEEN 1 AND 8", name="concurrency_range"),
        CheckConstraint("rate_limit_per_minute BETWEEN 1 AND 600", name="rate_range"),
        CheckConstraint(
            "state <> 'ENABLED' OR policy_status IN ('APPROVED','RESTRICTED')", name="enabled_requires_policy"
        ),
        Index("ix_sources_due", "state", "next_run_at"),
    )
    id: Mapped[int] = pk()
    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(253), index=True)
    category: Mapped[SourceCategory] = mapped_column(enum_col(SourceCategory), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(60), nullable=False)
    collection_method: Mapped[CollectionMethod] = mapped_column(enum_col(CollectionMethod), nullable=False)
    documentation_url: Mapped[str | None] = mapped_column(Text)
    terms_url: Mapped[str | None] = mapped_column(Text)
    policy_status: Mapped[PolicyStatus] = mapped_column(
        enum_col(PolicyStatus), nullable=False, default=PolicyStatus.UNREVIEWED
    )
    policy_notes: Mapped[str | None] = mapped_column(Text)
    state: Mapped[SourceState] = mapped_column(
        enum_col(SourceState), nullable=False, default=SourceState.DISABLED
    )
    health: Mapped[SourceHealth] = mapped_column(
        enum_col(SourceHealth), nullable=False, default=SourceHealth.UNKNOWN
    )
    health_reason: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    secret_id: Mapped[int | None] = mapped_column(ForeignKey("encrypted_secrets.id", ondelete="SET NULL"))
    schedule_interval_seconds: Mapped[int | None] = mapped_column(Integer)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_system: Mapped[bool] = mapped_column(default=False, nullable=False)


class SourcePolicyReview(Base):
    __tablename__ = "source_policy_reviews"
    id: Mapped[int] = pk()
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision: Mapped[PolicyStatus] = mapped_column(enum_col(PolicyStatus), nullable=False)
    robots_summary: Mapped[str | None] = mapped_column(Text)
    terms_notes: Mapped[str | None] = mapped_column(Text)
    allowed_paths: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceExclusion(Base, Timestamps):
    """Denylist: domain (`example.com`, matches subdomains) or URL prefix (`https://x.com/path`)."""

    __tablename__ = "source_exclusions"
    id: Mapped[int] = pk()
    pattern: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class SourceRun(Base):
    __tablename__ = "source_runs"
    __table_args__ = (
        # At most one active run per source (no overlapping runs).
        Index(
            "uq_source_runs_one_active",
            "source_id",
            unique=True,
            postgresql_where=text("status IN ('QUEUED','RUNNING','RETRY_SCHEDULED')"),
        ),
        Index("ix_source_runs_source_started", "source_id", "created_at"),
    )
    id: Mapped[int] = pk()
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    trigger: Mapped[RunTrigger] = mapped_column(enum_col(RunTrigger), nullable=False)
    status: Mapped[RunStatus] = mapped_column(enum_col(RunStatus), nullable=False, default=RunStatus.QUEUED)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=600)
    cancel_requested: Mapped[bool] = mapped_column(default=False, nullable=False)
    discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unchanged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(Text)
    cursor_before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    cursor_after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class SourceRunItem(Base):
    __tablename__ = "source_run_items"
    id: Mapped[int] = pk()
    run_id: Mapped[int] = mapped_column(
        ForeignKey("source_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    external_id: Mapped[str | None] = mapped_column(String(300))
    url: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[RunItemOutcome] = mapped_column(enum_col(RunItemOutcome), nullable=False)
    raw_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_source_versions.id", ondelete="SET NULL")
    )
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceCursor(Base):
    __tablename__ = "source_cursors"
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True)
    cursor: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SourceHealthEvent(Base):
    __tablename__ = "source_health_events"
    id: Mapped[int] = pk()
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True, nullable=False
    )
    health: Mapped[SourceHealth] = mapped_column(enum_col(SourceHealth), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FetchLog(Base):
    """Blocked / failed fetch log without sensitive request data (no headers, no query strings)."""

    __tablename__ = "fetch_logs"
    id: Mapped[int] = pk()
    host: Mapped[str | None] = mapped_column(String(253), index=True)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(300))
    status_code: Mapped[int | None] = mapped_column(Integer)
    bytes: Mapped[int | None] = mapped_column(BigInteger)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class HostRateState(Base):
    """Per-host politeness state shared across worker processes."""

    __tablename__ = "host_rate_state"
    __table_args__ = (UniqueConstraint("host"),)
    id: Mapped[int] = pk()
    host: Mapped[str] = mapped_column(String(253), nullable=False)
    next_allowed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    robots_txt: Mapped[str | None] = mapped_column(Text)
    robots_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    crawl_delay_seconds: Mapped[float | None] = mapped_column()
