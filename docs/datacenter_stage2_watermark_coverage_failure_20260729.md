# Datacenter Stage 2 Watermark Coverage Failure 2026-07-29

## Incident Summary

The 2026-07-29 production Datacenter run had Stage 2 incremental enabled, but
the planner selected a full Stage 2 materialization:

```text
stage2_incremental_enabled=true
stage2_plan=REQUESTED_START_BEFORE_WATERMARK
stage2_plan_mode=FULL
stage2_planned_materialization_start=2025-08-01
stage2_planned_materialization_end=2026-07-28
stage2_actual_materialized_start=2025-08-01
stage2_actual_materialized_end=2026-07-28
downstream_incremental_stages=3,7,8,9
```

The Datacenter run completed with `pipeline_status=WARN`, but the transitional
EC bridge requested an incorrect broad historical backfill:

```text
ec_bridge_mode=HISTORICAL_BACKFILL
ec_bridge_required_start=2025-08-01
ec_bridge_required_end=2026-07-28
ec_bridge_load_status=BACKFILL_REFUSED
ec_bridge_status=FAILED
ec_bridge_retry_required=true
error=planner gate did not pass: BLOCKED_INVALID_DATE_RANGE
backup_path=NONE
```

No EC write was performed by the refused bridge.

## Immediate Disable

Stage 2 incremental was disabled before diagnosis:

```text
backup=temp/scheduler_config_before_stage2_watermark_failure_disable_20260729_122542.json
datacenter_stage2_incremental_enabled: true -> false
datacenter_stage2_overlap_trading_days: 5 -> 5
unexpected_changed_keys=NONE
```

The config was validated with the scheduler config loader. The production config
is ignored and was not staged or committed.

## Production File Metadata

Before diagnosis:

```text
data/analysis.db|regular file|7228706816|68290|2026-07-29 08:18:44.383447447 +0300
data/analysis.db-wal|MISSING
data/analysis.db-shm|MISSING
data/osakedata.db|regular file|1945534464|88025|2026-07-29 08:06:42.561967080 +0300
data/osakedata.db-wal|MISSING
data/osakedata.db-shm|MISSING
```

Safe diagnostic copies were created under:

```text
/tmp/rawcandle_stage2_watermark_failure_20260729_122718/
```

## Watermark Transition Evidence

The 2026-07-28 Stage 2 incremental run for signal date `2026-07-27` logged:

```text
stage2_plan=NEW_SIGNAL_DATES_WITH_LOOKBACK_OVERLAP
stage2_plan_mode=INCREMENTAL
stage2_planned_materialization_start=2026-07-20
stage2_planned_materialization_end=2026-07-27
stage2_actual_materialized_start=2026-07-20
stage2_actual_materialized_end=2026-07-27
downstream_dirty_start=2026-07-20
downstream_dirty_end=2026-07-27
```

Production backups from 2026-07-28 showed the relevant dirty-chain watermarks
were narrowed to the last materialized overlap range:

```text
TICKER_SWING_BASE  2026-07-20..2026-07-27
GROUP_SWING_BASE   2026-07-20..2026-07-27
GROUP_TIMING       2026-07-20..2026-07-27
GROUP_OVERHEAT     2026-07-20..2026-07-27
TICKER_SCANNER     2026-07-20..2026-07-27
```

Using that copied state, the 2026-07-29 Stage 2 planner reproduced:

```text
requested_start=2025-08-01
requested_end=2026-07-28
watermark_start=2026-07-20
watermark_end=2026-07-27
mode=FULL
reason_code=REQUESTED_START_BEFORE_WATERMARK
materialization_start=2025-08-01
materialization_end=2026-07-28
```

## Root Cause

Root-cause class:

```text
WATERMARK_RANGE_REPLACED_BY_LAST_MATERIALIZATION
```

`dc_pipeline_watermark.start_date` is interpreted by the planner as the earliest
continuous validated coverage date. The Stage 2 pilot watermark writers were
instead storing the last dirty materialization start. After the first successful
incremental overlap run, coverage evidence was narrowed from the historical
coverage start to `2026-07-20`. On the next run, the planner correctly applied
`REQUESTED_START_BEFORE_WATERMARK` to that incorrect evidence and selected FULL.

