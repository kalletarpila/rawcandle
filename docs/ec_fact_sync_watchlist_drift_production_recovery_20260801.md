# EC Fact Sync Watchlist Drift Production Recovery 2026-08-01

## Classification

```text
EC_FACT_RECOVERY_WITH_WATCHLIST_DRIFT_VERIFIED_AND_REENABLED
```

## Context

The production Datacenter -> EC canonical fact bridge was behind after the current Datacenter watchlist file was intentionally changed from the stored EC watchlist membership.

Deployed code fix:

```text
4a6c278 Decouple EC fact sync from watchlist drift
```

Recovery range:

```text
2026-07-24..2026-07-31
```

Root cause:

```text
watchlist membership drift previously returned BLOCKED_WATCHLIST_SOURCE
for canonical fact synchronization, even though canonical EC facts are full-universe
and independent of user watchlist membership.
```

## Repository State

```text
branch=chore/ignore-backups
HEAD=4a6c27811f1d3a1d731dce6559200f01b6dcf8bb
origin/chore/ignore-backups=4a6c27811f1d3a1d731dce6559200f01b6dcf8bb
expected_unstaged_change=watchlists/datacenter_watchlist.txt
```

## Safety Controls

Stage 2 incremental was disabled before production DB writes.

```text
disable_config_backup=temp/scheduler_config_before_ec_fact_watchlist_drift_recovery_disable_20260801T152604Z.json
config_loader_status=OK
changed_keys=datacenter_stage2_incremental_enabled
unexpected_changed_keys=NONE
datacenter_stage2_incremental_enabled=false
datacenter_stage2_overlap_trading_days=5
```

Active-writer check:

```text
stock_update_scheduler_active=false
datacenter_pipeline_active=false
ec_historical_backfill_active=false
ec_latest_refresh_active=false
lsof_open_analysis_db_handles=none
wal_size_before=0
```

Only the bounded EC historical backfill and its canonical watermark finalization wrote to the production DB.

## Pre-Recovery Evidence

Production DB:

```text
db_path=/home/kalle/projects/rawcandle/data/analysis.db
db_size_before=7537115136
db_mtime_before=2026-08-01 08:11:41.013638172 +0300
wal_size_before=0
shm_size_before=32768
```

Canonical DC heads:

```text
dc_ticker_swing_signal_daily=2026-07-31 rows_2026_07_31=236
dc_group_swing_signal_daily=2026-07-31 rows_2026_07_31=54
dc_group_synthetic_ohlc_daily=2026-07-31 rows_2026_07_31=53
dc_group_index_daily=2026-07-31 rows_2026_07_31=54
```

Canonical EC heads before:

```text
ec_ticker_signal_daily=2026-07-30 rows_2026_07_31=0
ec_group_signal_daily=2026-07-30 rows_2026_07_31=0
ec_group_synthetic_ohlc_daily=2026-07-30 rows_2026_07_31=0
ec_group_index_daily=2026-07-30 rows_2026_07_31=0
```

Canonical EC watermark heads before:

```text
TICKER_SWING_BASE=2026-07-30 status=OK
GROUP_SWING_BASE=2026-07-30 status=OK
SYNTHETIC_OHLC_BASE=2026-07-30 status=OK
GROUP_INDEX=2026-07-30 status=OK
```

Watchlist state before:

```text
watchlist_file=/home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt
watchlist_file_sha256=5dfa86d390202fb6bd561fad43967a382de9012ccfbb01f5a725042eefd087e8
watchlist_file_normalized_members=37
ec_watchlist_member_count=16
watchlist_drift_present=true
```

Stored EC watchlist membership:

```text
AEHR, AEIS, AXTI, CLS, CRDO, CRGY, DIOD, ECG, LRCX, MRVL, NVDA, NVT, PRIM, TXN, VRT, VSH
```

Before snapshot checksums:

```text
before_ec_pipeline_watermark_sha256=7ffbcd1cccd2a00312e7e7479edb779f952df2f52fbd4f44720b813cbdf9946e
before_ec_watchlist_sha256=a2abfc2960206eb1edecd5eefec9ea82e93f1f8f159214494797a2b6bfe803d7
before_ec_watchlist_member_sha256=65e2e769d9b367467da0a301c66e2bed25a2f9c1d0dc06b801e9537efd5d182c
```

Snapshot files are under:

```text
temp/ec_fact_watchlist_drift_recovery_20260801T152647Z/
```

## Production Backup

The backfill CLI created the guarded production backup under `temp/`.

```text
backup_path=/home/kalle/projects/rawcandle/temp/analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V1__20260724_20260731__20260801T152803Z.sqlite
backup_size=7537115136
backup_mtime=2026-08-01 18:28:10.632813040 +0300
backup_sha256=23e8e4f1e5de85e0e387fdc0878b45c9a5693cf48d36053941777ec8504bff54
```

## Backfill Command

Exactly one bounded historical backfill was run:

```bash
PYTHONPATH=. python3 -m rawcandle.cli.run_ec_source_layer_backfill \
  --db /home/kalle/projects/rawcandle/data/analysis.db \
  --ecosystem DATACENTER \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --date-from 2026-07-24 \
  --date-to 2026-07-31 \
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
stdout=temp/ec_fact_watchlist_drift_recovery_20260801T152647Z/backfill_stdout.txt
stderr=temp/ec_fact_watchlist_drift_recovery_20260801T152647Z/backfill_stderr.txt
exit_code_file=temp/ec_fact_watchlist_drift_recovery_20260801T152647Z/backfill_exit_code.txt
exit_code=0
```

## Backfill Result

