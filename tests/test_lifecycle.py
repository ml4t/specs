from __future__ import annotations

import json
import math
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast

import pytest
from jsonschema import ValidationError, validate

from ml4t.specs import (
    LIFECYCLE_V1,
    BarPayload,
    CallbackCardinality,
    CallbackExceptionSemantics,
    EventCompletion,
    FundingPayload,
    GapEvidence,
    HistoricalStrategyCompatibilityError,
    InformationField,
    LifecycleContract,
    LifecycleCountError,
    LifecyclePhase,
    LifecycleVersion,
    MarketEvent,
    MarketEventKind,
    ProhibitedFieldAccessError,
    QuotePayload,
    TradePayload,
    UnsupportedLifecycleVersionError,
    lifecycle_schema,
    negotiate_lifecycle_version,
    require_historical_strategy_compatibility,
)

EVENT_TIME = datetime(2026, 8, 8, 14, 30, tzinfo=UTC)
RECEIPT_TIME = EVENT_TIME + timedelta(milliseconds=4)


def event(
    kind: MarketEventKind = MarketEventKind.BAR,
    payload: Any | None = None,
    **overrides: Any,
) -> MarketEvent:
    payloads = {
        MarketEventKind.BAR: BarPayload(100, 102, 99, 101, 1_000),
        MarketEventKind.TRADE: TradePayload(101, 25),
        MarketEventKind.QUOTE: QuotePayload(100, 101, 10, 12),
        MarketEventKind.FUNDING: FundingPayload(0.0001),
    }
    values = {
        "version": LifecycleVersion.V1,
        "event_time": EVENT_TIME,
        "receipt_time": RECEIPT_TIME,
        "kind": kind,
        "completion": EventCompletion.COMPLETE,
        "source": "fixture",
        "asset": "SPY",
        "payload": payload if payload is not None else payloads[kind],
        "provider_sequence": 7,
    }
    values.update(overrides)
    return MarketEvent(**cast("Any", values))


def test_lifecycle_v1_is_complete_versioned_and_round_trips() -> None:
    assert LIFECYCLE_V1.version is LifecycleVersion.V1
    assert tuple(spec.phase for spec in LIFECYCLE_V1.phases) == tuple(LifecyclePhase)
    assert LIFECYCLE_V1.phase_spec(LifecyclePhase.MARKET_EVENT).callback == "on_data"
    assert LifecycleContract.from_mapping(LIFECYCLE_V1.to_dict()) == LIFECYCLE_V1
    assert lifecycle_schema()["properties"]["version"] == {"const": "1"}
    assert lifecycle_schema()["properties"]["phases"]["minItems"] == len(LifecyclePhase)


def test_lifecycle_materializes_collections_and_normalizes_enums() -> None:
    first = replace(
        LIFECYCLE_V1.phases[0],
        phase=cast("Any", "run_start"),
        visible_fields=cast("Any", []),
        cardinality=cast("Any", "exactly_once"),
        exception_semantics=cast("Any", "abort_before_side_effects"),
    )
    contract = LifecycleContract(cast("Any", "1"), cast("Any", [first, *LIFECYCLE_V1.phases[1:]]))

    assert first.visible_fields == ()
    assert contract.phases[0] == first
    assert LifecycleContract.from_mapping(contract.to_dict()) == contract


def test_lifecycle_schema_accepts_only_the_exact_versioned_contract() -> None:
    schema = lifecycle_schema()
    contract = LIFECYCLE_V1.to_dict()
    validate(contract, schema)

    malformed = LIFECYCLE_V1.to_dict()
    malformed["phases"][0]["callback"] = "renamed"
    with pytest.raises(ValidationError):
        validate(malformed, schema)

    malformed = LIFECYCLE_V1.to_dict()
    malformed["phases"][1]["visible_fields"] = ["current_close"]
    with pytest.raises(ValidationError):
        validate(malformed, schema)


