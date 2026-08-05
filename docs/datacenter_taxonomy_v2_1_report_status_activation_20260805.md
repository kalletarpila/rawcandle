# Datacenter Taxonomy V2.1 Report Status Activation 2026-08-05

## Final Classification

```text
DATACENTER_V2_1_REPORT_STATUS_ONLY_EXECUTION_FAILED_V2_REMAINS_ACTIVE
```

The controlled `REPORT_STATUS_ONLY` production execution was attempted for
`DC_TAXONOMY_FULL_V2_1`, but activation was not performed. The execution stopped
before activation because EC whole-range validation detected stale old-version
EC rows in the replacement range.

## Repository And Sources

```text
branch=chore/ignore-backups
implementation_commit=ccf1cb0
local_HEAD_before_execution=ccf1cb0505090386d8edde59c1a3941fa8622fe9
remote_HEAD_before_execution=ccf1cb0505090386d8edde59c1a3941fa8622fe9
```

Source hashes:

```text
data/datacenter_taxonomy_full_v2.csv
sha256=178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1

data/datacenter_taxonomy_full_v2_1.csv
sha256=2e27c6e68aa22c53c04e123f79744058b39a6a22b465634fda7510971c3159ef
```

No taxonomy CSV content was modified.

## Evidence Root

```text
temp/datacenter_taxonomy_v2_1_report_status_only_20260805T124038Z/
```

Key evidence files:

```text
preflight_snapshot.json
exact_diff.json
report_status_only_classification.json
plan_preview.json
pre_execution_writer_lock_guard_check.json
execution_failure_extracted_summary.json
post_failure_readonly_verification.json
deployment_2/operation_prepare_2026-08-05T124135Z_1b3a6267/prepare.json
deployment_2/operation_rebuild_2026-08-05T124226Z_c30d09ee/run_summary.json
```

## Exact Diff And Eligibility

The exact classifier accepted the change as report-status-only:

```text
change_execution_class=REPORT_STATUS_ONLY
report_status_only_safe=true
report_status_only_blocking_reasons=[]
changed_fields=notes, report_group_status, taxonomy_version
changed_rows=350
changed_tickers=257
computational_rebuild_required=false
datacenter_pipeline_required=false
stage2_required=false
```

Expected structural/computational changes were absent:

```text
ticker additions=0
ticker removals=0
layer changes=0
subindustry changes=0
primary membership changes=0
secondary membership changes=0
is_primary changes=0
role_weight changes=0
estimated_rebuild_row_count=0
affected_group_count=0
```

## Prepare Result

Unified prepare completed:

```text
prepare_status=READY_TO_REBUILD
deployment_id=2
selected_rebuild_mode=DELTA_REBUILD
change_execution_class=REPORT_STATUS_ONLY
plan_hash=a58c27c005bea5cc488d035649857988825ee8bff71120b1e2b7c6c8367a216f
date_range=2025-08-01..2026-08-04
blocking_errors=[]
```

V2.1 taxonomy metadata was loaded as inactive:

```text
DC_TAXONOMY_FULL_V2 active=true
DC_TAXONOMY_FULL_V2_1 active=false
active taxonomy count=1
```

## Guard, Lock, And Backup

Pre-execution checks:

```text
scheduler_is_running=false
taxonomy_operation_lock_active=false
skip_next_run=false
```

The rebuild CLI acquired and released the canonical taxonomy operation lock.
Final lock status:

```text
lock_active=false
```

Scheduler guard was restored:

```text
skip_next_run=false
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V2
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V2
```

Scheduler config backup:

```text
temp/datacenter_taxonomy_v2_1_report_status_only_20260805T124038Z/scheduler_config_before_execution.json
sha256=f3ecdc488c0b08bea7ce22d757056bfb7539723fee994589c27989ba33c83089
```

SQLite backup:

