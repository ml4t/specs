from copy import deepcopy
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from ml4t.specs import (
    FeedSpec,
    MarketDataSemantics,
    MarketDataSpec,
    read_spec_payload,
    write_spec_payload,
)


@pytest.mark.parametrize("suffix", [".json", ".yaml"])
@pytest.mark.parametrize(
    "declaration, expected",
    [({}, "NYSE"), ({"calendar": None}, None), ({"calendar": "CME_Equity"}, "CME_Equity")],
)
def test_artifact_handoff_preserves_calendar_intent(tmp_path, suffix, declaration, expected):
    semantics = MarketDataSemantics.from_mapping({"time_contract_version": 2, **declaration})
    artifact = MarketDataSpec(artifact_id="bars", semantics=semantics)
    path = tmp_path / f"bars{suffix}"
    write_spec_payload(artifact, path)
    payload = read_spec_payload(path)
    assert ("calendar" in payload["semantics"]) == ("calendar" in declaration)
    loaded = MarketDataSpec.from_mapping(payload)
    feed = loaded.to_feed_spec()
    assert feed.resolve_calendar() == expected
    assert feed.resolve_calendar(calendar=None) is None
    assert feed.resolve_calendar(calendar="LSE") == "LSE"
    assert feed.to_dict().get("calendar") == declaration.get("calendar")
    assert ("calendar" in feed.to_dict()) == ("calendar" in declaration)


@pytest.mark.parametrize(
    "declaration, expected",
    [({}, "NYSE"), ({"calendar": None}, None), ({"calendar": "24/7"}, "24/7")],
)
def test_feed_copy_and_projection_do_not_reenable_disabled_calendars(declaration, expected):
    feed = FeedSpec(time_contract_version=2, **declaration)
    copies = [
        deepcopy(feed),
        replace(feed, price_col="mid"),
        FeedSpec.from_mapping(asdict(feed)),
        FeedSpec.from_any(SimpleNamespace(metadata=feed)),
        FeedSpec.from_mapping(feed.to_dict()),
    ]
    for copied in copies:
        assert copied.resolve_calendar() == expected
    cleared = feed.with_overrides(calendar=None)
    assert cleared.resolve_calendar() is None
    assert feed.resolve_calendar() == expected
    assert cleared.to_dict()["calendar"] is None


def test_legacy_null_remains_unspecified_until_explicit_migration():
    legacy = FeedSpec.from_mapping({"calendar": None})
    assert legacy.calendar is None
    assert legacy.resolve_calendar() == "NYSE"
    assert legacy.resolve_calendar(calendar=None) is None
    assert FeedSpec(calendar="NYSE").with_overrides(calendar=None).calendar == "NYSE"
    migrated = FeedSpec.from_mapping({**legacy.to_dict(), "time_contract_version": 2})
    assert migrated.resolve_calendar() is None
    assert FeedSpec(time_contract_version=2).resolve_calendar() == "NYSE"


def test_grid_declarations_survive_real_serialized_feed_handoff(tmp_path):
    declaration = {
        "time_contract_version": 2,
        "calendar": "NYSE",
        "data_frequency": "1h",
        "timezone": "America/New_York",
        "timestamp_semantics": "bar_close",
        "bar_grid_anchor": "session_open",
        "bar_label": "right",
        "partial_bar_policy": "include",
    }
    artifact = MarketDataSpec(artifact_id="hourly", semantics=MarketDataSemantics(**declaration))
    path = tmp_path / "hourly.json"
    write_spec_payload(artifact, path)
    feed = FeedSpec.from_mapping(read_spec_payload(path))
    for name, expected in declaration.items():
        assert getattr(feed, name) == expected
    assert {name: feed.to_dict()[name] for name in declaration} == declaration


@pytest.mark.parametrize(
    "changes, error",
    [
        ({"time_contract_version": 3}, "time_contract_version"),
        ({"time_contract_version": True}, "time_contract_version"),
        ({"calendar": ""}, "calendar"),
        ({"calendar": False}, "calendar"),
        ({"bar_grid_anchor": "first_observation"}, "bar_grid_anchor"),
        ({"bar_label": "middle"}, "bar_label"),
        ({"partial_bar_policy": "guess"}, "partial_bar_policy"),
        ({"bar_label": "left"}, "bar_close"),
        ({"timestamp_semantics": "session_label"}, "session_label"),
    ],
)
@pytest.mark.parametrize("contract_type", [FeedSpec, MarketDataSemantics])
def test_invalid_declarations_fail_without_mutating_input(changes, error, contract_type):
    payload = {
        "time_contract_version": 2,
        "calendar": "NYSE",
        "data_frequency": "1h",
        "timestamp_semantics": "bar_close",
        "bar_grid_anchor": "session_open",
        "bar_label": "right",
        "partial_bar_policy": "include",
        **changes,
    }
    original = deepcopy(payload)
    with pytest.raises(ValueError, match=error):
        contract_type.from_mapping(payload)
    assert payload == original


def test_legacy_artifact_serialization_does_not_acquire_new_time_defaults():
    payload = MarketDataSpec(artifact_id="legacy").to_dict()["semantics"]
    assert payload == {
        "data_frequency": None,
        "calendar": None,
        "timezone": None,
        "timestamp_semantics": None,
        "session_start_time": None,
        "bar_type": None,
    }


def test_window_units_do_not_alias_rows_sessions_and_elapsed_time():
    from ml4t.specs import WindowUnit

    assert {unit.value for unit in WindowUnit} == {
        "observation",
        "expected_bar",
        "session",
        "elapsed",
    }
    with pytest.raises(ValueError):
        WindowUnit("day")
