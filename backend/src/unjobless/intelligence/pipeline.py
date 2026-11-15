"""Processing pipeline for raw versions.

Raw version → text → classify → (vacancy | signal | sentiment/topics) → normalise → resolve company →
dedupe → lifecycle → mark processed. Two modes:

- auto (scheduled connectors): creates/updates canonical vacancies and signals directly;
- review (user imports): stores the proposal on the ImportItem for the owner to confirm (Block 33).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from unjobless.core.logging import get_logger
from unjobless.db.models import (
    ImportItem,
    OpportunitySignal,
    RawSourceDocument,
    RawSourceVersion,
    SignalEntity,
    Source,
)
from unjobless.domain.enums import (
    CollectionMethod,
    FieldOrigin,
    OpportunityClassification,
    PolicyStatus,
    ProcessingStatus,
)
from unjobless.domain.enums import VerificationStatus as V
from unjobless.intelligence import dedup, lifecycle, sentiment
from unjobless.intelligence.companies import resolve_company
from unjobless.intelligence.extraction import EXTRACTOR_VERSION, extract
from unjobless.intelligence.signals import SignalResult, classify_with_ai
from unjobless.intelligence.structured import extract_main_text
from unjobless.intelligence.text import guess_language, html_to_text
from unjobless.intelligence.vacancies import (
    apply_extraction,
    create_vacancy,
    link_source,
    vacancy_for_document,
)

log = get_logger(__name__)

VACANCY_CLASSES = {OpportunityClassification.DIRECT_VACANCY, OpportunityClassification.RECRUITMENT_CAMPAIGN}
SIGNAL_CLASSES = {
    OpportunityClassification.INFORMAL_OPPORTUNITY_LEAD,
    OpportunityClassification.REFERRAL_SIGNAL,
    OpportunityClassification.RECRUITMENT_CAMPAIGN,
    OpportunityClassification.CAREER_PROGRAM,
    OpportunityClassification.SCHOLARSHIP_OR_COMPETITION,
}
DISCUSSION_CLASSES = {
    OpportunityClassification.EMPLOYER_DISCUSSION,
    OpportunityClassification.EMPLOYER_REVIEW,
    OpportunityClassification.CAREER_TREND,
    OpportunityClassification.REFERRAL_SIGNAL,
    OpportunityClassification.INFORMAL_OPPORTUNITY_LEAD,
}
TRUSTED = {CollectionMethod.ATS_PUBLIC_API, CollectionMethod.OFFICIAL_API}


def version_text(version: RawSourceVersion) -> str:
    """Best readable text for analysis (extracted text > HTML conversion > raw text) plus transcriptions."""
    if version.extracted_text:
        text = version.extracted_text
    elif version.content_type.startswith("text/html"):
        text = extract_main_text(version.raw_text or "")
    elif version.content_type == "application/json":
        text = version.raw_text or ""
    else:
        text = (
            html_to_text(version.raw_text or "")
            if "<" in (version.raw_text or "")[:500]
            else (version.raw_text or "")
        )
    from unjobless.db.models import ContentTranscription

    extra = [t.text for t in _transcriptions(version, ContentTranscription)]
    return "\n\n".join([text, *extra]).strip()


def _transcriptions(version: RawSourceVersion, model: Any) -> list[Any]:
    from sqlalchemy.orm import object_session

    s = object_session(version)
    if s is None:
        return []
    return list(s.execute(select(model).where(model.version_id == version.id)).scalars())


def analyze(db: Session, version: RawSourceVersion, *, use_ai: bool = True) -> dict[str, Any]:
    """Pure analysis (no canonical writes). Returns classification + extraction proposal."""
    text = version_text(version)
    structured = [s for s in (version.structured_data or []) if isinstance(s, dict)]
    title = version.title
    sig = (
        classify_with_ai(
            db, text, title=title, structured=bool(structured), input_ref=f"raw_version:{version.id}"
        )
        if use_ai
        else None
    )
    if sig is None:
        from unjobless.intelligence.signals import classify

        sig = classify(text, title=title, structured=bool(structured))
    proposal: dict[str, Any] = {
        "classification": sig.to_dict(),
        "language": version.language or guess_language(text),
        "extractor_version": EXTRACTOR_VERSION,
    }
    if sig.primary in VACANCY_CLASSES or structured:
        x, method = extract(
            text,
            title=title,
            structured=structured,
            db=db,
            use_ai=use_ai,
            input_ref=f"raw_version:{version.id}",
        )
        proposal["extraction"] = x.model_dump(mode="json")
        proposal["extraction_method"] = method
    return {"text": text, "signal": sig, "proposal": proposal}


def process_version(db: Session, version_id: int, *, use_ai: bool = True) -> None:
    from unjobless.domain.enums import ImportItemStatus

    version = db.get(RawSourceVersion, version_id)
    if version is None:
        return
    if version.processing_status == ProcessingStatus.SUCCEEDED:
        # Identical content re-imported: the raw version is shared, but each new import item still
        # needs its own review proposal.
        pending = (
            db.execute(
                select(ImportItem).where(
                    ImportItem.raw_version_id == version.id, ImportItem.status == ImportItemStatus.EXTRACTED
                )
            )
            .scalars()
            .all()
        )
        if not pending:
            return
        result = analyze(db, version, use_ai=use_ai)
        for it in pending:
            _to_review(db, it, result)
        return
    doc = db.get(RawSourceDocument, version.document_id)
    source = db.get(Source, doc.source_id) if doc else None
    if doc is None or source is None:
        return
    version.processing_status = ProcessingStatus.RUNNING
    db.flush()
    try:
        result = analyze(db, version, use_ai=use_ai)
        sig: SignalResult = result["signal"]
        version.classification = sig.primary
        version.classification_detail = result["proposal"]["classification"]
        version.language = version.language or result["proposal"]["language"]
        items = db.execute(select(ImportItem).where(ImportItem.raw_version_id == version.id)).scalars().all()
        if source.is_system or items:
            for item in items:
                if item.status in (ImportItemStatus.EXTRACTED, ImportItemStatus.NEEDS_REVIEW):
                    _to_review(db, item, result)
        else:
            _auto_ingest(db, source, doc, version, result)
        version.processing_status = ProcessingStatus.SUCCEEDED
        version.processing_error = None
    except Exception as exc:
        log.warning("process_version_failed", version=version_id, error_type=type(exc).__name__)
        version.processing_status = ProcessingStatus.FAILED
        version.processing_error = f"{type(exc).__name__}: {str(exc)[:500]}"
        raise


def _to_review(db: Session, item: ImportItem | None, result: dict[str, Any]) -> None:
    from unjobless.domain.enums import ImportItemStatus
    from unjobless.domain.state_machines import IMPORT_ITEM

    if item is None:
        return
    item.extraction = result["proposal"]
    if item.status != ImportItemStatus.NEEDS_REVIEW:
        IMPORT_ITEM.check(item.status, ImportItemStatus.NEEDS_REVIEW)
        item.status = ImportItemStatus.NEEDS_REVIEW


def _auto_ingest(
    db: Session, source: Source, doc: RawSourceDocument, version: RawSourceVersion, result: dict[str, Any]
) -> None:
    sig: SignalResult = result["signal"]
    text: str = result["text"]
    proposal = result["proposal"]
    company_id = None
    if "extraction" in proposal:
        from unjobless.ai.task_schemas import JobExtraction

        x = JobExtraction.model_validate(proposal["extraction"])
        trusted = source.collection_method in TRUSTED and source.policy_status == PolicyStatus.APPROVED
        existing = vacancy_for_document(db, doc.id)
        if existing is not None:
            apply_extraction(db, existing, x, version=version, source_text=text)
            link_source(db, existing, source, doc, version, application_url=x.application_url)
            if trusted:
                lifecycle.confirm_seen_in_trusted_listing(db, existing, source)
            lifecycle.apply_deadline_rule(db, existing)
            company_id = existing.company_id
        elif x.is_job_posting and x.title:
            if trusted:
                status = V.VERIFIED_OPEN  # live listing on an approved, documented ATS/API source
                reason = f"Listed by {source.name} (approved documented API)."
            elif any(s.get("provenance") == "schema_org_jobposting" for s in version.structured_data or []):
                status = V.LIKELY_OPEN
                reason = "Published as structured JobPosting data on the employer's site."
            else:
                status = (
                    sig.recommendation
                    if sig.recommendation in (V.NEW_UNREVIEWED, V.NEEDS_REVIEW, V.EXPIRED)
                    else V.NEEDS_REVIEW
                )
                reason = sig.reason
            v = create_vacancy(
                db,
                x=x,
                source=source,
                document=doc,
                version=version,
                source_text=text,
                status=status,
                classification=sig.primary
                if sig.primary in VACANCY_CLASSES
                else OpportunityClassification.DIRECT_VACANCY,
                reason=reason,
            )
            v = dedup.process_new_vacancy(db, v)
            company_id = v.company_id
            _schedule_match(v.id)
    elif sig.primary in SIGNAL_CLASSES:
        s = create_signal(db, version, sig, source_text=text)
        company_id = s.company_id
    if sig.primary in DISCUSSION_CLASSES:
        first_party = source.category.value in ("ATS_BOARD", "CAREER_PAGE", "JOB_API")
        sentiment.store_observations(
            db, version, text, company_id=company_id, source_id=source.id, first_party=first_party
        )


def create_signal(
    db: Session, version: RawSourceVersion, sig: SignalResult, *, source_text: str, status: V | None = None
) -> OpportunitySignal:
    company_name = next((e.value for e in sig.entities if e.kind == "company"), None)
    comp = resolve_company(db, company_name) if company_name else None
    s = OpportunitySignal(
        raw_version_id=version.id,
        primary_classification=sig.primary,
        secondary_classifications=[c.value for c in sig.secondary],
        signal_type=sig.signal_type,
        confidence=sig.confidence,
        verification_recommendation=sig.recommendation,
        status=status
        or (
            sig.recommendation
            if sig.recommendation in (V.POTENTIAL_LEAD, V.EXPIRED, V.NEEDS_REVIEW)
            else V.POTENTIAL_LEAD
        ),
        reason=sig.reason,
        ambiguity_flags=sig.ambiguity_flags,
        company_id=comp.id if comp else None,
        company_text=company_name,
        role_text=next((e.value for e in sig.entities if e.kind == "role"), None),
        location_text=next((e.value for e in sig.entities if e.kind == "location"), None),
        application_url=next((e.value for e in sig.entities if e.kind == "application_url"), None),
        summary=source_text[:600],
        language=version.language,
        observed_at=version.source_published_at or version.collected_at,
        detail={"method": sig.method, "evidence": sig.evidence_excerpts},
    )
    db.add(s)
    db.flush()
    for e in sig.entities:
        db.add(
            SignalEntity(
                signal_id=s.id,
                kind=e.kind,
                value=e.value[:2000],
                origin=FieldOrigin(e.origin),
                evidence_excerpt=e.excerpt[:2000],
            )
        )
    db.flush()
    return s


def _schedule_match(vacancy_id: int) -> None:
    try:
        from unjobless.jobs.queue import defer

        defer("recompute_matches", queueing_lock="recompute_matches")
    except Exception:  # noqa: S110 - matching also runs on its own schedule
        pass


def enqueue_versions(version_ids: list[int]) -> None:
    from unjobless.jobs.queue import defer

    for vid in version_ids:
        defer("process_version", queueing_lock=f"version-{vid}", version_id=vid)
