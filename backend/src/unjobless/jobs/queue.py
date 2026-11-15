"""Deferring work from sync code (API/services). Failures are tolerated: the periodic scheduler
tick re-delivers anything still QUEUED in the database, so a lost message only delays work."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from unjobless.core.logging import get_logger

log = get_logger(__name__)
_lock = threading.Lock()
_opened = False

# Test hook: when set, defers are recorded/executed by this callable instead of the real queue.
DEFER_OVERRIDE: Callable[[str, dict[str, Any], str | None], None] | None = None


def _ensure_open() -> Any:
    global _opened
    from unjobless.jobs.app import get_app

    app = get_app()
    with _lock:
        if not _opened:
            app.open()
            _opened = True
    return app


def defer(task_name: str, *, queueing_lock: str | None = None, **kwargs: Any) -> bool:
    if DEFER_OVERRIDE is not None:
        DEFER_OVERRIDE(task_name, kwargs, queueing_lock)
        return True
    try:
        app = _ensure_open()
        app.configure_task(name=task_name, queueing_lock=queueing_lock).defer(**kwargs)
        return True
    except Exception as exc:
        # AlreadyEnqueued (queueing lock) is expected and fine; anything else is retried by the tick.
        log.info("defer_skipped", task=task_name, reason=type(exc).__name__)
        return False