```text
backup_path=/home/kalle/projects/rawcandle/temp/taxonomy_change_backups/analysis_taxonomy_change_2_20260805T124226Z.sqlite
backup_mode=EXISTING_BACKUP
backup_validation_status=OK
backup_schema_compatibility_status=EXACT_MATCH
backup_size=7943979008
backup_sha256=7b00488c4f713c53641920fa270c5c35ede6d6fca89bc531e4a9d2d1430b2721
integrity_check=ok
```

No backup restore was attempted.

## Execution Command

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m rawcandle.cli.run_datacenter_taxonomy_change \
  --analysis-db data/analysis.db \
  --deployment-id 2 \
  --proposed-taxonomy-csv data/datacenter_taxonomy_full_v2_1.csv \
  --date-to 2026-08-04 \
  --scheduler-config scheduler_config.json \
  --watchlist watchlists/datacenter_watchlist.txt \
  --evidence-root temp/datacenter_taxonomy_v2_1_report_status_only_20260805T124038Z \
  --confirm-deployment-id 2 \
  --confirm-proposed-taxonomy-version DC_TAXONOMY_FULL_V2_1 \
  --confirm-proposed-source-hash 2e27c6e68aa22c53c04e123f79744058b39a6a22b465634fda7510971c3159ef \
  --confirm-date-from 2025-08-01 \
  --confirm-date-to 2026-08-04 \
  --confirm-rebuild-mode DELTA_REBUILD \
  --confirm-plan-hash a58c27c005bea5cc488d035649857988825ee8bff71120b1e2b7c6c8367a216f \
  --format json
