# Phase 13G.3.27: Refresh Test Market Bundle

## Outcome

Refresh Test now uses the compact immutable market source bundle, while taxonomy remains a full SQLite copy.

Refresh Production is not migrated in Phase 13G.3.27.

## Source Policy

Previously, Refresh Test created full SQLite backups of both `osakedata.db` and
`analysis.db` before the downstream rebuild. The Test lane now copies only the
taxonomy authority. It builds a `STABLE_SOURCE_BUNDLE` market database after the
provider and canonical candidates have been rebuilt, so the market projection is
bound to the exact Test canonical candidate and calculation date.

The full V2, RP V2, RV, and downstream validation calls receive the compact
`market.db` path and the copied taxonomy path. There is no direct-live-market or
full-market-copy fallback in the normal Refresh Test path. The existing shared
full-copy helper remains unchanged for Refresh Production.

Taxonomy remains `FULL_SQLITE_BACKUP`. The copied database is interpreted with
the existing active `dc_ecosystem` contract, and its version and semantic
fingerprint are recorded. `DIRECT_LOCKED_READ` is not enabled.

## Durable Binding

`read_only_source_binding.json` and `refresh_test_evidence.json` retain the
foundation bundle manifest without inventing another semantic fingerprint. The
evidence includes:

- `FUNDAMENTALS_READ_ONLY_SOURCE_V1` and `STABLE_SOURCE_BUNDLE`
- calculation date and canonical semantic binding
- market semantic fingerprint, physical SHA-256, schema and row counts
- `PRICE_FOUND`, `NO_MATCHING_VALID_PRICE`, `NO_CUTOFF`, and `NO_TICKER` coverage
- taxonomy copy SHA-256, active version, and semantic fingerprint
- source bytes avoided, compact bytes, and bundle construction time
- ephemeral bundle/copy paths and cleanup requirements

This lightweight evidence remains in the run directory after terminal cleanup
and is suitable for a later stale-Test guard in Refresh Production.

## Failure And Cleanup

Bundle construction, source or canonical drift, bundle validation, incomplete
market closure, and taxonomy-copy failures propagate as terminal Test failures.
The workflow does not switch to live market reads.

The compact bundle, its construction artifacts, taxonomy copy, and all other
candidate databases live below the existing Test lane. Existing terminal lane
cleanup removes them on success or failure. Reports, JSON binding evidence, and
other lightweight run artifacts remain outside that lane.

## Validation And Measurement

Fixture integration exercises the real compact builder and active-taxonomy
binding. SQLite page granularity makes the fixture source and compact database
both 57,344 bytes, so the test records exact source and compact sizes rather than
asserting a misleading small-fixture ratio. Build duration is captured in every
Test binding as `bundle_build_seconds`.

The already accepted Phase 13G.3.26 production-shaped benchmark remains the
large-input measurement: 1,990,488,064 source bytes versus a 14,508,032-byte
compact bundle, built in 3.976 seconds. This phase did not create another
multi-gigabyte market copy merely to repeat that benchmark.

Focused tests prove compact-market/full-taxonomy routing, no normal Test market
backup, complete manifest persistence, no-cutoff coverage, fail-closed source
preparation, terminal artifact cleanup, surviving lightweight evidence, and the
unchanged Production full-copy policy. No live Refresh Test or Production
workflow was executed, production databases were not modified, and scheduler
state was not changed.

## Remaining Work

Refresh Production still uses full SQLite source copies. Its future migration
must consume and revalidate the successful Test binding without weakening stale
Test, publication, recovery, or postflight guards.

A Full Workflow end-to-end acceptance test remains mandatory after Refresh Production adopts the same source-consistency contract.
