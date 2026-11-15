"""URL + paste import, review workflow. Uses a fake fetcher (no live network) and real Postgres commits."""

import pytest
from sqlalchemy import select

from tests.helpers import FakeFetcher
from unjobless.db.models import ImportItem, JobVacancy, OpportunitySignal
from unjobless.db.session import session_scope
from unjobless.domain.enums import ImportBatchStatus, ImportItemStatus
from unjobless.domain.enums import VerificationStatus as V
from unjobless.ingestion import imports, review

pytestmark = pytest.mark.db

PAGE = """<html><head><title>Data Intern - Acme</title></head><body><main>
<h1>Data Analyst Intern</h1><p>We're hiring a Data Analyst Intern at PT Acme in Jakarta (hybrid).</p>
<h2>Requirements</h2><ul><li>SQL</li><li>Python</li></ul>
<p>Apply at https://acme.example/apply/data-intern before 31 December 2026.</p></main></body></html>"""
ROBOTS = (200, "text/plain", "User-agent: *\nAllow: /")


class PublicFetcher(FakeFetcher):
    pass


def routes():
    return {
        "https://acme.example/robots.txt": ROBOTS,
        "https://acme.example/jobs/1": (200, "text/html", PAGE + " " * 300),
        "https://login.example/robots.txt": ROBOTS,
        "https://login.example/post": (403, "text/html", "Forbidden"),
        "https://wall.example/robots.txt": ROBOTS,
        "https://wall.example/p": (
            200,
            "text/html",
            "<html><body>Please verify you are human. Captcha.</body></html>",
        ),
        "https://norobots.example/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /"),
        "https://norobots.example/x": (200, "text/html", PAGE),
    }


def test_line_validation_dedupes_and_blocks(db):
    lines = imports.check_lines(
        db,
        "https://acme.example/jobs/1\nhttps://acme.example/jobs/1?utm_source=x\nhttp://127.0.0.1/admin\nftp://x.example/\nnot a url\nacme.example/jobs/2",
    )
    ok = [c for c in lines if c.ok]
    assert [c.url for c in ok] == ["https://acme.example/jobs/1", "https://acme.example/jobs/2"]
    errs = {c.raw: c.error for c in lines if not c.ok}
    assert "Duplicate" in errs["https://acme.example/jobs/1?utm_source=x"]
    assert "private" in errs["http://127.0.0.1/admin"]


def test_batch_partial_failure_and_per_item_states(engine, clean_db):
    with session_scope() as db:
        batch, _ = imports.create_url_batch(
            db,
            "https://acme.example/jobs/1\nhttps://login.example/post\nhttps://wall.example/p\nhttps://norobots.example/x",
        )
        ids = [
            i.id
            for i in db.execute(
                select(ImportItem).where(ImportItem.batch_id == batch.id).order_by(ImportItem.position)
            ).scalars()
        ]
        bid = batch.id
    f = PublicFetcher(routes())
    for i in ids:
        imports.process_import_item(i, fetcher=f, use_ai=False)
    with session_scope() as db:
        items = {
            i.input_url: i for i in db.execute(select(ImportItem).where(ImportItem.batch_id == bid)).scalars()
        }
        assert items["https://acme.example/jobs/1"].status == ImportItemStatus.NEEDS_REVIEW
        assert items["https://acme.example/jobs/1"].extraction["extraction"]["title"]
        assert items["https://login.example/post"].status == ImportItemStatus.UNAVAILABLE
        assert "Paste content" in items["https://login.example/post"].failure_reason
        assert items["https://wall.example/p"].failure_code == "access_wall"
        assert items["https://norobots.example/x"].status == ImportItemStatus.BLOCKED
        from unjobless.db.models import ImportBatch

        assert db.get(ImportBatch, bid).status == ImportBatchStatus.COMPLETED_WITH_ERRORS
        # Nothing is saved as a vacancy without review
        assert db.query(JobVacancy).count() == 0


