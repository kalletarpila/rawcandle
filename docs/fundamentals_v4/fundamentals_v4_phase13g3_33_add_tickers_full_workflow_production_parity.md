# Phase 13G.3.33 Add Tickers Full Workflow Production Parity

## Decision

Phase 13G.3.33 proves Add Tickers through the real Full Workflow with STABLE_SOURCE_BUNDLE market input and DIRECT_LOCKED_READ taxonomy input in Preview, Test, and Production.

Normal Add Tickers runtime creates no full market or taxonomy source database copies.

The exercised Administration entry point is `FundamentalsAdminUIService.full_workflow(operation_type="ADD_TICKERS")`. The suite does not assemble Preview, Test, and Production as an alternate workflow.

## Fixture

The fixture uses fake Sharadar transport and fixture-only SQLite roots. It includes:

- KRSA reviewed company continuity with a new security;
- PSQL and QVCG reviewed new-company/new-security identities;
- valid ARQ/MRQ fiscal identity and provider staging;
- canonical reconciliation and TTM input;
- market classifications and price rows;
- an active `dc_ecosystem` taxonomy;
- enough history for full Score and RP output, plus RV for an eligible taxonomy member.

Measured successful-run database sizes were:

| Role | Bytes |
| --- | ---: |
| provider | 147,456 |
| canonical | 360,448 |
| analysis | 532,480 |
| market | 16,384 |
| taxonomy | 307,200 |

The compact market bundle was 32,768 bytes. A successful Full Workflow completed in approximately 49 seconds on the acceptance host.

## Source Contract

Preview, Test, and Production each persist a versioned read-only source binding. The suite compares only the semantic authority contract:

- `FUNDAMENTALS_READ_ONLY_SOURCE_V1` contract version;
- calculation/as-of date;
- canonical semantic binding;
- market semantic and schema fingerprints;
- row and valuation-coverage counts/fingerprints;
- active taxonomy domain, version, membership count, and semantic fingerprint.

Ephemeral bundle paths, source inode metadata, build duration, and physical SQLite hashes do not authorize Test-to-Production parity. Downstream receives a compact market path and the protected live taxonomy path. Taxonomy writer contention is rejected under the same authoritative lock in both Test and Production.

No source `osakedata.db` or taxonomy `analysis.db` is passed to SQLite copy helpers. Terminal cleanup removes compact SQLite bundles and candidate databases. Small source-binding manifests and operation reports remain as audit evidence.

## Success Path

The real orchestration completes Preview, consumes its authorization in Test, then revalidates both Preview and Test in Production. Production creates backups only for provider, canonical, and analysis; rebuilds V2 Score/Lifecycle/Valuation, RP V2, and RV; validates and publishes the analysis candidate; performs postflight; and commits the journal as `COMPLETED`.

The publication journal roles are exactly:

- provider
- canonical
- analysis

Market and taxonomy are never publication, rollback, or recovery roles.

## Fault Cases

- Market drift after Test rejects Production before backups, journal creation, or mutation.
- Active taxonomy drift after Test rejects Production before publication.
- Transient Sharadar failure remains a structured retryable acquisition failure and stops Full Workflow before Test.
- Missing fiscal identity remains fail-closed and stops Full Workflow before Test.
- A normal failure after durable journal preparation but before the first live mutation removes the nonterminal journal and unnecessary backups.
- A failure after the publication boundary restores and verifies the complete OLD provider/canonical/analysis generation and leaves a terminal `ROLLED_BACK` journal.
- A simulated process crash leaves a nonterminal journal. The next real Add Tickers Production entrypoint performs recovery before interpreting Preview/Test state, restores OLD, returns `RETRY_REQUIRED`, and does not continue mutation in that invocation.
- Taxonomy writer contention fails closed while Add Tickers holds its protected direct-read lock.

## Defects Closed

The acceptance suite exposed and closed two production-path gaps:

1. Add Tickers guarded against an existing shared journal but did not journal its own three-database publication. It now uses the shared durable journal and shared idempotent OLD-generation recovery contract.
2. Durable result redaction can represent `retry_authorization` as `[REDACTED]`. UI/report consumers now treat that value as a mapping only when it actually is one, preventing a stale Production result from breaking Full Workflow reporting.

The recovery guard now runs after the production, scheduler, and taxonomy locks are held but before Preview/Test/source-binding validation. A recovery-triggering invocation always stops with retry required.

Identity resolution, approval fingerprints, acquisition classification, fiscal validation, provider staging, canonical reconciliation, request pacing, and the Full Workflow stage policy were not relaxed.

## Safety

All acceptance execution uses fixture roots and fake network transport. No live provider, canonical, analysis, market, or taxonomy database is opened for mutation. Scheduler/systemd state is not changed. Generated fixture databases, backups, journals, locks, and reports are not committed.

## Verification

The focused verification completed with 258 passing tests:

- 12 Add Tickers Full Workflow, acquisition/fiscal failure, and UI retry-reporting tests;
- 157 Add Tickers batch, identity, source-bundle, transaction, V2/RP/RV, and Sharadar pacing tests;
- 61 shared Refresh publication/recovery tests;
- 5 Refresh Full Workflow production-parity tests;
- 23 Add Tickers and Refresh orchestration regressions.

The Refresh production-parity market fixture was aligned with the production source schema by adding the required `osakedata.market` column. No production reader or validation rule was relaxed. Compile/import validation and `git diff --check` passed.
