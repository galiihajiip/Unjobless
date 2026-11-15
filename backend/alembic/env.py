from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from unjobless.core.config import get_settings
from unjobless.db.models import Base

config = context.config
target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    """Procrastinate's queue tables are managed by vendored SQL migrations, not ORM metadata."""
    return not (name or "").startswith("procrastinate")


def _url() -> str:
    return config.attributes.get("database_url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, compare_type=True, include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection")
    if connectable is not None:
        context.configure(connection=connectable, target_metadata=target_metadata, compare_type=True, include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = engine_from_config({"sqlalchemy.url": _url()}, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True, include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
