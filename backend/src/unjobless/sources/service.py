"""Source registry service: creation, configuration, policy review, state changes, exclusions."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from unjobless.core.audit import audit
from unjobless.core.errors import Conflict, NotFound, ValidationFailed
from unjobless.core.time import utcnow
from unjobless.db.models import Source, SourceExclusion, SourcePolicyReview
from unjobless.domain.enums import PolicyStatus, SourceState
from unjobless.domain.state_machines import ENABLEABLE_POLICIES, SOURCE_STATE
from unjobless.fetch.urls import host_of, matches_exclusion
from unjobless.sources.connectors.system import SYSTEM_SOURCE_KEYS
from unjobless.sources.contract import ConnectorInfo
from unjobless.sources.registry import get_connector_class

MIN_INTERVAL_SECONDS = 300


def validate_config(info: ConnectorInfo, config: dict[str, Any]) -> dict[str, Any]:
    try:
        return info.config_model.model_validate(config).model_dump(mode="json")
    except ValidationError as exc:
        raise ValidationFailed(
            "Invalid connector configuration.",
            details={"errors": [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]},
        ) from exc


def is_excluded(db: Session, url_or_domain: str) -> SourceExclusion | None:
    target = url_or_domain if "://" in url_or_domain else f"https://{url_or_domain}/"
    for ex in db.execute(select(SourceExclusion)).scalars():
        if matches_exclusion(target, ex.pattern):
            return ex
    return None


def create_source(
    db: Session,
    *,
    key: str,
    name: str,
    connector_type: str,
    config: dict[str, Any] | None = None,
    domain: str | None = None,
    schedule_interval_seconds: int | None = None,
    rate_limit_per_minute: int | None = None,
    policy_notes: str | None = None,
) -> Source:
    info = get_connector_class(connector_type).info
    if not info.user_visible:
        raise ValidationFailed("This connector type is internal and cannot be created manually.")
    if db.execute(select(Source).where(Source.key == key)).scalar_one_or_none():
        raise Conflict(f"A source with key {key!r} already exists.")
    if domain and is_excluded(db, domain):
        raise ValidationFailed(f"{domain} is on the exclusion list and cannot be added as a source.")
    interval = schedule_interval_seconds if schedule_interval_seconds is not None else info.default_schedule_seconds
    if interval is not None and interval < MIN_INTERVAL_SECONDS:
        raise ValidationFailed(f"Schedule interval must be at least {MIN_INTERVAL_SECONDS} seconds.")
    src = Source(
        key=key,
        name=name,
        domain=(domain or "").lower() or None,
        category=info.category,
        connector_type=info.type,
        collection_method=info.collection_method,
        documentation_url=info.documentation_url,
        terms_url=info.terms_url,
        policy_status=PolicyStatus.UNREVIEWED,  # unclear permission → disabled until reviewed
        policy_notes=policy_notes,
        state=SourceState.DISABLED,
        config=validate_config(info, config or {}),
        schedule_interval_seconds=interval,
        rate_limit_per_minute=rate_limit_per_minute or info.default_rate_limit_per_minute,
    )
    db.add(src)
    db.flush()
    audit(db, "source.created", target_type="source", target_id=src.id, details={"type": connector_type})
    return src


def ensure_system_source(db: Session, connector_type: str) -> Source:
    """Internal sources that own user imports. Always APPROVED+ENABLED but never scheduled."""
    key = SYSTEM_SOURCE_KEYS[connector_type]
    src = db.execute(select(Source).where(Source.key == key)).scalar_one_or_none()
    if src:
        return src
    info = get_connector_class(connector_type).info
    src = Source(
        key=key,
        name=info.name,
        category=info.category,
        connector_type=info.type,
        collection_method=info.collection_method,
        policy_status=PolicyStatus.APPROVED,
        policy_notes="Owner-supplied content. The owner is responsible for having the right to use it.",
        state=SourceState.ENABLED,
        schedule_interval_seconds=None,
        is_system=True,
    )
    db.add(src)
    db.flush()
    return src


def get_source(db: Session, source_id: int) -> Source:
    src = db.get(Source, source_id)
    if src is None:
        raise NotFound("Source not found.")
    return src


def update_source(db: Session, src: Source, changes: dict[str, Any]) -> Source:
    if src.is_system:
        raise ValidationFailed("System sources cannot be edited.")
    info = get_connector_class(src.connector_type).info
    if "config" in changes and changes["config"] is not None:
        src.config = validate_config(info, changes["config"])
    if "schedule_interval_seconds" in changes:
        v = changes["schedule_interval_seconds"]
        if v is not None and v < MIN_INTERVAL_SECONDS:
            raise ValidationFailed(f"Schedule interval must be at least {MIN_INTERVAL_SECONDS} seconds.")
        src.schedule_interval_seconds = v
    for f in ("name", "rate_limit_per_minute", "max_concurrency", "policy_notes"):
        if f in changes and changes[f] is not None:
            setattr(src, f, changes[f])
    audit(db, "source.updated", target_type="source", target_id=src.id, details={"fields": sorted(changes)})
    return src


def review_policy(
    db: Session,
    src: Source,
    *,
    decision: PolicyStatus,
    robots_summary: str | None = None,
    terms_notes: str | None = None,
    allowed_paths: list[str] | None = None,
    reviewer_note: str | None = None,
) -> SourcePolicyReview:
    if decision == PolicyStatus.UNREVIEWED:
        raise ValidationFailed("A review must decide APPROVED, RESTRICTED or DENIED.")
    review = SourcePolicyReview(
        source_id=src.id,
        decision=decision,
        robots_summary=robots_summary,
        terms_notes=terms_notes,
        allowed_paths=allowed_paths or [],
        reviewer_note=reviewer_note,
    )
    db.add(review)
    src.policy_status = decision
    if decision not in ENABLEABLE_POLICIES and src.state != SourceState.DISABLED:
        src.state = SourceState.DISABLED
        src.next_run_at = None
    audit(db, "source.policy_reviewed", target_type="source", target_id=src.id, details={"decision": decision.value})
    db.flush()
    return review


def change_state(db: Session, src: Source, target: SourceState) -> Source:
    if src.is_system:
        raise ValidationFailed("System sources cannot be paused or disabled.")
    SOURCE_STATE.check(src.state, target)
    if target == SourceState.ENABLED:
        if src.policy_status not in ENABLEABLE_POLICIES:
            raise ValidationFailed(
                "Review this source's terms and robots policy before enabling it.", code="policy_review_required"
            )
        if src.domain and is_excluded(db, src.domain):
            raise ValidationFailed("This source's domain is on the exclusion list.", code="excluded")
        src.next_run_at = utcnow() if src.schedule_interval_seconds else None
    else:
        src.next_run_at = None
    src.state = target
    audit(db, f"source.{target.value.lower()}", target_type="source", target_id=src.id)
    db.flush()
    return src


def add_exclusion(db: Session, pattern: str, reason: str) -> SourceExclusion:
    pattern = pattern.strip().lower()
    if not pattern or (("://" not in pattern) and not host_of(f"https://{pattern}/")):
        raise ValidationFailed("Enter a domain (example.com) or a URL prefix (https://example.com/path).")
    if db.execute(select(SourceExclusion).where(SourceExclusion.pattern == pattern)).scalar_one_or_none():
        raise Conflict("That pattern is already excluded.")
    ex = SourceExclusion(pattern=pattern, reason=reason)
    db.add(ex)
    db.flush()
    # Disable any source whose domain is now excluded.
    for src in db.execute(select(Source).where(Source.is_system.is_(False), Source.domain.is_not(None))).scalars():
        if src.domain and matches_exclusion(f"https://{src.domain}/", pattern) and src.state != SourceState.DISABLED:
            src.state = SourceState.DISABLED
            src.next_run_at = None
    audit(db, "source.exclusion_added", details={"pattern": pattern})
    return ex


def can_collect(db: Session, src: Source) -> tuple[bool, str | None]:
    if src.state != SourceState.ENABLED:
        return False, f"Source is {src.state.value.lower()}."
    if src.policy_status not in ENABLEABLE_POLICIES:
        return False, "Source policy is not approved."
    if src.domain and is_excluded(db, src.domain):
        return False, "Source domain is excluded."
    return True, None
