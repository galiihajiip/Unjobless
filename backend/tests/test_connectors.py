"""Connector contract tests against recorded fixtures (no live network)."""

import pytest

from tests.helpers import FakeFetcher, approved_source, fixture_json
from unjobless.db.models import RawSourceVersion
from unjobless.domain.enums import RunStatus, RunTrigger
from unjobless.jobs import runner

pytestmark = pytest.mark.db

GH = "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"
LV = "https://api.lever.co/v0/postings/acme?mode=json"
AS = "https://api.ashbyhq.com/posting-api/job-board/acme?includeCompensation=true"


@pytest.mark.parametrize(
    "ctype,url,fixture",
    [("greenhouse_board", GH, "greenhouse.json"), ("lever_postings", LV, "lever.json"), ("ashby_board", AS, "ashby.json")],
)
def test_ats_connector_maps_fields_and_provenance(db, ctype, url, fixture):
    src = approved_source(db, key=ctype.replace("_", "-"), connector_type=ctype, config={"board": "acme", "company_name": "Acme"})
    fetcher = FakeFetcher({url: (200, "application/json", fixture_json(fixture))})
    run = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
    out = runner.execute_run(db, run.id, fetcher=fetcher)
    assert out.status == RunStatus.SUCCEEDED, run.error_message
    assert run.new == 2
    v = db.get(RawSourceVersion, out.new_version_ids[0])
    s = v.structured_data[0]
    assert s["provenance"] == "documented_ats_api"
    assert s["title"] and s["application_url"].startswith("https://")
    assert v.extracted_text and "<" not in v.extracted_text[:200]
    # No invented fields: salary only when the API provides it
    if ctype == "greenhouse_board":
        assert "salary" not in s
    if ctype == "lever_postings":
        assert s["salary"]["currency"] == "USD" and s["salary"]["period"] == "YEAR"


def test_board_not_found_marks_unavailable(db):
    src = approved_source(db, key="gh", connector_type="greenhouse_board", config={"board": "acme"})
    run = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
    runner.execute_run(db, run.id, fetcher=FakeFetcher({}))
    assert run.status == RunStatus.FAILED and run.error_code == "unavailable"


def test_invalid_board_slug_rejected(db):
    from unjobless.core.errors import ValidationFailed
    from unjobless.sources import service

    with pytest.raises(ValidationFailed):
        service.create_source(db, key="bad", name="bad", connector_type="greenhouse_board", config={"board": "../../etc"})
