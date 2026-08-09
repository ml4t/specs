from __future__ import annotations

import json
import os
import stat

import pytest

import ml4t.specs.io as spec_io
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


def test_write_spec_payload_accepts_artifact_spec(tmp_path) -> None:
    spec = MarketDataSpec(artifact_id="prices")

    path = write_spec_payload(spec, tmp_path / "market_data.yaml")

    assert MarketDataSpec.from_mapping(read_spec_payload(path)) == spec


@pytest.mark.parametrize("suffix", [".txt", "", ".toml"])
def test_spec_io_rejects_unsupported_extensions(tmp_path, suffix: str) -> None:
    path = tmp_path / f"market_data{suffix}"
    with pytest.raises(ValueError, match="extension"):
        write_spec_payload({"artifact_id": "prices"}, path)
    with pytest.raises(ValueError, match="extension"):
        read_spec_payload(path)


@pytest.mark.parametrize(
    ("content", "suffix"),
    [
        ("- first\n- second\n", ".yaml"),
        ("42\n", ".yaml"),
        (json.dumps(["first", "second"]), ".json"),
        (json.dumps(42), ".json"),
    ],
)
def test_read_spec_payload_rejects_non_mapping_documents(
    tmp_path,
    content: str,
    suffix: str,
) -> None:
    path = tmp_path / f"invalid{suffix}"
    path.write_text(content)

    with pytest.raises(ValueError, match="mapping"):
        read_spec_payload(path)


def test_read_spec_payload_normalizes_mapping_keys(tmp_path) -> None:
    path = tmp_path / "numeric-key.yaml"
    path.write_text("1: value\n")

    assert read_spec_payload(path) == {"1": "value"}


def test_write_spec_payload_does_not_replace_valid_file_on_serialization_error(tmp_path) -> None:
    path = tmp_path / "market_data.json"
    path.write_text('{"artifact_id": "valid"}\n')

    with pytest.raises(TypeError):
        write_spec_payload({"invalid": object()}, path)

    assert read_spec_payload(path) == {"artifact_id": "valid"}


@pytest.mark.skipif(os.name == "nt", reason="Windows does not expose POSIX permission bits")
def test_write_spec_payload_preserves_existing_permissions(tmp_path) -> None:
    path = tmp_path / "market_data.json"
    path.write_text("{}\n")
    path.chmod(0o640)

    write_spec_payload({"artifact_id": "prices"}, path)

    assert stat.S_IMODE(path.stat().st_mode) == 0o640


@pytest.mark.skipif(os.name == "nt", reason="Windows does not expose POSIX permission bits")
def test_write_spec_payload_applies_umask_to_new_files(tmp_path) -> None:
    path = tmp_path / "market_data.json"

    previous_umask = os.umask(0o077)
    try:
        write_spec_payload({"artifact_id": "prices"}, path)
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_write_spec_payload_retries_temporary_name_collisions(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tokens = iter(("collision", "available"))
    monkeypatch.setattr(spec_io, "token_hex", lambda _length: next(tokens))
    path = tmp_path / "market_data.json"
    collision = tmp_path / ".market_data.json.collision"
    collision.write_text("occupied")

    write_spec_payload({"artifact_id": "prices"}, path)

    assert read_spec_payload(path) == {"artifact_id": "prices"}
    assert collision.read_text() == "occupied"


def test_spec_io_supports_yml_and_empty_documents(tmp_path) -> None:
    path = tmp_path / "empty.yml"
    path.write_text("")
    assert read_spec_payload(path) == {}

    write_spec_payload({1: "value"}, path)
    assert read_spec_payload(path) == {"1": "value"}


def test_read_spec_payload_copies_mapping() -> None:
    source = {1: "value"}
    result = read_spec_payload(source)

    assert result == {"1": "value"}
    assert result is not source


def test_write_spec_payload_handles_temporary_file_creation_failure(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_to_create(*_args, **_kwargs):
        raise OSError("no temporary file")

    monkeypatch.setattr(spec_io, "_open_temporary_file", fail_to_create)
    path = tmp_path / "market_data.json"

    with pytest.raises(OSError, match="no temporary file"):
        write_spec_payload({"artifact_id": "prices"}, path)
    assert not path.exists()
