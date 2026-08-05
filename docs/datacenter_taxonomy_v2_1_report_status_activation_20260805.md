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
