from fastapi.testclient import TestClient

from unjobless.api.app import create_app


def test_live():
    client = TestClient(create_app())
    r = client.get("/api/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert "x-request-id" in r.headers


def test_redaction_processor():
    from unjobless.core.logging import redact_processor

    out = redact_processor(None, "info", {"api_key": "sk-abc", "msg": "key sk-ant-ABCDEFGHIJKLMNOP leaked", "nested": {"password": "x"}})
    assert out["api_key"] == "[REDACTED]"
    assert "ABCDEFGHIJ" not in out["msg"]
    assert out["nested"]["password"] == "[REDACTED]"
