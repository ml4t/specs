from __future__ import annotations

from ml4t.specs import (
    ArtifactKind,
    ArtifactStorage,
    FeedSpec,
    MarketDataSchema,
    MarketDataSemantics,
    MarketDataSpec,
    TimestampSemantics,
)


def test_market_data_spec_from_mapping_normalizes_timestamp_semantics() -> None:
    spec = MarketDataSpec.from_mapping(
        {
            "artifact_id": "nasdaq100_1m_nbbo_v1",
            "kind": "market_data",
            "schema": {
                "timestamp_col": "ts",
                "entity_col": "asset",
                "close_col": "last_trade_price",
                "bid_col": "close_bid_price",
                "ask_col": "close_ask_price",
                "mid_col": "mid_close",
            },
            "semantics": {
                "data_frequency": "1m",
                "calendar": "NYSE",
                "timezone": "America/New_York",
                "timestamp_semantics": "bar_close",
                "session_start_time": "09:30:00",
                "bar_type": "ohlcv_nbbo",
            },
        }
    )

    assert spec.kind == ArtifactKind.MARKET_DATA
    assert spec.schema.entity_col == "asset"
    assert spec.schema.bid_col == "close_bid_price"
    assert spec.schema.ask_col == "close_ask_price"
    assert spec.semantics.timestamp_semantics == TimestampSemantics.BAR_CLOSE


def test_feed_spec_from_market_data_spec() -> None:
    spec = MarketDataSpec(
        artifact_id="prices",
        storage=ArtifactStorage(path="prices.parquet"),
        schema=MarketDataSchema(
            timestamp_col="ts",
            entity_col="ticker",
            price_col="last",
            open_col="o",
            high_col="h",
            low_col="l",
            close_col="c",
            volume_col="vol",
        ),
        semantics=MarketDataSemantics(
            data_frequency="1d",
            calendar="XNYS",
            timezone="UTC",
            timestamp_semantics=TimestampSemantics.BAR_CLOSE,
        ),
    )

    feed_spec = FeedSpec.from_any(spec)

    assert feed_spec.timestamp_col == "ts"
    assert feed_spec.entity_col == "ticker"
    assert feed_spec.price_col == "last"
    assert feed_spec.close_col == "c"
    assert feed_spec.volume_col == "vol"
    assert feed_spec.calendar == "XNYS"
    assert feed_spec.timezone == "UTC"
    assert feed_spec.data_frequency == "1d"
    assert feed_spec.timestamp_semantics is TimestampSemantics.BAR_CLOSE


def test_feed_spec_from_market_data_spec_mapping() -> None:
    spec_dict = MarketDataSpec(
        artifact_id="bars",
        storage=ArtifactStorage(path="bars.parquet"),
        schema=MarketDataSchema(timestamp_col="date", entity_col="asset", close_col="close_px"),
        semantics=MarketDataSemantics(
            data_frequency="1h",
            timestamp_semantics=TimestampSemantics.SESSION_LABEL,
        ),
    ).to_dict()

    feed_spec = FeedSpec.from_any(spec_dict)

    assert feed_spec.timestamp_col == "date"
    assert feed_spec.entity_col == "asset"
    assert feed_spec.close_col == "close_px"
    assert feed_spec.price_col == "close"
    assert feed_spec.data_frequency == "1h"
    assert feed_spec.timestamp_semantics is TimestampSemantics.SESSION_LABEL


def test_market_data_spec_to_feed_spec() -> None:
    spec = MarketDataSpec(
        artifact_id="intraday",
        storage=ArtifactStorage(path="intraday.parquet"),
        schema=MarketDataSchema(timestamp_col="timestamp", entity_col="asset", price_col="mid"),
        semantics=MarketDataSemantics(calendar="24/7"),
    )

    feed_spec = spec.to_feed_spec()

    assert feed_spec.timestamp_col == "timestamp"
    assert feed_spec.entity_col == "asset"
    assert feed_spec.price_col == "mid"
    assert feed_spec.calendar == "24/7"
