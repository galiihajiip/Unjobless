"""All ORM models; importing this module registers every table on Base.metadata."""

from .base import Base
from .ingestion import *  # noqa: F403
from .intelligence import *  # noqa: F403
from .owner import *  # noqa: F403
from .personal import *  # noqa: F403
from .sources import *  # noqa: F403

__all__ = ["Base"]


def _name_enum_checks() -> None:
    """Give every enum CHECK constraint a stable, column-specific name.

    Two columns of the same enum type in one table would otherwise share a constraint name.
    """
    from sqlalchemy import CheckConstraint
    from sqlalchemy.sql.elements import conv

    for table in Base.metadata.tables.values():
        for c in table.constraints:
            if isinstance(c, CheckConstraint) and getattr(c, "_type_bound", False):
                cols = [col.name for col in c.columns]
                if cols:
                    c.name = conv(f"ck_{table.name}_{cols[0]}_enum"[:63])


_name_enum_checks()
