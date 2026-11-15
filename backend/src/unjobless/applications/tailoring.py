"""Truthful, evidence-grounded CV tailoring and cover letters.

Every proposed claim references profile fact ids. Automatic checks reject (by default) any AI
rewrite that introduces numbers, skills or tools absent from the referenced facts. The master
profile is never modified; each tailored result and each round of owner decisions is a new,
immutable TailoredResume row (parent → child).
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from unjobless.ai.redact import redact_profile
from unjobless.core.audit import audit
from unjobless.core.errors import NotFound, ValidationFailed
from unjobless.db.models import CoverLetter, JobSkill, JobVacancy, TailoredResume
from unjobless.intelligence import normalize as N
from unjobless.intelligence.text import normalize_key
from unjobless.profile.cv import active_version
from unjobless.profile.schemas import ProfileData

NUM = re.compile(r"\d+(?:[.,]\d+)?%?")
Lang = Literal["id", "en"]


def _cid() -> str:
    return "c_" + uuid.uuid4().hex[:8]


def _skills_in(text: str) -> set[str]:
    return {c for c, *_ in N.find_skills(text)}


def check_claim(proposed: str, sources: list[str]) -> list[str]:
    """Problems that make a rewrite unsafe to accept automatically."""
    src = " ".join(sources)
    issues = []
    new_nums = set(NUM.findall(proposed)) - set(NUM.findall(src))
    if new_nums:
        issues.append(f"Introduces numbers not in your profile: {', '.join(sorted(new_nums))}")
    new_skills = _skills_in(proposed) - _skills_in(src)
    if new_skills:
        issues.append(f"Mentions skills/tools not in the referenced facts: {', '.join(sorted(new_skills))}")
    return issues


def _vacancy_context(db: Session, v: JobVacancy) -> dict[str, Any]:
    skills = db.execute(select(JobSkill).where(JobSkill.vacancy_id == v.id)).scalars().all()
    return {
        "title": v.title, "company": v.company_name, "required_skills": [s.skill for s in skills if s.required],
        "preferred_skills": [s.skill for s in skills if not s.required], "responsibilities": (v.details or {}).get("responsibilities", [])[:15],
        "language": v.language,
    }


def _relevance(text: str, keys: set[str]) -> int:
    t = set(normalize_key(text).split())
    return len(t & keys)


def baseline(profile: ProfileData, vac: dict[str, Any], lang: Lang) -> dict[str, Any]:
    """Deterministic tailoring (no AI): reorder by relevance, keep wording verbatim."""
    req = {N.normalized_skill_key(s) for s in vac["required_skills"] + vac["preferred_skills"]}
    title_keys = set(normalize_key(vac["title"]).split()) | {normalize_key(s) for s in vac["required_skills"]}
    skills_sorted = sorted(profile.skills, key=lambda s: (N.normalized_skill_key(s.name) not in req, s.name.lower()))
    entries = [(x.id, "experience", x.title + " " + " ".join(b.text for b in x.bullets)) for x in profile.experiences] + [
        (p.id, "project", f"{p.name} {p.description or ''} {' '.join(p.technologies)} " + " ".join(b.text for b in p.bullets)) for p in profile.projects
    ]
    order = [eid for eid, _k, txt in sorted(entries, key=lambda e: -_relevance(e[2], title_keys))]
    have = {N.normalized_skill_key(s.name) for s in profile.skills} | {N.normalized_skill_key(t) for p in profile.projects for t in p.technologies}
    missing = [s for s in vac["required_skills"] if N.normalized_skill_key(s) not in have]
    matched = [s for s in skills_sorted if N.normalized_skill_key(s.name) in req]
    claims: list[dict[str, Any]] = []
    if profile.headline:
        claims.append({"id": _cid(), "section": "headline", "original": profile.headline, "proposed": profile.headline, "fact_ids": [], "issues": [], "accepted": True, "source": "profile"})
    elif matched:
        edu = profile.educations[0] if profile.educations else None
        base = (f"{edu.degree or ''} {edu.field or ''}".strip() + (" — " if edu else "")) if edu else ""
        joiner = "berpengalaman dengan" if lang == "id" else "experienced with"
        text = f"{base}{joiner} {', '.join(s.name for s in matched[:4])}".strip()
        claims.append({"id": _cid(), "section": "headline", "original": None, "proposed": text, "fact_ids": [s.id for s in matched[:4]] + ([edu.id] if edu else []), "issues": [], "accepted": None, "source": "composed_from_facts"})
    if profile.summary:
        claims.append({"id": _cid(), "section": "summary", "original": profile.summary, "proposed": profile.summary, "fact_ids": [], "issues": [], "accepted": True, "source": "profile"})
    return {"skill_order": [s.id for s in skills_sorted], "entry_order": order, "claims": claims, "missing_requirements": missing, "needs_user_confirmation": [], "method": "rules"}


def with_ai(db: Session, profile: ProfileData, vac: dict[str, Any], lang: Lang, base: dict[str, Any], vacancy_id: int) -> tuple[dict[str, Any], int | None]:
    from unjobless.ai.gateway import AIBudgetExceeded, AINotConfigured, AITaskFailed, AIUnavailable, ai_available, run_task

    if not ai_available(db, "cv_tailoring"):
        return base, None
    facts = profile.facts()
    payload = {
        "output_language": "Indonesian" if lang == "id" else "English",
        "profile_facts": redact_profile([{"id": k, **v} for k, v in facts.items()]),
        "vacancy_untrusted": vac,
    }
    try:
        res = run_task(db, "cv_tailoring", payload, input_ref=f"vacancy:{vacancy_id}")
    except (AINotConfigured, AIUnavailable, AIBudgetExceeded, AITaskFailed):
        return {**base, "ai_note": "AI tailoring unavailable; showing deterministic reordering only."}, None
    o: Any = res.output
    claims: list[dict[str, Any]] = []

    def add(section: str, proposed: str, fact_ids: list[str], original: str | None = None, changed: bool = False) -> None:
        valid_ids = [f for f in fact_ids if f in facts]
        sources = [str(facts[f]["text"]) for f in valid_ids]
        issues = check_claim(proposed, sources + ([original] if original else []))
        if not valid_ids:
            issues.append("No supporting profile fact was referenced.")
        if changed:
            issues.append("The model reported that facts changed.")
        claims.append({"id": _cid(), "section": section, "original": original, "proposed": proposed, "fact_ids": valid_ids, "issues": issues,
                       "accepted": False if issues else None, "source": "ai"})

    add("headline", o.headline, o.headline_fact_ids)
    add("summary", o.summary, o.summary_fact_ids)
    for sec in o.sections:
        for b in sec.bullets:
            if b.source_fact_id in facts and facts[b.source_fact_id]["kind"] == "bullet":
                add("bullet", b.rewritten, [b.source_fact_id], original=str(facts[b.source_fact_id]["text"]), changed=b.changed_facts)
    known_skill_ids = {s.id for s in profile.skills}
    skill_order = [s for s in o.skill_order if s in known_skill_ids] + [s for s in base["skill_order"] if s not in o.skill_order]
    entry_ids = {x.id for x in profile.experiences} | {p.id for p in profile.projects}
    entry_order = [e for e in o.entry_order if e in entry_ids] + [e for e in base["entry_order"] if e not in o.entry_order]
    have = {N.normalized_skill_key(s.name) for s in profile.skills}
    missing = list(dict.fromkeys(base["missing_requirements"] + [m for m in o.missing_requirements if N.normalized_skill_key(m) not in have]))
    return {"skill_order": skill_order, "entry_order": entry_order, "claims": claims, "missing_requirements": missing,
            "needs_user_confirmation": list(o.needs_user_confirmation), "method": f"ai:{res.run.model}"}, res.run.id


def generate(db: Session, vacancy_id: int, *, language: Lang = "id", use_ai: bool = True) -> TailoredResume:
    v = db.get(JobVacancy, vacancy_id)
    if v is None:
        raise NotFound("Vacancy not found.")
    pv = active_version(db)
    if pv is None:
        raise ValidationFailed("Confirm your master profile before tailoring a CV.", code="profile_required")
    profile = ProfileData.model_validate(pv.data)
    vac = _vacancy_context(db, v)
    content = baseline(profile, vac, language)
    run_id = None
    if use_ai:
        content, run_id = with_ai(db, profile, vac, language, content, v.id)
    tr = TailoredResume(vacancy_id=v.id, profile_version_id=pv.id, language=language, content=content,
                        generation_settings={"use_ai": use_ai, "language": language}, ai_task_run_id=run_id, template="ats_classic")
    db.add(tr)
    db.flush()
    audit(db, "tailoring.generated", target_type="tailored_resume", target_id=tr.id, details={"vacancy_id": v.id, "method": content.get("method")})
    return tr


def decide(db: Session, tr: TailoredResume, decisions: dict[str, Any], *, edits: dict[str, str] | None = None, finalize: bool = False, template: str | None = None) -> TailoredResume:
    """Owner accepts/rejects/edits claims. Produces a new immutable child version."""
    content = {**tr.content, "claims": [dict(c) for c in tr.content.get("claims", [])]}
    pv_facts = ProfileData.model_validate(_profile_data(db, tr)).facts()
    for c in content["claims"]:
        if c["id"] in decisions:
            want = decisions[c["id"]]
            if want is True and c.get("issues") and not decisions.get(f"{c['id']}:confirm_issues"):
                raise ValidationFailed(f"Claim {c['id']} has unresolved issues; confirm them explicitly to accept.", code="claim_needs_confirmation")
            c["accepted"] = bool(want) if want is not None else None
        if edits and c["id"] in edits:
            new = edits[c["id"]].strip()
            c["issues"] = check_claim(new, [str(pv_facts[f]["text"]) for f in c.get("fact_ids", []) if f in pv_facts] + ([c["original"]] if c.get("original") else []))
            c["proposed"], c["edited_by_owner"] = new, True
            c["accepted"] = None if c["issues"] else True
    child = TailoredResume(vacancy_id=tr.vacancy_id, profile_version_id=tr.profile_version_id, parent_id=tr.id, language=tr.language,
                           content=content, generation_settings=tr.generation_settings, ai_task_run_id=tr.ai_task_run_id,
                           finalized=finalize, template=template or tr.template)
    db.add(child)
    db.flush()
    audit(db, "tailoring.decided", target_type="tailored_resume", target_id=child.id, details={"parent": tr.id, "finalized": finalize})
    return child


def _profile_data(db: Session, tr: TailoredResume) -> dict[str, Any]:
    from unjobless.db.models import CandidateProfileVersion

    pv = db.get(CandidateProfileVersion, tr.profile_version_id)
    assert pv is not None
    return pv.data


def resolved_document(db: Session, tr: TailoredResume) -> dict[str, Any]:
    """The CV that would be exported: master facts reordered + only ACCEPTED claims applied."""
    profile = ProfileData.model_validate(_profile_data(db, tr))
    c = tr.content
    accepted = {cl["id"]: cl for cl in c.get("claims", []) if cl.get("accepted") is True}
    headline = next((cl["proposed"] for cl in accepted.values() if cl["section"] == "headline"), profile.headline)
    summary = next((cl["proposed"] for cl in accepted.values() if cl["section"] == "summary"), profile.summary)
    bullet_rewrites = {cl["fact_ids"][0]: cl["proposed"] for cl in accepted.values() if cl["section"] == "bullet" and cl.get("fact_ids")}
    pos = {e: i for i, e in enumerate(c.get("entry_order", []))}
    exps = sorted(profile.experiences, key=lambda x: pos.get(x.id, 999))
    prjs = sorted(profile.projects, key=lambda x: pos.get(x.id, 999))
    sk_pos = {s: i for i, s in enumerate(c.get("skill_order", []))}
    skills = sorted(profile.skills, key=lambda s: sk_pos.get(s.id, 999))
    return {
        "language": tr.language,
        "contact": profile.contact.model_dump(), "links": profile.links, "headline": headline, "summary": summary,
        "experiences": [{"title": x.title, "organization": x.organization, "location": x.location, "start": x.start, "end": x.end, "kind": x.kind,
                         "bullets": [bullet_rewrites.get(b.id, b.text) for b in x.bullets]} for x in exps],
        "projects": [{"name": p.name, "role": p.role, "description": p.description, "technologies": p.technologies, "url": p.url,
                      "bullets": [bullet_rewrites.get(b.id, b.text) for b in p.bullets]} for p in prjs],
        "educations": [e.model_dump(include={"institution", "degree", "field", "start", "end", "gpa"}) for e in profile.educations],
        "skills": [s.name for s in skills],
        "certifications": [s.model_dump(include={"name", "issuer", "date"}) for s in profile.certifications],
        "awards": [s.model_dump(include={"name", "issuer", "date"}) for s in profile.awards],
        "publications": [s.model_dump(include={"name", "issuer", "date"}) for s in profile.publications],
        "languages": [f"{lang.language}{' — ' + lang.proficiency if lang.proficiency else ''}" for lang in profile.languages],
    }


def cover_letter(db: Session, vacancy_id: int, *, language: Lang = "id", tailored_resume_id: int | None = None, use_ai: bool = True) -> CoverLetter:
    v = db.get(JobVacancy, vacancy_id)
    pv = active_version(db)
    if v is None:
        raise NotFound("Vacancy not found.")
    if pv is None:
        raise ValidationFailed("Confirm your master profile first.", code="profile_required")
    profile = ProfileData.model_validate(pv.data)
    facts = profile.facts()
    vac = _vacancy_context(db, v)
    body, claims, run_id = None, [], None
    if use_ai:
        from unjobless.ai.gateway import AIBudgetExceeded, AINotConfigured, AITaskFailed, AIUnavailable, ai_available, run_task

        if ai_available(db, "cover_letter"):
            try:
                res = run_task(db, "cover_letter", {"output_language": "Indonesian" if language == "id" else "English",
                                                    "profile_facts": redact_profile([{"id": k, **x} for k, x in facts.items()]), "vacancy_untrusted": vac},
                               input_ref=f"vacancy:{v.id}")
                o: Any = res.output
                body = "\n\n".join([o.greeting, *o.paragraphs, o.closing])
                for cl in o.claims:
                    ids = [f for f in cl.fact_ids if f in facts]
                    issues = check_claim(cl.sentence, [str(facts[f]["text"]) for f in ids])
                    claims.append({"sentence": cl.sentence, "fact_ids": ids, "issues": issues + ([] if ids else ["No supporting fact referenced."])})
                run_id = res.run.id
            except (AINotConfigured, AIUnavailable, AIBudgetExceeded, AITaskFailed):
                body = None
    if body is None:
        body, claims = _template_letter(profile, vac, language)
    cl_row = CoverLetter(vacancy_id=v.id, profile_version_id=pv.id, tailored_resume_id=tailored_resume_id, language=language, body=body, claims=claims, ai_task_run_id=run_id)
    db.add(cl_row)
    db.flush()
    return cl_row


def _template_letter(profile: ProfileData, vac: dict[str, Any], lang: Lang) -> tuple[str, list[dict[str, Any]]]:
    have = {N.normalized_skill_key(s.name): s for s in profile.skills}
    matched = [have[N.normalized_skill_key(s)] for s in vac["required_skills"] if N.normalized_skill_key(s) in have][:4]
    exp = profile.experiences[0] if profile.experiences else None
    edu = profile.educations[0] if profile.educations else None
    company = vac.get("company") or ("perusahaan Anda" if lang == "id" else "your company")
    claims = []
    if lang == "id":
        parts = ["Yth. Tim Rekrutmen,", f"Saya ingin melamar posisi {vac['title']} di {company}."]
        if edu:
            s = f"Saat ini saya menempuh/telah menyelesaikan {' '.join(x for x in [edu.degree, edu.field] if x) or 'pendidikan'} di {edu.institution}."
            parts.append(s)
            claims.append({"sentence": s, "fact_ids": [edu.id], "issues": []})
        if exp:
            s = f"Pengalaman saya sebagai {exp.title} di {exp.organization} relevan dengan posisi ini."
            parts.append(s)
            claims.append({"sentence": s, "fact_ids": [exp.id], "issues": []})
        if matched:
            s = f"Saya memiliki kemampuan {', '.join(m.name for m in matched)} yang dibutuhkan untuk peran ini."
            parts.append(s)
            claims.append({"sentence": s, "fact_ids": [m.id for m in matched], "issues": []})
        parts += ["Terima kasih atas waktu dan pertimbangan Anda.", "Hormat saya,", profile.contact.full_name or ""]
    else:
        parts = ["Dear Hiring Team,", f"I am applying for the {vac['title']} position at {company}."]
        if edu:
            s = f"I am studying or have completed {' '.join(x for x in [edu.degree, edu.field] if x) or 'my studies'} at {edu.institution}."
            parts.append(s)
            claims.append({"sentence": s, "fact_ids": [edu.id], "issues": []})
        if exp:
            s = f"My experience as {exp.title} at {exp.organization} is relevant to this role."
            parts.append(s)
            claims.append({"sentence": s, "fact_ids": [exp.id], "issues": []})
        if matched:
            s = f"I bring skills in {', '.join(m.name for m in matched)}, which this role requires."
            parts.append(s)
            claims.append({"sentence": s, "fact_ids": [m.id for m in matched], "issues": []})
        parts += ["Thank you for your time and consideration.", "Kind regards,", profile.contact.full_name or ""]
    return "\n\n".join(p for p in parts if p), claims
