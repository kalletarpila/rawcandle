# Datacenter EC Bridge Parity Failure 2026-07-28

## Incident Summary

The first production Stage 2 incremental run materialized Datacenter output for:

```text
2026-07-20 .. 2026-07-27
```

The scheduler correctly selected:

```text
ec_bridge_mode=HISTORICAL_BACKFILL
required_refresh_start=2026-07-20
required_refresh_end=2026-07-27
```

The transitional EC backfill failed on the first selected date:

```text
status=BACKFILL_FAILED
ec_bridge_status=FAILED
ec_bridge_retry_required=true
error=Fact parity audit did not meet acceptance criteria: status=FAILED, total_mismatch_count=14
```

No production repair was executed during the initial diagnostic/fix increment.
The later production repair is recorded in the Completed Production Repair
section below.

## Immediate Safety Action

Before diagnostic work, `scheduler_config.json` was backed up and the Stage 2
incremental flag was disabled:

```text
backup=temp/scheduler_config_before_ec_bridge_diagnostic_20260728_115419.json
datacenter_stage2_incremental_enabled: true -> false
datacenter_stage2_overlap_trading_days: 5 -> 5
unexpected_changed_keys=NONE
```

The config was validated with the existing scheduler config loader. The local
production config is ignored and was not staged or committed.

## Production File Metadata

Before temp-copy diagnostics:

```text
data/analysis.db|regular file|7128670208|1785215411|2026-07-28 08:10:11.413073259 +0300
data/analysis.db-wal|regular empty file|0|1785215411|2026-07-28 08:10:11.413073259 +0300
data/analysis.db-shm|regular file|32768|1785215411|2026-07-28 08:10:11.421642444 +0300
data/osakedata.db|regular file|1944674304|1785215271|2026-07-28 08:07:51.915021817 +0300
data/osakedata.db-wal|MISSING
data/osakedata.db-shm|MISSING
```

After temp-copy diagnostics:

```text
data/analysis.db|regular file|7128670208|1785215411|2026-07-28 08:10:11.413073259 +0300
data/analysis.db-wal|regular empty file|0|1785215411|2026-07-28 08:10:11.413073259 +0300
data/analysis.db-shm|regular file|32768|1785215411|2026-07-28 08:10:11.421642444 +0300
data/osakedata.db|regular file|1944674304|1785215271|2026-07-28 08:07:51.915021817 +0300
data/osakedata.db-wal|MISSING
data/osakedata.db-shm|MISSING
```

`analysis.db-wal` existed but was empty, so the DB file had no WAL frames to
apply. SQL and write-capable commands were run only against `/tmp` copies.

Diagnostic workspace:

```text
/tmp/rawcandle_ec_bridge_failure_20260728_20260728_115508/
```

## Partial Update Evidence

The current production-copy `analysis.db` was compared against the pre-backfill
backup:

```text
temp/analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V1__20260720_20260727__20260728T051003Z.sqlite
```

Classification:

```text
PARTIALLY_UPDATED
```

The failed backfill committed fact-row replacements for 2026-07-20 before
failing parity. No EC fact keys were inserted or deleted for 2026-07-20..2026-07-24,
but rows on 2026-07-20 changed:

```text
ec_ticker_signal_daily:         changed_rows=236
ec_group_signal_daily:          changed_rows=54
ec_group_synthetic_ohlc_daily:  changed_rows=53
ec_group_index_daily:           changed_rows=54
ec_pipeline_watermark:          unchanged
```

The changed fields were lineage/timestamp fields in all four fact tables
(`source_pk_json`, `source_row_hash`, `source_run_id`, `created_at_utc`) plus a
small set of ticker structure fields on one ticker row. The failed run did not
reach later selected dates.

Machine-readable comparison artifact:

```text
/tmp/rawcandle_ec_bridge_failure_20260728_20260728_115508/pre_vs_current_ec_diff.json
```

## Reproduction

Using a fresh `/tmp` copy of the pre-backfill backup, the exact historical
backfill command reproduced the failure:

```text
date_from=2026-07-20
date_to=2026-07-27
selected_dates=2026-07-20,2026-07-21,2026-07-22,2026-07-23,2026-07-24,2026-07-27
skipped_dates=2026-07-25,2026-07-26
failed_date=2026-07-20
failed_step=audit_dc_ec_fact_parity
total_mismatch_count=14
```

## Mismatch Details

All 14 mismatches were reproduced deterministically. Summary:

```text
source_table=dc_pipeline_watermark
target_table=ec_pipeline_watermark
signal_date=2026-07-20
mismatch_type=VALUE_MISMATCH
field_name=latest_signal_date
source_value=2026-07-27
target_value=2026-07-24
count=14
```

Affected watermark identities:

```text
DAILY_REPORT / UNKNOWN:DAILY_REPORT
GROUP_INDEX / dc_group_index_daily
GROUP_OVERHEAT / UNKNOWN:GROUP_OVERHEAT
GROUP_SWING_BASE / dc_group_swing_signal_daily
GROUP_TIMING / UNKNOWN:GROUP_TIMING
PIPELINE_AUDIT / UNKNOWN:PIPELINE_AUDIT
ROLLING_REPORT_2 / UNKNOWN:ROLLING_REPORT_2
ROLLING_REPORT_30 / UNKNOWN:ROLLING_REPORT_30
ROLLING_REPORT_5 / UNKNOWN:ROLLING_REPORT_5
SYNTHETIC_OHLC_BASE / dc_group_synthetic_ohlc_daily
SYNTHETIC_OHLC_RELATIVE / dc_group_synthetic_ohlc_daily
SYNTHETIC_OHLC_STRUCTURE / UNKNOWN:SYNTHETIC_OHLC_STRUCTURE
TICKER_SCANNER / UNKNOWN:TICKER_SCANNER
TICKER_SWING_BASE / dc_ticker_swing_signal_daily
```

Full diagnostic artifact:

```text
/tmp/rawcandle_ec_bridge_failure_20260728_20260728_115508/repro_14_mismatches.json
```

## Root Cause

Root-cause class:

```text
PARITY_AUDIT_DEFECT
```

Historical EC backfill intentionally does not refresh `ec_pipeline_watermark`.
That policy is explicitly documented in the backfill output:

```text
Historical backfill intentionally skipped ec_pipeline_watermark writes
```

However, the per-date fact parity audit still compared `dc_pipeline_watermark`
against `ec_pipeline_watermark`. After the Datacenter incremental run, DC
watermarks had advanced to 2026-07-27 while EC watermarks remained at 2026-07-24.
The historical backfill was therefore blocked by a watermark parity check that
contradicted the historical backfill watermark policy.

The four EC fact loaders were not the cause of the 14 mismatches.

## Fix

Changed files:

```text
rawcandle/ec_dc_fact_parity_audit.py
rawcandle/cli/run_ec_source_layer_backfill.py
tests/test_ec_dc_fact_parity_audit.py
tests/test_run_ec_source_layer_backfill_cli.py
```

Implemented behavior:

```text
audit_dc_ec_fact_parity(..., include_pipeline_watermark=True)
```

The default remains strict and preserves existing refresh/build behavior.

Historical backfill now calls:

```text
include_pipeline_watermark=False
```

This keeps fact parity strict while excluding the watermark comparison that
historical backfill is contractually not supposed to satisfy.

Genuine fact parity mismatches still fail.

## Verification

Fresh temp-copy backfill after the fix:

```text
status=BACKFILL_COMPLETED
completed_dates=2026-07-20,2026-07-21,2026-07-22,2026-07-23,2026-07-24,2026-07-27
coverage_status=OK_WITH_WARNINGS for each completed date
parity_status=OK_WITH_WARNINGS for each completed date
total_mismatch_count=0 for each completed date
overall total_mismatch_count=0
```

Final row counts per completed date:

```text
ticker_rows=236
group_signal_rows=54
synthetic_ohlc_rows=53
group_index_rows=54
```

Idempotency:

```text
same 2026-07-20..2026-07-27 range rerun on the fixed temp DB
status=BACKFILL_COMPLETED
total_mismatch_count=0
2026-07-27 action=REPLACE_EXISTING on rerun
```

EC watermark:

```text
pre-backfill ec_pipeline_watermark == fixed-temp-copy ec_pipeline_watermark
```

The diff was empty; historical backfill did not refresh EC watermarks.

## Completed Production Repair

Repair timestamp:

```text
2026-07-28 12:06:59 EEST
```

Command:

```text
PYTHONPATH=. python3 -m rawcandle.cli.run_ec_source_layer_backfill \
  --db /home/kalle/projects/rawcandle/data/analysis.db \
  --ecosystem DATACENTER \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --date-from 2026-07-20 \
  --date-to 2026-07-27 \
  --taxonomy-csv /home/kalle/projects/rawcandle/data/datacenter_ecosystem_taxonomy_full_v1.csv \
  --watchlist /home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt \
  --backup-dir /home/kalle/projects/rawcandle/temp \
  --confirm-db /home/kalle/projects/rawcandle/data/analysis.db \
  --confirm-ecosystem DATACENTER \
  --confirm-taxonomy-version DC_TAXONOMY_FULL_V1 \
  --allow-replace-existing
```

Fresh pre-repair backup:

```text
/home/kalle/projects/rawcandle/temp/analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V1__20260720_20260727__20260728T090659Z.sqlite
size=7128670208
sha256=2ecb2206a9555b63f47a43b93931fae1914293b9f55f87963a8a0a8194520945
```

Pre-repair EC state:

```text
ec_ticker_signal_daily         max_date=2026-07-24
ec_group_signal_daily          max_date=2026-07-24
ec_group_synthetic_ohlc_daily  max_date=2026-07-24
ec_group_index_daily           max_date=2026-07-24
```

Pre-repair row counts:

```text
2026-07-20 ticker=236 group_signal=54 synthetic_ohlc=53 group_index=54
2026-07-21 ticker=236 group_signal=54 synthetic_ohlc=53 group_index=54
2026-07-22 ticker=236 group_signal=54 synthetic_ohlc=53 group_index=54
2026-07-23 ticker=236 group_signal=54 synthetic_ohlc=53 group_index=54
2026-07-24 ticker=236 group_signal=54 synthetic_ohlc=53 group_index=54
2026-07-27 ticker=0   group_signal=0  synthetic_ohlc=0  group_index=0
```

