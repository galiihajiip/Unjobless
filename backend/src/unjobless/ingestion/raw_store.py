"""Raw ingestion and evidence store.

- One RawSourceDocument per (source, native id) or (source, canonical URL).
- A new immutable RawSourceVersion is written only when the normalised content hash changes.
- Raw content is size-capped; large bodies go to the private file store.
- Metadata is sanitised: no cookies, auth headers or session data are ever persisted.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from unjobless.core.errors import Conflict
from unjobless.core.time import utcnow
from unjobless.db.models import JobVacancySource, RawSourceDocument, RawSourceVersion, Source
from unjobless.domain.enums import ProcessingStatus, RunItemOutcome
from unjobless.fetch.urls import canonicalize_url
from unjobless.ingestion.filestore import FileStore, get_filestore
from unjobless.sources.contract import CollectedItem

INLINE_TEXT_LIMIT = 1_000_000  # characters kept inline in raw_text
MAX_RAW_BYTES = 10 * 1024 * 1024  # anything larger is truncated (flagged)
MAX_EXTRACTED_CHARS = 300_000
FORBIDDEN_META_KEYS = re.compile(
    r"(?i)(cookie|authorization|auth|token|session|password|secret|api[-_]?key|set-cookie|x-csrf)"
)


def normalize_for_hash(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", text).strip()


def content_hash(text: str, title: str | None = None) -> str:
    return hashlib.sha256(
        (normalize_for_hash(title or "") + "\n" + normalize_for_hash(text)).encode()
    ).hexdigest()


def sanitize_metadata(meta: dict[str, Any], depth: int = 0) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (meta or {}).items():
        if FORBIDDEN_META_KEYS.search(str(k)):
            continue
        if isinstance(v, dict) and depth < 4:
            out[str(k)] = sanitize_metadata(v, depth + 1)
        elif isinstance(v, list):
            out[str(k)] = [sanitize_metadata(x, depth + 1) if isinstance(x, dict) else x for x in v[:200]]
        elif isinstance(v, str):
            out[str(k)] = v[:5000]
        elif isinstance(v, int | float | bool) or v is None:
            out[str(k)] = v
        else:
            out[str(k)] = str(v)[:5000]
    return out


@dataclass
class StoreResult:
    document: RawSourceDocument
    version: RawSourceVersion
    outcome: RunItemOutcome


def store_item(
    db: Session,
    source: Source,
    item: CollectedItem,
    *,
    filestore: FileStore | None = None,
    seen_in_listing: bool = True,
    collected_at: datetime | None = None,
) -> StoreResult:
    now = collected_at or utcnow()
    raw = item.raw_text or ""
    truncated = False
    encoded = raw.encode("utf-8", errors="replace")
    if len(encoded) > MAX_RAW_BYTES:
        encoded = encoded[:MAX_RAW_BYTES]
        raw = encoded.decode("utf-8", errors="ignore")
        truncated = True
    canonical = item.canonical_url or (canonicalize_url(item.url) if item.url else None)

    doc: RawSourceDocument | None = None
    if item.native_id:
        doc = db.execute(
            select(RawSourceDocument).where(
                RawSourceDocument.source_id == source.id, RawSourceDocument.source_native_id == item.native_id
            )
        ).scalar_one_or_none()
    elif canonical:
        doc = db.execute(
            select(RawSourceDocument).where(
                RawSourceDocument.source_id == source.id,
                RawSourceDocument.source_native_id.is_(None),
                RawSourceDocument.canonical_url == canonical,
            )
        ).scalar_one_or_none()
    if doc is None:
        doc = RawSourceDocument(
            source_id=source.id,
            source_native_id=item.native_id,
            canonical_url=canonical,
            original_url=item.url,
            collection_method=source.collection_method,
            first_collected_at=now,
            last_collected_at=now,
        )
        db.add(doc)
        db.flush()
    doc.last_collected_at = now
    doc.gone_at = None
    if seen_in_listing:
        doc.last_seen_in_listing_at = now

    h = content_hash(raw, item.title)
    existing = db.execute(
        select(RawSourceVersion).where(
            RawSourceVersion.document_id == doc.id, RawSourceVersion.content_hash == h
        )
    ).scalar_one_or_none()
    if existing is not None:
        if doc.latest_version_id != existing.id:
            # Content reverted to an earlier version: point back to it, no new row.
            doc.latest_version_id = existing.id
        return StoreResult(doc, existing, RunItemOutcome.UNCHANGED)

    blob_ref = None
    inline = raw
    if len(raw) > INLINE_TEXT_LIMIT:
        blob_ref, _ = (filestore or get_filestore()).put(encoded, namespace="raw", suffix=".txt")
        inline = raw[:INLINE_TEXT_LIMIT]
        truncated = True
    is_new = doc.latest_version_id is None
    version = RawSourceVersion(
        document_id=doc.id,
        content_hash=h,
        content_type=item.content_type[:100],
        raw_text=inline,
        blob_ref=blob_ref,
        extracted_text=(item.extracted_text or None) and item.extracted_text[:MAX_EXTRACTED_CHARS],
        title=item.title,
        metadata_=sanitize_metadata(
            {**item.metadata, **({"application_url": item.application_url} if item.application_url else {})}
        ),
        structured_data=item.structured,
        source_published_at=item.published_at,
        collected_at=now,
        language=item.language,
        byte_size=len(encoded),
        truncated=truncated,
        processing_status=ProcessingStatus.QUEUED,
    )
    db.add(version)
    db.flush()
    doc.latest_version_id = version.id
    return StoreResult(doc, version, RunItemOutcome.NEW if is_new else RunItemOutcome.CHANGED)


def full_raw_text(version: RawSourceVersion, filestore: FileStore | None = None) -> str:
    if version.blob_ref:
        return (filestore or get_filestore()).get(version.blob_ref).decode("utf-8", errors="replace")
    return version.raw_text or ""


def delete_document(db: Session, doc: RawSourceDocument) -> None:
    """Safe deletion: refuses while a canonical vacancy cites this document (provenance must remain)."""
    cited = db.execute(
        select(JobVacancySource.id).where(JobVacancySource.raw_document_id == doc.id).limit(1)
    ).first()
    if cited:
        raise Conflict("This raw document is evidence for a vacancy and cannot be deleted.")
    fs = get_filestore()
    for v in db.execute(select(RawSourceVersion).where(RawSourceVersion.document_id == doc.id)).scalars():
        if v.blob_ref:
            fs.delete(v.blob_ref)
    doc.latest_version_id = None
    db.flush()
    db.delete(doc)


def purge_expired(db: Session) -> int:
    """Delete raw documents past their retention date that are not cited by any vacancy."""
    n = 0
    rows = (
        db.execute(select(RawSourceDocument).where(RawSourceDocument.retention_until < utcnow()))
        .scalars()
        .all()
    )
    for doc in rows:
        try:
            delete_document(db, doc)
            n += 1
        except Conflict:
            continue
    return n
