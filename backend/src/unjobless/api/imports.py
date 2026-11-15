from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, File, Form, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from unjobless.api.deps import DB
from unjobless.core.errors import NotFound, ValidationFailed
from unjobless.db.models import (
    ContentTranscription,
    ImportBatch,
    ImportItem,
    RawSourceVersion,
    SourceMediaAsset,
)
from unjobless.domain.enums import ImportItemStatus
from unjobless.ingestion import imports as svc
from unjobless.ingestion import review
from unjobless.ingestion.media import attach_media, validate_upload
from unjobless.ingestion.raw_store import full_raw_text
from unjobless.jobs.queue import defer

router = APIRouter(prefix="/imports", tags=["imports"])


class UrlCheckIn(BaseModel):
    text: str = Field(max_length=200_000)


class UrlBatchIn(UrlCheckIn):
    note: str | None = Field(default=None, max_length=2000)
    category_hint: str | None = Field(default=None, max_length=60)


class PasteRecordIn(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)
    source_url: str | None = Field(default=None, max_length=2048)
    platform: str | None = Field(default=None, max_length=80)
    author_label: str | None = Field(default=None, max_length=120)
    published_at: datetime | None = None
    content_type_hint: str | None = Field(default=None, max_length=60)
    notes: str | None = Field(default=None, max_length=2000)
    extra_text: str | None = Field(default=None, max_length=200_000)


class PasteBatchIn(BaseModel):
    records: list[PasteRecordIn] = Field(min_length=1, max_length=20)
    note: str | None = None


class CorrectionsIn(BaseModel):
    corrections: dict[str, Any] = Field(default_factory=dict)


class MergeIn(BaseModel):
    vacancy_id: int


