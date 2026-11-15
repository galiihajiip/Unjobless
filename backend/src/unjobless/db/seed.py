"""Development fixtures (`unjobless seed`). Refuses to run in production.

Creates a clearly-labelled mock source with synthetic postings (no real companies or people),
runs it, and processes the results so every screen has data to show during development.
"""

from __future__ import annotations

from sqlalchemy import select

from unjobless.core.config import get_settings
from unjobless.db.models import Source
from unjobless.db.session import session_scope
from unjobless.domain.enums import PolicyStatus, RunTrigger, SourceState

FIXTURE_ITEMS = [
    {"id": "fx-1", "title": "[FIXTURE] Data Analyst Intern", "body": "We're hiring a Data Analyst Intern at PT Contoh Data (Jakarta, hybrid). Requirements: SQL, Python, Excel. Benefits: uang saku Rp 3.000.000 per bulan, mentorship. Apply at https://fixture.invalid/apply/da-intern before 31 December 2026."},
    {"id": "fx-2", "title": "[FIXTURE] Magang UI/UX Designer", "body": "Lowongan Magang UI/UX Designer di Studio Fiktif, Bandung (onsite). Kualifikasi: menguasai Figma, portfolio. Durasi 6 bulan. Daftar di https://fixture.invalid/apply/uiux paling lambat 15 Januari 2027."},
    {"id": "fx-3", "title": "[FIXTURE] Backend Engineer (Go)", "body": "Join our team as Backend Engineer, remote within Indonesia. Requirements: Go, PostgreSQL, Docker, 2 years experience. Salary IDR 12.000.000 - 18.000.000 per month. Apply: https://fixture.invalid/apply/backend"},
    {"id": "fx-4", "title": "", "body": "[FIXTURE] Kantorku lagi buka posisi Product Analyst, bisa aku refer, DM aku ya."},
    {"id": "fx-5", "title": "", "body": "[FIXTURE] Pengalaman magang di PT Fiktif: mentornya suportif tapi uang saku telat terus."},
]


def seed() -> None:
    if get_settings().is_production:
        raise SystemExit("Refusing to load fixtures in production.")
    from unjobless.intelligence.pipeline import process_version
    from unjobless.jobs import runner
    from unjobless.sources import service

    with session_scope() as db:
        src = db.execute(select(Source).where(Source.key == "dev-fixtures")).scalar_one_or_none()
        if src is None:
            src = service.create_source(db, key="dev-fixtures", name="Development fixtures (synthetic)", connector_type="mock",
                                        config={"items": FIXTURE_ITEMS}, policy_notes="Synthetic data for local development only.")
            service.review_policy(db, src, decision=PolicyStatus.APPROVED, terms_notes="No external source.")
            service.change_state(db, src, SourceState.ENABLED)
        run = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
        out = runner.execute_run(db, run.id)
        for vid in out.new_version_ids if out else []:
            process_version(db, vid, use_ai=False)
    print("Loaded development fixtures (marked [FIXTURE]).")
