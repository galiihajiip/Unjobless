from datetime import date, timedelta

import pytest

from tests.helpers import FakeFetcher, approved_source, fixture_json
from unjobless.core.time import utcnow
from unjobless.db.models import (
    JobEvidence,
    JobVacancy,
    JobVacancySource,
    OpportunitySignal,
    SentimentAnalysis,
    VacancyStatusHistory,
)
from unjobless.domain.enums import Actor, RunTrigger
from unjobless.domain.enums import VerificationStatus as V
from unjobless.intelligence import dedup, lifecycle
from unjobless.intelligence.pipeline import process_version
from unjobless.jobs import runner

pytestmark = pytest.mark.db
GH = "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"


def run_gh(db, src, body):
    run = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
    out = runner.execute_run(db, run.id, fetcher=FakeFetcher({GH: (200, "application/json", body)}))
    for vid in out.new_version_ids:
        process_version(db, vid, use_ai=False)
    return run


def test_ats_jobs_become_verified_vacancies_with_provenance(db):
    src = approved_source(db, key="gh", connector_type="greenhouse_board", config={"board": "acme"})
    run_gh(db, src, fixture_json("greenhouse.json"))
    vs = db.query(JobVacancy).all()
    assert len(vs) == 2
    v = vs[0]
    assert v.verification_status == V.VERIFIED_OPEN and v.last_verified_at is not None
    assert v.company_name == "GitLab"
    link = db.query(JobVacancySource).filter_by(vacancy_id=v.id).one()
    assert link.source_id == src.id and link.raw_document_id
    assert db.query(JobEvidence).filter_by(vacancy_id=v.id).count() > 0
    assert db.query(VacancyStatusHistory).filter_by(vacancy_id=v.id).count() == 1


def test_missing_from_complete_listing_is_uncertain_not_closed(db):
    import json

    src = approved_source(db, key="gh", connector_type="greenhouse_board", config={"board": "acme"})
    body = json.loads(fixture_json("greenhouse.json"))
    run_gh(db, src, json.dumps(body).encode())
    body["jobs"] = body["jobs"][:1]
    run_gh(db, src, json.dumps(body).encode())
    statuses = sorted(v.verification_status.value for v in db.query(JobVacancy).all())
    assert statuses == ["STATUS_UNKNOWN", "VERIFIED_OPEN"]
    assert all(v.verification_status != V.CLOSED for v in db.query(JobVacancy).all())


def test_same_vacancy_from_two_sources_merges(db):
    a = approved_source(db, key="gh-a", connector_type="greenhouse_board", config={"board": "acme"})
    b = approved_source(db, key="gh-b", connector_type="greenhouse_board", config={"board": "acme"})
    run_gh(db, a, fixture_json("greenhouse.json"))
    run_gh(db, b, fixture_json("greenhouse.json"))
    canon = db.query(JobVacancy).filter(JobVacancy.merged_into_id.is_(None)).all()
    assert len(canon) == 2
    for v in canon:
        assert db.query(JobVacancySource).filter_by(vacancy_id=v.id).count() == 2


def make_v(db, title, company_id=None, city=None, seniority="UNKNOWN", **kw):
    from unjobless.db.models import JobLocation

    v = JobVacancy(
        title=title,
        normalized_title=title.lower(),
        company_id=company_id,
        seniority=seniority,
        description=kw.pop("description", title + " description " * 20),
        **kw,
    )
    db.add(v)
    db.flush()
    if city:
        db.add(JobLocation(vacancy_id=v.id, raw=city, city=city))
        db.flush()
    return v


def test_distinct_locations_do_not_auto_merge(db):
    from unjobless.db.models import Company

    c = Company(name="Acme", normalized_name="acme")
    db.add(c)
    db.flush()
    a = make_v(db, "data analyst intern", c.id, "Jakarta")
    b = make_v(db, "data analyst intern", c.id, "Surabaya")
    assert dedup.process_new_vacancy(db, b).id == b.id
    assert b.merged_into_id is None and a.merged_into_id is None


def test_distinct_levels_do_not_auto_merge(db):
    from unjobless.db.models import Company

    c = Company(name="Acme", normalized_name="acme")
    db.add(c)
    db.flush()
    make_v(db, "backend engineer", c.id, seniority="JUNIOR")
    b = make_v(db, "backend engineer", c.id, seniority="SENIOR")
    dedup.process_new_vacancy(db, b)
    assert b.merged_into_id is None


