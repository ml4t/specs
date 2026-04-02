from __future__ import annotations

from ml4t.specs import (
    ArtifactStorage,
    MarketDataSemantics,
    MarketDataSpec,
    TimestampSemantics,
    read_spec_payload,
    write_spec_payload,
)


def test_spec_io_yaml_round_trip(tmp_path) -> None:
    spec = MarketDataSpec.from_mapping(
        {
            "artifact_id": "us_equities_daily_bars_v1",
            "kind": "market_data",
            "storage": {"path": "market_data/prices.parquet", "format": "parquet"},
            "schema": {
                "timestamp_col": "timestamp",
                "entity_col": "asset",
                "open_col": "adj_open",
                "high_col": "adj_high",
                "low_col": "adj_low",
                "close_col": "adj_close",
                "volume_col": "adj_volume",
            },
            "semantics": {
                "data_frequency": "1d",
                "calendar": "NYSE",
                "timezone": "America/New_York",
                "timestamp_semantics": "bar_close",
            },
            "provenance": {"source_artifacts": ["raw_prices_v1"]},
        }
    )

    path = write_spec_payload(spec.to_dict(), tmp_path / "market_data.yaml")
    loaded = MarketDataSpec.from_mapping(read_spec_payload(path))

    assert loaded == spec


def test_spec_io_json_round_trip(tmp_path) -> None:
    spec = MarketDataSpec(
        artifact_id="us_equities_daily_bars_v1",
        storage=ArtifactStorage(path="market_data/prices.parquet"),
        semantics=MarketDataSemantics(
            data_frequency="1d",
            timestamp_semantics=TimestampSemantics.BAR_CLOSE,
        ),
    )

    path = write_spec_payload(spec.to_dict(), tmp_path / "market_data.json")
    loaded = MarketDataSpec.from_mapping(read_spec_payload(path))

    assert loaded == spec