```

Result:

```text
exit_code=1
run_status=FAILED
failed_phase=REBUILDING
failure_code=PHASE_FAILED
resume_from_phase=REBUILDING
retry_required=true
current_taxonomy_remains_active=true
scheduler_guard_restored=true
```

Completed phases:

```text
PLANNED
BACKUP
DELTA_CARRY_FORWARD
DC_REBUILD_SKIPPED_REPORT_STATUS_ONLY
```

The EC rebuild chunks completed, but whole-range validation failed:

```text
chunk_count=7
chunk_statuses=BACKFILL_COMPLETED x 7
coverage_status=OK
parity_status=OK
total_mismatch_count=0
whole_range_validation_status=FAILED
stale_validation_status=BLOCKED_STALE_ROWS
blocking_error=stale rows block whole-range validation
```

Stale EC rows reported by validation:

```text
ec_ticker_signal_daily=65257
ec_group_signal_daily=13716
ec_group_synthetic_ohlc_daily=13462
ec_group_index_daily=13716
```

## No Computational Work

Confirmed by execution phases and service dispatch:

```text
datacenter_pipeline_invoked=false
stage2_invoked=false
ticker_calculation_invoked=false
group_calculation_invoked=false
synthetic_calculation_invoked=false
group_index_calculation_invoked=false
downstream_calculation_invoked=false
report_generation_invoked=false
external_fetch_invoked=false
```

The normal DC rebuild phase did not run. The recorded phase was:

```text
DC_REBUILD_SKIPPED_REPORT_STATUS_ONLY
```

## DC Carry-Forward

Replacement range:

```text
2025-08-01..2026-08-04
```

Canonical DC target rows were created for V2.1 and heads matched V2:

| table | V2 rows in range | V2.1 rows | V2 head | V2.1 head | semantic result |
| --- | ---: | ---: | --- | --- | --- |
| `dc_ticker_swing_signal_daily` | 65021 | 65021 | 2026-08-04 | 2026-08-04 | match |
| `dc_group_synthetic_ohlc_daily` | 13409 | 13409 | 2026-08-04 | 2026-08-04 | match |
| `dc_group_swing_signal_daily` | 13662 | 13409 | 2026-08-04 | 2026-08-04 | hash mismatch |
| `dc_group_index_daily` | 13662 | 13409 | 2026-08-04 | 2026-08-04 | hash mismatch |

The group-swing and group-index mismatch is part of the failed state evidence
and must be reviewed before any retry/activation. Source V2 rows remained
present.

Other taxonomy-versioned Datacenter tables were inspected in
`post_failure_readonly_verification.json`; no price-derived recalculation was
performed.

## EC Construction

V2.1 EC target rows were constructed with head `2026-08-04` and no duplicate
target rows:

| table | V2.1 rows | head | duplicate count |
| --- | ---: | --- | ---: |
| `ec_ticker_signal_daily` | 65021 | 2026-08-04 | 0 |
| `ec_group_signal_daily` | 13409 | 2026-08-04 | 0 |
| `ec_group_synthetic_ohlc_daily` | 13409 | 2026-08-04 | 0 |
| `ec_group_index_daily` | 13409 | 2026-08-04 | 0 |

However, old V2 EC rows remained in the same replacement range, so old-version
cleanup did not reach the required final state:

| table | old V2 rows still present in range |
| --- | ---: |
| `ec_ticker_signal_daily` | 65021 |
| `ec_group_signal_daily` | 13662 |
| `ec_group_synthetic_ohlc_daily` | 13409 |
| `ec_group_index_daily` | 13662 |

## Cleanup, Watermarks, And Activation

Old-version EC cleanup did not complete because execution failed before the
post-EC cleanup/finalization phase.

Watermark finalization was not performed:

```text
watermark_finalization_performed=false
```

Canonical EC watermark lineage remained on V2:

```text
TICKER_SWING_BASE taxonomy_version_id=2 latest_signal_date=2026-08-04 status=OK
GROUP_SWING_BASE taxonomy_version_id=2 latest_signal_date=2026-08-04 status=OK
SYNTHETIC_OHLC_BASE taxonomy_version_id=2 latest_signal_date=2026-08-04 status=OK
GROUP_INDEX taxonomy_version_id=2 latest_signal_date=2026-08-04 status=OK
```

Deployment 2 final state:

```text
status=LOADED_NOT_ACTIVE
dc_rebuild_status=NOT_STARTED
ec_rebuild_status=FAILED
coverage_status=NOT_STARTED
parity_status=NOT_STARTED
activation_status=NOT_ACTIVE
last_error=stale rows block whole-range validation
```

Read-only activation plan after failure:

```text
activation_plan_status=BLOCKED
safe_to_activate=false
blocking_errors=[
  EC watermark lineage does not belong to proposed taxonomy,
  coverage is not accepted,
  full DC rebuild is incomplete,
  full EC rebuild is incomplete,
  parity is not accepted
]
```

Activation was not run.

## Final Production State

Database:

```text
DC_TAXONOMY_FULL_V2 status=ACTIVE is_active=1
DC_TAXONOMY_FULL_V2_1 status=INACTIVE is_active=0
active taxonomy count=1
```

Scheduler config:

```text
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V2
datacenter_taxonomy_csv=data/datacenter_taxonomy_full_v2.csv
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V2
ec_source_layer_taxonomy_csv=data/datacenter_taxonomy_full_v2.csv
skip_next_run=false
datacenter_stage2_incremental_enabled=true
datacenter_stage2_overlap_trading_days=5
```

## V2.1 Report Status Counts

The proposed V2.1 CSV contains:

```text
CORE=230
EXTENDED=106
WATCH_ONLY=14
```

Selected ticker statuses were written to
`post_failure_readonly_verification.json` under
`selected_tickers_from_v2_1_csv`.

Because activation failed, future reports still resolve active taxonomy metadata
from V2, not V2.1. No report generation was run.

## Explicit Non-Actions

The following did not occur:

```text
Scheduler run
Datacenter pipeline run
Stage 2 run
ticker/group/synthetic/group-index calculation
downstream technical calculation
report generation
market data fetch
migration
automatic backup restore
activation
unrelated cleanup
taxonomy CSV modification
watchlist modification
```

## Recommended Next Action

Do not activate V2.1 from deployment 2 as-is. Investigate the stale EC rows and
the group-swing/group-index DC carry-forward row-count mismatch before any retry.
The safe next backend action is reported as:

```text
safe_next_action=resume_from_failed_phase
```

## Read-Only Failure Diagnosis

Classification:

```text
DATACENTER_V2_1_RSO_FAILURE_ROOT_CAUSE_CONFIRMED
resume_classification=RESUME_FROM_OLD_EC_CLEANUP_AFTER_CODE_FIX
```

Diagnostic evidence root:

```text
temp/datacenter_v2_1_rso_failure_diagnostic/
```

This diagnosis was read-only for production state. It did not resume deployment
2, apply cleanup, rerun EC loaders, finalize watermarks, activate V2.1, modify
Scheduler config, modify facts, modify taxonomy CSVs, or restore the backup.

No-write verification after diagnosis:

```text
diagnostic_db_write_detected=false
deployment_changed=false
facts_changed=false
watermarks_changed=false
scheduler_config_changed=false
taxonomy_csv_changed=false
operation_lock_changed=false
```

### Failed Operation Evidence

Failed operation:

```text
operation_id=rebuild_2026-08-05T124226Z_c30d09ee
operation_type=REBUILD
started_at_utc=2026-08-05T124226Z
completed_at_utc=2026-08-05T124402Z
status=FAILED
failed_phase=REBUILDING
resume_from_phase=REBUILDING
```

Completed phases remained:

```text
PLANNED
BACKUP
DELTA_CARRY_FORWARD
DC_REBUILD_SKIPPED_REPORT_STATUS_ONLY
```

There was no cleanup artifact and no `CLEANUP_PLANNED`,
`OLD_EC_CLEANED`, validation, watermark-finalization, or activation phase in
the operation evidence.

### Actual Phase Order

The actual code path is:

```text
rawcandle/cli/run_datacenter_taxonomy_change.py
  main()
    -> create operation
    -> acquire taxonomy_operation_lock_context
    -> execute_taxonomy_rebuild()

