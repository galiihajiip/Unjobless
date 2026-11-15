"""Feed/query performance benchmark on synthetic data (`python -m unjobless.evaluation.perf <database-url>`).

Never run against a real database: it inserts thousands of synthetic rows.
"""

from __future__ import annotations

import random
import statistics
import sys
import time
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

TITLES = ["Data Analyst", "Backend Engineer", "Frontend Developer", "UI/UX Designer", "Marketing Intern", "Accounting Staff", "Product Manager", "QA Engineer", "Content Writer", "HR Generalist"]
CITIES = ["Jakarta", "Bandung", "Surabaya", "Yogyakarta", "Medan", "Semarang", "Bali", "Tangerang"]
SKILLS = ["SQL", "Python", "Excel", "Figma", "React", "Go", "Docker", "Communication", "Tableau", "Java"]


def seed(url: str, n: int) -> None:
    eng = create_engine(url)
    rng = random.Random(42)
    with eng.begin() as c:
        c.execute(text("INSERT INTO companies (name, normalized_name, manually_verified) SELECT 'Company ' || g, 'company ' || g, false FROM generate_series(1, 400) g"))
        base = c.execute(text("SELECT min(id) FROM companies")).scalar_one()
        rows = []
        for i in range(n):
            t = f"{rng.choice(['', 'Junior ', 'Senior ', 'Magang '])}{rng.choice(TITLES)}"
            city = rng.choice(CITIES)
            rows.append({
                "t": t, "nt": t.lower(), "co": base + rng.randint(0, 399), "cn": f"Company {rng.randint(1, 400)}", "st": rng.choice(["VERIFIED_OPEN", "LIKELY_OPEN", "NEEDS_REVIEW", "STATUS_UNKNOWN", "EXPIRED"]),
                "fr": rng.choice(["NEW", "ACTIVE", "STALE", "CLOSING_SOON"]), "et": rng.choice(["INTERNSHIP", "FULL_TIME", "CONTRACT"]), "wa": rng.choice(["ONSITE", "HYBRID", "REMOTE"]),
                "loc": city, "conf": rng.random(), "desc": f"{t} role in {city}. " + " ".join(rng.sample(SKILLS, 4)) * 20,
                "sk": " ".join(rng.sample(SKILLS, 3)), "days": rng.randint(0, 200),
            })
        c.execute(text(
            "INSERT INTO job_vacancies (title, normalized_title, company_id, company_name, verification_status, freshness, employment_type, work_arrangement, seniority, location_text, data_confidence, description, skills_text, first_seen_at, last_seen_at, details, field_meta, extraction_warnings, classification, deadline_tz_uncertain) "
            "VALUES (:t, :nt, :co, :cn, :st, :fr, :et, :wa, 'UNKNOWN', :loc, :conf, :desc, :sk, now() - make_interval(days => :days), now(), '{}', '{}', '[]', 'DIRECT_VACANCY', true)"
        ), rows)
        c.execute(text("INSERT INTO job_locations (vacancy_id, raw, city, is_remote) SELECT id, location_text, location_text, false FROM job_vacancies"))
        c.execute(text("INSERT INTO job_skills (vacancy_id, skill, normalized_skill, required, origin) SELECT v.id, s, lower(s), true, 'EXPLICIT' FROM job_vacancies v, unnest(string_to_array(v.skills_text, ' ')) s"))
        c.execute(text("INSERT INTO match_analyses (vacancy_id, preferences_hash, algorithm_version, candidate_fit_score, preference_fit_score, data_confidence_score, overall_score, weights, breakdown, is_current) SELECT id, 'x', '1.0', random(), random(), 0.5, random(), '{}', '{}', true FROM job_vacancies"))
        c.execute(text("ANALYZE"))


def bench(client: TestClient, path: str, n: int = 7) -> dict[str, Any]:
    times = []
    for _ in range(n):
        t = time.perf_counter()
        r = client.get(path)
        times.append((time.perf_counter() - t) * 1000)
        assert r.status_code == 200, r.text[:200]
    return {"path": path, "p50_ms": round(statistics.median(times), 1), "max_ms": round(max(times), 1)}


def main(url: str, n: int = 20000) -> list[dict[str, Any]]:
    import os

    os.environ["DATABASE_URL"] = url
    from unjobless.api.app import create_app
    from unjobless.api.deps import require_owner

    seed(url, n)
    app = create_app()
    app.dependency_overrides[require_owner] = lambda: None
    c = TestClient(app)
    paths = [
        "/api/vacancies?limit=25",
        "/api/vacancies?limit=25&q=data%20analyst%20jakarta&sort=relevance",
        "/api/vacancies?limit=25&city=Bandung&employment_type=INTERNSHIP&work_arrangement=HYBRID",
        "/api/vacancies?limit=25&skill=Python&skill=SQL&sort=best_fit",
        "/api/vacancies?limit=25&sort=deadline&min_confidence=0.6",
        "/api/vacancies/facets",
        "/api/overview",
    ]
    out = [bench(c, p) for p in paths]
    first = c.get("/api/vacancies?limit=25").json()
    cur = first["next_cursor"]
    for _ in range(20):
        cur = c.get(f"/api/vacancies?limit=25&cursor={cur}").json()["next_cursor"]
    out.append(bench(c, f"/api/vacancies?limit=25&cursor={cur}"))
    return out


if __name__ == "__main__":
    for row in main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 20000):
        print(row)
