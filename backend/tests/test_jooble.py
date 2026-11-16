import json

import httpx
import pytest

from tests.helpers import FakeFetcher, approved_source
from unjobless.core.crypto import encrypt_secret
from unjobless.db.models import EncryptedSecret, JobVacancy
from unjobless.domain.enums import RunStatus, RunTrigger
from unjobless.domain.enums import VerificationStatus as V
from unjobless.fetch.safe_fetch import SafeFetcher
from unjobless.intelligence.pipeline import process_version
from unjobless.jobs import runner

pytestmark = pytest.mark.db
URL = "https://id.jooble.org/api/test-key"
JOBS = {
    "totalCount": 2,
    "jobs": [
        {
            "id": 11,
            "title": "Magang <b>Data</b> Analyst",
            "location": "Jakarta",
            "snippet": "Magang 6 bulan, SQL &amp; Excel",
            "salary": "Rp 3 jt",
            "source": "glints.com",
            "type": "Internship",
            "link": "https://id.jooble.org/desc/11",
            "company": "PT Contoh",
            "updated": "2026-11-15T00:00:00",
        },
        {
            "id": 12,
            "title": "Intern Marketing",
            "location": "Bandung",
            "snippet": "",
            "source": "kalibrr.com",
            "link": "https://id.jooble.org/desc/12",
            "company": "CV Maju",
            "updated": "2026-11-14T00:00:00",
        },
    ],
}


class CountingFetcher(FakeFetcher):
    def get(self, url, **kw):
        self.bodies = getattr(self, "bodies", []) + [kw.get("json_body")]
        return super().get(url, **kw)


def with_key(db, src):
    sec = EncryptedSecret(
        purpose="source-secret",
        ciphertext=encrypt_secret("test-key", purpose="source-secret"),
        fingerprint="f",
        hint="…-key",
    )
    db.add(sec)
    db.flush()
    src.secret_id = sec.id


def test_jooble_maps_jobs_as_likely_open(db):
    src = approved_source(
        db,
        key="jb",
        connector_type="jooble_api",
        config={"searches": [{"keywords": "magang", "location": "Indonesia"}], "pages_per_search": 1},
    )
    with_key(db, src)
    f = CountingFetcher({URL: (200, "application/json", json.dumps(JOBS))})
    run = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
    out = runner.execute_run(db, run.id, fetcher=f)
    assert out.status == RunStatus.SUCCEEDED and run.new == 2
    assert f.bodies[0] == {"keywords": "magang", "location": "Indonesia", "page": "1"}
    for vid in out.new_version_ids:
        process_version(db, vid, use_ai=False)
    v = db.query(JobVacancy).filter(JobVacancy.title == "Magang Data Analyst").one()
    assert v.verification_status == V.LIKELY_OPEN and v.company_name == "PT Contoh"
    assert v.application_url == "https://id.jooble.org/desc/11"


def test_daily_budget_is_respected(db):
    src = approved_source(
        db,
        key="jb",
        connector_type="jooble_api",
        config={
            "searches": [{"keywords": "a"}, {"keywords": "b"}, {"keywords": "c"}],
            "pages_per_search": 1,
            "daily_request_budget": 2,
        },
    )
    with_key(db, src)
    f = CountingFetcher({URL: (200, "application/json", json.dumps(JOBS))})
    run = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
    runner.execute_run(db, run.id, fetcher=f)
    assert len(f.calls) == 2
    run2 = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
    runner.execute_run(db, run2.id, fetcher=f)
    assert len(f.calls) == 2  # same day: budget already used


def test_wrong_country_key_explains(db):
    src = approved_source(db, key="jb", connector_type="jooble_api", config={})
    with_key(db, src)
    run = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
    runner.execute_run(db, run.id, fetcher=FakeFetcher({URL: (403, "text/html", "Forbidden")}))
    assert run.status == RunStatus.FAILED and "another country" in run.error_message


def test_safe_fetcher_posts_json_and_never_follows_post_redirects():
    from unjobless.core.errors import FetchFailed

    seen = {}

    def handler(request):
        seen["method"], seen["body"] = request.method, json.loads(request.content)
        return httpx.Response(200, headers={"content-type": "application/json"}, text="{}")

    f = SafeFetcher(resolver=lambda h, p: ["93.184.215.14"], transport=httpx.MockTransport(handler))
    f.get("https://api.example.com/x", json_body={"a": 1})
    assert seen == {"method": "POST", "body": {"a": 1}}
    f2 = SafeFetcher(
        resolver=lambda h, p: ["93.184.215.14"],
        transport=httpx.MockTransport(
            lambda r: httpx.Response(302, headers={"location": "http://127.0.0.1/"})
        ),
    )
    with pytest.raises(FetchFailed):
        f2.get("https://api.example.com/x", json_body={"a": 1})