rawcandle/datacenter_taxonomy_change_orchestrator.py
  execute_taxonomy_rebuild()
    -> set scheduler guard
    -> active-writer check
    -> backup
    -> copy_delta_carry_forward()
    -> REPORT_STATUS_ONLY skips DC rebuild
    -> services.run_ec_rebuild()
    -> plan_ec_taxonomy_replacement_cleanup()
    -> finalize_ec_taxonomy_rebuild_validation()
```

Relevant line evidence:

```text
rawcandle/cli/run_datacenter_taxonomy_change.py:35-58
  acquires operation lock and calls execute_taxonomy_rebuild

rawcandle/datacenter_taxonomy_change_orchestrator.py:172-179
  production DC rebuild service skips run_datacenter_swing_pipeline
  for REPORT_STATUS_ONLY

rawcandle/datacenter_taxonomy_change_orchestrator.py:1478-1501
  backup, delta carry-forward, DC_REBUILD_SKIPPED_REPORT_STATUS_ONLY,
  then services.run_ec_rebuild()

rawcandle/datacenter_taxonomy_change_orchestrator.py:1502-1512
  cleanup is planned only after services.run_ec_rebuild() returns OK

rawcandle/ec_taxonomy_full_rebuild_orchestrator.py:1458-1495
  services.run_ec_rebuild performs whole-range validation internally and
  returns FAILED before the outer cleanup phase can run

rawcandle/ec_taxonomy_full_rebuild_orchestrator.py:1025-1046
  whole-range validation calls validate_rebuild_stale_rows and blocks on
  old-version EC rows
