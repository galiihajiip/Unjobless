from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from unjobless.api.deps import DB
from unjobless.core.errors import NotFound
from unjobless.db.models import (
    FetchLog,
    Source,
    SourceExclusion,
    SourceHealthEvent,
    SourcePolicyReview,
    SourceRun,
    SourceRunItem,
)
from unjobless.domain.enums import PolicyStatus, RunItemOutcome, RunTrigger, SourceState
from unjobless.jobs.queue import defer
from unjobless.jobs.runner import (
    active_run,
    cancel_run,
    enqueue_source_run,
    reset_source_runs_for_disable,
    run_summary,
)
from unjobless.sources import service
from unjobless.sources.registry import all_connectors

router = APIRouter(prefix="/sources", tags=["sources"])


class SourceOut(BaseModel):
    id: int
    key: str
    name: str
    domain: str | None
    category: str
    connector_type: str
    collection_method: str
    documentation_url: str | None
    terms_url: str | None
    policy_status: str
    policy_notes: str | None
    state: str
    health: str
    health_reason: str | None
    config: dict[str, Any]
    schedule_interval_seconds: int | None
    next_run_at: datetime | None
    rate_limit_per_minute: int
    max_concurrency: int
    last_success_at: datetime | None
    last_attempt_at: datetime | None
    consecutive_failures: int
    is_system: bool
    has_secret: bool
    active_run: dict[str, Any] | None = None
    last_run: dict[str, Any] | None = None
    stats: dict[str, Any] | None = None


