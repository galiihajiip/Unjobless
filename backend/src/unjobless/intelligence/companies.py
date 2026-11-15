"""Company entity resolution: legal/trading names, aliases, website domain as supporting evidence."""

from __future__ import annotations

import re

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from unjobless.core.audit import audit
from unjobless.core.errors import NotFound, ValidationFailed
from unjobless.db.models import (
    Company,
    CompanyAlias,
    JobVacancy,
    OpportunitySignal,
    SentimentAnalysis,
    TopicObservation,
)
from unjobless.fetch.urls import host_of
from unjobless.intelligence.text import normalize_key

LEGAL_FORMS = r"\b(pt|cv|tbk|persero|perum|ud|pd|inc|incorporated|ltd|limited|llc|corp|corporation|co|company|gmbh|bv|plc|pte|sdn bhd|group)\b"
AUTO_MATCH = 95
CANDIDATE_MATCH = 85


def normalize_company(name: str) -> str:
    k = normalize_key(name)
    k = re.sub(LEGAL_FORMS, " ", k)
    return re.sub(r"\s+", " ", k).strip(" .")


def resolve_company(
    db: Session, name: str | None, *, website: str | None = None, create: bool = True
) -> Company | None:
    """Exact normalized name/alias → domain → high fuzzy match. Similar-but-different names are not merged."""
    if not name or len(name.strip()) < 2:
        return None
    norm = normalize_company(name)
    if not norm:
        return None
    domain = host_of(website) if website and "://" in website else (website or None)
    domain = domain[4:] if domain and domain.startswith("www.") else domain
    c = (
        db.execute(select(Company).where(Company.normalized_name == norm, Company.merged_into_id.is_(None)))
        .scalars()
        .first()
    )
    if c is None:
        alias = (
            db.execute(select(CompanyAlias).where(CompanyAlias.normalized_alias == norm)).scalars().first()
        )
        c = db.get(Company, alias.company_id) if alias else None
    if c is None and domain:
        c = (
            db.execute(
                select(Company).where(Company.website_domain == domain, Company.merged_into_id.is_(None))
            )
            .scalars()
            .first()
        )
    if c is None:
        # Fuzzy: only when very close AND same first token (avoid "Bank Mandiri" vs "Bank Mandiri Taspen" style merges)
        cands = (
            db.execute(
                select(Company)
                .where(Company.normalized_name.op("%")(norm), Company.merged_into_id.is_(None))
                .limit(10)
            )
            .scalars()
            .all()
        )
        for cand in cands:
            if (
                fuzz.ratio(cand.normalized_name, norm) >= AUTO_MATCH
                and cand.normalized_name.split()[0] == norm.split()[0]
                and abs(len(cand.normalized_name) - len(norm)) <= 2
            ):
                c = cand
                break
    if c is None:
        if not create:
            return None
        c = Company(name=name.strip()[:300], normalized_name=norm, website_domain=domain)
        db.add(c)
        db.flush()
    else:
        if domain and not c.website_domain:
            c.website_domain = domain
    if normalize_key(name) != normalize_key(c.name):
        add_alias(db, c, name, source="observed")
    while c.merged_into_id:
        nxt = db.get(Company, c.merged_into_id)
        if nxt is None:
            break
        c = nxt
    return c


def add_alias(db: Session, company: Company, alias: str, source: str = "user") -> None:
    na = normalize_company(alias)
    if not na:
        return
    exists = db.execute(
        select(CompanyAlias.id).where(
            CompanyAlias.company_id == company.id, CompanyAlias.normalized_alias == na
        )
    ).first()
    if not exists:
        db.add(
            CompanyAlias(company_id=company.id, alias=alias.strip()[:300], normalized_alias=na, source=source)
        )
        db.flush()


def merge_companies(db: Session, keep_id: int, merge_id: int) -> Company:
    """Manual correction: fold `merge_id` into `keep_id`, re-pointing references; reversible via aliases + audit."""
    if keep_id == merge_id:
        raise ValidationFailed("Choose two different companies.")
    keep, gone = db.get(Company, keep_id), db.get(Company, merge_id)
    if keep is None or gone is None:
        raise NotFound("Company not found.")
    for model in (JobVacancy, OpportunitySignal, SentimentAnalysis, TopicObservation):
        db.query(model).filter(model.company_id == gone.id).update({model.company_id: keep.id})
    db.query(CompanyAlias).filter(CompanyAlias.company_id == gone.id).update(
        {CompanyAlias.company_id: keep.id}
    )
    add_alias(db, keep, gone.name, source="merge")
    gone.merged_into_id = keep.id
    keep.manually_verified = True
    audit(
        db,
        "company.merged",
        target_type="company",
        target_id=keep.id,
        details={"merged": gone.id, "name": gone.name},
    )
    return keep