This affected:

```text
TICKER_SWING_BASE
GROUP_SWING_BASE
GROUP_TIMING
GROUP_OVERHEAT
TICKER_SCANNER
```

No identity mismatch was found for the Stage 2 row.

## Fix

Changed files:

```text
analysis/datacenter_indices/pipeline_watermark.py
analysis/datacenter_indices/swing_pipeline_orchestrator.py
tests/test_datacenter_pipeline_watermark.py
tests/test_datacenter_swing_pipeline_orchestrator.py
tests/test_datacenter_stage2_incremental_e2e_verification.py
docs/datacenter_stage2_watermark_coverage_failure_20260729.md
```

Implemented behavior:

```text
upsert_pipeline_watermark(..., preserve_coverage_start=True)
```

The option merges only compatible, overlapping, successful `OK` coverage ranges:

```text
new_start = min(previous_start, materialized_start)
new_end   = max(previous_end, materialized_end)
```

The option is enabled only for the Stage 2 pilot dirty-chain components:

```text
TICKER_SWING_BASE
GROUP_SWING_BASE
GROUP_TIMING
GROUP_OVERHEAT
TICKER_SCANNER
```

Default replacement behavior remains unchanged for other watermark callers,
including reports and artifacts. Disjoint ranges are not silently represented as
continuous coverage.

## Temp-Copy Verification

On a temp copy, the pre-first-incremental state was simulated as:

```text
2025-08-01..2026-07-24
```

After a successful overlap materialization:

```text
materialized=2026-07-20..2026-07-27
stored_watermark=2025-08-01..2026-07-27
```

The next-day planner for `2026-07-28` then produced:

```text
mode=INCREMENTAL
reason_code=NEW_SIGNAL_DATES_WITH_LOOKBACK_OVERLAP
materialization_start=2026-07-21
materialization_end=2026-07-28
watermark_start=2025-08-01
watermark_end=2026-07-27
```

The transitional EC bridge decision for that fixed materialization was bounded:

```text
bridge_mode=HISTORICAL_BACKFILL
required_refresh_start=2026-07-21
required_refresh_end=2026-07-28
```

A temp-copy backfill for that bounded range was accepted and completed:

```text
planner_status=READY_BACKFILL_PLAN
status=BACKFILL_COMPLETED
selected_dates=2026-07-21,2026-07-22,2026-07-23,2026-07-24,2026-07-27,2026-07-28
skipped_dates=2026-07-25,2026-07-26
parity_status=OK_WITH_WARNINGS for each completed date
total_mismatch_count=0
```

## Production Repair Decision

The 2026-07-29 full Datacenter run had already restored the current production
DC dirty-chain watermarks:

```text
TICKER_SWING_BASE  2025-08-01..2026-07-28
GROUP_SWING_BASE   2025-08-01..2026-07-28
GROUP_TIMING       2025-08-01..2026-07-28
GROUP_OVERHEAT     2025-08-01..2026-07-28
TICKER_SCANNER     2025-08-01..2026-07-28
```

Therefore:

```text
production_dc_watermark_repair=NOT_REQUIRED
```

Before EC repair, production state was:

```text
dc_fact_head=2026-07-28
ec_fact_head=2026-07-27
```

## Production EC Repair

Chosen repair path:

```text
run_ec_source_layer_refresh --signal-date 2026-07-28
```

This was chosen instead of historical backfill because the repair was a single
new latest date and the temp-copy latest refresh proved it would load the four
EC fact tables, refresh `ec_pipeline_watermark`, and run coverage/parity audits.

Fresh pre-repair backup:

```text
temp/analysis_before_stage2_watermark_failure_ec_refresh_20260729_123712.sqlite
size=7228706816
sha256=93660a488f8eadff6c28f0a00826c510acbc618183269a2822c1a4ab7aa690b1
```

