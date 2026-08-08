"""Versioned runtime-neutral lifecycle and market-event contracts."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar


class LifecycleVersion(StrEnum):
    """Portable lifecycle contract versions."""

    V1 = "1"


class LifecyclePhase(StrEnum):
    """Ordered portable strategy phases."""

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


def _non_empty(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _utc(value: datetime, name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != UTC.utcoffset(value)
    ):
        raise ValueError(f"{name} must be timezone-aware UTC")
    return value.astimezone(UTC)


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


@dataclass(frozen=True, slots=True)
class GapEvidence:
    """Evidence that a provider sequence is continuous or has a known gap."""

    detected: bool
    reason: str
    previous_sequence: str | None = None
    current_sequence: str | None = None

    def __post_init__(self) -> None:
        _non_empty(self.reason, "gap reason")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> GapEvidence:
        return cls(
            detected=bool(value["detected"]),
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
        if _finite(self.price, "price") <= 0:
            raise ValueError("price must be positive")
        if _finite(self.size, "size") < 0:
            raise ValueError("size must be non-negative")


@dataclass(frozen=True, slots=True)
class QuotePayload:
    """Validated quote event payload."""

    bid: float
    ask: float
    bid_size: float
    ask_size: float

    def __post_init__(self) -> None:
        bid = _finite(self.bid, "bid")
        ask = _finite(self.ask, "ask")
        if bid <= 0 or ask <= 0:
            raise ValueError("bid and ask must be positive")
        if ask < bid:
            raise ValueError("ask must be at least bid")
        if _finite(self.bid_size, "bid_size") < 0 or _finite(self.ask_size, "ask_size") < 0:
            raise ValueError("quote sizes must be non-negative")


@dataclass(frozen=True, slots=True)
class FundingPayload:
    """Validated funding-rate event payload."""

    rate: float

    def __post_init__(self) -> None:
        _finite(self.rate, "rate")


MarketEventPayload = BarPayload | TradePayload | QuotePayload | FundingPayload

_PAYLOAD_TYPES: dict[MarketEventKind, type[MarketEventPayload]] = {
    MarketEventKind.BAR: BarPayload,
    MarketEventKind.TRADE: TradePayload,
    MarketEventKind.QUOTE: QuotePayload,
    MarketEventKind.FUNDING: FundingPayload,
}


@dataclass(frozen=True, slots=True)
class MarketEvent:
    """Versioned event identity with validated payload and gap evidence."""

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
    metadata: Mapping[str, Any] = field(default_factory=dict)

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
        _non_empty(self.source, "source")
        _non_empty(self.asset, "asset")
        if not isinstance(self.payload, _PAYLOAD_TYPES[kind]):
            raise TypeError(f"{kind.value} event requires {_PAYLOAD_TYPES[kind].__name__}")
        if self.provider_sequence is None and self.gap is None:
            raise ValueError("provider_sequence or gap evidence is required")
        if isinstance(self.provider_sequence, bool) or not isinstance(
            self.provider_sequence, str | int | None
        ):
            raise TypeError("provider_sequence must be a string, integer, or None")
        if isinstance(self.provider_sequence, str) and not self.provider_sequence:
            raise ValueError("provider_sequence must not be empty")
        if isinstance(self.provider_sequence, int) and self.provider_sequence < 0:
            raise ValueError("provider_sequence must be non-negative")
        metadata = _json_metadata(self.metadata)
        if not isinstance(metadata, dict):
            raise TypeError("metadata must be a mapping")
        object.__setattr__(self, "metadata", metadata)

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
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> MarketEvent:
        """Restore and validate an event record."""
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


@dataclass(frozen=True, slots=True)
class LifecyclePhaseSpec:
    """Callback, visibility, intent, count, and exception contract for one phase."""

    phase: LifecyclePhase
    callback: str
    visible_fields: tuple[InformationField, ...]
    intents_allowed: bool
    cardinality: CallbackCardinality
    exception_semantics: CallbackExceptionSemantics

    def __post_init__(self) -> None:
        _non_empty(self.callback, "callback")

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
    """One complete ordered portable lifecycle version."""

    version: LifecycleVersion
    phases: tuple[LifecyclePhaseSpec, ...]

    _EXPECTED_PHASES: ClassVar[tuple[LifecyclePhase, ...]] = tuple(LifecyclePhase)

    def __post_init__(self) -> None:
        observed = tuple(spec.phase for spec in self.phases)
        if observed != self._EXPECTED_PHASES:
            raise ValueError(
                "lifecycle phases must be complete, unique, and in contract order: "
                + ", ".join(phase.value for phase in self._EXPECTED_PHASES)
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
                }
                for spec in self.phases
            ],
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> LifecycleContract:
        """Restore and validate a lifecycle specification."""
        version = negotiate_lifecycle_version(value["version"])
        raw_phases = value["phases"]
        if not isinstance(raw_phases, Sequence) or isinstance(raw_phases, str | bytes):
            raise TypeError("phases must be a sequence")
        phases = tuple(
            LifecyclePhaseSpec(
                phase=LifecyclePhase(raw["phase"]),
                callback=raw["callback"],
                visible_fields=tuple(InformationField(field) for field in raw["visible_fields"]),
                intents_allowed=bool(raw["intents_allowed"]),
                cardinality=CallbackCardinality(raw["cardinality"]),
                exception_semantics=CallbackExceptionSemantics(raw["exception_semantics"]),
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
    if "on_historical_data" in callback_names:
        raise HistoricalStrategyCompatibilityError(
            strategy,
            "on_historical_data",
            LifecyclePhase.CAUSAL_INITIALIZATION,
        )


_PRIOR = (InformationField.PRIOR_COMPLETED_DATA,)
_OPEN = _PRIOR + (InformationField.OFFICIAL_OPEN, InformationField.CURRENT_OPEN)
_INTRABAR = _OPEN + (InformationField.CURRENT_HIGH, InformationField.CURRENT_LOW)
_COMPLETE = _INTRABAR + (InformationField.CURRENT_CLOSE,)

LIFECYCLE_V1 = LifecycleContract(
    version=LifecycleVersion.V1,
    phases=(
        LifecyclePhaseSpec(
            LifecyclePhase.RUN_START,
            "on_start",
            (),
            False,
            CallbackCardinality.EXACTLY_ONCE,
            CallbackExceptionSemantics.ABORT_BEFORE_SIDE_EFFECTS,
        ),
        LifecyclePhaseSpec(
            LifecyclePhase.CAUSAL_INITIALIZATION,
            "on_prepare",
            _PRIOR,
            True,
            CallbackCardinality.EXACTLY_ONCE,
            CallbackExceptionSemantics.ABORT_BEFORE_SIDE_EFFECTS,
        ),
        LifecyclePhaseSpec(
            LifecyclePhase.PRE_OPEN,
            "on_pre_open",
            _PRIOR,
            True,
            CallbackCardinality.ONCE_PER_EVENT,
            CallbackExceptionSemantics.ROLLBACK_AND_ABORT,
        ),
        LifecyclePhaseSpec(
            LifecyclePhase.OPENING_AUCTION,
            "on_open",
            _OPEN,
            True,
            CallbackCardinality.ONCE_PER_EVENT,
            CallbackExceptionSemantics.ROLLBACK_AND_ABORT,
        ),
        LifecyclePhaseSpec(
            LifecyclePhase.FILL_RECONCILIATION,
            "on_fill_reconciliation",
            _OPEN + (InformationField.POST_FILL_STATE,),
            False,
            CallbackCardinality.ONCE_PER_EVENT,
            CallbackExceptionSemantics.ROLLBACK_AND_ABORT,
        ),
        LifecyclePhaseSpec(
            LifecyclePhase.INTRABAR,
            "on_intrabar",
            _INTRABAR,
            True,
            CallbackCardinality.ONCE_PER_EVENT,
            CallbackExceptionSemantics.ROLLBACK_AND_ABORT,
        ),
        LifecyclePhaseSpec(
            LifecyclePhase.CLOSE,
            "on_close",
            _COMPLETE,
            True,
            CallbackCardinality.ONCE_PER_EVENT,
            CallbackExceptionSemantics.ROLLBACK_AND_ABORT,
        ),
        LifecyclePhaseSpec(
            LifecyclePhase.MARKET_EVENT,
            "on_data",
            _INTRABAR,
            True,
            CallbackCardinality.ONCE_PER_EVENT,
            CallbackExceptionSemantics.ROLLBACK_AND_ABORT,
        ),
        LifecyclePhaseSpec(
            LifecyclePhase.RUN_END,
            "on_end",
            _COMPLETE + (InformationField.POST_FILL_STATE,),
            False,
            CallbackCardinality.EXACTLY_ONCE,
            CallbackExceptionSemantics.CLEANUP_AND_RERAISE,
        ),
    ),
)


def lifecycle_schema() -> dict[str, Any]:
    """Return the generated JSON-schema document for the supported lifecycle version."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "ML4T portable lifecycle contract",
        "type": "object",
        "required": ["version", "phases"],
        "properties": {
            "version": {"const": LifecycleVersion.V1.value},
            "phases": {
                "type": "array",
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
    "lifecycle_schema",
    "negotiate_lifecycle_version",
    "require_historical_strategy_compatibility",
]
