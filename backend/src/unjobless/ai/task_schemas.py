"""Versioned output schemas for every AI task. Bump SCHEMA_VERSION on any breaking change.

All schemas are converted to strict JSON Schema (every property required, nullable via null,
`additionalProperties: false`) by `strict_json_schema`.
"""

from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Origin = Literal["EXPLICIT", "INFERRED"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(Strict):
    field: str = Field(description="Name of the extracted field this evidence supports.")
    excerpt: str = Field(description="Verbatim excerpt copied from the source text. Never paraphrase.")
    origin: Origin
    confidence: float = Field(ge=0, le=1)


# ---------------------------------------------------------------- job extraction (v1)


class JobExtraction(Strict):
    is_job_posting: bool = Field(
        description="True only if the text describes a concrete, actionable opening."
    )
    language: str | None = Field(description="ISO 639-1 code of the source text, e.g. 'id' or 'en'.")
    title: str | None
    alternative_title: str | None
    company: str | None
    department: str | None
    locations: list[str]
    work_arrangement: Literal["ONSITE", "HYBRID", "REMOTE", "FLEXIBLE", "UNKNOWN"]
    employment_type: Literal[
        "FULL_TIME",
        "PART_TIME",
        "CONTRACT",
        "INTERNSHIP",
        "FREELANCE",
        "TEMPORARY",
        "TRAINEE",
        "VOLUNTEER",
        "UNKNOWN",
    ]
    seniority: Literal[
        "INTERN", "ENTRY", "JUNIOR", "MID", "SENIOR", "LEAD", "MANAGER", "EXECUTIVE", "UNKNOWN"
    ]
    job_family: str | None
    industry: str | None
    application_url: str | None = Field(description="Only a URL that literally appears in the text.")
    application_email: str | None
    application_deadline: str | None = Field(
        description="YYYY-MM-DD, only if a deadline is explicitly stated."
    )
    application_open_date: str | None
    start_date: str | None
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None = Field(description="ISO 4217, e.g. IDR, USD.")
    pay_period: Literal["HOUR", "DAY", "WEEK", "MONTH", "YEAR", "PROJECT", "UNKNOWN"]
    is_paid: bool | None = Field(description="null unless paid/unpaid is explicit.")
    internship_duration_months: float | None
    contract_duration_months: float | None
    openings_count: int | None
    recruitment_batch: str | None
    education_level: str | None
    majors: list[str]
    min_semester: int | None
    min_gpa: float | None
    experience_years_min: float | None
    required_skills: list[str]
    preferred_skills: list[str]
    tools: list[str]
    language_requirements: list[str]
    certifications: list[str]
    portfolio_required: bool | None
    legal_requirements: list[str]
    soft_skills: list[str]
    application_documents: list[str]
    selection_stages: list[str]
    responsibilities: list[str]
    deliverables: list[str]
    benefits: list[str]
    working_hours: str | None
    remote_eligible_countries: list[str]
    conversion_info: str | None
    reporting_line: str | None
    evidence: list[Evidence]
    warnings: list[str] = Field(description="Ambiguities, conflicting statements, or parsing doubts.")


# ---------------------------------------------------------------- signal classification (v1)

Classification = Literal[
    "DIRECT_VACANCY",
    "INFORMAL_OPPORTUNITY_LEAD",
    "REFERRAL_SIGNAL",
    "RECRUITMENT_CAMPAIGN",
    "CAREER_PROGRAM",
    "SCHOLARSHIP_OR_COMPETITION",
    "EMPLOYER_DISCUSSION",
    "EMPLOYER_REVIEW",
    "CAREER_TREND",
    "IRRELEVANT",
]
SignalTypeL = Literal[
    "DIRECT_HIRING",
    "POSSIBLE_HIRING",
    "REFERRAL_AVAILABLE",
    "FUTURE_HIRING_INTENT",
    "APPLICATION_INVITATION",
    "RECRUITMENT_BATCH",
    "CAREER_EVENT",
    "NOT_AN_OPPORTUNITY",
]


class SignalEntityOut(Strict):
    kind: Literal["company", "role", "location", "date", "application_url", "contact", "program"]
    value: str
    origin: Origin
    excerpt: str


class SignalClassification(Strict):
    primary: Classification
    secondary: list[Classification]
    signal_type: SignalTypeL
    confidence: float = Field(ge=0, le=1)
    reason: str
    ambiguity_flags: list[str]
    entities: list[SignalEntityOut]
    evidence_excerpts: list[str]


# ---------------------------------------------------------------- sentiment & topics (v1)


class SentimentItem(Strict):
    target: Literal[
        "COMPANY",
        "RECRUITMENT_PROCESS",
        "INTERVIEW",
        "INTERNSHIP_EXPERIENCE",
        "MANAGEMENT",
        "WORK_CULTURE",
        "COMPENSATION",
        "WORKLOAD",
        "ROLE",
        "JOB_SEARCH",
    ]
    polarity: Literal["POSITIVE", "NEUTRAL", "NEGATIVE", "MIXED", "UNCERTAIN"]
    company: str | None
    confidence: float = Field(ge=0, le=1)
    sarcasm_uncertain: bool
    excerpt: str


class TopicItem(Strict):
    topic: str
    confidence: float = Field(ge=0, le=1)
    excerpt: str


class SentimentTopics(Strict):
    sentiments: list[SentimentItem]
    topics: list[TopicItem]


# ---------------------------------------------------------------- CV structuring (v1)


class FactRef(Strict):
    excerpt: str = Field(description="Verbatim excerpt from the CV text supporting this entry.")


class CVEducation(Strict):
    institution: str
    degree: str | None
    field: str | None
    start: str | None
    end: str | None
    gpa: str | None
    details: list[str]
    evidence: FactRef


class CVExperience(Strict):
    organization: str
    title: str
    kind: Literal["work", "internship", "organization", "volunteer", "freelance"]
    location: str | None
    start: str | None
    end: str | None
    bullets: list[str]
    evidence: FactRef


class CVProject(Strict):
    name: str
    role: str | None
    start: str | None
    end: str | None
    description: str | None
    bullets: list[str]
    technologies: list[str]
    url: str | None
    evidence: FactRef


class CVSimple(Strict):
    name: str
    issuer: str | None
    date: str | None
    evidence: FactRef


class CVLanguage(Strict):
    language: str
    proficiency: str | None


class CVStructure(Strict):
    full_name: str | None
    headline: str | None
    summary: str | None
    email: str | None
    phone: str | None
    location: str | None
    links: list[str]
    educations: list[CVEducation]
    experiences: list[CVExperience]
    projects: list[CVProject]
    skills: list[str]
    certifications: list[CVSimple]
    awards: list[CVSimple]
    publications: list[CVSimple]
    languages: list[CVLanguage]
    warnings: list[str]


# ---------------------------------------------------------------- explanations (v1)


class MatchExplanation(Strict):
    summary: str
    strengths: list[str]
    gaps: list[str]
    unknowns: list[str]


class ComparisonExplanation(Strict):
    summary: str
    tradeoffs: list[str]
    recommendation: str
    uncertainty: str


# ---------------------------------------------------------------- tailoring (v1)


class TailoredBullet(Strict):
    source_fact_id: str = Field(description="id of the profile fact this bullet is rewritten from.")
    original: str
    rewritten: str
    changed_facts: bool = Field(
        description="True if anything beyond wording changed. Must normally be false."
    )


class TailoredSection(Strict):
    source_entry_id: str
    bullets: list[TailoredBullet]


class CVTailoring(Strict):
    headline: str
    headline_fact_ids: list[str]
    summary: str
    summary_fact_ids: list[str]
    skill_order: list[str]
    entry_order: list[str]
    sections: list[TailoredSection]
    missing_requirements: list[str]
    needs_user_confirmation: list[str]


class CoverLetterClaim(Strict):
    sentence: str
    fact_ids: list[str]


class CoverLetterDraft(Strict):
    greeting: str
    paragraphs: list[str]
    closing: str
    claims: list[CoverLetterClaim]
    needs_user_confirmation: list[str]


# ---------------------------------------------------------------- strict schema conversion


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema → strict structured-output schema (inline $defs, all required, no extras)."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
            out = {k: resolve(v) for k, v in node.items() if k not in ("title", "default")}
            # numeric bounds are not universally supported in structured outputs; enforced by pydantic instead
            for k in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
                out.pop(k, None)
            if out.get("type") == "object" and "properties" in out:
                out["required"] = list(out["properties"].keys())
                out["additionalProperties"] = False
            return out
        if isinstance(node, list):
            return [resolve(x) for x in node]
        return node

    return resolve(schema)
