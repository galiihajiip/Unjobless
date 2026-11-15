import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from unjobless.db.models import (
    CandidateProfile,
    Company,
    JobComparison,
    JobComparisonItem,
    JobVacancy,
    OwnerAccount,
    RawSourceDocument,
    RawSourceVersion,
    Source,
    SourceRun,
)
from unjobless.domain.enums import CollectionMethod, PolicyStatus, RunStatus, RunTrigger, SourceCategory, SourceState

pytestmark = pytest.mark.db


def make_source(db, **kw):
    s = Source(
        key=kw.pop("key", "src-1"),
        name="Test",
        category=SourceCategory.ATS_BOARD,
        connector_type="mock",
        collection_method=CollectionMethod.ATS_PUBLIC_API,
        **kw,
    )
    db.add(s)
    db.flush()
    return s


def make_vacancy(db, **kw):
    v = JobVacancy(title=kw.pop("title", "Data Intern"), normalized_title="data intern", **kw)
    db.add(v)
    db.flush()
    return v


def test_migrations_created_all_tables(db):
    n = db.execute(text("select count(*) from information_schema.tables where table_schema='public'")).scalar()
    assert n >= 60
    exts = {r[0] for r in db.execute(text("select extname from pg_extension"))}
    assert {"pg_trgm", "unaccent"} <= exts


def test_single_owner_enforced(db):
    db.add(OwnerAccount(display_name="A", password_hash="x"))
    db.flush()
    db.add(OwnerAccount(display_name="B", password_hash="y"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_single_profile_enforced(db):
    db.add(CandidateProfile())
    db.flush()
    db.add(CandidateProfile())
    with pytest.raises(IntegrityError):
        db.flush()


def test_enabled_source_requires_reviewed_policy(db):
    make_source(db, state=SourceState.ENABLED, policy_status=PolicyStatus.UNREVIEWED)
    with pytest.raises(IntegrityError):
        db.flush()


def test_enum_values_are_checked(db):
    make_source(db)
    with pytest.raises(IntegrityError):
        db.execute(text("update sources set state='HACKED'"))


def test_one_active_run_per_source(db):
    s = make_source(db)
    db.add(SourceRun(source_id=s.id, trigger=RunTrigger.MANUAL, status=RunStatus.QUEUED, idempotency_key="a"))
    db.flush()
    db.add(SourceRun(source_id=s.id, trigger=RunTrigger.MANUAL, status=RunStatus.RUNNING, idempotency_key="b"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_finished_runs_do_not_block_new_run(db):
    s = make_source(db)
    db.add(SourceRun(source_id=s.id, trigger=RunTrigger.MANUAL, status=RunStatus.SUCCEEDED, idempotency_key="a"))
    db.add(SourceRun(source_id=s.id, trigger=RunTrigger.MANUAL, status=RunStatus.QUEUED, idempotency_key="b"))
    db.flush()


def test_raw_version_unique_per_hash(db):
    s = make_source(db)
    d = RawSourceDocument(source_id=s.id, canonical_url="https://x.test/a", collection_method=CollectionMethod.ATS_PUBLIC_API)
    db.add(d)
    db.flush()
    db.add(RawSourceVersion(document_id=d.id, content_hash="h" * 64, content_type="text/html"))
    db.flush()
    db.add(RawSourceVersion(document_id=d.id, content_hash="h" * 64, content_type="text/html"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_comparison_hard_limit_two(db):
    a, b, c = make_vacancy(db), make_vacancy(db), make_vacancy(db)
    cmp = JobComparison(weights={}, result={}, algorithm_version="1")
    db.add(cmp)
    db.flush()
    db.add_all([JobComparisonItem(comparison_id=cmp.id, vacancy_id=a.id, position=1), JobComparisonItem(comparison_id=cmp.id, vacancy_id=b.id, position=2)])
    db.flush()
    db.add(JobComparisonItem(comparison_id=cmp.id, vacancy_id=c.id, position=3))
    with pytest.raises(IntegrityError):
        db.flush()


def test_comparison_rejects_duplicate_vacancy(db):
    a = make_vacancy(db)
    cmp = JobComparison(weights={}, result={}, algorithm_version="1")
    db.add(cmp)
    db.flush()
    db.add_all([JobComparisonItem(comparison_id=cmp.id, vacancy_id=a.id, position=1), JobComparisonItem(comparison_id=cmp.id, vacancy_id=a.id, position=2)])
    with pytest.raises(IntegrityError):
        db.flush()


def test_salary_order_constraint(db):
    make_vacancy(db, salary_min=5_000_000, salary_max=1_000_000)
    with pytest.raises(IntegrityError):
        db.flush()


def test_vacancy_full_text_search(db):
    co = Company(name="PT Maju Jaya", normalized_name="maju jaya")
    db.add(co)
    db.flush()
    make_vacancy(db, title="Magang Data Analyst", company_name="PT Maju Jaya", description="Program magang 6 bulan di Jakarta")
    hits = db.execute(text("select title from job_vacancies where search_vector @@ plainto_tsquery('simple', 'magang jakarta')")).all()
    assert hits and hits[0][0] == "Magang Data Analyst"
