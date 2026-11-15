"""CV ingestion → confirm → preferences → matching → comparison → tailoring → export → tracker."""

import io
import zipfile

import pytest
from sqlalchemy import select

from unjobless.core.errors import InvalidTransition, ValidationFailed
from unjobless.db.models import CandidateProfileVersion, JobComparisonItem, JobSkill, JobVacancy, MatchAnalysis, TailoredResume
from unjobless.db.session import session_scope
from unjobless.domain.enums import ApplicationStatus, EmploymentType, ProfileVersionStatus, WorkArrangement
from unjobless.domain.enums import VerificationStatus as V
from unjobless.profile import compare, cv, matching
from unjobless.profile.schemas import CareerPreferencesData, ProfileData

pytestmark = pytest.mark.db

CV_LINES = [
    "Budi Santoso", "budi.synthetic@example.com | +62 812 0000 0000 | Bandung",
    "Pendidikan", "Universitas Contoh — S1 Informatika 2022 - sekarang", "IPK: 3.60",
    "Pengalaman", "Data Analyst Intern di PT Data Sejahtera Jan 2025 - Jun 2025", "- Membuat dashboard penjualan dengan SQL dan Looker",
    "- Membersihkan data 20.000 baris dengan Python",
    "Proyek", "Prediksi Harga Rumah", "- Model regresi dengan Python dan Scikit-learn",
    "Keahlian", "SQL, Python, Excel, Looker, Communication",
]


def make_docx() -> bytes:
    import docx

    d = docx.Document()
    for ln in CV_LINES:
        d.add_paragraph(ln)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def test_rejects_non_cv_files(db):
    with pytest.raises(ValidationFailed):
        cv.upload_resume(db, b"MZ\x90\x00binary", "x.exe")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<x/>")
        z.writestr("word/vbaProject.bin", "macro")
    with pytest.raises(ValidationFailed):
        cv.upload_resume(db, buf.getvalue(), "evil.docm")


def test_cv_to_confirmed_profile(engine, clean_db, tmp_path, monkeypatch):
    monkeypatch.setenv("UNJOBLESS_FILES_DIR", str(tmp_path))
    from unjobless.core.config import get_settings

    get_settings.cache_clear()
    data = make_docx()
    with session_scope() as db:
        doc = cv.upload_resume(db, data, "cv.docx")
        rid = doc.id
    vid = cv.process_resume(rid, use_ai=False)
    with session_scope() as db:
        v = db.get(CandidateProfileVersion, vid)
        assert v.status == ProfileVersionStatus.DRAFT
        p = ProfileData.model_validate(v.data)
        assert {"SQL", "Python", "Excel", "Looker"} <= {s.name for s in p.skills}
        assert p.experiences and "Data Analyst Intern" in p.experiences[0].title
        assert p.experiences[0].kind == "internship"
        assert any("20.000" in b.text for b in p.experiences[0].bullets)  # metric preserved verbatim
        assert p.educations and p.educations[0].gpa == "3.60"
        cv.confirm(db, v)
    with session_scope() as db:
        # Editing a confirmed version creates a new draft; the confirmed one is immutable
        active = cv.active_version(db)
        edited = cv.update_draft(db, active, {**active.data, "headline": "Aspiring data analyst"})
        assert edited.id != active.id and active.data.get("headline") is None
        # original file unchanged
        from unjobless.db.models import ResumeDocument
        from unjobless.ingestion.filestore import get_filestore

        assert get_filestore().get(db.get(ResumeDocument, rid).blob_ref) == data
    get_settings.cache_clear()


def seed_profile(db, prefs=None):
    p = ProfileData.model_validate({
        "headline": None, "contact": {"full_name": "Test Person"},
        "educations": [{"id": "edu_1", "institution": "Uni", "degree": "S1", "field": "Informatika", "gpa": "3.6"}],
        "experiences": [{"id": "exp_1", "organization": "PT A", "title": "Data Analyst Intern", "kind": "internship",
                         "bullets": [{"id": "b_1", "text": "Built SQL dashboards for 3 teams"}]}],
        "skills": [{"id": "sk_1", "name": "SQL"}, {"id": "sk_2", "name": "Python"}],
    })
    v = cv.new_draft(db, p)
    cv.confirm(db, v)
    from unjobless.db.models import CareerPreferences

    db.add(CareerPreferences(data=(prefs or CareerPreferencesData(target_roles=["data analyst"], work_arrangements=["REMOTE", "HYBRID"], preferred_cities=["Jakarta"], min_compensation=3_000_000)).model_dump(mode="json")))
    db.flush()
    return v


