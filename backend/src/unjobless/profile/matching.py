"""Evidence-based matching (deterministic). Documented in docs/product/MATCHING.md.

Three separate scores in [0,1] (or None when nothing comparable is known):
- candidate_fit_score — how the confirmed profile's evidence meets the vacancy requirements;
- preference_fit_score — how the vacancy matches the owner's stated preferences;
- data_confidence_score — completeness/reliability of the vacancy record.

Missing information is `unknown`: it is excluded from the weighted average (never counted as 0
or as a win) and listed in the breakdown. Overall = documented weights × the two fit scores,
and only when both exist.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from unjobless.db.models import (
    CareerPreferences,
    JobLocation,
    JobRequirement,
    JobSkill,
    JobVacancy,
    MatchAnalysis,
)
from unjobless.domain.state_machines import OPEN_STATUSES
from unjobless.intelligence import normalize as N
from unjobless.intelligence.companies import normalize_company
from unjobless.intelligence.text import normalize_key
from unjobless.profile.cv import active_version
from unjobless.profile.schemas import CareerPreferencesData, ProfileData

ALGORITHM_VERSION = "1.0"
DEFAULT_WEIGHTS = {"candidate_fit": 0.6, "preference_fit": 0.4}
CFIT_WEIGHTS = {"required_skills": 0.5, "preferred_skills": 0.15, "role_relevance": 0.2, "education": 0.15}
PFIT_WEIGHTS = {
    "role_target": 0.25,
    "work_arrangement": 0.2,
    "location": 0.2,
    "employment_type": 0.15,
    "compensation": 0.15,
    "industry": 0.05,
}
EDU_RANK = {"HIGH_SCHOOL": 1, "DIPLOMA": 2, "STUDENT": 2, "BACHELOR": 3, "MASTER": 4, "DOCTORATE": 5}


@dataclass
class Component:
    name: str
    score: float | None  # None = unknown
    weight: float
    detail: str
    matched: list[dict[str, Any]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    partial: list[str] = field(default_factory=list)


def _weighted(components: list[Component]) -> float | None:
    known = [c for c in components if c.score is not None and c.weight > 0]
    if not known:
        return None
    tw = sum(c.weight for c in known)
    return round(sum(c.score * c.weight for c in known) / tw, 4)  # type: ignore[operator]


def get_preferences(db: Session) -> CareerPreferencesData:
    row = db.execute(select(CareerPreferences)).scalar_one_or_none()
    return CareerPreferencesData.model_validate(row.data) if row else CareerPreferencesData()


def preferences_hash(p: CareerPreferencesData) -> str:
    return hashlib.sha256(json.dumps(p.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()


def _candidate_skill_index(profile: ProfileData) -> dict[str, list[str]]:
    idx: dict[str, list[str]] = {}
    for s in profile.skills:
        idx.setdefault(N.normalized_skill_key(s.name), []).append(s.id)
    for p in profile.projects:
        for t in p.technologies:
            idx.setdefault(N.normalized_skill_key(t), []).append(p.id)
    for x in profile.experiences:
        for b in x.bullets:
            for canonical, *_ in N.find_skills(b.text):
                idx.setdefault(N.normalized_skill_key(canonical), []).append(b.id)
    return idx


def _gpa(profile: ProfileData) -> float | None:
    for e in profile.educations:
        if e.gpa:
            try:
                return float(e.gpa.replace(",", ".").split("/")[0])
            except ValueError:
                continue
    return None


def _edu_level(profile: ProfileData, prefs: CareerPreferencesData) -> str | None:
    if prefs.education_level:
        return prefs.education_level
    for e in profile.educations:
        d = (e.degree or "").lower()
        for k, v in (
            ("s3", "DOCTORATE"),
            ("phd", "DOCTORATE"),
            ("s2", "MASTER"),
            ("master", "MASTER"),
            ("s1", "BACHELOR"),
            ("bachelor", "BACHELOR"),
            ("sarjana", "BACHELOR"),
            ("d3", "DIPLOMA"),
            ("sma", "HIGH_SCHOOL"),
            ("smk", "HIGH_SCHOOL"),
        ):
            if re.search(rf"\b{k}\b", d):
                return v
    return None


def eligibility(
    v: JobVacancy, profile: ProfileData | None, prefs: CareerPreferencesData
) -> tuple[bool | None, list[str], list[str]]:
    """(eligible, blocking reasons, unknowns). None = cannot tell."""
    reasons, unknowns = [], []
    excluded_co = {normalize_company(c) for c in prefs.excluded_companies}
    if v.company_name and normalize_company(v.company_name) in excluded_co:
        reasons.append(f"{v.company_name} is on your excluded companies list.")
    if v.industry and normalize_key(v.industry) in {normalize_key(i) for i in prefs.excluded_industries}:
        reasons.append(f"Industry {v.industry} is excluded in your preferences.")
    text = f"{v.title} {v.description or ''}".lower()
    for kw in prefs.excluded_keywords:
        if kw and re.search(rf"\b{re.escape(kw.lower())}\b", text):
            reasons.append(f"Mentions excluded keyword “{kw}”.")
    if v.min_gpa is not None:
        gpa = _gpa(profile) if profile else None
        if gpa is None:
            unknowns.append("Your GPA is not in your profile.")
        elif gpa < float(v.min_gpa):
            reasons.append(f"Requires GPA ≥ {v.min_gpa}; your profile shows {gpa}.")
    if v.min_semester is not None:
        if prefs.current_semester is None:
            unknowns.append("Your current semester is not set in preferences.")
        elif prefs.current_semester < v.min_semester:
            reasons.append(
                f"Requires semester ≥ {v.min_semester}; you are in semester {prefs.current_semester}."
            )
    if reasons:
        return False, reasons, unknowns
    return (None if unknowns else True), reasons, unknowns


def compute(
    db: Session, v: JobVacancy, profile: ProfileData | None, prefs: CareerPreferencesData
) -> dict[str, Any]:
    skills = db.execute(select(JobSkill).where(JobSkill.vacancy_id == v.id)).scalars().all()
    reqs = db.execute(select(JobRequirement).where(JobRequirement.vacancy_id == v.id)).scalars().all()
    locs = db.execute(select(JobLocation).where(JobLocation.vacancy_id == v.id)).scalars().all()
    required = [s for s in skills if s.required]
    preferred = [s for s in skills if not s.required]

    cfit: list[Component] = []
    if profile is None:
        cfit_score = None
    else:
        idx = _candidate_skill_index(profile)
        if required:
            matched = [
                {"skill": s.skill, "evidence": idx[s.normalized_skill]}
                for s in required
                if s.normalized_skill in idx
            ]
            missing = [s.skill for s in required if s.normalized_skill not in idx]
            cfit.append(
                Component(
                    "required_skills",
                    len(matched) / len(required),
                    CFIT_WEIGHTS["required_skills"],
                    f"{len(matched)} of {len(required)} required skills evidenced in your profile.",
                    matched,
                    missing,
                )
            )
        else:
            cfit.append(
                Component(
                    "required_skills",
                    None,
                    CFIT_WEIGHTS["required_skills"],
                    "The vacancy lists no required skills.",
                )
            )
        if preferred:
            matched = [
                {"skill": s.skill, "evidence": idx[s.normalized_skill]}
                for s in preferred
                if s.normalized_skill in idx
            ]
            cfit.append(
                Component(
                    "preferred_skills",
                    len(matched) / len(preferred),
                    CFIT_WEIGHTS["preferred_skills"],
                    f"{len(matched)} of {len(preferred)} preferred skills.",
                    matched,
                    [s.skill for s in preferred if s.normalized_skill not in idx],
                )
            )
        else:
            cfit.append(
                Component(
                    "preferred_skills", None, CFIT_WEIGHTS["preferred_skills"], "No preferred skills listed."
                )
            )
        title_tokens = set(normalize_key(v.title).split()) - {
            "intern",
            "internship",
            "magang",
            "staff",
            "junior",
            "senior",
            "the",
            "and",
            "di",
            "untuk",
        }
        role_hits = []
        for x in profile.experiences:
            overlap = title_tokens & set(normalize_key(x.title).split())
            if overlap:
                role_hits.append(
                    {"fact": x.id, "text": f"{x.title} at {x.organization}", "overlap": sorted(overlap)}
                )
        for pr in profile.projects:
            overlap = title_tokens & set(
                normalize_key(f"{pr.name} {pr.role or ''} {pr.description or ''}").split()
            )
            if len(overlap) >= 1:
                role_hits.append({"fact": pr.id, "text": pr.name, "overlap": sorted(overlap)})
        if title_tokens:
            score = min(
                1.0, len({t for h in role_hits for t in h["overlap"]}) / max(1, min(3, len(title_tokens)))
            )
            cfit.append(
                Component(
                    "role_relevance",
                    score,
                    CFIT_WEIGHTS["role_relevance"],
                    f"{len(role_hits)} related experiences/projects.",
                    role_hits[:5],
                )
            )
        edu_req = next((r.value for r in reqs if r.kind == "education"), None) or v.education_level
        mine = _edu_level(profile, prefs)
        if edu_req and mine and edu_req in EDU_RANK and mine in EDU_RANK:
            ok = EDU_RANK[mine] >= EDU_RANK[edu_req] or (
                edu_req == "BACHELOR" and mine == "STUDENT" and v.employment_type.value == "INTERNSHIP"
            )
            cfit.append(
                Component(
                    "education",
                    1.0 if ok else 0.0,
                    CFIT_WEIGHTS["education"],
                    f"Requires {edu_req}; you: {mine}.",
                )
            )
        else:
            cfit.append(
                Component(
                    "education",
                    None,
                    CFIT_WEIGHTS["education"],
                    "Education requirement or your level is unknown.",
                )
            )
        cfit_score = _weighted(cfit)

    pfit: list[Component] = []
    targets = [normalize_key(t) for t in prefs.target_roles + prefs.job_families if t]
    if targets:
        vt = normalize_key(f"{v.title} {v.job_family or ''}")
        hit = [t for t in targets if t and (t in vt or set(t.split()) <= set(vt.split()))]
        partial = [t for t in targets if t not in hit and set(t.split()) & set(vt.split())]
        pfit.append(
            Component(
                "role_target",
                1.0 if hit else 0.5 if partial else 0.0,
                PFIT_WEIGHTS["role_target"],
                "Matches a target role."
                if hit
                else "Partly related to a target role."
                if partial
                else "Not one of your target roles.",
            )
        )
    wa = v.work_arrangement.value
    if prefs.work_arrangements:
        if wa == "UNKNOWN":
            pfit.append(
                Component(
                    "work_arrangement", None, PFIT_WEIGHTS["work_arrangement"], "Work arrangement not stated."
                )
            )
        else:
            pfit.append(
                Component(
                    "work_arrangement",
                    1.0 if wa in prefs.work_arrangements or wa == "FLEXIBLE" else 0.0,
                    PFIT_WEIGHTS["work_arrangement"],
                    f"{wa.title()} vs your preference.",
                )
            )
    cities = {normalize_key(c) for c in prefs.preferred_cities}
    if cities or not prefs.remote_ok:
        remote = wa == "REMOTE" or any(loc.is_remote for loc in locs)
        vac_cities = {normalize_key(loc.city) for loc in locs if loc.city}
        if remote and prefs.remote_ok:
            pfit.append(
                Component("location", 1.0, PFIT_WEIGHTS["location"], "Remote, and you accept remote work.")
            )
        elif vac_cities:
            pfit.append(
                Component(
                    "location",
                    1.0 if vac_cities & cities else 0.0,
                    PFIT_WEIGHTS["location"],
                    f"Location: {', '.join(sorted(vac_cities))}.",
                )
            )
        else:
            pfit.append(
                Component(
                    "location", None, PFIT_WEIGHTS["location"], "Location not stated or not recognised."
                )
            )
    if prefs.employment_types:
        et = v.employment_type.value
        pfit.append(
            Component(
                "employment_type",
                None if et == "UNKNOWN" else (1.0 if et in prefs.employment_types else 0.0),
                PFIT_WEIGHTS["employment_type"],
                "Employment type not stated." if et == "UNKNOWN" else f"{et.replace('_', ' ').title()}.",
            )
        )
    if prefs.min_compensation:
        if v.salary_max is None and v.salary_min is None:
            pfit.append(
                Component(
                    "compensation",
                    None,
                    PFIT_WEIGHTS["compensation"],
                    "Compensation not stated (treated as unknown, not zero).",
                )
            )
        elif (v.salary_currency or "IDR") != prefs.compensation_currency or (
            v.pay_period and v.pay_period.value != prefs.compensation_period
        ):
            pfit.append(
                Component(
                    "compensation",
                    None,
                    PFIT_WEIGHTS["compensation"],
                    "Compensation is in a different currency/period; not compared automatically.",
                )
            )
        else:
            top = float(v.salary_max or v.salary_min or 0)
            pfit.append(
                Component(
                    "compensation",
                    1.0 if top >= prefs.min_compensation else round(top / prefs.min_compensation, 2),
                    PFIT_WEIGHTS["compensation"],
                    f"Up to {top:,.0f} vs your minimum {prefs.min_compensation:,.0f}.",
                )
            )
    if prefs.industries:
        pfit.append(
            Component(
                "industry",
                None
                if not v.industry
                else (
                    1.0 if normalize_key(v.industry) in {normalize_key(i) for i in prefs.industries} else 0.0
                ),
                PFIT_WEIGHTS["industry"],
                "Industry unknown." if not v.industry else f"Industry: {v.industry}.",
            )
        )
    pfit_score = _weighted(pfit)

    eligible, blocks, unknown_elig = eligibility(v, profile, prefs)
    if eligible is False:
        pfit_score = 0.0  # a hard exclusion/ineligibility makes the preference fit zero
    overall = None
    if cfit_score is not None and pfit_score is not None:
        overall = round(
            DEFAULT_WEIGHTS["candidate_fit"] * cfit_score + DEFAULT_WEIGHTS["preference_fit"] * pfit_score, 4
        )
    unknowns = [c.name for c in cfit + pfit if c.score is None] + unknown_elig
    return {
        "candidate_fit_score": cfit_score,
        "preference_fit_score": pfit_score,
        "data_confidence_score": float(v.data_confidence or 0.0),
        "overall_score": overall,
        "eligible": eligible,
        "weights": {
            "overall": DEFAULT_WEIGHTS,
            "candidate_fit": CFIT_WEIGHTS,
            "preference_fit": PFIT_WEIGHTS,
        },
        "breakdown": {
            "candidate_fit": [c.__dict__ for c in cfit],
            "preference_fit": [c.__dict__ for c in pfit],
            "eligibility_blocks": blocks,
            "unknowns": unknowns,
            "note": "Scores are transparent heuristics, not a prediction of hiring success.",
        },
    }


def upsert_match(
    db: Session,
    v: JobVacancy,
    profile_version_id: int | None,
    profile: ProfileData | None,
    prefs: CareerPreferencesData,
) -> MatchAnalysis:
    ph = preferences_hash(prefs)
    res = compute(db, v, profile, prefs)
    db.execute(
        update(MatchAnalysis)
        .where(MatchAnalysis.vacancy_id == v.id, MatchAnalysis.is_current.is_(True))
        .values(is_current=False)
    )
    m = db.execute(
        select(MatchAnalysis).where(
            MatchAnalysis.vacancy_id == v.id,
            MatchAnalysis.profile_version_id == profile_version_id,
            MatchAnalysis.preferences_hash == ph,
            MatchAnalysis.algorithm_version == ALGORITHM_VERSION,
        )
    ).scalar_one_or_none()
    if m is None:
        m = MatchAnalysis(
            vacancy_id=v.id,
            profile_version_id=profile_version_id,
            preferences_hash=ph,
            algorithm_version=ALGORITHM_VERSION,
            **res,
            is_current=True,
        )
        db.add(m)
    else:
        for k, val in res.items():
            setattr(m, k, val)
        m.is_current = True
    db.flush()
    return m


def recompute_all(db: Session, *, only_open: bool = False) -> int:
    pv = active_version(db)
    profile = ProfileData.model_validate(pv.data) if pv else None
    prefs = get_preferences(db)
    q = select(JobVacancy).where(JobVacancy.merged_into_id.is_(None))
    if only_open:
        q = q.where(JobVacancy.verification_status.in_(OPEN_STATUSES))
    n = 0
    for v in db.execute(q).scalars():
        upsert_match(db, v, pv.id if pv else None, profile, prefs)
        n += 1
    return n
