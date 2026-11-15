"""Shared fixtures.

DB tests use the `unjobless_test` database (created by deploy/postgres/init in the dev compose).
Override with UNJOBLESS_TEST_DATABASE_URL. The schema is migrated once per session from empty,
and each test runs inside a transaction that is rolled back.
"""

from __future__ import annotations

import base64
import os

os.environ.setdefault("UNJOBLESS_ENV", "test")
os.environ.setdefault("UNJOBLESS_LOG_JSON", "false")
os.environ.setdefault("UNJOBLESS_MASTER_KEY", base64.urlsafe_b64encode(b"k" * 32).decode())
os.environ.setdefault("UNJOBLESS_SESSION_SECRET", base64.urlsafe_b64encode(b"s" * 32).decode())
TEST_DB_URL = os.environ.get(
    "UNJOBLESS_TEST_DATABASE_URL", "postgresql+psycopg://unjobless:unjobless@127.0.0.1:5433/unjobless_test"
)
os.environ["DATABASE_URL"] = TEST_DB_URL

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402


def _reset_schema(engine) -> None:  # type: ignore[no-untyped-def]
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS procrastinate CASCADE"))
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


@pytest.fixture(scope="session")
def engine():  # type: ignore[no-untyped-def]
    from unjobless.db.migrate import upgrade_head

    eng = create_engine(TEST_DB_URL, future=True)
    try:
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"test database unavailable: {exc}")
    _reset_schema(eng)
    upgrade_head(TEST_DB_URL)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    """Session bound to an outer transaction that is rolled back after the test.

    Uses SAVEPOINTs so code under test may call commit().
    """
    connection = engine.connect()
    trans = connection.begin()
    session = sessionmaker(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )()
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


@pytest.fixture
def clean_db(engine) -> Iterator[None]:  # type: ignore[no-untyped-def]
    """For tests that need real commits across connections (API/worker). Truncates all app tables after."""
    yield
    from unjobless.db.models import Base

    names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
