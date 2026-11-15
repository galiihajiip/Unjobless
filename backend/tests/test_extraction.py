from datetime import date

from unjobless.intelligence import normalize as N
from unjobless.intelligence.extraction import extract, from_structured, rules_extract, verify_ai_evidence

ID_POST = """Lowongan Magang Data Analyst - PT Maju Bersama
Lokasi: Jakarta Selatan (hybrid)
Durasi: 6 bulan
Kualifikasi:
- Mahasiswa S1 Statistika/Informatika minimal semester 6
- IPK minimal 3,25
- Menguasai SQL, Python, dan Excel
Fasilitas:
- Uang saku Rp 3,5 juta per bulan
- Sertifikat
Kirim CV ke rekrutmen@majubersama.example paling lambat 20 Desember 2026."""

EN_POST = """Software Engineer Intern (Remote)
Responsibilities:
- Build REST API endpoints
Requirements:
- Experience with TypeScript and React
Nice to have:
- Docker
Salary: USD 1,200 - 1,500 / month. Apply at https://jobs.example.com/apply/se-intern by December 31, 2026."""


def test_indonesian_salary_parsing():
    s = N.parse_salary("Gaji Rp 4.500.000 - Rp 5.000.000 per bulan")
    assert (s.min, s.max, s.currency, s.period) == (4_500_000, 5_000_000, "IDR", "MONTH")
    assert N.parse_salary("uang saku Rp 3,5 juta/bulan").min == 3_500_000
    assert N.parse_salary("Hubungi 0812 3456") is None


def test_indonesian_dates():
    d = N.find_cued_date("Batas akhir pendaftaran 15 Januari 2027", N.DEADLINE_CUE)
    assert d.value == date(2027, 1, 15)
    assert N.parse_dates("tanggal 31/12/2026")[0].value == date(2026, 12, 31)


def test_rules_extract_indonesian_post():
    x = rules_extract(
        ID_POST, title="Lowongan Magang Data Analyst - PT Maju Bersama", today=date(2026, 11, 16)
    )
    assert x["employment_type"] == "INTERNSHIP" and x["work_arrangement"] == "HYBRID"
    assert x["salary_min"] == 3_500_000 and x["salary_currency"] == "IDR" and x["pay_period"] == "MONTH"
    assert x["application_deadline"] == "2026-12-20"
    assert x["min_gpa"] == 3.25 and x["min_semester"] == 6
    assert x["internship_duration_months"] == 6
    assert {"SQL", "Python", "Excel"} <= set(x["required_skills"])
    assert x["application_email"] == "rekrutmen@majubersama.example"
    assert x["language"] == "id"
    assert all(e["excerpt"] for e in x["evidence"])


def test_rules_extract_english_post_and_preferred_skills():
    x = rules_extract(EN_POST, title="Software Engineer Intern (Remote)", today=date(2026, 11, 16))
    assert x["work_arrangement"] == "REMOTE"
    assert x["salary_currency"] == "USD" and x["salary_min"] == 1200 and x["salary_max"] == 1500
    assert x["application_url"] == "https://jobs.example.com/apply/se-intern"
    assert "Docker" in x["preferred_skills"] and "Docker" not in x["required_skills"]
    assert x["application_deadline"] == "2026-12-31"


def test_missing_fields_stay_null():
    x = rules_extract("We need a helper. Contact us.", title="Helper")
    assert x["salary_min"] is None and x["application_deadline"] is None and x["is_paid"] is None


def test_structured_values_take_precedence():
    s = {
        "provenance": "documented_ats_api",
        "title": "Data Intern",
        "company": "Acme",
        "locations": ["Bandung"],
        "salary": {"min": 1, "max": 2, "currency": "USD", "period": "MONTH"},
    }
    x, method = extract("Location: Jakarta", structured=[s], use_ai=False)
    assert x.locations == ["Bandung"] and x.company == "Acme" and x.salary_currency == "USD"
    assert method.startswith("documented_ats_api")
    assert from_structured(s)["evidence"][0]["origin"] == "EXPLICIT"


def test_ai_values_without_verbatim_evidence_are_dropped():
    ai = {
        "application_deadline": "2027-01-01",
        "salary_min": 9e6,
        "salary_max": 9e6,
        "application_url": "https://made.up/x",
        "is_paid": True,
        "min_gpa": None,
        "evidence": [{"field": "salary", "excerpt": "Rp 9 juta", "origin": "EXPLICIT", "confidence": 0.9}],
        "warnings": [],
    }
    out = verify_ai_evidence(ai, "Lowongan admin. Gaji kompetitif.")
    assert (
        out["application_deadline"] is None and out["salary_min"] is None and out["application_url"] is None
    )
    assert out["evidence"][0]["origin"] == "INFERRED"
