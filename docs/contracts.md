# Contract guide

## Market data

FeedSpec and MarketDataSpec define column mappings, frequency, timestamps, calendars, storage, and
provenance. Consumers validate the contract before interpreting a table.

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
