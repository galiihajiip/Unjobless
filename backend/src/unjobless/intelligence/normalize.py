"""Deterministic normalisation for Indonesian and English career content.

Every parser returns the raw matched text alongside the value so callers can store evidence.
Nothing here guesses: when parsing is uncertain the function returns None.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from unjobless.intelligence.text import normalize_key

# ---------------------------------------------------------------- employment / arrangement

EMPLOYMENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "INTERNSHIP",
        re.compile(
            r"\b(intern(ship)?s?|magang|pkl|praktik kerja lapangan|kerja praktek|kp\b|mbkm|msib)\b", re.I
        ),
    ),
    (
        "TRAINEE",
        re.compile(
            r"\b(management trainee|mt program|trainee|officer development program|odp|graduate program)\b",
            re.I,
        ),
    ),
    ("FREELANCE", re.compile(r"\b(freelance|freelancer|lepas)\b", re.I)),
    ("PART_TIME", re.compile(r"\b(part[- ]?time|paruh waktu)\b", re.I)),
    ("CONTRACT", re.compile(r"\b(contract|kontrak|pkwt)\b", re.I)),
    ("TEMPORARY", re.compile(r"\b(temporary|sementara)\b", re.I)),
    ("VOLUNTEER", re.compile(r"\b(volunteer|relawan|sukarelawan)\b", re.I)),
    ("FULL_TIME", re.compile(r"\b(full[- ]?time|penuh waktu|permanent|karyawan tetap|pkwtt)\b", re.I)),
]
ARRANGEMENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("HYBRID", re.compile(r"\b(hybrid|hibrida)\b", re.I)),
    (
        "REMOTE",
        re.compile(
            r"\b(remote|fully remote|wfa|work from anywhere|work from home|wfh|kerja dari rumah|jarak jauh)\b",
            re.I,
        ),
    ),
    ("ONSITE", re.compile(r"\b(on[- ]?site|wfo|work from office|kerja di kantor|onsite)\b", re.I)),
    ("FLEXIBLE", re.compile(r"\b(flexible (working|location|arrangement)|fleksibel)\b", re.I)),
]
SENIORITY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("INTERN", re.compile(r"\b(intern|magang)\b", re.I)),
    ("ENTRY", re.compile(r"\b(entry[- ]level|fresh ?graduate|fresh ?grad|lulusan baru)\b", re.I)),
    ("JUNIOR", re.compile(r"\b(junior|jr\.?)\b", re.I)),
    ("SENIOR", re.compile(r"\b(senior|sr\.?)\b", re.I)),
    ("LEAD", re.compile(r"\b(lead|principal|staff engineer)\b", re.I)),
    ("MANAGER", re.compile(r"\b(manager|head of|manajer)\b", re.I)),
    ("EXECUTIVE", re.compile(r"\b(director|vp|vice president|chief|direktur)\b", re.I)),
]


@dataclass
class Match:
    value: str
    excerpt: str
    start: int
    end: int


def first_match(text: str, patterns: list[tuple[str, re.Pattern[str]]]) -> Match | None:
    best: Match | None = None
    for value, pat in patterns:
        m = pat.search(text)
        if m and (best is None or m.start() < best.start):
            best = Match(value, m.group(0), m.start(), m.end())
    return best


def employment_type(text: str) -> Match | None:
    # Prefer internship/trainee mentions in the title-ish first 300 chars
    head = text[:300]
    return first_match(head, EMPLOYMENT_PATTERNS) or first_match(text, EMPLOYMENT_PATTERNS)


def work_arrangement(text: str) -> Match | None:
    return first_match(text, ARRANGEMENT_PATTERNS)


def seniority(title: str) -> str | None:
    m = first_match(title, SENIORITY_PATTERNS)
    return m.value if m else None


# ---------------------------------------------------------------- salary

_NUM = r"(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)"
_MULT = r"\s*(juta|jt|rb|ribu|k|m|million|mio)?"
SALARY_RE = re.compile(
    r"(?P<cur>rp\.?|idr|usd|us\$|\$|sgd|s\$|eur|€|myr|rm)\s*"
    + _NUM
    + _MULT
    + r"(?:\s*(?:-|–|—|s/d|sd|sampai|to|hingga)\s*(?:rp\.?|idr|usd|\$|sgd|eur|€)?\s*"
    + _NUM
    + _MULT
    + r")?"
    + r"(?:\s*(?:/|per|tiap)\s*(?P<per>bulan|bln|month|mo|tahun|year|yr|annum|jam|hour|hr|hari|day|minggu|week|proyek|project))?",
    re.I,
)
CURRENCY = {
    "rp": "IDR",
    "rp.": "IDR",
    "idr": "IDR",
    "usd": "USD",
    "us$": "USD",
    "$": "USD",
    "sgd": "SGD",
    "s$": "SGD",
    "eur": "EUR",
    "€": "EUR",
    "myr": "MYR",
    "rm": "MYR",
}
PERIOD = {
    "bulan": "MONTH",
    "bln": "MONTH",
    "month": "MONTH",
    "mo": "MONTH",
    "tahun": "YEAR",
    "year": "YEAR",
    "yr": "YEAR",
    "annum": "YEAR",
    "jam": "HOUR",
    "hour": "HOUR",
    "hr": "HOUR",
    "hari": "DAY",
    "day": "DAY",
    "minggu": "WEEK",
    "week": "WEEK",
    "proyek": "PROJECT",
    "project": "PROJECT",
}
MULT = {
    "juta": 1_000_000,
    "jt": 1_000_000,
    "m": 1_000_000,
    "million": 1_000_000,
    "mio": 1_000_000,
    "rb": 1_000,
    "ribu": 1_000,
    "k": 1_000,
}


def _to_number(raw: str, mult: str | None, currency: str) -> float | None:
    s = raw
    if mult:
        # "4,5 juta" or "4.5 juta" → decimal separator
        s = s.replace(",", ".")
        if s.count(".") > 1:
            s = s.replace(".", "")
    else:
        # thousands separators: "4.500.000" / "4,500,000"; a single separator with 3 trailing digits is thousands
        if re.fullmatch(r"\d{1,3}([.,]\d{3})+", s):
            s = re.sub(r"[.,]", "", s)
        else:
            s = s.replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    if mult:
        v *= MULT.get(mult.lower(), 1)
    return v


@dataclass
class Salary:
    min: float | None
    max: float | None
    currency: str
    period: str | None
    excerpt: str
    start: int
    end: int


def parse_salary(text: str) -> Salary | None:
    for m in SALARY_RE.finditer(text):
        cur = CURRENCY.get(m.group("cur").lower().rstrip("."), CURRENCY.get(m.group("cur").lower()))
        if not cur:
            continue
        g = m.groups()
        lo = _to_number(g[1], g[2], cur)
        hi = _to_number(g[3], g[4] or g[2], cur) if g[3] else None
        if lo is None:
            continue
        # Ignore implausible numbers (e.g. "$1" in prose, years, phone numbers)
        if cur == "IDR" and lo < 100_000:
            continue
        if cur != "IDR" and lo < 5:
            continue
        per = PERIOD.get((m.group("per") or "").lower())
        return Salary(lo, hi if hi is not None else lo, cur, per, m.group(0).strip(), m.start(), m.end())
    return None


UNPAID_RE = re.compile(r"\b(unpaid|tidak dibayar|tanpa (gaji|uang saku)|non[- ]?paid)\b", re.I)
PAID_RE = re.compile(
    r"\b(paid internship|magang berbayar|uang saku|stipend|insentif|allowance|digaji)\b", re.I
)


# ---------------------------------------------------------------- dates

MONTHS = {
    "jan": 1,
    "januari": 1,
    "january": 1,
    "feb": 2,
    "februari": 2,
    "february": 2,
    "mar": 3,
    "maret": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "mei": 5,
    "may": 5,
    "jun": 6,
    "juni": 6,
    "june": 6,
    "jul": 7,
    "juli": 7,
    "july": 7,
    "agu": 8,
    "agt": 8,
    "ags": 8,
    "agustus": 8,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "okt": 10,
    "oct": 10,
    "oktober": 10,
    "october": 10,
    "nov": 11,
    "nop": 11,
    "november": 11,
    "nopember": 11,
    "des": 12,
    "dec": 12,
    "desember": 12,
    "december": 12,
}
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))
DATE_TEXT_RE = re.compile(
    rf"\b(\d{{1,2}})\s+({_MON})\.?\s+(\d{{4}})\b|\b({_MON})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.I
)
DATE_NUM_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b|\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
DEADLINE_CUE = re.compile(
    r"(deadline|batas (akhir|waktu)( pendaftaran| pengiriman)?|closing date|apply (by|before)|ditutup|"
    r"pendaftaran (ditutup|dibuka hingga|sampai)|last day|paling lambat|terakhir|until|hingga|s/d|before|\bby)",
    re.I,
)
START_CUE = re.compile(r"(start date|mulai|start(s|ing)? on|periode magang)", re.I)


@dataclass
class DateMatch:
    value: date
    excerpt: str
    start: int
    end: int


def parse_dates(text: str) -> list[DateMatch]:
    out: list[DateMatch] = []
    for m in DATE_TEXT_RE.finditer(text):
        try:
            if m.group(1):
                d = date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
            else:
                d = date(int(m.group(6)), MONTHS[m.group(4).lower()], int(m.group(5)))
        except (ValueError, KeyError):
            continue
        out.append(DateMatch(d, m.group(0), m.start(), m.end()))
    for m in DATE_NUM_RE.finditer(text):
        try:
            if m.group(1):
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            else:  # Indonesian convention: DD/MM/YYYY
                d = date(int(m.group(6)), int(m.group(5)), int(m.group(4)))
        except ValueError:
            continue
        out.append(DateMatch(d, m.group(0), m.start(), m.end()))
    return sorted(out, key=lambda x: x.start)


def find_cued_date(text: str, cue: re.Pattern[str], window: int = 80) -> DateMatch | None:
    dates = parse_dates(text)
    for c in cue.finditer(text):
        for d in dates:
            if c.start() <= d.start <= c.end() + window:
                return DateMatch(d.value, text[c.start() : d.end], c.start(), d.end)
    return None


def parse_iso_date(v: object) -> date | None:
    if not v:
        return None
    s = str(v)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


# ---------------------------------------------------------------- locations (Indonesia-first)

ID_CITIES = {
    "jakarta": ("Jakarta", "DKI Jakarta"),
    "jakarta selatan": ("Jakarta Selatan", "DKI Jakarta"),
    "jaksel": ("Jakarta Selatan", "DKI Jakarta"),
    "jakarta pusat": ("Jakarta Pusat", "DKI Jakarta"),
    "jakpus": ("Jakarta Pusat", "DKI Jakarta"),
    "jakarta barat": ("Jakarta Barat", "DKI Jakarta"),
    "jakarta timur": ("Jakarta Timur", "DKI Jakarta"),
    "jakarta utara": ("Jakarta Utara", "DKI Jakarta"),
    "bandung": ("Bandung", "Jawa Barat"),
    "surabaya": ("Surabaya", "Jawa Timur"),
    "yogyakarta": ("Yogyakarta", "DI Yogyakarta"),
    "jogja": ("Yogyakarta", "DI Yogyakarta"),
    "jogjakarta": ("Yogyakarta", "DI Yogyakarta"),
    "semarang": ("Semarang", "Jawa Tengah"),
    "malang": ("Malang", "Jawa Timur"),
    "medan": ("Medan", "Sumatera Utara"),
    "bali": ("Bali", "Bali"),
    "denpasar": ("Denpasar", "Bali"),
    "tangerang": ("Tangerang", "Banten"),
    "tangerang selatan": ("Tangerang Selatan", "Banten"),
    "tangsel": ("Tangerang Selatan", "Banten"),
    "bsd": ("Tangerang Selatan", "Banten"),
    "bekasi": ("Bekasi", "Jawa Barat"),
    "depok": ("Depok", "Jawa Barat"),
    "bogor": ("Bogor", "Jawa Barat"),
    "makassar": ("Makassar", "Sulawesi Selatan"),
    "palembang": ("Palembang", "Sumatera Selatan"),
    "batam": ("Batam", "Kepulauan Riau"),
    "balikpapan": ("Balikpapan", "Kalimantan Timur"),
    "solo": ("Surakarta", "Jawa Tengah"),
    "surakarta": ("Surakarta", "Jawa Tengah"),
    "pekanbaru": ("Pekanbaru", "Riau"),
    "cikarang": ("Cikarang", "Jawa Barat"),
}
COUNTRY_WORDS = {
    "indonesia": "ID",
    "singapore": "SG",
    "singapura": "SG",
    "malaysia": "MY",
    "united states": "US",
    "usa": "US",
    "remote": None,
}
CITY_RE = re.compile(
    r"\b(" + "|".join(sorted((re.escape(k) for k in ID_CITIES), key=len, reverse=True)) + r")\b", re.I
)


@dataclass
class Location:
    raw: str
    city: str | None
    region: str | None
    country: str | None
    is_remote: bool


def normalize_location(raw: str) -> Location:
    key = normalize_key(raw)
    remote = bool(re.search(r"\b(remote|wfh|wfa|anywhere)\b", key))
    m = CITY_RE.search(key)
    if m:
        city, region = ID_CITIES[m.group(1).lower()]
        return Location(raw, city, region, "ID", remote)
    country = next(
        (code for word, code in COUNTRY_WORDS.items() if re.search(rf"\b{re.escape(word)}\b", key) and code),
        None,
    )
    return Location(raw, None, None, country, remote)


def find_locations(text: str, limit: int = 5) -> list[tuple[str, int, int]]:
    out: list[tuple[str, int, int]] = []
    seen = set()
    for m in CITY_RE.finditer(text):
        k = m.group(1).lower()
        city = ID_CITIES[k][0]
        if city not in seen:
            seen.add(city)
            out.append((m.group(0), m.start(), m.end()))
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- skills taxonomy

SKILL_ALIASES: dict[str, list[str]] = {
    "Python": ["python"],
    "SQL": ["sql", "mysql", "postgresql", "postgres"],
    "Excel": ["excel", "microsoft excel", "ms excel", "spreadsheet"],
    "JavaScript": ["javascript", "js"],
    "TypeScript": ["typescript", "ts"],
    "React": ["react", "reactjs", "react.js"],
    "Node.js": ["node.js", "nodejs", "node"],
    "Java": ["java"],
    "Go": ["golang"],
    "PHP": ["php"],
    "Laravel": ["laravel"],
    "Kotlin": ["kotlin"],
    "Swift": ["swift"],
    "Flutter": ["flutter"],
    "Dart": ["dart"],
    "C++": ["c++"],
    "C#": ["c#"],
    "R": ["r programming", "bahasa r"],
    "Tableau": ["tableau"],
    "Power BI": ["power bi", "powerbi"],
    "Looker": ["looker", "looker studio", "google data studio"],
    "Machine Learning": ["machine learning", "ml"],
    "Deep Learning": ["deep learning"],
    "Data Analysis": ["data analysis", "analisis data", "data analytics"],
    "Statistics": ["statistics", "statistik"],
    "Figma": ["figma"],
    "UI/UX Design": ["ui/ux", "ui ux", "ux design", "ui design", "user experience"],
    "Adobe Photoshop": ["photoshop"],
    "Adobe Illustrator": ["illustrator"],
    "Canva": ["canva"],
    "Git": ["git", "github", "gitlab"],
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"],
    "AWS": ["aws", "amazon web services"],
    "GCP": ["gcp", "google cloud"],
    "Azure": ["azure"],
    "Linux": ["linux"],
    "Django": ["django"],
    "FastAPI": ["fastapi"],
    "Flask": ["flask"],
    "Spring": ["spring boot", "spring"],
    "Vue.js": ["vue", "vue.js", "vuejs"],
    "Angular": ["angular"],
    "HTML": ["html"],
    "CSS": ["css"],
    "Tailwind CSS": ["tailwind"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "TensorFlow": ["tensorflow"],
    "PyTorch": ["pytorch"],
    "Scikit-learn": ["scikit-learn", "sklearn"],
    "NLP": ["nlp", "natural language processing"],
    "Computer Vision": ["computer vision"],
    "SEO": ["seo"],
    "Digital Marketing": ["digital marketing", "pemasaran digital"],
    "Social Media": ["social media", "media sosial", "instagram", "tiktok"],
    "Copywriting": ["copywriting", "copywriter"],
    "Content Writing": ["content writing", "penulisan konten"],
    "Accounting": ["accounting", "akuntansi"],
    "Finance": ["finance", "keuangan"],
    "Tax": ["tax", "perpajakan", "pajak"],
    "Auditing": ["audit", "auditing"],
    "Project Management": ["project management", "manajemen proyek"],
    "Agile": ["agile", "scrum"],
    "Communication": ["communication", "komunikasi"],
    "Leadership": ["leadership", "kepemimpinan"],
    "Teamwork": ["teamwork", "kerja sama tim", "team player"],
    "Problem Solving": ["problem solving", "pemecahan masalah"],
    "English": ["english", "bahasa inggris"],
    "Mandarin": ["mandarin", "chinese"],
    "Microsoft Office": ["microsoft office", "ms office"],
    "Public Speaking": ["public speaking"],
    "Customer Service": ["customer service", "layanan pelanggan"],
    "Sales": ["sales", "penjualan"],
    "Recruitment": ["recruitment", "rekrutmen"],
    "Human Resources": ["human resources", "hrd", "sdm"],
    "AutoCAD": ["autocad"],
    "SAP": ["sap"],
    "Selenium": ["selenium"],
    "Postman": ["postman"],
    "REST API": ["rest api", "restful"],
    "GraphQL": ["graphql"],
    "MongoDB": ["mongodb"],
    "Redis": ["redis"],
    "Spark": ["apache spark", "pyspark", "spark"],
    "Airflow": ["airflow"],
    "dbt": ["dbt"],
    "BigQuery": ["bigquery"],
    "Video Editing": ["video editing", "premiere", "capcut", "editing video"],
    "Photography": ["photography", "fotografi"],
}
_ALIAS_TO_SKILL = {normalize_key(a): k for k, aliases in SKILL_ALIASES.items() for a in [k, *aliases]}
_AMBIGUOUS = {
    "go",
    "r",
    "ts",
    "js",
    "node",
    "spring",
    "spark",
    "ml",
    "sap",
    "sales",
    "tax",
    "audit",
    "git",
    "english",
}


def canonical_skill(name: str) -> str:
    k = normalize_key(name)
    return _ALIAS_TO_SKILL.get(k, name.strip())


def normalized_skill_key(name: str) -> str:
    return normalize_key(canonical_skill(name))


def find_skills(text: str) -> list[tuple[str, str, int, int]]:
    """(canonical, matched text, start, end) for taxonomy skills found in text."""
    found: dict[str, tuple[str, str, int, int]] = {}
    low = text
    for alias_key, canonical in _ALIAS_TO_SKILL.items():
        if canonical in found or len(alias_key) < 2:
            continue
        if alias_key in _AMBIGUOUS and alias_key not in ("english",):
            # require exact-case-ish token match for ambiguous short aliases
            pat = re.compile(rf"(?<![\w.]){re.escape(alias_key)}(?![\w])", re.I if len(alias_key) > 3 else 0)
        else:
            pat = re.compile(rf"(?<![\w]){re.escape(alias_key)}(?![\w])", re.I)
        m = pat.search(low)
        if m:
            found[canonical] = (canonical, m.group(0), m.start(), m.end())
    return sorted(found.values(), key=lambda x: x[2])


# ---------------------------------------------------------------- education

EDU_RE = re.compile(
    r"\b(S1|S2|S3|D3|D4|SMA|SMK|Bachelor'?s?|Master'?s?|Diploma|PhD|Sarjana|mahasiswa|student)\b", re.I
)
EDU_MAP = {
    "s1": "BACHELOR",
    "sarjana": "BACHELOR",
    "bachelor": "BACHELOR",
    "bachelors": "BACHELOR",
    "bachelor's": "BACHELOR",
    "d4": "BACHELOR",
    "s2": "MASTER",
    "master": "MASTER",
    "masters": "MASTER",
    "master's": "MASTER",
    "s3": "DOCTORATE",
    "phd": "DOCTORATE",
    "d3": "DIPLOMA",
    "diploma": "DIPLOMA",
    "sma": "HIGH_SCHOOL",
    "smk": "HIGH_SCHOOL",
    "mahasiswa": "STUDENT",
    "student": "STUDENT",
}
SEMESTER_RE = re.compile(
    r"(?:minimal|min\.?|at least|semester)\s*(?:semester\s*)?(\d{1,2})\b|\bsemester\s*(\d{1,2})\s*(?:ke atas|keatas|\+|or above|and above)",
    re.I,
)
GPA_RE = re.compile(r"\b(?:ipk|gpa)\s*(?:minimal|min\.?|minimum|of|≥|>=)?\s*:?\s*([0-4][.,]\d{1,2})", re.I)
EXPERIENCE_RE = re.compile(
    r"(?:minimal|min\.?|at least|minimum)?\s*(\d{1,2})\+?\s*(?:tahun|years?|yrs?)\s*(?:pengalaman|of experience|experience)",
    re.I,
)
OPENINGS_RE = re.compile(r"\b(\d{1,3})\s*(?:orang|posisi|positions?|openings?|slots?|kuota)\b", re.I)
DURATION_RE = re.compile(r"(?:durasi|duration|selama|periode)?\s*:?\s*(\d{1,2})\s*(?:bulan|months?)\b", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.I)
