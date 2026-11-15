"""Collection queue / run lifecycle tests (domain level, real Postgres)."""

from datetime import timedelta

import pytest

from unjobless.core.errors import ValidationFailed
from unjobless.core.time import utcnow
from unjobless.db.models import SourceCursor, SourceRun
from unjobless.domain.enums import PolicyStatus, RunStatus, RunTrigger, SourceHealth, SourceState
from unjobless.jobs import runner
from unjobless.sources import service

pytestmark = pytest.mark.db

ITEMS = [{"id": str(i), "title": f"Job {i}", "body": "desc"} for i in range(5)]


def enabled_mock(db, key="m", **cfg):
    s = service.create_source(db, key=key, name="Mock", connector_type="mock", config={"items": ITEMS, **cfg})
    service.review_policy(db, s, decision=PolicyStatus.APPROVED)
    service.change_state(db, s, SourceState.ENABLED)
    return s


def test_success_run_stores_items_and_cursor(db):
    s = enabled_mock(db)
    run = runner.enqueue_source_run(db, s, RunTrigger.MANUAL)
    out = runner.execute_run(db, run.id)
    assert out.status == RunStatus.SUCCEEDED
    assert (run.discovered, run.new) == (5, 5)
    assert len(out.new_version_ids) == 5
    assert db.get(SourceCursor, s.id).cursor["seen"] == 5
    assert s.health == SourceHealth.HEALTHY and s.last_success_at is not None
    assert s.next_run_at > utcnow()


def test_second_run_is_idempotent(db):
    s = enabled_mock(db)
    runner.execute_run(db, runner.enqueue_source_run(db, s, RunTrigger.MANUAL).id)
    run2 = runner.enqueue_source_run(db, s, RunTrigger.MANUAL)
    runner.execute_run(db, run2.id)
    assert (run2.new, run2.unchanged) == (0, 5)


def test_duplicate_enqueue_returns_active_run(db):
    s = enabled_mock(db)
    a = runner.enqueue_source_run(db, s, RunTrigger.MANUAL)
    b = runner.enqueue_source_run(db, s, RunTrigger.SCHEDULE)
    assert a.id == b.id
    assert db.query(SourceRun).filter_by(source_id=s.id).count() == 1


def test_execute_twice_runs_once(db):
    s = enabled_mock(db)
    run = runner.enqueue_source_run(db, s, RunTrigger.MANUAL)
    assert runner.execute_run(db, run.id) is not None
    assert runner.execute_run(db, run.id) is None


def test_failure_schedules_retry_with_backoff_then_fails(db):
    s = enabled_mock(db, fail_with="error")
    run = runner.enqueue_source_run(db, s, RunTrigger.MANUAL)
    runner.execute_run(db, run.id)
    assert run.status == RunStatus.RETRY_SCHEDULED and run.retry_at > utcnow()
    for _ in range(run.max_attempts - 1):
        run.retry_at = utcnow() - timedelta(seconds=1)
        db.flush()
        delivered = runner.scheduler_tick(db)
        assert run.id in delivered and run.status == RunStatus.QUEUED
        runner.execute_run(db, run.id)
    assert run.status == RunStatus.FAILED
    assert s.consecutive_failures == 1
    assert s.health in (SourceHealth.DEGRADED, SourceHealth.FAILING)


def test_unavailable_source_fails_without_retry(db):
    s = enabled_mock(db, fail_with="unavailable")
    run = runner.enqueue_source_run(db, s, RunTrigger.MANUAL)
    runner.execute_run(db, run.id)
    assert run.status == RunStatus.FAILED and run.error_code == "unavailable"
    assert s.health == SourceHealth.UNAVAILABLE


def test_rate_limited_uses_retry_after(db):
    s = enabled_mock(db, fail_with="rate_limited")
    run = runner.enqueue_source_run(db, s, RunTrigger.MANUAL)
    runner.execute_run(db, run.id)
    assert run.status == RunStatus.RETRY_SCHEDULED
    assert 100 < (run.retry_at - utcnow()).total_seconds() <= 121
    assert s.health == SourceHealth.RATE_LIMITED


def test_paused_source_cannot_run_and_queued_run_is_cancelled(db):
    s = enabled_mock(db)
    run = runner.enqueue_source_run(db, s, RunTrigger.MANUAL)
    service.change_state(db, s, SourceState.PAUSED)
    out = runner.execute_run(db, run.id)
    assert out.status == RunStatus.CANCELLED
    with pytest.raises(ValidationFailed):
        runner.enqueue_source_run(db, s, RunTrigger.MANUAL)


def test_disabled_source_never_collects(db):
    s = service.create_source(db, key="d", name="D", connector_type="mock", config={"items": ITEMS})
    with pytest.raises(ValidationFailed):
        runner.enqueue_source_run(db, s, RunTrigger.SCHEDULE)


def test_timeout_moves_to_retry(db):
    s = enabled_mock(db, items=[{"id": str(i), "title": "t"} for i in range(25)])
    run = runner.enqueue_source_run(db, s, RunTrigger.MANUAL)
    run.timeout_seconds = 0
    db.flush()
    clock = iter(range(0, 10_000, 5))
    runner.execute_run(db, run.id, now_fn=lambda: next(clock))
    assert run.status == RunStatus.RETRY_SCHEDULED and run.error_code == "timeout"


def test_cancel_running_run(db):
    s = enabled_mock(db, items=[{"id": str(i), "title": "t"} for i in range(25)])
    run = runner.enqueue_source_run(db, s, RunTrigger.MANUAL)
    run.cancel_requested = True
    db.flush()
    runner.execute_run(db, run.id)
    assert run.status == RunStatus.CANCELLED


def test_worker_restart_recovers_stale_run(db):
    s = enabled_mock(db)
    run = runner.enqueue_source_run(db, s, RunTrigger.MANUAL)
    runner.claim_run(db, run.id)  # worker claimed then died
    run.heartbeat_at = utcnow() - timedelta(hours=2)
    db.flush()
    runner.scheduler_tick(db)
    assert run.status == RunStatus.RETRY_SCHEDULED and run.error_code == "stale"


def test_scheduler_enqueues_due_sources_once(db):
    s = enabled_mock(db)
    s.next_run_at = utcnow() - timedelta(minutes=1)
    db.flush()
    first = runner.scheduler_tick(db)
    second = runner.scheduler_tick(db)
    assert len(first) == 1
    assert first[0] not in second or db.get(SourceRun, first[0]).status == RunStatus.QUEUED
    assert db.query(SourceRun).filter_by(source_id=s.id).count() == 1


def test_one_bad_item_does_not_fail_run(db, monkeypatch):
    s = enabled_mock(db)
    real = runner.store_item

    def flaky(db_, src, item, **kw):
        if item.native_id == "2":
            raise ValueError("bad item")
        return real(db_, src, item, **kw)

    monkeypatch.setattr(runner, "store_item", flaky)
    run = runner.enqueue_source_run(db, s, RunTrigger.MANUAL)
    runner.execute_run(db, run.id)
    assert run.status == RunStatus.PARTIAL and run.errors == 1 and run.new == 4
