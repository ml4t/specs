## Owning issue

Closes #

Follow the [shared contribution policy](https://github.com/ml4t/ecosystem/blob/main/CONTRIBUTING.md)
and [Specs guide](https://github.com/ml4t/specs/blob/main/CONTRIBUTING.md).
Keep one problem or coherent change in this PR. Automated dependency updates and administrative
metadata changes do not require a separate issue.

## Outcome

Describe the user-visible or standards outcome.

## Compatibility

- [ ] No public compatibility impact
- [ ] Compatibility impact is documented in the owning issue and migration guidance

For incompatible contract changes, identify the new version, migration guidance, serialized
fixtures, and affected producer/consumer libraries. Agree on intentional changes to definitions
or defaults in the owning issue; correct verified defects even when outputs change.

## Verification

For a bug fix, record a regression through the affected public API or real workflow:

- Base revision, command, and failing result:
- PR revision, same command, and passing result:

For other changes, report the relevant commands and outcomes. Documentation changes do not need
artificial regression tests. Explain checks that do not apply.

- [ ] Verification covers the affected contract or workflow
- [ ] Ruff lint and format checks pass
- [ ] `ty` passes
- [ ] Test suite passes
- [ ] Package build passes when applicable
- [ ] Strict MkDocs build passes when documentation is affected
- [ ] Ecosystem qualification passes

## AI assistance

State whether AI tools helped with code or prose, and identify those parts. Write "None" if unused.

- [ ] I reviewed and tested this submission and can explain its implementation and evidence

## Documentation and release

State the documentation, release notes, and patch-release work required after merge.
