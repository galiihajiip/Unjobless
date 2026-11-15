"""Collection run lifecycle (domain level, queue-agnostic).

`source_runs` is the source of truth. The queue (Procrastinate) only delivers "execute run N"
messages; losing a message is harmless because `scheduler_tick` re-delivers QUEUED runs and
recovers stale RUNNING ones. Every step is idempotent:

- enqueue: partial unique index ⇒ at most one active run per source; duplicate enqueue returns it;
- claim: `SELECT … FOR UPDATE SKIP LOCKED` + status check ⇒ a run executes at most once at a time;
- items: raw store is content-hash idempotent.
"""

from __future__ import annotations

import random
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from unjobless.core.errors import ValidationFailed
from unjobless.core.logging import get_logger
from unjobless.core.time import utcnow
from unjobless.db.models import Source, SourceCursor, SourceHealthEvent, SourceRun, SourceRunItem
from unjobless.domain.enums import (
    ACTIVE_RUN_STATUSES,
    RunItemOutcome,
    RunStatus,
    RunTrigger,
    SourceHealth,
    SourceState,
)
from unjobless.domain.state_machines import RUN
from unjobless.fetch.safe_fetch import SafeFetcher
from unjobless.ingestion.raw_store import store_item
from unjobless.sources.contract import (
    CollectContext,
    CollectionCancelled,
    SourceRateLimited,
    SourceUnavailable,
)
from unjobless.sources.registry import get_connector_class
from unjobless.sources.service import can_collect

log = get_logger(__name__)

HEARTBEAT_EVERY_ITEMS = 10
STALE_FACTOR = 2


class RunTimeout(Exception):
    pass


# Hooks invoked with the ids of raw versions that are new/changed (processing pipeline subscribes).
NEW_VERSION_HOOKS: list[Callable[[list[int]], None]] = []


@dataclass
class RunOutcome:
    run_id: int
    status: RunStatus
    new_version_ids: list[int] = field(default_factory=list)


def backoff_seconds(attempt: int, base: float, cap: float) -> float:
    """Exponential backoff with full jitter: random(0, min(cap, base·2^(attempt-1)))."""
    upper = min(cap, base * (2 ** max(0, attempt - 1)))
    return max(base / 2, random.uniform(0, upper))


def enqueue_source_run(
    db: Session, source: Source, trigger: RunTrigger, *, key: str | None = None
) -> SourceRun:
    if trigger == RunTrigger.MANUAL and source.state != SourceState.ENABLED:
        raise ValidationFailed("Enable this source before running it.", code="source_not_enabled")
    ok, reason = can_collect(db, source)
    if not ok:
        raise ValidationFailed(reason or "Source cannot collect.", code="source_cannot_collect")
    existing = active_run(db, source.id)
    if existing is not None:
        return existing
    info = get_connector_class(source.connector_type).info
    run = SourceRun(
        source_id=source.id,
        trigger=trigger,
        status=RunStatus.QUEUED,
        idempotency_key=key or f"{trigger.value.lower()}:{source.id}:{uuid.uuid4().hex}",
        max_attempts=info.retry.max_attempts,
    )
    try:
        with db.begin_nested():
            db.add(run)
            db.flush()
    except IntegrityError:
        existing = active_run(db, source.id)
        if existing is not None:
            return existing
        raise
    return run


def active_run(db: Session, source_id: int) -> SourceRun | None:
    return db.execute(
        select(SourceRun).where(SourceRun.source_id == source_id, SourceRun.status.in_(ACTIVE_RUN_STATUSES))
    ).scalar_one_or_none()


def cancel_run(db: Session, run: SourceRun) -> SourceRun:
    if run.status in (RunStatus.QUEUED, RunStatus.RETRY_SCHEDULED):
        run.status = RunStatus.CANCELLED
        run.finished_at = utcnow()
    elif run.status == RunStatus.RUNNING:
        run.cancel_requested = True
    return run


def _set_health(db: Session, source: Source, health: SourceHealth, reason: str | None) -> None:
    if source.health != health or source.health_reason != reason:
        db.add(SourceHealthEvent(source_id=source.id, health=health, reason=reason))
    source.health = health
    source.health_reason = reason


