"""Worker tasks. Thin wrappers around domain services; all state lives in Postgres tables."""

from __future__ import annotations

from unjobless.core.logging import get_logger
from unjobless.db.session import session_scope
from unjobless.jobs.app import get_app

log = get_logger(__name__)
app = get_app()


def _register_hooks() -> None:
    from unjobless.intelligence.pipeline import enqueue_versions
    from unjobless.jobs import maintenance, runner

    if enqueue_versions not in runner.NEW_VERSION_HOOKS:
        runner.NEW_VERSION_HOOKS.append(enqueue_versions)
    if not maintenance.DAILY_STEPS:
        maintenance.DAILY_STEPS.extend([maintenance.lifecycle_recheck, maintenance.trends_refresh])


_register_hooks()


@app.task(name="run_source", queue="collection", pass_context=False)
def run_source(run_id: int) -> None:
    from unjobless.jobs.runner import execute_run

    with session_scope() as db:
        execute_run(db, run_id)


@app.periodic(cron="* * * * *", periodic_id="tick")
@app.task(name="scheduler_tick", queue="maintenance", queueing_lock="scheduler_tick")
def scheduler_tick(timestamp: int) -> None:
    from unjobless.jobs.maintenance import redeliver_pending
    from unjobless.jobs.queue import defer
    from unjobless.jobs.runner import scheduler_tick as tick

    with session_scope() as db:
        for run_id in tick(db):
            defer("run_source", queueing_lock=f"run-{run_id}", run_id=run_id)
    redeliver_pending()


@app.periodic(cron="17 3 * * *", periodic_id="daily")
@app.task(name="daily_maintenance", queue="maintenance", queueing_lock="daily_maintenance")
def daily_maintenance(timestamp: int) -> None:
    from unjobless.jobs.maintenance import daily

    daily()


@app.task(name="process_version", queue="processing", retry=3)
def process_version(version_id: int) -> None:
    from unjobless.intelligence.pipeline import process_version as run

    with session_scope() as db:
        run(db, version_id)


@app.task(name="process_import_item", queue="imports", retry=2)
def process_import_item(item_id: int) -> None:
    from unjobless.ingestion.imports import process_import_item as run

    run(item_id)


@app.task(name="process_resume", queue="processing", retry=2)
def process_resume(resume_id: int) -> None:
    from unjobless.profile.cv import process_resume as run

    run(resume_id)


@app.task(name="process_media", queue="media", retry=1)
def process_media(media_id: int) -> None:
    from unjobless.ingestion.media import process_media_asset as run

    run(media_id)


@app.task(name="recompute_matches", queue="processing", queueing_lock="recompute_matches")
def recompute_matches() -> None:
    from unjobless.profile.matching import recompute_all

    with session_scope() as db:
        recompute_all(db)
