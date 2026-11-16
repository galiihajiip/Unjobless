import json

import pytest

from tests.helpers import FakeFetcher, approved_source
from unjobless.db.models import JobVacancy, RawSourceVersion, Source
from unjobless.domain.enums import RunStatus, RunTrigger
from unjobless.domain.enums import VerificationStatus as V
from unjobless.intelligence.pipeline import process_version
from unjobless.jobs import runner

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _no_pause(monkeypatch):
    from unjobless.sources.connectors import remote_feeds

    monkeypatch.setattr(remote_feeds, "PAGE_PAUSE_SECONDS", 0)

SR = "https://api.smartrecruiters.com/v1/companies/acme/postings"


def sr_listing(released="2026-11-13T06:29:28.110Z"):
    return {
        "totalFound": 2,
        "content": [
            {
                "id": "1",
                "name": "Data Analyst Intern",
                "releasedDate": released,
                "location": {"city": "Jakarta", "country": "id", "remote": False},
                "company": {"name": "Acme"},
                "typeOfEmployment": {"label": "Internship"},
                "function": {"label": "Data"},
            },
            {
                "id": "2",
                "name": "Engineer",
                "releasedDate": released,
                "location": {"city": "Singapore", "country": "sg"},
                "company": {"name": "Acme"},
            },
        ],
    }


DETAIL = {
    "postingUrl": "https://jobs.smartrecruiters.com/Acme/1-data",
    "applyUrl": "https://jobs.smartrecruiters.com/Acme/1-data?oga=true",
    "jobAd": {"sections": {"jobDescription": {"title": "Job", "text": "<p>Analyse data with SQL.</p>"}}},
}


def test_smartrecruiters_location_filter_and_incremental(db):
    src = approved_source(
        db,
        key="sr",
        connector_type="smartrecruiters",
        config={"board": "acme", "location_keywords": ["indonesia", "jakarta"]},
    )
    f = FakeFetcher(
        {
            f"{SR}?limit=100&offset=0": (200, "application/json", json.dumps(sr_listing())),
            f"{SR}/1": (200, "application/json", json.dumps(DETAIL)),
        }
    )
    run = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
    out = runner.execute_run(db, run.id, fetcher=f)
    assert out.status == RunStatus.SUCCEEDED and run.new == 1  # Singapore job filtered out
    for vid in out.new_version_ids:
        process_version(db, vid, use_ai=False)
    v = db.query(JobVacancy).one()
    assert v.verification_status == V.VERIFIED_OPEN and v.employment_type.value == "INTERNSHIP"
    # second run: unchanged posting → no detail call, no new raw version, still seen (not marked unknown)
    f2 = FakeFetcher({f"{SR}?limit=100&offset=0": (200, "application/json", json.dumps(sr_listing()))})
    run2 = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
    runner.execute_run(db, run2.id, fetcher=f2)
    assert run2.unchanged == 1 and not any(c[-2:] == "/1" for c in f2.calls)
    assert db.query(RawSourceVersion).count() == 1
    db.refresh(v)
    assert v.verification_status == V.VERIFIED_OPEN


def test_remote_feed_region_filter_and_likely_open(db):
    data = [
        {"legal": "attribution"},
        {
            "id": 1,
            "position": "Data Intern",
            "company": "RemoteCo",
            "location": "Worldwide",
            "url": "https://remoteok.com/r/1",
            "apply_url": "https://remoteok.com/r/1",
            "description": "<p>SQL</p>",
            "date": "2026-11-13T08:00:21+00:00",
            "tags": [],
        },
        {
            "id": 2,
            "position": "Nurse",
            "company": "USCo",
            "location": "United States",
            "url": "https://remoteok.com/r/2",
            "description": "x",
            "tags": [],
        },
        {
            "id": 3,
            "position": "Designer",
            "company": "AsiaCo",
            "location": "Asia, Europe",
            "url": "https://remoteok.com/r/3",
            "description": "y",
            "tags": [],
        },
    ]
    src = approved_source(db, key="rok", connector_type="remoteok_feed", config={})
    run = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
    out = runner.execute_run(
        db,
        run.id,
        fetcher=FakeFetcher({"https://remoteok.com/api": (200, "application/json", json.dumps(data))}),
    )
    assert run.new == 2  # US-only job excluded
    for vid in out.new_version_ids:
        process_version(db, vid, use_ai=False)
    statuses = {v.title: v.verification_status for v in db.query(JobVacancy)}
    assert set(statuses) == {"Data Intern", "Designer"}
    assert all(s == V.LIKELY_OPEN for s in statuses.values())  # aggregator, not employer → not "verified"
    assert all(v.work_arrangement.value == "REMOTE" for v in db.query(JobVacancy))


def test_keyword_filter(db):
    from unjobless.sources.connectors.remote_feeds import RemoteFeedConfig, keyword_ok, region_ok

    cfg = RemoteFeedConfig(keywords=["intern"])
    assert keyword_ok(cfg, "Data Intern") and not keyword_ok(cfg, "Senior Engineer")
    assert (
        region_ok(RemoteFeedConfig(), [])
        and region_ok(RemoteFeedConfig(), ["APAC"])
        and not region_ok(RemoteFeedConfig(), ["Canada"])
    )


def test_starter_pack_installs_approved_and_enabled(db):
    from unjobless.sources.starter_pack import PACK, install

    created = install(db, [PACK[0]["key"], "himalayas"])
    assert len(created) == 2
    for s in created:
        assert s.state.value == "ENABLED" and s.policy_status.value == "APPROVED"
    assert install(db, ["himalayas"]) == []  # idempotent
    assert db.query(Source).filter(Source.key == "himalayas").count() == 1