The refresh also created its own guarded pre-write backup:

```text
/home/kalle/projects/rawcandle/temp/analysis__ec_source_layer_refresh__DATACENTER__DC_TAXONOMY_FULL_V1__20260728__20260729T093818Z.sqlite
```

Production refresh result:

```text
status=REFRESH_COMPLETED
planner_status=READY_REFRESH_NEW_DATE
selected_signal_date=2026-07-28
coverage_status=OK_WITH_WARNINGS
parity_status=OK_WITH_WARNINGS
total_mismatch_count=0
ticker_rows=236
group_signal_rows=54
synthetic_ohlc_rows=53
group_index_rows=54
watermark_rows=15
```

## Final Verification

Post-repair copied production fact heads:

```text
dc_ticker_swing_signal_daily   max_date=2026-07-28 rows=92578
dc_group_swing_signal_daily    max_date=2026-07-28 rows=21252
dc_group_synthetic_ohlc_daily  max_date=2026-07-28 rows=21985
dc_group_index_daily           max_date=2026-07-28 rows=90402
ec_ticker_signal_daily         max_date=2026-07-28 rows=11564
ec_group_signal_daily          max_date=2026-07-28 rows=2646
ec_group_synthetic_ohlc_daily  max_date=2026-07-28 rows=2597
ec_group_index_daily           max_date=2026-07-28 rows=2646
ec_pipeline_watermark          max_date=2026-07-28 rows=15
```

Post-repair parity:

```text
status=OK_WITH_WARNINGS
total_mismatch_count=0
```

Post-repair planner for target `2026-07-28`:

```text
mode=SKIP
reason_code=WATERMARK_COVERS_REQUESTED_TARGET
watermark_start=2025-08-01
watermark_end=2026-07-28
```

The source price copy did not yet contain a valid next USA signal date after
`2026-07-28`; the future-date incremental behavior is covered by the regression
fixture.

## Tests

Static check:

```text
python3 -m py_compile analysis/datacenter_indices/pipeline_watermark.py analysis/datacenter_indices/swing_pipeline_orchestrator.py
```

Focused tests:

```text
pytest tests/test_datacenter_pipeline_watermark.py \
  tests/test_datacenter_swing_pipeline_orchestrator.py \
  tests/test_datacenter_stage2_incremental_e2e_verification.py \
  tests/test_datacenter_pipeline_plan.py

54 passed
```

Targeted EC/scheduler/CLI tests:

```text
pytest tests/test_run_ec_source_layer_refresh_cli.py \
  tests/test_run_ec_source_layer_backfill_cli.py \
  tests/test_stock_update_scheduler_runner.py \
  tests/test_run_datacenter_stage2_incremental_plan_cli.py \
  tests/test_run_datacenter_swing_pipeline_cli.py

139 passed
```

The full suite was not run because the changed code path is narrowly scoped and
focused plus targeted downstream tests passed.

## Re-Enable Readiness

Current readiness:

```text
code_fix_verified=true
tests_passed=true
temp_next_day_plan=INCREMENTAL
production_watermarks_correct=true
dc_fact_head=2026-07-28
ec_fact_head=2026-07-28
total_mismatch_count=0
production_repair_status=OK
working_tree_commit_created=true
code_fix_commit=a353409
incremental_reenable_status=REENABLED
datacenter_stage2_incremental_enabled=true
datacenter_stage2_overlap_trading_days=5
```

Stage 2 incremental was re-enabled only after the fix, focused tests,
production EC repair, and implementation commit succeeded.

## Explicit Production Actions and Non-Actions

Production actions performed:

```text
disabled datacenter_stage2_incremental_enabled
created production analysis.db backup
ran one-day EC latest refresh for 2026-07-28
re-enabled datacenter_stage2_incremental_enabled after commit a353409
```

Production actions not performed:

```text
no scheduler run
no full Datacenter rerun
no production Stage 2 run
no downstream Datacenter stage run
no broad EC historical backfill
no DC watermark row update
no schema migration
no network call
no push
no unrelated cleanup
```