```text
status=BACKFILL_COMPLETED
planner_status=READY_BACKFILL_PLAN
total_mismatch_count=0
```

Selected dates:

```text
2026-07-24 REPLACE_EXISTING
2026-07-27 REPLACE_EXISTING
2026-07-28 REPLACE_EXISTING
2026-07-29 REPLACE_EXISTING
2026-07-30 REPLACE_EXISTING
2026-07-31 BACKFILL_MISSING
```

Skipped non-aligned dates:

```text
2026-07-25 NOT_ALIGNED_SOURCE
2026-07-26 NOT_ALIGNED_SOURCE
```

Coverage and parity:

```text
coverage_status=OK_WITH_WARNINGS for each selected date
parity_status=OK_WITH_WARNINGS for each selected date
total_mismatch_count=0
acceptance=OK
```

Watermark finalization:

```text
watermark_policy=ADVANCE_CANONICAL_FACT_HEADS_AFTER_VALIDATED_BACKFILL
watermark_refresh_performed=true
watermark_advanced=true
watermark_candidate_latest_signal_date=2026-07-31
watermark_rows_inserted=0
watermark_rows_updated=4
watermark_rows_unchanged=0
watermark_rows_total=4
watermark_advance_status=OK
```

## Watchlist Drift Verification

The planner/backfill surfaced the intentional drift but did not block canonical fact synchronization.

```text
watchlist_membership_status=DRIFT_DETECTED
watchlist_sync_required=true
watchlist_source_member_count=37
watchlist_loaded_member_count=16
watchlist_missing_in_loaded_count=28
watchlist_loaded_only_count=7
planner_status_not_BLOCKED_WATCHLIST_SOURCE=true
```

Deterministic drift lists:

```text
watchlist_missing_in_loaded=[
  AAPL, ALAB, AMBA, AMD, AMZN, ANET, AVGO, CNC, DT, FTNT, GFS, LITE,
  MU, NNE, ORCL, PANW, PLTR, POET, SEZL, SIMO, SKHY, SMCI, SMH, SNDK,
  SPCX, STX, WST, ZBRA
]
watchlist_loaded_only=[
  AEHR, AEIS, AXTI, DIOD, PRIM, TXN, VSH
]
```

No watchlist membership apply was performed.

## Post-Recovery Evidence

Canonical EC heads after:

```text
ec_ticker_signal_daily=2026-07-31 rows_2026_07_31=236
ec_group_signal_daily=2026-07-31 rows_2026_07_31=54
ec_group_synthetic_ohlc_daily=2026-07-31 rows_2026_07_31=53
ec_group_index_daily=2026-07-31 rows_2026_07_31=54
```

Canonical EC watermark heads after:

```text
TICKER_SWING_BASE dc_ticker_swing_signal_daily latest_signal_date=2026-07-31 status=OK
GROUP_SWING_BASE dc_group_swing_signal_daily latest_signal_date=2026-07-31 status=OK
SYNTHETIC_OHLC_BASE dc_group_synthetic_ohlc_daily latest_signal_date=2026-07-31 status=OK
GROUP_INDEX dc_group_index_daily latest_signal_date=2026-07-31 status=OK
canonical_duplicate_scopes=0
canonical_behind_2026_07_31=0
latest_signal_date_moved_backwards=false
```

Production DB after:

```text
db_size_after=7537500160
db_mtime_after=2026-08-01 18:28:12.692995866 +0300
wal_size_after=0
shm_size_after=32768
```

## Watchlist Table Non-Mutation Proof

After snapshot checksums:

```text
after_ec_watchlist_sha256=a2abfc2960206eb1edecd5eefec9ea82e93f1f8f159214494797a2b6bfe803d7
after_ec_watchlist_member_sha256=65e2e769d9b367467da0a301c66e2bed25a2f9c1d0dc06b801e9537efd5d182c
```

Comparison:

```text
ec_watchlist_unchanged=true
ec_watchlist_member_unchanged=true
ec_watchlist_member_count_after=16
```

The stored EC membership remained:

```text
AEHR, AEIS, AXTI, CLS, CRDO, CRGY, DIOD, ECG, LRCX, MRVL, NVDA, NVT, PRIM, TXN, VRT, VSH
```

## Noncanonical Watermark Proof

```text
before_noncanonical_watermark_count=11
after_noncanonical_watermark_count=11
noncanonical_watermark_rows_unchanged=true
```

Only these canonical rows advanced:

```text
TICKER_SWING_BASE
GROUP_SWING_BASE
SYNTHETIC_OHLC_BASE
GROUP_INDEX
```

## Re-Enable

Stage 2 incremental was re-enabled only after fact, watermark, watchlist non-mutation, and noncanonical watermark gates passed.

```text
reenable_config_backup=temp/scheduler_config_before_ec_fact_watchlist_drift_recovery_reenable_20260801T152939Z.json
config_loader_status=OK
changed_keys=datacenter_stage2_incremental_enabled
unexpected_changed_keys=NONE
datacenter_stage2_incremental_enabled=true
datacenter_stage2_overlap_trading_days=5
```

## Explicit Non-Actions

```text
watchlists/datacenter_watchlist.txt not modified by recovery
watchlists/datacenter_watchlist.txt not staged
ec_watchlist not updated
ec_watchlist_member not updated
stock update scheduler not run
Datacenter pipeline not run
Stage 2 not run
downstream Datacenter stages not run
latest EC refresh not run
range outside 2026-07-24..2026-07-31 not backfilled
migrations not run
Python code not modified
tests not run
unrelated cleanup not performed
network not used except later documentation push
```
