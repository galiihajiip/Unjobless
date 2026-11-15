"""Opportunity Signal Engine (rules first, optional AI for ambiguous content).

Combines a configurable multilingual lexicon (Indonesian + English, incl. slang) with deterministic
rules and context features. Output is a schema-shaped `SignalResult`. Confidence never verifies
anything: verification needs evidence rules (see lifecycle) or the owner's confirmation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from unjobless.domain.enums import OpportunityClassification as C
from unjobless.domain.enums import SignalType as ST
from unjobless.domain.enums import VerificationStatus as V
from unjobless.intelligence import normalize as N

DEFAULT_LEXICON: dict[str, list[str]] = {
    "hiring": [
        r"we('| a)?re hiring",
        r"\bis hiring\b",
        r"\bnow hiring\b",
        r"\bhiring\b(?! freeze)",
        r"\bkami (sedang )?(membuka|mencari|merekrut)\b",
        r"\b(dibuka|membuka) (lowongan|kesempatan|pendaftaran)\b",
        r"\blowongan( kerja| magang)?\b",
        r"\bloker\b",
        r"\blowker\b",
        r"\bopen recruitment\b",
        r"\boprec\b",
        r"\bjoin our team\b",
        r"\bjoin us\b",
        r"\bopen position",
        r"\bjob opening",
        r"\bvacanc(y|ies)\b",
        r"\bapply now\b",
        r"\bdaftar sekarang\b",
        r"\bsegera daftar",
        r"\bwe are looking for\b",
        r"\blooking for (an? )?\w+",
        r"\bdicari\b",
        r"\bdibutuhkan\b",
        r"\bmembutuhkan\b",
        r"\bopportunity to join\b",
        r"\bopen (internship|magang)\b",
        r"\bbuka magang\b",
        r"\bwanted\b",
        r"\b(lagi |sedang )?butuh\b",
        r"\bnew grad(uate)? roles?\b",
        r"\binternship (opportunity|program|position)\b",
        r"\bmagang (di|batch)\b",
    ],
    "structure": [
        r"\b(requirements?|qualifications?|kualifikasi|persyaratan|syarat)\b",
        r"\b(job ?desc(ription)?|deskripsi pekerjaan|tanggung jawab|responsibilit(y|ies))\b",
        r"\b(benefits?|fasilitas|keuntungan)\b",
        r"\b(how to apply|cara (melamar|daftar|mendaftar)|tata cara)\b",
        r"\b(deadline|batas akhir|closing date|paling lambat)\b",
        r"\b(you will|you'll|what you('ll| will) do|anda akan|kamu akan)\b",
        r"\b(durasi|duration|lokasi|location|penempatan|placement)\s*:?",
        r"\b(usia|age)\s+\d",
    ],
    "apply_path": [
        r"https?://",
        r"\b[\w.+-]+@[\w-]+\.[\w.]+",
        r"\blink (di|in) bio\b",
        r"\bkirim (cv|lamaran)\b",
        r"\bsend (your )?(cv|resume)\b",
        r"\bapply (via|at|here|through)\b",
        r"\bdaftar (via|di|melalui)\b",
    ],
    "referral": [
        r"\breferral\b",
        r"\brefer(ral)?kan\b",
        r"\bbisa (aku |saya |gue |gw )?refer",
        r"\b(i|we) can refer\b",
        r"\bhappy to refer\b",
        r"\btitip cv\b",
        r"\bdrop (your )?cv\b",
        r"\bdm (aku|saya|me|gue)\b",
        r"\bjalur orang dalam\b",
        r"\bmau (di)?refer\b",
    ],
    "future": [
        r"\bnext month\b",
        r"\bbulan depan\b",
        r"\btahun depan\b",
        r"\bakan (segera )?(buka|dibuka|membuka)\b",
        r"\bcoming soon\b",
        r"\bsegera dibuka\b",
        r"\brencananya\b",
        r"\bmaybe\b",
        r"\bmungkin\b",
        r"\bkayaknya\b",
        r"\bkatanya\b",
        r"\brumou?rs?\b",
        r"\bplanning to (hire|open)\b",
        r"\bwill (be )?(hiring|open)",
        r"\bsoon\b",
        r"\bmight\b",
        r"\bheard (from|that)\b",
        r"\bnothing official\b",
        r"\bbelum (ada )?(resmi|official)\b",
        r"\bbakal\b",
        r"\bnanti (aku|saya) kabarin\b",
    ],
    "question": [
        r"\bada (yang )?(tahu|tau|info)\b",
        r"\banyone (know|knows|here)\b",
        r"\bis \w+ (still )?hiring\b",
        r"\b(lagi|masih) buka\b.*\?",
        r"\bapakah\b.*\?",
        r"\bgimana (cara|caranya)\b",
        r"\bdoes anyone\b",
        r"\bhas anyone\b",
        r"\bany(one)? (info|leads?)\b",
        r"\bpunya info\b",
        r"\bhow long did\b",
    ],
    "review": [
        r"\bpengalaman (magang|kerja|interview|wawancara)\b",
        r"\bmy (internship|interview|work) experience\b",
        r"\b(i|we)? ?(worked|interned) at\b",
        r"\bworkload\b",
        r"\bgood pay\b",
        r"\bmanagement (changed|is|was)\b",
        r"\bcerita\b.*\bpengalaman\b",
        r"\bselama (magang|kerja) di\b",
        r"\btoxic\b",
        r"\bgaji (telat|kecil|ga dibayar)\b",
        r"\breview\b",
        r"\binterview (was|process|experience)\b",
        r"\bproses (rekrutmen|seleksi|interview)\b.*\b(lama|ribet|ghosting|ghosted)\b",
        r"\bghost(ed|ing)\b",
        r"\bunderpaid\b",
        r"\boverworked\b",
        r"\b(great|terrible|awful|amazing|bad|good) (place|company|culture|mentor)",
        r"\bculture (is|was)\b",
        r"\bkultur(nya)?\b",
    ],
    "campaign": [
        r"\bbatch \d+\b",
        r"\bcampus (hiring|recruitment)\b",
        r"\bgraduate program\b",
        r"\bmanagement trainee\b",
        r"\b(odp|mt) program\b",
        r"\brekrutmen bersama\b",
        r"\bjob fair\b",
        r"\bbursa kerja\b",
        r"\bprogram (magang|internship)\b",
        r"\bmsib\b",
        r"\bkampus merdeka\b",
    ],
    "program": [
        r"\bbootcamp\b",
        r"\bfellowship\b",
        r"\bmentorship program\b",
        r"\btraining program\b",
        r"\bpelatihan\b",
        r"\bwebinar\b",
        r"\bworkshop\b",
        r"\bcareer (fair|day|class|event)\b",
    ],
    "scholarship": [r"\bbeasiswa\b", r"\bscholarship\b", r"\blomba\b", r"\bcompetition\b", r"\bhackathon\b"],
    "trend": [
        r"\bhiring freeze\b",
        r"\blayoffs?\b",
        r"\bphk\b",
        r"\bjob market\b",
        r"\bpasar kerja\b",
        r"\btren\b",
        r"\btrend\b",
        r"\bunemployment\b",
        r"\bpengangguran\b",
    ],
    "career": [
        r"\bintern(ship)?s?\b",
        r"\bmagang\b",
        r"\bjobs?\b",
        r"\bkerja\b",
        r"\bkarir\b",
        r"\bcareers?\b",
        r"\bhiring\b",
        r"\bloker\b",
        r"\blowongan\b",
        r"\brecruit",
        r"\brekrut",
        r"\bcv\b",
        r"\bresume\b",
        r"\binterview\b",
        r"\bposisi\b",
        r"\bposition\b",
        r"\bvacanc",
        r"\btrainee\b",
        r"\bfreelance\b",
        r"\broles?\b",
        r"\bnew grad",
        r"\blamaran\b",
        r"\bkantor\b",
        r"\bfresh ?grad",
        r"\bgraduates?\b",
    ],
    "irrelevant": [
        r"\bthe internship \(2013\)",
        r"\bmovie\b",
        r"\bfilm\b",
        r"\bnetflix\b",
        r"\bnonton\b",
        r"\bdrama\b",
        r"\bepisode\b",
    ],
}


@dataclass
class Entity:
    kind: str
    value: str
    origin: str
    excerpt: str


@dataclass
class SignalResult:
    primary: C
    secondary: list[C]
    signal_type: ST
    confidence: float
    reason: str
    ambiguity_flags: list[str]
    entities: list[Entity]
    evidence_excerpts: list[str]
    recommendation: V
    features: dict[str, Any] = field(default_factory=dict)
    method: str = "rules"

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary": self.primary.value,
            "secondary": [s.value for s in self.secondary],
            "signal_type": self.signal_type.value,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
            "ambiguity_flags": self.ambiguity_flags,
            "entities": [e.__dict__ for e in self.entities],
            "evidence_excerpts": self.evidence_excerpts,
            "recommendation": self.recommendation.value,
            "method": self.method,
        }


class Lexicon:
    def __init__(self, overrides: dict[str, list[str]] | None = None):
        merged = {k: list(v) for k, v in DEFAULT_LEXICON.items()}
        for k, v in (overrides or {}).items():
            merged.setdefault(k, []).extend(v)
        self.patterns = {k: [re.compile(p, re.I) for p in v] for k, v in merged.items()}

    def hits(self, group: str, text: str) -> list[re.Match[str]]:
        out = []
        for p in self.patterns.get(group, []):
            m = p.search(text)
            if m:
                out.append(m)
        return out


_DEFAULT = Lexicon()


def _excerpt(text: str, m: re.Match[str], pad: int = 60) -> str:
    s, e = max(0, m.start() - pad), min(len(text), m.end() + pad)
    return text[s:e].strip()


def classify(
    text: str,
    *,
    title: str | None = None,
    structured: bool = False,
    today: date | None = None,
    lexicon: Lexicon | None = None,
) -> SignalResult:
    lx = lexicon or _DEFAULT
    today = today or date.today()
    full = f"{title or ''}\n{text}".strip()
    h = {g: lx.hits(g, full) for g in DEFAULT_LEXICON}
    n = {g: len(v) for g, v in h.items()}
    has_q = "?" in full
    flags: list[str] = []
    entities: list[Entity] = []
    evidence: list[str] = []

    urls = N.URL_RE.findall(full)
    emails = N.EMAIL_RE.findall(full)
    for u in urls[:3]:
        entities.append(Entity("application_url", u, "EXPLICIT", u))
    for em in emails[:2]:
        entities.append(Entity("contact", em, "EXPLICIT", em))
    for raw, _s, _e in N.find_locations(full, 3):
        entities.append(Entity("location", raw, "EXPLICIT", raw))
    deadline = N.find_cued_date(full, N.DEADLINE_CUE)
    if deadline:
        entities.append(Entity("date", deadline.value.isoformat(), "EXPLICIT", deadline.excerpt))
    role = _role_guess(title, full)
    if role:
        entities.append(Entity("role", role[0], role[1], role[2]))
    for g in ("hiring", "referral", "future", "review", "question", "campaign"):
        for m in h[g][:2]:
            evidence.append(_excerpt(full, m))

    secondary: list[C] = []
    expired = bool(deadline and deadline.value < today)
    if expired:
        flags.append("deadline_passed")
    if sum(v for g, v in n.items() if g not in ("irrelevant", "apply_path", "structure")) == 0:
        return SignalResult(
            C.IRRELEVANT,
            [],
            ST.NOT_AN_OPPORTUNITY,
            0.85,
            "No career-related terms found.",
            [],
            [],
            [],
            V.REJECTED_AS_IRRELEVANT,
            n,
        )
    if n["irrelevant"] and n["hiring"] == 0 and n["structure"] == 0:
        return SignalResult(
            C.IRRELEVANT,
            [],
            ST.NOT_AN_OPPORTUNITY,
            0.75,
            "Career words used in an unrelated context (e.g. entertainment).",
            ["unrelated_usage"],
            [],
            [_excerpt(full, h["irrelevant"][0])],
            V.REJECTED_AS_IRRELEVANT,
            n,
        )

    explicit = n["hiring"] > 0
    structure = n["structure"]
    apply_path = n["apply_path"] > 0
    is_question = has_q and n["question"] > 0
    future = n["future"] > 0

    def result(primary: C, st: ST, conf: float, reason: str, rec: V) -> SignalResult:
        if expired and rec in (V.NEW_UNREVIEWED, V.NEEDS_REVIEW, V.POTENTIAL_LEAD, V.LIKELY_OPEN):
            rec = V.EXPIRED
        return SignalResult(
            primary,
            [s for s in secondary if s != primary],
            st,
            max(0.05, min(conf, 0.97)),
            reason,
            flags,
            entities,
            evidence[:5],
            rec,
            n,
        )

    if n["review"] and not (explicit and structure >= 2):
        if n["hiring"]:
            secondary.append(C.EMPLOYER_DISCUSSION)
        return result(
            C.EMPLOYER_REVIEW,
            ST.NOT_AN_OPPORTUNITY,
            0.7 + 0.05 * min(n["review"], 3),
            "Describes personal experience with an employer or process; no confirmed opening.",
            V.REJECTED_AS_IRRELEVANT,
        )
    if is_question and not (structure >= 2 and apply_path):
        flags.append("question_not_announcement")
        return result(
            C.EMPLOYER_DISCUSSION,
            ST.NOT_AN_OPPORTUNITY,
            0.75,
            "Asks whether an opportunity exists; this is not an announcement.",
            V.REJECTED_AS_IRRELEVANT,
        )
    if n["referral"]:
        secondary.append(C.INFORMAL_OPPORTUNITY_LEAD)
        if not role:
            flags.append("role_unspecified")
        return result(
            C.REFERRAL_SIGNAL,
            ST.REFERRAL_AVAILABLE,
            0.7 + (0.1 if role else 0),
            "Someone offers or requests a referral.",
            V.POTENTIAL_LEAD,
        )
    if n["campaign"] and future and not explicit_open_call(h):
        flags.append("details_pending")
        return result(
            C.RECRUITMENT_CAMPAIGN,
            ST.RECRUITMENT_BATCH,
            0.55,
            "Recruitment programme announced; details or dates still pending.",
            V.POTENTIAL_LEAD,
        )
    if future and not (structure >= 2 and apply_path):
        flags.append("unconfirmed_future_opening")
        return result(
            C.INFORMAL_OPPORTUNITY_LEAD,
            ST.FUTURE_HIRING_INTENT,
            0.6,
            "Mentions possible or future hiring without confirmation.",
            V.POTENTIAL_LEAD,
        )
    if n["scholarship"] and not explicit:
        return result(
            C.SCHOLARSHIP_OR_COMPETITION,
            ST.CAREER_EVENT,
            0.7,
            "Scholarship or competition announcement.",
            V.POTENTIAL_LEAD,
        )
    if n["program"] and not (explicit and structure >= 2):
        return result(
            C.CAREER_PROGRAM,
            ST.CAREER_EVENT,
            0.65,
            "Career program, training or event — not a job opening.",
            V.POTENTIAL_LEAD,
        )
    if n["trend"] and not (structure >= 1 and apply_path):
        return result(
            C.CAREER_TREND,
            ST.NOT_AN_OPPORTUNITY,
            0.65,
            "Discusses the job market or hiring trends.",
            V.REJECTED_AS_IRRELEVANT,
        )

    posting_shape = (
        apply_path
        and role is not None
        and (structure >= 2 or (structure >= 1 and role[1] == "EXPLICIT" and bool(title)))
    )
    if explicit or structured or posting_shape:
        if n["campaign"]:
            secondary.append(C.RECRUITMENT_CAMPAIGN)
        complete = (
            (role is not None or structured) and (apply_path or structured) and (structure >= 1 or structured)
        )
        if complete:
            conf = 0.6 + 0.08 * min(structure, 3) + (0.1 if apply_path else 0) + (0.1 if structured else 0)
            primary = C.RECRUITMENT_CAMPAIGN if n["campaign"] and not role else C.DIRECT_VACANCY
            rec = V.NEEDS_REVIEW if conf < 0.75 else V.NEW_UNREVIEWED
            return result(
                primary,
                ST.RECRUITMENT_BATCH if primary == C.RECRUITMENT_CAMPAIGN else ST.DIRECT_HIRING,
                conf,
                "Explicit opening with a role, requirements or details, and an application path.",
                rec,
            )
        missing = [
            x
            for x, ok in (
                ("role", role is not None),
                ("application_path", apply_path),
                ("details", structure >= 1),
            )
            if not ok
        ]
        flags.extend(f"missing_{m}" for m in missing)
        if n["campaign"]:
            return result(
                C.RECRUITMENT_CAMPAIGN,
                ST.RECRUITMENT_BATCH,
                0.55,
                f"Recruitment announcement missing: {', '.join(missing)}.",
                V.POTENTIAL_LEAD,
            )
        return result(
            C.INFORMAL_OPPORTUNITY_LEAD,
            ST.POSSIBLE_HIRING,
            0.5,
            f"Hiring is mentioned but key details are missing: {', '.join(missing)}.",
            V.POTENTIAL_LEAD,
        )
    if n["campaign"]:
        return result(
            C.RECRUITMENT_CAMPAIGN,
            ST.RECRUITMENT_BATCH,
            0.5,
            "Recruitment programme mentioned without an explicit open call.",
            V.POTENTIAL_LEAD,
        )
    flags.append("weak_signal")
    return result(
        C.CAREER_TREND,
        ST.NOT_AN_OPPORTUNITY,
        0.4,
        "Career-related content without an opportunity.",
        V.REJECTED_AS_IRRELEVANT,
    )


def explicit_open_call(h: dict[str, list[re.Match[str]]]) -> bool:
    return any(
        re.search(r"(sudah dibuka|now open|is open|apply now|daftar sekarang)", m.group(0), re.I)
        for m in h.get("hiring", [])
    )


ROLE_RE = re.compile(
    r"\b((?:senior |junior |sr\.? |jr\.? )?(?:[A-Z][\w/&+.-]*\s){0,4}"
    r"(?:Intern|Internship|Engineer|Developer|Analyst|Designer|Manager|Specialist|Officer|Staff|Assistant|Associate|Consultant|Scientist|Writer|Marketing|Admin|Trainee|Programmer|Accountant|Executive|Coordinator|Lead|Barista|Cashier|Kasir|Driver|Teller|Akuntansi|Analis))\b"
)
ID_ROLE_RE = re.compile(
    r"\b(?:posisi|lowongan|magang|loker|dicari|dibutuhkan|hiring)\s*:?\s*([A-Za-z][\w /&+.-]{3,60}?)(?=[\n,.;!()]|\s-\s|$)",
    re.I,
)


def _role_guess(title: str | None, text: str) -> tuple[str, str, str] | None:
    if title and len(title) < 140:
        m = ROLE_RE.search(title)
        if m:
            return m.group(1).strip(), "EXPLICIT", title
    m2 = ID_ROLE_RE.search(text)
    if m2 and len(m2.group(1).split()) <= 8:
        return m2.group(1).strip(), "EXPLICIT", m2.group(0).strip()
    m = ROLE_RE.search(text[:2000])
    if m:
        return m.group(1).strip(), "INFERRED", _excerpt(text, m, 30)
    return None


def classify_with_ai(
    db: Any, text: str, *, title: str | None = None, structured: bool = False, input_ref: str | None = None
) -> SignalResult:
    """Rules first; AI only when ambiguous and configured. AI can relabel but never verifies."""
    from unjobless.ai.gateway import (
        AIBudgetExceeded,
        AINotConfigured,
        AITaskFailed,
        AIUnavailable,
        ai_available,
        run_task,
    )

    base = classify(text, title=title, structured=structured, lexicon=load_lexicon(db))
    if base.confidence >= 0.7 or structured or not ai_available(db, "signal_classification"):
        return base
    try:
        res = run_task(
            db, "signal_classification", {"title": title, "text_untrusted": text[:12000]}, input_ref=input_ref
        )
    except (AINotConfigured, AIUnavailable, AIBudgetExceeded, AITaskFailed):
        return base
    o: Any = res.output
    primary = C(o.primary)
    rec = {
        C.DIRECT_VACANCY: V.NEEDS_REVIEW,  # AI can never produce a verified/likely-open status
        C.IRRELEVANT: V.REJECTED_AS_IRRELEVANT,
        C.EMPLOYER_DISCUSSION: V.REJECTED_AS_IRRELEVANT,
        C.EMPLOYER_REVIEW: V.REJECTED_AS_IRRELEVANT,
        C.CAREER_TREND: V.REJECTED_AS_IRRELEVANT,
    }.get(primary, V.POTENTIAL_LEAD)
    if "deadline_passed" in base.ambiguity_flags and rec in (V.NEEDS_REVIEW, V.POTENTIAL_LEAD):
        rec = V.EXPIRED
    ents = [
        Entity(e.kind, e.value, e.origin, e.excerpt) for e in o.entities if e.excerpt and e.excerpt in text
    ] or base.entities
    return SignalResult(
        primary=primary,
        secondary=[C(s) for s in o.secondary if s != o.primary],
        signal_type=ST(o.signal_type),
        confidence=min(float(o.confidence), 0.95),
        reason=o.reason,
        ambiguity_flags=sorted(set(o.ambiguity_flags) | set(base.ambiguity_flags)),
        entities=ents,
        evidence_excerpts=[x for x in o.evidence_excerpts if x in text][:5] or base.evidence_excerpts,
        recommendation=rec,
        features=base.features,
        method=f"ai:{res.run.model}",
    )


def load_lexicon(db: Any) -> Lexicon:
    from unjobless.db.models import AppSettings

    row = db.get(AppSettings, "signal_lexicon_extra")
    return Lexicon(row.value) if row and isinstance(row.value, dict) else _DEFAULT
