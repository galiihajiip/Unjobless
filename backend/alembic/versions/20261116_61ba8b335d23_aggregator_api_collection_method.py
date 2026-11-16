"""aggregator api collection method

Revision ID: 61ba8b335d23
Revises: e3c85d617790
Create Date: 2026-11-16 11:50:41.540273
"""

from collections.abc import Sequence

from alembic import op

revision: str = "61ba8b335d23"
down_revision: str | None = "e3c85d617790"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD = [
    "OFFICIAL_API",
    "ATS_PUBLIC_API",
    "HTML_CRAWL",
    "RSS",
    "SITEMAP",
    "STRUCTURED_DATA",
    "USER_URL_IMPORT",
    "USER_PASTE",
    "USER_UPLOAD",
    "EMAIL_ALERT",
]
NEW = [*OLD, "AGGREGATOR_API"]
TABLES = ["sources", "raw_source_documents"]


def _replace(values: list[str]) -> None:
    allowed = ", ".join(f"'{v}'" for v in values)
    for t in TABLES:
        op.drop_constraint(op.f(f"ck_{t}_collection_method_enum"), t, type_="check")
        op.create_check_constraint(
            op.f(f"ck_{t}_collection_method_enum"), t, f"collection_method IN ({allowed})"
        )


def upgrade() -> None:
    _replace(NEW)


def downgrade() -> None:
    _replace(OLD)
