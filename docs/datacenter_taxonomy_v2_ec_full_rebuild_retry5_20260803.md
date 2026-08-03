# Datacenter Taxonomy V2 EC Full Rebuild Retry 5 - 2026-08-03

## Final Classification

```text
DATACENTER_EC_V2_FULL_REBUILD_FAILED_V1_REMAINS_ACTIVE
```

The controlled production DATACENTER EC full historical rebuild for
`DC_TAXONOMY_FULL_V2` was retried once after the loader scoping fixes:

```text
4672e7b Scope EC ticker loader by taxonomy
73a25ab Scope EC group loader by taxonomy
e7de27d Scope EC synthetic and index loaders by taxonomy
```

The retry did not complete. Chunk 1 failed on the first selected date,
`2025-08-01`, during `audit_dc_facts_against_ec_sidecar`:

```text
Coverage audit returned non-success status: FAILED
```

The previous uniqueness failure was not reproduced. The four EC loaders
completed for `2025-08-01`, parity reported zero mismatches, but the coverage
audit still failed because the requested chunk/range was not fully covered.
No chunk completed, canonical EC watermark finalization did not run, rebuild
evidence was not applied, V2 was not activated, and V1 remained the active
scheduler taxonomy.

No second rebuild attempt, manual chunk execution, cleanup of partial V2 EC
rows, Datacenter pipeline run, scheduler run, Stage 2 run, EC latest refresh,
ordinary EC backfill, migration, restore, activation, or taxonomy/watchlist
edit was performed.

## Source And Repository Verification

Repository state before the retry:

```text
branch=chore/ignore-backups
HEAD=e7de27de1d31ede01d696da5cec360762ef913ef
origin/chore/ignore-backups=e7de27de1d31ede01d696da5cec360762ef913ef
working_tree_expected_change= M watchlists/datacenter_watchlist.txt
```

Recent relevant history:

```text
e7de27d Scope EC synthetic and index loaders by taxonomy
73a25ab Scope EC group loader by taxonomy
4672e7b Scope EC ticker loader by taxonomy
```

The pre-existing `watchlists/datacenter_watchlist.txt` working-tree change was
not modified, staged, or committed by this retry.

Taxonomy and backup hashes:

```text
data/datacenter_ecosystem_taxonomy_full_v1.csv
sha256=1ad6ef41b91ef429174090bfcd338acf1e79680d939b4b788c834a79c73e9e5d

data/datacenter_taxonomy_full_v2.csv
sha256=178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1

temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/analysis_before_datacenter_v2_full_rebuild.sqlite
sha256=ef63868f55073dd3a9eedccea5097871446b02af1577f8c4659fe6dd325db3ea
```

## Initial Production State

Deployment row before the retry:

```text
taxonomy_change_id=1
ecosystem_code=DATACENTER
previous_taxonomy_version=DC_TAXONOMY_FULL_V1
proposed_taxonomy_version=DC_TAXONOMY_FULL_V2
status=VALIDATION_REQUIRED
dc_rebuild_status=OK
ec_rebuild_status=FAILED
coverage_status=NOT_STARTED
parity_status=NOT_STARTED
activation_status=NOT_ACTIVE
rebuild_start_date=2025-08-01
previous_last_error=UNIQUE constraint failed: ec_group_synthetic_ohlc_daily.ecosystem_id, ec_group_synthetic_ohlc_daily.taxonomy_version_id, ec_group_synthetic_ohlc_daily.signal_date, ec_group_synthetic_ohlc_daily.entity_id, ec_group_synthetic_ohlc_daily.ohlc_calc_version
```

Taxonomy state before and after the retry:

```text
DC_TAXONOMY_FULL_V1 status=ACTIVE is_active=1
DC_TAXONOMY_FULL_V2 status=INACTIVE is_active=0
```

Scheduler config before guard and after guard restoration:

```text
skip_next_run=false
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V1
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V1
datacenter_stage2_incremental_enabled=true
datacenter_stage2_overlap_trading_days=5
```

Accepted V2 DC facts were already present before the retry:

```text
dc_ticker_swing_signal_daily        2025-08-01..2026-07-31 rows=64507 dates=251
dc_group_swing_signal_daily         2025-08-01..2026-07-31 rows=13554 dates=251
dc_group_synthetic_ohlc_daily       2025-08-01..2026-07-31 rows=13303 dates=251
dc_group_index_daily                2020-01-02..2026-07-31 rows=89262 dates=1653
```

V2 EC facts before the retry contained partial rows from earlier failed
attempts:

```text
ec_ticker_signal_daily              2025-08-01 rows=257 distinct_entities=257
ec_group_signal_daily               2025-08-01 rows=54  distinct_entities=54
ec_group_synthetic_ohlc_daily       no V2 rows
ec_group_index_daily                no V2 rows
```

