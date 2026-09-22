# Phase 13G.3.28: Refresh Production Market Bundle

## Outcome

Refresh Test and Refresh Production now use the same versioned compact market source-consistency contract.

Taxonomy remains a full SQLite copy in Phase 13G.3.28.

No publication, rollback, recovery, or journal role is added for the market source bundle.

## Production Source Policy

Previously, Refresh Production made full SQLite copies of both `osakedata.db`
and the taxonomy database before constructing its provider and canonical
candidates. Production now builds the same `STABLE_SOURCE_BUNDLE` used by
Refresh Test and continues to make a `FULL_SQLITE_BACKUP` of taxonomy.

The compact bundle is built from live market data after the fresh Production
canonical candidate is complete. This is required because the projection and
coverage identities are bound to that exact canonical requirement set and the
calculation date. Full V2, RP V2, RV, candidate validation, and postflight
validation receive the compact market path and copied taxonomy path. The normal
Production path no longer creates a full market database copy.

## Test Authorization Binding

Production authorization now requires both the successful Test result binding
and its durable `read_only_source_binding.json` artifact to exist and agree.
Production builds a fresh source bundle and compares versioned semantic state:

- source-contract version and calculation date
- selected market semantic and schema fingerprints
- compact row counts
- canonical valuation requirement binding
- coverage counts and per-status identity fingerprints
- taxonomy mode, domain, active version, semantic fingerprint, and row count

Ephemeral paths, compact SQLite physical SHA, taxonomy-copy physical SHA, build
time, and unrelated source details are not semantic authorization fields. Thus
byte-layout differences and market changes outside the registered projection do
not make Test stale.

Relevant market value or selected-row identity changes, coverage identity
changes, canonical requirement drift, contract or calculation-date changes, and
taxonomy version/fingerprint changes produce
`REFRESH_TEST_SOURCE_BINDING_STALE`. The result requires a fresh Preview and
Test and cannot proceed as a direct Production retry.

## Actual Guard Order

Production preserves all prior guards and uses this order:

1. Validate successful Preview/Test authorization and durable Test binding.
2. Acquire the Production lock and run recovery and storage preflight.
3. Revalidate Sharadar source state against Preview/Test.
4. Build provider and canonical candidates.
5. Build compact market and full-copy taxonomy sources against the canonical candidate.
6. Compare the fresh semantic binding with the successful Test binding.
7. Only on a match, build and validate the analysis candidate.
8. Run the existing immediate pre-publication source recheck.
9. Create backups and enter the unchanged three-role journal publication.
10. Validate the published generation and commit the journal.

Provider and canonical candidates necessarily precede source-binding comparison,
because canonical requirements are an input to the compact bundle contract. A
stale binding still stops before analysis construction, backups, journal
creation, or publication.

## Publication And Recovery

The publication roles remain provider, canonical, and analysis. The bundle and
taxonomy copy are read-only candidate inputs and are never published or restored.
The existing durable journal transitions, replacement order, rollback, crash
recovery, and postflight gates are unchanged.

Before the publication boundary, ordinary failure removes the candidate lane.
After a journaled crash, existing recovery policy owns the lane and removes it
after terminal recovery. Terminal success, rollback, or recovery leaves no
phase-owned bundle database.

## Validation And Measurement

Fixture tests cover successful semantic matching, physical-layout tolerance,
market value and coverage drift, canonical and contract drift, calculation-date
drift, taxonomy drift, stale pre-publication stop, compact downstream routing,
postflight source routing, cleanup, and the unchanged journal/recovery suite.

Fixture evidence records 1,000 full market-copy bytes avoided, a 100-byte compact
fixture bundle, and a 0.1-second synthetic build time. Runtime evidence always
records actual source bytes, compact bytes, and measured build duration. The
accepted Phase 13G.3.26 production-shaped measurement remains 1,990,488,064
source bytes versus 14,508,032 compact bytes in 3.976 seconds. No new large copy
was created for this phase.

No live Refresh Production or Full Workflow was executed. Production databases
and scheduler state were not changed.

## Remaining Acceptance

A fixture-sized Refresh Full Workflow end-to-end acceptance test is mandatory before the compact source architecture is considered production-ready.
