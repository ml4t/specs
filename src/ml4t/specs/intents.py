"""Canonical strategy intent, execution-policy, and position-rule contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Any

from ._validation import finite as _finite
from ._validation import non_empty as _non_empty
from ._validation import utc as _utc
from .lifecycle import (
    LIFECYCLE_V1,
    InformationField,
    LifecyclePhase,
    LifecycleVersion,
    negotiate_lifecycle_version,
)


class TargetMeasure(StrEnum):
    """Units used by a target intent."""

    WEIGHT = "weight"
    QUANTITY = "quantity"


class RoundingPolicy(StrEnum):
    """How target quantities become tradable quantities."""

    NONE = "none"
    TOWARD_ZERO = "toward_zero"
    NEAREST = "nearest"


class ResidualPolicy(StrEnum):
    """How sizing residuals are handled."""

    KEEP_CASH = "keep_cash"
    LARGEST_REMAINDER = "largest_remainder"
    REJECT = "reject"


class IntentReason(StrEnum):
    """Typed reason for a strategy intent."""

    SIGNAL = "signal"
    REBALANCE = "rebalance"
    POSITION_RULE = "position_rule"
    LIQUIDATION = "liquidation"
    MANUAL = "manual"


class OrderSide(StrEnum):
    """Unsigned child-order direction."""

    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    """Portable child-order types."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"
    MOC = "moc"


class TimeInForce(StrEnum):
    """Portable order duration policies."""

    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"
    OPG = "opg"
    CLS = "cls"


class SessionPolicy(StrEnum):
    """Sessions in which an order is eligible."""

    REGULAR = "regular"
    EXTENDED = "extended"
    ANY = "any"


class ExecutionCapability(StrEnum):
    """Venue or client capabilities required by a child order."""

    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"
    OPENING_AUCTION = "opening_auction"
    CLOSE_AUCTION = "close_auction"
    PARTIAL_FILL = "partial_fill"
    CONTINGENT = "contingent"


class EvaluationMode(StrEnum):
    """Where an order or rule is evaluated."""

    CLIENT = "client"
    BROKER_NATIVE = "broker_native"


class FillEligibility(StrEnum):
    """When an accepted child intent can fill."""

    CURRENT_PHASE = "current_phase"
    NEXT_PHASE = "next_phase"
    OPENING_AUCTION = "opening_auction"
    CLOSE_AUCTION = "close_auction"


class ExecutionBehavior(StrEnum):
    """How one execution behavior is provided."""

    DISABLED = "disabled"
    CLIENT = "client"
    BROKER_NATIVE = "broker_native"


class BarPathPolicy(StrEnum):
    """How ambiguous intrabar trigger order is resolved."""

    REJECT_AMBIGUOUS = "reject_ambiguous"
    CONSERVATIVE = "conservative"
    OPEN_HIGH_LOW_CLOSE = "open_high_low_close"
    OPEN_LOW_HIGH_CLOSE = "open_low_high_close"


class PositionRuleType(StrEnum):
    """Portable position-rule kinds."""

    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TRAILING_STOP = "trailing_stop"
    TIME_EXIT = "time_exit"
    SCALED_EXIT = "scaled_exit"
    COMPOSITE = "composite"


class RuleComposition(StrEnum):
    """How child position rules compose."""

    ALL = "all"
    ANY = "any"
    FIRST_TRIGGERED = "first_triggered"


class RuleActivation(StrEnum):
    """Current position-rule activation state."""

    INACTIVE = "inactive"
    ACTIVE = "active"
    TRIGGERED = "triggered"
    COMPLETE = "complete"


class PositionActionType(StrEnum):
    """Typed result of position-rule evaluation."""

    HOLD = "hold"
    EXIT_FULL = "exit_full"
    EXIT_PARTIAL = "exit_partial"
    ADJUST_STOP = "adjust_stop"


class ExitReason(StrEnum):
    """Typed reason for a position exit."""

    NONE = "none"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TRAILING_STOP = "trailing_stop"
    TIME_EXIT = "time_exit"
    SIGNAL = "signal"
    LIQUIDATION = "liquidation"


def _intent_phase(phase: LifecyclePhase) -> None:
    if not LIFECYCLE_V1.phase_spec(phase).intents_allowed:
        raise ValueError(f"phase {phase.value!r} does not allow intents")


