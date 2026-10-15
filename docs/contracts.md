# Contract guide

## Market data

FeedSpec and MarketDataSpec define column mappings, frequency, timestamps, calendars, storage, and
provenance. Consumers validate the contract before interpreting a table.

### Calendar selection and temporal contract versions

New time-aware consumers use `time_contract_version=2`. This temporal version is independent of
the artifact's `version`. It preserves an omitted calendar separately from an explicit `None`:

| Declaration | Effective calendar |
|---|---|
| Explicit function argument | That name, or no calendar when `None` |
| Argument omitted, metadata declares a calendar | The metadata value, including explicit `None` in version 2 |
| Neither declares a calendar | `NYSE` |

Use the same `calendar` keyword in functions, configs and serialized metadata. Consumers use
`UNSET_CALENDAR` as their omitted-argument default and call `FeedSpec.resolve_calendar`. Ordinary
callers do not need the marker. `None` means observation order/row counts; a named `24/7` calendar
still defines expected times and can detect missing observations.

```python
from ml4t.specs import FeedSpec, UNSET_CALENDAR

metadata = FeedSpec(time_contract_version=2, calendar="24/7")
assert metadata.resolve_calendar() == "24/7"
assert metadata.resolve_calendar(calendar=None) is None
assert FeedSpec(time_contract_version=2).resolve_calendar() == "NYSE"

disabled = metadata.with_overrides(calendar=None)
assert disabled.to_dict()["calendar"] is None
inherited = disabled.with_overrides(calendar=UNSET_CALENDAR)
assert "calendar" not in inherited.to_dict()
```

Serialize with `FeedSpec.to_dict()`, `MarketDataSemantics.to_dict()` or `MarketDataSpec.to_dict()`
before using the shared JSON/YAML writer. These methods omit an undeclared calendar and retain
explicit null. `dataclasses.asdict` is an in-memory projection, not the version-2 wire format.
Copied/replaced version-2 objects and nested artifact-to-feed projections preserve declaration
presence. Consumers must resolve the calendar before passing it to a provider; the unset marker is
not a provider name. Specs validates names structurally; consumers validate provider availability
and the requested schedule without substituting a different exchange.

Constructors and payloads without a temporal version retain version 1. Its null metadata means
unspecified and its `with_overrides(calendar=None)` retains the previous calendar. Explicit arguments
to the new resolver still take precedence, including `None`. Migrating a legacy payload requires
choosing whether an old null meant no declaration or an intentional opt-out: remove the key for
inheritance, or retain null for disable, then set `time_contract_version=2`. Do not relabel legacy
payloads automatically. Non-calendar null overrides retain the legacy no-override convention.

### Fixed-bar grid declarations

Version 2 adds explicit `bar_grid_anchor`, `bar_label` and `partial_bar_policy` fields. They are
optional metadata, without inferred defaults. A consumer performing grid validation must require
the fields it needs along with declared `data_frequency`, timestamp semantics and timezone for
naive timestamps. Specs does not infer a frequency or compute market schedules.

| Field | Supported declaration and meaning |
|---|---|
| `bar_grid_anchor` | `session_open`: start the grid at each authoritative tradable interval's open, including a reopen after a break. A continuous daily schedule uses its declared daily boundary. |
| `bar_label` | `left` or `right`: which boundary the bar timestamp names. `bar_close` timestamp semantics requires `right`; `event_time` alone does not choose a side. |
| `partial_bar_policy` | `include` or `exclude`: retain or omit a final interval shorter than the declared duration at a break or close. |

Session labels are identifiers, not intraday bar timestamps; they cannot declare an intraday grid.
Calendar closures and breaks come from the selected schedule, not missing observations. The metadata
does not authorize filling prices, changing row counts, or treating event-count bars as fixed-time
bars. Validation of invalid declarations occurs before a contract is returned or persisted.

`WindowUnit` distinguishes `observation` (input rows), `expected_bar` (declared grid steps),
`session` (authoritative trading sessions) and `elapsed` (an explicit duration). It performs no
conversion. Consumers must retain the selected unit and must not reinterpret, for example, a
session-count window as a count of observed dates when a scheduled session is absent. Annualization
is a separately declared numerical convention; a calendar-free workflow does not imply NYSE scaling.

The temporal contract does not change the defaults of already released consumers. Each library must
adopt the resolver and serializer and qualify its public workflows before claiming conformance.

## Lifecycle and events

LifecycleContract defines callback ordering, information availability, intent permissions, and
exception behavior. MarketEvent carries versioned event identity and immutable metadata.

## Strategy intent and execution

CanonicalTargetIntent records the strategy decision. CanonicalChildOrderIntent records the order
derived from it, including session lineage and fill eligibility. ExecutionPolicy records the
assumptions required to execute those orders.

## Position rules

PositionRulePolicy defines portable exit behavior. PositionRuleState persists stateful rule progress
so simulation and live runtimes can resume consistently.

Backtest and live must validate these objects against the same contract rather than relying on
undocumented engine-specific interpretations.
