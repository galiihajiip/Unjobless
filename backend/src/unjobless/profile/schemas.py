"""Master profile document and career preferences (validated JSON stored per version)."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def fid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    verified: bool = False
    evidence: str | None = Field(default=None, description="Verbatim excerpt from the source CV, if any.")
    source: Literal["cv", "user"] = "cv"


class Contact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None


class Education(Fact):
    institution: str
    degree: str | None = None
    field: str | None = None
    start: str | None = None
    end: str | None = None
    gpa: str | None = None
    current_semester: int | None = None
    details: list[str] = Field(default_factory=list)


class Bullet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    text: str
    verified: bool = False


class Experience(Fact):
    organization: str
    title: str
    kind: Literal["work", "internship", "organization", "volunteer", "freelance"] = "work"
    location: str | None = None
    start: str | None = None
    end: str | None = None
    bullets: list[Bullet] = Field(default_factory=list)


class Project(Fact):
    name: str
    role: str | None = None
    start: str | None = None
    end: str | None = None
    description: str | None = None
    bullets: list[Bullet] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    url: str | None = None


class Skill(Fact):
    name: str
    level: Literal["basic", "intermediate", "advanced", "expert"] | None = None


class Simple(Fact):
    name: str
    issuer: str | None = None
    date: str | None = None


class Language(Fact):
    language: str
    proficiency: str | None = None


class ProfileData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    headline: str | None = None
    summary: str | None = None
    contact: Contact = Field(default_factory=Contact)
    links: list[str] = Field(default_factory=list)
    educations: list[Education] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    certifications: list[Simple] = Field(default_factory=list)
    awards: list[Simple] = Field(default_factory=list)
    publications: list[Simple] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def facts(self) -> dict[str, dict[str, object]]:
        """Flat index of every fact id → {kind, text} (used for evidence linking in tailoring)."""
        out: dict[str, dict[str, object]] = {}
        for e in self.educations:
            out[e.id] = {
                "kind": "education",
                "text": " ".join(
                    x for x in [e.degree, e.field, e.institution, e.gpa and f"GPA {e.gpa}"] if x
                ),
                "verified": e.verified,
            }
        for x in self.experiences:
            out[x.id] = {
                "kind": "experience",
                "text": f"{x.title} at {x.organization} ({x.start or '?'}–{x.end or 'present'})",
                "verified": x.verified,
            }
            for b in x.bullets:
                out[b.id] = {"kind": "bullet", "text": b.text, "parent": x.id, "verified": b.verified}
        for p in self.projects:
            out[p.id] = {
                "kind": "project",
                "text": f"{p.name}: {p.description or ''} [{', '.join(p.technologies)}]",
                "verified": p.verified,
            }
            for b in p.bullets:
                out[b.id] = {"kind": "bullet", "text": b.text, "parent": p.id, "verified": b.verified}
        for s in self.skills:
            out[s.id] = {"kind": "skill", "text": s.name, "verified": s.verified}
        for group, kind in (
            (self.certifications, "certification"),
            (self.awards, "award"),
            (self.publications, "publication"),
        ):
            for c in group:
                out[c.id] = {
                    "kind": kind,
                    "text": " ".join(x for x in [c.name, c.issuer, c.date] if x),
                    "verified": c.verified,
                }
        for lang in self.languages:
            out[lang.id] = {
                "kind": "language",
                "text": f"{lang.language} {lang.proficiency or ''}".strip(),
                "verified": lang.verified,
            }
        return out


class CareerPreferencesData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_roles: list[str] = Field(default_factory=list, max_length=30)
    job_families: list[str] = Field(default_factory=list, max_length=30)
    industries: list[str] = Field(default_factory=list, max_length=30)
    skills_to_develop: list[str] = Field(default_factory=list, max_length=50)
    employment_types: list[
        Literal[
            "FULL_TIME",
            "PART_TIME",
            "CONTRACT",
            "INTERNSHIP",
            "FREELANCE",
            "TEMPORARY",
            "TRAINEE",
            "VOLUNTEER",
        ]
    ] = Field(default_factory=list)
    work_arrangements: list[Literal["ONSITE", "HYBRID", "REMOTE", "FLEXIBLE"]] = Field(default_factory=list)
    preferred_cities: list[str] = Field(default_factory=list, max_length=30)
    remote_ok: bool = True
    commute_area_note: str | None = Field(default=None, max_length=300)
    min_compensation: float | None = Field(default=None, ge=0)
    compensation_currency: str = "IDR"
    compensation_period: Literal["MONTH", "YEAR", "HOUR"] = "MONTH"
    education_level: (
        Literal["HIGH_SCHOOL", "DIPLOMA", "STUDENT", "BACHELOR", "MASTER", "DOCTORATE"] | None
    ) = None
    current_semester: int | None = Field(default=None, ge=1, le=16)
    career_goals: str | None = Field(default=None, max_length=2000)
    excluded_companies: list[str] = Field(default_factory=list, max_length=100)
    excluded_industries: list[str] = Field(default_factory=list, max_length=50)
    excluded_keywords: list[str] = Field(default_factory=list, max_length=50)
    language: Literal["id", "en"] = "id"
