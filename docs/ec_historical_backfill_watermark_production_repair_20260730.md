# EC Historical Backfill Watermark Production Repair - 2026-07-30

## Summary

Repair classification:

```text
EC_WATERMARK_REPAIR_VERIFIED_AND_REENABLED
```

Purpose:

```text
Advance only the four canonical EC fact watermark heads after a previously
successful Datacenter -> EC historical fact synchronization.
```

Repair range:

```text
2026-07-22..2026-07-29
```

Code version:

```text
d9d42dc Advance EC fact watermarks after historical backfill
```

Repository state before production DB repair:

```text
branch=chore/ignore-backups
HEAD=d9d42dcf70efbd904507960580673602cf0af358
origin/chore/ignore-backups=d9d42dcf70efbd904507960580673602cf0af358
working_tree_clean=true
```

## Safety Gates

Temporary Stage 2 incremental disable:

```text
backup=temp/scheduler_config_before_ec_watermark_repair_20260730T080013Z.json
datacenter_stage2_incremental_enabled=false
datacenter_stage2_overlap_trading_days=5
config_loader_status=OK
changed_keys=datacenter_stage2_incremental_enabled
unexpected_changed_keys=NONE
```

Active writer check:

```text
stock update scheduler active=false
Datacenter pipeline active=false
EC latest refresh active=false
EC historical backfill active=false
analysis.db open handles=false
```

The scheduler UI process was running, but `lsof` showed no open handle on
`analysis.db`, `analysis.db-wal`, or `analysis.db-shm`.

## Pre-Repair Production Evidence

Production database:

```text
path=data/analysis.db
size=7329411072
mtime=2026-07-30 08:09:44.537317218 +0300
wal_size=0
wal_mtime=2026-07-30 11:01:21.093058688 +0300
shm_size=32768
shm_mtime=2026-07-30 11:01:21.119751517 +0300
```

Pre-repair EC fact heads:

```text
ec_ticker_signal_daily         max_signal_date=2026-07-29 row_count=11800
ec_group_signal_daily          max_signal_date=2026-07-29 row_count=2700
ec_group_synthetic_ohlc_daily  max_signal_date=2026-07-29 row_count=2650
ec_group_index_daily           max_signal_date=2026-07-29 row_count=2700
```

Pre-repair canonical EC watermark rows:

```text
GROUP_INDEX          dc_group_index_daily           latest_signal_date=2026-07-28 status=OK updated_at_utc=2026-07-29T09:38:24Z
GROUP_SWING_BASE     dc_group_swing_signal_daily    latest_signal_date=2026-07-28 status=OK updated_at_utc=2026-07-29T09:38:24Z
SYNTHETIC_OHLC_BASE  dc_group_synthetic_ohlc_daily  latest_signal_date=2026-07-28 status=OK updated_at_utc=2026-07-29T09:38:24Z
TICKER_SWING_BASE    dc_ticker_swing_signal_daily   latest_signal_date=2026-07-28 status=OK updated_at_utc=2026-07-29T09:38:24Z
```

Pre-repair full watermark snapshot:

```text
path=temp/ec_pipeline_watermark_before_repair_20260730T080013Z.csv
rows=15
sha256=e01e16d6d812aa128520059ff38ffffd5f5266c104cda81009d2a279d0bbb755
```

## Backup

Fresh guarded CLI backup created immediately before writes:

```text
path=temp/analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V1__20260722_20260729__20260730T080148Z.sqlite
size=7329411072
mtime=2026-07-30 11:01:56.065214828 +0300
sha256=40d49e220b75d45fbad357f426a3cda02180d1f2a1ffefbed49110b3d43323ac
```

## Backfill Command

Exact command:

```bash
PYTHONPATH=. python3 -m rawcandle.cli.run_ec_source_layer_backfill \
  --db /home/kalle/projects/rawcandle/data/analysis.db \
  --ecosystem DATACENTER \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --date-from 2026-07-22 \
  --date-to 2026-07-29 \
  --taxonomy-csv /home/kalle/projects/rawcandle/data/datacenter_ecosystem_taxonomy_full_v1.csv \
  --watchlist /home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt \
  --backup-dir /home/kalle/projects/rawcandle/temp \
  --confirm-db /home/kalle/projects/rawcandle/data/analysis.db \
  --confirm-ecosystem DATACENTER \
  --confirm-taxonomy-version DC_TAXONOMY_FULL_V1 \
  --allow-replace-existing
```

Captured output:

```text
stdout=temp/ec_watermark_repair_backfill_stdout_20260730T080013Z.txt
stderr=temp/ec_watermark_repair_backfill_stderr_20260730T080013Z.txt
exit_code_file=temp/ec_watermark_repair_backfill_exit_code_20260730T080013Z.txt
exit_code=0
```

