"""End-to-end smoke test against a running Unjobless deployment.

Usage (from backend/):  uv run python ../deploy/scripts/smoke_test.py https://localhost:8443 \
    --password "..." [--setup-token TOKEN] [--insecure] [--live-source] [--phase seed|verify]

- seed:   bootstrap (if needed), create profile + preferences, paste import + confirm, compare,
          tailor + export, optionally a live public ATS source run; writes a summary JSON.
- verify: log in and check the records from `seed` still exist (used after backup/restore/migration).

Synthetic data only. `--insecure` skips TLS verification (for Caddy's local CA on localhost).
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
from pathlib import Path

import httpx

STATE = Path(__file__).with_name("smoke_state.json")
PASTE = (
    "Lowongan Magang Data Analyst — PT Smoke Test Indonesia (Jakarta, hybrid).\n"
    "Kualifikasi: mahasiswa S1 semester 6, menguasai SQL dan Python.\n"
    "Fasilitas: uang saku Rp 2.500.000 per bulan.\n"
    "Daftar di https://smoke.invalid/apply/da paling lambat 31 Desember 2026."
)
PASTE2 = "We're hiring a Junior Data Analyst at Example Analytics (remote). Requirements: SQL, Excel, Tableau. Apply at https://smoke.invalid/apply/jda"


class Client:
    def __init__(self, base: str, insecure: bool):
        self.c = httpx.Client(base_url=base.rstrip("/") + "/api", verify=not insecure, timeout=60, follow_redirects=False)

    def csrf(self) -> dict[str, str]:
        return {"X-CSRF-Token": self.c.cookies.get("uj_csrf") or ""}

    def get(self, path: str) -> httpx.Response:
        return self.c.get(path)

    def post(self, path: str, json_body: object = None, **kw: object) -> httpx.Response:
        return self.c.post(path, json=json_body if json_body is not None else ({} if "files" not in kw else None), headers=self.csrf(), **kw)  # type: ignore[arg-type]

    def put(self, path: str, json_body: object) -> httpx.Response:
        return self.c.put(path, json=json_body, headers=self.csrf())


def ok(r: httpx.Response, what: str) -> dict:
    if r.status_code >= 400:
        print(f"FAIL {what}: {r.status_code} {r.text[:300]}")
        sys.exit(1)
    print(f"ok   {what}")
    return r.json() if r.headers.get("content-type", "").startswith("application/json") else {}


def wait(cond, what: str, timeout: float = 120.0) -> object:  # type: ignore[no-untyped-def]
    start = time.time()
    while time.time() - start < timeout:
        v = cond()
        if v:
            print(f"ok   {what}")
            return v
        time.sleep(2)
    print(f"FAIL timeout waiting for {what}")
    sys.exit(1)


def login(cl: Client, password: str, token: str | None) -> None:
    st = ok(cl.get("/auth/state"), "auth state")
    if not st["bootstrapped"]:
        ok(cl.post("/auth/bootstrap", {"display_name": "Smoke Tester", "password": password, "setup_token": token}), "bootstrap owner")
    elif not st["authenticated"]:
        ok(cl.post("/auth/login", {"password": password}), "login")


def docx_cv() -> bytes:
    import docx

    d = docx.Document()
    for ln in ["Sinta Pratiwi (synthetic)", "sinta.synthetic@example.com", "Pendidikan", "Universitas Contoh — S1 Statistika 2022 - sekarang", "IPK: 3.55",
               "Pengalaman", "Data Intern di PT Contoh Jan 2025 - Jun 2025", "- Membuat laporan mingguan dengan SQL", "Keahlian", "SQL, Python, Excel"]:
        d.add_paragraph(ln)
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()


def seed(cl: Client, live: bool) -> None:
    r = ok(cl.c.post("/profile/resumes", files={"file": ("cv.docx", docx_cv(), "application/octet-stream")}, headers=cl.csrf()), "upload synthetic CV")
    rid = r["resume_id"]
    wait(lambda: cl.get(f"/profile/resumes/{rid}/extraction").json().get("status") == "done", "CV processed by worker")
    draft = cl.get("/profile").json()["latest_draft"]
    ok(cl.post(f"/profile/versions/{draft['id']}/confirm"), "confirm profile")
    ok(cl.put("/profile/preferences", {"target_roles": ["data analyst"], "work_arrangements": ["REMOTE", "HYBRID"], "preferred_cities": ["Jakarta"], "employment_types": ["INTERNSHIP", "FULL_TIME"]}), "save preferences")
    ids = []
    for text in (PASTE, PASTE2):
        b = ok(cl.post("/imports/paste", {"records": [{"text": text, "platform": "smoke"}]}), "paste import")["batch"]
        item = wait(lambda b=b: next((i for i in cl.get(f"/imports/batches/{b['id']}").json()["items"] if i["status"] == "NEEDS_REVIEW"), None), "paste analysed")
        v = ok(cl.post(f"/imports/items/{item['id']}/confirm-vacancy", {"corrections": {}}), "confirm vacancy")
        ids.append(v["vacancy_id"])
    ok(cl.post("/profile/matches/recompute"), "recompute matches")
    cmp_ = ok(cl.post("/compare", {"vacancy_ids": ids, "save": True}), "compare two vacancies")
    r3 = cl.post("/compare", {"vacancy_ids": [ids[0], ids[1], ids[0]]})
    assert r3.status_code == 422, "third vacancy must be rejected"
    print("ok   compare rejects three ids")
    tr = ok(cl.post(f"/vacancies/{ids[0]}/tailor", {"language": "id", "use_ai": False}), "tailor CV")
    ex = ok(cl.post(f"/tailored/{tr['id']}/export", {"format": "pdf", "template": "ats_classic"}), "export PDF")
    pdf = cl.get(f"/exports/{ex['id']}")
    assert pdf.content.startswith(b"%PDF"), "export is not a PDF"
    print("ok   download PDF")
    app = ok(cl.post(f"/applications/{ids[0]}"), "track application")
    if live:
        s = ok(cl.post("/sources", {"key": "smoke-gitlab", "name": "GitLab (Greenhouse)", "connector_type": "greenhouse_board", "config": {"board": "gitlab"}}), "add live source")
        ok(cl.post(f"/sources/{s['id']}/policy-review", {"decision": "APPROVED", "terms_notes": "Documented public Job Board API."}), "review policy")
        ok(cl.post(f"/sources/{s['id']}/enable"), "enable source")
        ok(cl.post(f"/sources/{s['id']}/run"), "run now")
        wait(lambda: (cl.get(f"/sources/{s['id']}").json().get("last_run") or {}).get("status") in ("SUCCEEDED", "PARTIAL"), "live source run finished", 300)
        wait(lambda: cl.get("/vacancies?limit=1&status=VERIFIED_OPEN").json()["total"] > 2, "ATS jobs processed into verified vacancies", 300)
    STATE.write_text(json.dumps({"vacancy_ids": ids, "comparison_id": cmp_["id"], "tailored_id": tr["id"], "export_id": ex["id"], "application_id": app["id"], "resume_id": rid}))
    print(f"seed complete → {STATE}")


def verify(cl: Client) -> None:
    st = json.loads(STATE.read_text())
    for vid in st["vacancy_ids"]:
        v = ok(cl.get(f"/vacancies/{vid}"), f"vacancy {vid} present")
        assert v["source_links"], "source references must survive"
    ok(cl.get(f"/compare/{st['comparison_id']}"), "comparison present")
    ok(cl.get(f"/tailored/{st['tailored_id']}"), "tailored CV present")
    pdf = cl.get(f"/exports/{st['export_id']}")
    assert pdf.content.startswith(b"%PDF"), "exported file missing after restore"
    print("ok   export file present")
    cvf = cl.get(f"/profile/resumes/{st['resume_id']}/file")
    assert cvf.status_code == 200 and cvf.content[:2] == b"PK", "original CV missing after restore"
    print("ok   original CV present")
    prof = ok(cl.get("/profile"), "profile")
    assert prof["active"], "confirmed profile missing"
    print("verify complete")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--password", required=True)
    ap.add_argument("--setup-token")
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--live-source", action="store_true")
    ap.add_argument("--phase", choices=["seed", "verify"], default="seed")
    a = ap.parse_args()
    cl = Client(a.base, a.insecure)
    login(cl, a.password, a.setup_token)
    seed(cl, a.live_source) if a.phase == "seed" else verify(cl)


if __name__ == "__main__":
    main()
