# ML4T Specs

ml4t-specs defines the runtime-neutral contracts shared by ML4T libraries. It keeps serialized
market-data, artifact, strategy lifecycle, execution, intent, and position-rule semantics consistent
without depending on an execution engine.

Use these contracts when data or behavior crosses a library boundary. Library-specific
implementations remain in their owning packages.

## Related libraries

- [Engineer](https://www.ml4trading.io/docs/engineer/) uses shared artifact metadata.
- [Backtest](https://www.ml4trading.io/docs/backtest/) implements the portable strategy lifecycle.
- [Live](https://www.ml4trading.io/docs/live/) implements the same lifecycle against live adapters.

Continue with [Getting started](getting-started.md) or review the [Contract guide](contracts.md).