def test_review_confirm_vacancy_and_idempotent_reimport(engine, clean_db):
    with session_scope() as db:
        batch, _ = imports.create_url_batch(db, "https://acme.example/jobs/1")
        iid = db.execute(select(ImportItem.id).where(ImportItem.batch_id == batch.id)).scalar_one()
    imports.process_import_item(iid, fetcher=PublicFetcher(routes()), use_ai=False)
    with session_scope() as db:
        v = review.confirm_as_vacancy(db, db.get(ImportItem, iid), {"company": "PT Acme"})
        vid = v.id
        assert v.verification_status == V.VERIFIED_OPEN and v.company_name == "PT Acme"
        assert v.field_meta["company"]["origin"] == "USER_PROVIDED"
    with session_scope() as db:
        b2, _ = imports.create_url_batch(db, "https://acme.example/jobs/1")
        iid2 = db.execute(select(ImportItem.id).where(ImportItem.batch_id == b2.id)).scalar_one()
    imports.process_import_item(iid2, fetcher=PublicFetcher(routes()), use_ai=False)
    with session_scope() as db:
        it = db.get(ImportItem, iid2)
        assert it.status == ImportItemStatus.DUPLICATE and it.result_vacancy_id == vid


def test_retry_after_correction(engine, clean_db):
    with session_scope() as db:
        batch, _ = imports.create_url_batch(db, "https://login.example/post")
        iid = db.execute(select(ImportItem.id).where(ImportItem.batch_id == batch.id)).scalar_one()
    imports.process_import_item(iid, fetcher=PublicFetcher(routes()), use_ai=False)
    with session_scope() as db:
        imports.retry_item(db, db.get(ImportItem, iid), corrected_url="https://acme.example/jobs/1")
    imports.process_import_item(iid, fetcher=PublicFetcher(routes()), use_ai=False)
    with session_scope() as db:
        it = db.get(ImportItem, iid)
        assert it.status == ImportItemStatus.NEEDS_REVIEW and it.retry_count == 1


def test_paste_preserves_exact_text_and_lead_stays_unverified(engine, clean_db):
    from unjobless.db.models import RawSourceVersion
    from unjobless.intelligence.pipeline import process_version

    text = "Kantorku   lagi buka posisi Product Analyst, bisa aku refer.\nDM aku ya 🙏"
    with session_scope() as db:
        batch = imports.create_paste_batch(
            db, [imports.PasteInput(text=text, platform="Instagram", author_label="@public_account")]
        )
        item = db.execute(select(ImportItem).where(ImportItem.batch_id == batch.id)).scalar_one()
        iid, vid = item.id, item.raw_version_id
        assert db.get(RawSourceVersion, vid).raw_text == text
    with session_scope() as db:
        process_version(db, vid, use_ai=False)
    with session_scope() as db:
        it = db.get(ImportItem, iid)
        assert it.status == ImportItemStatus.NEEDS_REVIEW
        assert it.extraction["classification"]["primary"] == "REFERRAL_SIGNAL"
        s = review.confirm_as_lead(db, it)
        assert s.status == V.POTENTIAL_LEAD
    with session_scope() as db:
        assert db.query(JobVacancy).count() == 0 and db.query(OpportunitySignal).count() == 1


def test_paste_rejects_unsafe_source_url(db):
    from unjobless.core.errors import ValidationFailed

    with pytest.raises(ValidationFailed):
        imports.create_paste_batch(db, [imports.PasteInput(text="x", source_url="javascript:alert(1)")])


def test_identical_paste_twice_gets_review_each_time(engine, clean_db):
    from unjobless.intelligence.pipeline import process_version

    text = "We're hiring a Junior Data Analyst at Example Analytics (remote). Requirements: SQL. Apply at https://x.invalid/a"
    ids = []
    for _ in range(2):
        with session_scope() as db:
            b = imports.create_paste_batch(db, [imports.PasteInput(text=text)])
            it = db.execute(select(ImportItem).where(ImportItem.batch_id == b.id)).scalar_one()
            ids.append((it.id, it.raw_version_id))
        with session_scope() as db:
            process_version(db, ids[-1][1], use_ai=False)
    assert ids[0][1] == ids[1][1]  # same immutable raw version
    with session_scope() as db:
        assert all(db.get(ImportItem, i).status == ImportItemStatus.NEEDS_REVIEW for i, _ in ids)
