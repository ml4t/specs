# ml4t-specs

[![Python 3.12-3.14](https://img.shields.io/badge/python-3.12--3.14-blue.svg)](https://www.python.org/downloads/)
[![PyPI](https://img.shields.io/pypi/v/ml4t-specs)](https://pypi.org/project/ml4t-specs/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Shared schema and artifact contracts for the ML4T library ecosystem.

The stable support matrix is CPython 3.12 through 3.14 on Linux, macOS, and Windows.
CPython 3.15 prereleases are tested on all three operating systems but are not advertised as
stable until Python 3.15 is final.

## What This Package Does

`ml4t-specs` provides the small set of shared types that multiple ML4T libraries use to
describe:

- market data column mappings and feed semantics
- artifact metadata and storage conventions
- versioned strategy lifecycle and market-event semantics
- canonical targets, child orders, execution assumptions, and position-rule state
- lightweight YAML/JSON spec payloads

It exists so the higher-level libraries can exchange consistent contracts without re-defining
the same dataclasses in multiple repos.

Today it is used by:

- `ml4t-backtest` for feed, lifecycle, strategy-intent, execution, and position-rule semantics
- `ml4t-live` for the same runtime-neutral execution contracts
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

### Lifecycle And Market Events

`LifecycleContract` defines callback ordering, available information, intent permissions,
callback counts, exception behavior, and causal rank for each portable strategy phase.
`LIFECYCLE_V1` is the supported contract. `MarketEvent` supplies versioned event identity,
validated payloads, provider sequence or gap evidence, and immutable JSON metadata.

### Strategy And Execution Contracts

`CanonicalTargetIntent` records a strategy decision before order construction.
`CanonicalChildOrderIntent` records the resulting unsigned order, its target lineage, fill
decision session, fill session, eligibility phase, time in force, and required execution
capabilities. The two session fields permit a close decision to schedule a child for a later
session's opening auction.
`ExecutionPolicy` records the assumptions under which an engine or venue executes those orders.
`PositionRulePolicy` and `PositionRuleState` make client-side and broker-native exit behavior
portable and resumable.

These contracts serialize to JSON-compatible mappings. Their comparison helpers report exact
field-level differences, including generated identities and timestamps. Callers comparing two
engines must align those fields first. Auction fill eligibility and auction time-in-force values
require the matching declared capability. A decision that observes a completed close cannot fill
at that same close. Instrument prices may be negative, while quantities, trailing amounts, and
trailing percentages remain positive. Favorable and adverse excursions are signed fractional
returns. Use `validate_child_against_policy()` before submission to reject child orders that need
execution behavior disabled by the selected policy.

For intraday strategies, `NEXT_PHASE` from `INTRABAR` or `MARKET_EVENT` means the next event in
that same phase. Across sessions, `NEXT_PHASE` resolves to the later session's opening auction.

`CanonicalChildOrderIntent` requires both `decision_session` and `effective_session`. An order
decided before the opening auction uses `eligibility_phase=PRE_OPEN` with
`fill_eligibility=OPENING_AUCTION`; using `eligibility_phase=OPENING_AUCTION` means the decision
already observed that session's open and is rejected for same-open execution.

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
