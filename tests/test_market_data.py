from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from ml4t.specs import (
    ArtifactKind,
    ArtifactProvenance,
    ArtifactStorage,
    FeedSpec,
    MarketDataSchema,
    MarketDataSemantics,
    MarketDataSpec,
    TimestampSemantics,
    optional_str,
    serialize_artifact_value,
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


def test_market_data_spec_rejects_conflicting_kind() -> None:
    with pytest.raises(ValueError, match="kind"):
        MarketDataSpec.from_mapping({"artifact_id": "prices", "kind": "features"})


@pytest.mark.parametrize("artifact_id", ["", "   "])
def test_market_data_spec_rejects_empty_artifact_id(artifact_id: str) -> None:
    with pytest.raises(ValueError, match="artifact_id"):
        MarketDataSpec(artifact_id=artifact_id)


@pytest.mark.parametrize("version", [True, 0, -1])
def test_market_data_spec_rejects_invalid_version(version: int) -> None:
    with pytest.raises(ValueError, match="version"):
        MarketDataSpec(artifact_id="prices", version=version)


@pytest.mark.parametrize("field", ["storage", "provenance", "schema", "semantics"])
def test_market_data_spec_rejects_non_mapping_nested_payload(field: str) -> None:
    with pytest.raises(TypeError, match=field):
        MarketDataSpec.from_mapping({"artifact_id": "prices", field: []})


def test_storage_rejects_invalid_partition_columns() -> None:
    with pytest.raises(TypeError, match="partition_by"):
        ArtifactStorage.from_mapping({"partition_by": 1})


def test_artifact_helpers_normalize_storage_and_provenance() -> None:
    storage = ArtifactStorage.from_mapping(
        {"path": Path("bars.parquet"), "format": "parquet", "partition_by": "symbol"}
    )
    provenance = ArtifactProvenance.from_mapping(
        {"source_artifacts": "raw-bars", "content_hash": 123, "created_by": ""}
    )

    assert storage.partition_by == ("symbol",)
    assert provenance.source_artifacts == ("raw-bars",)
    assert provenance.content_hash == "123"
    assert provenance.created_by is None
    assert ArtifactStorage.from_mapping(None) == ArtifactStorage()
    assert ArtifactProvenance.from_mapping(None) == ArtifactProvenance()


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: ArtifactStorage.from_mapping(cast("Any", [])), "storage"),
        (lambda: ArtifactProvenance.from_mapping(cast("Any", [])), "provenance"),
        (lambda: ArtifactProvenance.from_mapping({"source_artifacts": 1}), "source_artifacts"),
    ],
)
def test_artifact_helpers_reject_malformed_mappings(factory, message: str) -> None:
    with pytest.raises(TypeError, match=message):
        factory()


def test_artifact_value_serialization_handles_nested_supported_values() -> None:
    value = {
        "kind": ArtifactKind.FEATURES,
        "path": Path("features.parquet"),
        "tuple": (ArtifactKind.LABELS,),
        "list": [Path("predictions.parquet")],
    }

    assert serialize_artifact_value(value) == {
        "kind": "features",
        "path": "features.parquet",
        "tuple": ["labels"],
        "list": ["predictions.parquet"],
    }
    assert serialize_artifact_value(1) == 1
    assert optional_str(None) is None
    assert optional_str(12) == "12"


def test_feed_spec_from_flat_aliases_and_overrides() -> None:
    spec = FeedSpec.from_mapping(
        {
            "datetime_col": "date",
            "ticker_col": "ticker",
            "close_col": "settle",
            "frequency": "1d",
            "timestamp_semantics": "session_label",
        }
    )

    assert spec.timestamp_col == "date"
    assert spec.entity_col == "ticker"
    assert spec.price_col == "settle"
    assert spec.close_col == "settle"
    assert spec.data_frequency == "1d"
    assert spec.timestamp_semantics is TimestampSemantics.SESSION_LABEL
    assert spec.with_overrides(price_col=None) is spec
    assert spec.with_overrides(price_col="adjusted_close").price_col == "adjusted_close"


