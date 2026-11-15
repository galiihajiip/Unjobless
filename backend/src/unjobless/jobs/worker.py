"""`unjobless worker` — runs the Procrastinate worker with bounded concurrency.

Procrastinate handles SIGINT/SIGTERM by finishing in-flight jobs (graceful shutdown); anything
interrupted harder is recovered by the scheduler tick's stale-run logic.
"""

from __future__ import annotations

from unjobless.core.config import get_settings
from unjobless.core.logging import configure_logging, get_logger


def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    from unjobless.jobs import tasks  # noqa: F401  (register tasks)
    from unjobless.jobs.app import get_app

    get_logger(__name__).info("worker_starting", concurrency=settings.global_worker_concurrency)
    get_app().run_worker(
        queues=["collection", "imports", "processing", "media", "maintenance", "default"],
        concurrency=settings.global_worker_concurrency,
        wait=True,
        install_signal_handlers=True,
    )
