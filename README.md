# ml4t-specs

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![PyPI](https://img.shields.io/pypi/v/ml4t-specs)](https://pypi.org/project/ml4t-specs/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Shared schema and artifact contracts for the ML4T library ecosystem.

## What This Package Does

`ml4t-specs` provides the small set of shared types that multiple ML4T libraries use to
describe:

- market data column mappings and feed semantics
- artifact metadata and storage conventions
- lightweight YAML/JSON spec payloads

It exists so the higher-level libraries can exchange consistent contracts without re-defining
the same dataclasses in multiple repos.

Today it is used by:

- `ml4t-backtest` for `FeedSpec` and market-data execution semantics
- `ml4t-engineer` for artifact metadata
- `ml4t-diagnostic` for artifact and backtest-result integration
- `ml4t-models` as an optional integration bridge when `ml4t-specs` is installed

## Installation

```bash
pip install ml4t-specs
```

## Main Types

### FeedSpec

`FeedSpec` defines how downstream libraries should interpret a tradable price table:

- timestamp column
- entity column
- price / OHLCV columns
- quote columns
- calendar and timezone
- data frequency and timestamp semantics

```python
from ml4t.specs import FeedSpec

feed = FeedSpec(
    timestamp_col="date",
    entity_col="ticker",
    close_col="settle",
    price_col="settle",
    calendar="NYSE",
    timezone="America/New_York",
    data_frequency="daily",
)
```

### MarketDataSpec

`MarketDataSpec` bundles schema, semantics, and artifact metadata into one serializable object.

```python
from ml4t.specs import ArtifactStorage, MarketDataSchema, MarketDataSemantics, MarketDataSpec

spec = MarketDataSpec(
    artifact_id="us_equities_daily",
    schema=MarketDataSchema(timestamp_col="date", entity_col="ticker", close_col="close"),
    semantics=MarketDataSemantics(calendar="NYSE", data_frequency="daily"),
    storage=ArtifactStorage(path="data/us_equities_daily.parquet"),
)
```

### Artifact Contracts

The base artifact layer gives ML4T libraries a shared way to talk about persisted outputs:

- `ArtifactKind`
- `ArtifactStorage`
- `ArtifactProvenance`
- `ArtifactSpec`

## Read And Write Spec Payloads

```python
from ml4t.specs import read_spec_payload, write_spec_payload

write_spec_payload(spec, "market_data.yaml")
loaded = read_spec_payload("market_data.yaml")
```

## Why This Exists

The public ML4T libraries share a few contract types at their boundaries. Keeping them here:

- reduces duplication
- keeps cross-library serialization consistent
- gives backtest, modeling, engineering, and diagnostics code one shared contract vocabulary

This package is intentionally small. It is a support layer, not a full end-user workflow library.

## Development

```bash
git clone https://github.com/ml4t/specs.git
cd ml4t-specs
uv sync --dev
uv run ruff check src/ tests/
uv run ty check
uv run pytest tests/ -q
uv build
```

## License

MIT