Backfill result:

```text
status=BACKFILL_COMPLETED
exit_code=0
total_mismatch_count=0
selected_dates=2026-07-20,2026-07-21,2026-07-22,2026-07-23,2026-07-24,2026-07-27
skipped_dates=2026-07-25,2026-07-26
```

Per-date audit after repair:

```text
2026-07-20 coverage=OK_WITH_WARNINGS parity=OK_WITH_WARNINGS mismatches=0
2026-07-21 coverage=OK_WITH_WARNINGS parity=OK_WITH_WARNINGS mismatches=0
2026-07-22 coverage=OK_WITH_WARNINGS parity=OK_WITH_WARNINGS mismatches=0
2026-07-23 coverage=OK_WITH_WARNINGS parity=OK_WITH_WARNINGS mismatches=0
2026-07-24 coverage=OK_WITH_WARNINGS parity=OK_WITH_WARNINGS mismatches=0
2026-07-27 coverage=OK_WITH_WARNINGS parity=OK_WITH_WARNINGS mismatches=0
```

Post-repair EC state:

```text
ec_ticker_signal_daily         max_date=2026-07-27 rows=11328
ec_group_signal_daily          max_date=2026-07-27 rows=2592
ec_group_synthetic_ohlc_daily  max_date=2026-07-27 rows=2544
ec_group_index_daily           max_date=2026-07-27 rows=2592
```

Post-repair row counts:

```text
2026-07-20 ticker=236 group_signal=54 synthetic_ohlc=53 group_index=54
2026-07-21 ticker=236 group_signal=54 synthetic_ohlc=53 group_index=54
2026-07-22 ticker=236 group_signal=54 synthetic_ohlc=53 group_index=54
2026-07-23 ticker=236 group_signal=54 synthetic_ohlc=53 group_index=54
2026-07-24 ticker=236 group_signal=54 synthetic_ohlc=53 group_index=54
2026-07-27 ticker=236 group_signal=54 synthetic_ohlc=53 group_index=54
```

EC watermark verification:

```text
pre_hash=4bf7a777b17f377653c1f54d2ac3e10691dd51e239ff76352245d0eca095c541
post_hash=4bf7a777b17f377653c1f54d2ac3e10691dd51e239ff76352245d0eca095c541
result=UNCHANGED
```

Incremental execution remained disabled:

```text
datacenter_stage2_incremental_enabled=false
datacenter_stage2_overlap_trading_days=5
```

Final readiness classification:

```text
REPAIR_VERIFIED_READY_TO_REENABLE
```

## Tests

Focused tests run:

```text
pytest tests/test_ec_dc_fact_parity_audit.py tests/test_run_ec_source_layer_backfill_cli.py
28 passed
```

Broader targeted tests run:

```text
pytest \
  tests/test_run_ec_source_layer_refresh_cli.py \
  tests/test_run_ec_source_layer_build_cli.py \
  tests/test_ec_dc_coverage_audit.py \
  tests/test_datacenter_stage2_incremental_e2e_verification.py \
  tests/test_stock_update_scheduler_runner.py
137 passed
```

The full suite was not run because the changed interface is narrow and focused
plus downstream bridge/refresh/build tests passed.

## Completed Production Repair Procedure

The approved manual repair was executed after the parity-audit fix was committed
and verified.

1. Confirmed `datacenter_stage2_incremental_enabled=false`.
2. Backed up current production `analysis.db`.
3. Recorded current EC fact counts and `ec_pipeline_watermark`.
4. Ran the corrected historical backfill for:

```text
2026-07-20 .. 2026-07-27
```

5. Verified coverage and fact parity.
6. Confirmed `total_mismatch_count=0`.
7. Confirmed historical backfill did not move or refresh `ec_pipeline_watermark`.
8. Inspected the manual repair summary.
9. Left Stage 2 incremental execution disabled until a separate config-only
   re-enable step.

Rollback considerations:

```text
temp/analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V1__20260720_20260727__20260728T051003Z.sqlite
```

That backup is the pre-backfill state for the failed 2026-07-28 bridge attempt,
but it should not be restored blindly if later valid Datacenter or EC changes
exist.

## Explicit Non-Actions

The approved production EC historical backfill was executed for
`2026-07-20..2026-07-27` and updated the four EC fact tables. No production
scheduler run, Datacenter pipeline run, Stage 2 run, downstream production
stage, latest-date EC refresh, schema migration, EC watermark update, network
call, incremental re-enable, push during the repair operation, or unrelated
cleanup was performed.

## Final Current Status

```text
root_cause=PARITY_AUDIT_DEFECT
code_fix_commit=3a02938
production_repair_status=BACKFILL_COMPLETED
total_mismatch_count=0
ec_fact_head=2026-07-27
ec_pipeline_watermark=UNCHANGED
incremental_reenable_readiness=READY
```
