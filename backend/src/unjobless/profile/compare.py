"""Two-vacancy comparison with a hard maximum of two (service + DB constraints + API validation).

Each criterion yields A, B, Tie or Unknown with evidence for each side. Missing data is never a
win or a zero: a criterion is `Unknown` unless both sides have comparable information. Scores are
reproducible from stored inputs; weights are editable; trade-offs are explained.
"""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from unjobless.core.errors import NotFound, ValidationFailed
from unjobless.db.models import JobBenefit, JobComparison, JobComparisonItem, JobVacancy, MatchAnalysis
from unjobless.intelligence import lifecycle
from unjobless.profile.cv import active_version
from unjobless.profile.matching import get_preferences, upsert_match
from unjobless.profile.schemas import ProfileData

ALGORITHM_VERSION = "1.0"
Winner = Literal["A", "B", "Tie", "Unknown"]
DEFAULT_WEIGHTS: dict[str, float] = {
    "candidate_fit": 3, "location": 2, "work_arrangement": 2, "compensation": 2, "benefits": 1,
    "growth_learning": 1, "eligibility": 2, "application_practicality": 1, "data_confidence": 1,
}
FRESHNESS_RANK = {"NEW": 3, "ACTIVE": 3, "CLOSING_SOON": 2, "STALE": 1, "UNKNOWN": 1, "EXPIRED": 0}
LEARNING_WORDS = ("mentor", "training", "pelatihan", "learning", "belajar", "sertifikat", "certificate", "coaching", "workshop")


def validate_ids(ids: list[int]) -> tuple[int, int]:
    if len(ids) != 2:
        raise ValidationFailed("Select exactly two vacancies to compare.", code="compare_requires_two")
    if ids[0] == ids[1]:
        raise ValidationFailed("Select two different vacancies.", code="compare_duplicate")
    return ids[0], ids[1]


def _cmp_num(a: float | None, b: float | None, *, higher_better: bool = True, tie_margin: float = 0.05) -> Winner:
    if a is None or b is None:
        return "Unknown"
    if abs(a - b) <= tie_margin * max(abs(a), abs(b), 1e-9):
        return "Tie"
    return ("A" if a > b else "B") if higher_better else ("A" if a < b else "B")


def _criterion(name: str, winner: Winner, a: Any, b: Any, note: str, weight: float) -> dict[str, Any]:
    return {"criterion": name, "winner": winner, "a": a, "b": b, "note": note, "weight": weight}


def _match(db: Session, v: JobVacancy) -> MatchAnalysis:
    m = db.execute(select(MatchAnalysis).where(MatchAnalysis.vacancy_id == v.id, MatchAnalysis.is_current.is_(True))).scalar_one_or_none()
    if m is None:
        pv = active_version(db)
        m = upsert_match(db, v, pv.id if pv else None, ProfileData.model_validate(pv.data) if pv else None, get_preferences(db))
    return m