def to_out(db: DB, s: Source, with_runs: bool = True) -> SourceOut:
    data = {c: getattr(s, c) for c in SourceOut.model_fields if hasattr(s, c) and c not in ("has_secret",)}
    out = SourceOut(**data, has_secret=s.secret_id is not None)
    if with_runs:
        act = active_run(db, s.id)
        out.active_run = run_summary(act) if act else None
        last = db.execute(
            select(SourceRun)
            .where(SourceRun.source_id == s.id, SourceRun.finished_at.is_not(None))
            .order_by(SourceRun.finished_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        out.last_run = run_summary(last) if last else None
        agg = db.execute(
            select(
                func.count(SourceRun.id),
                func.coalesce(func.sum(SourceRun.discovered), 0),
                func.coalesce(func.sum(SourceRun.new), 0),
                func.coalesce(func.sum(SourceRun.changed), 0),
                func.coalesce(func.sum(SourceRun.errors), 0),
                func.avg(func.extract("epoch", SourceRun.finished_at - SourceRun.started_at)),
            ).where(SourceRun.source_id == s.id, SourceRun.finished_at.is_not(None))
        ).one()
        out.stats = {
            "runs": agg[0],
            "discovered": int(agg[1]),
            "new": int(agg[2]),
            "changed": int(agg[3]),
            "errors": int(agg[4]),
            "avg_duration_seconds": float(agg[5]) if agg[5] is not None else None,
        }
    return out


class SourceCreate(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9\-]{1,78}$")
    name: str = Field(min_length=1, max_length=200)
    connector_type: str
    domain: str | None = Field(default=None, max_length=253)
    config: dict[str, Any] = Field(default_factory=dict)
    schedule_interval_seconds: int | None = Field(default=None, ge=300, le=7 * 86400)
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=600)
    policy_notes: str | None = None


class SourcePatch(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    schedule_interval_seconds: int | None = Field(default=None, ge=300, le=7 * 86400)
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=600)
    max_concurrency: int | None = Field(default=None, ge=1, le=8)
    policy_notes: str | None = None


class PolicyReviewIn(BaseModel):
    decision: PolicyStatus
    robots_summary: str | None = None
    terms_notes: str | None = None
    allowed_paths: list[str] = Field(default_factory=list)
    reviewer_note: str | None = None


class ExclusionIn(BaseModel):
    pattern: str = Field(min_length=3, max_length=500)
    reason: str = Field(min_length=1, max_length=1000)


@router.get("/connectors")
def connectors() -> list[dict[str, Any]]:
    out = []
    for info in all_connectors():
        if not info.user_visible:
            continue
        out.append(
            {
                "type": info.type,
                "name": info.name,
                "description": info.description,
                "category": info.category.value,
                "collection_method": info.collection_method.value,
                "documentation_url": info.documentation_url,
                "terms_url": info.terms_url,
                "auth_required": info.auth_required,
                "default_schedule_seconds": info.default_schedule_seconds,
                "default_rate_limit_per_minute": info.default_rate_limit_per_minute,
                "capabilities": {
                    "discovery": info.supports_discovery,
                    "pagination": info.supports_pagination,
                    "incremental": info.supports_incremental,
                    "health_check": info.supports_health_check,
                },
                "content_types": list(info.content_types),
                "retry": {
                    "max_attempts": info.retry.max_attempts,
                    "base_delay_seconds": info.retry.base_delay_seconds,
                },
                "attribution": info.attribution,
                "freshness_strategy": info.freshness_strategy,
                "terms_review": info.terms_review,
                "config_schema": info.config_model.model_json_schema(),
            }
        )
    return out


@router.get("/starter-pack")
def starter_pack() -> list[dict[str, Any]]:
    from unjobless.sources.starter_pack import describe

    return describe()


class PackIn(BaseModel):
    keys: list[str] = Field(min_length=1, max_length=50)


@router.post("/starter-pack", status_code=201)
def install_pack(body: PackIn, db: DB) -> list[SourceOut]:
    from unjobless.sources.starter_pack import install

    created = install(db, body.keys)
    db.commit()
    for s in created:
        run = enqueue_source_run(db, s, RunTrigger.MANUAL)
        db.commit()
        defer("run_source", queueing_lock=f"run-{run.id}", run_id=run.id)
    return [to_out(db, s) for s in created]


@router.get("")
def list_sources(db: DB, include_system: bool = False) -> list[SourceOut]:
    q = select(Source).order_by(Source.name)
    if not include_system:
        q = q.where(Source.is_system.is_(False))
    return [to_out(db, s) for s in db.execute(q).scalars()]


@router.post("", status_code=201)
def create(body: SourceCreate, db: DB) -> SourceOut:
    s = service.create_source(db, **body.model_dump())
    return to_out(db, s)


@router.get("/exclusions")
def exclusions(db: DB) -> list[dict[str, Any]]:
    return [
        {"id": e.id, "pattern": e.pattern, "reason": e.reason, "created_at": e.created_at.isoformat()}
        for e in db.execute(select(SourceExclusion).order_by(SourceExclusion.pattern)).scalars()
    ]


@router.post("/exclusions", status_code=201)
def add_exclusion(body: ExclusionIn, db: DB) -> dict[str, Any]:
    e = service.add_exclusion(db, body.pattern, body.reason)
    return {"id": e.id, "pattern": e.pattern, "reason": e.reason}


@router.delete("/exclusions/{exclusion_id}")
def remove_exclusion(exclusion_id: int, db: DB) -> dict[str, str]:
    e = db.get(SourceExclusion, exclusion_id)
    if e is None:
        raise NotFound("Exclusion not found.")
    db.delete(e)
    return {"status": "deleted"}


@router.get("/fetch-log")
def fetch_log(db: DB, limit: int = Query(50, le=200)) -> list[dict[str, Any]]:
    rows = db.execute(select(FetchLog).order_by(FetchLog.at.desc()).limit(limit)).scalars()
    return [
        {
            "host": r.host,
            "outcome": r.outcome,
            "reason": r.reason,
            "status_code": r.status_code,
            "at": r.at.isoformat(),
        }
        for r in rows
    ]


@router.get("/{source_id}")
def get(source_id: int, db: DB) -> SourceOut:
    return to_out(db, service.get_source(db, source_id))


@router.patch("/{source_id}")
def patch(source_id: int, body: SourcePatch, db: DB) -> SourceOut:
    s = service.get_source(db, source_id)
    service.update_source(db, s, body.model_dump(exclude_unset=True))
    return to_out(db, s)


@router.post("/{source_id}/policy-review")
def policy_review(source_id: int, body: PolicyReviewIn, db: DB) -> SourceOut:
    s = service.get_source(db, source_id)
    service.review_policy(db, s, **body.model_dump())
    if s.state == SourceState.DISABLED:
        reset_source_runs_for_disable(db, s.id)
    return to_out(db, s)


@router.get("/{source_id}/policy-reviews")
def policy_reviews(source_id: int, db: DB) -> list[dict[str, Any]]:
    rows = db.execute(
        select(SourcePolicyReview)
        .where(SourcePolicyReview.source_id == source_id)
        .order_by(SourcePolicyReview.reviewed_at.desc())
    ).scalars()
    return [
        {
            "decision": r.decision.value,
            "robots_summary": r.robots_summary,
            "terms_notes": r.terms_notes,
            "allowed_paths": r.allowed_paths,
            "reviewer_note": r.reviewer_note,
            "reviewed_at": r.reviewed_at.isoformat(),
        }
        for r in rows
    ]


def _state(source_id: int, target: SourceState, db: DB) -> SourceOut:
    s = service.get_source(db, source_id)
    service.change_state(db, s, target)
    if target != SourceState.ENABLED:
        reset_source_runs_for_disable(db, s.id)
    return to_out(db, s)


@router.post("/{source_id}/enable")
def enable(source_id: int, db: DB) -> SourceOut:
    return _state(source_id, SourceState.ENABLED, db)


@router.post("/{source_id}/resume")
def resume(source_id: int, db: DB) -> SourceOut:
    return _state(source_id, SourceState.ENABLED, db)


@router.post("/{source_id}/pause")
def pause(source_id: int, db: DB) -> SourceOut:
    return _state(source_id, SourceState.PAUSED, db)


@router.post("/{source_id}/disable")
def disable(source_id: int, db: DB) -> SourceOut:
    return _state(source_id, SourceState.DISABLED, db)


@router.post("/{source_id}/run", status_code=202)
def run_now(source_id: int, db: DB) -> dict[str, Any]:
    s = service.get_source(db, source_id)
    run = enqueue_source_run(db, s, RunTrigger.MANUAL)
    db.commit()
    defer("run_source", queueing_lock=f"run-{run.id}", run_id=run.id)
    return run_summary(run)


class SecretIn(BaseModel):
    value: str = Field(min_length=4, max_length=500)


@router.put("/{source_id}/secret")
def set_secret(source_id: int, body: SecretIn, db: DB) -> dict[str, Any]:
    """Store a connector credential (e.g. a mailbox app password) encrypted. Never returned."""
    from unjobless.core.audit import audit
    from unjobless.core.crypto import encrypt_secret, fingerprint, mask_hint
    from unjobless.db.models import EncryptedSecret

    s = service.get_source(db, source_id)
    purpose = "source-secret"
    if s.secret_id:
        sec = db.get(EncryptedSecret, s.secret_id)
    else:
        sec = None
    if sec is None:
        sec = EncryptedSecret(purpose=purpose, ciphertext=b"", fingerprint="", hint="")
        db.add(sec)
    sec.purpose, sec.ciphertext = purpose, encrypt_secret(body.value, purpose=purpose)
    sec.fingerprint, sec.hint = fingerprint(body.value), mask_hint(body.value)
    db.flush()
    s.secret_id = sec.id
    audit(db, "source.secret_set", target_type="source", target_id=s.id)
    return {"has_secret": True, "hint": sec.hint}


@router.delete("/{source_id}/secret")
def delete_secret(source_id: int, db: DB) -> dict[str, Any]:
    s = service.get_source(db, source_id)
    s.secret_id = None
    return {"has_secret": False}


@router.get("/{source_id}/runs")
def runs(source_id: int, db: DB, limit: int = Query(20, le=100), offset: int = 0) -> dict[str, Any]:
    q = select(SourceRun).where(SourceRun.source_id == source_id)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(q.order_by(SourceRun.created_at.desc()).limit(limit).offset(offset)).scalars()
    return {"items": [run_summary(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.post("/{source_id}/runs/{run_id}/cancel")
def cancel(source_id: int, run_id: int, db: DB) -> dict[str, Any]:
    run = db.get(SourceRun, run_id)
    if run is None or run.source_id != source_id:
        raise NotFound("Run not found.")
    return run_summary(cancel_run(db, run))


@router.get("/{source_id}/runs/{run_id}/items")
def run_items(source_id: int, run_id: int, db: DB, failed_only: bool = False) -> list[dict[str, Any]]:
    q = select(SourceRunItem).join(SourceRun).where(SourceRun.id == run_id, SourceRun.source_id == source_id)
    if failed_only:
        q = q.where(SourceRunItem.outcome == RunItemOutcome.ERROR)
    rows = db.execute(q.order_by(SourceRunItem.id).limit(500)).scalars()
    return [
        {
            "id": r.id,
            "external_id": r.external_id,
            "url": r.url,
            "outcome": r.outcome.value,
            "error": r.error,
            "raw_version_id": r.raw_version_id,
        }
        for r in rows
    ]


@router.get("/{source_id}/health-events")
def health_events(source_id: int, db: DB) -> list[dict[str, Any]]:
    rows = db.execute(
        select(SourceHealthEvent)
        .where(SourceHealthEvent.source_id == source_id)
        .order_by(SourceHealthEvent.at.desc())
        .limit(50)
    ).scalars()
    return [{"health": r.health.value, "reason": r.reason, "at": r.at.isoformat()} for r in rows]
