"""Discover feed API: filter combinations, search, stable keyset pagination, owner actions."""

import pytest
from fastapi.testclient import TestClient

from unjobless.api.app import create_app
from unjobless.db.models import JobLocation, JobSkill, JobVacancy
from unjobless.db.session import session_scope
from unjobless.domain.enums import EmploymentType, WorkArrangement
from unjobless.domain.enums import VerificationStatus as V

pytestmark = pytest.mark.db


@pytest.fixture
def client(engine, clean_db):
    c = TestClient(create_app(), client=("203.0.113.40", 1))
    c.post("/api/auth/bootstrap", json={"display_name": "O", "password": "correct horse battery staple"})
    c.headers["X-CSRF-Token"] = c.cookies.get("uj_csrf")
    with session_scope() as db:
        for i in range(60):
            v = JobVacancy(
                title=f"{'Data' if i % 2 else 'Design'} Intern {i}", normalized_title=f"intern {i}",
                verification_status=V.VERIFIED_OPEN if i % 5 else V.EXPIRED,
                employment_type=EmploymentType.INTERNSHIP if i % 3 else EmploymentType.FULL_TIME,
                work_arrangement=WorkArrangement.REMOTE if i % 4 == 0 else WorkArrangement.ONSITE,
                description="magang jakarta sql" if i % 2 else "design figma bandung", data_confidence=(i % 10) / 10,
            )
            db.add(v)
            db.flush()
            db.add(JobLocation(vacancy_id=v.id, raw="x", city="Jakarta" if i % 2 else "Bandung"))
            db.add(JobSkill(vacancy_id=v.id, skill="SQL" if i % 2 else "Figma", normalized_skill="sql" if i % 2 else "figma"))
    return c


def ids(r):
    return [x["id"] for x in r.json()["items"]]


def test_default_hides_expired(client):
    r = client.get("/api/vacancies?limit=100")
    assert r.json()["total"] == 48 and all(x["verification_status"] != "EXPIRED" for x in r.json()["items"])


def test_filters_combine_with_and(client):
    r = client.get("/api/vacancies?limit=100&city=Jakarta&employment_type=INTERNSHIP&skill=SQL")
    items = r.json()["items"]
    assert items and all(x["employment_type"] == "INTERNSHIP" and x["title"].startswith("Data") for x in items)
    r2 = client.get("/api/vacancies?limit=100&city=Jakarta&skill=Figma")
    assert r2.json()["total"] == 0


def test_full_text_search(client):
    r = client.get("/api/vacancies?limit=100&q=figma%20bandung&sort=relevance")
    assert r.json()["total"] > 0 and all(x["title"].startswith("Design") for x in r.json()["items"])


@pytest.mark.parametrize("sort", ["newest", "confidence", "deadline", "best_fit"])
def test_keyset_pagination_is_stable_and_complete(client, sort):
    seen, cursor = [], None
    while True:
        r = client.get(f"/api/vacancies?limit=7&sort={sort}" + (f"&cursor={cursor}" if cursor else ""))
        seen += ids(r)
        cursor = r.json()["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 48


def test_save_dismiss_and_hide_dismissed(client):
    first = ids(client.get("/api/vacancies?limit=1"))[0]
    assert client.put(f"/api/vacancies/{first}/saved", json={"state": "DISMISSED"}).status_code == 200
    assert first not in ids(client.get("/api/vacancies?limit=100"))
    assert first in ids(client.get("/api/vacancies?limit=100&saved=dismissed"))


def test_owner_status_correction_recorded(client):
    vid = ids(client.get("/api/vacancies?limit=1"))[0]
    r = client.post(f"/api/vacancies/{vid}/status", json={"status": "CLOSED", "reason": "Company confirmed it is filled"})
    assert r.json()["status"] == "CLOSED"
    hist = client.get(f"/api/vacancies/{vid}").json()["history"]
    assert hist[0]["actor"] == "USER" and hist[0]["to"] == "CLOSED"


def test_invalid_cursor_rejected(client):
    assert client.get("/api/vacancies?cursor=not-base64!!").status_code == 422


def test_apply_link_requires_safe_url(client):
    with session_scope() as db:
        v = JobVacancy(title="x", normalized_title="x", application_url="javascript:alert(1)")
        db.add(v)
        db.flush()
        vid = v.id
    r = client.get(f"/api/vacancies/{vid}/apply-link")
    assert r.status_code == 422