Backfill result:

```text
status=BACKFILL_COMPLETED
planner_status=READY_BACKFILL_PLAN
total_mismatch_count=0
coverage_status=OK_WITH_WARNINGS for all selected dates
parity_status=OK_WITH_WARNINGS for all selected dates
```

Selected dates:

```text
2026-07-22 REPLACE_EXISTING
2026-07-23 REPLACE_EXISTING
2026-07-24 REPLACE_EXISTING
2026-07-27 REPLACE_EXISTING
2026-07-28 REPLACE_EXISTING
2026-07-29 REPLACE_EXISTING
```

Skipped dates:

```text
2026-07-25 NOT_ALIGNED_SOURCE
2026-07-26 NOT_ALIGNED_SOURCE
```

Watermark finalization:

```text
watermark_policy=ADVANCE_CANONICAL_FACT_HEADS_AFTER_VALIDATED_BACKFILL
watermark_refresh_performed=true
watermark_advanced=true
watermark_candidate_latest_signal_date=2026-07-29
watermark_rows_inserted=0
watermark_rows_updated=4
watermark_rows_unchanged=0
watermark_rows_total=4
watermark_advance_status=OK
```

## Post-Repair Verification

Post-repair EC fact heads:

```text
ec_ticker_signal_daily         max_signal_date=2026-07-29 row_count=11800
ec_group_signal_daily          max_signal_date=2026-07-29 row_count=2700
ec_group_synthetic_ohlc_daily  max_signal_date=2026-07-29 row_count=2650
ec_group_index_daily           max_signal_date=2026-07-29 row_count=2700
```

Per-selected-date row counts:

```text
date        ticker_rows group_signal_rows synthetic_ohlc_rows group_index_rows
2026-07-22  236         54                53                  54
2026-07-23  236         54                53                  54
2026-07-24  236         54                53                  54
2026-07-27  236         54                53                  54
2026-07-28  236         54                53                  54
2026-07-29  236         54                53                  54
```

Post-repair fact verification:

```text
coverage_acceptance=OK
parity_acceptance=OK
total_mismatch_count=0 for every selected date
include_pipeline_watermark=false
```

Post-repair canonical EC watermark rows:

```text
GROUP_INDEX          dc_group_index_daily           latest_signal_date=2026-07-29 status=OK updated_at_utc=2026-07-30T08:01:57Z
GROUP_SWING_BASE     dc_group_swing_signal_daily    latest_signal_date=2026-07-29 status=OK updated_at_utc=2026-07-30T08:01:57Z
SYNTHETIC_OHLC_BASE  dc_group_synthetic_ohlc_daily  latest_signal_date=2026-07-29 status=OK updated_at_utc=2026-07-30T08:01:57Z
TICKER_SWING_BASE    dc_ticker_swing_signal_daily   latest_signal_date=2026-07-29 status=OK updated_at_utc=2026-07-30T08:01:57Z
```

Canonical checks:

```text
canonical_behind_2026_07_29=0
canonical_duplicate_scopes=0
latest_signal_date_moved_backwards=false
```

Noncanonical watermark verification:

```text
before_noncanonical_sha256=ac7b683ee05036d4b18a4d519eb451865c0c4d926656b2f3c5db2c515fa85a72
after_noncanonical_sha256=ac7b683ee05036d4b18a4d519eb451865c0c4d926656b2f3c5db2c515fa85a72
noncanonical_watermark_rows_unchanged=true
```

Noncanonical rows verified unchanged include:

```text
DAILY_REPORT
GROUP_OVERHEAT
GROUP_TIMING
PIPELINE_AUDIT
ROLLING_REPORT_2
ROLLING_REPORT_5
ROLLING_REPORT_30
SYNTHETIC_OHLC_RELATIVE
SYNTHETIC_OHLC_STRUCTURE
TICKER_SCANNER
WEEKLY_REPORT
```

## Re-Enable

Stage 2 incremental re-enabled after all repair gates passed:

```text
backup=temp/scheduler_config_before_stage2_incremental_reenable_after_ec_watermark_repair_20260730T080343Z.json
datacenter_stage2_incremental_enabled=true
datacenter_stage2_overlap_trading_days=5
config_loader_status=OK
changed_keys=datacenter_stage2_incremental_enabled
unexpected_changed_keys=NONE
```

## Explicit Non-Actions

The repair did not run:

```text
stock update scheduler
Datacenter pipeline
Stage 2
downstream Datacenter stages
EC latest refresh
any broad or different historical backfill range
schema migration
network API or external provider call
git commit
git push
```

The repair did not modify Python code, tests, migrations, loaders, scheduler
runtime code, or durable sync-debt storage.
