"""AI Studio API: providers (encrypted keys, masked), model pricing, task routing, budget, usage."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from unjobless.ai.gateway import spent_today, test_provider
from unjobless.ai.providers import DEFAULT_ANTHROPIC_MODEL, KNOWN_PRICES
from unjobless.ai.tasks import TASKS
from unjobless.api.deps import DB
from unjobless.core.audit import audit
from unjobless.core.crypto import encrypt_secret, fingerprint, mask_hint
from unjobless.core.errors import Conflict, NotFound, ValidationFailed
from unjobless.core.time import utcnow
from unjobless.db.models import AIModelConfig, AIProviderConfig, AITaskRun, AIUsageEvent, AppSettings

router = APIRouter(prefix="/ai", tags=["ai"])


class ProviderIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["anthropic", "openai_compatible"]
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, min_length=8, max_length=500)
    default_model: str | None = Field(default=None, max_length=120)
    is_default: bool = False
    allow_as_fallback: bool = False


class ProviderPatch(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = Field(default=None, min_length=8, max_length=500)
    default_model: str | None = None
    is_default: bool | None = None
    enabled: bool | None = None
    allow_as_fallback: bool | None = None


class ModelPriceIn(BaseModel):
    model: str = Field(min_length=1, max_length=120)
    input_price_per_mtok: float | None = Field(default=None, ge=0)
    output_price_per_mtok: float | None = Field(default=None, ge=0)


class RoutesIn(BaseModel):
    routes: dict[str, dict[str, Any]]


class BudgetIn(BaseModel):
    daily_budget_usd: float | None = Field(default=None, ge=0)


def provider_out(p: AIProviderConfig) -> dict[str, Any]:
    """Never includes the key. Only a masked hint and a fingerprint prefix."""
    return {
        "id": p.id,
        "name": p.name,
        "kind": p.kind,
        "base_url": p.base_url,
        "has_key": p.encrypted_api_key is not None,
        "key_hint": p.key_hint,
        "key_fingerprint": (p.key_fingerprint or "")[:12] or None,
        "default_model": p.default_model or (DEFAULT_ANTHROPIC_MODEL if p.kind == "anthropic" else None),
        "is_default": p.is_default,
        "enabled": p.enabled,
        "allow_as_fallback": p.allow_as_fallback,
        "cooldown_until": p.cooldown_until.isoformat() if p.cooldown_until else None,
        "last_error": p.last_error,
        "last_tested_at": p.last_tested_at.isoformat() if p.last_tested_at else None,
    }


def _get(db: DB, pid: int) -> AIProviderConfig:
    p = db.get(AIProviderConfig, pid)
    if p is None:
        raise NotFound("Provider not found.")
    return p


def _set_key(p: AIProviderConfig, key: str) -> None:
    key = key.strip()
    p.encrypted_api_key = encrypt_secret(key)
    p.key_fingerprint = fingerprint(key)
    p.key_hint = mask_hint(key)


def _make_default(db: DB, p: AIProviderConfig) -> None:
    db.execute(update(AIProviderConfig).where(AIProviderConfig.id != p.id).values(is_default=False))
    db.flush()
    p.is_default = True


@router.get("/providers")
def providers(db: DB) -> list[dict[str, Any]]:
    return [
        provider_out(p)
        for p in db.execute(select(AIProviderConfig).order_by(AIProviderConfig.name)).scalars()
    ]


@router.post("/providers", status_code=201)
def create_provider(body: ProviderIn, db: DB) -> dict[str, Any]:
    if body.kind == "openai_compatible" and not body.base_url:
        raise ValidationFailed("A base URL is required for OpenAI-compatible providers.")
    if body.base_url and not body.base_url.startswith("https://"):
        raise ValidationFailed("Provider base URL must use https.")
    if db.execute(select(AIProviderConfig).where(AIProviderConfig.name == body.name)).scalar_one_or_none():
        raise Conflict("A provider with that name exists.")
    p = AIProviderConfig(
        name=body.name,
        kind=body.kind,
        base_url=body.base_url,
        default_model=body.default_model,
        allow_as_fallback=body.allow_as_fallback,
    )
    if body.api_key:
        _set_key(p, body.api_key)
    db.add(p)
    db.flush()
    is_first = db.execute(select(func.count()).select_from(AIProviderConfig)).scalar_one() == 1
    if body.is_default or is_first:
        _make_default(db, p)
    audit(
        db,
        "ai.provider_created",
        target_type="ai_provider",
        target_id=p.id,
        details={"kind": body.kind, "key_set": bool(body.api_key)},
    )
    return provider_out(p)


@router.patch("/providers/{pid}")
def patch_provider(pid: int, body: ProviderPatch, db: DB) -> dict[str, Any]:
    p = _get(db, pid)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("api_key"):
        _set_key(p, changes.pop("api_key"))
        p.cooldown_until = None
        audit(db, "ai.key_rotated", target_type="ai_provider", target_id=p.id)
    changes.pop("api_key", None)
    if changes.get("base_url") and not str(changes["base_url"]).startswith("https://"):
        raise ValidationFailed("Provider base URL must use https.")
    if changes.pop("is_default", None):
        _make_default(db, p)
    for k, v in changes.items():
        setattr(p, k, v)
    audit(
        db,
        "ai.provider_updated",
        target_type="ai_provider",
        target_id=p.id,
        details={"fields": sorted(changes)},
    )
    return provider_out(p)


@router.delete("/providers/{pid}/key")
def delete_key(pid: int, db: DB) -> dict[str, Any]:
    p = _get(db, pid)
    p.encrypted_api_key = p.key_fingerprint = p.key_hint = None
    audit(db, "ai.key_deleted", target_type="ai_provider", target_id=p.id)
    return provider_out(p)


@router.delete("/providers/{pid}")
def delete_provider(pid: int, db: DB) -> dict[str, str]:
    p = _get(db, pid)
    db.delete(p)
    audit(db, "ai.provider_deleted", target_type="ai_provider", target_id=pid)
    return {"status": "deleted"}


@router.post("/providers/{pid}/test")
def test(pid: int, db: DB) -> dict[str, Any]:
    return test_provider(db, _get(db, pid))


@router.get("/providers/{pid}/models")
def models(pid: int, db: DB) -> list[dict[str, Any]]:
    p = _get(db, pid)
    rows = db.execute(select(AIModelConfig).where(AIModelConfig.provider_id == p.id)).scalars()
    out = [
        {
            "model": m.model,
            "input_price_per_mtok": m.input_price_per_mtok,
            "output_price_per_mtok": m.output_price_per_mtok,
            "source": "configured",
        }
        for m in rows
    ]
    if p.kind == "anthropic":
        have = {m["model"] for m in out}
        out += [
            {"model": k, "input_price_per_mtok": v[0], "output_price_per_mtok": v[1], "source": "list_price"}
            for k, v in KNOWN_PRICES.items()
            if k not in have
        ]
    return out


@router.put("/providers/{pid}/models")
def set_model_price(pid: int, body: ModelPriceIn, db: DB) -> dict[str, Any]:
    p = _get(db, pid)
    m = db.execute(
        select(AIModelConfig).where(AIModelConfig.provider_id == p.id, AIModelConfig.model == body.model)
    ).scalar_one_or_none()
    if m is None:
        m = AIModelConfig(provider_id=p.id, model=body.model)
        db.add(m)
    m.input_price_per_mtok, m.output_price_per_mtok = body.input_price_per_mtok, body.output_price_per_mtok
    return body.model_dump()


@router.get("/tasks")
def tasks(db: DB) -> dict[str, Any]:
    routes = (db.get(AppSettings, "ai_task_routes") or AppSettings(key="", value={})).value
    return {
        "tasks": [
            {
                "name": t.name,
                "version": t.version,
                "schema_version": t.schema_version,
                "effort": t.effort,
                "max_tokens": t.max_tokens,
                "route": routes.get(t.name),
            }
            for t in TASKS.values()
        ]
    }


@router.put("/tasks/routes")
def set_routes(body: RoutesIn, db: DB) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for task, r in body.routes.items():
        if task not in TASKS:
            raise ValidationFailed(f"Unknown task {task!r}.")
        pid = r.get("provider_id")
        if pid is not None and db.get(AIProviderConfig, int(pid)) is None:
            raise ValidationFailed(f"Unknown provider for {task}.")
        clean[task] = {"provider_id": int(pid) if pid else None, "model": (r.get("model") or None)}
    row = db.get(AppSettings, "ai_task_routes")
    if row is None:
        db.add(AppSettings(key="ai_task_routes", value=clean))
    else:
        row.value = clean
    return {"routes": clean}


@router.get("/budget")
def budget(db: DB) -> dict[str, Any]:
    row = db.get(AppSettings, "ai_daily_budget_usd")
    return {"daily_budget_usd": row.value if row else None, "spent_last_24h_usd": round(spent_today(db), 4)}


@router.put("/budget")
def set_budget(body: BudgetIn, db: DB) -> dict[str, Any]:
    row = db.get(AppSettings, "ai_daily_budget_usd")
    if row is None:
        db.add(AppSettings(key="ai_daily_budget_usd", value=body.daily_budget_usd))
    else:
        row.value = body.daily_budget_usd
    return {"daily_budget_usd": body.daily_budget_usd}


@router.get("/usage")
def usage(db: DB, days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
    since = utcnow() - timedelta(days=days)
    by_task = db.execute(
        select(
            AIUsageEvent.task,
            func.count(),
            func.coalesce(func.sum(AIUsageEvent.input_tokens), 0),
            func.coalesce(func.sum(AIUsageEvent.output_tokens), 0),
            func.sum(AIUsageEvent.cost_estimate),
        )
        .where(AIUsageEvent.at > since)
        .group_by(AIUsageEvent.task)
    ).all()
    runs = db.execute(select(AITaskRun).order_by(AITaskRun.created_at.desc()).limit(50)).scalars()
    return {
        "days": days,
        "by_task": [
            {
                "task": t,
                "calls": c,
                "input_tokens": int(i or 0),
                "output_tokens": int(o or 0),
                "cost_estimate_usd": float(cost) if cost is not None else None,
            }
            for t, c, i, o, cost in by_task
        ],
        "recent_runs": [
            {
                "id": r.id,
                "task": r.task,
                "status": r.status.value,
                "model": r.model,
                "provider_kind": r.provider_kind,
                "prompt_version": r.prompt_version,
                "attempts": r.attempts,
                "error": r.error,
                "created_at": r.created_at.isoformat(),
            }
            for r in runs
        ],
    }
