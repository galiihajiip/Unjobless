"""procrastinate queue schema

Revision ID: 7893af309bfe
Revises: 7f119800a8be
Create Date: 2026-11-16 05:26:08.581944
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pathlib import Path

from alembic import op


revision: str = '7893af309bfe'
down_revision: str | None = '7f119800a8be'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SQL_FILE = Path(__file__).resolve().parents[1] / "sql" / "procrastinate_3.11.0_schema.sql"


def upgrade() -> None:
    # Vendored from procrastinate 3.11.0 (sql/schema.sql). Future procrastinate upgrades add a new
    # Alembic revision that applies procrastinate's own sql/migrations files for that version range.
    op.get_bind().exec_driver_sql(SQL_FILE.read_text())


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        DROP TABLE IF EXISTS procrastinate_events, procrastinate_periodic_defers, procrastinate_jobs,
            procrastinate_workers CASCADE;
        DO $$ DECLARE r record; BEGIN
          FOR r IN SELECT p.oid::regprocedure AS sig FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                   WHERE n.nspname = current_schema() AND p.proname LIKE 'procrastinate%' LOOP
            EXECUTE 'DROP FUNCTION IF EXISTS ' || r.sig || ' CASCADE';
          END LOOP;
        END $$;
        DROP TYPE IF EXISTS procrastinate_job_to_defer_v1, procrastinate_job_event_type, procrastinate_job_status CASCADE;
        """
    )