```

Therefore `OLD_EC_CLEANED` was not scheduled in the failed run. It was not
invoked, did not fail, and was not invoked with an empty or wrong candidate set.
The phase order is wrong for this RSO/replacement path: stale-row validation ran
inside EC rebuild before the outer cleanup phase was reachable.

### Cleanup Candidate Reconstruction

Read-only cleanup planner reconstruction for deployment 2:

```text
cleanup_plan_status=BLOCKED
safe_to_apply=false
blocking_errors=[DC rebuild status is not OK]
target_taxonomy_version_id=3
date_range=2025-08-01..2026-08-04
```

The `safe_to_apply=false` result is caused by the generic cleanup precondition
that requires `dc_rebuild_status=OK`. In RSO execution, DC calculation was
intentionally skipped and deployment 2 remained:

```text
dc_rebuild_status=NOT_STARTED
```

This is a second RSO-specific orchestration bug: report-status-only DC
carry-forward success is not normalized into a cleanup-acceptable DC-complete
state.

Despite that status blocker, the cleanup candidate predicate selected exactly
the stale rows reported by whole-range validation:

| table | cleanup candidates | stale-validation count | old taxonomy IDs |
| --- | ---: | ---: | --- |
| `ec_ticker_signal_daily` | 65257 | 65257 | 1, 2 |
| `ec_group_signal_daily` | 13716 | 13716 | 1, 2 |
| `ec_group_synthetic_ohlc_daily` | 13462 | 13462 | 1, 2 |
| `ec_group_index_daily` | 13716 | 13716 | 1, 2 |

Predicate:

```sql
ecosystem_id = DATACENTER
AND taxonomy_version_id <> 3
AND signal_date BETWEEN '2025-08-01' AND '2026-08-04'
```

The stale rows are legitimate old V1/V2 EC rows awaiting guarded cleanup, not
invalid V2.1 rows.

### EC Fact State

All seven EC chunks completed:

```text
chunk_count=7
chunk_status=BACKFILL_COMPLETED for all chunks
coverage_status=OK for all chunks
parity_status=OK for all chunks
total_mismatch_count=0 for all chunks
```

Final selected date `2026-08-04`:

```text
ticker source_row_count=257 loaded_row_count=257 failed_row_count=0
group signal source_row_count=53 loaded_row_count=53 failed_row_count=0
synthetic source_row_count=53 loaded_row_count=53 failed_row_count=0
group index source_row_count=53 loaded_row_count=53 failed_row_count=0
parity total_mismatch_count=0
```

V2.1 target fact purity:

```text
ec_ticker_signal_daily distinct_ticker_count=257
missing_taxonomy_tickers=[]
unexpected_tickers=[]

ec_group_signal_daily distinct_group_count=53
missing_layers=[]
missing_subindustries=[]
unexpected_groups=[]

ec_group_synthetic_ohlc_daily distinct_group_count=53
missing_layers=[]
missing_subindustries=[]
unexpected_groups=[]

ec_group_index_daily distinct_group_count=53
missing_layers=[]
missing_subindustries=[]
unexpected_groups=[]
```

Classification:

```text
V2_1_FACT_STATE_CLEAN
EC_REBUILD_REQUIRED=false
```

### DC Carry-Forward Count Diagnosis

The previously reported group-swing and group-index row-count differences are
not caused by missing dates, wrong date range, duplicate keys, signal-version
filtering, or broad data loss. The difference is exactly one source-only
ecosystem group row per trading date:

```text
group_type=ecosystem
group_name=DC_ECOSYSTEM_TOTAL
row_key_source_only_count=253
row_key_target_only_count=0
```

Affected DC tables:

```text
dc_group_swing_signal_daily
dc_group_index_daily
```

The V2.1 target contains all 16 layer groups and 37 subindustry groups. It does
not contain the source V2 ecosystem aggregate rows. This is a carry-forward
scope bug or contract mismatch around ecosystem-level group handling, not a
price-derived recalculation defect.

EC construction and parity used the 53 taxonomy groups and completed cleanly.
Therefore this ecosystem-row omission did not cause the stale EC validation
failure. It should still be fixed or explicitly classified before activation,
because the target DC lineage is not byte-for-byte complete versus V2 for the
two group-level canonical tables.

Classification:

```text
DC_CARRY_FORWARD_INCOMPLETE
```

### Root Cause

Deepest root cause:

```text
RSO execution uses an outer cleanup phase that is ordered after services.run_ec_rebuild,
but services.run_ec_rebuild performs whole-range stale-row validation internally
before returning OK. Because old EC rows are expected to exist until cleanup,
the internal validation fails and the outer cleanup phase is never reached.
```

Secondary blockers:

```text
1. Cleanup planner requires deployment.dc_rebuild_status=OK, but RSO intentionally
   records DC_REBUILD_SKIPPED_REPORT_STATUS_ONLY and leaves dc_rebuild_status
   NOT_STARTED.

