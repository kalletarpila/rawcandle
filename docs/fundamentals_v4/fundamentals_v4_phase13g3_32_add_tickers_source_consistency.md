# Phase 13G.3.32 Add Tickers Source Consistency

## Decision

Add Tickers Preview, Test, and Production now use `STABLE_SOURCE_BUNDLE` for
market and `DIRECT_LOCKED_READ` for taxonomy.

The old normal copy lane treated provider, canonical, analysis, market, and
taxonomy as five copied roles. The normal runtime split is now:

- writable/candidate roles: provider, canonical, analysis;
- read-only market input: a compact immutable bundle bound to canonical state,
  requested ticker history, and calculation date;
- read-only taxonomy input: the active `dc_ecosystem` generation read directly
  under the authoritative taxonomy lock.

Explicit full-copy helpers remain compatibility/test utilities only. They are
not selected by normal Add Tickers runtime.

## Protection And Binding

Preview and Test acquire authoritative taxonomy protection before source
preparation and retain it through all downstream taxonomy reads, validation,
and terminal candidate cleanup. Production preserves the established order:

`Admin Production lock -> scheduler lock -> taxonomy lock`

Production holds taxonomy protection through Preview revalidation, source
mutation, full V2/RP/RV rebuild, candidate validation, publication, postflight,
and terminal cleanup. Contending taxonomy writers fail closed.

Preview persists the versioned market/taxonomy binding. Test verifies that
binding before mutation and persists the rebuilt candidate's binding.
Production first revalidates Preview through the same shared abstraction, then
builds fresh post-mutation sources and compares their semantic binding with the
successful Test. Paths, mtimes, and SQLite page layout are excluded from the
semantic comparison. Relevant market drift reports the market section stale;
an active taxonomy version or semantic-fingerprint change reports taxonomy
stale.

## Preserved Contracts

Identity approvals and fingerprints, security/company continuity, Sharadar
acquisition and retry behavior, fiscal-identity validation, provider staging,
canonical reconciliation, lineage, V2/RP/RV economics, stale-plan guards, and
structured workflow stops are unchanged. No network request or live workflow
was used for this phase.

Market and taxonomy remain read-only inputs and are never Add Tickers
publication, rollback, or recovery roles. Publication and OLD-generation
restore remain exactly provider, canonical, and analysis. Journal states,
replacement order, rollback, crash recovery, and retry-required recovery
behavior are unchanged.

## Cleanup And Tests

Normal terminal Preview/Test cleanup removes the three candidate DBs, compact
market bundle, and partial bundle artifacts before releasing taxonomy
protection. Production removes its preflight and downstream bundles on success,
stale rejection, failure, rollback, and recovery terminal paths while retaining
lightweight JSON/report binding evidence.

Focused fixture tests prove:

- Preview, Test, and Production create no full market or taxonomy copy;
- all three stages report the required source modes;
- downstream receives compact market and protected live taxonomy paths;
- matching Test/Production bindings pass and relevant market/taxonomy drift is
  rejected;
- taxonomy writers cannot enter during Test or Production protected reads;
- publication/backup roles remain provider, canonical, and analysis;
- existing identity, acquisition, fiscal, rollback, and Refresh source-contract
  regressions remain green.

## Copy Reduction

Accepted production-shaped evidence records `1,990,488,064` market bytes and
`11,078,471,680` taxonomy bytes, totaling `13,068,959,744` bytes (`12.171 GiB`)
per old full source snapshot. The migrated normal Add Tickers Preview, Test, and
Production stages each avoid one such full source snapshot. A complete
Preview -> Test -> Production sequence therefore avoids approximately
`39,206,879,232` bytes (`36.514 GiB`) of gross full-source copying, before the
much smaller compact market bundles are counted. No new production-shaped copy
was created for this measurement.

## Next Phase

A fixture-sized Add Tickers Full Workflow production-parity rerun is mandatory
after this migration. This phase contains a focused orchestration proof but does
not execute the separately scoped broad final Full Workflow production-parity
suite.
