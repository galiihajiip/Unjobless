from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, DateTime, Enum, Identity, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def pk() -> Mapped[int]:
    return mapped_column(BigInteger, Identity(always=False), primary_key=True)


def enum_col(enum_cls: type[StrEnum], **kw: Any) -> Any:
    """Enum stored as VARCHAR + CHECK constraint (portable, easy to migrate)."""
    return Enum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        length=40,
        name=f"{enum_cls.__name__.lower()}",
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
        **kw,
    )


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
