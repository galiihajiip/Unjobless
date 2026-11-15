import pytest

from unjobless.core.errors import InvalidTransition, ValidationFailed
from unjobless.domain.enums import PolicyStatus, SourceState
from unjobless.sources import service
from unjobless.sources.contract import Connector, ConnectorInfo
from unjobless.sources.registry import all_connectors, get_connector_class, register

pytestmark = pytest.mark.db


def mock_source(db, key="mock-1", **kw):
    return service.create_source(db, key=key, name="Mock", connector_type="mock", config={"items": []}, **kw)


def test_new_source_defaults_disabled_and_unreviewed(db):
    s = mock_source(db)
    assert s.state == SourceState.DISABLED
    assert s.policy_status == PolicyStatus.UNREVIEWED
    ok, reason = service.can_collect(db, s)
    assert not ok and "disabled" in reason


def test_cannot_enable_without_policy_review(db):
    s = mock_source(db)
    with pytest.raises(ValidationFailed) as e:
        service.change_state(db, s, SourceState.ENABLED)
    assert e.value.code == "policy_review_required"


def test_review_enable_pause_resume_disable(db):
    s = mock_source(db)
    service.review_policy(db, s, decision=PolicyStatus.APPROVED, terms_notes="internal mock")
    service.change_state(db, s, SourceState.ENABLED)
    assert s.next_run_at is not None
    assert service.can_collect(db, s) == (True, None)
    service.change_state(db, s, SourceState.PAUSED)
    assert service.can_collect(db, s)[0] is False
    service.change_state(db, s, SourceState.ENABLED)
    service.change_state(db, s, SourceState.DISABLED)
    with pytest.raises(InvalidTransition):
        service.change_state(db, s, SourceState.PAUSED)


def test_denied_policy_disables_source(db):
    s = mock_source(db)
    service.review_policy(db, s, decision=PolicyStatus.APPROVED)
    service.change_state(db, s, SourceState.ENABLED)
    service.review_policy(db, s, decision=PolicyStatus.DENIED, reviewer_note="ToS prohibits scraping")
    assert s.state == SourceState.DISABLED


def test_invalid_config_rejected(db):
    with pytest.raises(ValidationFailed):
        service.create_source(db, key="bad", name="Bad", connector_type="mock", config={"unknown_field": 1})


def test_min_schedule_interval(db):
    with pytest.raises(ValidationFailed):
        mock_source(db, schedule_interval_seconds=60)


def test_exclusion_blocks_and_disables(db):
    s = mock_source(db, domain="jobs.example.com")
    service.review_policy(db, s, decision=PolicyStatus.APPROVED)
    service.change_state(db, s, SourceState.ENABLED)
    service.add_exclusion(db, "example.com", "owner request")
    assert s.state == SourceState.DISABLED
    with pytest.raises(ValidationFailed):
        mock_source(db, key="other", domain="careers.example.com")
    assert service.is_excluded(db, "https://sub.example.com/x") is not None
    assert service.is_excluded(db, "https://notexample.com/") is None


def test_internal_connectors_not_user_creatable(db):
    with pytest.raises(ValidationFailed):
        service.create_source(db, key="x", name="x", connector_type="user_paste")


def test_new_connector_registers_without_core_changes(db):
    from unjobless.domain.enums import CollectionMethod, SourceCategory

    @register
    class ExtraConnector(Connector):
        info = ConnectorInfo(
            type="extra_test",
            name="Extra",
            category=SourceCategory.RSS_FEED,
            collection_method=CollectionMethod.RSS,
            description="test",
            documentation_url=None,
            terms_url=None,
        )

        def collect(self, ctx):
            yield from ()

    assert get_connector_class("extra_test") is ExtraConnector
    assert any(c.type == "extra_test" for c in all_connectors())
    s = service.create_source(db, key="extra", name="Extra", connector_type="extra_test")
    assert s.category == SourceCategory.RSS_FEED