def test_lifecycle_and_event_records_encode_as_json_and_restore() -> None:
    contracts = (
        (LIFECYCLE_V1, LifecycleContract.from_mapping),
        (event(metadata={"conditions": ["regular"]}), MarketEvent.from_mapping),
    )

    for original, restore in contracts:
        decoded = json.loads(json.dumps(original.to_dict()))
        assert decoded == original.to_dict()
        assert restore(decoded) == original


def test_opening_decisions_cannot_observe_current_close() -> None:
    initialization = LIFECYCLE_V1.phase_spec(LifecyclePhase.CAUSAL_INITIALIZATION)
    pre_open = LIFECYCLE_V1.phase_spec(LifecyclePhase.PRE_OPEN)
    opening = LIFECYCLE_V1.phase_spec(LifecyclePhase.OPENING_AUCTION)
    close = LIFECYCLE_V1.phase_spec(LifecyclePhase.CLOSE)

    pre_open.require_visible(InformationField.PRIOR_COMPLETED_DATA)
    opening.require_visible(InformationField.OFFICIAL_OPEN)
    close.require_visible(InformationField.CURRENT_CLOSE)
    with pytest.raises(ProhibitedFieldAccessError, match="current_close.*pre_open"):
        pre_open.require_visible(InformationField.CURRENT_CLOSE)
    assert initialization.intents_allowed
    assert pre_open.intents_allowed
    assert not LIFECYCLE_V1.phase_spec(LifecyclePhase.FILL_RECONCILIATION).intents_allowed


def test_callback_count_and_exception_contracts() -> None:
    start = LIFECYCLE_V1.phase_spec(LifecyclePhase.RUN_START)
    intrabar = LIFECYCLE_V1.phase_spec(LifecyclePhase.INTRABAR)
    end = LIFECYCLE_V1.phase_spec(LifecyclePhase.RUN_END)

    assert start.cardinality is CallbackCardinality.EXACTLY_ONCE
    assert start.exception_semantics is CallbackExceptionSemantics.ABORT_BEFORE_SIDE_EFFECTS
    assert intrabar.exception_semantics is CallbackExceptionSemantics.ROLLBACK_AND_ABORT
    assert end.exception_semantics is CallbackExceptionSemantics.CLEANUP_AND_RERAISE
    start.validate_count(1)
    intrabar.validate_count(3, event_count=3)
    with pytest.raises(LifecycleCountError, match="expected 1.*observed 0"):
        start.validate_count(0)
    with pytest.raises(ValueError, match="event_count"):
        intrabar.validate_count(0)
    with pytest.raises(LifecycleCountError, match="expected 2.*observed 1"):
        intrabar.validate_count(1, event_count=2)


def test_contract_rejects_missing_or_misordered_phases() -> None:
    with pytest.raises(ValueError, match="complete, unique, and in contract order"):
        LifecycleContract(LifecycleVersion.V1, LIFECYCLE_V1.phases[:-1])
    with pytest.raises(ValueError, match="callback"):
        replace(LIFECYCLE_V1.phases[0], callback="")
    with pytest.raises(ValueError, match="non-negative"):
        replace(LIFECYCLE_V1.phases[0], causal_rank=-1)
    with pytest.raises(TypeError, match="integer"):
        replace(LIFECYCLE_V1.phases[0], causal_rank=cast("Any", True))
    with pytest.raises(TypeError, match="intents_allowed"):
        replace(LIFECYCLE_V1.phases[0], intents_allowed=cast("Any", 1))


