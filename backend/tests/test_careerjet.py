import json
from urllib.parse import parse_qs, urlsplit

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
BODY = {
    "type": "JOBS",
    "hits": 2,
    "pages": 1,
    "jobs": [
        {
            "title": "Magang Data Analyst",
            "company": "PT Contoh",
            "date": "Sun, 15 Nov 2026 00:00:00 GMT",
            "description": "Magang 6 bulan. SQL.",
            "locations": "Jakarta Selatan, DKI Jakarta",
            "salary": "Rp 3.000.000 per bulan",
            "salary_min": 3000000,
            "salary_max": 3000000,
            "salary_currency_code": "IDR",
            "salary_type": "M",
            "url": "https://jobviewtrack.com/x1",
        },
        {
            "title": "Intern HR",
            "company": "CV Maju",
            "date": "Sat, 14 Nov 2026 00:00:00 GMT",
            "description": "",
            "locations": "Surabaya",
            "url": "https://jobviewtrack.com/x2",
        },
    ],
}


class AnyUrlFetcher(FakeFetcher):
    user_agent = "UnjoblessBot/test"

    def __init__(self, status=200, body=BODY):
        super().__init__({})
        self.status, self.body, self.kw = status, body, []

    def get(self, url, **kw):
        self.calls.append(url)
        self.kw.append(kw)
        from unjobless.fetch.safe_fetch import FetchResult

        return FetchResult(
            url=url,
            requested_url=url,
            status_code=self.status,
            content_type="application/json",
            charset="utf-8",
            body=json.dumps(self.body).encode(),
            truncated=False,
        )


def make(db, **cfg):
    src = approved_source(
        db,
        key="cj",
        connector_type="careerjet_api",
        config={
            "declared_ip": "203.0.113.7",
            "searches": [{"keywords": "magang"}],
            "pages_per_search": 1,
            **cfg,
        },
    )
    sec = EncryptedSecret(
        purpose="source-secret",
        ciphertext=encrypt_secret("cj-key", purpose="source-secret"),
        fingerprint="f",
        hint="…-key",
    )
    db.add(sec)
    db.flush()
    src.secret_id = sec.id
    return src


def test_careerjet_params_auth_and_mapping(db):
    src = make(db)
    f = AnyUrlFetcher()
    run = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
    out = runner.execute_run(db, run.id, fetcher=f)
    assert out.status == RunStatus.SUCCEEDED and run.new == 2
    q = parse_qs(urlsplit(f.calls[0]).query)
    assert (
        q["locale_code"] == ["id_ID"]
        and q["user_ip"] == ["203.0.113.7"]
        and q["user_agent"] == ["UnjoblessBot/test"]
    )
    assert f.kw[0]["basic_auth"] == ("cj-key", "")
    for vid in out.new_version_ids:
        process_version(db, vid, use_ai=False)
    v = db.query(JobVacancy).filter_by(title="Magang Data Analyst").one()
    assert (
        v.verification_status == V.LIKELY_OPEN
        and float(v.salary_min) == 3000000
        and v.salary_currency == "IDR"
    )


def test_undeclared_ip_gives_actionable_error(db):
    src = make(db)
    run = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
    runner.execute_run(
        db,
        run.id,
        fetcher=AnyUrlFetcher(403, {"error": "Unauthorized access from IP 1.2.3.4", "type": "ERROR"}),
    )
    assert run.status == RunStatus.FAILED and "Server IP addresses" in run.error_message


def test_basic_auth_sent_only_to_requested_host():
    seen = []

    def handler(request):
        seen.append((request.headers.get("host"), request.headers.get("authorization")))
        if len(seen) == 1:
            return httpx.Response(302, headers={"location": "https://other.example/"})
        return httpx.Response(200, headers={"content-type": "application/json"}, text="{}")

    from unjobless.core.errors import FetchFailed

    f = SafeFetcher(resolver=lambda h, p: ["93.184.215.14"], transport=httpx.MockTransport(handler))
    with pytest.raises(FetchFailed):
        f.get("https://api.example.com/q", basic_auth=("k", ""))
    assert len(seen) == 1 and seen[0][1].startswith("Basic ")