def vacancy(db, title, skills, **kw):
    v = JobVacancy(title=title, normalized_title=title.lower(), verification_status=V.VERIFIED_OPEN, data_confidence=0.7, **kw)
    db.add(v)
    db.flush()
    for s, req in skills:
        db.add(JobSkill(vacancy_id=v.id, skill=s, normalized_skill=s.lower(), required=req))
    db.flush()
    return v


def test_matching_scores_and_unknowns(db):
    pv = seed_profile(db)
    a = vacancy(db, "Data Analyst Intern", [("SQL", True), ("Tableau", True)], work_arrangement=WorkArrangement.REMOTE, employment_type=EmploymentType.INTERNSHIP)
    matching.recompute_all(db)
    m = db.execute(select(MatchAnalysis).where(MatchAnalysis.vacancy_id == a.id, MatchAnalysis.is_current.is_(True))).scalar_one()
    req = next(c for c in m.breakdown["candidate_fit"] if c["name"] == "required_skills")
    assert req["score"] == 0.5 and req["missing"] == ["Tableau"]
    assert req["matched"][0]["evidence"] == ["sk_1"]
    assert "compensation" in m.breakdown["unknowns"]  # salary not stated → unknown, not zero
    assert m.candidate_fit_score is not None and m.preference_fit_score is not None
    assert m.profile_version_id == pv.id


def test_match_changes_after_preferences_change(db):
    seed_profile(db)
    a = vacancy(db, "Data Analyst Intern", [("SQL", True)], work_arrangement=WorkArrangement.ONSITE)
    matching.recompute_all(db)
    before = db.execute(select(MatchAnalysis.preference_fit_score).where(MatchAnalysis.vacancy_id == a.id, MatchAnalysis.is_current.is_(True))).scalar_one()
    from unjobless.db.models import CareerPreferences

    row = db.execute(select(CareerPreferences)).scalar_one()
    row.data = {**row.data, "work_arrangements": ["ONSITE"]}
    db.flush()
    matching.recompute_all(db)
    after = db.execute(select(MatchAnalysis.preference_fit_score).where(MatchAnalysis.vacancy_id == a.id, MatchAnalysis.is_current.is_(True))).scalar_one()
    assert after > before


def test_excluded_company_is_ineligible(db):
    seed_profile(db, CareerPreferencesData(excluded_companies=["PT Jahat"]))
    a = vacancy(db, "Analyst", [("SQL", True)], company_name="PT Jahat")
    m = matching.upsert_match(db, a, None, None, matching.get_preferences(db))
    assert m.eligible is False and m.breakdown["eligibility_blocks"]


@pytest.mark.parametrize("ids", [[], [1], [1, 2, 3], [5, 5]])
def test_compare_rejects_anything_but_two_distinct(db, ids):
    with pytest.raises(ValidationFailed):
        compare.validate_ids(ids)


def test_compare_result_reproducible_and_missing_is_unknown(db):
    seed_profile(db)
    a = vacancy(db, "Data Analyst Intern", [("SQL", True)], work_arrangement=WorkArrangement.REMOTE, salary_min=3_000_000, salary_max=4_000_000, salary_currency="IDR")
    b = vacancy(db, "Data Analyst Intern", [("SQL", True), ("Python", True)], work_arrangement=WorkArrangement.ONSITE)
    r1 = compare.compare(db, [a.id, b.id], save=True)
    r2 = compare.compare(db, [a.id, b.id], save=False)
    assert [c["winner"] for c in r1["criteria"]] == [c["winner"] for c in r2["criteria"]]
    comp = next(c for c in r1["criteria"] if c["criterion"] == "compensation")
    assert comp["winner"] == "Unknown"  # B does not state pay → not a win for A
    assert db.query(JobComparisonItem).filter_by(comparison_id=r1["id"]).count() == 2


