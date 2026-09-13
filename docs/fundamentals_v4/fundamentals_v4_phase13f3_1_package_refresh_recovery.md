# Phase 13F.3.1 Package Refresh Recovery

Status: `OUTCOME B - PACKAGE REFRESH RECOVERED; DOWNSTREAM TECHNICAL CHAIN STILL BLOCKED`

Phase 13F.3.1 carried forward the accepted Phase 13F.3 ticker-transition
findings and focused on the `package_refresh` non-return and downstream
copy-only chain. Production writes were not authorized or performed.

## Artifacts

Primary run:

`temp/fundamentals_v4_phase13f3_1_package_refresh_recovery/20260913T_PHASE13F3_1_FINAL4/`

Useful evidence:

- `run_1/package_refresh_telemetry.json`
- `run_1/package_refresh_result.json`
- `run_1/rehearsal_result.json`
- `phase13f3_1_result.json`

No transient `.db`, `.db-journal`, `.db-wal` or `.db-shm` artifacts remained
after cleanup.

## Root Cause

The Phase 13F.3 apparent non-return was not a SQLite write deadlock. It was a
long-running authoritative `phase10b.calculate` stage with no durable inner
progress output. In the instrumented run, calculation completed in about 197
seconds before the package write transaction began.

A second issue was found during instrumentation: the first callback attempted
to inspect the analysis copy through a separate read-only SQLite connection
while the package writer held `BEGIN IMMEDIATE`, causing `database is locked`.
Telemetry now avoids opening a second SQLite connection during active write
transactions.

A third stale validation defect was corrected: `phase10b.validate_candidate_package`
had a hard-coded `50_585` endpoint expectation. It now derives row-count
expectations from the current package rows.

## Package Result

Final instrumented package refresh:

- calculation completed;
- apply stages completed through `score`, `lifecycle`, `valuation`, `delta`,
  `diagnostic`, `relative` and `manifest`;
- first apply: `APPLIED`;
- second apply: `NO_CHANGE`;
- second physical no-change: `true`;
- diagnostic endpoints: `87,328`;
- diagnostic evaluations: `698,624`;
- score rows: `87,328`;
- valuation rows: `87,328`;
- package relative result rows: `13,743`.

## Downstream Result

The copy-only chain progressed past package refresh:

- pre-refresh Relative Valuation compatibility: `OPERATIONAL_UNIVERSE_MISMATCH`;
- manual full-universe Relative Valuation refresh completed;
- post-refresh Relative Valuation compatibility: `COMPATIBLE`;
- second RV refresh: `NO_CHANGE` with zero bulk and pointer writes.

## Remaining Blockers

Outcome A was not claimed because the downstream acceptance gates are still
blocked:

- successor Snapshot smoke failed for VMRK, IA, VAI, NXH and NMAD with
  `NO_FUNDAMENTAL_ENDPOINT_ON_OR_BEFORE_REPORT_DATE`;
- production canonical state has zero `v4_quarter` and zero `v4_ttm_values`
  rows for the five carried-forward company identities;
- provider fundamentals tables have no observations for the old or successor
  transition tickers, so package refresh cannot manufacture fundamental
  endpoints without a separately authorized canonical/provider onboarding
  correction;
- AREB still has one post-delisting current Relative Valuation row in the
  candidate refresh;
- `OWN_HISTORY_STRUCTURAL_BREAK_POLICY_REQUIRES_SEPARATE_VERSIONED_CONTRACT`
  remains deferred by design.

## Production Isolation

Production quick checks passed after the run for:

- `data/fundamentals_provider.db`
- `data/fundamentals_v4.db`
- `data/fundamentals_analysis.db`

The run reported production immutability as `true`.

## Next Scope

Do not prepare a Phase 13F.4 production deployment runbook yet. The next phase
must explicitly address fundamentals endpoint absence for the five successor
identities and date-aware exclusion of AREB from current Relative Valuation,
then rerun the full copy-only chain and deterministic replay.
