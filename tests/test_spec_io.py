from __future__ import annotations

import json
import os
import stat
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import yaml

import ml4t.specs.io as spec_io
from ml4t.specs import (
    ArtifactStorage,
    CanonicalTargetIntent,
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


def test_read_spec_payload_keeps_json_compatible_yaml_scalars(tmp_path) -> None:
    intent_path = tmp_path / "intent.yaml"
    intent_path.write_text(
        """\
intent_id: target-1
decision_time: 2026-08-08T13:00:00+00:00
information_cutoff: 2026-08-08T12:59:59+00:00
effective_session: 2026-08-10
effective_phase: pre_open
targets:
- asset: NO
  measure: weight
  value: 0.5
idempotency_key: target-key
measure: weight
cash_buffer: 0.05
rounding: toward_zero
residual: keep_cash
reason: rebalance
lifecycle_version: '1'
""",
        encoding="utf-8",
    )
    payload = read_spec_payload(intent_path)
    assert isinstance(payload["decision_time"], str)
    assert payload["effective_session"] == "2026-08-10"
    assert payload["targets"][0]["asset"] == "NO"
    intent = CanonicalTargetIntent.from_mapping(payload)
    assert intent.decision_time == datetime(2026, 8, 8, 13, 0, tzinfo=UTC)
    assert intent.information_cutoff == datetime(2026, 8, 8, 12, 59, 59, tzinfo=UTC)
    assert intent.effective_session == date(2026, 8, 10)
    assert intent.targets[0].asset == "NO"

    market_path = tmp_path / "market.yaml"
    market_path.write_text(
        """\
artifact_id: prices
provenance:
  created_by: no
semantics:
  calendar: NYSE
""",
        encoding="utf-8",
    )
    market = read_spec_payload(market_path)
    assert market["provenance"]["created_by"] == "no"
    assert MarketDataSpec.from_mapping(market).provenance.created_by == "no"

    flags = tmp_path / "flags.yaml"
    flags.write_text("enabled: false\nabsent: null\ncount: 2\ntoken: yes\n", encoding="utf-8")
    assert read_spec_payload(flags) == {
        "enabled": False,
        "absent": None,
        "count": 2,
        "token": "yes",
    }
    assert yaml.safe_load("asset: NO\n") == {"asset": False}


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


def test_spec_payload_rejects_keys_that_collide_after_normalization(tmp_path) -> None:
    payload = {1: "numeric", "1": "text"}

    with pytest.raises(ValueError, match="colliding key"):
        read_spec_payload(payload)
    with pytest.raises(ValueError, match="colliding key"):
        write_spec_payload(payload, tmp_path / "collision.json")


def test_write_spec_payload_cleans_up_when_temporary_permissions_fail(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_to_restrict(_path, _mode):
        raise OSError("cannot restrict temporary file")

    monkeypatch.setattr(Path, "chmod", fail_to_restrict)
    path = tmp_path / "market_data.json"

    with pytest.raises(OSError, match="cannot restrict"):
        write_spec_payload({"artifact_id": "prices"}, path)
    assert not path.exists()
    assert list(tmp_path.iterdir()) == []


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
