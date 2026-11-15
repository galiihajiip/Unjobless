from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from unjobless.api.deps import DB
from unjobless.core.errors import NotFound
from unjobless.db.models import ComparisonWeights, JobComparison, JobComparisonItem, JobVacancy
from unjobless.profile import compare as svc

router = APIRouter(prefix="/compare", tags=["compare"])


class CompareIn(BaseModel):
    # Hard limit at the API boundary too: exactly two IDs (service also checks distinctness).
    vacancy_ids: list[int] = Field(min_length=2, max_length=2)
    weights: dict[str, float] | None = None
    save: bool = True


@router.post("")
def run(body: CompareIn, db: DB) -> dict[str, Any]:
    return svc.compare(db, body.vacancy_ids, body.weights, save=body.save)


@router.post("/explain")
def explain(body: CompareIn, db: DB) -> dict[str, Any]:
    """Optional AI narrative over the deterministic result (never changes scores)."""
    from unjobless.ai.gateway import run_task

    res = svc.compare(db, body.vacancy_ids, body.weights, save=False)
    payload = {"criteria": res["criteria"], "totals": res["totals"], "unknown": res["unknown_criteria"], "a": res["a"], "b": res["b"]}
    out = run_task(db, "comparison_explanation", payload, input_ref=f"compare:{body.vacancy_ids[0]}-{body.vacancy_ids[1]}")
    return out.output.model_dump()


@router.get("/defaults")
def defaults(db: DB) -> dict[str, Any]:
    saved = db.execute(select(ComparisonWeights).where(ComparisonWeights.name == "default")).scalar_one_or_none()
    return {"weights": saved.weights if saved else svc.DEFAULT_WEIGHTS, "builtin": svc.DEFAULT_WEIGHTS}


class WeightsIn(BaseModel):
    weights: dict[str, float]


@router.put("/defaults")
def set_defaults(body: WeightsIn, db: DB) -> dict[str, Any]:
    w = {k: max(0.0, min(10.0, float(v))) for k, v in body.weights.items() if k in svc.DEFAULT_WEIGHTS}
    row = db.execute(select(ComparisonWeights).where(ComparisonWeights.name == "default")).scalar_one_or_none()
    if row is None:
        db.add(ComparisonWeights(name="default", weights=w))
    else:
        row.weights = w
    return {"weights": w}


@router.get("/history")
def history(db: DB) -> list[dict[str, Any]]:
    rows = db.execute(select(JobComparison).order_by(JobComparison.created_at.desc()).limit(50)).scalars().all()
    out = []
    for c in rows:
        items = db.execute(select(JobComparisonItem, JobVacancy).join(JobVacancy, JobVacancy.id == JobComparisonItem.vacancy_id).where(JobComparisonItem.comparison_id == c.id).order_by(JobComparisonItem.position)).all()
        out.append({"id": c.id, "created_at": c.created_at.isoformat(), "lean": c.result.get("recommendation", {}).get("lean"),
                    "vacancies": [{"id": v.id, "title": v.title, "company": v.company_name} for _i, v in items]})
    return out


@router.get("/{comparison_id}")
def get(comparison_id: int, db: DB) -> dict[str, Any]:
    c = db.get(JobComparison, comparison_id)
    if c is None:
        raise NotFound("Comparison not found.")
    return {**c.result, "id": c.id, "created_at": c.created_at.isoformat()}
