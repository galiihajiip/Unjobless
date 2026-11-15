from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
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
    ImportBatchStatus,
    ImportItemStatus,
    ImportKind,
    OpportunityClassification,
    ProcessingStatus,
    TextOrigin,
    TranscriptionKind,
)

from .base import Base, Timestamps, enum_col, pk


class RawSourceDocument(Base):
    """Identity of one collected item. Content lives in immutable RawSourceVersion rows."""

    __tablename__ = "raw_source_documents"
    __table_args__ = (
        Index(
            "uq_raw_doc_native",
            "source_id",
            "source_native_id",
            unique=True,
            postgresql_where=text("source_native_id IS NOT NULL"),
        ),
        Index(
            "uq_raw_doc_url",
            "source_id",
            "canonical_url",
            unique=True,
            postgresql_where=text("source_native_id IS NULL AND canonical_url IS NOT NULL"),
        ),
    )
    id: Mapped[int] = pk()
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_native_id: Mapped[str | None] = mapped_column(String(300))
    canonical_url: Mapped[str | None] = mapped_column(Text, index=True)
    original_url: Mapped[str | None] = mapped_column(Text)
    collection_method: Mapped[CollectionMethod] = mapped_column(enum_col(CollectionMethod), nullable=False)
    first_collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_in_listing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latest_version_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "raw_source_versions.id", ondelete="SET NULL", use_alter=True, name="fk_raw_doc_latest_version"
        )
    )
    gone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RawSourceVersion(Base):
    """Immutable content snapshot. A new row is written only when the content hash changes."""

    __tablename__ = "raw_source_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "content_hash", name="uq_raw_version_doc_hash"),
        CheckConstraint("byte_size >= 0", name="size_nonneg"),
    )
    id: Mapped[int] = pk()
    document_id: Mapped[int] = mapped_column(
        ForeignKey("raw_source_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text)
    blob_ref: Mapped[str | None] = mapped_column(String(200))
    extracted_text: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    structured_data: Mapped[list[Any] | None] = mapped_column(JSONB)
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    language: Mapped[str | None] = mapped_column(String(12))
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        enum_col(ProcessingStatus), nullable=False, default=ProcessingStatus.QUEUED
    )
    processing_error: Mapped[str | None] = mapped_column(Text)
    classification: Mapped[OpportunityClassification | None] = mapped_column(
        enum_col(OpportunityClassification)
    )
    classification_detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class SourceMediaAsset(Base):
    __tablename__ = "source_media_assets"
    id: Mapped[int] = pk()
    version_id: Mapped[int] = mapped_column(
        ForeignKey("raw_source_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    blob_ref: Mapped[str | None] = mapped_column(String(200))
    mime: Mapped[str | None] = mapped_column(String(100))
    sha256: Mapped[str | None] = mapped_column(String(64))
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    alt_text: Mapped[str | None] = mapped_column(Text)
    permitted_download: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        enum_col(ProcessingStatus), nullable=False, default=ProcessingStatus.QUEUED
    )
    processing_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentTranscription(Base):
    __tablename__ = "content_transcriptions"
    id: Mapped[int] = pk()
    version_id: Mapped[int] = mapped_column(
        ForeignKey("raw_source_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_id: Mapped[int | None] = mapped_column(ForeignKey("source_media_assets.id", ondelete="CASCADE"))
    kind: Mapped[TranscriptionKind] = mapped_column(enum_col(TranscriptionKind), nullable=False)
    origin: Mapped[TextOrigin] = mapped_column(enum_col(TextOrigin), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    engine: Mapped[str | None] = mapped_column(String(80))
    language: Mapped[str | None] = mapped_column(String(12))
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportBatch(Base, Timestamps):
    __tablename__ = "import_batches"
    id: Mapped[int] = pk()
    kind: Mapped[ImportKind] = mapped_column(enum_col(ImportKind), nullable=False)
    status: Mapped[ImportBatchStatus] = mapped_column(
        enum_col(ImportBatchStatus), nullable=False, default=ImportBatchStatus.PENDING
    )
    note: Mapped[str | None] = mapped_column(Text)
    category_hint: Mapped[str | None] = mapped_column(String(60))
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ImportItem(Base, Timestamps):
    __tablename__ = "import_items"
    __table_args__ = (
        UniqueConstraint("batch_id", "idempotency_key", name="uq_import_item_batch_key"),
        CheckConstraint("retry_count >= 0", name="retry_nonneg"),
    )
    id: Mapped[int] = pk()
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_url: Mapped[str | None] = mapped_column(Text)
    detected_domain: Mapped[str | None] = mapped_column(String(253))
    detected_connector: Mapped[str | None] = mapped_column(String(60))
    paste_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[ImportItemStatus] = mapped_column(
        enum_col(ImportItemStatus), nullable=False, default=ImportItemStatus.QUEUED, index=True
    )
    raw_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_source_versions.id", ondelete="SET NULL")
    )
    extraction: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result_vacancy_id: Mapped[int | None] = mapped_column(ForeignKey("job_vacancies.id", ondelete="SET NULL"))
    result_signal_id: Mapped[int | None] = mapped_column(
        ForeignKey("opportunity_signals.id", ondelete="SET NULL")
    )
    failure_reason: Mapped[str | None] = mapped_column(Text)
    failure_code: Mapped[str | None] = mapped_column(String(60))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    user_corrections: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class ProcessingJob(Base):
    """Domain-level record of background work (independent of the queue implementation)."""

    __tablename__ = "processing_jobs"
    __table_args__ = (
        Index(
            "uq_processing_jobs_active_key",
            "idempotency_key",
            unique=True,
            postgresql_where=text("status IN ('QUEUED','RUNNING')"),
        ),
    )
    id: Mapped[int] = pk()
    kind: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(60))
    target_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[ProcessingStatus] = mapped_column(enum_col(ProcessingStatus), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