## Evidence Directory

Evidence was written under:

```text
temp/datacenter_taxonomy_v2_ec_full_rebuild_retry5_20260803T165421Z/
```

Important evidence files:

```text
backup_validation.json
ec_full_rebuild_plan.stdout
ec_full_rebuild_plan.stderr
ec_full_rebuild_run.stdout
ec_full_rebuild_run.stderr
ec_taxonomy_full_rebuild_progress.json
failed_chunk_summary_after_failure.txt
deployment_before.csv
deployment_after_failure.csv
dc_fact_summary_before.csv
dc_watermarks_before.csv
ec_fact_summary_before.csv
ec_fact_summary_after_failure.csv
ec_partial_20250801_before.csv
ec_partial_20250801_after_failure.csv
ec_watermarks_before.csv
ec_watermarks_after_failure.csv
taxonomy_versions_before.csv
taxonomy_versions_after_failure.csv
scheduler_config.before_guard.json
scheduler_config.guard_on.json
scheduler_config.before_restore.json
scheduler_config.restored.json
```

Evidence hashes:

```text
ec_taxonomy_full_rebuild_progress.json
sha256=21042ff8f746b1d2fe134aa1a13f03e5d43a094b3dfdefd67a924784ba9caf03

backup_validation.json
sha256=a1176db359dd6d0c17463e99ea09a8ab7711a0e5aba2e2735b2d9ab15ac02a6d

ec_full_rebuild_run.stdout
sha256=c90f1132c872d73f5d0e5450cb782b69929a8280a0e95018d37a702b326cac9f
```

## Scheduler Guard And Writer Check

Before production EC writes, `skip_next_run` was set to `true`. The taxonomy
config keys remained on V1:

```text
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V1
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V1
```

The pre-write process check found only the check command itself. The host
`fuser` check returned no open `analysis.db`, WAL, or SHM handles.

After the failed retry, `scheduler_config.json` was restored byte-for-byte from
the pre-guard copy:

```text
skip_next_run=false
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V1
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V1
datacenter_stage2_incremental_enabled=true
datacenter_stage2_overlap_trading_days=5
config_matches_before_guard=true
```

## Existing Backup Validation

The original pre-DC-rebuild backup was reused. No new full production DB backup
was created.

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

Allowed live-only columns were all in `ec_taxonomy_change_deployment`:

```text
last_error
prepared_at_utc
rebuild_evidence_json
rebuild_evidence_sha256
validation_completed_at_utc
validation_evidence_json
validation_evidence_sha256
```

## Read-Only Plans

The activation plan before the retry was blocked, as expected:

```text
activation_plan_status=BLOCKED
safe_to_activate=false
blocking_errors include:
- EC fact head incomplete for all four canonical EC fact tables
- EC watermark lineage does not belong to proposed taxonomy
- coverage is not accepted
- full EC rebuild is incomplete
- parity is not accepted
```

The full rebuild plan was ready:

```text
status=READY_TAXONOMY_FULL_REBUILD_PLAN
rebuild_mode=TAXONOMY_FULL_REBUILD
deployment_id=1
taxonomy_version=DC_TAXONOMY_FULL_V2
taxonomy_version_id=2
requested_start=2025-08-01
requested_end=2026-07-31
chunk_count=7
chunk_plan_hash=d18633422e76197901112f89b514eac940634869122538d6012eda9d20375e76
```

Chunk plan:

```text
chunk 1: 2025-08-01..2025-09-29 span=60
chunk 2: 2025-09-30..2025-11-28 span=60
chunk 3: 2025-11-29..2026-01-27 span=60
chunk 4: 2026-01-28..2026-03-28 span=60
chunk 5: 2026-03-29..2026-05-27 span=60
chunk 6: 2026-05-28..2026-07-26 span=60
chunk 7: 2026-07-27..2026-07-31 span=5
```

## Rebuild Attempt

Exactly one orchestrated rebuild attempt was run. No manual chunk execution and
no automatic retry was performed.

Result:

```text
overall_status=FAILED
retry_required=True
watermark_finalization_performed=False
completed_chunk_count=0
failed_chunk_index=1
failed_chunk_range=2025-08-01..2025-09-29
failed_chunk_status=BACKFILL_FAILED
failed_date=2025-08-01
failed_step=audit_dc_facts_against_ec_sidecar
error=Coverage audit returned non-success status: FAILED
coverage_status=OK
parity_status=OK
total_mismatch_count=0
```

Completed steps for the failed date:

```text
load_ec_ticker_signal_daily_from_dc
load_ec_group_signal_daily_from_dc
load_ec_group_synthetic_ohlc_daily_from_dc
load_ec_group_index_daily_from_dc
audit_dc_facts_against_ec_sidecar
```

