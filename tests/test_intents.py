from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
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
    validate_child_lineage,
)

DECISION_TIME = datetime(2026, 8, 8, 13, 0, tzinfo=UTC)


def target(**overrides: Any) -> CanonicalTargetIntent:
    values = {
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
    restored_target = CanonicalTargetIntent.from_mapping(fixture["target"])
    restored_child = CanonicalChildOrderIntent.from_mapping(fixture["child"])

    assert restored_target.to_dict() == fixture["target"]
    assert restored_child.to_dict() == fixture["child"]
    validate_child_lineage(restored_target, restored_child)


@given(
    value=st.floats(allow_nan=False, allow_infinity=False, width=64),
    measure=st.sampled_from(TargetMeasure),
)
def test_asset_targets_preserve_finite_signed_values(value: float, measure: TargetMeasure) -> None:
    accepted = AssetTarget("SPY", measure, value)

    assert accepted.value == value
    assert accepted.measure is measure


def test_target_round_trip_and_optional_position_rule_policy() -> None:
    original = target(position_rule_policy_id="rules-1")

    assert CanonicalTargetIntent.from_mapping(original.to_dict()) == original


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
        ({"effective_phase": LifecyclePhase.RUN_START}, ValueError, "does not allow"),
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
    assert AssetTarget.from_mapping(
        {"asset": "SPY", "measure": "weight", "value": 0.5}
    ) == AssetTarget("SPY", TargetMeasure.WEIGHT, 0.5)
    record = target().to_dict()
    for invalid in ("targets", 1):
        record["targets"] = invalid
        with pytest.raises(TypeError, match="targets"):
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
    original = child(
        order_type=order_type,
        parameters=parameters,
        capabilities=capabilities,
    )

    assert CanonicalChildOrderIntent.from_mapping(original.to_dict()) == original


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
                "order_type": OrderType.LIMIT,
                "parameters": OrderParameters(),
                "capabilities": (ExecutionCapability.LIMIT,),
            },
            ValueError,
            "limit_price",
        ),
        (
            {
                "order_type": OrderType.STOP,
                "parameters": OrderParameters(),
                "capabilities": (ExecutionCapability.STOP,),
            },
            ValueError,
            "stop_price",
        ),
        (
            {
                "order_type": OrderType.STOP_LIMIT,
                "parameters": OrderParameters(stop_price=99),
                "capabilities": (ExecutionCapability.STOP_LIMIT,),
            },
            ValueError,
            "stop_price and limit_price",
        ),
        (
            {
                "order_type": OrderType.TRAILING_STOP,
                "parameters": OrderParameters(),
                "capabilities": (ExecutionCapability.TRAILING_STOP,),
            },
            ValueError,
            "exactly one",
        ),
        (
            {
                "order_type": OrderType.TRAILING_STOP,
                "parameters": OrderParameters(trail_amount=1, trail_percent=0.01),
                "capabilities": (ExecutionCapability.TRAILING_STOP,),
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
    ("parameters", "error", "message"),
    [
        ({"limit_price": 0}, ValueError, "positive"),
        ({"stop_price": -1}, ValueError, "positive"),
        ({"trail_amount": math.inf}, ValueError, "finite"),
        ({"trail_percent": cast("Any", True)}, TypeError, "number"),
    ],
)
def test_order_parameters_reject_invalid_values(
    parameters: dict[str, Any], error: type[Exception], message: str
) -> None:
    with pytest.raises(error, match=message):
        OrderParameters(**parameters)


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
            "names",
        ),
        (
            lambda: PositionRuleDefinition(
                "rule", PositionRuleType.STOP_LOSS, parameters=(("pct", math.inf),)
            ),
            "finite",
        ),
        (
            lambda: PositionRuleDefinition("rule", PositionRuleType.COMPOSITE, children=("a",)),
            "together",
        ),
        (
            lambda: PositionRuleDefinition(
                "rule", PositionRuleType.COMPOSITE, composition=RuleComposition.ALL
            ),
            "together",
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


def test_position_rule_state_round_trip_for_hold_and_exit() -> None:
    hold = rule_state()
    exit_state = rule_state(
        activation=RuleActivation.TRIGGERED,
        remaining_exit_quantity=4,
        action=PositionActionType.EXIT_PARTIAL,
        exit_reason=ExitReason.STOP_LOSS,
    )

    assert PositionRuleState.from_mapping(hold.to_dict()) == hold
    assert PositionRuleState.from_mapping(exit_state.to_dict()) == exit_state


@pytest.mark.parametrize(
    ("overrides", "error", "message"),
    [
        ({"policy_id": ""}, ValueError, "policy_id"),
        ({"asset": ""}, ValueError, "asset"),
        ({"idempotency_key": ""}, ValueError, "idempotency_key"),
        ({"entry_time": datetime(2026, 8, 8)}, ValueError, "entry_time"),
        ({"entry_price": math.inf}, ValueError, "finite"),
        ({"entry_price": 0}, ValueError, "prices"),
        ({"high_water_mark": 0}, ValueError, "prices"),
        ({"low_water_mark": 0}, ValueError, "prices"),
        ({"entry_quantity": 0}, ValueError, "entry_quantity"),
        ({"remaining_exit_quantity": -1}, ValueError, "between zero"),
        ({"remaining_exit_quantity": 11}, ValueError, "between zero"),
        ({"low_water_mark": 111}, ValueError, "must not exceed"),
        ({"exit_reason": ExitReason.SIGNAL}, ValueError, "hold action"),
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