def test_merge_and_undo_is_traceable(db):
    from unjobless.db.models import DeduplicationCandidate

    a = make_v(db, "x", canonical_url="https://a.example/j/1")
    b = make_v(db, "x", canonical_url="https://a.example/j/1")
    keep = dedup.process_new_vacancy(db, b)
    assert keep.id == a.id and b.merged_into_id == a.id
    cand = db.query(DeduplicationCandidate).one()
    dedup.undo_merge(db, cand)
    assert b.merged_into_id is None


def test_lifecycle_explicit_deadline_expires(db):
    v = make_v(
        db,
        "x",
        verification_status=V.VERIFIED_OPEN,
        application_deadline=date(2026, 1, 1),
        field_meta={"evidenced_fields": ["application_deadline"]},
    )
    lifecycle.apply_deadline_rule(db, v, today=date(2026, 2, 1))
    assert v.verification_status == V.EXPIRED and v.freshness.value == "EXPIRED"


def test_lifecycle_old_post_without_deadline_not_expired(db):
    v = make_v(
        db, "x", verification_status=V.VERIFIED_OPEN, source_published_at=utcnow() - timedelta(days=400)
    )
    lifecycle.apply_deadline_rule(db, v)
    assert v.verification_status == V.VERIFIED_OPEN


def test_lifecycle_inferred_deadline_does_not_expire(db):
    v = make_v(
        db,
        "x",
        verification_status=V.VERIFIED_OPEN,
        application_deadline=date(2026, 1, 1),
        field_meta={"application_deadline": {"origin": "INFERRED"}},
    )
    lifecycle.apply_deadline_rule(db, v, today=date(2026, 2, 1))
    assert v.verification_status == V.VERIFIED_OPEN


def test_user_correction_always_allowed_and_recorded(db):
    v = make_v(db, "x", verification_status=V.EXPIRED)
    lifecycle.set_status(db, v, V.NEEDS_REVIEW, reason="owner says still open", actor=Actor.USER)
    h = db.query(VacancyStatusHistory).filter_by(vacancy_id=v.id).one()
    assert h.actor == Actor.USER and h.to_status == V.NEEDS_REVIEW


def test_closing_soon_freshness(db):
    v = make_v(
        db,
        "x",
        verification_status=V.VERIFIED_OPEN,
        application_deadline=date.today() + timedelta(days=3),
        first_seen_at=utcnow() - timedelta(days=10),
        last_verified_at=utcnow(),
    )
    assert lifecycle.compute_freshness(v).value == "CLOSING_SOON"


def test_mock_source_discussion_creates_sentiment_not_vacancy(db):
    src = approved_source(
        db,
        key="m",
        connector_type="mock",
        config={
            "items": [
                {
                    "id": "1",
                    "title": "",
                    "body": "Pengalaman magang di PT Cepat: kultur toxic dan gaji telat.",
                }
            ]
        },
    )
    run = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
    out = runner.execute_run(db, run.id)
    process_version(db, out.new_version_ids[0], use_ai=False)
    assert db.query(JobVacancy).count() == 0
    assert db.query(SentimentAnalysis).count() >= 1
    assert all(s.polarity.value in ("NEGATIVE", "MIXED") for s in db.query(SentimentAnalysis))


def test_mock_source_referral_creates_signal(db):
    src = approved_source(
        db,
        key="m",
        connector_type="mock",
        config={
            "items": [
                {
                    "id": "1",
                    "title": "",
                    "body": "Kantorku buka posisi Product Analyst, bisa aku refer, DM aku ya.",
                }
            ]
        },
    )
    run = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
    out = runner.execute_run(db, run.id)
    process_version(db, out.new_version_ids[0], use_ai=False)
    s = db.query(OpportunitySignal).one()
    assert s.primary_classification.value == "REFERRAL_SIGNAL" and s.status == V.POTENTIAL_LEAD
    assert db.query(JobVacancy).count() == 0


def test_same_role_listed_for_two_countries_in_one_ats_stays_separate(db):
    import json

    src = approved_source(db, key="gh", connector_type="greenhouse_board", config={"board": "acme"})
    body = json.loads(fixture_json("greenhouse.json"))
    j = body["jobs"][0]
    twin = {
        **j,
        "id": 999999,
        "absolute_url": j["absolute_url"] + "-de",
        "location": {"name": "Remote, Germany"},
    }
    j["location"] = {"name": "Remote, Netherlands"}
    body["jobs"] = [j, twin]
    run_gh(db, src, json.dumps(body).encode())
    assert db.query(JobVacancy).filter(JobVacancy.merged_into_id.is_(None)).count() == 2
