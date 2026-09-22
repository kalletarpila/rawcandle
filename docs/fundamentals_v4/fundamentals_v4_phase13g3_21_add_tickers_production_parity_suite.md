# Phase 13G.3.21 Add Tickers Production-Parity Suite

## Purpose

This phase adds a permanent fixture-sized acceptance boundary for the complete Add Tickers workflow. It was motivated by defects that crossed component boundaries: lossy Sharadar projections, false quarter acceptance, reviewed-identity differences, provider failures represented as empty history, workflow progression after review, and incomplete terminal evidence.

Production parity means using the real Production orchestration and safety boundaries with fixture-sized databases; it does not require copying the full Production data volume.

A multi-stage Add Tickers Production workflow is not considered acceptance-tested unless Preview, Test on copies, Production preflight, publication, and postflight are exercised through the real orchestration.

Fault-injection tests must prove that every guarded failure stops before the next unauthorized boundary and preserves self-contained terminal evidence.

## Test Architecture

The primary test is `tests/test_add_tickers_full_workflow_production_parity.py`. It calls `FundamentalsAdminUIService.full_workflow()` and injects only supported fixture paths plus a fake Sharadar transport. The runtime remains real for:

- request parsing and Preview plan creation;
- approved identity resolution and approval-state binding;
- acquisition and fiscal-identity validation;
- provider staging and canonical reconciliation;
- TTM and structural-contract rebuilds;
- full B1 V2, Score, Lifecycle, Valuation, Diagnostics, RP V2, and RV rebuilds;
- Preview/Test binding and production source revalidation;
- writer locks, verified backups, atomic analysis replacement, postflight, reports, and cleanup.

The fake transport returns `SharadarResult`, records every request, performs no network I/O, and fails the test if complete-history calls regain a `fields=` projection. It does not mock the acquisition result or downstream producer output.

The production rehearsal uses the real `production_transaction.run_transaction()` implementation against isolated live-role fixture paths. Add Tickers currently uses the shared publication journal as a global recovery/write guard. Its own publication contract mutates the backed-up provider/canonical roles and atomically replaces analysis; the successful-path assertion therefore records `publication_recovery_preflight=NO_JOURNAL`. Shared incomplete-journal recovery and retry-required behavior remains covered by `test_fundamentals_admin_refresh_production.py`, including the Add Tickers invocation chain.

## Fixture Databases

`tests/add_tickers_production_parity_fixtures.py` creates five deterministic roles:

- provider: production provider schema and predecessor metadata;
- canonical: production canonical and TTM schemas plus bound predecessor identities;
- analysis: a disposable old generation replaced by the real V2 candidate;
- market: classification, OHLC, and split-event schemas;
- taxonomy: the current migrated EC sidecar and active `dc_ecosystem` domain.

The representative batch is:

| Ticker | Identity pattern | ARQ quarters | Expected model behavior |
| --- | --- | ---: | --- |
| KRSA | Existing company, distinct successor security | 8 | Score and lifecycle ready |
| PSQL | New company/security, short history | 3 | Legitimate model not-ready states, no integrity error |
| QVCG | Distinct successor company/security, long history | 8 | Complete canonical and analysis lineage |

The test proves `network ARQ -> staging -> canonical quarters -> analysis input` for every ticker. KRSA's eight newly acquired quarters are asserted directly, so old company history cannot create a false positive.

The observed fixture set contains five SQLite databases. The largest is about 520 KiB after publication and the aggregate fixture directory is about 1.4 MB. Pytest owns and removes the temporary root; no generated databases are committed.

## Failure Matrix

`tests/test_add_tickers_full_workflow_failure_matrix.py` drives the real Preview acquisition boundary and real Full Workflow stop decision for:

- transient provider failure;
- permanent provider failure;
- authoritative zero usable history;
- invalid response shape;
- incomplete fiscal identity.

Every case stops after Preview, invokes neither Test nor Production, and retains structured ticker/retry facts in the durable workflow result.

The wider permanent matrix is intentionally split across focused suites:

- stale source and bound-plan changes: `test_fundamentals_admin_batch_add_tickers.py`;
- approval mismatch, stale approval, provider/canonical contradiction, and PROPOSED decisions: `test_fundamentals_admin_identity_resolution.py`;
- rollback journal, WAL, and SHM rejection before backup/write: `test_fundamentals_admin_production_transaction.py`;
- taxonomy/market source drift, candidate failure, postflight failure, and complete rollback: `test_fundamentals_admin_production_transaction.py`;
- crash recovery at each role boundary, idempotent recovery, terminal journals, and Add Tickers retry-required integration: `test_fundamentals_admin_refresh_production.py`;
- review-stop and self-contained terminal reporting: `test_fundamentals_admin_full_workflow.py`;
- UI summaries, lazy loading, 8/16/24 paging, hidden-run policy, and global newest-first ordering: `test_fundamentals_admin_ui.py`.

This division keeps failures attributable and avoids duplicating the generic recovery suite inside one slow test.

## Sharadar Pacing

`SharadarClient` now owns one process-level `SharadarRequestLimiter` for real default transport requests. `SHARADAR_MIN_REQUEST_INTERVAL_SECONDS` is `0.5` seconds. The limiter serializes request starts, covers initial attempts and retries, and allows retry backoff to wait longer.

Custom injected transports do not sleep unless a limiter is explicitly injected. Focused tests use a fake monotonic clock and sleeper to prove sequential, retry, and concurrent spacing without wall-clock delay. The Production-parity suite uses fake transport and makes zero real Sharadar requests.

## Running The Suite

Run the complete fixture workflow when changing Add Tickers acquisition, identity resolution, provider/canonical candidates, fiscal identity, V2/RP/RV orchestration, Preview/Test binding, Full Workflow, production guards, publication/recovery, or terminal reporting:

```bash
pytest -q tests/test_add_tickers_full_workflow_production_parity.py
```

Run the boundary matrix and related regressions with:

```bash
pytest -q \
  tests/test_add_tickers_full_workflow_failure_matrix.py \
  tests/test_fundamentals_admin_batch_add_tickers.py \
  tests/test_fundamentals_admin_identity_resolution.py \
  tests/test_fundamentals_admin_production_transaction.py \
  tests/test_fundamentals_admin_full_workflow.py \
  tests/test_fundamentals_v4_sharadar_provider.py
```

The complete fixture workflow currently runs in roughly 45-50 seconds locally. It does not access `data/`, the live report root, systemd, the scheduler, backup production files, or the Internet.
