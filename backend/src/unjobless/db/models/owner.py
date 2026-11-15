from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from unjobless.domain.enums import Actor

from .base import Base, Timestamps, enum_col, pk


class OwnerAccount(Base, Timestamps):
    """The single private owner. `singleton` + CHECK guarantees at most one row."""

    __tablename__ = "owner_account"
    __table_args__ = (CheckConstraint("singleton = 1", name="single_owner"),)
    id: Mapped[int] = pk()
    singleton: Mapped[int] = mapped_column(Integer, nullable=False, default=1, unique=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    password_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OwnerSession(Base):
    __tablename__ = "owner_sessions"
    id: Mapped[int] = pk()
    owner_id: Mapped[int] = mapped_column(ForeignKey("owner_account.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    ip: Mapped[str | None] = mapped_column(INET)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id: Mapped[int] = pk()
    ip: Mapped[str | None] = mapped_column(INET, index=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class AppSettings(Base, Timestamps):
    """Key/value settings; values are validated by typed settings schemas in the service layer."""

    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = pk()
    actor: Mapped[Actor] = mapped_column(enum_col(Actor), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(60))
    target_id: Mapped[str | None] = mapped_column(String(60))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class UserNote(Base, Timestamps):
    __tablename__ = "user_notes"
    id: Mapped[int] = pk()
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[int] = mapped_column(nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
