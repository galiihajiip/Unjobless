"""AI gateway: the only entry point domain code uses to run AI tasks."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from unjobless.ai.providers import (
    DEFAULT_ANTHROPIC_MODEL,
    KNOWN_PRICES,
    ProviderAdapter,
    ProviderAuthError,
    ProviderBadRequest,
    ProviderError,
    ProviderRateLimited,
    ProviderRefused,
    ProviderUnavailable,
    build_adapter,
)
from unjobless.ai.task_schemas import strict_json_schema
from unjobless.ai.tasks import AITask, get_task, render_user
from unjobless.core.crypto import decrypt_secret
from unjobless.core.errors import AppError
from unjobless.core.logging import get_logger
from unjobless.core.time import utcnow
from unjobless.db.models import AIModelConfig, AIPromptVersion, AIProviderConfig, AITaskRun, AIUsageEvent, AppSettings
from unjobless.domain.enums import AITaskStatus
from unjobless.domain.state_machines import AI_TASK

log = get_logger(__name__)


class AINotConfigured(AppError):
    status_code = 409
    code = "ai_not_configured"


class AIUnavailable(AppError):
    status_code = 503
    code = "ai_unavailable"


class AIBudgetExceeded(AppError):
    status_code = 429
    code = "ai_budget_exceeded"


class AITaskFailed(AppError):
    status_code = 502
    code = "ai_task_failed"


@dataclass
class TaskResult:
    output: BaseModel
    run: AITaskRun


# Test hook: inject an adapter for a provider kind without network.
ADAPTER_OVERRIDE: dict[str, ProviderAdapter] = {}


def _setting(db: Session, key: str, default: Any) -> Any:
    row = db.get(AppSettings, key)
    return row.value if row is not None else default


def _adapter(p: AIProviderConfig) -> ProviderAdapter:
    if p.kind in ADAPTER_OVERRIDE:
        return ADAPTER_OVERRIDE[p.kind]
    key = decrypt_secret(p.encrypted_api_key) if p.encrypted_api_key else None
    return build_adapter(p.kind, key, p.base_url)


def resolve_route(db: Session, task: str, provider_id: int | None = None) -> tuple[AIProviderConfig, str]:
    routes: dict[str, Any] = _setting(db, "ai_task_routes", {})
    route = routes.get(task) or {}
    pid = provider_id or route.get("provider_id")
    if pid:
        p = db.get(AIProviderConfig, pid)
    else:
        p = db.execute(select(AIProviderConfig).where(AIProviderConfig.is_default.is_(True))).scalar_one_or_none()
    if p is None or not p.enabled:
        raise AINotConfigured("No enabled AI provider is configured. Add one in AI Studio.")
    model = route.get("model") or p.default_model or (DEFAULT_ANTHROPIC_MODEL if p.kind == "anthropic" else None)
    if not model:
        raise AINotConfigured(f"Provider {p.name!r} has no model selected.")
    return p, model


def ai_available(db: Session, task: str) -> bool:
    try:
        p, _ = resolve_route(db, task)
    except AINotConfigured:
        return False
    return p.cooldown_until is None or p.cooldown_until <= utcnow()


def _price(db: Session, provider: AIProviderConfig, model: str) -> tuple[float, float] | None:
    cfg = db.execute(
        select(AIModelConfig).where(AIModelConfig.provider_id == provider.id, AIModelConfig.model == model)
    ).scalar_one_or_none()
    if cfg and cfg.input_price_per_mtok is not None and cfg.output_price_per_mtok is not None:
        return cfg.input_price_per_mtok, cfg.output_price_per_mtok
    return KNOWN_PRICES.get(model) if provider.kind == "anthropic" else None


def spent_today(db: Session) -> float:
    since = utcnow() - timedelta(days=1)
    return float(db.execute(select(func.coalesce(func.sum(AIUsageEvent.cost_estimate), 0.0)).where(AIUsageEvent.at > since)).scalar_one())


def _ensure_prompt_version(db: Session, t: AITask) -> None:
    exists = db.execute(
        select(AIPromptVersion.id).where(AIPromptVersion.task == t.name, AIPromptVersion.version == t.version)
    ).first()
    if not exists:
        db.add(AIPromptVersion(task=t.name, version=t.version, template_hash=t.template_hash(), schema_version=t.schema_version))


def run_task(
    db: Session,
    task_name: str,
    payload: dict[str, Any],
    *,
    input_ref: str | None = None,
    provider_id: int | None = None,
) -> TaskResult:
    t = get_task(task_name)
    provider, model = resolve_route(db, task_name, provider_id)
    budget = _setting(db, "ai_daily_budget_usd", None)
    if budget is not None and spent_today(db) >= float(budget):
        raise AIBudgetExceeded("Today's AI budget has been reached. Raise it in AI Studio or wait.")
    _ensure_prompt_version(db, t)
    user = render_user(payload)
    run = AITaskRun(
        task=t.name,
        status=AITaskStatus.PENDING,
        provider_id=provider.id,
        provider_kind=provider.kind,
        model=model,
        prompt_version=t.version,
        schema_version=t.schema_version,
        input_ref=input_ref,
        input_hash=hashlib.sha256(user.encode()).hexdigest(),
    )
    db.add(run)
    db.flush()
    if provider.cooldown_until and provider.cooldown_until > utcnow():
        # Respect the provider's rate limit: wait it out rather than switching providers.
        raise AIUnavailable(f"{provider.name} is cooling down after a rate limit; the task will retry later.")
    candidates = [(provider, model)]
    fallback = _fallback_provider(db, provider)
    if fallback is not None:
        candidates.append(fallback)
    last_error: Exception | None = None
    for prov, mdl in candidates:
        if prov.cooldown_until and prov.cooldown_until > utcnow():
            last_error = ProviderRateLimited(f"{prov.name} is cooling down after a rate limit.")
            continue
        run.provider_id, run.provider_kind, run.model = prov.id, prov.kind, mdl
        try:
            out = _attempt(db, t, prov, mdl, user, run)
            return TaskResult(out, run)
        except ProviderRateLimited as e:
            prov.cooldown_until = utcnow() + timedelta(seconds=max(30.0, e.retry_after or 60.0))
            prov.last_error = e.message
            _finish(run, AITaskStatus.RATE_LIMITED, e.message)
            # A rate limit is respected: no switching providers to evade it.
            raise AIUnavailable("The AI provider is rate limited; the task will retry later.") from e
        except ProviderUnavailable as e:
            prov.last_error = e.message
            last_error = e
            run.status = AITaskStatus.PENDING  # allow another attempt with the fallback provider
            continue
        except (ProviderAuthError, ProviderBadRequest, ProviderRefused) as e:
            prov.last_error = e.message
            _finish(run, AITaskStatus.FAILED_PROVIDER, e.message)
            raise AITaskFailed(e.message) from e
    _finish(run, AITaskStatus.FAILED_PROVIDER, str(last_error) if last_error else "No provider available")
    raise AIUnavailable(str(last_error) if last_error else "No AI provider available.")


def _fallback_provider(db: Session, primary: AIProviderConfig) -> tuple[AIProviderConfig, str] | None:
    fb = db.execute(
        select(AIProviderConfig).where(
            AIProviderConfig.allow_as_fallback.is_(True),
            AIProviderConfig.enabled.is_(True),
            AIProviderConfig.id != primary.id,
        )
    ).scalars().first()
    if fb is None:
        return None
    model = fb.default_model or (DEFAULT_ANTHROPIC_MODEL if fb.kind == "anthropic" else None)
    return (fb, model) if model else None


def _finish(run: AITaskRun, status: AITaskStatus, error: str | None = None) -> None:
    if run.status != status:
        AI_TASK.check(run.status, status)
    run.status = status
    run.error = (error or None) and error[:2000]
    run.finished_at = utcnow()


def _attempt(db: Session, t: AITask, prov: AIProviderConfig, model: str, user: str, run: AITaskRun) -> BaseModel:
    AI_TASK.check(run.status, AITaskStatus.RUNNING)
    run.status = AITaskStatus.RUNNING
    adapter = _adapter(prov)
    schema = strict_json_schema(t.output_model)
    prompt = user
    for attempt in (1, 2):  # one repair retry for format/validation errors only
        run.attempts += 1
        res = adapter.complete_json(
            model=model, system=t.system, user=prompt, schema=schema, max_tokens=t.max_tokens, effort=t.effort, timeout=t.timeout
        )
        price = _price(db, prov, model)
        cost = None
        if price and res.input_tokens is not None and res.output_tokens is not None:
            cost = (res.input_tokens * price[0] + res.output_tokens * price[1]) / 1_000_000
        db.add(
            AIUsageEvent(
                task_run_id=run.id, provider_id=prov.id, model=res.model, task=t.name,
                input_tokens=res.input_tokens, output_tokens=res.output_tokens, cost_estimate=cost, latency_ms=res.latency_ms,
            )
        )
        try:
            out = t.output_model.model_validate(res.data)
        except ValidationError as e:
            errs = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:10])
            if attempt == 1:
                prompt = user + f"\n\nYour previous output failed schema validation ({errs}). Return corrected JSON only."
                continue
            _finish(run, AITaskStatus.FAILED_VALIDATION, errs)
            raise AITaskFailed("The AI output did not match the expected format.") from e
        run.output = out.model_dump(mode="json")
        prov.cooldown_until = None
        _finish(run, AITaskStatus.SUCCEEDED)
        return out
    raise AITaskFailed("unreachable")  # pragma: no cover


def test_provider(db: Session, provider: AIProviderConfig) -> dict[str, Any]:
    """Minimal live call to verify key + model. Records the outcome on the provider."""
    from unjobless.ai.task_schemas import MatchExplanation

    model = provider.default_model or (DEFAULT_ANTHROPIC_MODEL if provider.kind == "anthropic" else None)
    provider.last_tested_at = utcnow()
    if not model:
        return {"ok": False, "message": "Select a model first."}
    try:
        res = _adapter(provider).complete_json(
            model=model,
            system="Connection test. Reply with the requested JSON.",
            user="Return summary='ok' and empty lists.",
            schema=strict_json_schema(MatchExplanation),
            max_tokens=1000,
            effort="low",
            timeout=60,
        )
        provider.last_error = None
        return {"ok": True, "message": f"Connected. Model {res.model} responded in {res.latency_ms} ms."}
    except ProviderError as e:
        provider.last_error = e.message
        return {"ok": False, "message": e.message}
    except AppError as e:
        return {"ok": False, "message": e.message}
