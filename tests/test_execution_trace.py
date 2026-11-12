from datetime import UTC, datetime

import pytest

from ml4t.specs import ExecutionFill, OrderSide


def test_execution_report_round_trips_without_inventing_missing_fee():
    fill = ExecutionFill(
        order_id="native-1",
        asset="SPY",
        side=OrderSide.BUY,
        quantity=60,
        price=100.01,
        execution_id="exec-1",
        executed_at=datetime(2026, 8, 11, 13, 30, tzinfo=UTC),
        received_at=datetime(2026, 8, 11, 13, 31, tzinfo=UTC),
    )
    assert ExecutionFill.from_mapping(fill.to_dict()) == fill
    assert fill.to_dict()["fee"] is None


@pytest.mark.parametrize(
    ("key", "value"),
    [("quantity", 0), ("price", float("nan")), ("executed_at", "2026-08-11T13:30:00")],
)
def test_invalid_execution_report_cannot_be_deserialized(key, value):
    payload = {
        "order_id": "native-1",
        "asset": "SPY",
        "side": "buy",
        "quantity": 60,
        "price": 100.01,
    }
    payload[key] = value
    with pytest.raises(ValueError, match=key):
        ExecutionFill.from_mapping(payload)


def test_execution_report_retains_fee_currency_and_negative_price():
    fill = ExecutionFill(
        order_id="native-1",
        asset="CL",
        side=OrderSide.SELL,
        quantity=2,
        price=-10,
        venue="NYMEX",
        fee=-0.03,
        fee_currency="USD",
        currency="USD",
        multiplier=1000,
    )
    assert ExecutionFill.from_mapping(fill.to_dict()) == fill
