"""Deferring work from sync code (API requests, CLI, and sync tasks running inside the worker).

A dedicated, independent Procrastinate App on a *sync* psycopg connector is used for deferring. It
does not share state with the worker's async app, so it is safe to call from worker threads.
Task names map to queues here (the worker applies each task's retry policy when it runs the job).

Failures are tolerated: the periodic scheduler tick re-delivers anything still QUEUED in the domain
tables, so a lost message only delays work.
"""

from __future__ import annotations

import atexit
import threading
from collections.abc import Callable
from typing import Any

from unjobless.core.logging import get_logger

log = get_logger(__name__)
_lock = threading.Lock()
_app: Any = None

TASK_QUEUES = {
    "run_source": "collection",
    "process_import_item": "imports",
    "process_version": "processing",
    "process_resume": "processing",
    "recompute_matches": "processing",
    "process_media": "media",
}

# Test hook: when set, defers are recorded/executed by this callable instead of the real queue.
DEFER_OVERRIDE: Callable[[str, dict[str, Any], str | None], None] | None = None


def _defer_app() -> Any:
    global _app
    with _lock:
        if _app is None:
            import procrastinate

            from unjobless.jobs.app import conninfo

            app = procrastinate.App(connector=procrastinate.SyncPsycopgConnector(conninfo=conninfo(), min_size=1, max_size=4))
            app.open()
            atexit.register(app.close)
            _app = app
    return _app


def defer(task_name: str, *, queueing_lock: str | None = None, **kwargs: Any) -> bool:
    if DEFER_OVERRIDE is not None:
        DEFER_OVERRIDE(task_name, kwargs, queueing_lock)
        return True
    try:
        _defer_app().configure_task(
            name=task_name, queue=TASK_QUEUES.get(task_name, "default"), queueing_lock=queueing_lock
        ).defer(**kwargs)
        return True
    except Exception as exc:
        # AlreadyEnqueued (queueing lock held) is expected and fine; anything else is re-delivered by the tick.
        log.info("defer_skipped", task=task_name, reason=type(exc).__name__)
        return False
