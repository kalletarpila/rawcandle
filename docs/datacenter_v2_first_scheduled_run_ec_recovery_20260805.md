# Datacenter V2 First Scheduled Run EC Recovery 2026-08-05

## Classification

```text
recovery_classification=DATACENTER_V2_EC_RECOVERY_VERIFIED
operation_type=EC_SOURCE_LAYER_CANONICAL_FACT_RECOVERY
target_ecosystem=DATACENTER
target_taxonomy_version=DC_TAXONOMY_FULL_V2
required_range=2026-07-27..2026-08-04
code_version=719f33e
branch=chore/ignore-backups
```

This recovery corrected the EC canonical fact coverage after the first normal scheduled Datacenter V2 run. The Datacenter `dc_*` materializations were already present through `2026-08-04`; the recovery was limited to the Datacenter V2 EC canonical source-layer facts and canonical EC fact watermarks.

## Scope

Allowed and performed:

- Guarded EC source-layer backfill for `DATACENTER / DC_TAXONOMY_FULL_V2`.
- Range: `2026-07-27..2026-08-04`.
- Existing canonical backfill CLI: `python3 -m rawcandle.cli.run_ec_source_layer_backfill`.
- One SQLite backup under `temp/` before the EC writes.
- Coverage and fact parity validation.
- Canonical EC fact watermark advancement to `2026-08-04`.
- Read-only UI taxonomy state inspection after recovery.

Not performed:

- No Scheduler run.
- No Datacenter pipeline run.
- No Stage 2 run.
- No Datacenter loader or recalculation.
- No taxonomy prepare, rebuild, cleanup, activation, or migration.
- No external data fetch.
- No unrelated cleanup.
- No tests.

## Evidence Directory

```text
evidence_dir=temp/datacenter_v2_ec_recovery_20260805_20260805T085807Z
```

Key evidence files:

```text
config_baseline.txt
taxonomy_baseline.txt
dc_fact_heads_baseline.txt
ec_fact_heads_baseline.txt
ec_watermarks_baseline.txt
active_process_check.txt
sqlite_sidecar_check.txt
read_only_recovery_plan.txt
read_only_recovery_plan.sha256
run_ec_source_layer_backfill.stdout
run_ec_source_layer_backfill.stderr
run_ec_source_layer_backfill.exit_code
backup_integrity_check.txt
backup_stat.txt
backup_sha256.txt
post_ec_v2_scoped_counts.txt
post_ec_fact_heads.txt
post_ec_watermarks.txt
post_coverage_parity_audit.txt
post_v1_after_activation.txt
dc_nonimpact_hash_compare.txt
ui_taxonomy_state_inspect.txt
scheduler_guard_final_restored_verification.txt
final_file_hashes.txt
```

## Starting State

Repository state before writes:

```text
branch=chore/ignore-backups
HEAD=719f33ee58bb1b975e2dfc6254fb55fe69e96938
origin/chore/ignore-backups=719f33ee58bb1b975e2dfc6254fb55fe69e96938
working_tree_status=clean
```

Scheduler config baseline:

```text
skip_next_run=False
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V2
datacenter_taxonomy_csv=data/datacenter_taxonomy_full_v2.csv
datacenter_stage2_incremental_enabled=True
datacenter_stage2_overlap_trading_days=5
ec_source_layer_enabled=True
ec_source_layer_mode=refresh_latest
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V2
ec_source_layer_taxonomy_csv=data/datacenter_taxonomy_full_v2.csv
```

File hashes:

```text
scheduler_config.json=f3ecdc488c0b08bea7ce22d757056bfb7539723fee994589c27989ba33c83089
data/datacenter_taxonomy_full_v2.csv=178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1
watchlists/datacenter_watchlist.txt=5dfa86d390202fb6bd561fad43967a382de9012ccfbb01f5a725042eefd087e8
```

Datacenter source fact heads before recovery:

```text
dc_ticker_swing_signal_daily=2026-08-04
dc_group_swing_signal_daily=2026-08-04
dc_group_synthetic_ohlc_daily=2026-08-04
dc_group_index_daily=2026-08-04
```

EC fact heads before recovery:

```text
ec_ticker_signal_daily=2026-07-31
ec_group_signal_daily=2026-07-31
ec_group_synthetic_ohlc_daily=2026-07-31
ec_group_index_daily=2026-07-31
```

Canonical V2 EC watermarks before recovery:

```text
TICKER_SWING_BASE    dc_ticker_swing_signal_daily   2026-07-31 OK
GROUP_SWING_BASE     dc_group_swing_signal_daily    2026-07-31 OK
SYNTHETIC_OHLC_BASE  dc_group_synthetic_ohlc_daily  2026-07-31 OK
GROUP_INDEX          dc_group_index_daily           2026-07-31 OK
```