2. RSO DC carry-forward does not copy ecosystem aggregate rows
   group_type=ecosystem/group_name=DC_ECOSYSTEM_TOTAL for
   dc_group_swing_signal_daily and dc_group_index_daily.
```

### Safe Resume Point

Current DB state has complete V2.1 EC target facts and clean per-chunk
coverage/parity, but cleanup is blocked by code/status gating and the DC
ecosystem aggregate carry-forward gap remains.

Safe resume decision:

```text
safe_resume_phase=OLD_EC_CLEANED
phases_to_skip=[
  BACKUP,
  DELTA_CARRY_FORWARD for already verified ticker/layer/subindustry rows,
  DC_REBUILD,
  EC_REBUILD
]
phases_to_execute=[
  repair or explicitly waive missing DC ecosystem aggregate rows,
  OLD_EC_CLEANED,
  WHOLE_RANGE_VALIDATED,
  WATERMARKS_FINALIZED,
  READY_TO_ACTIVATE
]
backup_to_reuse=/home/kalle/projects/rawcandle/temp/taxonomy_change_backups/analysis_taxonomy_change_2_20260805T124226Z.sqlite
cleanup_required=true
DC_recopy_required=true for ecosystem aggregate rows unless contract is changed
EC_rebuild_required=false
restore_required=false
```

Top-level `resume_from_phase=REBUILDING` is too coarse. The precise safe resume
point after code correction is old-version EC cleanup, with no reason to rerun
EC target construction.

### Required Code Fix

Required before resume:

```text
1. Move old-version EC cleanup before whole-range stale validation for the
   taxonomy replacement path, or split EC rebuild so chunk loading can complete
   before cleanup and whole-range validation runs afterward.

2. Teach RSO execution to persist/normalize DC carry-forward success as a
   cleanup-acceptable DC-complete state, instead of leaving
   dc_rebuild_status=NOT_STARTED.

3. Fix or explicitly classify ecosystem aggregate group carry-forward:
   group_type=ecosystem/group_name=DC_ECOSYSTEM_TOTAL should either be copied
   for RSO target DC lineage or formally excluded from the required contract.
```

Recommended hardening:

```text
1. Add explicit phase statuses:
   DC_FACTS_CARRIED_FORWARD, EC_FACTS_CONSTRUCTED, OLD_EC_CLEANED,
   WHOLE_RANGE_VALIDATED, WATERMARKS_FINALIZED.

2. Make cleanup candidate count and stale-row count share one helper/predicate.

3. Make resume start from the earliest failed semantic phase, not generic
   REBUILDING.
