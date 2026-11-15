"""Structured vacancy extraction with field-level evidence.

Layers (later layers fill gaps, never overwrite explicit structured values):
1. structured source data (documented ATS API fields, schema.org JobPosting) → EXPLICIT;
2. deterministic rules over the text (Indonesian + English) → EXPLICIT with verbatim excerpts;
3. optional AI extraction (schema-validated). Each AI value must be backed by an excerpt that is
   actually found in the source text; otherwise it is downgraded to INFERRED and flagged.

Missing values stay null. Nothing is guessed.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from unjobless.ai.task_schemas import Evidence, JobExtraction
from unjobless.intelligence import normalize as N
from unjobless.intelligence.text import find_span, guess_language

EXTRACTOR_VERSION = "1.0"

LIST_FIELDS = [
    "locations",
    "majors",
    "required_skills",
    "preferred_skills",
    "tools",
    "language_requirements",
    "certifications",
    "legal_requirements",
    "soft_skills",
    "application_documents",
    "selection_stages",
    "responsibilities",
    "deliverables",
    "benefits",
    "remote_eligible_countries",
]


def empty_extraction() -> dict[str, Any]:
    base: dict[str, Any] = {f: None for f in JobExtraction.model_fields}
    for f in LIST_FIELDS + ["evidence", "warnings"]:
        base[f] = []
    base.update(
        is_job_posting=False,
        work_arrangement="UNKNOWN",
        employment_type="UNKNOWN",
        seniority="UNKNOWN",
        pay_period="UNKNOWN",
    )
    return base


SECTION_HEADS = {
    "responsibilities": r"(responsibilities|what you('ll| will) do|job ?desc(ription)?|deskripsi pekerjaan|tanggung jawab|tugas|jobdesk)",
    "requirements": r"(requirements|qualifications|what we('re| are) looking for|kualifikasi|persyaratan|syarat|kriteria)",
    "benefits": r"(benefits?|perks|what we offer|fasilitas|keuntungan|benefit)",
    "documents": r"(documents?|dokumen|berkas|kelengkapan)",
    "stages": r"(selection process|hiring process|tahapan seleksi|proses seleksi|alur rekrutmen)",
    "nice": r"(nice to have|preferred|plus points?|bonus points?|diutamakan|nilai tambah)",
}
COMPANY_RE = re.compile(
    r"\b(?:PT|CV|Tbk|Perum|PD)\.?\s+[A-Z][\w&.-]*(?:\s+(?!di\b|in\b|at\b)[A-Z][\w&.-]*){0,4}"
)
HEAD_RE = re.compile(r"^\s*(?:#+\s*)?(" + "|".join(SECTION_HEADS.values()) + r")\s*:?\s*$", re.I | re.M)


def _sections(text: str) -> dict[str, list[tuple[str, int]]]:
    """Split text into headed sections; returns {section_kind: [(line, offset)]}."""
    out: dict[str, list[tuple[str, int]]] = {}
    heads = list(HEAD_RE.finditer(text))
    # Also treat "Requirements: a, b" inline heads
    for i, h in enumerate(heads):
        kind = next(
            (k for k, pat in SECTION_HEADS.items() if re.fullmatch(pat, h.group(1).strip(), re.I)), None
        )
        if not kind:
            continue
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        offset = h.end()
        for line in text[h.end() : end].split("\n"):
            stripped = line.strip().lstrip("-•*·●▪◦0123456789.) ").strip()
            if 2 < len(stripped) < 400:
                out.setdefault(kind, []).append((stripped, text.find(line.strip(), offset)))
            offset += len(line) + 1
    for kind, pat in SECTION_HEADS.items():
        for m in re.finditer(rf"\b{pat}\s*:\s*([^\n]{{3,400}})", text, re.I):
            items = [
                x.strip() for x in re.split(r"[;,]|\s-\s", m.group(m.lastindex or 1)) if len(x.strip()) > 2
            ]
            for it in items[:12]:
                out.setdefault(kind, []).append((it, m.start()))
    return out


def rules_extract(text: str, *, title: str | None = None, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    full = f"{title}\n{text}" if title and title not in text[:300] else text
    e = empty_extraction()
    ev: list[dict[str, Any]] = []

    def add(field: str, excerpt: str, conf: float = 0.8, origin: str = "EXPLICIT") -> None:
        ev.append({"field": field, "excerpt": excerpt.strip()[:500], "origin": origin, "confidence": conf})

    e["language"] = guess_language(full)
    if title:
        e["title"] = title.strip()[:300]
        add("title", title, 0.95)
    else:
        from unjobless.intelligence.signals import _role_guess

        role = _role_guess(None, full)
        if role:
            e["title"] = role[0][:300]
            add("title", role[2], 0.6 if role[1] == "EXPLICIT" else 0.4, role[1])
    cm = COMPANY_RE.search(full)
    if cm:
        e["company"] = cm.group(0).strip(" .,")[:300]
        add("company", cm.group(0), 0.75)
    m = N.employment_type(full)
    if m:
        e["employment_type"] = m.value
        add("employment_type", m.excerpt, 0.8)
    m = N.work_arrangement(full)
    if m:
        e["work_arrangement"] = m.value
        add("work_arrangement", m.excerpt, 0.8)
    if e["title"]:
        sen = N.seniority(e["title"])
        if sen:
            e["seniority"] = sen
    elif e["employment_type"] == "INTERNSHIP":
        e["seniority"] = "INTERN"
    sal = N.parse_salary(full)
    if sal:
        e.update(
            salary_min=sal.min,
            salary_max=sal.max,
            salary_currency=sal.currency,
            pay_period=sal.period or "UNKNOWN",
        )
        add("salary", sal.excerpt, 0.85)
        if sal.period is None:
            e["warnings"].append("Salary period not stated.")
    if N.UNPAID_RE.search(full):
        e["is_paid"] = False
        add("is_paid", N.UNPAID_RE.search(full).group(0), 0.9)  # type: ignore[union-attr]
    elif sal or N.PAID_RE.search(full):
        e["is_paid"] = True
        add("is_paid", sal.excerpt if sal else N.PAID_RE.search(full).group(0), 0.75)  # type: ignore[union-attr]
    dl = N.find_cued_date(full, N.DEADLINE_CUE)
    if dl:
        e["application_deadline"] = dl.value.isoformat()
        add("application_deadline", dl.excerpt, 0.85)
    st = N.find_cued_date(full, N.START_CUE)
    if st and (not dl or st.value != dl.value):
        e["start_date"] = st.value.isoformat()
        add("start_date", st.excerpt, 0.7)
    locs = N.find_locations(full)
    e["locations"] = [raw for raw, _s, _e in locs]
    for raw, _s, _e in locs:
        add("locations", raw, 0.75)
    urls = [u.rstrip(".,;") for u in N.URL_RE.findall(full)]
    apply_url = next(
        (u for u in urls if re.search(r"(apply|career|karir|job|lowongan|recruit|form|daftar)", u, re.I)),
        urls[0] if urls else None,
    )
    if apply_url:
        e["application_url"] = apply_url
        add("application_url", apply_url, 0.8)
    emails = N.EMAIL_RE.findall(full)
    if emails:
        e["application_email"] = emails[0]
        add("application_email", emails[0], 0.8)
    m2 = N.GPA_RE.search(full)
    if m2:
        e["min_gpa"] = float(m2.group(1).replace(",", "."))
        add("min_gpa", m2.group(0), 0.85)
    m2 = N.SEMESTER_RE.search(full)
    if m2:
        e["min_semester"] = int(m2.group(1) or m2.group(2))
        add("min_semester", m2.group(0), 0.7)
    m2 = N.EXPERIENCE_RE.search(full)
    if m2:
        e["experience_years_min"] = float(m2.group(1))
        add("experience_years_min", m2.group(0), 0.75)
    m2 = N.OPENINGS_RE.search(full)
    if m2 and 0 < int(m2.group(1)) < 500:
        e["openings_count"] = int(m2.group(1))
        add("openings_count", m2.group(0), 0.6)
    if e["employment_type"] == "INTERNSHIP":
        m2 = N.DURATION_RE.search(full)
        if m2:
            e["internship_duration_months"] = float(m2.group(1))
            add("internship_duration_months", m2.group(0), 0.75)
    m2 = N.EDU_RE.search(full)
    if m2:
        e["education_level"] = N.EDU_MAP.get(
            m2.group(1).lower().rstrip("'s"), N.EDU_MAP.get(m2.group(1).lower())
        )
        add("education_level", m2.group(0), 0.7)

    secs = _sections(full)
    req_lines = [ln for ln, _ in secs.get("requirements", [])]
    nice_lines = [ln for ln, _ in secs.get("nice", [])]
    e["responsibilities"] = _dedupe([ln for ln, _ in secs.get("responsibilities", [])])[:25]
    e["benefits"] = _dedupe([ln for ln, _ in secs.get("benefits", [])])[:20]
    e["application_documents"] = _dedupe([ln for ln, _ in secs.get("documents", [])])[:15]
    e["selection_stages"] = _dedupe([ln for ln, _ in secs.get("stages", [])])[:15]
    for f in ("responsibilities", "benefits"):
        for item in e[f][:5]:
            add(f, item, 0.7)

    req_text = "\n".join(req_lines) or full
    nice_text = "\n".join(nice_lines)
    required, preferred = [], []
    for canonical, matched, _s, _e in N.find_skills(req_text):
        required.append(canonical)
        add("required_skills", matched, 0.75 if req_lines else 0.55, "EXPLICIT" if req_lines else "INFERRED")
    for canonical, matched, _s, _e in N.find_skills(nice_text):
        if canonical not in required:
            preferred.append(canonical)
            add("preferred_skills", matched, 0.7)
    e["required_skills"], e["preferred_skills"] = required[:30], preferred[:20]
    if not req_lines and required:
        e["warnings"].append("Skills found in the text but no requirements section; treat as indicative.")
    soft = [
        s
        for s in required
        if s in {"Communication", "Leadership", "Teamwork", "Problem Solving", "Public Speaking"}
    ]
    e["soft_skills"] = soft
    e["required_skills"] = [s for s in e["required_skills"] if s not in soft]
    langs = [s for s in e["required_skills"] if s in {"English", "Mandarin"}]
    e["language_requirements"] = langs
    e["required_skills"] = [s for s in e["required_skills"] if s not in langs]
    e["portfolio_required"] = True if re.search(r"\bportfolio\b", req_text, re.I) else None
    if e["application_deadline"] and date.fromisoformat(e["application_deadline"]) < today:
        e["warnings"].append("The stated deadline has passed.")
    e["evidence"] = ev
    return e


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for x in items:
        k = x.lower()
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


def from_structured(s: dict[str, Any]) -> dict[str, Any]:
    """Explicit values from a documented API / JSON-LD record."""
    e = empty_extraction()
    ev: list[dict[str, Any]] = []
    prov = s.get("provenance", "structured")

    def put(field: str, value: Any, excerpt: Any = None) -> None:
        if value in (None, "", []):
            return
        e[field] = value
        ev.append(
            {
                "field": field,
                "excerpt": f"[{prov}] {str(excerpt if excerpt is not None else value)[:300]}",
                "origin": "EXPLICIT",
                "confidence": 0.95,
            }
        )

    put("title", s.get("title"))
    put("company", s.get("company"))
    put("department", s.get("department"))
    put("locations", [x for x in s.get("locations") or [] if x])
    if s.get("employment_type"):
        put("employment_type", s["employment_type"])
    elif s.get("commitment"):
        m = N.employment_type(str(s["commitment"]))
        if m:
            put("employment_type", m.value, s["commitment"])
    if s.get("work_arrangement"):
        put("work_arrangement", s["work_arrangement"])
    put("application_url", s.get("application_url"))
    put("industry", s.get("industry"))
    put("openings_count", s.get("openings_count") if isinstance(s.get("openings_count"), int) else None)
    d = N.parse_iso_date(s.get("deadline"))
    if d:
        put("application_deadline", d.isoformat(), s.get("deadline"))
    sal = s.get("salary") or {}
    if sal and (sal.get("min") is not None or sal.get("max") is not None):
        put("salary_min", float(sal["min"]) if sal.get("min") is not None else None, sal)
        put("salary_max", float(sal["max"]) if sal.get("max") is not None else None, sal)
        put("salary_currency", sal.get("currency"))
        if sal.get("period"):
            put("pay_period", sal["period"])
    countries = [c for c in s.get("remote_eligible_countries") or [] if c]
    put("remote_eligible_countries", countries)
    e["is_job_posting"] = bool(s.get("title"))
    e["evidence"] = ev
    return e


def merge(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    """Fill gaps in `primary` from `secondary`; never overwrite a primary value."""
    out = dict(primary)
    for f in JobExtraction.model_fields:
        if f in ("evidence", "warnings"):
            continue
        pv, sv = out.get(f), secondary.get(f)
        unknown = pv in (None, [], "UNKNOWN") or (f == "is_job_posting" and pv is False)
        if unknown and sv not in (None, [], "UNKNOWN"):
            out[f] = sv
    present = {(x["field"], x["excerpt"]) for x in out.get("evidence", [])}
    out["evidence"] = list(out.get("evidence", [])) + [
        x for x in secondary.get("evidence", []) if (x["field"], x["excerpt"]) not in present
    ]
    out["warnings"] = _dedupe(list(out.get("warnings", [])) + list(secondary.get("warnings", [])))
    return out


def verify_ai_evidence(ai: dict[str, Any], source_text: str) -> dict[str, Any]:
    """Downgrade AI evidence whose excerpt is not in the source; null out unsupported scalar facts."""
    out = dict(ai)
    good: list[dict[str, Any]] = []
    supported: set[str] = set()
    for item in ai.get("evidence", []):
        if find_span(source_text, item.get("excerpt", "")):
            good.append(item)
            supported.add(item["field"])
        else:
            good.append(
                {**item, "origin": "INFERRED", "confidence": min(0.3, float(item.get("confidence", 0.3)))}
            )
    out["evidence"] = good
    # High-risk facts must be evidenced verbatim or they are dropped (never fabricate).
    for f in ("application_deadline", "salary_min", "salary_max", "application_url", "is_paid", "min_gpa"):
        field_key = "salary" if f.startswith("salary") else f
        if out.get(f) is not None and field_key not in supported and f not in supported:
            out[f] = None
            out.setdefault("warnings", []).append(
                f"Dropped AI value for {f}: no verbatim evidence in the source."
            )
    url = out.get("application_url")
    if url and url not in source_text:
        out["application_url"] = None
    return out


def extract(
    text: str,
    *,
    title: str | None = None,
    structured: list[dict[str, Any]] | None = None,
    db: Any = None,
    use_ai: bool = True,
    input_ref: str | None = None,
    today: date | None = None,
) -> tuple[JobExtraction, str]:
    """Return (validated extraction, method)."""
    result = empty_extraction()
    method = []
    for s in structured or []:
        result = merge(result, from_structured(s))
        method.append(s.get("provenance", "structured"))
    desc = text
    if structured and structured[0].get("description_text"):
        desc = structured[0]["description_text"]
    title = title or result.get("title")
    rules = rules_extract(desc, title=title, today=today)
    result = merge(result, rules)
    method.append("rules")
    if use_ai and db is not None:
        from unjobless.ai.gateway import (
            AIBudgetExceeded,
            AINotConfigured,
            AITaskFailed,
            AIUnavailable,
            ai_available,
            run_task,
        )

        if ai_available(db, "job_extraction"):
            try:
                res = run_task(
                    db,
                    "job_extraction",
                    {"title_hint": title, "text_untrusted": desc[:40000]},
                    input_ref=input_ref,
                )
                ai = verify_ai_evidence(res.output.model_dump(mode="json"), desc)
                result = merge(result, ai)
                method.append(f"ai:{res.run.model}")
            except (AINotConfigured, AIUnavailable, AIBudgetExceeded, AITaskFailed):
                result["warnings"] = [
                    *result["warnings"],
                    "AI extraction unavailable; rule-based extraction only.",
                ]
    result["is_job_posting"] = bool(
        result.get("is_job_posting")
        or (
            result.get("title")
            and (result.get("application_url") or result.get("application_email") or structured)
        )
    )
    result["evidence"] = [Evidence(**x).model_dump() for x in result["evidence"] if x.get("excerpt")]
    return JobExtraction.model_validate(result), "+".join(method)


def data_confidence(x: JobExtraction) -> float:
    """Completeness/reliability of the record (not a quality judgement of the job)."""
    checks = [
        x.title is not None,
        x.company is not None,
        bool(x.locations) or x.work_arrangement == "REMOTE",
        x.employment_type != "UNKNOWN",
        x.application_url is not None or x.application_email is not None,
        bool(x.responsibilities),
        bool(x.required_skills) or x.education_level is not None,
        x.application_deadline is not None,
        x.salary_min is not None or x.is_paid is not None,
    ]
    explicit_share = (
        (sum(1 for e in x.evidence if e.origin == "EXPLICIT") / len(x.evidence)) if x.evidence else 0.0
    )
    return round(0.75 * (sum(checks) / len(checks)) + 0.25 * explicit_share, 3)