def _transition(run: SourceRun, status: RunStatus) -> None:
    RUN.check(run.status, status)
    run.status = status


def claim_run(db: Session, run_id: int) -> SourceRun | None:
    run = db.execute(
        select(SourceRun).where(SourceRun.id == run_id).with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if run is None or run.status not in (RunStatus.QUEUED, RunStatus.RETRY_SCHEDULED):
        return None
    if run.status == RunStatus.RETRY_SCHEDULED and run.retry_at and run.retry_at > utcnow():
        return None
    _transition(run, RunStatus.RUNNING)
    now = utcnow()
    run.started_at = now
    run.heartbeat_at = now
    db.commit()
    return run


def execute_run(
    db: Session,
    run_id: int,
    *,
    fetcher: SafeFetcher | None = None,
    now_fn: Callable[[], float] = time.monotonic,
) -> RunOutcome | None:
    """Execute one claimed run to a terminal (or retry-scheduled) state. Safe to call twice."""
    run = claim_run(db, run_id)
    if run is None:
        return None
    source = db.get(Source, run.source_id)
    assert source is not None
    ok, reason = can_collect(db, source)
    if not ok:
        _transition(run, RunStatus.CANCELLED)
        run.error_code, run.error_message, run.finished_at = "not_collectable", reason, utcnow()
        db.commit()
        return RunOutcome(run.id, run.status)

    connector_cls = get_connector_class(source.connector_type)
    info = connector_cls.info
    cursor_row = db.get(SourceCursor, source.id)
    cursor = dict(cursor_row.cursor) if cursor_row else {}
    run.cursor_before = cursor
    source.last_attempt_at = utcnow()
    started = now_fn()
    own_fetcher = fetcher is None
    fetcher = fetcher or SafeFetcher()

    def cancelled() -> bool:
        db.refresh(run, ["cancel_requested"])
        if now_fn() - started > run.timeout_seconds:
            raise RunTimeout()
        return bool(run.cancel_requested)

    def get_secret() -> str | None:
        if source.secret_id is None:
            return None
        from unjobless.core.crypto import decrypt_secret
        from unjobless.db.models import EncryptedSecret

        sec = db.get(EncryptedSecret, source.secret_id)
        return decrypt_secret(sec.ciphertext, purpose=sec.purpose) if sec else None

    ctx = CollectContext(
        config=info.config_model.model_validate(source.config or {}),
        cursor=cursor,
        fetcher=fetcher,
        get_secret=get_secret,
        is_cancelled=cancelled,
        log=log.bind(source=source.key, run=run.id),
        source_domain=source.domain,
        min_interval_seconds=60.0 / max(1, source.rate_limit_per_minute),
    )
    from unjobless.db.session import get_sessionmaker
    from unjobless.fetch.politeness import polite_get

    polite_db = get_sessionmaker()()

    def _polite(url: str, **kw: Any) -> Any:
        return polite_get(polite_db, fetcher, url, min_interval_seconds=ctx.min_interval_seconds, **kw)

    ctx.polite_get = _polite
    new_versions: list[int] = []
    seen_docs: set[int] = set()
    unchanged_docs: list[int] = []
    try:
        connector = connector_cls()
        for n, item in enumerate(connector.collect(ctx), start=1):
            run.discovered += 1
            try:
                with db.begin_nested():
                    res = store_item(db, source, item)
                    outcome = res.outcome
                    seen_docs.add(res.document.id)
                    db.add(
                        SourceRunItem(
                            run_id=run.id,
                            external_id=item.native_id,
                            url=item.url,
                            outcome=outcome,
                            raw_version_id=res.version.id,
                        )
                    )
                if outcome == RunItemOutcome.NEW:
                    run.new += 1
                    new_versions.append(res.version.id)
                elif outcome == RunItemOutcome.CHANGED:
                    run.changed += 1
                    new_versions.append(res.version.id)
                else:
                    run.unchanged += 1
                    unchanged_docs.append(res.document.id)
            except Exception as exc:  # one bad item never fails the run
                run.errors += 1
                db.add(
                    SourceRunItem(
                        run_id=run.id,
                        external_id=item.native_id,
                        url=item.url,
                        outcome=RunItemOutcome.ERROR,
                        error=f"{type(exc).__name__}: {str(exc)[:300]}",
                    )
                )
            if n % HEARTBEAT_EVERY_ITEMS == 0:
                run.heartbeat_at = utcnow()
                db.commit()
                ctx.check_cancel()
            if n >= ctx.max_items:
                break
        # success
        _post_run_lifecycle(db, source, seen_docs, unchanged_docs, ctx.listing_complete and not run.errors)
        final = RunStatus.PARTIAL if run.errors else RunStatus.SUCCEEDED
        _transition(run, final)
        run.finished_at = utcnow()
        if ctx.new_cursor is not None:
            run.cursor_after = ctx.new_cursor
            if cursor_row is None:
                db.add(SourceCursor(source_id=source.id, cursor=ctx.new_cursor))
            else:
                cursor_row.cursor = ctx.new_cursor
        source.last_success_at = utcnow()
        source.consecutive_failures = 0
        _set_health(
            db,
            source,
            SourceHealth.DEGRADED if run.errors else SourceHealth.HEALTHY,
            f"{run.errors} item errors" if run.errors else None,
        )
        _schedule_next(source)
    except CollectionCancelled:
        _transition(run, RunStatus.CANCELLED)
        run.finished_at = utcnow()
        _schedule_next(source)
    except SourceRateLimited as exc:
        delay = exc.retry_after or backoff_seconds(
            run.attempt, info.retry.base_delay_seconds, info.retry.max_delay_seconds
        )
        _set_health(db, source, SourceHealth.RATE_LIMITED, str(exc)[:300])
        _fail_or_retry(run, source, "rate_limited", str(exc), delay, force_retry=True)
    except SourceUnavailable as exc:
        _transition(run, RunStatus.FAILED)
        run.error_code, run.error_message, run.finished_at = "unavailable", str(exc)[:1000], utcnow()
        source.consecutive_failures += 1
        _set_health(db, source, SourceHealth.UNAVAILABLE, str(exc)[:300])
        _schedule_next(source)
    except RunTimeout:
        delay = backoff_seconds(run.attempt, info.retry.base_delay_seconds, info.retry.max_delay_seconds)
        _fail_or_retry(run, source, "timeout", f"Run exceeded {run.timeout_seconds}s", delay)
        _derive_failure_health(db, source)
    except Exception as exc:
        log.warning("run_failed", run=run.id, error_type=type(exc).__name__)
        delay = backoff_seconds(run.attempt, info.retry.base_delay_seconds, info.retry.max_delay_seconds)
        _fail_or_retry(run, source, "error", f"{type(exc).__name__}: {str(exc)[:500]}", delay)
        _derive_failure_health(db, source)
    finally:
        polite_db.close()
        if own_fetcher:
            fetcher.close()
    db.commit()
    for hook in NEW_VERSION_HOOKS:
        if new_versions:
            hook(new_versions)
    return RunOutcome(run.id, run.status, new_versions)


def _post_run_lifecycle(db: Session, source: Source, seen: set[int], unchanged: list[int], complete: bool) -> None:
    """Re-confirm vacancies seen again unchanged; mark those missing from a complete listing uncertain."""
    from unjobless.intelligence import lifecycle
    from unjobless.intelligence.vacancies import vacancy_for_document

    for doc_id in unchanged:
        v = vacancy_for_document(db, doc_id)
        if v is not None:
            lifecycle.confirm_seen_in_trusted_listing(db, v, source)
    if complete:
        lifecycle.mark_missing_from_complete_listing(db, source, seen)


def _schedule_next(source: Source) -> None:
    if source.state == SourceState.ENABLED and source.schedule_interval_seconds:
        source.next_run_at = utcnow() + timedelta(seconds=source.schedule_interval_seconds)


def _fail_or_retry(
    run: SourceRun, source: Source, code: str, message: str, delay: float, *, force_retry: bool = False
) -> None:
    run.error_code, run.error_message = code, message[:1000]
    if run.attempt < run.max_attempts or (force_retry and run.attempt < run.max_attempts + 2):
        _transition(run, RunStatus.RETRY_SCHEDULED)
        run.retry_at = utcnow() + timedelta(seconds=delay)
    else:
        _transition(run, RunStatus.FAILED)
        run.finished_at = utcnow()
        source.consecutive_failures += 1
        _schedule_next(source)


def _derive_failure_health(db: Session, source: Source) -> None:
    if source.consecutive_failures >= 3:
        _set_health(db, source, SourceHealth.FAILING, "3 or more consecutive failed runs")
    else:
        _set_health(db, source, SourceHealth.DEGRADED, "Recent run failed")


def scheduler_tick(db: Session) -> list[int]:
    """Periodic maintenance. Returns run ids that should be (re)delivered to workers."""
    now = utcnow()
    to_deliver: list[int] = []

    # 1. Stale RUNNING runs (worker crashed / killed): retry or fail.
    for run in db.execute(
        select(SourceRun).where(SourceRun.status == RunStatus.RUNNING).with_for_update(skip_locked=True)
    ).scalars():
        last = run.heartbeat_at or run.started_at or run.created_at
        if last + timedelta(seconds=run.timeout_seconds * STALE_FACTOR) < now:
            source = db.get(Source, run.source_id)
            assert source is not None
            _fail_or_retry(run, source, "stale", "Worker stopped responding during this run.", 60)

    # 2. Retries whose backoff elapsed.
    for run in db.execute(
        select(SourceRun).where(SourceRun.status == RunStatus.RETRY_SCHEDULED, SourceRun.retry_at <= now)
    ).scalars():
        _transition(run, RunStatus.QUEUED)
        run.attempt += 1
        run.retry_at = None
        to_deliver.append(run.id)

    # 3. Due sources.
    due = (
        db.execute(
            select(Source).where(
                Source.state == SourceState.ENABLED,
                Source.is_system.is_(False),
                Source.schedule_interval_seconds.is_not(None),
                Source.next_run_at <= now,
            )
        )
        .scalars()
        .all()
    )
    for src in due:
        if active_run(db, src.id) is not None:
            continue
        ok, _ = can_collect(db, src)
        if not ok:
            continue
        run = enqueue_source_run(
            db,
            src,
            RunTrigger.SCHEDULE,
            key=f"schedule:{src.id}:{src.next_run_at.isoformat() if src.next_run_at else now.isoformat()}",
        )
        src.next_run_at = now + timedelta(seconds=src.schedule_interval_seconds or 3600)
        to_deliver.append(run.id)

    # 4. Re-deliver QUEUED runs that may have lost their queue message.
    lost = db.execute(
        select(SourceRun.id).where(
            SourceRun.status == RunStatus.QUEUED, SourceRun.created_at < now - timedelta(minutes=2)
        )
    ).scalars()
    to_deliver.extend(i for i in lost if i not in to_deliver)
    db.commit()
    return to_deliver


def reset_source_runs_for_disable(db: Session, source_id: int) -> None:
    """When a source is disabled/paused, cancel queued work and request cancellation of running work."""
    db.execute(
        update(SourceRun)
        .where(
            SourceRun.source_id == source_id,
            SourceRun.status.in_([RunStatus.QUEUED, RunStatus.RETRY_SCHEDULED]),
        )
        .values(status=RunStatus.CANCELLED, finished_at=utcnow(), error_code="source_stopped")
    )
    db.execute(
        update(SourceRun)
        .where(SourceRun.source_id == source_id, SourceRun.status == RunStatus.RUNNING)
        .values(cancel_requested=True)
    )


def run_summary(run: SourceRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "status": run.status.value,
        "trigger": run.trigger.value,
        "attempt": run.attempt,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "retry_at": run.retry_at.isoformat() if run.retry_at else None,
        "discovered": run.discovered,
        "new": run.new,
        "changed": run.changed,
        "unchanged": run.unchanged,
        "duplicates": run.duplicates,
        "errors": run.errors,
        "error_code": run.error_code,
        "error_message": run.error_message,
        "duration_seconds": (run.finished_at - run.started_at).total_seconds()
        if run.finished_at and run.started_at
        else None,
    }
