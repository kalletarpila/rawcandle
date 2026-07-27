# Datacenter Stage 2 Incremental E2E Verification

This document records the safety-bounded verification increment for the
Datacenter Stage 2 incremental pilot.

## Scope

Verified flow:

```text
Stage 2 planner
  -> Datacenter orchestrator incremental range wiring
  -> Stage 3/7/8/9 conservative dirty-chain propagation
  -> structured Datacenter summary
  -> scheduler EC bridge decision
  -> latest refresh or historical backfill selection
  -> coverage/parity result handling
  -> scheduler-visible bridge status
```

No production scheduler, production Datacenter pipeline, real EC refresh,
real EC backfill, real database planning, or production database write was
performed.

## Test Architecture

The verification uses a layered integration approach:

- Real Stage 2 planner logic with temporary SQLite price and analysis databases.
- Real Datacenter orchestrator range wiring, skip handling, summary fields, and
  `dc_pipeline_watermark` writes against temporary SQLite databases.
- Mocked heavy Datacenter stage runner boundaries for Stage 1-9. The mocks
  record exact CLI arguments and allow targeted failure injection.
- Real scheduler EC bridge decision and post-step status/log construction.
- Mocked EC refresh and historical backfill functions. No real EC write path is
  invoked.

This avoids a parallel test-only pipeline while keeping production boundaries
isolated.

## Temporary Database Strategy

All executable verification tests use `tmp_path` databases:

- `osakedata.db` contains a minimal `osakedata` table and synthetic USA OHLCV
  rows.
- `analysis.db` is initialized through `DatabaseManager`.
- `dc_pipeline_watermark` is populated only in the temporary analysis database.

Tests assert that database paths are under `/tmp/` and not under the production
`/home/kalle/projects/rawcandle/data/` prefix.

## Scenarios Executed

- Feature disabled / legacy compatibility:
  Stage 2 and Stage 3/7/8/9 retain the configured full start date, the planner
  is not invoked, and the scheduler bridge remains on latest refresh.
- Incremental multi-date success:
  Real planner emits `INCREMENTAL`; output overlap is based on valid trading
  dates; input warmup starts before output materialization; Stage 2 and
  Stage 3/7/8/9 receive the conservative dirty range; Stage 6 remains on the
  original range; watermarks advance only for successful stages; scheduler
  selects historical backfill and does not invoke latest refresh.
- Incremental single-date success:
  Zero overlap makes the actual materialized range equal the selected signal
  date, and the scheduler selects latest refresh with watermark refresh
  reported as performed.
- Planner `SKIP`:
  Stage 2 and Stage 3/7/8/9 are skipped, Stage 6 is not planner-skipped, dirty
  chain watermarks do not advance, and no EC bridge write path is invoked.
- Partial Stage 2 failure:
  A simulated per-date write occurs before Stage 2 returns failure; the Stage 2
  watermark does not advance, downstream stages do not run, summary output does
  not claim an actual materialized range, and scheduler bridge skips EC work.
- Downstream failures:
  Stage 3, Stage 7, Stage 8, and Stage 9 failure cases stop later dependent
  stages and do not write the failed stage watermark.
- Historical EC backfill failures:
  Coverage failure, parity failure, mismatch count, malformed output, and
  exception-style failure are treated as bridge failures with retry required and
  no latest-refresh fallback.
- Latest EC refresh failure:
  Existing compatibility behavior remains: a failed latest refresh is visible
  and maps to a warning-level scheduler outcome when the main run succeeded.
- EC source layer disabled:
  No refresh or backfill function is invoked, bridge fields report disabled
  state, and no retry is required.

## Production Defects Found

No production-code defects were found during this verification increment. The
changes are tests and documentation only.

## Test Results

Executed during implementation:

```text
pytest -q tests/test_datacenter_stage2_incremental_e2e_verification.py
15 passed
```

The final focused regression run for this increment is recorded in the task
completion summary.

## Remaining Production-Only Gaps

- No production scheduler activation has been performed.
- No real production Datacenter pipeline run has been performed.
- No real EC refresh or historical EC backfill has been performed.
- No real production database was opened, planned against, or written.
- The real Stage 2/3/7/8/9 heavy write path remains covered by focused unit and
  persistence tests rather than by a full production-like dataset run.

## Rollout Recommendation

Keep `datacenter_stage2_incremental_enabled=false` in production until a
separately approved dry-run or controlled production activation window is
planned. Use scheduler summaries to verify `stage2_actual_materialized_*` and
`ec_bridge_*` fields before considering routine enablement.

## Rollback Recommendation

Disable `datacenter_stage2_incremental_enabled`. This returns the scheduler to
the legacy Datacenter full-range execution and latest-date EC refresh path. Use
the existing EC historical backfill CLI manually for any recorded affected range
that requires repair.
