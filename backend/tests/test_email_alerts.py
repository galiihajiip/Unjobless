"""Job-alert mailbox connector with a fake IMAP mailbox (no network)."""

from email.message import EmailMessage

import pytest

from tests.helpers import approved_source
from unjobless.db.models import JobVacancy
from unjobless.domain.enums import RunStatus, RunTrigger
from unjobless.intelligence.pipeline import process_version
from unjobless.jobs import runner
from unjobless.sources.connectors import email_alerts

pytestmark = pytest.mark.db

HTML = """<html><body>
<h2>Lowongan baru untukmu</h2>
<table><tr><td><a href="https://glints.com/id/opportunities/jobs/data-analyst-intern/1111-2222?utm_source=email&trk=x">Data Analyst Intern</a>
<div>PT Maju Data · Jakarta Selatan · IDR 3.000.000 - 4.000.000</div></td></tr>
<tr><td><a href="https://glints.com/id/opportunities/jobs/ui-ux-intern/3333-4444?utm_source=email">UI/UX Designer Intern</a>
<div>Studio Kreatif · Bandung</div></td></tr></table>
<a href="https://glints.com/id/settings/unsubscribe">Unsubscribe</a> <a href="https://glints.com/id/opportunities/jobs/explore">See all jobs</a>
</body></html>"""


def alert(sender="Glints <noreply@glints.com>") -> bytes:
    m = EmailMessage()
    m["From"] = sender
    m["Subject"] = "2 lowongan baru"
    m["Date"] = "Mon, 16 Nov 2026 08:00:00 +0700"
    m.set_content("plain fallback")
    m.add_alternative(HTML, subtype="html")
    return bytes(m)


class FakeMailbox:
    messages = [(10, alert()), (11, alert("Spam <x@evil.example>"))]
    opened = []

    def __init__(self, host, user, pw):
        FakeMailbox.opened.append((host, user, pw))

    def fetch_since(self, folder, last_uid, since_days):
        return [(u, r) for u, r in self.messages if u > last_uid]

    def close(self):
        pass


@pytest.fixture(autouse=True)
def fake_mb(monkeypatch):
    monkeypatch.setattr(email_alerts, "MAILBOX_FACTORY", FakeMailbox)
    FakeMailbox.opened = []


def test_parse_alert_extracts_jobs_and_strips_tracking():
    import email
    import email.policy

    jobs = email_alerts.parse_alert(email.message_from_bytes(alert(), policy=email.policy.default))
    assert [j["title"] for j in jobs] == ["Data Analyst Intern", "UI/UX Designer Intern"]
    assert "utm_source" not in jobs[0]["url"] and "trk" not in jobs[0]["url"]
    assert "PT Maju Data" in jobs[0]["context"]


def test_requires_secret(db):
    src = approved_source(db, key="mail", connector_type="email_job_alerts", config={"username": "alerts@example.com"})
    run = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
    runner.execute_run(db, run.id)
    assert run.status == RunStatus.FAILED and run.error_code == "unavailable"


def test_alerts_become_vacancies_incrementally(db):
    from unjobless.core.crypto import encrypt_secret
    from unjobless.db.models import EncryptedSecret

    src = approved_source(db, key="mail", connector_type="email_job_alerts", config={"username": "alerts@example.com"})
    sec = EncryptedSecret(purpose="source-secret", ciphertext=encrypt_secret("app-pass-1234", purpose="source-secret"), fingerprint="f", hint="…1234")
    db.add(sec)
    db.flush()
    src.secret_id = sec.id
    run = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
    out = runner.execute_run(db, run.id)
    assert out.status == RunStatus.SUCCEEDED and run.new == 2  # spam sender ignored
    assert FakeMailbox.opened[0][2] == "app-pass-1234"
    for vid in out.new_version_ids:
        process_version(db, vid, use_ai=False)
    titles = sorted(v.title for v in db.query(JobVacancy))
    assert titles == ["Data Analyst Intern", "UI/UX Designer Intern"]
    v = db.query(JobVacancy).filter_by(title="Data Analyst Intern").one()
    assert v.application_url.startswith("https://glints.com/") and v.verification_status.value != "VERIFIED_OPEN"
    run2 = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
    runner.execute_run(db, run2.id)
    assert run2.discovered == 0  # cursor: only new mail next time


def test_private_imap_host_rejected(db):
    from unjobless.core.errors import ValidationFailed
    from unjobless.sources import service

    with pytest.raises(ValidationFailed):
        service.create_source(db, key="m2", name="m", connector_type="email_job_alerts", config={"username": "a@b.co", "imap_host": "localhost"})
