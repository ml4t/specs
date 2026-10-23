# ml4t-specs

Runtime-neutral, serializable contracts shared at the boundaries of the ML4T libraries. The package
defines market-data schemas, artifact metadata, strategy lifecycle events, canonical order intents,
execution policies, and position-rule state without depending on a backtest or live engine.

## Public entry points

```python
from ml4t.specs import FeedSpec, LifecycleContract, MarketDataSpec
from ml4t.specs import read_spec_payload, write_spec_payload
```

Use exports from `ml4t.specs` rather than implementation modules. Contract field names, enum values,
validation behavior, and serialized representations are public compatibility surfaces.

## Source map

| Path | Responsibility |
|---|---|
| `src/ml4t/specs/base.py` | Artifact identity, provenance, and storage contracts |
| `src/ml4t/specs/market_data.py` | Feed, schema, semantics, and market-data specifications |
| `src/ml4t/specs/lifecycle.py` | Versioned lifecycle phases, events, and causal validation |
| `src/ml4t/specs/intents.py` | Targets, child orders, execution policies, and position rules |
| `src/ml4t/specs/io.py` | YAML and JSON payload reading and writing |
| `tests/fixtures/` | Canonical serialized compatibility fixtures |
| `docs/contracts.md` | Contract semantics and cross-library responsibilities |

## Contract constraints

- Keep specifications independent of engine implementations. Backtest and Live own runtime
  behavior; Specs owns the values they exchange.
- Use versioned, serializable values for cross-library behavior.
- Export supported contract types from `ml4t.specs`.
- Preserve compatible payloads. When compatibility cannot be maintained, add a new contract version,
  migration guidance, and fixtures that define the transition.

## Guide maintenance

Update this guide when a public contract family, authoritative documentation path, quality command,
or cross-library ownership boundary changes. Do not add current issue state, local workspace paths,
or implementation inventories that become stale as files move.

## Quality commands

```bash
uv sync --dev
uv run ruff check src tests
uv run ruff format --check src tests
uv run ty check
uv run pytest
uv run mkdocs build --strict
```

## Maintainer-directed change batching

For our own fixes and agent work directed by the maintainer, use a bounded, coherent PR rather
than one PR per small defect or implementation step. One PR may close several related issues
when the changes serve the same user workflow, subsystem repair or compatibility objective and
can be reviewed and reverted together. Keep implementation, regressions, documentation and
follow-up repairs together; use focused commits and retain evidence for each defect. Do not
create separate issues or PRs merely for individual files, tests, assertions or platform variants.

Split unrelated changes, independently risky or breaking changes, separate ownership boundaries,
and work that needs independent release or rollback decisions. A general maintenance label alone
does not make a batch coherent. Reuse or safely consolidate existing owned submissions instead of
opening overlapping PRs; preserve contributor attribution, recoverable history and other owners'
active work. Do not rewrite or close someone else's work merely to reduce the queue count.

Run focused checks while iterating, then qualify the complete final revision with every applicable
required gate. Group related work before expensive CI; do not weaken checks, bypass review or
claim old-head checks qualify changed code. This maintainer-directed batching rule takes precedence
over a literal one-issue-per-PR reading of contributor intake guidance.
