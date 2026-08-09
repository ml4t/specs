from __future__ import annotations

import json
import math
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ml4t.specs import (
    AssetTarget,
    BarPathPolicy,
    CanonicalChildOrderIntent,
    CanonicalTargetIntent,
    EvaluationMode,
    ExecutionBehavior,
    ExecutionCapability,
    ExecutionPolicy,
    ExitReason,
    FillEligibility,
    IntentReason,
    LifecyclePhase,
    LifecycleVersion,
    OrderParameters,
    OrderSide,
    OrderType,
    PositionActionType,
    PositionRuleDefinition,
    PositionRulePolicy,
    PositionRuleState,
    PositionRuleType,
    ResidualPolicy,
    RoundingPolicy,
    RuleActivation,
    RuleComposition,
    SessionPolicy,
    TargetMeasure,
    TimeInForce,
    canonical_intent_fixture,
    compare_child_intents,
    compare_target_intents,
    validate_child_against_policy,
    validate_child_lineage,
)

DECISION_TIME = datetime(2026, 8, 8, 13, 0, tzinfo=UTC)
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "canonical_intent_v1.json"


def target(**overrides: Any) -> CanonicalTargetIntent:
    values: dict[str, Any] = {
        "intent_id": "target-1",
        "decision_time": DECISION_TIME,
        "information_cutoff": DECISION_TIME - timedelta(seconds=1),
        "effective_session": date(2026, 8, 10),
        "effective_phase": LifecyclePhase.PRE_OPEN,
        "targets": (AssetTarget("SPY", TargetMeasure.WEIGHT, 0.5),),
        "idempotency_key": "target-key",
        "measure": TargetMeasure.WEIGHT,
        "cash_buffer": 0.05,
        "rounding": RoundingPolicy.TOWARD_ZERO,
        "residual": ResidualPolicy.KEEP_CASH,
        "reason": IntentReason.REBALANCE,
        "lifecycle_version": LifecycleVersion.V1,
    }
    values.update(overrides)
    return CanonicalTargetIntent(**cast("Any", values))


def child(**overrides: Any) -> CanonicalChildOrderIntent:
    values = {
        "child_intent_id": "child-1",
        "target_intent_id": "target-1",
        "idempotency_key": "child-key",
        "asset": "SPY",
        "side": OrderSide.BUY,
        "quantity": 10.0,
        "order_type": OrderType.MARKET,
        "parameters": OrderParameters(),
        "effective_session": date(2026, 8, 10),
        "eligibility_phase": LifecyclePhase.PRE_OPEN,
        "fill_eligibility": FillEligibility.OPENING_AUCTION,
        "time_in_force": TimeInForce.OPG,
        "session_policy": SessionPolicy.REGULAR,
        "capabilities": (ExecutionCapability.OPENING_AUCTION,),
        "reason": IntentReason.REBALANCE,
        "lifecycle_version": LifecycleVersion.V1,
    }
    values.update(overrides)
    return CanonicalChildOrderIntent(**cast("Any", values))


def execution_policy(**overrides: Any) -> ExecutionPolicy:
    values = {
        "policy_id": "execution-1",
        "market_fill_phase": LifecyclePhase.OPENING_AUCTION,
        "opening_auction": ExecutionBehavior.BROKER_NATIVE,
        "moc": ExecutionBehavior.BROKER_NATIVE,
        "limit": ExecutionBehavior.BROKER_NATIVE,
        "stop": ExecutionBehavior.CLIENT,
        "stop_limit": ExecutionBehavior.CLIENT,
        "trailing": ExecutionBehavior.CLIENT,
        "contingent": ExecutionBehavior.DISABLED,
        "fee_bps": 1.0,
        "slippage_bps": 2.0,
        "spread_bps": 3.0,
        "impact_bps": 4.0,
        "latency_ms": 5.0,
        "liquidity_fraction": 0.1,
        "allow_partial_fills": True,
        "bar_path": BarPathPolicy.REJECT_AMBIGUOUS,
    }
    values.update(overrides)
    return ExecutionPolicy(**cast("Any", values))


def rule_state(**overrides: Any) -> PositionRuleState:
    values = {
        "policy_id": "rules-1",
        "asset": "SPY",
        "activation": RuleActivation.ACTIVE,
        "entry_time": DECISION_TIME,
        "entry_price": 100.0,
        "entry_quantity": 10.0,
        "high_water_mark": 110.0,
        "low_water_mark": 95.0,
        "max_favorable_excursion": 0.1,
        "max_adverse_excursion": -0.05,
        "remaining_exit_quantity": 10.0,
        "idempotency_key": "rule-state-key",
        "action": PositionActionType.HOLD,
        "exit_reason": ExitReason.NONE,
        "evaluation_mode": EvaluationMode.CLIENT,
    }
    values.update(overrides)
    return PositionRuleState(**cast("Any", values))


def test_golden_fixture_loads_unchanged_and_round_trips() -> None:
    fixture = canonical_intent_fixture()
    assert fixture == json.loads(FIXTURE_PATH.read_text())
    assert json.loads(json.dumps(fixture)) == fixture
    restored_target = CanonicalTargetIntent.from_mapping(fixture["target"])
    restored_child = CanonicalChildOrderIntent.from_mapping(fixture["child"])

    assert restored_target.to_dict() == fixture["target"]
    assert restored_child.to_dict() == fixture["child"]
    validate_child_lineage(restored_target, restored_child)