def compare(db: Session, ids: list[int], weights: dict[str, float] | None = None, *, save: bool = True) -> dict[str, Any]:
    a_id, b_id = validate_ids(ids)
    a, b = db.get(JobVacancy, a_id), db.get(JobVacancy, b_id)
    if a is None or b is None:
        raise NotFound("Vacancy not found.")
    w = {**DEFAULT_WEIGHTS, **{k: float(v) for k, v in (weights or {}).items() if k in DEFAULT_WEIGHTS}}
    if any(v < 0 or v > 10 for v in w.values()):
        raise ValidationFailed("Weights must be between 0 and 10.")
    ma, mb = _match(db, a), _match(db, b)
    prefs = get_preferences(db)
    crit: list[dict[str, Any]] = []

    crit.append(_criterion("candidate_fit", _cmp_num(ma.candidate_fit_score, mb.candidate_fit_score), ma.candidate_fit_score, mb.candidate_fit_score,
                           "How well your confirmed profile evidence covers each vacancy's requirements.", w["candidate_fit"]))

    def loc_score(m: MatchAnalysis) -> float | None:
        return next((c["score"] for c in m.breakdown.get("preference_fit", []) if c["name"] == "location"), None)

    crit.append(_criterion("location", _cmp_num(loc_score(ma), loc_score(mb)), a.location_text or ("Remote" if a.work_arrangement.value == "REMOTE" else None),
                           b.location_text or ("Remote" if b.work_arrangement.value == "REMOTE" else None), "Against your preferred cities and remote preference.", w["location"]))

    def wa_score(v: JobVacancy) -> float | None:
        if v.work_arrangement.value == "UNKNOWN" or not prefs.work_arrangements:
            return None
        return 1.0 if v.work_arrangement.value in prefs.work_arrangements or v.work_arrangement.value == "FLEXIBLE" else 0.0

    crit.append(_criterion("work_arrangement", _cmp_num(wa_score(a), wa_score(b)), a.work_arrangement.value, b.work_arrangement.value, "Against your preferred arrangements.", w["work_arrangement"]))

    def pay(v: JobVacancy) -> tuple[float | None, str]:
        if v.salary_max is None and v.salary_min is None:
            return None, "Not stated"
        top = float(v.salary_max or v.salary_min)  # type: ignore[arg-type]
        return top, f"{v.salary_currency or ''} {float(v.salary_min or top):,.0f}–{top:,.0f} / {(v.pay_period.value if v.pay_period else 'period?').lower()}"

    pa, pb = pay(a), pay(b)
    same_basis = (a.salary_currency == b.salary_currency) and ((a.pay_period and a.pay_period.value) == (b.pay_period and b.pay_period.value))
    comp_w: Winner = _cmp_num(pa[0], pb[0]) if same_basis else "Unknown"
    crit.append(_criterion("compensation", comp_w, pa[1], pb[1], "Unknown when either side does not state pay or they use different currencies/periods." if comp_w == "Unknown" else "Higher stated maximum.", w["compensation"]))

    def benefits(v: JobVacancy) -> list[str]:
        return [x.value for x in db.execute(select(JobBenefit).where(JobBenefit.vacancy_id == v.id)).scalars()]

    ba, bb = benefits(a), benefits(b)
    crit.append(_criterion("benefits", "Unknown" if not ba and not bb else _cmp_num(float(len(ba)), float(len(bb)), tie_margin=0.2) if ba and bb else "Unknown", ba, bb,
                           "Counts listed benefits only when both list them; an unlisted benefit is unknown, not absent.", w["benefits"]))

    def learning(v: JobVacancy) -> list[str]:
        text = " ".join(benefits(v) + [v.description or ""]).lower()
        return [kw for kw in LEARNING_WORDS if kw in text]

    la, lb = learning(a), learning(b)
    crit.append(_criterion("growth_learning", "Unknown" if not la and not lb else _cmp_num(float(len(la)), float(len(lb)), tie_margin=0.3), la or None, lb or None,
                           "Explicit mentorship/training/learning mentions in the posting.", w["growth_learning"]))
    ea, eb = ma.eligible, mb.eligible
    elig: Winner = "Unknown" if ea is None or eb is None else "Tie" if ea == eb else ("A" if ea else "B")
    crit.append(_criterion("eligibility", elig, ea, eb, "Hard requirements you may not meet (GPA, semester, exclusions).", w["eligibility"]))

    def practicality(v: JobVacancy) -> float | None:
        if v.application_url is None and not (v.details or {}).get("application_email"):
            return None
        return float(FRESHNESS_RANK.get(v.freshness.value, 1)) + (0.5 if v.application_url else 0)

    crit.append(_criterion("application_practicality", _cmp_num(practicality(a), practicality(b), tie_margin=0.1),
                           {"deadline": a.application_deadline.isoformat() if a.application_deadline else None, "freshness": a.freshness.value, "apply_link": bool(a.application_url)},
                           {"deadline": b.application_deadline.isoformat() if b.application_deadline else None, "freshness": b.freshness.value, "apply_link": bool(b.application_url)},
                           "Known application path and freshness.", w["application_practicality"]))
    crit.append(_criterion("data_confidence", _cmp_num(a.data_confidence, b.data_confidence, tie_margin=0.1), a.data_confidence, b.data_confidence,
                           "How complete and reliable each record is — not a quality judgement of the job.", w["data_confidence"]))

    # Weighted tally: only decided criteria count; unknown ones reduce confidence instead.
    tot_a = sum(c["weight"] for c in crit if c["winner"] == "A")
    tot_b = sum(c["weight"] for c in crit if c["winner"] == "B")
    decided = sum(c["weight"] for c in crit if c["winner"] in ("A", "B", "Tie"))
    total_w = sum(c["weight"] for c in crit) or 1.0
    coverage = round(decided / total_w, 3)
    unknown = [c["criterion"] for c in crit if c["winner"] == "Unknown"]
    tradeoffs = []
    for c in crit:
        if c["winner"] == "A":
            tradeoffs.append(f"A is better on {c['criterion'].replace('_', ' ')}.")
        elif c["winner"] == "B":
            tradeoffs.append(f"B is better on {c['criterion'].replace('_', ' ')}.")
    if tot_a == tot_b or coverage < 0.5:
        lean, rec = "none", "No clear winner on the information available; use the trade-offs and fill in the unknowns."
    else:
        lean = "A" if tot_a > tot_b else "B"
        rec = f"On your weights, {lean} leads ({max(tot_a, tot_b):.0f} vs {min(tot_a, tot_b):.0f} weighted points), but this is a decision aid, not an answer."
    result = {
        "a": _summary(a, ma), "b": _summary(b, mb), "criteria": crit, "weights": w,
        "totals": {"A": tot_a, "B": tot_b, "decided_weight": decided, "total_weight": total_w},
        "coverage": coverage, "unknown_criteria": unknown, "tradeoffs": tradeoffs,
        "recommendation": {"lean": lean, "text": rec, "uncertainty": "high" if coverage < 0.5 else "medium" if unknown else "low"},
        "algorithm_version": ALGORITHM_VERSION,
    }
    if save:
        pv = active_version(db)
        cmp_row = JobComparison(weights=w, result=result, profile_version_id=pv.id if pv else None, algorithm_version=ALGORITHM_VERSION)
        db.add(cmp_row)
        db.flush()
        db.add_all([JobComparisonItem(comparison_id=cmp_row.id, vacancy_id=a.id, position=1), JobComparisonItem(comparison_id=cmp_row.id, vacancy_id=b.id, position=2)])
        db.flush()
        result["id"] = cmp_row.id
    return result


def _summary(v: JobVacancy, m: MatchAnalysis) -> dict[str, Any]:
    return {
        "id": v.id, "title": v.title, "company": v.company_name, "status": v.verification_status.value,
        "freshness": lifecycle.compute_freshness(v).value, "candidate_fit_score": m.candidate_fit_score,
        "preference_fit_score": m.preference_fit_score, "overall_score": m.overall_score, "application_url": v.application_url,
    }
