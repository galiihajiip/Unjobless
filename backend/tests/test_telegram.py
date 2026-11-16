"""Public Telegram channel preview connector: parsing, back-paging, incremental cursor, signals."""

import pytest

from tests.helpers import FakeFetcher, approved_source
from unjobless.db.models import JobVacancy, OpportunitySignal
from unjobless.domain.enums import RunStatus, RunTrigger
from unjobless.domain.enums import VerificationStatus as V
from unjobless.intelligence.pipeline import process_version
from unjobless.jobs import runner
from unjobless.sources.connectors.telegram import TelegramConfig, parse_page

pytestmark = pytest.mark.db


def msg(ch, i, text, link=None):
    a = f'<br/>Selengkapnya: <a href="{link}">{link}</a>' if link else ""
    return (
        f'<div class="tgme_widget_message_wrap"><div class="tgme_widget_message js-widget_message" data-post="{ch}/{i}">'
        f'<div class="tgme_widget_message_text js-message_text">{text}{a}</div>'
        f'<div class="tgme_widget_message_footer"><a class="tgme_widget_message_date" href="https://t.me/{ch}/{i}">'
        f'<time datetime="2026-11-15T08:00:00+00:00" class="time">08:00</time></a></div></div></div>'
    )


def page(ch, ids):
    return (
        "<html><body>"
        + "".join(
            msg(
                ch,
                i,
                f"Lowongan Magang Data Analyst PT Contoh {i}<br/>Kirim CV ke hr@contoh.co.id. Deadline 30 November 2026.",
                f"https://contoh.co.id/karir/{i}",
            )
            for i in ids
        )
        + "</body></html>"
    )


ROBOTS = ("https://t.me/robots.txt", (404, "text/plain", b""))


def test_parse_page_extracts_text_links_and_dates():
    posts = parse_page(page("lokerx", [5, 6]), "lokerx")
    assert [p["id"] for p in posts] == [5, 6]
    assert "Magang Data Analyst" in posts[0]["text"] and "\n" in posts[0]["text"]
    assert posts[0]["links"] == ["https://contoh.co.id/karir/5"] and posts[0]["published_at"].year == 2026


def test_config_normalises_and_rejects_bad_usernames():
    assert TelegramConfig(channels=["@lokerx", "https://t.me/s/LokerY"]).channels == ["lokerx", "LokerY"]
    with pytest.raises(ValueError):
        TelegramConfig(channels=["not a channel!"])


def test_backfill_then_incremental(db):
    src = approved_source(
        db,
        key="tg",
        connector_type="telegram_channel",
        config={"channels": ["lokerx"], "pages_per_channel": 2},
    )
    src.rate_limit_per_minute = 600
    f = FakeFetcher(
        dict(
            [
                ROBOTS,
                ("https://t.me/s/lokerx", (200, "text/html", page("lokerx", range(21, 41)))),
                ("https://t.me/s/lokerx?before=21", (200, "text/html", page("lokerx", range(1, 21)))),
            ]
        )
    )
    run = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
    out = runner.execute_run(db, run.id, fetcher=f)
    assert out.status == RunStatus.SUCCEEDED and run.new == 40
    for vid in out.new_version_ids[:3]:
        process_version(db, vid, use_ai=False)
    v = db.query(JobVacancy).first()
    assert db.query(OpportunitySignal).count() >= 1 or v is not None, "post was neither a vacancy nor a lead"
    if v is not None:
        assert v.verification_status in (
            V.NEEDS_REVIEW,
            V.NEW_UNREVIEWED,
        )  # social posts are never auto-verified
    # Next run: two new posts; the connector stops at the posts it already has.
    f2 = FakeFetcher(
        dict([ROBOTS, ("https://t.me/s/lokerx", (200, "text/html", page("lokerx", range(23, 43))))])
    )
    run2 = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
    runner.execute_run(db, run2.id, fetcher=f2)
    assert run2.new == 2 and [c for c in f2.calls if "t.me/s" in c] == ["https://t.me/s/lokerx"]


def test_private_or_missing_channel_is_unavailable(db):
    src = approved_source(
        db, key="tg2", connector_type="telegram_channel", config={"channels": ["nochannel"]}
    )
    src.rate_limit_per_minute = 600
    f = FakeFetcher(
        dict(
            [
                ROBOTS,
                ("https://t.me/s/nochannel", (200, "text/html", "<html>channel preview unavailable</html>")),
            ]
        )
    )
    run = runner.enqueue_source_run(db, src, RunTrigger.MANUAL)
    runner.execute_run(db, run.id, fetcher=f)
    assert run.status == RunStatus.FAILED and "nochannel" in (run.error_message or "")


def test_titles_lose_emoji_and_markdown_but_keep_phone_numbers():
    from unjobless.sources.connectors.telegram import _tidy_line

    assert _tidy_line("📢 *LOWONGAN PEKERJAAN – AKUNTAN*") == "LOWONGAN PEKERJAAN – AKUNTAN"
    assert _tidy_line("🎓 FRESH GRADUATE, ADA PELUANG!") == "FRESH GRADUATE, ADA PELUANG!"
    assert _tidy_line("+62 812 3456") == "+62 812 3456" and _tidy_line("(Urgent) Admin") == "(Urgent) Admin"
    assert _tidy_line("snake_case_word stays") == "snake_case_word stays"


def test_company_does_not_run_onto_next_line():
    from unjobless.intelligence.extraction import COMPANY_RE

    assert (
        COMPANY_RE.search("Rekrutmen PT Paguntaka Cahaya Nusantara\nPKWT").group(0)
        == "PT Paguntaka Cahaya Nusantara"
    )
