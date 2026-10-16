# Contributing to ML4T Specs

Follow the [shared ML4T contribution policy](https://github.com/ml4t/ecosystem/blob/main/CONTRIBUTING.md).
Search existing issues and describe one problem or coherent change per issue and focused pull
request. Link the owning issue; automated dependency updates and administrative metadata changes
retain the shared exception. Disclose AI assistance for code and prose, review the submission,
and be prepared to explain its implementation and evidence.

For defects, provide a minimal public-API reproduction with package and environment details.
Record the same regression command failing on the base revision and passing on the correction.
Correct verified numerical defects; agree on intentional changes to definitions or defaults in
the owning issue. Documentation changes use relevant documentation checks rather than artificial
regression tests. Report suspected vulnerabilities through
[private security reporting](https://github.com/ml4t/specs/security/advisories/new).

## Preserve contract compatibility

Specs owns runtime-neutral values exchanged between libraries. Field names, enum values,
validation behavior, and serialized payloads are public compatibility surfaces. Preserve compatible
payloads. An incompatible change needs a new contract version, migration guidance, and fixtures
that define the transition. Describe affected producer and consumer libraries in the owning issue;
Backtest and Live retain responsibility for their runtime behavior.

Read the [contract guide](docs/contracts.md) and use the documented development and quality
commands in [AGENTS.md](AGENTS.md#quality-commands). Include the commands and outcomes in your PR.
