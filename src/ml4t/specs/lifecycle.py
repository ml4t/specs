"""Versioned runtime-neutral lifecycle and market-event contracts."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from dataclasses import field as dataclass_field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, ClassVar

from ._validation import finite as _finite
from ._validation import non_empty as _non_empty
from ._validation import require_fields as _require_fields
from ._validation import utc as _utc


class LifecycleVersion(StrEnum):
    """Portable lifecycle contract versions."""

    V1 = "1"


class LifecyclePhase(StrEnum):
    """Portable strategy phase labels in serialization order."""

    RUN_START = "run_start"
    CAUSAL_INITIALIZATION = "causal_initialization"
    PRE_OPEN = "pre_open"
    OPENING_AUCTION = "opening_auction"
    FILL_RECONCILIATION = "fill_reconciliation"
    INTRABAR = "intrabar"
    CLOSE = "close"
    MARKET_EVENT = "market_event"
    RUN_END = "run_end"


class InformationField(StrEnum):
    """Information classes whose visibility depends on lifecycle phase."""

    PRIOR_COMPLETED_DATA = "prior_completed_data"
    OFFICIAL_OPEN = "official_open"
    CURRENT_OPEN = "current_open"
    CURRENT_HIGH = "current_high"
    CURRENT_LOW = "current_low"
    RUNNING_HIGH = "running_high"
    RUNNING_LOW = "running_low"
    CURRENT_CLOSE = "current_close"
    POST_FILL_STATE = "post_fill_state"


class CallbackCardinality(StrEnum):
    """Required callback invocation count."""

    EXACTLY_ONCE = "exactly_once"
    ONCE_PER_EVENT = "once_per_event"


class CallbackExceptionSemantics(StrEnum):
    """Required behavior when a callback raises."""

    ABORT_BEFORE_SIDE_EFFECTS = "abort_before_side_effects"
    ROLLBACK_AND_ABORT = "rollback_and_abort"
    CLEANUP_AND_RERAISE = "cleanup_and_reraise"


class MarketEventKind(StrEnum):
    """Portable market-event payload kinds."""

    BAR = "bar"
    TRADE = "trade"
    QUOTE = "quote"
    FUNDING = "funding"


class EventCompletion(StrEnum):
    """Whether an event can still change at its event identity."""

    EVOLVING = "evolving"
    COMPLETE = "complete"


class UnsupportedLifecycleVersionError(ValueError):
    """Raised before side effects when a lifecycle version is unsupported."""

    def __init__(self, requested: object, required_phase: LifecyclePhase | None = None) -> None:
        self.requested = str(requested)
        self.required_phase = required_phase
        self.supported_versions = tuple(version.value for version in LifecycleVersion)
        phase = required_phase.value if required_phase is not None else "contract negotiation"
        supported = ", ".join(self.supported_versions)
        super().__init__(
            f"Unsupported lifecycle version {self.requested!r} for {phase}; supported: {supported}"
        )


class HistoricalStrategyCompatibilityError(ValueError):
    """Raised when historical-data callbacks cannot satisfy the portable lifecycle."""

    def __init__(self, strategy: str, callback: str, required_phase: LifecyclePhase) -> None:
        self.strategy = strategy
        self.callback = callback
        self.required_phase = required_phase
        self.supported_versions = tuple(version.value for version in LifecycleVersion)
        super().__init__(
            f"Strategy {strategy!r} callback {callback!r} is incompatible with lifecycle phase "
            f"{required_phase.value!r}; supported versions: {', '.join(self.supported_versions)}"
        )


class ProhibitedFieldAccessError(ValueError):
    """Raised when a phase attempts to observe causally unavailable information."""


class LifecycleCountError(ValueError):
    """Raised when callback invocation counts violate the contract."""


def _json_metadata(value: object, path: str = "metadata") -> object:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must contain finite numbers")
        return value
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise TypeError(f"{path} keys must be non-empty strings")
            result[key] = _json_metadata(item, f"{path}.{key}")
        return result
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_json_metadata(item, f"{path}[]") for item in value]
    raise TypeError(f"{path} must contain only JSON-compatible values")


def _freeze_json(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return tuple(_freeze_json(item) for item in value)
    return value


def _provider_sequence(value: object, name: str) -> str | int | None:
    if isinstance(value, bool) or not isinstance(value, str | int | None):
        raise TypeError(f"{name} must be a string, integer, or None")
    if isinstance(value, str):
        return _non_empty(value, name)
    if isinstance(value, int) and value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


@dataclass(frozen=True, slots=True)
class GapEvidence:
    """Evidence that a provider sequence is continuous or has a known gap."""

    detected: bool
    reason: str
    previous_sequence: str | int | None = None
    current_sequence: str | int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.detected, bool):
            raise TypeError("detected must be a bool")
        object.__setattr__(self, "reason", _non_empty(self.reason, "gap reason"))
        object.__setattr__(
            self,
            "previous_sequence",
            _provider_sequence(self.previous_sequence, "previous_sequence"),
        )
        object.__setattr__(
            self,
            "current_sequence",
            _provider_sequence(self.current_sequence, "current_sequence"),
        )
        if self.detected and (self.previous_sequence is None or self.current_sequence is None):
            raise ValueError("detected gap requires previous_sequence and current_sequence")
        if self.detected and type(self.previous_sequence) is not type(self.current_sequence):
            raise TypeError("detected gap sequences must have the same type")
        if self.detected and self.previous_sequence == self.current_sequence:
            raise ValueError("detected gap sequences must differ")
        if (
            self.detected
            and isinstance(self.previous_sequence, int)
            and isinstance(self.current_sequence, int)
            and self.previous_sequence >= self.current_sequence
        ):
            raise ValueError("detected integer gap sequences must increase")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> GapEvidence:
        _require_fields(value, "detected", "reason")
        return cls(
            detected=value["detected"],
            reason=value["reason"],
            previous_sequence=value.get("previous_sequence"),
            current_sequence=value.get("current_sequence"),
        )


@dataclass(frozen=True, slots=True)
class BarPayload:
    """Validated OHLCV event payload."""

    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        values = {
            name: _finite(getattr(self, name), name)
            for name in ("open", "high", "low", "close", "volume")
        }
        for name, value in values.items():
            object.__setattr__(self, name, value)
        if values["volume"] < 0:
            raise ValueError("volume must be non-negative")
        if values["high"] < max(values["open"], values["low"], values["close"]):
            raise ValueError("high must be at least open, low, and close")
        if values["low"] > min(values["open"], values["high"], values["close"]):
            raise ValueError("low must be at most open, high, and close")


@dataclass(frozen=True, slots=True)
class TradePayload:
    """Validated trade event payload."""

    price: float
    size: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "price", _finite(self.price, "price"))
        size = _finite(self.size, "size")
        object.__setattr__(self, "size", size)
        if size < 0:
            raise ValueError("size must be non-negative")


@dataclass(frozen=True, slots=True)
class QuotePayload:
    """Validated quote payload that preserves locked and crossed feed observations."""

    bid: float
    ask: float
    bid_size: float
    ask_size: float

    def __post_init__(self) -> None:
        bid = _finite(self.bid, "bid")
        ask = _finite(self.ask, "ask")
        bid_size = _finite(self.bid_size, "bid_size")
        ask_size = _finite(self.ask_size, "ask_size")
        object.__setattr__(self, "bid", bid)
        object.__setattr__(self, "ask", ask)
        object.__setattr__(self, "bid_size", bid_size)
        object.__setattr__(self, "ask_size", ask_size)
        if bid_size < 0 or ask_size < 0:
            raise ValueError("quote sizes must be non-negative")


@dataclass(frozen=True, slots=True)
class FundingPayload:
    """Validated funding-rate event payload."""

    rate: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "rate", _finite(self.rate, "rate"))


MarketEventPayload = BarPayload | TradePayload | QuotePayload | FundingPayload

_PAYLOAD_TYPES: dict[MarketEventKind, type[MarketEventPayload]] = {
    MarketEventKind.BAR: BarPayload,
    MarketEventKind.TRADE: TradePayload,
    MarketEventKind.QUOTE: QuotePayload,
    MarketEventKind.FUNDING: FundingPayload,
}


@dataclass(frozen=True, slots=True)
class MarketEvent:
    """Versioned event identity with validated payload and gap evidence.

    Events are unhashable because JSON metadata may contain mappings and sequences.
    """

    version: LifecycleVersion
    event_time: datetime
    receipt_time: datetime
    kind: MarketEventKind
    completion: EventCompletion
    source: str
    asset: str
    payload: MarketEventPayload
    provider_sequence: str | int | None = None
    gap: GapEvidence | None = None
    metadata: Mapping[str, Any] = dataclass_field(default_factory=dict)
    __hash__ = None

    def __post_init__(self) -> None:
        version = negotiate_lifecycle_version(self.version)
        kind = self.kind if isinstance(self.kind, MarketEventKind) else MarketEventKind(self.kind)
        completion = (
            self.completion
            if isinstance(self.completion, EventCompletion)
            else EventCompletion(self.completion)
        )
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "completion", completion)
        object.__setattr__(self, "event_time", _utc(self.event_time, "event_time"))
        object.__setattr__(self, "receipt_time", _utc(self.receipt_time, "receipt_time"))
        if self.receipt_time < self.event_time:
            raise ValueError("receipt_time must not precede event_time")
        object.__setattr__(self, "source", _non_empty(self.source, "source"))
        object.__setattr__(self, "asset", _non_empty(self.asset, "asset"))
        if not isinstance(self.payload, _PAYLOAD_TYPES[kind]):
            raise TypeError(f"{kind.value} event requires {_PAYLOAD_TYPES[kind].__name__}")
        if self.provider_sequence is None and self.gap is None:
            raise ValueError("provider_sequence or gap evidence is required")
        if self.gap is not None and not isinstance(self.gap, GapEvidence):
            raise TypeError("gap must be GapEvidence or None")
        object.__setattr__(
            self,
            "provider_sequence",
            _provider_sequence(self.provider_sequence, "provider_sequence"),
        )
        if (
            self.gap is not None
            and self.gap.current_sequence is not None
            and self.gap.current_sequence != self.provider_sequence
        ):
            raise ValueError("gap current_sequence must match provider_sequence")
        metadata = _json_metadata(self.metadata)
        if not isinstance(metadata, dict):
            raise TypeError("metadata must be a mapping")
        object.__setattr__(self, "metadata", _freeze_json(metadata))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible event record."""
        return {
            "version": self.version.value,
            "event_time": self.event_time.isoformat(),
            "receipt_time": self.receipt_time.isoformat(),
            "kind": self.kind.value,
            "completion": self.completion.value,
            "source": self.source,
            "asset": self.asset,
            "payload": asdict(self.payload),
            "provider_sequence": self.provider_sequence,
            "gap": asdict(self.gap) if self.gap is not None else None,
            "metadata": _json_metadata(self.metadata),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> MarketEvent:
        """Restore and validate an event record."""
        _require_fields(
            value,
            "version",
            "event_time",
            "receipt_time",
            "kind",
            "completion",
            "source",
            "asset",
            "payload",
        )
        kind = MarketEventKind(value["kind"])
        payload_value = value["payload"]
        if not isinstance(payload_value, Mapping):
            raise TypeError("payload must be a mapping")
        gap_value = value.get("gap")
        if gap_value is not None and not isinstance(gap_value, Mapping):
            raise TypeError("gap must be a mapping or None")
        metadata = value.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise TypeError("metadata must be a mapping")
        return cls(
            version=value["version"],
            event_time=datetime.fromisoformat(value["event_time"]),
            receipt_time=datetime.fromisoformat(value["receipt_time"]),
            kind=kind,
            completion=value["completion"],
            source=value["source"],
            asset=value["asset"],
            payload=_PAYLOAD_TYPES[kind](**payload_value),
            provider_sequence=value.get("provider_sequence"),
            gap=GapEvidence.from_mapping(gap_value) if gap_value is not None else None,
            metadata=metadata,
        )


_EVENT_COMPLETION_BY_PHASE = {
    LifecyclePhase.OPENING_AUCTION: EventCompletion.COMPLETE,
    LifecyclePhase.INTRABAR: EventCompletion.COMPLETE,
    LifecyclePhase.CLOSE: EventCompletion.COMPLETE,
    LifecyclePhase.MARKET_EVENT: EventCompletion.EVOLVING,
}


def validate_event_against_phase(event: MarketEvent, phase: LifecyclePhase) -> None:
    """Require event completion state to match its portable callback phase."""
    if not isinstance(event, MarketEvent):
        raise TypeError("event must be a MarketEvent")
    phase = LifecyclePhase(phase)
    expected = _EVENT_COMPLETION_BY_PHASE.get(phase)
    if expected is None:
        raise ValueError(f"phase {phase.value!r} does not deliver market events")
    if event.completion is not expected:
        raise ValueError(
            f"phase {phase.value!r} requires {expected.value!r} event completion, "
            f"received {event.completion.value!r}"
        )


@dataclass(frozen=True, slots=True)
class LifecyclePhaseSpec:
    """Callback, visibility, intent, count, and exception contract for one phase."""

    phase: LifecyclePhase
    callback: str
    visible_fields: tuple[InformationField, ...]
    intents_allowed: bool
    cardinality: CallbackCardinality
    exception_semantics: CallbackExceptionSemantics
    causal_rank: int
    current_phase_fill_conflicts: tuple[InformationField, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "phase", LifecyclePhase(self.phase))
        visible_fields = tuple(InformationField(field) for field in self.visible_fields)
        if len(set(visible_fields)) != len(visible_fields):
            raise ValueError("visible_fields must be unique")
        object.__setattr__(
            self,
            "visible_fields",
            tuple(sorted(visible_fields, key=lambda field: field.value)),
        )
        fill_conflicts = tuple(
            InformationField(field) for field in self.current_phase_fill_conflicts
        )
        if len(set(fill_conflicts)) != len(fill_conflicts):
            raise ValueError("current_phase_fill_conflicts must be unique")
        object.__setattr__(
            self,
            "current_phase_fill_conflicts",
            tuple(sorted(fill_conflicts, key=lambda field: field.value)),
        )
        object.__setattr__(self, "cardinality", CallbackCardinality(self.cardinality))
        object.__setattr__(
            self,
            "exception_semantics",
            CallbackExceptionSemantics(self.exception_semantics),
        )
        if not isinstance(self.intents_allowed, bool):
            raise TypeError("intents_allowed must be a bool")
        object.__setattr__(self, "callback", _non_empty(self.callback, "callback"))
        if isinstance(self.causal_rank, bool) or not isinstance(self.causal_rank, int):
            raise TypeError("causal_rank must be an integer")
        if self.causal_rank < 0:
            raise ValueError("causal_rank must be non-negative")
        if not set(self.current_phase_fill_conflicts).issubset(self.visible_fields):
            raise ValueError("current_phase_fill_conflicts must be visible in the phase")

    def require_visible(self, field: InformationField) -> None:
        """Reject information that is unavailable in this phase."""
        if field not in self.visible_fields:
            raise ProhibitedFieldAccessError(
                f"{field.value} is not visible during {self.phase.value}"
            )

    def validate_count(self, observed: int, event_count: int | None = None) -> None:
        """Validate callback invocation count for this phase."""
        expected = 1 if self.cardinality is CallbackCardinality.EXACTLY_ONCE else event_count
        if expected is None:
            raise ValueError("event_count is required for once-per-event callbacks")
        if observed != expected:
            raise LifecycleCountError(
                f"{self.callback} expected {expected} invocation(s), observed {observed}"
            )


@dataclass(frozen=True, slots=True)
class LifecycleContract:
    """One complete portable lifecycle version in serialization order."""

    version: LifecycleVersion
    phases: tuple[LifecyclePhaseSpec, ...]

    _EXPECTED_PHASES: ClassVar[tuple[LifecyclePhase, ...]] = tuple(LifecyclePhase)

    def __post_init__(self) -> None:
        object.__setattr__(self, "version", negotiate_lifecycle_version(self.version))
        object.__setattr__(self, "phases", tuple(self.phases))
        if any(not isinstance(spec, LifecyclePhaseSpec) for spec in self.phases):
            raise TypeError("each phase must be a LifecyclePhaseSpec")
        observed = tuple(spec.phase for spec in self.phases)
        if observed != self._EXPECTED_PHASES:
            raise ValueError(
                "lifecycle phases must be complete, unique, and in contract order: "
                + ", ".join(phase.value for phase in self._EXPECTED_PHASES)
            )
        registered_phases = _REGISTERED_LIFECYCLE_PHASES[self.version]
        if self.phases != registered_phases:
            raise ValueError(
                f"lifecycle contract does not match registered version {self.version.value!r}"
            )

    def phase_spec(self, phase: LifecyclePhase) -> LifecyclePhaseSpec:
        """Return the specification for one phase."""
        return self.phases[self._EXPECTED_PHASES.index(phase)]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible lifecycle specification."""
        return {
            "version": self.version.value,
            "phases": [
                {
                    "phase": spec.phase.value,
                    "callback": spec.callback,
                    "visible_fields": [field.value for field in spec.visible_fields],
                    "intents_allowed": spec.intents_allowed,
                    "cardinality": spec.cardinality.value,
                    "exception_semantics": spec.exception_semantics.value,
                    "causal_rank": spec.causal_rank,
                    "current_phase_fill_conflicts": [
                        field.value for field in spec.current_phase_fill_conflicts
                    ],
                }
                for spec in self.phases
            ],
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> LifecycleContract:
        """Restore and validate a lifecycle specification."""
        _require_fields(value, "version", "phases")
        version = negotiate_lifecycle_version(value["version"])
        raw_phases = value["phases"]
        if not isinstance(raw_phases, Sequence) or isinstance(raw_phases, str | bytes):
            raise TypeError("phases must be a sequence")
        if any(not isinstance(raw, Mapping) for raw in raw_phases):
            raise TypeError("each phase must be a mapping")
        for raw in raw_phases:
            _require_fields(
                raw,
                "phase",
                "callback",
                "visible_fields",
                "intents_allowed",
                "cardinality",
                "exception_semantics",
                "causal_rank",
                "current_phase_fill_conflicts",
            )
        phases = tuple(
            LifecyclePhaseSpec(
                phase=LifecyclePhase(raw["phase"]),
                callback=raw["callback"],
                visible_fields=tuple(InformationField(field) for field in raw["visible_fields"]),
                intents_allowed=raw["intents_allowed"],
                cardinality=CallbackCardinality(raw["cardinality"]),
                exception_semantics=CallbackExceptionSemantics(raw["exception_semantics"]),
                causal_rank=raw["causal_rank"],
                current_phase_fill_conflicts=tuple(
                    InformationField(field) for field in raw["current_phase_fill_conflicts"]
                ),
            )
            for raw in raw_phases
        )
        return cls(version=version, phases=phases)


def negotiate_lifecycle_version(
    requested: LifecycleVersion | str, required_phase: LifecyclePhase | None = None
) -> LifecycleVersion:
    """Return a supported version or fail before engine side effects."""
    try:
        return requested if isinstance(requested, LifecycleVersion) else LifecycleVersion(requested)
    except ValueError as error:
        raise UnsupportedLifecycleVersionError(requested, required_phase) from error


def require_historical_strategy_compatibility(strategy: str, callback_names: Sequence[str]) -> None:
    """Reject callbacks that expose non-causal historical initialization."""
    if isinstance(callback_names, str | bytes):
        raise TypeError("callback_names must be a sequence of callback names")
    if "on_historical_data" in callback_names:
        raise HistoricalStrategyCompatibilityError(
            strategy,
            "on_historical_data",
            LifecyclePhase.CAUSAL_INITIALIZATION,
        )


_PRIOR = (InformationField.PRIOR_COMPLETED_DATA,)
_OPEN = _PRIOR + (InformationField.OFFICIAL_OPEN, InformationField.CURRENT_OPEN)
_INTRABAR = _OPEN + (InformationField.CURRENT_HIGH, InformationField.CURRENT_LOW)
_MARKET_EVENT = _OPEN + (InformationField.RUNNING_HIGH, InformationField.RUNNING_LOW)
_COMPLETE = _INTRABAR + (InformationField.CURRENT_CLOSE,)

_LIFECYCLE_V1_PHASES = (
    LifecyclePhaseSpec(
        LifecyclePhase.RUN_START,
        "on_start",
        (),
        False,
        CallbackCardinality.EXACTLY_ONCE,
        CallbackExceptionSemantics.ABORT_BEFORE_SIDE_EFFECTS,
        0,
    ),
    LifecyclePhaseSpec(
        LifecyclePhase.CAUSAL_INITIALIZATION,
        "on_prepare",
        _PRIOR,
        True,
        CallbackCardinality.EXACTLY_ONCE,
        CallbackExceptionSemantics.ABORT_BEFORE_SIDE_EFFECTS,
        1,
    ),
    LifecyclePhaseSpec(
        LifecyclePhase.PRE_OPEN,
        "on_pre_open",
        _PRIOR,
        True,
        CallbackCardinality.ONCE_PER_EVENT,
        CallbackExceptionSemantics.ROLLBACK_AND_ABORT,
        2,
    ),
    LifecyclePhaseSpec(
        LifecyclePhase.OPENING_AUCTION,
        "on_open",
        _OPEN,
        True,
        CallbackCardinality.ONCE_PER_EVENT,
        CallbackExceptionSemantics.ROLLBACK_AND_ABORT,
        3,
        (InformationField.OFFICIAL_OPEN, InformationField.CURRENT_OPEN),
    ),
    LifecyclePhaseSpec(
        LifecyclePhase.FILL_RECONCILIATION,
        "on_fill_reconciliation",
        _OPEN + (InformationField.POST_FILL_STATE,),
        False,
        CallbackCardinality.ONCE_PER_EVENT,
        CallbackExceptionSemantics.ROLLBACK_AND_ABORT,
        4,
    ),
    LifecyclePhaseSpec(
        LifecyclePhase.INTRABAR,
        "on_intrabar",
        _INTRABAR,
        True,
        CallbackCardinality.ONCE_PER_EVENT,
        CallbackExceptionSemantics.ROLLBACK_AND_ABORT,
        5,
        (InformationField.CURRENT_HIGH, InformationField.CURRENT_LOW),
    ),
    LifecyclePhaseSpec(
        LifecyclePhase.CLOSE,
        "on_close",
        _COMPLETE,
        True,
        CallbackCardinality.ONCE_PER_EVENT,
        CallbackExceptionSemantics.ROLLBACK_AND_ABORT,
        6,
        (InformationField.CURRENT_CLOSE,),
    ),
    LifecyclePhaseSpec(
        LifecyclePhase.MARKET_EVENT,
        "on_data",
        _MARKET_EVENT,
        True,
        CallbackCardinality.ONCE_PER_EVENT,
        CallbackExceptionSemantics.ROLLBACK_AND_ABORT,
        5,
    ),
    LifecyclePhaseSpec(
        LifecyclePhase.RUN_END,
        "on_end",
        _COMPLETE + (InformationField.POST_FILL_STATE,),
        False,
        CallbackCardinality.EXACTLY_ONCE,
        CallbackExceptionSemantics.CLEANUP_AND_RERAISE,
        7,
    ),
)

_REGISTERED_LIFECYCLE_PHASES = {
    LifecycleVersion.V1: _LIFECYCLE_V1_PHASES,
}

LIFECYCLE_V1 = LifecycleContract(
    version=LifecycleVersion.V1,
    phases=_LIFECYCLE_V1_PHASES,
)


def lifecycle_contract(version: LifecycleVersion | str) -> LifecycleContract:
    """Return the canonical contract for a supported lifecycle version."""
    negotiated = negotiate_lifecycle_version(version)
    try:
        phases = _REGISTERED_LIFECYCLE_PHASES[negotiated]
    except KeyError as error:
        raise UnsupportedLifecycleVersionError(negotiated) from error
    return LifecycleContract(version=negotiated, phases=phases)


def lifecycle_schema() -> dict[str, Any]:
    """Return the generated JSON-schema document for the supported lifecycle version."""
    phase_schemas = []
    for spec in LIFECYCLE_V1.phases:
        visible_fields = [{"const": field.value} for field in spec.visible_fields]
        visible_fields_schema: dict[str, Any] = {
            "type": "array",
            "items": False,
            "minItems": len(visible_fields),
            "maxItems": len(visible_fields),
        }
        if visible_fields:
            visible_fields_schema["prefixItems"] = visible_fields
        fill_fields = [{"const": field.value} for field in spec.current_phase_fill_conflicts]
        fill_fields_schema: dict[str, Any] = {
            "type": "array",
            "items": False,
            "minItems": len(fill_fields),
            "maxItems": len(fill_fields),
        }
        if fill_fields:
            fill_fields_schema["prefixItems"] = fill_fields
        phase_schemas.append(
            {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "phase",
                    "callback",
                    "visible_fields",
                    "intents_allowed",
                    "cardinality",
                    "exception_semantics",
                    "causal_rank",
                    "current_phase_fill_conflicts",
                ],
                "properties": {
                    "phase": {"const": spec.phase.value},
                    "callback": {"const": spec.callback},
                    "visible_fields": visible_fields_schema,
                    "intents_allowed": {"const": spec.intents_allowed},
                    "cardinality": {"const": spec.cardinality.value},
                    "exception_semantics": {"const": spec.exception_semantics.value},
                    "causal_rank": {"const": spec.causal_rank},
                    "current_phase_fill_conflicts": fill_fields_schema,
                },
            }
        )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "ML4T portable lifecycle contract",
        "type": "object",
        "additionalProperties": False,
        "required": ["version", "phases"],
        "properties": {
            "version": {"const": LifecycleVersion.V1.value},
            "phases": {
                "type": "array",
                "prefixItems": phase_schemas,
                "items": False,
                "minItems": len(LifecyclePhase),
                "maxItems": len(LifecyclePhase),
            },
        },
    }


__all__ = [
    "BarPayload",
    "CallbackCardinality",
    "CallbackExceptionSemantics",
    "EventCompletion",
    "FundingPayload",
    "GapEvidence",
    "HistoricalStrategyCompatibilityError",
    "InformationField",
    "LIFECYCLE_V1",
    "LifecycleContract",
    "LifecycleCountError",
    "LifecyclePhase",
    "LifecyclePhaseSpec",
    "LifecycleVersion",
    "MarketEvent",
    "MarketEventKind",
    "MarketEventPayload",
    "ProhibitedFieldAccessError",
    "QuotePayload",
    "TradePayload",
    "UnsupportedLifecycleVersionError",
    "lifecycle_contract",
    "lifecycle_schema",
    "negotiate_lifecycle_version",
    "require_historical_strategy_compatibility",
    "validate_event_against_phase",
]