class RejectIn(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class RetryIn(BaseModel):
    corrected_url: str | None = Field(default=None, max_length=2048)


def item_out(db: DB, it: ImportItem, full: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": it.id, "batch_id": it.batch_id, "position": it.position, "input_url": it.input_url, "detected_domain": it.detected_domain,
        "detected_connector": it.detected_connector, "paste_meta": it.paste_meta, "status": it.status.value,
        "failure_reason": it.failure_reason, "failure_code": it.failure_code, "retry_count": it.retry_count,
        "result_vacancy_id": it.result_vacancy_id, "result_signal_id": it.result_signal_id, "raw_version_id": it.raw_version_id,
        "created_at": it.created_at.isoformat(), "updated_at": it.updated_at.isoformat(),
        "classification": (it.extraction or {}).get("classification"),
        "title": ((it.extraction or {}).get("extraction") or {}).get("title"),
        "paste_fallback": it.status in (ImportItemStatus.BLOCKED, ImportItemStatus.UNAVAILABLE, ImportItemStatus.FAILED),
    }
    if full:
        out["extraction"] = it.extraction
        out["user_corrections"] = it.user_corrections
        if it.raw_version_id:
            v = db.get(RawSourceVersion, it.raw_version_id)
            if v:
                from unjobless.intelligence.pipeline import version_text

                out["raw"] = {
                    "content_type": v.content_type, "title": v.title, "collected_at": v.collected_at.isoformat(), "content_hash": v.content_hash,
                    "byte_size": v.byte_size, "truncated": v.truncated, "metadata": v.metadata_, "language": v.language,
                    "text": version_text(v)[:60_000],
                    "raw_text": full_raw_text(v)[:60_000] if v.content_type == "text/plain" else None,
                    "processing_status": v.processing_status.value, "processing_error": v.processing_error,
                }
                out["media"] = [
                    {"id": m.id, "kind": m.kind, "mime": m.mime, "status": m.processing_status.value, "message": m.processing_error}
                    for m in db.execute(select(SourceMediaAsset).where(SourceMediaAsset.version_id == v.id)).scalars()
                ]
                out["transcriptions"] = [
                    {"kind": t.kind.value, "origin": t.origin.value, "engine": t.engine, "text": t.text[:20_000]}
                    for t in db.execute(select(ContentTranscription).where(ContentTranscription.version_id == v.id)).scalars()
                ]
    return out


@router.post("/urls/check")
def check(body: UrlCheckIn, db: DB) -> dict[str, Any]:
    lines = svc.check_lines(db, body.text)
    return {"lines": [c.__dict__ for c in lines], "valid": sum(c.ok for c in lines), "max": svc.get_settings().max_urls_per_batch}


@router.post("/urls", status_code=202)
def import_urls(body: UrlBatchIn, db: DB) -> dict[str, Any]:
    batch, checks = svc.create_url_batch(db, body.text, note=body.note, category_hint=body.category_hint)
    db.commit()
    svc.enqueue_batch(db, batch)
    return {"batch": svc.batch_summary(db, batch), "skipped_lines": [c.__dict__ for c in checks if not c.ok]}


@router.post("/paste", status_code=202)
def import_paste(body: PasteBatchIn, db: DB) -> dict[str, Any]:
    batch = svc.create_paste_batch(db, [svc.PasteInput(**r.model_dump()) for r in body.records], note=body.note)
    db.commit()
    svc.enqueue_paste_batch(db, batch)
    return {"batch": svc.batch_summary(db, batch)}


@router.post("/upload", status_code=202)
async def import_upload(
    db: DB,
    file: UploadFile = File(...),
    source_url: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    extra_text: str | None = Form(default=None),
) -> dict[str, Any]:
    """Poster/screenshot/PDF/captions the owner is authorised to process → OCR/text → review."""
    data = await file.read(svc.get_settings().max_upload_bytes + 1)
    mime = validate_upload(data, file.content_type, file.filename)
    placeholder = f"[uploaded file: {file.filename or 'file'} ({mime})]"
    batch = svc.create_paste_batch(db, [svc.PasteInput(text=placeholder + (f"\n\n{notes}" if notes else ""), source_url=source_url, platform="upload", notes=notes, extra_text=extra_text)])
    item = db.execute(select(ImportItem).where(ImportItem.batch_id == batch.id)).scalar_one()
    version = db.get(RawSourceVersion, item.raw_version_id)
    assert version is not None
    asset = attach_media(db, version, data, mime)
    db.commit()
    defer("process_media", queueing_lock=f"media-{asset.id}", media_id=asset.id)
    return {"batch": svc.batch_summary(db, batch), "media_id": asset.id}


@router.get("/batches")
def batches(db: DB, limit: int = Query(20, le=100), offset: int = 0) -> dict[str, Any]:
    total = db.execute(select(func.count()).select_from(ImportBatch)).scalar_one()
    rows = db.execute(select(ImportBatch).order_by(ImportBatch.created_at.desc()).limit(limit).offset(offset)).scalars()
    return {"items": [svc.batch_summary(db, b) for b in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/batches/{batch_id}")
def batch(batch_id: int, db: DB) -> dict[str, Any]:
    b = db.get(ImportBatch, batch_id)
    if b is None:
        raise NotFound("Batch not found.")
    items = db.execute(select(ImportItem).where(ImportItem.batch_id == b.id).order_by(ImportItem.position)).scalars()
    return {"batch": svc.batch_summary(db, b), "items": [item_out(db, i) for i in items]}


@router.get("/review-queue")
def review_queue(db: DB, limit: int = Query(50, le=200)) -> list[dict[str, Any]]:
    rows = db.execute(
        select(ImportItem).where(ImportItem.status == ImportItemStatus.NEEDS_REVIEW).order_by(ImportItem.updated_at.desc()).limit(limit)
    ).scalars()
    return [item_out(db, i) for i in rows]


@router.get("/items/{item_id}")
def item(item_id: int, db: DB) -> dict[str, Any]:
    return item_out(db, svc.get_item(db, item_id), full=True)


@router.post("/items/{item_id}/corrections")
def corrections(item_id: int, body: CorrectionsIn, db: DB) -> dict[str, Any]:
    it = review.save_corrections(db, svc.get_item(db, item_id), body.corrections)
    return item_out(db, it, full=True)


@router.post("/items/{item_id}/confirm-vacancy")
def confirm_vacancy(item_id: int, body: CorrectionsIn, db: DB) -> dict[str, Any]:
    v = review.confirm_as_vacancy(db, svc.get_item(db, item_id), body.corrections or None)
    return {"vacancy_id": v.id}


@router.post("/items/{item_id}/confirm-lead")
def confirm_lead(item_id: int, db: DB) -> dict[str, Any]:
    s = review.confirm_as_lead(db, svc.get_item(db, item_id))
    return {"signal_id": s.id}


@router.post("/items/{item_id}/reject")
def reject(item_id: int, body: RejectIn, db: DB) -> dict[str, Any]:
    return item_out(db, review.reject(db, svc.get_item(db, item_id), body.reason))


@router.post("/items/{item_id}/merge")
def merge(item_id: int, body: MergeIn, db: DB) -> dict[str, Any]:
    v = review.merge_into(db, svc.get_item(db, item_id), body.vacancy_id)
    return {"vacancy_id": v.id}


@router.post("/items/{item_id}/retry")
def retry(item_id: int, body: RetryIn, db: DB) -> dict[str, Any]:
    it = svc.get_item(db, item_id)
    if it.input_url is None and it.status != ImportItemStatus.FAILED:
        raise ValidationFailed("Paste items do not need refetching.")
    return item_out(db, svc.retry_item(db, it, corrected_url=body.corrected_url))


@router.post("/items/{item_id}/reprocess")
def reprocess(item_id: int, db: DB) -> dict[str, Any]:
    """Re-run analysis (e.g. after adding an AI provider) on a stored item."""
    it = svc.get_item(db, item_id)
    if not it.raw_version_id:
        raise ValidationFailed("Nothing stored to reprocess.")
    v = db.get(RawSourceVersion, it.raw_version_id)
    from unjobless.domain.enums import ProcessingStatus

    if v:
        v.processing_status = ProcessingStatus.QUEUED
    db.commit()
    defer("process_version", queueing_lock=f"version-{it.raw_version_id}", version_id=it.raw_version_id)
    return item_out(db, it)