def test_feed_spec_from_objects_and_defaults() -> None:
    direct = FeedSpec(timestamp_col="ts")
    assert FeedSpec.from_any(direct) is direct
    assert FeedSpec.from_any(None) == FeedSpec()

    nested = SimpleNamespace(
        metadata=SimpleNamespace(
            schema=SimpleNamespace(time_col="date", group_col="asset", price_col="price"),
            semantics=SimpleNamespace(calendar="XNYS", frequency="1d"),
        )
    )
    spec = FeedSpec.from_object(nested)
    assert spec.timestamp_col == "date"
    assert spec.entity_col == "asset"
    assert spec.price_col == "price"
    assert spec.close_col == "price"
    assert spec.calendar == "XNYS"
    assert spec.data_frequency == "1d"

    direct_object = FeedSpec.from_object(SimpleNamespace(time_col="time", group_col="asset"))
    assert direct_object.timestamp_col == "time"
    assert direct_object.entity_col == "asset"

    semantics_only = FeedSpec.from_object(
        SimpleNamespace(schema=None, semantics=SimpleNamespace(calendar="24/7"))
    )
    assert semantics_only.calendar == "24/7"


def test_feed_spec_resolves_explicit_and_detected_entities() -> None:
    explicit = FeedSpec(entity_col=["ticker"])
    assert explicit.resolve(["timestamp", "ticker"], ["symbol"]).entity_col == "ticker"

    detected = FeedSpec(entity_col=None)
    assert detected.resolve(["timestamp", "symbol"], ["asset", "symbol"]).entity_col == "symbol"


def test_feed_spec_resolution_rejects_invalid_columns() -> None:
    with pytest.raises(ValueError, match="timestamp_col"):
        FeedSpec().resolve(["symbol"], ["symbol"])
    with pytest.raises(ValueError, match="entity_col"):
        FeedSpec(entity_col="missing").resolve(["timestamp", "symbol"], ["symbol"])
    with pytest.raises(ValueError, match="Cannot detect"):
        FeedSpec(entity_col=None).resolve(["timestamp"], ["symbol"])
    with pytest.raises(ValueError, match="single entity"):
        FeedSpec(entity_col=["symbol", "venue"]).resolve(
            ["timestamp", "symbol", "venue"], ["symbol"]
        )


def test_feed_spec_empty_entity_sequence_allows_detection() -> None:
    spec = FeedSpec(entity_col=[]).resolve(["timestamp", "symbol"], ["symbol"])
    assert spec.entity_col == "symbol"


def test_schema_and_semantics_mapping_defaults() -> None:
    assert MarketDataSchema.from_mapping(None) == MarketDataSchema()
    assert MarketDataSemantics.from_mapping(None) == MarketDataSemantics()
    assert MarketDataSemantics(
        timestamp_semantics=TimestampSemantics.EVENT_TIME
    ).timestamp_semantics is (TimestampSemantics.EVENT_TIME)


def test_market_data_spec_rejects_non_mapping_payload() -> None:
    with pytest.raises(TypeError, match="market data spec"):
        MarketDataSpec.from_mapping(cast("Any", []))


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"artifact_id": None}, "artifact_id"),
        ({"artifact_id": 123}, "artifact_id"),
        ({"artifact_id": "prices", "version": True}, "version"),
        ({"artifact_id": "prices", "version": "1"}, "version"),
    ],
)
def test_market_data_mapping_rejects_coercible_invalid_identity_fields(
    payload: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        MarketDataSpec.from_mapping(payload)


@pytest.mark.parametrize("field", ["timestamp_col", "entity_col", "price_col", "close_col"])
def test_market_data_schema_rejects_invalid_required_columns(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        MarketDataSchema.from_mapping({field: None})


def test_feed_spec_rejects_malformed_sources() -> None:
    with pytest.raises(TypeError, match="mapping"):
        FeedSpec.from_mapping(cast("Any", []))
    with pytest.raises(TypeError, match="recognized"):
        FeedSpec.from_object(object())


def test_feed_spec_rejects_self_referential_metadata() -> None:
    source = SimpleNamespace()
    source.metadata = source

    with pytest.raises(ValueError, match="reference cycles"):
        FeedSpec.from_object(source)


def test_feed_spec_rejects_indirect_metadata_cycles() -> None:
    first = SimpleNamespace()
    second = SimpleNamespace()
    first.metadata = second
    second.metadata = first

    with pytest.raises(ValueError, match="reference cycles"):
        FeedSpec.from_object(first)
