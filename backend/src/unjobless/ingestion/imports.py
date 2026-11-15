"""Universal URL importer and paste-content importer.

URL import: validate + de-duplicate lines → batch → each item fetched in the background through the
SafeFetcher (SSRF guards), robots.txt respected, access walls reported (never bypassed) with a
paste-content fallback. Paste import: exact text preserved as an immutable raw version.
Both feed the review queue (NEEDS_REVIEW): nothing is saved as a vacancy without the owner's confirmation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from unjobless.core.config import get_settings
from unjobless.core.errors import BlockedURL, FetchFailed, NotFound, ValidationFailed
from unjobless.core.logging import get_logger
from unjobless.core.time import utcnow
from unjobless.db.models import ContentTranscription, ImportBatch, ImportItem, Source
from unjobless.db.session import session_scope
from unjobless.domain.enums import (
    ImportBatchStatus,
    ImportItemStatus,
    ImportKind,
    RunItemOutcome,
    TextOrigin,
    TranscriptionKind,
)
from unjobless.domain.state_machines import IMPORT_ITEM, TERMINAL_IMPORT_ERR, TERMINAL_IMPORT_OK
from unjobless.fetch.politeness import log_fetch, robots_allows
from unjobless.fetch.safe_fetch import SafeFetcher, validate_url
from unjobless.fetch.urls import canonicalize_url, host_of
from unjobless.ingestion.raw_store import store_item
from unjobless.intelligence.structured import (
    extract_main_text,
    find_jobpostings,
    looks_like_access_wall,
    page_meta,
)
from unjobless.jobs.queue import defer
from unjobless.sources.contract import CollectedItem
from unjobless.sources.service import ensure_system_source, is_excluded

log = get_logger(__name__)

KNOWN_HOSTS = {
    "boards.greenhouse.io": "Greenhouse job page",
    "job-boards.greenhouse.io": "Greenhouse job page",
    "jobs.lever.co": "Lever job page",
    "jobs.ashbyhq.com": "Ashby job page",
    "www.linkedin.com": "LinkedIn (login usually required)",
    "linkedin.com": "LinkedIn (login usually required)",
    "www.instagram.com": "Instagram (login usually required)",
    "instagram.com": "Instagram (login usually required)",
    "x.com": "X / Twitter",
    "twitter.com": "X / Twitter",
    "www.facebook.com": "Facebook (login usually required)",
    "glints.com": "Glints",
    "www.jobstreet.co.id": "JobStreet",
    "id.jobstreet.com": "JobStreet",
    "www.kalibrr.com": "Kalibrr",
}
PASTE_FALLBACK = "Open the page in your browser, copy the post text, and use “Paste content” instead."


@dataclass
class LineCheck:
    line: int
    raw: str
    ok: bool
    url: str | None = None
    domain: str | None = None
    detected: str | None = None
    error: str | None = None
    duplicate_of: int | None = None


def check_lines(db: Session, text: str) -> list[LineCheck]:
    """Instant validation for the importer textarea (no network)."""
    out: list[LineCheck] = []
    seen: dict[str, int] = {}
    for i, raw in enumerate(text.splitlines(), start=1):
        s = raw.strip()
        if not s:
            continue
        if not s.lower().startswith(("http://", "https://")) and "." in s and " " not in s:
            s = "https://" + s
        try:
            validate_url(s, resolve=False)
        except BlockedURL as e:
            out.append(LineCheck(i, raw, False, error=e.message))
            continue
        canon = canonicalize_url(s)
        host = host_of(s) or ""
        if is_excluded(db, s):
            out.append(
                LineCheck(i, raw, False, url=s, domain=host, error="This domain is on your exclusion list.")
            )
            continue
        if canon in seen:
            out.append(
                LineCheck(
                    i,
                    raw,
                    False,
                    url=s,
                    domain=host,
                    error="Duplicate in this batch.",
                    duplicate_of=seen[canon],
                )
            )
            continue
        seen[canon] = i
        out.append(
            LineCheck(
                i, raw, True, url=s, domain=host, detected=KNOWN_HOSTS.get(host) or _source_for_host(db, host)
            )
        )
    return out


def _source_for_host(db: Session, host: str) -> str | None:
    src = (
        db.execute(select(Source).where(Source.domain.is_not(None), Source.is_system.is_(False)))
        .scalars()
        .all()
    )
    for s in src:
        if s.domain and (host == s.domain or host.endswith("." + s.domain)):
            return f"Registered source: {s.name}"
    return None


def create_url_batch(
    db: Session, text: str, *, note: str | None = None, category_hint: str | None = None
) -> tuple[ImportBatch, list[LineCheck]]:
    checks = check_lines(db, text)
    valid = [c for c in checks if c.ok]
    if not valid:
        raise ValidationFailed("No valid URLs to import.", details={"lines": [c.__dict__ for c in checks]})
    limit = get_settings().max_urls_per_batch
    if len(valid) > limit:
        raise ValidationFailed(f"A batch can contain at most {limit} URLs.")
    batch = ImportBatch(
        kind=ImportKind.URL,
        status=ImportBatchStatus.PENDING,
        note=note,
        category_hint=category_hint,
        item_count=len(valid),
    )
    db.add(batch)
    db.flush()
    for pos, c in enumerate(valid):
        db.add(
            ImportItem(
                batch_id=batch.id,
                position=pos,
                input_url=c.url,
                detected_domain=c.domain,
                detected_connector=c.detected,
                status=ImportItemStatus.QUEUED,
                idempotency_key=hashlib.sha256(canonicalize_url(c.url or "").encode()).hexdigest()[:40],
            )
        )
    db.flush()
    return batch, checks


def enqueue_batch(db: Session, batch: ImportBatch) -> None:
    for item in db.execute(
        select(ImportItem).where(
            ImportItem.batch_id == batch.id, ImportItem.status == ImportItemStatus.QUEUED
        )
    ).scalars():
        defer("process_import_item", queueing_lock=f"import-{item.id}", item_id=item.id)


def _set(
    item: ImportItem, status: ImportItemStatus, *, reason: str | None = None, code: str | None = None
) -> None:
    IMPORT_ITEM.check(item.status, status)
    item.status = status
    if status in TERMINAL_IMPORT_ERR:
        item.failure_reason, item.failure_code = reason, code
    elif status not in (ImportItemStatus.FETCHING,):
        item.failure_reason = item.failure_code = None


def refresh_batch_status(db: Session, batch_id: int) -> None:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        return
    statuses = [s for (s,) in db.execute(select(ImportItem.status).where(ImportItem.batch_id == batch_id))]
    if not statuses:
        return
    if all(s in TERMINAL_IMPORT_OK | TERMINAL_IMPORT_ERR for s in statuses):
        batch.status = (
            ImportBatchStatus.COMPLETED_WITH_ERRORS
            if any(s in TERMINAL_IMPORT_ERR for s in statuses)
            else ImportBatchStatus.COMPLETED
        )
    else:
        batch.status = ImportBatchStatus.PROCESSING


def process_import_item(item_id: int, *, fetcher: SafeFetcher | None = None, use_ai: bool = True) -> None:
    """Fetch + store + analyse one URL item. Each item fails independently of its batch."""
    with session_scope() as db:
        item = db.get(ImportItem, item_id)
        if item is None or item.status not in (ImportItemStatus.QUEUED, ImportItemStatus.FETCHING):
            return
        if item.input_url is None:
            return _process_paste_item(db, item, use_ai=use_ai)
        if item.status == ImportItemStatus.QUEUED:
            _set(item, ImportItemStatus.FETCHING)
        db.commit()
        own = fetcher is None
        f = fetcher or SafeFetcher()
        try:
            _fetch_and_store(db, item, f)
        finally:
            if own:
                f.close()
        db.commit()
        if item.status == ImportItemStatus.EXTRACTED and item.raw_version_id:
            from unjobless.intelligence.pipeline import process_version

            process_version(db, item.raw_version_id, use_ai=use_ai)
        refresh_batch_status(db, item.batch_id)


def _fetch_and_store(db: Session, item: ImportItem, f: SafeFetcher) -> None:
    url = item.input_url or ""
    host = host_of(url)
    if is_excluded(db, url):
        return _set(
            item, ImportItemStatus.BLOCKED, reason="This domain is on your exclusion list.", code="excluded"
        )
    try:
        if not robots_allows(db, f, url):
            log_fetch(db, "blocked", host, "robots_disallow")
            return _set(
                item,
                ImportItemStatus.BLOCKED,
                reason=f"The site's robots.txt does not allow automated fetching of this page. {PASTE_FALLBACK}",
                code="robots_disallow",
            )
        res = f.get(
            url,
            content_types=(
                "text/html",
                "application/xhtml+xml",
                "text/plain",
                "application/json",
                "application/ld+json",
            ),
        )
    except BlockedURL as e:
        log_fetch(db, "blocked", host, e.code)
        return _set(
            item,
            ImportItemStatus.BLOCKED,
            reason=f"{e.message} {PASTE_FALLBACK if e.code in ('content_type_not_allowed', 'too_large') else ''}".strip(),
            code=e.code,
        )
    except FetchFailed as e:
        log_fetch(db, "failed", host, e.code)
        return _set(item, ImportItemStatus.UNAVAILABLE, reason=f"{e.message} {PASTE_FALLBACK}", code=e.code)
    if res.status_code in (401, 402, 403, 407, 451):
        return _set(
            item,
            ImportItemStatus.UNAVAILABLE,
            reason=f"The page requires sign-in or blocks automated access (HTTP {res.status_code}). Unjobless does not bypass this. {PASTE_FALLBACK}",
            code="access_restricted",
        )
    if res.status_code == 404 or res.status_code == 410:
        return _set(
            item,
            ImportItemStatus.UNAVAILABLE,
            reason="The page was not found; the posting may have been removed.",
            code="not_found",
        )
    if res.status_code == 429:
        return _set(
            item,
            ImportItemStatus.UNAVAILABLE,
            reason="The site is rate limiting requests. Retry later.",
            code="rate_limited",
        )
    if res.status_code >= 400:
        return _set(
            item,
            ImportItemStatus.UNAVAILABLE,
            reason=f"The site returned HTTP {res.status_code}.",
            code="http_error",
        )
    html = res.text
    is_html = res.content_type in ("text/html", "application/xhtml+xml")
    text = extract_main_text(html) if is_html else html
    if is_html and looks_like_access_wall(html, text):
        return _set(
            item,
            ImportItemStatus.UNAVAILABLE,
            reason=f"The page shows a login or CAPTCHA wall. {PASTE_FALLBACK}",
            code="access_wall",
        )
    meta = page_meta(html) if is_html else {}
    postings = find_jobpostings(html) if is_html else []
    canonical = (
        meta.get("canonical")
        if meta.get("canonical", "") and str(meta.get("canonical")).startswith("http")
        else res.url
    )
    source = ensure_system_source(db, "user_url_import")
    stored = store_item(
        db,
        source,
        CollectedItem(
            native_id=None,
            url=res.url,
            canonical_url=canonicalize_url(str(canonical)),
            content_type=res.content_type,
            raw_text=html,
            extracted_text=text,
            title=(postings[0].get("title") if postings else None)
            or meta.get("og:title")
            or meta.get("title"),
            application_url=postings[0].get("application_url") if postings else None,
            metadata={
                **{k: v for k, v in meta.items() if k != "robots"},
                "requested_url": item.input_url,
                "redirects": res.redirects,
                "truncated": res.truncated,
            },
            structured=postings or None,
        ),
    )
    item.raw_version_id = stored.version.id
    _set(item, ImportItemStatus.EXTRACTED)
    if stored.outcome == RunItemOutcome.UNCHANGED:
        from unjobless.intelligence.vacancies import vacancy_for_document

        v = vacancy_for_document(db, stored.document.id)
        if v is not None:
            item.result_vacancy_id = v.id
            _set(item, ImportItemStatus.DUPLICATE)
            item.failure_reason = f"Already saved as vacancy #{v.id}."


# ---------------------------------------------------------------- paste import


@dataclass
class PasteInput:
    text: str
    source_url: str | None = None
    platform: str | None = None
    author_label: str | None = None
    published_at: datetime | None = None
    content_type_hint: str | None = None
    notes: str | None = None
    extra_text: str | None = None  # OCR / transcript the owner pasted


def create_paste_batch(db: Session, records: list[PasteInput], *, note: str | None = None) -> ImportBatch:
    if not records:
        raise ValidationFailed("Paste some content first.")
    maxc = get_settings().max_paste_chars
    for r in records:
        if not r.text.strip():
            raise ValidationFailed("Pasted content is empty.")
        if len(r.text) > maxc:
            raise ValidationFailed(f"Pasted content is longer than {maxc} characters.")
        if r.source_url:
            try:
                validate_url(r.source_url, resolve=False)
            except BlockedURL as e:
                raise ValidationFailed(f"Source URL: {e.message}") from e
    batch = ImportBatch(
        kind=ImportKind.PASTE, status=ImportBatchStatus.PENDING, note=note, item_count=len(records)
    )
    db.add(batch)
    db.flush()
    source = ensure_system_source(db, "user_paste")
    for pos, r in enumerate(records):
        digest = hashlib.sha256(r.text.encode()).hexdigest()
        stored = store_item(
            db,
            source,
            CollectedItem(
                native_id=f"paste:{digest[:32]}",
                url=r.source_url,
                content_type="text/plain",
                raw_text=r.text,  # preserved exactly
                title=None,
                published_at=r.published_at,
                metadata={
                    k: v
                    for k, v in {
                        "platform": r.platform,
                        "author_label": r.author_label,
                        "content_type_hint": r.content_type_hint,
                        "notes": r.notes,
                        "source_url": r.source_url,
                    }.items()
                    if v
                },
            ),
        )
        if r.extra_text and r.extra_text.strip():
            db.add(
                ContentTranscription(
                    version_id=stored.version.id,
                    kind=TranscriptionKind.USER_PROVIDED,
                    origin=TextOrigin.USER_PROVIDED,
                    text=r.extra_text[:maxc],
                    engine="owner",
                )
            )
        item = ImportItem(
            batch_id=batch.id,
            position=pos,
            input_url=None,
            detected_domain=host_of(r.source_url) if r.source_url else None,
            detected_connector=r.platform,
            paste_meta={
                "platform": r.platform,
                "author_label": r.author_label,
                "source_url": r.source_url,
                "notes": r.notes,
            },
            status=ImportItemStatus.QUEUED,
            raw_version_id=stored.version.id,
            idempotency_key=digest[:40],
        )
        db.add(item)
        db.flush()
        _set(item, ImportItemStatus.EXTRACTED)
        if stored.outcome == RunItemOutcome.UNCHANGED:
            from unjobless.intelligence.vacancies import vacancy_for_document

            v = vacancy_for_document(db, stored.document.id)
            if v is not None:
                item.result_vacancy_id = v.id
                _set(item, ImportItemStatus.DUPLICATE)
                item.failure_reason = f"This exact text is already saved as vacancy #{v.id}."
    db.flush()
    return batch


def _process_paste_item(db: Session, item: ImportItem, *, use_ai: bool) -> None:
    from unjobless.intelligence.pipeline import process_version

    if item.raw_version_id:
        process_version(db, item.raw_version_id, use_ai=use_ai)
    refresh_batch_status(db, item.batch_id)


def enqueue_paste_batch(db: Session, batch: ImportBatch) -> None:
    for item in db.execute(
        select(ImportItem).where(
            ImportItem.batch_id == batch.id, ImportItem.status == ImportItemStatus.EXTRACTED
        )
    ).scalars():
        if item.raw_version_id:
            defer(
                "process_version",
                queueing_lock=f"version-{item.raw_version_id}",
                version_id=item.raw_version_id,
            )


def retry_item(db: Session, item: ImportItem, *, corrected_url: str | None = None) -> ImportItem:
    if item.status not in TERMINAL_IMPORT_ERR:
        raise ValidationFailed("Only blocked, unavailable or failed items can be retried.")
    if corrected_url:
        validate_url(corrected_url, resolve=False)
        item.input_url = corrected_url
        item.detected_domain = host_of(corrected_url)
    item.retry_count += 1
    _set(item, ImportItemStatus.QUEUED)
    item.updated_at = utcnow()
    db.flush()
    defer("process_import_item", queueing_lock=f"import-{item.id}", item_id=item.id)
    return item


def batch_summary(db: Session, batch: ImportBatch) -> dict[str, Any]:
    counts = dict(
        db.execute(
            select(ImportItem.status, func.count())
            .where(ImportItem.batch_id == batch.id)
            .group_by(ImportItem.status)
        ).all()
    )
    return {
        "id": batch.id,
        "kind": batch.kind.value,
        "status": batch.status.value,
        "note": batch.note,
        "category_hint": batch.category_hint,
        "item_count": batch.item_count,
        "created_at": batch.created_at.isoformat(),
        "counts": {k.value: v for k, v in counts.items()},
    }


def get_item(db: Session, item_id: int) -> ImportItem:
    item = db.get(ImportItem, item_id)
    if item is None:
        raise NotFound("Import item not found.")
    return item