```

Optional diagnostics:

```text
1. Store per-table DC carry-forward source/target row-key diffs.
2. Store cleanup candidate hashes in the failed run summary.
3. Store V2.1 target fact purity checks in operation evidence.
```

### Focused Test Plan

Add focused tests for:

```text
1. RSO phase order includes cleanup before stale validation.
2. Complete V2.1 EC facts plus old V2 rows trigger cleanup.
3. Cleanup candidate count matches old-version rows.
4. Whole-range validation passes after cleanup.
5. Cleanup failure resumes from cleanup.
6. Whole-range validation failure after successful cleanup resumes from validation.
7. Verified DC carry-forward is not repeated.
8. Verified EC construction is not repeated.
9. Cleanup uses deployment target taxonomy ID.
10. Cleanup uses deployment replacement range.
11. Another ecosystem remains untouched.
12. Rows outside range remain untouched.
13. V2.1 semantic DC equality remains zero mismatch for the chosen contract.
14. V2.1 EC coverage/parity remains zero mismatch.
15. Watermarks finalize only after cleanup and whole-range validation.
16. Deployment reaches READY_TO_ACTIVATE after resume.
17. No Datacenter pipeline or Stage 2 runs during resume.
18. Existing normal delta/full workflows remain unchanged.
```

## Code Fix Status

Final code classification:

```text
DATACENTER_RSO_CLEANUP_ORDER_AND_AGGREGATE_CARRY_FORWARD_FIXED
```

The implementation corrected the generic report-status-only execution contract:

```text
coverage/parity success
-> old-version EC cleanup
-> whole-range stale-row validation
-> watermark finalization
```

The EC full-rebuild runner can now construct target EC facts and defer
whole-range validation/finalization to the outer taxonomy-change orchestrator.
For taxonomy replacement finalization, stale-row validation is blocked unless
cleanup evidence exists for the same:

```text
deployment_id
ecosystem_code
target_taxonomy_version
target_taxonomy_version_id
date_from
date_to
```

Valid cleanup evidence status is:

```text
APPLIED
NO_CHANGE
```

Otherwise validation reports:

```text
stale_validation_status=BLOCKED_CLEANUP_NOT_COMPLETED
```

### Aggregate Carry-Forward Contract

The corrected DC carry-forward validation compares the complete explicit key
universe for the copied scope, not only taxonomy CSV group codes.

Affected required aggregate keys:

```text
dc_group_swing_signal_daily:
  group_type=ecosystem
  group_name=DC_ECOSYSTEM_TOTAL

dc_group_index_daily:
  group_type=ecosystem
  group_name=DC_ECOSYSTEM_TOTAL
```

Observed production gap remains unchanged because this task did not resume or
repair deployment 2:

```text
dc_group_swing_signal_daily missing_target_ecosystem_aggregate_keys=253
dc_group_index_daily missing_target_ecosystem_aggregate_keys=253
total_missing_target_ecosystem_aggregate_keys=506
```

Ticker rows and ordinary layer/subindustry group rows validate cleanly. The
synthetic OHLC table had no source ecosystem aggregate rows in the current
production slice and remains clean under the validated contract.

### Deployment 2 Read-Only Resume Plan After Fix

Read-only artifact:

```text
temp/datacenter_v2_1_rso_fix_validation/deployment_2_read_only_resume_plan.json
```

Result:

```text
safe_to_resume=false
resume_from_phase=DC_FACTS_CARRIED_FORWARD
DC_recopy_required=true
EC_rebuild_required=false
cleanup_required=true
restore_required=false
backup_reuse_required=true
```

Existing backup to reuse:

```text
temp/taxonomy_change_backups/analysis_taxonomy_change_2_20260805T124226Z.sqlite
sha256=7b00488c4f713c53641920fa270c5c35ede6d6fca89bc531e4a9d2d1430b2721
```

The earliest safe controlled production resume is not `OLD_EC_CLEANED` yet,
because the corrected DC key-universe validation proves the current target DC
lineage is still missing required aggregate rows. A later controlled resume
should first run the deterministic idempotent DC carry-forward repair for the
missing aggregate rows, then apply old-version EC cleanup, then run whole-range
validation and watermark finalization. EC target construction should not be
rerun unless a fresh validation shows EC facts changed or are incomplete.

No production resume, cleanup, activation, Scheduler run, Datacenter pipeline,
Stage 2, EC work, DB write, config write, backup creation, restore, migration,
or unrelated cleanup occurred during this code-fix task.