@dataclass(frozen=True, slots=True)
class AssetTarget:
    """One signed asset target in an explicit unit."""

    asset: str
    measure: TargetMeasure
    value: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "measure", TargetMeasure(self.measure))
        object.__setattr__(self, "asset", _non_empty(self.asset, "asset"))
        object.__setattr__(self, "value", _finite(self.value, "target value"))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible asset target."""
        return {"asset": self.asset, "measure": self.measure.value, "value": self.value}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> AssetTarget:
        return cls(value["asset"], TargetMeasure(value["measure"]), value["value"])


@dataclass(frozen=True, slots=True)
class CanonicalTargetIntent:
    """Strategy decision; effective session may trail its UTC decision date by one day."""

    intent_id: str
    decision_time: datetime
    information_cutoff: datetime
    effective_session: date
    effective_phase: LifecyclePhase
    targets: tuple[AssetTarget, ...]
    idempotency_key: str
    measure: TargetMeasure
    cash_buffer: float
    rounding: RoundingPolicy
    residual: ResidualPolicy
    reason: IntentReason
    lifecycle_version: LifecycleVersion = LifecycleVersion.V1
    position_rule_policy_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "effective_phase", LifecyclePhase(self.effective_phase))
        object.__setattr__(self, "measure", TargetMeasure(self.measure))
        object.__setattr__(self, "rounding", RoundingPolicy(self.rounding))
        object.__setattr__(self, "residual", ResidualPolicy(self.residual))
        object.__setattr__(self, "reason", IntentReason(self.reason))
        object.__setattr__(self, "intent_id", _non_empty(self.intent_id, "intent_id"))
        object.__setattr__(
            self, "idempotency_key", _non_empty(self.idempotency_key, "idempotency_key")
        )
        object.__setattr__(self, "decision_time", _utc(self.decision_time, "decision_time"))
        object.__setattr__(
            self,
            "information_cutoff",
            _utc(self.information_cutoff, "information_cutoff"),
        )
        if self.information_cutoff > self.decision_time:
            raise ValueError("information_cutoff must not follow decision_time")
        if not isinstance(self.effective_session, date) or isinstance(
            self.effective_session, datetime
        ):
            raise TypeError("effective_session must be a date")
        if self.effective_session < self.decision_time.date() - timedelta(days=1):
            raise ValueError("effective_session is stale relative to decision_time")
        _intent_phase(self.effective_phase)
        if isinstance(self.targets, str | bytes):
            raise TypeError("targets must be an iterable of AssetTarget values")
        targets = tuple(self.targets)
        if not targets:
            raise ValueError("targets must not be empty")
        if any(not isinstance(target, AssetTarget) for target in targets):
            raise TypeError("each target must be an AssetTarget")
        assets = tuple(target.asset for target in targets)
        if len(assets) != len(set(assets)):
            raise ValueError("targets must contain each asset once")
        if any(target.measure is not self.measure for target in targets):
            raise ValueError("every target measure must match intent measure")
        object.__setattr__(self, "targets", tuple(sorted(targets, key=lambda item: item.asset)))
        cash_buffer = _finite(self.cash_buffer, "cash_buffer")
        object.__setattr__(self, "cash_buffer", cash_buffer)
        if not 0 <= cash_buffer < 1:
            raise ValueError("cash_buffer must be in [0, 1)")
        if self.position_rule_policy_id is not None:
            object.__setattr__(
                self,
                "position_rule_policy_id",
                _non_empty(self.position_rule_policy_id, "position_rule_policy_id"),
            )
        object.__setattr__(
            self,
            "lifecycle_version",
            negotiate_lifecycle_version(self.lifecycle_version, self.effective_phase),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible canonical target."""
        return {
            "intent_id": self.intent_id,
            "decision_time": self.decision_time.isoformat(),
            "information_cutoff": self.information_cutoff.isoformat(),
            "effective_session": self.effective_session.isoformat(),
            "effective_phase": self.effective_phase.value,
            "targets": [target.to_dict() for target in self.targets],
            "idempotency_key": self.idempotency_key,
            "measure": self.measure.value,
            "cash_buffer": self.cash_buffer,
            "rounding": self.rounding.value,
            "residual": self.residual.value,
            "reason": self.reason.value,
            "lifecycle_version": self.lifecycle_version.value,
            "position_rule_policy_id": self.position_rule_policy_id,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> CanonicalTargetIntent:
        """Restore and validate a canonical target."""
        targets = value["targets"]
        if not isinstance(targets, Sequence) or isinstance(targets, str | bytes):
            raise TypeError("targets must be a sequence")
        if any(not isinstance(target, Mapping) for target in targets):
            raise TypeError("each target must be a mapping")
        return cls(
            intent_id=value["intent_id"],
            decision_time=datetime.fromisoformat(value["decision_time"]),
            information_cutoff=datetime.fromisoformat(value["information_cutoff"]),
            effective_session=date.fromisoformat(value["effective_session"]),
            effective_phase=LifecyclePhase(value["effective_phase"]),
            targets=tuple(AssetTarget.from_mapping(target) for target in targets),
            idempotency_key=value["idempotency_key"],
            measure=TargetMeasure(value["measure"]),
            cash_buffer=value["cash_buffer"],
            rounding=RoundingPolicy(value["rounding"]),
            residual=ResidualPolicy(value["residual"]),
            reason=IntentReason(value["reason"]),
            lifecycle_version=value["lifecycle_version"],
            position_rule_policy_id=value.get("position_rule_policy_id"),
        )


@dataclass(frozen=True, slots=True)
class OrderParameters:
    """Typed prices for child orders; ``trail_percent`` is a decimal fraction in (0, 1]."""

    limit_price: float | None = None
    stop_price: float | None = None
    trail_amount: float | None = None
    trail_percent: float | None = None

    def __post_init__(self) -> None:
        for name in ("limit_price", "stop_price"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _finite(value, name))
        for name in ("trail_amount", "trail_percent"):
            value = getattr(self, name)
            if value is not None:
                normalized = _finite(value, name)
                object.__setattr__(self, name, normalized)
                if normalized <= 0:
                    raise ValueError(f"{name} must be positive")
        if self.trail_percent is not None and self.trail_percent > 1:
            raise ValueError("trail_percent must be at most 1")


_REQUIRED_CAPABILITY: dict[OrderType, ExecutionCapability | None] = {
    OrderType.MARKET: None,
    OrderType.LIMIT: ExecutionCapability.LIMIT,
    OrderType.STOP: ExecutionCapability.STOP,
    OrderType.STOP_LIMIT: ExecutionCapability.STOP_LIMIT,
    OrderType.TRAILING_STOP: ExecutionCapability.TRAILING_STOP,
    OrderType.MOC: ExecutionCapability.CLOSE_AUCTION,
}

_TIME_IN_FORCE_CAPABILITY: dict[TimeInForce, ExecutionCapability | None] = {
    TimeInForce.DAY: None,
    TimeInForce.GTC: None,
    TimeInForce.IOC: None,
    TimeInForce.FOK: None,
    TimeInForce.OPG: ExecutionCapability.OPENING_AUCTION,
    TimeInForce.CLS: ExecutionCapability.CLOSE_AUCTION,
}

_FILL_ELIGIBILITY_CAPABILITY: dict[FillEligibility, ExecutionCapability | None] = {
    FillEligibility.CURRENT_PHASE: None,
    FillEligibility.NEXT_PHASE: None,
    FillEligibility.OPENING_AUCTION: ExecutionCapability.OPENING_AUCTION,
    FillEligibility.CLOSE_AUCTION: ExecutionCapability.CLOSE_AUCTION,
}

_FILL_INFORMATION_FIELDS: dict[FillEligibility, frozenset[InformationField]] = {
    FillEligibility.CURRENT_PHASE: frozenset(),
    FillEligibility.NEXT_PHASE: frozenset(),
    FillEligibility.OPENING_AUCTION: frozenset(
        {InformationField.OFFICIAL_OPEN, InformationField.CURRENT_OPEN}
    ),
    FillEligibility.CLOSE_AUCTION: frozenset({InformationField.CURRENT_CLOSE}),
}

_CURRENT_PHASE_INFORMATION_FIELDS: dict[LifecyclePhase, frozenset[InformationField]] = {
    LifecyclePhase.OPENING_AUCTION: frozenset(
        {InformationField.OFFICIAL_OPEN, InformationField.CURRENT_OPEN}
    ),
    LifecyclePhase.INTRABAR: frozenset(
        {InformationField.CURRENT_HIGH, InformationField.CURRENT_LOW}
    ),
    LifecyclePhase.CLOSE: frozenset({InformationField.CURRENT_CLOSE}),
}

_ALLOWED_PARAMETERS: dict[OrderType, frozenset[str]] = {
    OrderType.MARKET: frozenset(),
    OrderType.LIMIT: frozenset({"limit_price"}),
    OrderType.STOP: frozenset({"stop_price"}),
    OrderType.STOP_LIMIT: frozenset({"limit_price", "stop_price"}),
    OrderType.TRAILING_STOP: frozenset({"trail_amount", "trail_percent"}),
    OrderType.MOC: frozenset(),
}

_MARKET_FILL_PHASES = frozenset(
    {
        LifecyclePhase.OPENING_AUCTION,
        LifecyclePhase.INTRABAR,
        LifecyclePhase.MARKET_EVENT,
    }
)


def _later_market_fill_phases(phase: LifecyclePhase) -> frozenset[LifecyclePhase]:
    if phase in {LifecyclePhase.INTRABAR, LifecyclePhase.MARKET_EVENT}:
        return frozenset({phase})
    current_rank = LIFECYCLE_V1.phase_spec(phase).causal_rank
    later_phases = {
        candidate
        for candidate in _MARKET_FILL_PHASES
        if LIFECYCLE_V1.phase_spec(candidate).causal_rank > current_rank
    }
    if not later_phases:
        return frozenset()
    next_rank = min(LIFECYCLE_V1.phase_spec(candidate).causal_rank for candidate in later_phases)
    return frozenset(
        candidate
        for candidate in later_phases
        if LIFECYCLE_V1.phase_spec(candidate).causal_rank == next_rank
    )


@dataclass(frozen=True, slots=True)
class CanonicalChildOrderIntent:
    """Unsigned venue-facing order intent with target lineage."""

    child_intent_id: str
    target_intent_id: str
    idempotency_key: str
    asset: str
    side: OrderSide
    quantity: float
    order_type: OrderType
    parameters: OrderParameters
    decision_session: date
    effective_session: date
    eligibility_phase: LifecyclePhase
    fill_eligibility: FillEligibility
    time_in_force: TimeInForce
    session_policy: SessionPolicy
    capabilities: tuple[ExecutionCapability, ...]
    reason: IntentReason
    lifecycle_version: LifecycleVersion = LifecycleVersion.V1

    def __post_init__(self) -> None:
        object.__setattr__(self, "side", OrderSide(self.side))
        object.__setattr__(self, "order_type", OrderType(self.order_type))
        object.__setattr__(self, "eligibility_phase", LifecyclePhase(self.eligibility_phase))
        object.__setattr__(self, "fill_eligibility", FillEligibility(self.fill_eligibility))
        object.__setattr__(self, "time_in_force", TimeInForce(self.time_in_force))
        object.__setattr__(self, "session_policy", SessionPolicy(self.session_policy))
        object.__setattr__(self, "reason", IntentReason(self.reason))
        if isinstance(self.capabilities, str | bytes):
            raise TypeError("capabilities must be an iterable of ExecutionCapability values")
        capabilities = tuple(ExecutionCapability(value) for value in self.capabilities)
        object.__setattr__(self, "capabilities", capabilities)
        for value, name in (
            (self.child_intent_id, "child_intent_id"),
            (self.target_intent_id, "target_intent_id"),
            (self.idempotency_key, "idempotency_key"),
            (self.asset, "asset"),
        ):
            object.__setattr__(self, name, _non_empty(value, name))
        quantity = _finite(self.quantity, "quantity")
        object.__setattr__(self, "quantity", quantity)
        if quantity <= 0:
            raise ValueError("quantity must be positive and unsigned")
        for name in ("decision_session", "effective_session"):
            value = getattr(self, name)
            if not isinstance(value, date) or isinstance(value, datetime):
                raise TypeError(f"{name} must be a date")
        if self.effective_session < self.decision_session:
            raise ValueError("effective_session must not precede decision_session")
        if not isinstance(self.parameters, OrderParameters):
            raise TypeError("parameters must be OrderParameters")
        _intent_phase(self.eligibility_phase)
        if len(self.capabilities) != len(set(self.capabilities)):
            raise ValueError("capabilities must be unique")
        required_capabilities = {
            capability
            for capability in (
                _REQUIRED_CAPABILITY[self.order_type],
                _TIME_IN_FORCE_CAPABILITY[self.time_in_force],
                _FILL_ELIGIBILITY_CAPABILITY[self.fill_eligibility],
            )
            if capability is not None
        }
        missing = required_capabilities - set(self.capabilities)
        if missing:
            required = ", ".join(sorted(capability.value for capability in missing))
            raise ValueError(f"child order requires capability: {required}")
        self._validate_eligibility()
        object.__setattr__(
            self,
            "capabilities",
            tuple(sorted(self.capabilities, key=lambda capability: capability.value)),
        )
        self._validate_parameters()
        object.__setattr__(
            self,
            "lifecycle_version",
            negotiate_lifecycle_version(self.lifecycle_version, self.eligibility_phase),
        )

    def _validate_eligibility(self) -> None:
        eligibility = self.fill_eligibility
        time_in_force = self.time_in_force
        if time_in_force is TimeInForce.OPG and eligibility is not FillEligibility.OPENING_AUCTION:
            raise ValueError("opg time in force requires opening_auction fill eligibility")
        if time_in_force is TimeInForce.CLS and eligibility is not FillEligibility.CLOSE_AUCTION:
            raise ValueError("cls time in force requires close_auction fill eligibility")
        if self.order_type is OrderType.MOC and eligibility is not FillEligibility.CLOSE_AUCTION:
            raise ValueError("moc order requires close_auction fill eligibility")
        if time_in_force in {TimeInForce.IOC, TimeInForce.FOK} and (
            eligibility is not FillEligibility.CURRENT_PHASE
        ):
            raise ValueError(
                f"{time_in_force.value} time in force requires current_phase eligibility"
            )
        same_session = self.effective_session == self.decision_session
        if not same_session and eligibility is FillEligibility.CURRENT_PHASE:
            raise ValueError("current_phase fill eligibility requires the decision session")
        if same_session:
            visible = set(LIFECYCLE_V1.phase_spec(self.eligibility_phase).visible_fields)
            information_fields = _FILL_INFORMATION_FIELDS[eligibility]
            if eligibility is FillEligibility.CURRENT_PHASE:
                information_fields = _CURRENT_PHASE_INFORMATION_FIELDS.get(
                    self.eligibility_phase, frozenset()
                )
            consumed = visible & information_fields
            if consumed:
                fields = ", ".join(sorted(field.value for field in consumed))
                raise ValueError(
                    f"fill eligibility would consume already visible information: {fields}"
                )
        if (
            eligibility is FillEligibility.NEXT_PHASE
            and same_session
            and not _later_market_fill_phases(self.eligibility_phase)
        ):
            raise ValueError(f"no later fill phase follows {self.eligibility_phase.value}")
        if (
            eligibility is FillEligibility.CURRENT_PHASE
            and self.eligibility_phase not in _MARKET_FILL_PHASES
        ):
            raise ValueError("current-phase order requires a market-fill phase")

    def _validate_parameters(self) -> None:
        parameters = self.parameters
        supplied = {
            name
            for name in ("limit_price", "stop_price", "trail_amount", "trail_percent")
            if getattr(parameters, name) is not None
        }
        irrelevant = supplied - _ALLOWED_PARAMETERS[self.order_type]
        if irrelevant:
            names = ", ".join(sorted(irrelevant))
            raise ValueError(f"{self.order_type.value} order does not allow parameters: {names}")
        if self.order_type is OrderType.LIMIT and parameters.limit_price is None:
            raise ValueError("limit order requires limit_price")
        if self.order_type is OrderType.STOP and parameters.stop_price is None:
            raise ValueError("stop order requires stop_price")
        if self.order_type is OrderType.STOP_LIMIT and (
            parameters.stop_price is None or parameters.limit_price is None
        ):
            raise ValueError("stop_limit order requires stop_price and limit_price")
        trailing_values = (parameters.trail_amount, parameters.trail_percent)
        if (
            self.order_type is OrderType.TRAILING_STOP
            and sum(value is not None for value in trailing_values) != 1
        ):
            raise ValueError("trailing_stop requires exactly one trailing parameter")

    def remaining_after_fill(self, filled_quantity: float) -> float:
        """Return the validated unsigned remainder after a partial fill."""
        filled = _finite(filled_quantity, "filled_quantity")
        if not 0 <= filled <= self.quantity:
            raise ValueError("filled_quantity must be between zero and order quantity")
        return self.quantity - filled

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible child intent."""
        return {
            "child_intent_id": self.child_intent_id,
            "target_intent_id": self.target_intent_id,
            "idempotency_key": self.idempotency_key,
            "asset": self.asset,
            "side": self.side.value,
            "quantity": self.quantity,
            "order_type": self.order_type.value,
            "parameters": asdict(self.parameters),
            "decision_session": self.decision_session.isoformat(),
            "effective_session": self.effective_session.isoformat(),
            "eligibility_phase": self.eligibility_phase.value,
            "fill_eligibility": self.fill_eligibility.value,
            "time_in_force": self.time_in_force.value,
            "session_policy": self.session_policy.value,
            "capabilities": [capability.value for capability in self.capabilities],
            "reason": self.reason.value,
            "lifecycle_version": self.lifecycle_version.value,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> CanonicalChildOrderIntent:
        """Restore and validate a child intent."""
        parameters = value["parameters"]
        if not isinstance(parameters, Mapping):
            raise TypeError("parameters must be a mapping")
        return cls(
            child_intent_id=value["child_intent_id"],
            target_intent_id=value["target_intent_id"],
            idempotency_key=value["idempotency_key"],
            asset=value["asset"],
            side=OrderSide(value["side"]),
            quantity=value["quantity"],
            order_type=OrderType(value["order_type"]),
            parameters=OrderParameters(**parameters),
            decision_session=date.fromisoformat(value["decision_session"]),
            effective_session=date.fromisoformat(value["effective_session"]),
            eligibility_phase=LifecyclePhase(value["eligibility_phase"]),
            fill_eligibility=FillEligibility(value["fill_eligibility"]),
            time_in_force=TimeInForce(value["time_in_force"]),
            session_policy=SessionPolicy(value["session_policy"]),
            capabilities=tuple(
                ExecutionCapability(capability) for capability in value["capabilities"]
            ),
            reason=IntentReason(value["reason"]),
            lifecycle_version=value["lifecycle_version"],
        )


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    """Recorded execution assumptions used by an engine or venue."""

    policy_id: str
    market_fill_phase: LifecyclePhase
    opening_auction: ExecutionBehavior
    close_auction: ExecutionBehavior
    limit: ExecutionBehavior
    stop: ExecutionBehavior
    stop_limit: ExecutionBehavior
    trailing: ExecutionBehavior
    contingent: ExecutionBehavior
    fee_bps: float
    slippage_bps: float
    spread_bps: float
    impact_bps: float
    latency_ms: float
    liquidity_fraction: float
    allow_partial_fills: bool
    bar_path: BarPathPolicy
    supported_sessions: tuple[SessionPolicy, ...] = (SessionPolicy.REGULAR,)
    lifecycle_version: LifecycleVersion = LifecycleVersion.V1

    def __post_init__(self) -> None:
        object.__setattr__(self, "market_fill_phase", LifecyclePhase(self.market_fill_phase))
        for name in (
            "opening_auction",
            "close_auction",
            "limit",
            "stop",
            "stop_limit",
            "trailing",
            "contingent",
        ):
            object.__setattr__(self, name, ExecutionBehavior(getattr(self, name)))
        object.__setattr__(self, "bar_path", BarPathPolicy(self.bar_path))
        if isinstance(self.supported_sessions, str | bytes):
            raise TypeError("supported_sessions must be an iterable of SessionPolicy values")
        supported_sessions = tuple(SessionPolicy(value) for value in self.supported_sessions)
        if not supported_sessions:
            raise ValueError("supported_sessions must not be empty")
        if len(supported_sessions) != len(set(supported_sessions)):
            raise ValueError("supported_sessions must be unique")
        object.__setattr__(
            self,
            "supported_sessions",
            tuple(sorted(supported_sessions, key=lambda session: session.value)),
        )
        if not isinstance(self.allow_partial_fills, bool):
            raise TypeError("allow_partial_fills must be a bool")
        object.__setattr__(
            self, "lifecycle_version", negotiate_lifecycle_version(self.lifecycle_version)
        )
        object.__setattr__(self, "policy_id", _non_empty(self.policy_id, "policy_id"))
        if self.market_fill_phase not in _MARKET_FILL_PHASES:
            raise ValueError(f"phase {self.market_fill_phase.value!r} does not allow market fills")
        if (
            self.market_fill_phase is LifecyclePhase.OPENING_AUCTION
            and self.opening_auction is ExecutionBehavior.DISABLED
        ):
            raise ValueError("opening-auction market fill phase requires opening_auction behavior")
        for name in ("fee_bps", "slippage_bps", "spread_bps", "impact_bps", "latency_ms"):
            value = _finite(getattr(self, name), name)
            object.__setattr__(self, name, value)
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        liquidity = _finite(self.liquidity_fraction, "liquidity_fraction")
        object.__setattr__(self, "liquidity_fraction", liquidity)
        if not 0 < liquidity <= 1:
            raise ValueError("liquidity_fraction must be in (0, 1]")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible execution policy."""
        return {
            "policy_id": self.policy_id,
            "market_fill_phase": self.market_fill_phase.value,
            "opening_auction": self.opening_auction.value,
            "close_auction": self.close_auction.value,
            "limit": self.limit.value,
            "stop": self.stop.value,
            "stop_limit": self.stop_limit.value,
            "trailing": self.trailing.value,
            "contingent": self.contingent.value,
            "fee_bps": self.fee_bps,
            "slippage_bps": self.slippage_bps,
            "spread_bps": self.spread_bps,
            "impact_bps": self.impact_bps,
            "latency_ms": self.latency_ms,
            "liquidity_fraction": self.liquidity_fraction,
            "allow_partial_fills": self.allow_partial_fills,
            "bar_path": self.bar_path.value,
            "supported_sessions": [session.value for session in self.supported_sessions],
            "lifecycle_version": self.lifecycle_version.value,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ExecutionPolicy:
        """Restore and validate an execution policy."""
        return cls(
            policy_id=value["policy_id"],
            market_fill_phase=LifecyclePhase(value["market_fill_phase"]),
            opening_auction=ExecutionBehavior(value["opening_auction"]),
            close_auction=ExecutionBehavior(value["close_auction"]),
            limit=ExecutionBehavior(value["limit"]),
            stop=ExecutionBehavior(value["stop"]),
            stop_limit=ExecutionBehavior(value["stop_limit"]),
            trailing=ExecutionBehavior(value["trailing"]),
            contingent=ExecutionBehavior(value["contingent"]),
            fee_bps=value["fee_bps"],
            slippage_bps=value["slippage_bps"],
            spread_bps=value["spread_bps"],
            impact_bps=value["impact_bps"],
            latency_ms=value["latency_ms"],
            liquidity_fraction=value["liquidity_fraction"],
            allow_partial_fills=value["allow_partial_fills"],
            bar_path=BarPathPolicy(value["bar_path"]),
            supported_sessions=tuple(
                SessionPolicy(session) for session in value["supported_sessions"]
            ),
            lifecycle_version=value["lifecycle_version"],
        )


_ORDER_POLICY_FIELD: dict[OrderType, str | None] = {
    OrderType.MARKET: None,
    OrderType.LIMIT: "limit",
    OrderType.STOP: "stop",
    OrderType.STOP_LIMIT: "stop_limit",
    OrderType.TRAILING_STOP: "trailing",
    OrderType.MOC: "close_auction",
}

_FILL_POLICY_FIELD: dict[FillEligibility, str | None] = {
    FillEligibility.CURRENT_PHASE: None,
    FillEligibility.NEXT_PHASE: None,
    FillEligibility.OPENING_AUCTION: "opening_auction",
    FillEligibility.CLOSE_AUCTION: "close_auction",
}

_CAPABILITY_POLICY_FIELD: dict[ExecutionCapability, str | None] = {
    ExecutionCapability.LIMIT: "limit",
    ExecutionCapability.STOP: "stop",
    ExecutionCapability.STOP_LIMIT: "stop_limit",
    ExecutionCapability.TRAILING_STOP: "trailing",
    ExecutionCapability.OPENING_AUCTION: "opening_auction",
    ExecutionCapability.CLOSE_AUCTION: "close_auction",
    ExecutionCapability.PARTIAL_FILL: None,
    ExecutionCapability.CONTINGENT: "contingent",
}


def validate_child_against_policy(
    policy: ExecutionPolicy, child: CanonicalChildOrderIntent
) -> None:
    """Reject a child order that requires behavior disabled by its execution policy."""
    fields = {
        field
        for field in (
            _ORDER_POLICY_FIELD[child.order_type],
            _FILL_POLICY_FIELD[child.fill_eligibility],
            *(_CAPABILITY_POLICY_FIELD[capability] for capability in child.capabilities),
        )
        if field is not None
    }
    disabled = sorted(
        field for field in fields if getattr(policy, field) is ExecutionBehavior.DISABLED
    )
    if disabled:
        raise ValueError(f"execution policy disables required behavior: {', '.join(disabled)}")
    if ExecutionCapability.PARTIAL_FILL in child.capabilities and not policy.allow_partial_fills:
        raise ValueError("execution policy disables partial fills")
    supports_session = (
        SessionPolicy.ANY in policy.supported_sessions
        or child.session_policy in policy.supported_sessions
        or (
            child.session_policy is SessionPolicy.ANY
            and {SessionPolicy.REGULAR, SessionPolicy.EXTENDED}.issubset(policy.supported_sessions)
        )
    )
    if not supports_session:
        raise ValueError(f"execution policy does not support session {child.session_policy.value}")
    if child.order_type is OrderType.MARKET and child.fill_eligibility in {
        FillEligibility.CURRENT_PHASE,
        FillEligibility.NEXT_PHASE,
    }:
        fill_phase = child.eligibility_phase
        if child.fill_eligibility is FillEligibility.NEXT_PHASE:
            valid_fill_phases = (
                frozenset({LifecyclePhase.OPENING_AUCTION})
                if child.effective_session > child.decision_session
                else _later_market_fill_phases(fill_phase)
            )
        else:
            valid_fill_phases = {fill_phase}
        if policy.market_fill_phase not in valid_fill_phases:
            phases = ", ".join(sorted(phase.value for phase in valid_fill_phases))
            raise ValueError(
                f"market order needs fill phase {phases}, but policy fills at "
                f"{policy.market_fill_phase.value}"
            )


@dataclass(frozen=True, slots=True)
class PositionRuleDefinition:
    """One versioned position rule or composition node."""

    rule_id: str
    rule_type: PositionRuleType
    parameters: tuple[tuple[str, float], ...] = ()
    children: tuple[str, ...] = ()
    composition: RuleComposition | None = None

    def __post_init__(self) -> None:
        if isinstance(self.parameters, str | bytes):
            raise TypeError("parameters must be an iterable of name-value pairs")
        if isinstance(self.children, str | bytes):
            raise TypeError("children must be an iterable of rule ids")
        object.__setattr__(self, "rule_type", PositionRuleType(self.rule_type))
        parameters = tuple(
            (_non_empty(name, "rule parameter name"), _finite(value, f"rule parameter {name}"))
            for name, value in self.parameters
        )
        children = tuple(_non_empty(child, "rule child") for child in self.children)
        object.__setattr__(self, "parameters", parameters)
        object.__setattr__(self, "children", children)
        if self.composition is not None:
            object.__setattr__(self, "composition", RuleComposition(self.composition))
        object.__setattr__(self, "rule_id", _non_empty(self.rule_id, "rule_id"))
        names = tuple(name for name, _ in parameters)
        if len(names) != len(set(names)):
            raise ValueError("rule parameter names must be unique")
        is_composite = self.rule_type is PositionRuleType.COMPOSITE
        if is_composite and (not self.children or self.composition is None):
            raise ValueError("composite rules require children and composition")
        if not is_composite and (self.children or self.composition is not None):
            raise ValueError("leaf rules forbid children and composition")
        if self.children and len(self.children) != len(set(self.children)):
            raise ValueError("rule children must be unique")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible rule definition."""
        return {
            "rule_id": self.rule_id,
            "rule_type": self.rule_type.value,
            "parameters": [{"name": name, "value": value} for name, value in self.parameters],
            "children": list(self.children),
            "composition": self.composition.value if self.composition is not None else None,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> PositionRuleDefinition:
        """Restore and validate a rule definition."""
        raw_parameters = value.get("parameters", ())
        if not isinstance(raw_parameters, Sequence) or isinstance(raw_parameters, str | bytes):
            raise TypeError("parameters must be a sequence")
        if any(not isinstance(parameter, Mapping) for parameter in raw_parameters):
            raise TypeError("each parameter must be a mapping")
        raw_children = value.get("children", ())
        if not isinstance(raw_children, Sequence) or isinstance(raw_children, str | bytes):
            raise TypeError("children must be a sequence")
        return cls(
            rule_id=value["rule_id"],
            rule_type=PositionRuleType(value["rule_type"]),
            parameters=tuple(
                (parameter["name"], parameter["value"]) for parameter in raw_parameters
            ),
            children=tuple(raw_children),
            composition=(
                RuleComposition(value["composition"])
                if value.get("composition") is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class PositionRulePolicy:
    """Versioned rule graph with one root and explicit evaluation location."""

    policy_id: str
    root_rule_id: str
    rules: tuple[PositionRuleDefinition, ...]
    evaluation_mode: EvaluationMode
    lifecycle_version: LifecycleVersion = LifecycleVersion.V1

    def __post_init__(self) -> None:
        if isinstance(self.rules, str | bytes):
            raise TypeError("rules must be an iterable of PositionRuleDefinition values")
        rules = tuple(self.rules)
        if any(not isinstance(rule, PositionRuleDefinition) for rule in rules):
            raise TypeError("each rule must be a PositionRuleDefinition")
        object.__setattr__(self, "rules", rules)
        object.__setattr__(self, "evaluation_mode", EvaluationMode(self.evaluation_mode))
        object.__setattr__(self, "policy_id", _non_empty(self.policy_id, "policy_id"))
        object.__setattr__(self, "root_rule_id", _non_empty(self.root_rule_id, "root_rule_id"))
        rule_ids = tuple(rule.rule_id for rule in self.rules)
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("position rule ids must be unique")
        if self.root_rule_id not in rule_ids:
            raise ValueError("root_rule_id must identify a rule")
        unknown_children = {
            child for rule in self.rules for child in rule.children if child not in rule_ids
        }
        if unknown_children:
            raise ValueError(f"unknown position rule children: {sorted(unknown_children)}")
        rules_by_id = {rule.rule_id: rule for rule in self.rules}
        states: dict[str, int] = {}
        stack = [(self.root_rule_id, False)]
        while stack:
            rule_id, expanded = stack.pop()
            if expanded:
                states[rule_id] = 2
                continue
            if states.get(rule_id) == 2:
                continue
            states[rule_id] = 1
            stack.append((rule_id, True))
            for child in reversed(rules_by_id[rule_id].children):
                if states.get(child) == 1:
                    raise ValueError(f"position rule graph contains a cycle at {child!r}")
                if states.get(child) != 2:
                    stack.append((child, False))
        visited = {rule_id for rule_id, state in states.items() if state == 2}
        unreachable = set(rule_ids) - visited
        if unreachable:
            raise ValueError(f"unreachable position rules: {sorted(unreachable)}")
        object.__setattr__(
            self, "lifecycle_version", negotiate_lifecycle_version(self.lifecycle_version)
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible position-rule policy."""
        return {
            "policy_id": self.policy_id,
            "root_rule_id": self.root_rule_id,
            "rules": [rule.to_dict() for rule in self.rules],
            "evaluation_mode": self.evaluation_mode.value,
            "lifecycle_version": self.lifecycle_version.value,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> PositionRulePolicy:
        """Restore and validate a position-rule policy."""
        raw_rules = value["rules"]
        if not isinstance(raw_rules, Sequence) or isinstance(raw_rules, str | bytes):
            raise TypeError("rules must be a sequence")
        if any(not isinstance(rule, Mapping) for rule in raw_rules):
            raise TypeError("each rule must be a mapping")
        return cls(
            policy_id=value["policy_id"],
            root_rule_id=value["root_rule_id"],
            rules=tuple(PositionRuleDefinition.from_mapping(rule) for rule in raw_rules),
            evaluation_mode=EvaluationMode(value["evaluation_mode"]),
            lifecycle_version=value["lifecycle_version"],
        )


@dataclass(frozen=True, slots=True)
class PositionRuleState:
    """Portable rule state with favorable >= 0 and adverse <= 0 fractional excursions."""

    policy_id: str
    asset: str
    activation: RuleActivation
    entry_time: datetime
    entry_price: float
    entry_quantity: float
    high_water_mark: float
    low_water_mark: float
    max_favorable_excursion: float
    max_adverse_excursion: float
    remaining_exit_quantity: float
    idempotency_key: str
    action: PositionActionType
    exit_reason: ExitReason
    evaluation_mode: EvaluationMode
    lifecycle_version: LifecycleVersion = LifecycleVersion.V1

    def __post_init__(self) -> None:
        object.__setattr__(self, "activation", RuleActivation(self.activation))
        object.__setattr__(self, "action", PositionActionType(self.action))
        object.__setattr__(self, "exit_reason", ExitReason(self.exit_reason))
        object.__setattr__(self, "evaluation_mode", EvaluationMode(self.evaluation_mode))
        object.__setattr__(
            self, "lifecycle_version", negotiate_lifecycle_version(self.lifecycle_version)
        )
        for value, name in (
            (self.policy_id, "policy_id"),
            (self.asset, "asset"),
            (self.idempotency_key, "idempotency_key"),
        ):
            object.__setattr__(self, name, _non_empty(value, name))
        object.__setattr__(self, "entry_time", _utc(self.entry_time, "entry_time"))
        for name in (
            "entry_price",
            "entry_quantity",
            "high_water_mark",
            "low_water_mark",
            "max_favorable_excursion",
            "max_adverse_excursion",
            "remaining_exit_quantity",
        ):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if self.entry_quantity <= 0:
            raise ValueError("entry_quantity must be positive")
        if not 0 <= self.remaining_exit_quantity <= self.entry_quantity:
            raise ValueError("remaining_exit_quantity must be between zero and entry_quantity")
        if self.low_water_mark > self.high_water_mark:
            raise ValueError("low_water_mark must not exceed high_water_mark")
        if self.max_favorable_excursion < 0:
            raise ValueError("max_favorable_excursion must be a non-negative fractional return")
        if self.max_adverse_excursion > 0:
            raise ValueError("max_adverse_excursion must be a non-positive fractional return")
        if (
            self.activation is RuleActivation.INACTIVE
            and self.action is not PositionActionType.HOLD
        ):
            raise ValueError("inactive position rules require hold action")
        if self.activation in {RuleActivation.TRIGGERED, RuleActivation.COMPLETE} and (
            self.exit_reason is ExitReason.NONE
        ):
            raise ValueError("triggered and complete position rules require an exit reason")
        if self.activation is RuleActivation.COMPLETE and self.remaining_exit_quantity != 0:
            raise ValueError("complete position rules require zero remaining exit quantity")
        if self.action in {PositionActionType.HOLD, PositionActionType.ADJUST_STOP}:
            if self.exit_reason is not ExitReason.NONE:
                raise ValueError("hold and adjust_stop actions require exit reason none")
        elif self.exit_reason is ExitReason.NONE:
            raise ValueError("exit action requires an exit reason")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible position-rule state."""
        return {
            "policy_id": self.policy_id,
            "asset": self.asset,
            "activation": self.activation.value,
            "entry_time": self.entry_time.isoformat(),
            "entry_price": self.entry_price,
            "entry_quantity": self.entry_quantity,
            "high_water_mark": self.high_water_mark,
            "low_water_mark": self.low_water_mark,
            "max_favorable_excursion": self.max_favorable_excursion,
            "max_adverse_excursion": self.max_adverse_excursion,
            "remaining_exit_quantity": self.remaining_exit_quantity,
            "idempotency_key": self.idempotency_key,
            "action": self.action.value,
            "exit_reason": self.exit_reason.value,
            "evaluation_mode": self.evaluation_mode.value,
            "lifecycle_version": self.lifecycle_version.value,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> PositionRuleState:
        """Restore and validate position-rule state."""
        return cls(
            policy_id=value["policy_id"],
            asset=value["asset"],
            activation=RuleActivation(value["activation"]),
            entry_time=datetime.fromisoformat(value["entry_time"]),
            entry_price=value["entry_price"],
            entry_quantity=value["entry_quantity"],
            high_water_mark=value["high_water_mark"],
            low_water_mark=value["low_water_mark"],
            max_favorable_excursion=value["max_favorable_excursion"],
            max_adverse_excursion=value["max_adverse_excursion"],
            remaining_exit_quantity=value["remaining_exit_quantity"],
            idempotency_key=value["idempotency_key"],
            action=PositionActionType(value["action"]),
            exit_reason=ExitReason(value["exit_reason"]),
            evaluation_mode=EvaluationMode(value["evaluation_mode"]),
            lifecycle_version=value["lifecycle_version"],
        )


@dataclass(frozen=True, slots=True)
class IntentComparison:
    """Field-level canonical-intent comparison result."""

    equivalent: bool
    differences: tuple[str, ...]


def _compare_intent_records(
    left_record: Mapping[str, Any], right_record: Mapping[str, Any]
) -> IntentComparison:
    differences = tuple(key for key in left_record if left_record.get(key) != right_record.get(key))
    return IntentComparison(not differences, differences)


def compare_target_intents(
    left: CanonicalTargetIntent, right: CanonicalTargetIntent
) -> IntentComparison:
    """Return an exact field-level diff, including identity and decision timestamps."""
    return _compare_intent_records(left.to_dict(), right.to_dict())


def compare_child_intents(
    left: CanonicalChildOrderIntent, right: CanonicalChildOrderIntent
) -> IntentComparison:
    """Return an exact field-level diff of child records before venue fill outcomes."""
    return _compare_intent_records(left.to_dict(), right.to_dict())


def validate_child_lineage(target: CanonicalTargetIntent, child: CanonicalChildOrderIntent) -> None:
    """Require child identity, lifecycle version, phase, and asset lineage."""
    if child.target_intent_id != target.intent_id:
        raise ValueError("child target_intent_id does not match target")
    if child.lifecycle_version is not target.lifecycle_version:
        raise ValueError("child lifecycle version does not match target")
    if child.asset not in {item.asset for item in target.targets}:
        raise ValueError("child asset is absent from target")
    if child.decision_session != target.effective_session:
        raise ValueError("child decision session does not match target effective session")
    if child.effective_session > target.effective_session:
        return
    target_rank = LIFECYCLE_V1.phase_spec(target.effective_phase).causal_rank
    child_rank = LIFECYCLE_V1.phase_spec(child.eligibility_phase).causal_rank
    if child_rank < target_rank:
        raise ValueError("child eligibility phase precedes target effective phase")


def canonical_intent_fixture() -> dict[str, Any]:
    """Return the golden contract fixture consumed by both engines."""
    target = CanonicalTargetIntent(
        intent_id="target-1",
        decision_time=datetime(2026, 8, 8, 13, 0, tzinfo=UTC),
        information_cutoff=datetime(2026, 8, 8, 12, 59, 59, tzinfo=UTC),
        effective_session=date(2026, 8, 10),
        effective_phase=LifecyclePhase.PRE_OPEN,
        targets=(AssetTarget("SPY", TargetMeasure.WEIGHT, 0.5),),
        idempotency_key="target-2026-08-10",
        measure=TargetMeasure.WEIGHT,
        cash_buffer=0.05,
        rounding=RoundingPolicy.TOWARD_ZERO,
        residual=ResidualPolicy.KEEP_CASH,
        reason=IntentReason.REBALANCE,
    )
    child = CanonicalChildOrderIntent(
        child_intent_id="child-1",
        target_intent_id=target.intent_id,
        idempotency_key="child-2026-08-10-SPY",
        asset="SPY",
        side=OrderSide.BUY,
        quantity=10,
        order_type=OrderType.MARKET,
        parameters=OrderParameters(),
        decision_session=date(2026, 8, 10),
        effective_session=date(2026, 8, 10),
        eligibility_phase=LifecyclePhase.PRE_OPEN,
        fill_eligibility=FillEligibility.OPENING_AUCTION,
        time_in_force=TimeInForce.OPG,
        session_policy=SessionPolicy.REGULAR,
        capabilities=(ExecutionCapability.OPENING_AUCTION,),
        reason=IntentReason.REBALANCE,
    )
    return {"target": target.to_dict(), "child": child.to_dict()}


__all__ = [
    "AssetTarget",
    "BarPathPolicy",
    "CanonicalChildOrderIntent",
    "CanonicalTargetIntent",
    "EvaluationMode",
    "ExecutionBehavior",
    "ExecutionCapability",
    "ExecutionPolicy",
    "ExitReason",
    "FillEligibility",
    "IntentComparison",
    "IntentReason",
    "OrderParameters",
    "OrderSide",
    "OrderType",
    "PositionActionType",
    "PositionRuleDefinition",
    "PositionRulePolicy",
    "PositionRuleState",
    "PositionRuleType",
    "ResidualPolicy",
    "RoundingPolicy",
    "RuleActivation",
    "RuleComposition",
    "SessionPolicy",
    "TargetMeasure",
    "TimeInForce",
    "canonical_intent_fixture",
    "compare_child_intents",
    "compare_target_intents",
    "validate_child_against_policy",
    "validate_child_lineage",
]
