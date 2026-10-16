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
    artifact = MarketDataSpec(
        artifact_id="hourly", semantics=MarketDataSemantics.from_mapping(declaration)
    )
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


@pytest.mark.parametrize("contract_type", [FeedSpec, MarketDataSemantics])
def test_grid_declaration_requires_versioned_opt_in(contract_type):
    with pytest.raises(ValueError, match="time_contract_version=2"):
        contract_type(bar_label="right")


@pytest.mark.parametrize("calendar, expected", [(None, None), ("24/7", "24/7")])
def test_semantics_calendar_resolution_matches_serialized_feed(calendar, expected):
    semantics = MarketDataSemantics(time_contract_version=2, calendar=calendar)
    assert semantics.resolve_calendar() == expected
    feed = MarketDataSpec(artifact_id="bars", semantics=semantics).to_feed_spec()
    assert feed.resolve_calendar() == semantics.resolve_calendar()
    assert semantics.resolve_calendar(calendar="NYSE") == "NYSE"
    with pytest.raises(ValueError, match="calendar"):
        semantics.resolve_calendar(calendar="")


def test_ignored_version_override_does_not_discard_calendar_disable():
    feed = FeedSpec(time_contract_version=2, calendar="NYSE")
    assert feed.with_overrides(time_contract_version=None, calendar=None).resolve_calendar() is None


def test_reset_to_inherited_calendar_survives_serialization():
    from ml4t.specs import UNSET_CALENDAR

    disabled = FeedSpec(time_contract_version=2, calendar=None)
    inherited = disabled.with_overrides(calendar=UNSET_CALENDAR)
    assert "calendar" not in inherited.to_dict()
    assert FeedSpec.from_mapping(inherited.to_dict()).resolve_calendar() == "NYSE"


def test_invalid_grid_does_not_replace_an_existing_persisted_contract(tmp_path):
    path = tmp_path / "bars.json"
    write_spec_payload(MarketDataSpec(artifact_id="existing"), path)
    before = path.read_bytes()
    payload = {
        "artifact_id": "new",
        "semantics": {
            "time_contract_version": 2,
            "timestamp_semantics": "bar_close",
            "bar_label": "left",
        },
    }
    with pytest.raises(ValueError, match="bar_close"):
        write_spec_payload(MarketDataSpec.from_mapping(payload), path)
    assert path.read_bytes() == before


def test_left_labeled_complete_bar_policy_is_preserved(tmp_path):
    spec = FeedSpec(
        time_contract_version=2,
        calendar="24/7",
        data_frequency="1h",
        bar_grid_anchor="session_open",
        bar_label="left",
        partial_bar_policy="exclude",
    )
    path = tmp_path / "feed.yaml"
    write_spec_payload(spec.to_dict(), path)
    restored = FeedSpec.from_mapping(read_spec_payload(path))
    assert restored.bar_label == "left"
    assert restored.partial_bar_policy == "exclude"
    assert restored.bar_grid_anchor == "session_open"


def test_version_override_migrates_legacy_declaration_without_losing_explicit_null():
    legacy = FeedSpec(calendar="NYSE")
    migrated = legacy.with_overrides(time_contract_version=2, calendar=None)
    assert migrated.time_contract_version == 2
    assert migrated.resolve_calendar() is None
    assert FeedSpec.from_mapping(migrated.to_dict()).resolve_calendar() is None
    assert legacy.resolve_calendar() == "NYSE"
