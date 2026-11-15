"""Import review & human verification (owner decisions on extracted items)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from unjobless.ai.task_schemas import JobExtraction
from unjobless.core.audit import audit
from unjobless.core.errors import NotFound, ValidationFailed
from unjobless.db.models import ImportItem, JobVacancy, RawSourceDocument, RawSourceVersion, Source
from unjobless.domain.enums import Actor, FieldOrigin, ImportItemStatus, OpportunityClassification
from unjobless.domain.enums import VerificationStatus as V
from unjobless.domain.state_machines import IMPORT_ITEM
from unjobless.ingestion.imports import refresh_batch_status
from unjobless.intelligence import dedup, lifecycle
from unjobless.intelligence.extraction import empty_extraction
from unjobless.intelligence.pipeline import create_signal, version_text
from unjobless.intelligence.signals import classify
from unjobless.intelligence.vacancies import create_vacancy, link_source

EDITABLE = set(JobExtraction.model_fields) - {"evidence", "warnings", "is_job_posting"}


def _ctx(db: Session, item: ImportItem) -> tuple[RawSourceVersion, RawSourceDocument, Source]:
    if not item.raw_version_id:
        raise ValidationFailed("This item has no stored content yet.")
    version = db.get(RawSourceVersion, item.raw_version_id)
    doc = db.get(RawSourceDocument, version.document_id) if version else None
    src = db.get(Source, doc.source_id) if doc else None
    if version is None or doc is None or src is None:
        raise NotFound("Stored content not found.")
    return version, doc, src


def _require_review(item: ImportItem) -> None:
    if item.status not in (
        ImportItemStatus.NEEDS_REVIEW,
        ImportItemStatus.DUPLICATE,
        ImportItemStatus.REJECTED,
    ):
        raise ValidationFailed(f"Item is {item.status.value.lower()}; it must be ready for review first.")


def corrected_extraction(item: ImportItem, corrections: dict[str, Any] | None) -> JobExtraction:
    base = dict((item.extraction or {}).get("extraction") or empty_extraction())
    corrections = {k: v for k, v in (corrections or {}).items() if k in EDITABLE}
    evidence = list(base.get("evidence", []))
    for k, v in corrections.items():
        base[k] = v
        evidence = [e for e in evidence if e.get("field") != k]
        if v not in (None, [], "UNKNOWN", ""):
            evidence.append(
                {
                    "field": k,
                    "excerpt": f"[owner correction] {str(v)[:300]}",
                    "origin": "INFERRED",
                    "confidence": 1.0,
                }
            )
    base["evidence"] = evidence
    base["is_job_posting"] = True
    return JobExtraction.model_validate(base)


def save_corrections(db: Session, item: ImportItem, corrections: dict[str, Any]) -> ImportItem:
    _require_review(item)
    x = corrected_extraction(item, corrections)
    payload = dict(item.extraction or {})
    payload["extraction"] = x.model_dump(mode="json")
    item.extraction = payload
    item.user_corrections = {
        **(item.user_corrections or {}),
        **{k: v for k, v in corrections.items() if k in EDITABLE},
    }
    audit(
        db,
        "import.corrected",
        target_type="import_item",
        target_id=item.id,
        details={"fields": sorted(corrections)},
    )
    return item


def confirm_as_vacancy(
    db: Session, item: ImportItem, corrections: dict[str, Any] | None = None
) -> JobVacancy:
    """Owner confirms this is a real, open vacancy. The only path from an import to VERIFIED_OPEN."""
    _require_review(item)
    version, doc, src = _ctx(db, item)
    x = corrected_extraction(item, corrections)
    if not x.title:
        raise ValidationFailed("A vacancy needs a title. Add one before confirming.")
    text = version_text(version)
    v = create_vacancy(
        db,
        x=x,
        source=src,
        document=doc,
        version=version,
        source_text=text,
        status=V.VERIFIED_OPEN,
        classification=OpportunityClassification.DIRECT_VACANCY,
        actor=Actor.USER,
        reason="Confirmed by the owner during import review.",
    )
    _mark_user_fields(db, v, corrections)
    lifecycle.apply_deadline_rule(db, v)
    v = dedup.process_new_vacancy(db, v)
    item.result_vacancy_id = v.id
    if corrections:
        item.user_corrections = {**(item.user_corrections or {}), **corrections}
    if item.status == ImportItemStatus.NEEDS_REVIEW:
        IMPORT_ITEM.check(item.status, ImportItemStatus.SAVED)
    item.status = ImportItemStatus.SAVED
    audit(
        db,
        "import.confirmed_vacancy",
        target_type="import_item",
        target_id=item.id,
        details={"vacancy_id": v.id},
    )
    refresh_batch_status(db, item.batch_id)
    return v


def _mark_user_fields(db: Session, v: JobVacancy, corrections: dict[str, Any] | None) -> None:
    if not corrections:
        return
    meta = dict(v.field_meta or {})
    for k in corrections:
        if k in EDITABLE:
            meta[k] = {"origin": FieldOrigin.USER_PROVIDED.value, "confidence": 1.0}
    v.field_meta = meta


def confirm_as_lead(db: Session, item: ImportItem) -> Any:
    """Save as an unverified lead (never promoted to a vacancy implicitly)."""
    _require_review(item)
    version, _doc, _src = _ctx(db, item)
    text = version_text(version)
    sig = classify(text, title=version.title)
    if sig.primary in (
        OpportunityClassification.IRRELEVANT,
        OpportunityClassification.EMPLOYER_DISCUSSION,
        OpportunityClassification.EMPLOYER_REVIEW,
        OpportunityClassification.CAREER_TREND,
        OpportunityClassification.DIRECT_VACANCY,
    ):
        sig.primary = OpportunityClassification.INFORMAL_OPPORTUNITY_LEAD
    s = create_signal(db, version, sig, source_text=text, status=V.POTENTIAL_LEAD)
    item.result_signal_id = s.id
    item.status = ImportItemStatus.SAVED
    audit(
        db, "import.confirmed_lead", target_type="import_item", target_id=item.id, details={"signal_id": s.id}
    )
    refresh_batch_status(db, item.batch_id)
    return s


def reject(db: Session, item: ImportItem, reason: str | None = None) -> ImportItem:
    _require_review(item)
    item.status = ImportItemStatus.REJECTED
    item.failure_reason = reason or "Rejected by the owner as irrelevant."
    audit(db, "import.rejected", target_type="import_item", target_id=item.id)
    refresh_batch_status(db, item.batch_id)
    return item


def merge_into(db: Session, item: ImportItem, vacancy_id: int) -> JobVacancy:
    _require_review(item)
    version, doc, src = _ctx(db, item)
    v = db.get(JobVacancy, vacancy_id)
    if v is None:
        raise NotFound("Vacancy not found.")
    link_source(db, v, src, doc, version)
    # Fill gaps only; never overwrite existing canonical values with the import's extraction.
    from decimal import Decimal

    from unjobless.intelligence.normalize import parse_iso_date

    x = corrected_extraction(item, None)
    if v.application_deadline is None and x.application_deadline:
        v.application_deadline = parse_iso_date(x.application_deadline)
    if v.salary_min is None and x.salary_min is not None:
        v.salary_min = Decimal(str(x.salary_min))
        v.salary_max = Decimal(str(x.salary_max if x.salary_max is not None else x.salary_min))
        v.salary_currency = v.salary_currency or x.salary_currency
    if v.application_url is None and x.application_url:
        v.application_url = x.application_url
    v.freshness = lifecycle.compute_freshness(v)
    item.result_vacancy_id = v.id
    item.status = ImportItemStatus.DUPLICATE
    item.failure_reason = f"Merged into vacancy #{v.id}."
    audit(db, "import.merged", target_type="import_item", target_id=item.id, details={"vacancy_id": v.id})
    refresh_batch_status(db, item.batch_id)
    return v