def test_compare_api_rejects_three(engine, clean_db):
    from fastapi.testclient import TestClient

    from unjobless.api.app import create_app

    c = TestClient(create_app(), client=("203.0.113.30", 1))
    c.post("/api/auth/bootstrap", json={"display_name": "O", "password": "correct horse battery staple"})
    c.headers["X-CSRF-Token"] = c.cookies.get("uj_csrf")
    assert c.post("/api/compare", json={"vacancy_ids": [1, 2, 3]}).status_code == 422
    assert c.post("/api/compare", json={"vacancy_ids": [4, 4]}).status_code == 422


def test_tailoring_never_changes_master_and_flags_invented_claims(db):
    from unjobless.applications import tailoring

    pv = seed_profile(db)
    before = dict(pv.data)
    a = vacancy(db, "Data Analyst Intern", [("SQL", True), ("Tableau", True)])
    tr = tailoring.generate(db, a.id, language="en", use_ai=False)
    assert "Tableau" in tr.content["missing_requirements"]
    assert db.get(CandidateProfileVersion, pv.id).data == before
    assert tailoring.check_claim("Built SQL dashboards for 5 teams using Tableau", ["Built SQL dashboards for 3 teams"])
    assert tailoring.check_claim("Created SQL dashboards for 3 teams", ["Built SQL dashboards for 3 teams"]) == []
    # decisions create a new immutable child
    child = tailoring.decide(db, tr, {c["id"]: True for c in tr.content["claims"] if not c["issues"]})
    assert child.parent_id == tr.id and db.query(TailoredResume).count() == 2


def test_claim_with_issues_requires_explicit_confirmation(db):
    from unjobless.applications import tailoring

    seed_profile(db)
    a = vacancy(db, "Data Analyst Intern", [("SQL", True)])
    tr = tailoring.generate(db, a.id, use_ai=False)
    content = dict(tr.content)
    content["claims"] = [{"id": "c_bad", "section": "bullet", "original": "Built SQL dashboards for 3 teams", "proposed": "Built dashboards for 10 teams", "fact_ids": ["b_1"], "issues": ["Introduces numbers"], "accepted": False}]
    tr2 = TailoredResume(vacancy_id=a.id, profile_version_id=tr.profile_version_id, language="id", content=content)
    db.add(tr2)
    db.flush()
    with pytest.raises(ValidationFailed):
        tailoring.decide(db, tr2, {"c_bad": True})


def test_export_pdf_and_docx_open(db, tmp_path, monkeypatch):
    from unjobless.applications import export, tailoring

    seed_profile(db)
    a = vacancy(db, "Data Analyst Intern — Ünïcode ✓", [("SQL", True)], company_name="PT Contoh Ñusantara")
    tr = tailoring.generate(db, a.id, use_ai=False)
    doc = tailoring.resolved_document(db, tr)
    for tpl in export.TEMPLATES:
        pdf = export.render_pdf(doc, tpl)
        assert pdf.startswith(b"%PDF") and len(pdf) > 1000
        docx_bytes = export.render_docx(doc, tpl)
        import docx

        d = docx.Document(io.BytesIO(docx_bytes))
        assert any("Data Analyst Intern" in p.text for p in d.paragraphs)


def test_tracker_flow_and_history(db):
    from unjobless.applications import tracker

    a = vacancy(db, "Analyst", [], application_url="https://jobs.example.com/apply/1")
    rec = tracker.get_or_create(db, a.id)
    tracker.set_status(db, rec, ApplicationStatus.PREPARING)
    tracker.set_status(db, rec, ApplicationStatus.APPLIED)
    assert rec.applied_at is not None
    with pytest.raises(InvalidTransition):
        tracker.set_status(db, rec, ApplicationStatus.SAVED)
    tracker.set_status(db, rec, ApplicationStatus.SAVED, force=True, note="correction")
    link = tracker.apply_link(db, a.id)
    assert link["domain"] == "jobs.example.com" and "does not submit" in link["note"]
