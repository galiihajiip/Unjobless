"""Periodic maintenance: re-delivery of pending work, pruning, retention, lifecycle rechecks."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import delete, select

from unjobless.core.logging import get_logger
from unjobless.core.time import utcnow
from unjobless.db.models import FetchLog, ImportItem, LoginAttempt, OwnerSession, RawSourceVersion
from unjobless.db.session import session_scope
from unjobless.domain.enums import ImportItemStatus, ProcessingStatus
from unjobless.jobs.queue import defer

log = get_logger(__name__)

# Extra daily steps registered by later modules (lifecycle recheck, trend refresh, backups...).
DAILY_STEPS: list[Callable[[], None]] = []


def redeliver_pending() -> None:
    """Re-defer work that is QUEUED in domain tables but may have lost its queue message."""
    cutoff = utcnow() - timedelta(minutes=2)
    with session_scope() as db:
        version_ids = db.execute(
            select(RawSourceVersion.id)
            .where(RawSourceVersion.processing_status == ProcessingStatus.QUEUED, RawSourceVersion.collected_at < cutoff)
            .limit(200)
        ).scalars().all()
        item_ids = db.execute(
            select(ImportItem.id)
            .where(ImportItem.status.in_([ImportItemStatus.QUEUED, ImportItemStatus.FETCHING]), ImportItem.updated_at < cutoff)
            .limit(200)
        ).scalars().all()
    for vid in version_ids:
        defer("process_version", queueing_lock=f"version-{vid}", version_id=vid)
    for iid in item_ids:
        defer("process_import_item", queueing_lock=f"import-{iid}", item_id=iid)


def prune_operational_tables() -> None:
    now = utcnow()
    with session_scope() as db:
        db.execute(delete(LoginAttempt).where(LoginAttempt.at < now - timedelta(days=30)))
        db.execute(delete(FetchLog).where(FetchLog.at < now - timedelta(days=30)))
        db.execute(delete(OwnerSession).where(OwnerSession.expires_at < now - timedelta(days=7)))


def daily() -> None:
    prune_operational_tables()
    from unjobless.ingestion.raw_store import purge_expired

    with session_scope() as db:
        n = purge_expired(db)
    log.info("retention_purge", deleted=n)
    for step in DAILY_STEPS:
        try:
            step()
        except Exception as exc:  # one failing step must not block the others
            log.warning("daily_step_failed", step=getattr(step, "__name__", "?"), error_type=type(exc).__name__)
