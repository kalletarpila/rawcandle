# Datacenter Taxonomy V2 EC Cleanup and Finalization - 2026-08-04

## Final Classification

```text
repair_classification=DATACENTER_EC_V2_CLEANUP_AND_FINALIZATION_VERIFIED_READY_FOR_ACTIVATION
```

Interpretation:

```text
cleanup_status=APPLIED
finalization_status=OK
deployment_status=READY_TO_ACTIVATE
activation_status=NOT_ACTIVE
active_taxonomy_version=DC_TAXONOMY_FULL_V1
proposed_taxonomy_version=DC_TAXONOMY_FULL_V2
```

Activation was not performed. The read-only activation plan remains blocked while
the scheduler is intentionally configured to V1:

```text
activation_plan_status=BLOCKED
blocking_errors=[
  configured scheduler taxonomy CSV does not match proposed taxonomy,
  configured scheduler taxonomy version does not match proposed taxonomy
]
```

## Scope

Repository and backend version:

```text
repo=/home/kalle/projects/rawcandle
branch=chore/ignore-backups
code_commit=c51e63f3991a3f72b1eb0f9a2a475e7e37c9a3fb
code_commit_message=Implement EC taxonomy replacement cleanup backend
```

Production database and taxonomy inputs:

```text
analysis_db=/home/kalle/projects/rawcandle/data/analysis.db
ecosystem=DATACENTER
deployment_id=1
target_taxonomy_version=DC_TAXONOMY_FULL_V2
target_taxonomy_version_id=2
cleanup_date_range=2025-08-01..2026-07-31
```

Pre-existing backup was verified before writes:

```text
backup_path=temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/analysis_before_datacenter_v2_full_rebuild.sqlite
backup_sha256=ef63868f55073dd3a9eedccea5097871446b02af1577f8c4659fe6dd325db3ea
```

Taxonomy file hashes:

```text
data/datacenter_taxonomy_full_v2.csv=178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1
data/datacenter_ecosystem_taxonomy_full_v1.csv=1ad6ef41b91ef429174090bfcd338acf1e79680d939b4b788c834a79c73e9e5d
```

## Scheduler Guard

The scheduler was guarded before production writes by setting only
`skip_next_run=true`, then restored after the writes and read-only checks.

Guard apply:

```text
scheduler_config_backup=temp/datacenter_taxonomy_v2_ec_cleanup_finalization_20260804T075729Z/scheduler_config.before_guard.json
changed_keys=[skip_next_run]
unexpected_changed_keys=NONE
skip_next_run_before=false
skip_next_run_after=true
datacenter_taxonomy_version_after=DC_TAXONOMY_FULL_V1
datacenter_taxonomy_csv_after=data/datacenter_ecosystem_taxonomy_full_v1.csv
```

Guard restore:

```text
changed_keys=[skip_next_run]
unexpected_changed_keys=NONE
skip_next_run_before_restore=true
skip_next_run_after_restore=false
datacenter_taxonomy_version_after_restore=DC_TAXONOMY_FULL_V1
datacenter_taxonomy_csv_after_restore=data/datacenter_ecosystem_taxonomy_full_v1.csv
```

Final scheduler config:

```text
config_valid=true
skip_next_run=false
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V1
datacenter_taxonomy_csv=data/datacenter_ecosystem_taxonomy_full_v1.csv
datacenter_stage2_incremental_enabled=true
datacenter_stage2_overlap_trading_days=5
```

## Active Writer Checks

Host-level checks were run before writes and after completion. No active
`analysis.db` users or scheduler processes were found in these checks.

Checked patterns included:

```text
fuser analysis.db analysis.db-wal analysis.db-shm
pgrep -af stock_update_scheduler
pgrep -af run_datacenter
pgrep -af ec_taxonomy
pgrep -af analysis.db
```

## Pre-Cleanup State

Deployment row before cleanup/finalization:

```text
taxonomy_change_id=1
status=VALIDATION_REQUIRED
dc_rebuild_status=OK
ec_rebuild_status=FAILED
coverage_status=NOT_STARTED
parity_status=NOT_STARTED
activation_status=NOT_ACTIVE
rebuild_start_date=2025-08-01
```

Taxonomy active state before cleanup/finalization:

```text
DC_TAXONOMY_FULL_V1 is_active=1
DC_TAXONOMY_FULL_V2 is_active=0
```

Old V1 DATACENTER EC fact rows existed inside the cleanup range:

```text
ec_ticker_signal_daily: 12272 rows, 2026-05-18..2026-07-31
ec_group_signal_daily: 2808 rows, 2026-05-18..2026-07-31
ec_group_synthetic_ohlc_daily: 2756 rows, 2026-05-18..2026-07-31
ec_group_index_daily: 2808 rows, 2026-05-18..2026-07-31
```

V2 fact rows already covered the rebuild range:

```text
ec_ticker_signal_daily: 64507 rows, 2025-08-01..2026-07-31
ec_group_signal_daily: 13554 rows, 2025-08-01..2026-07-31
ec_group_synthetic_ohlc_daily: 13303 rows, 2025-08-01..2026-07-31
ec_group_index_daily: 13554 rows, 2025-08-01..2026-07-31
```

## Cleanup Plan

Read-only cleanup planning result:

```text
cleanup_plan_status=READY_TO_APPLY
safe_to_apply=true
cleanup_plan_hash=b43eaa2936c293faff27d79e572544c794ae738db5bcb162d15ec46addd99ce9
delete_candidate_hash=db17b3a7debb5d5b21d857e48fcb4756bede9617ec36f313d1ab2c79d8d573dd
total_delete_candidates=20644
```

Delete candidates by table:

```text
ec_ticker_signal_daily=12272
ec_group_signal_daily=2808
ec_group_synthetic_ohlc_daily=2756
ec_group_index_daily=2808
```

## Cleanup Apply

The guarded cleanup was applied exactly once using the confirmed
`delete_candidate_hash`.

```text
cleanup_apply_status=APPLIED
cleanup_applied=true
cleanup_plan_hash=b43eaa2936c293faff27d79e572544c794ae738db5bcb162d15ec46addd99ce9
delete_candidate_hash=db17b3a7debb5d5b21d857e48fcb4756bede9617ec36f313d1ab2c79d8d573dd
invocation_source=APPLY_EC_TAXONOMY_REPLACEMENT_CLEANUP
```

Deleted counts:

```text
ec_ticker_signal_daily=12272
ec_group_signal_daily=2808
ec_group_synthetic_ohlc_daily=2756
ec_group_index_daily=2808
```

Post-cleanup old V1 DATACENTER rows inside the range:

```text
ec_ticker_signal_daily=0
ec_group_signal_daily=0
ec_group_synthetic_ohlc_daily=0
ec_group_index_daily=0
```

Post-cleanup V2 rows remained:

```text
ec_ticker_signal_daily: 64507 rows, 2025-08-01..2026-07-31
ec_group_signal_daily: 13554 rows, 2025-08-01..2026-07-31
ec_group_synthetic_ohlc_daily: 13303 rows, 2025-08-01..2026-07-31
ec_group_index_daily: 13554 rows, 2025-08-01..2026-07-31
```

Independent V2 row hashes were unchanged across cleanup:

```text
v2_hashes_unchanged=true
```

## Validation-Only Finalization

The validation finalization was run without rerunning loaders or chunks:

```text
finalization_status=OK
validation_mode=EXISTING_REBUILT_FACTS
validation_status=OK
whole_range_validation_status=OK
coverage_status=OK
parity_status=OK
total_mismatch_count=0
loaders_rerun=false
chunks_rerun=false
stale_row_count=0
```

Duplicate key counts:

```text
ec_ticker_signal_daily=0
ec_group_signal_daily=0
ec_group_synthetic_ohlc_daily=0
ec_group_index_daily=0
```

EC fact heads:

```text
ec_ticker_signal_daily=2026-07-31
ec_group_signal_daily=2026-07-31
ec_group_synthetic_ohlc_daily=2026-07-31
ec_group_index_daily=2026-07-31
```

Canonical V2 watermark finalization:

```text
watermark_finalization_performed=true
watermark_advance_status=OK
watermark_candidate_latest_signal_date=2026-07-31
watermark_rows_updated=4
watermark_rows_inserted=0
watermark_rows_total=4
taxonomy_lineage_recorded=true
```

Canonical EC watermark rows after finalization:

```text
GROUP_INDEX, dc_group_index_daily, taxonomy_version_id=2, latest_signal_date=2026-07-31, status=OK
GROUP_SWING_BASE, dc_group_swing_signal_daily, taxonomy_version_id=2, latest_signal_date=2026-07-31, status=OK
SYNTHETIC_OHLC_BASE, dc_group_synthetic_ohlc_daily, taxonomy_version_id=2, latest_signal_date=2026-07-31, status=OK
TICKER_SWING_BASE, dc_ticker_swing_signal_daily, taxonomy_version_id=2, latest_signal_date=2026-07-31, status=OK
```

Noncanonical watermark rows were not advanced to V2 lineage by this task.

## Deployment Evidence

Deployment evidence update:

```text
status_update=READY_TO_ACTIVATE
ready_to_activate=true
evidence_status=READY_TO_ACTIVATE
evidence_sha256=510479fa4cc9ae9653c712690376558e1a82c3ca58787e17938187e9028792a7
```

Deployment row after finalization:

```text
taxonomy_change_id=1
status=READY_TO_ACTIVATE
dc_rebuild_status=OK
ec_rebuild_status=OK
coverage_status=OK
parity_status=OK
activation_status=NOT_ACTIVE
last_error=
```

Taxonomy active state after finalization:

```text
DC_TAXONOMY_FULL_V1 is_active=1
DC_TAXONOMY_FULL_V2 is_active=0
```

## Post-Cleanup Plan

The post-cleanup read-only plan found no remaining old-version rows in the
range. The CLI status label remains generic, but all per-table candidate counts
are zero.

```text
cleanup_plan_status=READY_TO_APPLY
safe_to_apply=true
total_delete_candidates=0
ec_ticker_signal_daily=0
ec_group_signal_daily=0
ec_group_synthetic_ohlc_daily=0
ec_group_index_daily=0
```

## Evidence Artifacts

Evidence directory:

```text
temp/datacenter_taxonomy_v2_ec_cleanup_finalization_20260804T075729Z/
```

Key artifacts:

```text
scheduler_guard_summary.json
scheduler_guard_restore_summary.json
cleanup_plan.json
pre_cleanup_hashes.json
cleanup_apply.json
post_cleanup_hashes.json
finalize_validation_watermarks.json
apply_rebuild_evidence.json
activation_plan_readonly.json
post_cleanup_plan.json
```

## Explicit Non-Actions

The following were not performed:

```text
Datacenter pipeline run
Datacenter stage run
EC loader run
EC backfill or refresh
seven chunk rebuild
scheduler run
taxonomy activation
migration
restore
new production DB backup
external fetch
unrelated cleanup
```

Only the allowed production writes were performed:

```text
old-version DATACENTER EC canonical fact cleanup inside 2025-08-01..2026-07-31
V2 canonical DATACENTER EC watermark finalization
V2 deployment cleanup/validation evidence and status update
```