The taxonomy rebuild EC scope cleanup and reload for `2025-08-01` reported:

```text
status=OK
ecosystem_id=1
taxonomy_version_id=2
deleted_row_count=311
deleted_rows:
  ec_ticker_signal_daily=257
  ec_group_signal_daily=54
  ec_group_synthetic_ohlc_daily=0
  ec_group_index_daily=0
```

The first-date loaders left this V2 EC state:

```text
ec_ticker_signal_daily              2025-08-01 rows=257 distinct_entities=257
ec_group_signal_daily               2025-08-01 rows=54  distinct_entities=54
ec_group_synthetic_ohlc_daily       2025-08-01 rows=53  distinct_entities=53
ec_group_index_daily                2025-08-01 rows=54  distinct_entities=54
```

The planner/audit state still showed incomplete range coverage:

```text
planner_summary.loaded_state.missing_dates_count=40
planner_summary.loaded_state.missing_dates_sample=2025-08-04,2025-08-05,2025-08-06,2025-08-07,2025-08-08
planner_summary.schema_state.required_ec_missing_count=0
planner_summary.source_date_availability.missing_source_dates_count=19
planner_summary.source_readiness.missing_tables_count=0
```

## Production State After Failure

Deployment row after the failed retry:

```text
taxonomy_change_id=1
ecosystem_code=DATACENTER
previous_taxonomy_version=DC_TAXONOMY_FULL_V1
proposed_taxonomy_version=DC_TAXONOMY_FULL_V2
status=VALIDATION_REQUIRED
dc_rebuild_status=OK
ec_rebuild_status=FAILED
coverage_status=NOT_STARTED
parity_status=NOT_STARTED
activation_status=NOT_ACTIVE
rebuild_start_date=2025-08-01
last_error=Coverage audit returned non-success status: FAILED
```

V2 EC fact summary after the failed retry:

```text
ec_ticker_signal_daily              2025-08-01..2025-08-01 rows=257 dates=1
ec_group_signal_daily               2025-08-01..2025-08-01 rows=54  dates=1
ec_group_synthetic_ohlc_daily       2025-08-01..2025-08-01 rows=53  dates=1
ec_group_index_daily                2025-08-01..2025-08-01 rows=54  dates=1
```

DATACENTER EC watermarks after the failed retry remained non-finalized for V2:

```text
TICKER_SWING_BASE      source=dc_ticker_swing_signal_daily        taxonomy_version_id=NULL latest_signal_date=2026-07-31 status=OK
GROUP_SWING_BASE       source=dc_group_swing_signal_daily         taxonomy_version_id=NULL latest_signal_date=2026-07-31 status=OK
SYNTHETIC_OHLC_BASE    source=dc_group_synthetic_ohlc_daily       taxonomy_version_id=NULL latest_signal_date=2026-07-31 status=OK
GROUP_INDEX            source=dc_group_index_daily                taxonomy_version_id=NULL latest_signal_date=2026-07-31 status=OK
```

Because `taxonomy_version_id` is still `NULL`, these canonical EC watermark
rows do not establish V2 lineage. The rebuild remains incomplete and must not
be used as activation evidence.

Final taxonomy and scheduler state:

```text
DC_TAXONOMY_FULL_V1 status=ACTIVE is_active=1
DC_TAXONOMY_FULL_V2 status=INACTIVE is_active=0
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V1
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V1
skip_next_run=false
```

## Actions Not Performed

The following actions were intentionally not performed:

```text
second EC full rebuild attempt
manual chunk execution
manual cleanup of partial V2 EC rows
backup restore
new full production DB backup
Datacenter pipeline run
Stage 2 run
scheduler run
ordinary stock scheduler run
EC latest refresh
ordinary EC backfill
watermark finalization
apply_datacenter_taxonomy_rebuild_evidence
activation after-plan
V2 activation
V1 deactivation
scheduler taxonomy switch
taxonomy CSV modification
watchlist modification
migration
test suite
```

## Operational Conclusion

Retry 5 confirms that the synthetic/index taxonomy scoping fix removed the
previous duplicate-key failure path, but the full rebuild still fails before
chunk completion because the coverage audit expects more complete range
coverage than the first-date failure path provides.

The production state is intentionally left conservative:

```text
V1 remains active
V2 remains inactive
deployment ec_rebuild_status=FAILED
coverage_status=NOT_STARTED
parity_status=NOT_STARTED
activation_status=NOT_ACTIVE
retry_required=true
```

The next investigation should focus on the rebuild chunk coverage semantics:
the loaders can replace the first selected date successfully, but the
sidecar/coverage audit still evaluates the incomplete chunk/range as failed
before any chunk can be marked complete.
