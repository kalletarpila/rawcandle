# Datacenter V2 EC Full Rebuild Retry 2026-08-03

## Final Classification

```text
DATACENTER_EC_V2_FULL_REBUILD_FAILED_V1_REMAINS_ACTIVE
```

The controlled DATACENTER EC V2 full historical rebuild retry was attempted
once through the chunked orchestrator and stopped on the first chunk. No manual
chunk execution or automatic retry was performed.

## Source State

```text
branch=chore/ignore-backups
head=ba688654d800fc693f9f5728af7133257469f593
origin/chore/ignore-backups=ba688654d800fc693f9f5728af7133257469f593
```

Relevant backend commits:

```text
174de0e Implement Datacenter V2 DC rebuild acceptance
da52920 Add EC taxonomy full rebuild orchestrator
88bb13f Allow EC taxonomy rebuild to reuse production backup
ba68865 Allow compatible EC rebuild backup schema drift
```

Source checks:

```text
V1 taxonomy sha256=1ad6ef41b91ef429174090bfcd338acf1e79680d939b4b788c834a79c73e9e5d
V2 taxonomy sha256=178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1
original backup sha256=ef63868f55073dd3a9eedccea5097871446b02af1577f8c4659fe6dd325db3ea
```

The only pre-existing working-tree change was:

```text
 M watchlists/datacenter_watchlist.txt
```

It was not modified, staged, or committed by this retry.

## Starting Deployment State

```text
deployment_id=1
previous_taxonomy_version=DC_TAXONOMY_FULL_V1
proposed_taxonomy_version=DC_TAXONOMY_FULL_V2
source_sha256=178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1
rebuild_start_date=2025-08-01
status=VALIDATION_REQUIRED
dc_rebuild_status=OK
ec_rebuild_status=NOT_STARTED
coverage_status=NOT_STARTED
parity_status=NOT_STARTED
activation_status=NOT_ACTIVE
rebuild_evidence_sha256=8e76a1628596f6d63b6b724596bc38069830cbb120643a903d5cc418097ea2db
validation_evidence_sha256=3eead839b014a222afebdbfd7faf2dca3136e72f6bed15368702474874d4349d
```

Accepted V2 DC facts and V2 DC watermarks were complete through
`2026-07-31` before the retry. The retry did not rerun the Datacenter pipeline
and did not alter V2 DC facts or V2 DC watermarks.

## Evidence Directory

```text
temp/datacenter_taxonomy_v2_ec_full_rebuild_retry_20260803T114925Z/
```

Key evidence files:

```text
scheduler_config_before_guard_20260803T114925Z.json
scheduler_guard_set_evidence.json
active_writer_check_evidence.json
original_backup_validation_evidence.json
pre_ec_rebuild_snapshot.json
pre_activation_plan.json
ec_full_rebuild_plan.json
ec_full_rebuild_plan_command.json
ec_full_rebuild_run_command.json
ec_full_rebuild_run_capture_summary.json
ec_taxonomy_full_rebuild_progress.json
post_failed_ec_rebuild_snapshot.json
post_failure_activation_plan.json
failed_retry_pre_post_comparison.json
scheduler_guard_restore_evidence.json
```

## Scheduler Guard and Writer Check

The scheduler guard was set before production EC execution:

```text
skip_next_run: false -> true
unexpected_changed_keys=NONE
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V1
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V1
```

Active-writer check result:

```text
active_writer_check_status=OK
active_db_processes_detected=false
data/analysis.db-wal exists=false
data/analysis.db-shm exists=false
```

The guard was restored after the failed orchestrator attempt:

```text
skip_next_run: true -> false
unexpected_changed_keys=NONE
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V1
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V1
```

## Original Backup Validation

Original backup:

```text
temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/analysis_before_datacenter_v2_full_rebuild.sqlite
```

Validation result:

```text
backup_mode=EXISTING_BACKUP
backup_created_by_orchestrator=false
backup_reused=true
backup_validation_status=OK
backup_schema_compatibility_status=COMPATIBLE_ADDITIVE_DRIFT
backup_schema_exact_match=false
backup_schema_compatible_with_live=true
backup_schema_critical_mismatch_count=0
backup_schema_allowed_difference_count=7
backup_restore_requires_forward_schema_reapply=true
backup_sha256=ef63868f55073dd3a9eedccea5097871446b02af1577f8c4659fe6dd325db3ea
backup_error=null
```

Allowed live-only columns on `ec_taxonomy_change_deployment`:

```text
last_error
prepared_at_utc
rebuild_evidence_json
rebuild_evidence_sha256
validation_completed_at_utc
validation_evidence_json
validation_evidence_sha256
```

No fallback backup was created. The retry evidence backup directory remained
empty.

## Read-Only Plan

Plan command:

```bash
python3 -m rawcandle.cli.plan_ec_taxonomy_full_rebuild \
  --db /home/kalle/projects/rawcandle/data/analysis.db \
  --ecosystem DATACENTER \
  --taxonomy-version DC_TAXONOMY_FULL_V2 \
  --taxonomy-csv /home/kalle/projects/rawcandle/data/datacenter_taxonomy_full_v2.csv \
  --watchlist /home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt \
  --deployment-id 1 \
  --date-from 2025-08-01 \
  --date-to 2026-07-31 \
  --backup-dir /home/kalle/projects/rawcandle/temp/datacenter_taxonomy_v2_ec_full_rebuild_retry_20260803T114925Z/backups \
  --evidence-output-root /home/kalle/projects/rawcandle/temp/datacenter_taxonomy_v2_ec_full_rebuild_retry_20260803T114925Z \
  --confirm-db /home/kalle/projects/rawcandle/data/analysis.db \
  --confirm-ecosystem DATACENTER \
  --confirm-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --confirm-deployment-id 1 \
  --confirm-date-from 2025-08-01 \
  --confirm-date-to 2026-07-31 \
  --expected-active-taxonomy-version DC_TAXONOMY_FULL_V1 \
  --scheduler-config /home/kalle/projects/rawcandle/scheduler_config.json \
  --repo-root /home/kalle/projects/rawcandle
```

Plan result:

```text
exit_code=0
status=READY_TAXONOMY_FULL_REBUILD_PLAN
safe_to_run=true
rebuild_mode=TAXONOMY_FULL_REBUILD
requested_start=2025-08-01
requested_end=2026-07-31
taxonomy_version_id=2
chunk_count=7
chunk_plan_hash=d18633422e76197901112f89b514eac940634869122538d6012eda9d20375e76
blocking_errors=[]
```

Chunk plan:

```text
1: 2025-08-01..2025-09-29 span=60
2: 2025-09-30..2025-11-28 span=60
3: 2025-11-29..2026-01-27 span=60
4: 2026-01-28..2026-03-28 span=60
5: 2026-03-29..2026-05-27 span=60
6: 2026-05-28..2026-07-26 span=60
7: 2026-07-27..2026-07-31 span=5
```

Chunks were chronological, gapless, non-overlapping, and within the 60 calendar
day limit.

## Orchestrated Retry

Run command:

```bash
python3 -m rawcandle.cli.run_ec_taxonomy_full_rebuild \
  --db /home/kalle/projects/rawcandle/data/analysis.db \
  --ecosystem DATACENTER \
  --taxonomy-version DC_TAXONOMY_FULL_V2 \
  --taxonomy-csv /home/kalle/projects/rawcandle/data/datacenter_taxonomy_full_v2.csv \
  --watchlist /home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt \
  --deployment-id 1 \
  --date-from 2025-08-01 \
  --date-to 2026-07-31 \
  --backup-dir /home/kalle/projects/rawcandle/temp/datacenter_taxonomy_v2_ec_full_rebuild_retry_20260803T114925Z/backups \
  --evidence-output-root /home/kalle/projects/rawcandle/temp/datacenter_taxonomy_v2_ec_full_rebuild_retry_20260803T114925Z \
  --confirm-db /home/kalle/projects/rawcandle/data/analysis.db \
  --confirm-ecosystem DATACENTER \
  --confirm-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --confirm-deployment-id 1 \
  --confirm-date-from 2025-08-01 \
  --confirm-date-to 2026-07-31 \
  --existing-backup-path temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/analysis_before_datacenter_v2_full_rebuild.sqlite \
  --confirm-existing-backup-path /home/kalle/projects/rawcandle/temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/analysis_before_datacenter_v2_full_rebuild.sqlite \
  --expected-active-taxonomy-version DC_TAXONOMY_FULL_V1 \
  --scheduler-config /home/kalle/projects/rawcandle/scheduler_config.json \
  --repo-root /home/kalle/projects/rawcandle
```