## Scheduler Guard

The scheduler was guarded before the recovery write by setting only:

```text
skip_next_run=True
```

Guard verification:

```text
changed_keys=skip_next_run
unexpected_changed_keys=NONE
```

The guard was restored after validation:

```text
changed_keys=NONE
unexpected_changed_keys=NONE
skip_next_run=False
datacenter_stage2_incremental_enabled=True
datacenter_stage2_overlap_trading_days=5
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V2
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V2
```

Final file hashes after guard restore:

```text
scheduler_config.json=f3ecdc488c0b08bea7ce22d757056bfb7539723fee994589c27989ba33c83089
data/datacenter_taxonomy_full_v2.csv=178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1
watchlists/datacenter_watchlist.txt=5dfa86d390202fb6bd561fad43967a382de9012ccfbb01f5a725042eefd087e8
```

## Read-Only Plan

Read-only plan:

```text
status=READY_BACKFILL_PLAN
requested_start=2026-07-27
requested_end=2026-08-04
selected_date_count=7
aligned_dates=2026-07-27,2026-07-28,2026-07-29,2026-07-30,2026-07-31,2026-08-03,2026-08-04
missing_source_dates=2026-08-01,2026-08-02
latest_loaded_fact_date=2026-07-31
taxonomy_row_count=350
taxonomy_distinct_ticker_count=257
compatibility_status=OK
source_hash_match=True
watchlist_membership_status=MATCH
```

Plan hash:

```text
read_only_recovery_plan_sha256=d85736f60bc8f7b06a2cc1d12b74d9b34d8c1620478f5b289d770688f1867789
```

Selected actions:

```text
2026-07-27 REPLACE_EXISTING
2026-07-28 REPLACE_EXISTING
2026-07-29 REPLACE_EXISTING
2026-07-30 REPLACE_EXISTING
2026-07-31 REPLACE_EXISTING
2026-08-03 BACKFILL_MISSING
2026-08-04 BACKFILL_MISSING
```

## Backup

The canonical backfill CLI creates its backup using SQLite's backup API before EC writes begin. The current public CLI does not expose a separate pre-write `PRAGMA integrity_check` hook; integrity validation was performed immediately after the backfill returned and before final acceptance.

```text
backup_path=temp/datacenter_v2_ec_recovery_20260805_20260805T085807Z/backups/analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2__20260727_20260804__20260805T090629Z.sqlite
backup_size_bytes=7943188480
backup_sha256=fac78e330961d6d3003778b0085d75248cf06f66376b85b09a90438b50f12c82
backup_integrity_check=ok
```

The backup was written under `temp/`, not under `data/` and not next to the live database. No automatic restore was performed.

## Backfill Execution

Executed exactly once:

```text
python3 -m rawcandle.cli.run_ec_source_layer_backfill \
  --db data/analysis.db \
  --ecosystem DATACENTER \
  --taxonomy-version DC_TAXONOMY_FULL_V2 \
  --date-from 2026-07-27 \
  --date-to 2026-08-04 \
  --taxonomy-csv data/datacenter_taxonomy_full_v2.csv \
  --watchlist watchlists/datacenter_watchlist.txt \
  --backup-dir temp/datacenter_v2_ec_recovery_20260805_20260805T085807Z/backups \
  --confirm-db data/analysis.db \
  --confirm-ecosystem DATACENTER \
  --confirm-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --allow-replace-existing
```

Result:

```text
process_exit_code=0
backfill_status=BACKFILL_COMPLETED
planner_status=READY_BACKFILL_PLAN
selected_date_count=7
completed_dates=2026-07-27,2026-07-28,2026-07-29,2026-07-30,2026-07-31,2026-08-03,2026-08-04
skipped_dates=2026-08-01 NOT_ALIGNED_SOURCE, 2026-08-02 NOT_ALIGNED_SOURCE
total_mismatch_count=0
watermark_refresh_performed=true
watermark_advanced=true
watermark_candidate_latest_signal_date=2026-08-04
watermark_rows_updated=4
watermark_advance_status=OK
watchlist_reconciliation_status=NO_CHANGE
watchlist_membership_status=MATCH
```

Per-date loader, coverage, and parity statuses were `OK_WITH_WARNINGS` with `total_mismatch_count=0` for every selected date.

## Final EC Coverage

Scoped V2 row counts after recovery:

```text
ec_ticker_signal_daily         257 rows for each selected date
ec_group_signal_daily           54 rows for each selected date
ec_group_synthetic_ohlc_daily   53 rows for each selected date
ec_group_index_daily            54 rows for each selected date
```

Selected dates:

```text
2026-07-27
2026-07-28
2026-07-29
2026-07-30
2026-07-31
2026-08-03
2026-08-04
```

EC fact heads after recovery:

```text
ec_ticker_signal_daily=2026-08-04 rows_on_20260804=257
ec_group_signal_daily=2026-08-04 rows_on_20260804=54
ec_group_synthetic_ohlc_daily=2026-08-04 rows_on_20260804=53
ec_group_index_daily=2026-08-04 rows_on_20260804=54
```

Canonical V2 EC watermarks after recovery:

```text
TICKER_SWING_BASE    dc_ticker_swing_signal_daily   2026-08-04 OK
GROUP_SWING_BASE     dc_group_swing_signal_daily    2026-08-04 OK
SYNTHETIC_OHLC_BASE  dc_group_synthetic_ohlc_daily  2026-08-04 OK
GROUP_INDEX          dc_group_index_daily           2026-08-04 OK
```

Read-only post-plan confirmed all selected dates are fully loaded in EC:

```text
latest_loaded_fact_date=2026-08-04
classification=FULLY_LOADED_IN_EC for every selected date
count_mismatch_tables=[]
compatibility_status=OK
watchlist_membership_status=MATCH
```

## Coverage And Parity

Independent read-only post-recovery audit:

```text
date        coverage_status   parity_status     total_mismatch_count
2026-07-27  OK_WITH_WARNINGS  OK_WITH_WARNINGS  0
2026-07-28  OK_WITH_WARNINGS  OK_WITH_WARNINGS  0
2026-07-29  OK_WITH_WARNINGS  OK_WITH_WARNINGS  0
2026-07-30  OK_WITH_WARNINGS  OK_WITH_WARNINGS  0
2026-07-31  OK_WITH_WARNINGS  OK_WITH_WARNINGS  0
2026-08-03  OK_WITH_WARNINGS  OK_WITH_WARNINGS  0
2026-08-04  OK_WITH_WARNINGS  OK_WITH_WARNINGS  0
```

Acceptance:

```text
coverage_acceptance=OK
parity_acceptance=OK
total_mismatch_count=0
```

## DC Non-Impact

The recovery did not run Datacenter calculation stages. V2-scoped `dc_*` snapshots for the recovery range were unchanged before and after EC backfill:

```text
dc_ticker_unchanged=0
dc_group_signal_unchanged=0
dc_synth_unchanged=0
dc_index_unchanged=0
```

The zero values are `cmp` exit codes and mean byte-for-byte identical.

Row counts in the compared V2 snapshots:

```text
dc_ticker_swing_signal_daily=1799
dc_group_swing_signal_daily=378
dc_group_synthetic_ohlc_daily=371
dc_group_index_daily=378
```

## V1 Non-Impact

No V1 EC rows exist on or after the active V2 date:

```text
ec_ticker_signal_daily=0
ec_group_signal_daily=0
ec_group_synthetic_ohlc_daily=0
ec_group_index_daily=0
```

This recovery did not create V1 rows.

## UI Read-Only Inspect

Read-only scheduler UI taxonomy state inspection after recovery:

```text
active_taxonomy_version=DC_TAXONOMY_FULL_V2
active_taxonomy_sha256=178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1
active_deployment_status=ACTIVE
ticker_count=257
group_count=54
synthetic_group_count=53
dc_fact_head=2026-08-04
ec_fact_head=2026-08-04
dc_watermark_head=2026-08-04
ec_watermark_head=2026-08-04
scheduler_datacenter_taxonomy_version=DC_TAXONOMY_FULL_V2
scheduler_ec_taxonomy_version=DC_TAXONOMY_FULL_V2
db_config_consistency_status=OK
blocking_errors=
```

## Final State

```text
recovery_status=OK
dc_fact_head=2026-08-04
ec_fact_head=2026-08-04
canonical_ec_watermark_head=2026-08-04
coverage_acceptance=OK
parity_acceptance=OK
total_mismatch_count=0
skip_next_run=False
datacenter_stage2_incremental_enabled=True
datacenter_stage2_overlap_trading_days=5
taxonomy_version=DC_TAXONOMY_FULL_V2
watchlist_membership_status=MATCH
ui_inspect_status=OK
```

No scheduler, pipeline, Stage 2, Datacenter recalculation, taxonomy operation, migration, external fetch, test run, automatic restore, or unrelated cleanup occurred during this recovery.
