"""Career-page crawler against local fixture HTML (no live sites)."""

import pytest

from tests.helpers import FakeFetcher, approved_source
from unjobless.domain.enums import RunStatus, RunTrigger
from unjobless.jobs import runner

pytestmark = pytest.mark.db

LISTING = """<html><body><h1>Careers</h1>
<a href="/careers/data-intern">Data Intern</a>
<a href="/careers/backend">Backend Engineer</a>
<a href="https://evil.example/careers/x">Off-domain</a>
<a href="/blog/post">Blog</a></body></html>"""
JOB = """<html><head><link rel="canonical" href="https://www.acme.example/careers/data-intern"/>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting","title":"Data Intern","hiringOrganization":{"@type":"Organization","name":"PT Acme"},
"datePosted":"2026-11-01","validThrough":"2026-12-31","employmentType":"INTERN",
"jobLocation":{"@type":"Place","address":{"addressLocality":"Jakarta","addressCountry":"ID"}},
"baseSalary":{"@type":"MonetaryAmount","currency":"IDR","value":{"@type":"QuantitativeValue","minValue":2000000,"maxValue":3000000,"unitText":"MONTH"}},
"description":"<p>Help our analytics team.</p>"}</script></head><body><main><h1>Data Intern</h1><p>Help our analytics team with SQL.</p></main></body></html>"""
JOB2 = "<html><body><main><h1>Backend Engineer</h1><p>Requirements: Go, PostgreSQL. Apply at https://www.acme.example/apply/backend</p></main></body></html>"
WALL = "<html><body>Please verify you are human. Captcha required.</body></html>"
ROBOTS_OK = "User-agent: *\nAllow: /\n"


def routes(robots=ROBOTS_OK, job2=JOB2):
    return {
        "https://www.acme.example/robots.txt": (200, "text/plain", robots),
        "https://www.acme.example/careers": (200, "text/html", LISTING),
        "https://www.acme.example/careers/data-intern": (200, "text/html", JOB),
        "https://www.acme.example/careers/backend": (200, "text/html", job2),
    }


CFG = {
    "start_urls": ["https://www.acme.example/careers"],
    "allowed_path_prefixes": ["/careers"],
    "job_url_pattern": r"/careers/[a-z-]+$",
}


@pytest.fixture(autouse=True)
def _reset_host_state(engine):
    """Politeness state is committed on its own connection; reset it between tests."""
    from sqlalchemy import text

    with engine.begin() as c:
        c.execute(text("DELETE FROM host_rate_state"))
    yield
    with engine.begin() as c:
        c.execute(text("DELETE FROM host_rate_state"))


@pytest.fixture
def src(db):
    s = approved_source(
        db, key="acme-careers", connector_type="career_page", config=CFG, domain="acme.example"
    )
    s.rate_limit_per_minute = 600  # 0.1s between requests in tests
    db.flush()
    return s


def run_with(db, src, fetcher):
    run = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
    return run, runner.execute_run(db, run.id, fetcher=fetcher)


def test_crawls_only_enabled_domain_and_paths(db, src):
    f = FakeFetcher(routes())
    run, out = run_with(db, src, f)
    assert out.status == RunStatus.SUCCEEDED, run.error_message
    assert run.new == 2
    assert not any("evil.example" in c or "/blog/" in c for c in f.calls)


def test_jsonld_parsed_without_invention(db, src):
    from unjobless.db.models import RawSourceVersion

    run, out = run_with(db, src, FakeFetcher(routes()))
    versions = [db.get(RawSourceVersion, i) for i in out.new_version_ids]
    jp = next(v for v in versions if v.structured_data)
    s = jp.structured_data[0]
    assert s["provenance"] == "schema_org_jobposting" and s["employment_type"] == "INTERNSHIP"
    assert s["salary"] == {"min": 2000000, "max": 3000000, "currency": "IDR", "period": "MONTH"}
    other = next(v for v in versions if not v.structured_data)
    assert other.structured_data is None


def test_robots_disallow_blocks_listing(db, src):
    run, out = run_with(db, src, FakeFetcher(routes(robots="User-agent: *\nDisallow: /careers")))
    assert out.status == RunStatus.FAILED and run.error_code == "unavailable"


def test_access_wall_reported_not_bypassed(db, src):
    r = routes()
    r["https://www.acme.example/careers"] = (200, "text/html", WALL)
    run, out = run_with(db, src, FakeFetcher(r))
    assert out.status == RunStatus.FAILED and "CAPTCHA" in run.error_message


def test_changed_page_creates_new_version(db, src):
    run_with(db, src, FakeFetcher(routes()))
    run2, out2 = run_with(db, src, FakeFetcher(routes(job2=JOB2.replace("PostgreSQL", "PostgreSQL, Redis"))))
    assert run2.changed == 1 and run2.unchanged == 1


def test_robots_cannot_be_disabled(db):
    from unjobless.core.errors import ValidationFailed
    from unjobless.sources import service

    with pytest.raises(ValidationFailed):
        service.create_source(
            db,
            key="x",
            name="x",
            connector_type="career_page",
            config={**CFG, "respect_robots": False},
            domain="acme.example",
        )