@given(
    values=st.lists(
        st.floats(allow_nan=False, allow_infinity=False, width=64),
        min_size=1,
        max_size=8,
    ),
    measure=st.sampled_from(TargetMeasure),
)
def test_generated_target_intents_round_trip(values: list[float], measure: TargetMeasure) -> None:
    original = target(
        measure=measure,
        targets=tuple(
            AssetTarget(f"ASSET-{index}", measure, value) for index, value in enumerate(values)
        ),
    )
    restored = CanonicalTargetIntent.from_mapping(original.to_dict())

    assert restored == original
    assert tuple(item.value for item in restored.targets) == tuple(values)


def test_target_round_trip_and_optional_position_rule_policy() -> None:
    original = target(position_rule_policy_id="rules-1")

    assert CanonicalTargetIntent.from_mapping(original.to_dict()) == original


def test_target_order_is_canonical_by_asset() -> None:
    first = target(
        targets=(
            AssetTarget("SPY", TargetMeasure.WEIGHT, 0.5),
            AssetTarget("QQQ", TargetMeasure.WEIGHT, 0.4),
        )
    )
    second = target(targets=tuple(reversed(first.targets)))

    assert first == second
    assert tuple(item.asset for item in first.targets) == ("QQQ", "SPY")
    assert compare_target_intents(first, second).equivalent


def test_target_materializes_single_pass_iterables_before_validation() -> None:
    valid_targets = (
        AssetTarget(asset, TargetMeasure.WEIGHT, value) for asset, value in [("SPY", 1)]
    )
    original = target(targets=valid_targets)

    assert original.targets == (AssetTarget("SPY", TargetMeasure.WEIGHT, 1),)
    with pytest.raises(ValueError, match="measure"):
        target(targets=(AssetTarget("SPY", TargetMeasure.QUANTITY, 1) for _ in range(1)))
    with pytest.raises(TypeError, match="iterable"):
        target(targets=cast("Any", "SPY"))


@pytest.mark.parametrize(
    ("overrides", "error", "message"),
    [
        ({"intent_id": ""}, ValueError, "intent_id"),
        ({"idempotency_key": " "}, ValueError, "idempotency_key"),
        ({"decision_time": datetime(2026, 8, 8)}, ValueError, "decision_time"),
        (
            {"information_cutoff": datetime(2026, 8, 8, tzinfo=timezone(timedelta(hours=1)))},
            ValueError,
            "information_cutoff",
        ),
        ({"information_cutoff": DECISION_TIME + timedelta(seconds=1)}, ValueError, "must not"),
        ({"effective_session": DECISION_TIME}, TypeError, "date"),
        ({"effective_session": cast("Any", "2026-08-10")}, TypeError, "date"),
        ({"effective_phase": cast("Any", "run_start")}, ValueError, "does not allow"),
        ({"targets": ()}, ValueError, "must not be empty"),
        (
            {
                "targets": (
                    AssetTarget("SPY", TargetMeasure.WEIGHT, 0.5),
                    AssetTarget("SPY", TargetMeasure.WEIGHT, 0.4),
                )
            },
            ValueError,
            "each asset once",
        ),
        (
            {"targets": (AssetTarget("SPY", TargetMeasure.QUANTITY, 1),)},
            ValueError,
            "measure",
        ),
        ({"cash_buffer": cast("Any", True)}, TypeError, "number"),
        ({"cash_buffer": math.inf}, ValueError, "finite"),
        ({"cash_buffer": -0.1}, ValueError, r"\[0, 1\)"),
        ({"cash_buffer": 1.0}, ValueError, r"\[0, 1\)"),
        ({"position_rule_policy_id": ""}, ValueError, "position_rule_policy_id"),
        ({"lifecycle_version": cast("Any", "2")}, ValueError, "version"),
    ],
)
def test_target_rejection_is_atomic(
    overrides: dict[str, Any], error: type[Exception], message: str
) -> None:
    registry: list[CanonicalTargetIntent] = []
    with pytest.raises(error, match=message):
        registry.append(target(**overrides))
    assert registry == []


@pytest.mark.parametrize("value", ["", " "])
def test_asset_target_rejects_empty_asset(value: str) -> None:
    with pytest.raises(ValueError, match="asset"):
        AssetTarget(value, TargetMeasure.WEIGHT, 0.5)