Run result:

```text
exit_code=1
duration_seconds=36.215
overall_status=FAILED
retry_required=true
watermark_finalization_performed=false
progress_path=/home/kalle/projects/rawcandle/temp/datacenter_taxonomy_v2_ec_full_rebuild_retry_20260803T114925Z/ec_taxonomy_full_rebuild_progress.json
progress_sha256=a9bdc5cc4245f61faec48a59df62f10901e51fa699e490f145e87eb0099bb99f
```

Per-chunk result:

```text
chunk=1
range=2025-08-01..2025-09-29
status=BACKFILL_REFUSED
selected_dates=0
completed_dates=0
skipped_dates=0
coverage_status=OK
parity_status=OK
total_mismatch_count=0
error=planner gate did not pass: BLOCKED_TAXONOMY_SOURCE
```

The orchestrator stopped immediately. Chunks 2-7 were not executed.

Root planner gate:

```text
compatibility_summary.status=BLOCKED_TAXONOMY_SOURCE
compatibility_summary.error=taxonomy row_count expected 329 but got 350; taxonomy distinct_ticker_count expected 236 but got 257
```

## Post-Failure State

Deployment row after failure:

```text
status=VALIDATION_REQUIRED
dc_rebuild_status=OK
ec_rebuild_status=FAILED
coverage_status=NOT_STARTED
parity_status=NOT_STARTED
activation_status=NOT_ACTIVE
last_error=planner gate did not pass: BLOCKED_TAXONOMY_SOURCE
```

Safety comparison:

```text
ec_fact_summary_unchanged=true
ec_watermarks_unchanged=true
dc_watermarks_v2_unchanged=true
unrelated_ecosystems_unchanged=true
new_full_backups_created=0
scheduler_config_after_restore_v1=true
```

Whole-range validation did not run because the first chunk was refused before
EC fact writes. Stale-row validation and canonical EC watermark finalization
therefore did not run.

## Activation Plan After Failure

Read-only activation plan:

```text
activation_plan_status=BLOCKED
safe_to_activate=false
```

Blocking gates:

```text
EC fact head incomplete for ec_group_index_daily
EC fact head incomplete for ec_group_signal_daily
EC fact head incomplete for ec_group_synthetic_ohlc_daily
EC fact head incomplete for ec_ticker_signal_daily
EC watermark lineage does not belong to proposed taxonomy
configured scheduler taxonomy CSV does not match proposed taxonomy
configured scheduler taxonomy version does not match proposed taxonomy
coverage is not accepted
full EC rebuild is incomplete
parity is not accepted
```

## Explicit Non-Actions

This retry did not:

```text
rerun the Datacenter pipeline
run any DC stage
alter accepted V2 DC facts
alter V2 DC watermarks
activate V2
mark V1 inactive
switch scheduler taxonomy configuration
run the ordinary stock update scheduler
fetch external data
apply unrelated migrations
perform unrelated cleanup
create a second full DB backup
automatically restore the original backup
run tests
manually execute chunks
automatically retry after failure
```

Final active taxonomy state:

```text
V1 active=true
V2 active=false
scheduler taxonomy=DC_TAXONOMY_FULL_V1
```
