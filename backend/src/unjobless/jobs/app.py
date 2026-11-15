"""Procrastinate application (Postgres-backed queue)."""

from __future__ import annotations

from functools import lru_cache

import procrastinate

from unjobless.core.config import get_settings


def conninfo() -> str:
    url = get_settings().database_url
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


@lru_cache
def get_app() -> procrastinate.App:
    return procrastinate.App(
        connector=procrastinate.PsycopgConnector(conninfo=conninfo()),
        import_paths=["unjobless.jobs.tasks"],
    )
