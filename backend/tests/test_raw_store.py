import pytest

from unjobless.db.models import Source
from unjobless.domain.enums import RunItemOutcome
from unjobless.ingestion import raw_store
from unjobless.ingestion.raw_store import content_hash, sanitize_metadata, store_item
from unjobless.sources.contract import CollectedItem
from unjobless.sources.service import ensure_system_source

pytestmark = pytest.mark.db


def item(text="Hiring data intern", **kw):
    return CollectedItem(native_id=kw.pop("native_id", "j1"), url=kw.pop("url", "https://x.test/j/1?utm_source=a"), content_type="text/plain", raw_text=text, title=kw.pop("title", "Data Intern"), **kw)


@pytest.fixture
def src(db) -> Source:
    return ensure_system_source(db, "user_paste")


def test_hash_is_whitespace_stable():
    assert content_hash("a  b\n c", "T") == content_hash("a b c", "T")
    assert content_hash("a b c", "T") != content_hash("a b d", "T")


def test_identical_content_is_unchanged(db, src):
    r1 = store_item(db, src, item())
    r2 = store_item(db, src, item(text="Hiring   data intern"))
    assert r1.outcome == RunItemOutcome.NEW
    assert r2.outcome == RunItemOutcome.UNCHANGED
    assert r1.version.id == r2.version.id


def test_changed_content_creates_new_version(db, src):
    r1 = store_item(db, src, item())
    r2 = store_item(db, src, item(text="Hiring data intern — deadline extended"))
    assert r2.outcome == RunItemOutcome.CHANGED
    assert r2.document.id == r1.document.id
    assert r2.document.latest_version_id == r2.version.id
    assert r1.version.raw_text == "Hiring data intern"  # old version preserved


def test_canonical_url_identity_without_native_id(db, src):
    r1 = store_item(db, src, item(native_id=None, url="https://X.test/a/?utm_campaign=z#frag"))
    r2 = store_item(db, src, item(native_id=None, url="https://x.test/a"))
    assert r1.document.id == r2.document.id
    assert r1.document.canonical_url == "https://x.test/a"


def test_missing_metadata_is_ok(db, src):
    r = store_item(db, src, CollectedItem(native_id=None, url=None, content_type="text/plain", raw_text="only text"))
    assert r.outcome == RunItemOutcome.NEW
    assert r.version.source_published_at is None


def test_secrets_never_stored_in_metadata():
    meta = sanitize_metadata({"Cookie": "a", "headers": {"Authorization": "Bearer x", "etag": "1"}, "api_key": "k", "ok": 1})
    assert meta == {"headers": {"etag": "1"}, "ok": 1}


def test_oversized_payload_truncated_and_flagged(db, src, monkeypatch, tmp_path):
    monkeypatch.setattr(raw_store, "MAX_RAW_BYTES", 1000)
    monkeypatch.setattr(raw_store, "INLINE_TEXT_LIMIT", 500)
    from unjobless.ingestion.filestore import FileStore

    r = store_item(db, src, item(text="x" * 5000), filestore=FileStore(str(tmp_path)))
    assert r.version.truncated is True
    assert r.version.byte_size == 1000
    assert len(r.version.raw_text) == 500
    assert r.version.blob_ref and (tmp_path / r.version.blob_ref).exists()


def test_cited_document_cannot_be_deleted(db, src):
    from unjobless.core.errors import Conflict
    from unjobless.db.models import JobVacancy, JobVacancySource

    r = store_item(db, src, item())
    v = JobVacancy(title="Data Intern", normalized_title="data intern")
    db.add(v)
    db.flush()
    db.add(JobVacancySource(vacancy_id=v.id, raw_document_id=r.document.id, source_id=src.id))
    db.flush()
    with pytest.raises(Conflict):
        raw_store.delete_document(db, r.document)