@pytest.mark.parametrize("raw", [[], "phases", 1])
def test_contract_mapping_rejects_invalid_phase_collections(raw: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        LifecycleContract.from_mapping({"version": "1", "phases": raw})


def test_version_negotiation_fails_before_state_changes() -> None:
    state: list[str] = []
    assert negotiate_lifecycle_version("1") is LifecycleVersion.V1
    assert negotiate_lifecycle_version(LifecycleVersion.V1) is LifecycleVersion.V1

    with pytest.raises(UnsupportedLifecycleVersionError) as captured:
        negotiated = negotiate_lifecycle_version("2", LifecyclePhase.PRE_OPEN)
        state.append(negotiated.value)

    assert state == []
    assert captured.value.requested == "2"
    assert captured.value.required_phase is LifecyclePhase.PRE_OPEN
    assert captured.value.supported_versions == ("1",)
    assert "pre_open" in str(captured.value)


def test_historical_strategy_compatibility_is_explicit() -> None:
    require_historical_strategy_compatibility("Portable", ["on_prepare", "on_data"])

    with pytest.raises(HistoricalStrategyCompatibilityError) as captured:
        require_historical_strategy_compatibility("Legacy", ["on_historical_data"])

    assert captured.value.strategy == "Legacy"
    assert captured.value.callback == "on_historical_data"
    assert captured.value.required_phase is LifecyclePhase.CAUSAL_INITIALIZATION
    assert captured.value.supported_versions == ("1",)
    with pytest.raises(TypeError, match="sequence"):
        require_historical_strategy_compatibility("Legacy", "legacy_on_historical_data_hook")


@pytest.mark.parametrize("kind", list(MarketEventKind))
def test_market_event_variants_round_trip(kind: MarketEventKind) -> None:
    original = event(
        kind,
        metadata={"venue": "fixture", "conditions": ["regular"], "latency_ms": 0.5},
    )
    restored = MarketEvent.from_mapping(original.to_dict())

    assert restored == original
    assert restored.event_time.tzinfo is UTC
    assert restored.receipt_time.tzinfo is UTC
    assert restored.metadata == {
        "venue": "fixture",
        "conditions": ("regular",),
        "latency_ms": 0.5,
    }


def test_market_event_serialization_does_not_share_nested_metadata() -> None:
    original = event(metadata={"conditions": ["regular"]})
    record = original.to_dict()

    record["metadata"]["conditions"].append("late")

    assert original.metadata == {"conditions": ("regular",)}
    with pytest.raises(TypeError):
        cast("dict[str, Any]", original.metadata)["venue"] = "late"
    with pytest.raises(AttributeError):
        cast("list[str]", original.metadata["conditions"]).append("late")
    with pytest.raises(TypeError):
        hash(original)


def test_market_event_accepts_gap_evidence_without_sequence() -> None:
    gap = GapEvidence(True, "provider sequence skipped", "10", "12")
    original = event(provider_sequence=None, gap=gap)

    assert MarketEvent.from_mapping(original.to_dict()) == original
    assert GapEvidence.from_mapping(
        {
            "detected": False,
            "reason": "provider has no sequence",
            "previous_sequence": None,
            "current_sequence": None,
        }
    ) == GapEvidence(False, "provider has no sequence")

    integer_gap = GapEvidence(True, "provider sequence skipped", 10, 12)
    assert (
        GapEvidence.from_mapping(
            {
                "detected": True,
                "reason": "provider sequence skipped",
                "previous_sequence": 10,
                "current_sequence": 12,
            }
        )
        == integer_gap
    )


@pytest.mark.parametrize(
    ("overrides", "error", "message"),
    [
        ({"detected": True}, ValueError, "requires previous_sequence"),
        ({"detected": cast("Any", 1)}, TypeError, "detected must be a bool"),
        ({"previous_sequence": True}, TypeError, "previous_sequence"),
        ({"current_sequence": 1.5}, TypeError, "current_sequence"),
        ({"previous_sequence": ""}, ValueError, "must not be empty"),
        ({"current_sequence": -1}, ValueError, "non-negative"),
    ],
)
def test_gap_evidence_validates_sequence_identity(
    overrides: dict[str, Any], error: type[Exception], message: str
) -> None:
    values: dict[str, Any] = {
        "detected": False,
        "reason": "provider sequence state",
        "previous_sequence": None,
        "current_sequence": None,
    }
    values.update(overrides)
    with pytest.raises(error, match=message):
        GapEvidence(**values)


def test_market_event_normalizes_string_enums() -> None:
    original = event(
        version=cast("Any", "1"),
        kind=cast("Any", "bar"),
        completion=cast("Any", "evolving"),
    )

    assert original.version is LifecycleVersion.V1
    assert original.kind is MarketEventKind.BAR
    assert original.completion is EventCompletion.EVOLVING


@pytest.mark.parametrize(
    ("overrides", "error", "message"),
    [
        ({"version": cast("Any", "2")}, UnsupportedLifecycleVersionError, "version"),
        ({"event_time": datetime(2026, 8, 8)}, ValueError, "event_time"),
        (
            {"receipt_time": datetime(2026, 8, 8, tzinfo=timezone(timedelta(hours=1)))},
            ValueError,
            "receipt_time",
        ),
        (
            {"receipt_time": EVENT_TIME - timedelta(microseconds=1)},
            ValueError,
            "must not precede",
        ),
        ({"event_time": cast("Any", "now")}, TypeError, "event_time"),
        ({"source": ""}, ValueError, "source"),
        ({"asset": "  "}, ValueError, "asset"),
        ({"payload": TradePayload(100, 1)}, TypeError, "BarPayload"),
        ({"provider_sequence": None}, ValueError, "gap evidence"),
        ({"provider_sequence": True}, TypeError, "provider_sequence"),
        ({"provider_sequence": 1.5}, TypeError, "provider_sequence"),
        ({"provider_sequence": ""}, ValueError, "must not be empty"),
        ({"provider_sequence": -1}, ValueError, "non-negative"),
        (
            {"gap": cast("Any", {"detected": False, "reason": "not validated"})},
            TypeError,
            "GapEvidence",
        ),
    ],
)
def test_market_event_rejects_invalid_identity(
    overrides: dict[str, Any], error: type[Exception], message: str
) -> None:
    records: list[MarketEvent] = []
    with pytest.raises(error, match=message):
        records.append(event(**overrides))
    assert records == []


def test_market_event_mapping_rejects_malformed_nested_values() -> None:
    payload = event().to_dict()
    payload["payload"] = []
    with pytest.raises(TypeError, match="payload"):
        MarketEvent.from_mapping(payload)

    payload = event().to_dict()
    payload["gap"] = []
    with pytest.raises(TypeError, match="gap"):
        MarketEvent.from_mapping(payload)

    payload = event().to_dict()
    payload["metadata"] = []
    with pytest.raises(TypeError, match="metadata"):
        MarketEvent.from_mapping(payload)


def test_market_events_accept_zero_and_negative_instrument_prices() -> None:
    negative_bar = BarPayload(-10, -5, -40, -37.63, 1_000)

    assert event(payload=negative_bar).payload == negative_bar
    assert TradePayload(0, 1).price == 0
    assert QuotePayload(-2, -1, 1, 1).bid == -2


@pytest.mark.parametrize(
    "metadata",
    [
        {"value": math.nan},
        {"timestamp": EVENT_TIME},
        {1: "not a string key"},
        ["not", "a", "mapping"],
    ],
)
def test_market_event_rejects_non_json_metadata(metadata: object) -> None:
    with pytest.raises((TypeError, ValueError), match="metadata"):
        event(metadata=metadata)


@pytest.mark.parametrize(
    ("factory", "error", "message"),
    [
        (lambda: GapEvidence(False, ""), ValueError, "reason"),
        (lambda: BarPayload(100, 99, 98, 99, 1), ValueError, "high"),
        (lambda: BarPayload(100, 101, 100, 99, 1), ValueError, "low"),
        (lambda: BarPayload(100, 101, 99, 100, -1), ValueError, "volume"),
        (lambda: BarPayload(100, math.inf, 99, 100, 1), ValueError, "finite"),
        (lambda: BarPayload(100, 101, 99, 100, cast("Any", True)), TypeError, "number"),
        (lambda: TradePayload(1, -1), ValueError, "size"),
        (lambda: QuotePayload(2, 1, 1, 1), ValueError, "ask"),
        (lambda: QuotePayload(1, 2, -1, 1), ValueError, "sizes"),
        (lambda: QuotePayload(1, 2, 1, -1), ValueError, "sizes"),
        (lambda: FundingPayload(float("nan")), ValueError, "finite"),
    ],
)
def test_payload_validation(factory: Any, error: type[Exception], message: str) -> None:
    with pytest.raises(error, match=message):
        factory()
