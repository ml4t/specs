"""Runtime-neutral evidence for an observed incremental execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from ._validation import finite, non_empty, require_fields, utc
from .intents import OrderSide


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionFill:
    """One incremental fill in a run, with nullable provider evidence.

    Execution IDs are unique within a run and venue. A missing ID means the
    fill cannot be safely deduplicated. Fees are in the declared fee currency.
    """

    order_id: str
    asset: str
    side: OrderSide
    quantity: float
    price: float
    execution_id: str | None = None
    venue_order_id: str | None = None
    venue: str | None = None
    executed_at: datetime | None = None
    received_at: datetime | None = None
    fee: float | None = None
    fee_currency: str | None = None
    currency: str | None = None
    multiplier: float | None = None

    def __post_init__(self) -> None:
        for name in ("order_id", "asset"):
            object.__setattr__(self, name, non_empty(getattr(self, name), name))
        for name in ("execution_id", "venue_order_id", "venue", "fee_currency", "currency"):
            if (value := getattr(self, name)) is not None:
                object.__setattr__(self, name, non_empty(value, name))
        object.__setattr__(self, "side", OrderSide(self.side))
        for name in ("quantity", "price", "multiplier"):
            if (value := getattr(self, name)) is None and name == "multiplier":
                continue
            number = finite(value, name)
            if name != "price" and number <= 0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, number)
        if self.fee is not None:
            object.__setattr__(self, "fee", finite(self.fee, "fee"))
        for name in ("executed_at", "received_at"):
            if (stamp := getattr(self, name)) is not None:
                object.__setattr__(self, name, utc(stamp, name))

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""
        return {
            "order_id": self.order_id,
            "asset": self.asset,
            "side": self.side.value,
            "quantity": self.quantity,
            "price": self.price,
            "execution_id": self.execution_id,
            "venue_order_id": self.venue_order_id,
            "venue": self.venue,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "fee": self.fee,
            "fee_currency": self.fee_currency,
            "currency": self.currency,
            "multiplier": self.multiplier,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> ExecutionFill:
        """Read a serialized fill and validate its required fields."""
        require_fields(data, "order_id", "asset", "side", "quantity", "price")
        side = non_empty(data["side"], "side")
        return cls(
            order_id=non_empty(data["order_id"], "order_id"),
            asset=non_empty(data["asset"], "asset"),
            side=OrderSide(side),
            quantity=finite(data["quantity"], "quantity"),
            price=finite(data["price"], "price"),
            execution_id=_optional_string(data, "execution_id"),
            venue_order_id=_optional_string(data, "venue_order_id"),
            venue=_optional_string(data, "venue"),
            executed_at=_optional_time(data, "executed_at"),
            received_at=_optional_time(data, "received_at"),
            fee=_optional_number(data, "fee"),
            fee_currency=_optional_string(data, "fee_currency"),
            currency=_optional_string(data, "currency"),
            multiplier=_optional_number(data, "multiplier"),
        )


def _optional_string(data: Mapping[str, object], key: str) -> str | None:
    value = data.get(key)
    return None if value is None else non_empty(value, key)


def _optional_number(data: Mapping[str, object], key: str) -> float | None:
    value = data.get(key)
    return None if value is None else finite(value, key)


def _optional_time(data: Mapping[str, object], key: str) -> datetime | None:
    value = _optional_string(data, key)
    return None if value is None else datetime.fromisoformat(value)