@pytest.mark.parametrize("value", [math.inf, math.nan])
def test_asset_target_rejects_nonfinite_value(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        AssetTarget("SPY", TargetMeasure.WEIGHT, value)


def test_asset_target_mapping_and_invalid_target_collections() -> None:
    asset_target = AssetTarget("SPY", TargetMeasure.WEIGHT, 0.5)
    assert AssetTarget.from_mapping(asset_target.to_dict()) == asset_target
    record = target().to_dict()
    for invalid in ("targets", 1):
        record["targets"] = invalid
        with pytest.raises(TypeError, match="targets"):
            CanonicalTargetIntent.from_mapping(record)

    record = target().to_dict()
    record["targets"] = [["SPY", "weight", 0.5]]
    with pytest.raises(TypeError, match="each target"):
        CanonicalTargetIntent.from_mapping(record)


@pytest.mark.parametrize(
    ("order_type", "parameters", "capabilities"),
    [
        (OrderType.MARKET, OrderParameters(), ()),
        (
            OrderType.LIMIT,
            OrderParameters(limit_price=100),
            (ExecutionCapability.LIMIT,),
        ),
        (OrderType.STOP, OrderParameters(stop_price=99), (ExecutionCapability.STOP,)),
        (
            OrderType.STOP_LIMIT,
            OrderParameters(stop_price=99, limit_price=98),
            (ExecutionCapability.STOP_LIMIT,),
        ),
        (
            OrderType.TRAILING_STOP,
            OrderParameters(trail_amount=2),
            (ExecutionCapability.TRAILING_STOP,),
        ),
        (
            OrderType.TRAILING_STOP,
            OrderParameters(trail_percent=0.02),
            (ExecutionCapability.TRAILING_STOP,),
        ),
        (OrderType.MOC, OrderParameters(), (ExecutionCapability.CLOSE_AUCTION,)),
    ],
)
def test_child_order_types_round_trip(
    order_type: OrderType,
    parameters: OrderParameters,
    capabilities: tuple[ExecutionCapability, ...],
) -> None:
    eligibility = (
        FillEligibility.CLOSE_AUCTION if order_type is OrderType.MOC else FillEligibility.NEXT_PHASE
    )
    time_in_force = TimeInForce.CLS if order_type is OrderType.MOC else TimeInForce.DAY
    original = child(
        order_type=order_type,
        parameters=parameters,
        fill_eligibility=eligibility,
        time_in_force=time_in_force,
        capabilities=capabilities,
    )

    assert CanonicalChildOrderIntent.from_mapping(original.to_dict()) == original


@pytest.mark.parametrize(
    ("overrides", "capability"),
    [
        (
            {
                "time_in_force": TimeInForce.OPG,
                "fill_eligibility": FillEligibility.OPENING_AUCTION,
            },
            ExecutionCapability.OPENING_AUCTION,
        ),
        (
            {
                "time_in_force": TimeInForce.CLS,
                "fill_eligibility": FillEligibility.CLOSE_AUCTION,
            },
            ExecutionCapability.CLOSE_AUCTION,
        ),
        (
            {"fill_eligibility": FillEligibility.OPENING_AUCTION},
            ExecutionCapability.OPENING_AUCTION,
        ),
        (
            {"fill_eligibility": FillEligibility.CLOSE_AUCTION},
            ExecutionCapability.CLOSE_AUCTION,
        ),
    ],
)
def test_auction_semantics_require_matching_capability(
    overrides: dict[str, Any], capability: ExecutionCapability
) -> None:
    values: dict[str, Any] = {
        "time_in_force": TimeInForce.DAY,
        "fill_eligibility": FillEligibility.NEXT_PHASE,
        "capabilities": (),
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=capability.value):
        child(**values)

    values["capabilities"] = (capability,)
    assert child(**values).capabilities == (capability,)


def test_child_capability_order_is_canonical() -> None:
    capabilities = (ExecutionCapability.PARTIAL_FILL, ExecutionCapability.CONTINGENT)
    first = child(
        fill_eligibility=FillEligibility.NEXT_PHASE,
        time_in_force=TimeInForce.DAY,
        capabilities=capabilities,
    )
    second = child(
        fill_eligibility=FillEligibility.NEXT_PHASE,
        time_in_force=TimeInForce.DAY,
        capabilities=tuple(reversed(capabilities)),
    )

    assert first == second
    assert first.capabilities == (
        ExecutionCapability.CONTINGENT,
        ExecutionCapability.PARTIAL_FILL,
    )
    assert compare_child_intents(first, second).equivalent


@pytest.mark.parametrize(
    ("overrides", "error", "message"),
    [
        ({"child_intent_id": ""}, ValueError, "child_intent_id"),
        ({"target_intent_id": ""}, ValueError, "target_intent_id"),
        ({"idempotency_key": ""}, ValueError, "idempotency_key"),
        ({"asset": ""}, ValueError, "asset"),
        ({"quantity": 0}, ValueError, "positive and unsigned"),
        ({"quantity": -1}, ValueError, "positive and unsigned"),
        ({"quantity": cast("Any", True)}, TypeError, "number"),
        ({"effective_session": DECISION_TIME}, TypeError, "effective_session"),
        ({"effective_session": cast("Any", "2026-08-10")}, TypeError, "effective_session"),
        ({"eligibility_phase": LifecyclePhase.RUN_END}, ValueError, "does not allow"),
        (
            {"order_type": OrderType.LIMIT, "parameters": OrderParameters(), "capabilities": ()},
            ValueError,
            "requires capability",
        ),
        (
            {
                "capabilities": (
                    ExecutionCapability.OPENING_AUCTION,
                    ExecutionCapability.OPENING_AUCTION,
                )
            },
            ValueError,
            "unique",
        ),
        (
            {
                "eligibility_phase": LifecyclePhase.CLOSE,
                "fill_eligibility": FillEligibility.CURRENT_PHASE,
                "time_in_force": TimeInForce.DAY,
                "capabilities": (),
            },
            ValueError,
            "current_close",
        ),
        (
            {
                "eligibility_phase": LifecyclePhase.CLOSE,
                "order_type": OrderType.MOC,
                "fill_eligibility": FillEligibility.CLOSE_AUCTION,
                "time_in_force": TimeInForce.CLS,
                "capabilities": (ExecutionCapability.CLOSE_AUCTION,),
            },
            ValueError,
            "current_close",
        ),
        (
            {
                "eligibility_phase": LifecyclePhase.OPENING_AUCTION,
                "fill_eligibility": FillEligibility.OPENING_AUCTION,
                "time_in_force": TimeInForce.OPG,
                "capabilities": (ExecutionCapability.OPENING_AUCTION,),
            },
            ValueError,
            "current_open",
        ),
        (
            {
                "eligibility_phase": LifecyclePhase.OPENING_AUCTION,
                "fill_eligibility": FillEligibility.CURRENT_PHASE,
                "time_in_force": TimeInForce.IOC,
                "capabilities": (),
            },
            ValueError,
            "current_open",
        ),
        (
            {
                "order_type": OrderType.LIMIT,
                "parameters": OrderParameters(),
                "capabilities": (
                    ExecutionCapability.LIMIT,
                    ExecutionCapability.OPENING_AUCTION,
                ),
            },
            ValueError,
            "limit_price",
        ),
        (
            {
                "order_type": OrderType.STOP,
                "parameters": OrderParameters(),
                "capabilities": (
                    ExecutionCapability.STOP,
                    ExecutionCapability.OPENING_AUCTION,
                ),
            },
            ValueError,
            "stop_price",
        ),
        (
            {
                "order_type": OrderType.STOP_LIMIT,
                "parameters": OrderParameters(stop_price=99),
                "capabilities": (
                    ExecutionCapability.STOP_LIMIT,
                    ExecutionCapability.OPENING_AUCTION,
                ),
            },
            ValueError,
            "stop_price and limit_price",
        ),
        (
            {
                "order_type": OrderType.TRAILING_STOP,
                "parameters": OrderParameters(),
                "capabilities": (
                    ExecutionCapability.TRAILING_STOP,
                    ExecutionCapability.OPENING_AUCTION,
                ),
            },
            ValueError,
            "exactly one",
        ),
        (
            {
                "order_type": OrderType.TRAILING_STOP,
                "parameters": OrderParameters(trail_amount=1, trail_percent=0.01),
                "capabilities": (
                    ExecutionCapability.TRAILING_STOP,
                    ExecutionCapability.OPENING_AUCTION,
                ),
            },
            ValueError,
            "exactly one",
        ),
        ({"lifecycle_version": cast("Any", "2")}, ValueError, "version"),
    ],
)
def test_child_rejection_is_atomic(
    overrides: dict[str, Any], error: type[Exception], message: str
) -> None:
    registry: list[CanonicalChildOrderIntent] = []
    with pytest.raises(error, match=message):
        registry.append(child(**overrides))
    assert registry == []


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {
                "fill_eligibility": FillEligibility.NEXT_PHASE,
                "time_in_force": TimeInForce.OPG,
                "capabilities": (ExecutionCapability.OPENING_AUCTION,),
            },
            "opg time in force requires opening_auction",
        ),
        (
            {
                "order_type": OrderType.MOC,
                "fill_eligibility": FillEligibility.OPENING_AUCTION,
                "time_in_force": TimeInForce.OPG,
                "capabilities": (
                    ExecutionCapability.CLOSE_AUCTION,
                    ExecutionCapability.OPENING_AUCTION,
                ),
            },
            "moc order requires close_auction",
        ),
        (
            {
                "fill_eligibility": FillEligibility.OPENING_AUCTION,
                "time_in_force": TimeInForce.CLS,
                "capabilities": (
                    ExecutionCapability.CLOSE_AUCTION,
                    ExecutionCapability.OPENING_AUCTION,
                ),
            },
            "cls time in force requires close_auction",
        ),
        (
            {
                "fill_eligibility": FillEligibility.NEXT_PHASE,
                "time_in_force": TimeInForce.IOC,
                "capabilities": (),
            },
            "ioc time in force requires current_phase",
        ),
        (
            {
                "fill_eligibility": FillEligibility.NEXT_PHASE,
                "time_in_force": TimeInForce.FOK,
                "capabilities": (),
            },
            "fok time in force requires current_phase",
        ),
    ],
)
def test_child_rejects_contradictory_execution_fields(
    overrides: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        child(**overrides)


@pytest.mark.parametrize("time_in_force", [TimeInForce.IOC, TimeInForce.FOK])
def test_evolving_market_events_support_immediate_time_in_force(
    time_in_force: TimeInForce,
) -> None:
    order = child(
        eligibility_phase=LifecyclePhase.MARKET_EVENT,
        fill_eligibility=FillEligibility.CURRENT_PHASE,
        time_in_force=time_in_force,
        capabilities=(),
    )

    assert order.time_in_force is time_in_force


@pytest.mark.parametrize(
    ("order_type", "parameters", "capabilities", "irrelevant"),
    [
        (OrderType.MARKET, OrderParameters(stop_price=99), (), "stop_price"),
        (
            OrderType.LIMIT,
            OrderParameters(limit_price=100, trail_percent=0.5),
            (ExecutionCapability.LIMIT,),
            "trail_percent",
        ),
    ],
)
def test_child_rejects_irrelevant_order_parameters(
    order_type: OrderType,
    parameters: OrderParameters,
    capabilities: tuple[ExecutionCapability, ...],
    irrelevant: str,
) -> None:
    with pytest.raises(ValueError, match=irrelevant):
        child(
            order_type=order_type,
            parameters=parameters,
            fill_eligibility=FillEligibility.NEXT_PHASE,
            time_in_force=TimeInForce.DAY,
            capabilities=capabilities,
        )


@pytest.mark.parametrize(
    ("parameters", "error", "message"),
    [
        ({"limit_price": math.inf}, ValueError, "finite"),
        ({"stop_price": math.nan}, ValueError, "finite"),
        ({"trail_amount": 0}, ValueError, "positive"),
        ({"trail_amount": math.inf}, ValueError, "finite"),
        ({"trail_percent": cast("Any", True)}, TypeError, "number"),
        ({"trail_percent": 1.01}, ValueError, "at most 1"),
    ],
)
def test_order_parameters_reject_invalid_values(
    parameters: dict[str, Any], error: type[Exception], message: str
) -> None:
    with pytest.raises(error, match=message):
        OrderParameters(**parameters)


def test_order_parameters_support_nonpositive_instrument_prices() -> None:
    parameters = OrderParameters(limit_price=-10, stop_price=0)

    assert parameters.limit_price == -10
    assert parameters.stop_price == 0


def test_partial_fill_remainder_is_validated() -> None:
    order = child(quantity=10)
    assert order.remaining_after_fill(4) == 6
    assert order.remaining_after_fill(10) == 0
    for invalid in (-1, 11):
        with pytest.raises(ValueError, match="between zero"):
            order.remaining_after_fill(invalid)
    with pytest.raises(TypeError, match="number"):
        order.remaining_after_fill(cast("Any", True))


def test_child_mapping_rejects_non_mapping_parameters() -> None:
    record = child().to_dict()
    record["parameters"] = []
    with pytest.raises(TypeError, match="parameters"):
        CanonicalChildOrderIntent.from_mapping(record)


def test_execution_policy_round_trip_and_records_all_assumptions() -> None:
    original = execution_policy()

    assert ExecutionPolicy.from_mapping(original.to_dict()) == original
    assert original.to_dict()["bar_path"] == "reject_ambiguous"


@pytest.mark.parametrize(
    ("overrides", "error", "message"),
    [
        ({"policy_id": ""}, ValueError, "policy_id"),
        ({"fee_bps": -1}, ValueError, "non-negative"),
        ({"slippage_bps": math.inf}, ValueError, "finite"),
        ({"spread_bps": cast("Any", True)}, TypeError, "number"),
        ({"liquidity_fraction": 0}, ValueError, r"\(0, 1\]"),
        ({"liquidity_fraction": 1.1}, ValueError, r"\(0, 1\]"),
        ({"market_fill_phase": LifecyclePhase.RUN_START}, ValueError, "market fills"),
        ({"market_fill_phase": LifecyclePhase.RUN_END}, ValueError, "market fills"),
        ({"market_fill_phase": LifecyclePhase.CAUSAL_INITIALIZATION}, ValueError, "market fills"),
        ({"market_fill_phase": cast("Any", "close")}, ValueError, "market fills"),
    ],
)
def test_execution_policy_validation(
    overrides: dict[str, Any], error: type[Exception], message: str
) -> None:
    with pytest.raises(error, match=message):
        execution_policy(**overrides)


def test_execution_policy_rejects_unknown_recorded_policy() -> None:
    record = execution_policy().to_dict()
    record["bar_path"] = "guess"
    with pytest.raises(ValueError, match="guess"):
        ExecutionPolicy.from_mapping(record)


def test_child_must_be_supported_by_execution_policy() -> None:
    limit_child = child(
        order_type=OrderType.LIMIT,
        parameters=OrderParameters(limit_price=100),
        capabilities=(ExecutionCapability.LIMIT, ExecutionCapability.OPENING_AUCTION),
    )
    partial_child = child(
        capabilities=(ExecutionCapability.OPENING_AUCTION, ExecutionCapability.PARTIAL_FILL)
    )

    validate_child_against_policy(execution_policy(), limit_child)
    with pytest.raises(ValueError, match="limit"):
        validate_child_against_policy(
            execution_policy(limit=ExecutionBehavior.DISABLED), limit_child
        )
    with pytest.raises(ValueError, match="opening_auction"):
        validate_child_against_policy(
            execution_policy(opening_auction=ExecutionBehavior.DISABLED), child()
        )
    with pytest.raises(ValueError, match="partial fills"):
        validate_child_against_policy(execution_policy(allow_partial_fills=False), partial_child)
    contingent_child = child(
        fill_eligibility=FillEligibility.NEXT_PHASE,
        time_in_force=TimeInForce.DAY,
        capabilities=(ExecutionCapability.CONTINGENT,),
    )
    with pytest.raises(ValueError, match="contingent"):
        validate_child_against_policy(execution_policy(), contingent_child)


def test_market_child_fill_phase_must_match_execution_policy() -> None:
    current_phase_child = child(
        eligibility_phase=LifecyclePhase.INTRABAR,
        fill_eligibility=FillEligibility.CURRENT_PHASE,
        time_in_force=TimeInForce.IOC,
        capabilities=(),
    )
    next_phase_child = child(
        eligibility_phase=LifecyclePhase.PRE_OPEN,
        fill_eligibility=FillEligibility.NEXT_PHASE,
        time_in_force=TimeInForce.DAY,
        capabilities=(),
    )

    validate_child_against_policy(
        execution_policy(market_fill_phase=LifecyclePhase.INTRABAR), current_phase_child
    )
    validate_child_against_policy(execution_policy(), next_phase_child)
    with pytest.raises(ValueError, match="intrabar.*opening_auction"):
        validate_child_against_policy(execution_policy(), current_phase_child)


def test_position_rule_definition_and_policy_round_trip() -> None:
    stop = PositionRuleDefinition(
        "stop",
        PositionRuleType.STOP_LOSS,
        parameters=(("pct", 0.05),),
    )
    profit = PositionRuleDefinition(
        "profit",
        PositionRuleType.TAKE_PROFIT,
        parameters=(("pct", 0.1),),
    )
    root = PositionRuleDefinition(
        "root",
        PositionRuleType.COMPOSITE,
        children=("stop", "profit"),
        composition=RuleComposition.FIRST_TRIGGERED,
    )
    original = PositionRulePolicy(
        "rules-1",
        "root",
        (root, stop, profit),
        EvaluationMode.CLIENT,
    )

    assert PositionRulePolicy.from_mapping(original.to_dict()) == original
    assert PositionRuleDefinition.from_mapping(stop.to_dict()) == stop


def test_intent_contract_records_encode_as_json_and_restore() -> None:
    rule = PositionRuleDefinition("root", PositionRuleType.STOP_LOSS)
    rule_policy = PositionRulePolicy("rules-1", "root", (rule,), EvaluationMode.CLIENT)
    contracts = (
        (target(), CanonicalTargetIntent.from_mapping),
        (child(), CanonicalChildOrderIntent.from_mapping),
        (execution_policy(), ExecutionPolicy.from_mapping),
        (rule_policy, PositionRulePolicy.from_mapping),
        (rule_state(), PositionRuleState.from_mapping),
    )

    for original, restore in contracts:
        decoded = json.loads(json.dumps(original.to_dict()))
        assert decoded == original.to_dict()
        assert restore(decoded) == original


def test_rule_contracts_materialize_mutable_collections() -> None:
    leaf = PositionRuleDefinition(
        "leaf",
        cast("Any", "stop_loss"),
        parameters=cast("Any", [["pct", 0.05]]),
        children=cast("Any", []),
    )
    policy = PositionRulePolicy(
        "rules-1",
        "leaf",
        cast("Any", [leaf]),
        cast("Any", "client"),
    )

    assert leaf.parameters == (("pct", 0.05),)
    assert leaf.children == ()
    assert policy.rules == (leaf,)
    assert PositionRulePolicy.from_mapping(policy.to_dict()) == policy


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("parameters", "pct", "parameters must be a sequence"),
        ("parameters", ["pct"], "each parameter must be a mapping"),
        ("children", "root", "children must be a sequence"),
        ("children", 1, "children must be a sequence"),
    ],
)
def test_position_rule_definition_mapping_rejects_malformed_collections(
    field: str, value: object, message: str
) -> None:
    record = PositionRuleDefinition("root", PositionRuleType.STOP_LOSS).to_dict()
    record[field] = value

    with pytest.raises(TypeError, match=message):
        PositionRuleDefinition.from_mapping(record)


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: PositionRuleDefinition("", PositionRuleType.STOP_LOSS), "rule_id"),
        (
            lambda: PositionRuleDefinition(
                "rule", PositionRuleType.STOP_LOSS, parameters=(("pct", 1), ("pct", 2))
            ),
            "names",
        ),
        (
            lambda: PositionRuleDefinition(
                "rule", PositionRuleType.STOP_LOSS, parameters=(("", 1),)
            ),
            "parameter name",
        ),
        (
            lambda: PositionRuleDefinition(
                "rule", PositionRuleType.STOP_LOSS, parameters=((cast("Any", 1), 1),)
            ),
            "parameter name",
        ),
        (
            lambda: PositionRuleDefinition(
                "rule", PositionRuleType.STOP_LOSS, parameters=(("pct", math.inf),)
            ),
            "finite",
        ),
        (
            lambda: PositionRuleDefinition("rule", PositionRuleType.COMPOSITE, children=("a",)),
            "composite rules require",
        ),
        (
            lambda: PositionRuleDefinition(
                "rule", PositionRuleType.COMPOSITE, composition=RuleComposition.ALL
            ),
            "composite rules require",
        ),
        (
            lambda: PositionRuleDefinition(
                "rule",
                PositionRuleType.STOP_LOSS,
                children=("a",),
                composition=RuleComposition.ALL,
            ),
            "leaf rules forbid",
        ),
        (
            lambda: PositionRuleDefinition(
                "rule",
                PositionRuleType.COMPOSITE,
                children=("a", "a"),
                composition=RuleComposition.ALL,
            ),
            "unique",
        ),
    ],
)
def test_position_rule_definition_validation(factory: Any, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        factory()


def test_position_rule_policy_validation() -> None:
    rule = PositionRuleDefinition("root", PositionRuleType.STOP_LOSS)
    child_rule = PositionRuleDefinition("child", PositionRuleType.TAKE_PROFIT)
    for values, message in (
        ({"policy_id": ""}, "policy_id"),
        ({"root_rule_id": ""}, "root_rule_id"),
        ({"rules": (rule, rule)}, "unique"),
        ({"root_rule_id": "missing"}, "identify a rule"),
        (
            {
                "rules": (
                    PositionRuleDefinition(
                        "root",
                        PositionRuleType.COMPOSITE,
                        children=("missing",),
                        composition=RuleComposition.ALL,
                    ),
                    child_rule,
                )
            },
            "unknown",
        ),
        ({"lifecycle_version": cast("Any", "2")}, "version"),
    ):
        arguments: dict[str, Any] = {
            "policy_id": "rules-1",
            "root_rule_id": "root",
            "rules": (rule,),
            "evaluation_mode": EvaluationMode.CLIENT,
        }
        arguments.update(values)
        with pytest.raises(ValueError, match=message):
            PositionRulePolicy(**cast("Any", arguments))


def test_position_rule_policy_rejects_cycles_and_unreachable_rules() -> None:
    cyclic_root = PositionRuleDefinition(
        "root",
        PositionRuleType.COMPOSITE,
        children=("child",),
        composition=RuleComposition.ALL,
    )
    cyclic_child = PositionRuleDefinition(
        "child",
        PositionRuleType.COMPOSITE,
        children=("root",),
        composition=RuleComposition.ALL,
    )
    with pytest.raises(ValueError, match="cycle"):
        PositionRulePolicy("rules-1", "root", (cyclic_root, cyclic_child), EvaluationMode.CLIENT)

    root = PositionRuleDefinition("root", PositionRuleType.STOP_LOSS)
    unreachable = PositionRuleDefinition("unreachable", PositionRuleType.TAKE_PROFIT)
    with pytest.raises(ValueError, match="unreachable"):
        PositionRulePolicy("rules-1", "root", (root, unreachable), EvaluationMode.CLIENT)


def test_position_rule_policy_accepts_shared_acyclic_children() -> None:
    leaf = PositionRuleDefinition("leaf", PositionRuleType.STOP_LOSS)
    left = PositionRuleDefinition(
        "left",
        PositionRuleType.COMPOSITE,
        children=("leaf",),
        composition=RuleComposition.ALL,
    )
    right = PositionRuleDefinition(
        "right",
        PositionRuleType.COMPOSITE,
        children=("leaf",),
        composition=RuleComposition.ALL,
    )
    root = PositionRuleDefinition(
        "root",
        PositionRuleType.COMPOSITE,
        children=("left", "right"),
        composition=RuleComposition.ALL,
    )

    policy = PositionRulePolicy("rules-1", "root", (root, left, right, leaf), EvaluationMode.CLIENT)

    assert policy.root_rule_id == "root"


def test_position_rule_state_round_trip_for_hold_adjustment_and_exit() -> None:
    hold = rule_state()
    adjustment = rule_state(action=PositionActionType.ADJUST_STOP)
    exit_state = rule_state(
        activation=RuleActivation.TRIGGERED,
        remaining_exit_quantity=4,
        action=PositionActionType.EXIT_PARTIAL,
        exit_reason=ExitReason.STOP_LOSS,
    )

    assert PositionRuleState.from_mapping(hold.to_dict()) == hold
    assert PositionRuleState.from_mapping(adjustment.to_dict()) == adjustment
    assert PositionRuleState.from_mapping(exit_state.to_dict()) == exit_state


def test_position_rule_state_supports_negative_instrument_prices() -> None:
    original = rule_state(entry_price=-10, high_water_mark=-5, low_water_mark=-40)

    assert PositionRuleState.from_mapping(original.to_dict()) == original


@pytest.mark.parametrize(
    ("overrides", "error", "message"),
    [
        ({"policy_id": ""}, ValueError, "policy_id"),
        ({"asset": ""}, ValueError, "asset"),
        ({"idempotency_key": ""}, ValueError, "idempotency_key"),
        ({"entry_time": datetime(2026, 8, 8)}, ValueError, "entry_time"),
        ({"entry_price": math.inf}, ValueError, "finite"),
        ({"entry_quantity": 0}, ValueError, "entry_quantity"),
        ({"remaining_exit_quantity": -1}, ValueError, "between zero"),
        ({"remaining_exit_quantity": 11}, ValueError, "between zero"),
        ({"low_water_mark": 111}, ValueError, "must not exceed"),
        ({"max_favorable_excursion": -0.01}, ValueError, "non-negative fractional"),
        ({"max_adverse_excursion": 0.01}, ValueError, "non-positive fractional"),
        ({"exit_reason": ExitReason.SIGNAL}, ValueError, "hold and adjust_stop"),
        (
            {"action": PositionActionType.ADJUST_STOP, "exit_reason": ExitReason.STOP_LOSS},
            ValueError,
            "hold and adjust_stop",
        ),
        (
            {"action": PositionActionType.EXIT_FULL, "exit_reason": ExitReason.NONE},
            ValueError,
            "requires an exit reason",
        ),
    ],
)
def test_position_rule_state_validation(
    overrides: dict[str, Any], error: type[Exception], message: str
) -> None:
    with pytest.raises(error, match=message):
        rule_state(**overrides)


def test_intent_comparison_identifies_only_canonical_differences() -> None:
    first_target = target()
    first_child = child()

    assert compare_target_intents(first_target, first_target).equivalent
    target_difference = compare_target_intents(first_target, replace(first_target, cash_buffer=0.1))
    child_difference = compare_child_intents(first_child, replace(first_child, quantity=11))
    assert target_difference.differences == ("cash_buffer",)
    assert not target_difference.equivalent
    assert child_difference.differences == ("quantity",)
    assert not child_difference.equivalent
    assert compare_child_intents(first_child, first_child).equivalent
    assert compare_target_intents(
        first_target, replace(first_target, intent_id="other")
    ).differences == ("intent_id",)


def test_direct_construction_normalizes_string_enum_values() -> None:
    direct_target = target(
        effective_phase=cast("Any", "pre_open"),
        measure=cast("Any", "weight"),
        rounding=cast("Any", "toward_zero"),
        residual=cast("Any", "keep_cash"),
        reason=cast("Any", "rebalance"),
        targets=(AssetTarget("SPY", cast("Any", "weight"), 0.5),),
    )
    direct_child = child(
        side=cast("Any", "buy"),
        order_type=cast("Any", "market"),
        eligibility_phase=cast("Any", "pre_open"),
        fill_eligibility=cast("Any", "opening_auction"),
        time_in_force=cast("Any", "opg"),
        session_policy=cast("Any", "regular"),
        capabilities=cast("Any", ("opening_auction",)),
        reason=cast("Any", "rebalance"),
    )
    direct_policy = execution_policy(
        market_fill_phase=cast("Any", "opening_auction"),
        opening_auction=cast("Any", "broker_native"),
        moc=cast("Any", "broker_native"),
        limit=cast("Any", "broker_native"),
        stop=cast("Any", "client"),
        stop_limit=cast("Any", "client"),
        trailing=cast("Any", "client"),
        contingent=cast("Any", "disabled"),
        bar_path=cast("Any", "reject_ambiguous"),
    )
    direct_state = rule_state(
        activation=cast("Any", "active"),
        action=cast("Any", "hold"),
        exit_reason=cast("Any", "none"),
        evaluation_mode=cast("Any", "client"),
    )

    assert CanonicalTargetIntent.from_mapping(direct_target.to_dict()) == direct_target
    assert CanonicalChildOrderIntent.from_mapping(direct_child.to_dict()) == direct_child
    assert ExecutionPolicy.from_mapping(direct_policy.to_dict()) == direct_policy
    assert PositionRuleState.from_mapping(direct_state.to_dict()) == direct_state


def test_contract_identifiers_are_whitespace_canonicalized() -> None:
    direct_target = target(
        intent_id=" target-1 ",
        idempotency_key=" target-key ",
        position_rule_policy_id=" rules-1 ",
        targets=(AssetTarget(" SPY ", TargetMeasure.WEIGHT, 0.5),),
    )
    direct_child = child(
        child_intent_id=" child-1 ",
        target_intent_id=" target-1 ",
        idempotency_key=" child-key ",
        asset=" SPY ",
    )

    assert direct_target.intent_id == "target-1"
    assert direct_target.targets[0].asset == "SPY"
    assert direct_child.target_intent_id == direct_target.intent_id
    validate_child_lineage(direct_target, direct_child)


def test_child_lineage_validation() -> None:
    parent = target()
    valid = child()
    validate_child_lineage(parent, valid)

    for invalid, message in (
        (replace(valid, target_intent_id="other"), "target_intent_id"),
        (replace(valid, asset="QQQ"), "absent"),
    ):
        with pytest.raises(ValueError, match=message):
            validate_child_lineage(parent, invalid)

    mismatched_version = child()
    object.__setattr__(mismatched_version, "lifecycle_version", cast("Any", "other"))
    with pytest.raises(ValueError, match="lifecycle version"):
        validate_child_lineage(parent, mismatched_version)

    later_target = target(effective_phase=LifecyclePhase.CLOSE)
    with pytest.raises(ValueError, match="precedes"):
        validate_child_lineage(later_target, valid)

    prior_session_child = replace(valid, effective_session=date(2026, 8, 9))
    with pytest.raises(ValueError, match="effective session"):
        validate_child_lineage(parent, prior_session_child)

    next_session_child = replace(valid, effective_session=date(2026, 8, 11))
    validate_child_lineage(later_target, next_session_child)

    market_event_target = target(effective_phase=LifecyclePhase.MARKET_EVENT)
    close_child = child(
        eligibility_phase=LifecyclePhase.CLOSE,
        fill_eligibility=FillEligibility.NEXT_PHASE,
        time_in_force=TimeInForce.DAY,
        capabilities=(),
    )
    validate_child_lineage(market_event_target, close_child)

    close_target = target(effective_phase=LifecyclePhase.CLOSE)
    market_event_child = child(
        eligibility_phase=LifecyclePhase.MARKET_EVENT,
        fill_eligibility=FillEligibility.NEXT_PHASE,
        time_in_force=TimeInForce.DAY,
        capabilities=(),
    )
    with pytest.raises(ValueError, match="precedes"):
        validate_child_lineage(close_target, market_event_child)
