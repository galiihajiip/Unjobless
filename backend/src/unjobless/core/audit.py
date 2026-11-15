from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from unjobless.core.logging import _scrub
from unjobless.db.models import AuditEvent
from unjobless.domain.enums import Actor


def audit(
    db: Session,
    action: str,
    *,
    target_type: str | None = None,
    target_id: object = None,
    details: dict[str, Any] | None = None,
    actor: Actor = Actor.USER,
) -> None:
    """Record an audit event. Details are scrubbed; callers must never pass secrets or CV text."""
    db.add(
        AuditEvent(
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=None if target_id is None else str(target_id),
            details=_scrub(details or {}),
        )
    )
