"""All ORM models; importing this module registers every table on Base.metadata."""

from .base import Base
from .ingestion import *  # noqa: F403
from .intelligence import *  # noqa: F403
from .owner import *  # noqa: F403
from .personal import *  # noqa: F403
from .sources import *  # noqa: F403

__all__ = ["Base"]


def _add_enum_checks() -> None:
    """Add an explicit, column-specific CHECK constraint for every enum column.

    Enums are stored as VARCHAR (portable, easy to migrate); the constraint restricts values.
    """
    from sqlalchemy import CheckConstraint, Enum

    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, Enum) and col.type.enums:
                name = f"{col.name}_enum"
                if any(getattr(c, "name", None) and str(c.name).endswith(name) for c in table.constraints):
                    continue
                values = ", ".join("'" + v.replace("'", "''") + "'" for v in col.type.enums)
                table.append_constraint(CheckConstraint(f"{col.name} IN ({values})", name=name))


_add_enum_checks()
