# Datacenter Taxonomy V2 EC Full Rebuild Retry 6 - 2026-08-03

## Final Classification

```text
DATACENTER_EC_V2_FULL_REBUILD_FAILED_V1_REMAINS_ACTIVE
```

The controlled production DATACENTER EC full historical rebuild for
`DC_TAXONOMY_FULL_V2` was retried once using the taxonomy-scoped loader and
audit fixes through:

```text
4672e7b Scope EC ticker loader by taxonomy
73a25ab Scope EC group loader by taxonomy
e7de27d Scope EC synthetic and index loaders by taxonomy
783e614 Scope EC audits by Datacenter taxonomy
```

All seven EC backfill chunks completed, coverage and parity were accepted for
the loaded chunks, and total mismatch count was zero. The rebuild still failed
at whole-range validation because stale EC rows were detected for the same
ecosystem and date range with a taxonomy version other than V2. Watermark
finalization did not run, rebuild evidence was not applied, V2 was not
activated, and V1 remained active.

## Repository And Source Verification

```text
branch=chore/ignore-backups
HEAD=783e614edeb8bcbb0bcd73b1bc9fc4416cc4fcc4
origin/chore/ignore-backups=783e614edeb8bcbb0bcd73b1bc9fc4416cc4fcc4
working_tree_expected_change= M watchlists/datacenter_watchlist.txt
```

Input hashes matched the required values:

```text
data/datacenter_ecosystem_taxonomy_full_v1.csv
sha256=1ad6ef41b91ef429174090bfcd338acf1e79680d939b4b788c834a79c73e9e5d

data/datacenter_taxonomy_full_v2.csv
sha256=178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1

temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/analysis_before_datacenter_v2_full_rebuild.sqlite
sha256=ef63868f55073dd3a9eedccea5097871446b02af1577f8c4659fe6dd325db3ea
```

The pre-existing `watchlists/datacenter_watchlist.txt` working-tree change was
not modified, staged, or committed.

## Starting Production State

Deployment `1` still described the V2 proposal and remained unactivated:

```text
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
source_sha256=178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1
```

Taxonomy and scheduler state:

```text
DC_TAXONOMY_FULL_V1 status=ACTIVE is_active=1
DC_TAXONOMY_FULL_V2 status=INACTIVE is_active=0

skip_next_run=false
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V1
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V1
datacenter_stage2_incremental_enabled=true
datacenter_stage2_overlap_trading_days=5
```

The partial V2 EC state for `2025-08-01` already contained complete canonical
rows before retry 6:

```text
ec_ticker_signal_daily              rows=257 distinct_entities=257
ec_group_signal_daily               rows=54  distinct_entities=54
ec_group_synthetic_ohlc_daily       rows=53  distinct_entities=53
ec_group_index_daily                rows=54  distinct_entities=54
```

## Evidence Directory

Evidence was written under:

```text
temp/datacenter_taxonomy_v2_ec_full_rebuild_retry6_20260803T190404Z/
```

Important files:

```text
activation_plan_before.json
activation_plan_after_failure.json
dc_fact_summary_before.csv
dc_watermarks_before.csv
deployment_before.csv
deployment_after_failure.csv
ec_duplicate_keys_after_failure.csv
ec_fact_summary_before.csv
ec_fact_summary_after_failure.csv
ec_full_rebuild_plan.stdout
ec_full_rebuild_run.stdout
ec_full_rebuild_run.stderr
ec_partial_20250801_before.csv
ec_partial_20250801_after_failure.csv
ec_taxonomy_full_rebuild_progress.json
ec_watermarks_before.csv
ec_watermarks_after_failure.csv
scheduler_config.before_guard.json
scheduler_config.guard_on.json
scheduler_config.before_restore.json
scheduler_config.restored.json
stale_ec_rows_after_failure.csv
taxonomy_versions_before.csv
taxonomy_versions_after_failure.csv
watchlist.sha256
```

Evidence hashes:

```text
ec_taxonomy_full_rebuild_progress.json
sha256=bbfdf42471f2a9489c518c01f853591931a7626ca17d62c00c5f001d60d25b0d

ec_full_rebuild_run.stdout
sha256=529377f15337570895d99c3629a068c1ba0ae80b11bd09a8d90400a6d103adb1
```

## Scheduler Guard And Writer Check

Before production EC writes, only `skip_next_run` was set to `true`:

```text
changed_keys=skip_next_run
unexpected_changed_keys=NONE
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V1
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V1
```

The host writer check found no active DB users:

```text
fuser: no open analysis.db handles; WAL/SHM files did not exist
pgrep: no scheduler, Datacenter, EC, UI, analysis.db, or migration runner process
```

After the failed rebuild, only `skip_next_run` was restored to `false`:

```text
changed_keys=skip_next_run
unexpected_changed_keys=NONE
skip_next_run=false
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V1
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V1
datacenter_stage2_incremental_enabled=true
datacenter_stage2_overlap_trading_days=5
```

## Backup Validation

The original production backup was reused. No new full production DB backup was
created.

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

The seven allowed live-only columns were all operational evidence columns in
`ec_taxonomy_change_deployment`.

## Read-Only Rebuild Plan

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

Top-level result:

```text
overall_status=FAILED
retry_required=true
watermark_finalization_performed=false
watermark_finalization_status=NOT_RUN
deployment_id=1
taxonomy_version=DC_TAXONOMY_FULL_V2
requested_start=2025-08-01
requested_end=2026-07-31
chunk_count=7
```

All chunks completed backfill with zero mismatches:

```text
chunk 1 2025-08-01..2025-09-29 BACKFILL_COMPLETED coverage=OK parity=OK mismatch=0 completed_dates=41
chunk 2 2025-09-30..2025-11-28 BACKFILL_COMPLETED coverage=OK parity=OK mismatch=0 completed_dates=43
chunk 3 2025-11-29..2026-01-27 BACKFILL_COMPLETED coverage=OK parity=OK mismatch=0 completed_dates=39
chunk 4 2026-01-28..2026-03-28 BACKFILL_COMPLETED coverage=OK parity=OK mismatch=0 completed_dates=42
chunk 5 2026-03-29..2026-05-27 BACKFILL_COMPLETED coverage=OK parity=OK mismatch=0 completed_dates=41
chunk 6 2026-05-28..2026-07-26 BACKFILL_COMPLETED coverage=OK parity=OK mismatch=0 completed_dates=40
chunk 7 2026-07-27..2026-07-31 BACKFILL_COMPLETED coverage=OK parity=OK mismatch=0 completed_dates=5
```

## First-Date Idempotent Replacement

For `2025-08-01`, all four canonical loaders completed and replaced the
existing partial V2 rows idempotently:

```text
ec_ticker_signal_daily              loaded_row_count=257 source_taxonomy_match=true duplicate_source_count=0 duplicate_target_count=0 unresolved_count=0
ec_group_signal_daily               loaded_row_count=54  source_taxonomy_match=true duplicate_source_count=0 duplicate_target_count=0 unresolved_count=0
ec_group_synthetic_ohlc_daily       loaded_row_count=53  source_taxonomy_match=true duplicate_source_count=0 duplicate_target_count=0 unresolved_count=0
ec_group_index_daily                loaded_row_count=54  source_taxonomy_match=true duplicate_source_count=0 duplicate_target_count=0 unresolved_count=0
```

First-date row counts after the retry:

```text
ec_ticker_signal_daily              rows=257 distinct_entities=257
ec_group_signal_daily               rows=54  distinct_entities=54
ec_group_synthetic_ohlc_daily       rows=53  distinct_entities=53
ec_group_index_daily                rows=54  distinct_entities=54
```

First-date coverage and parity:

```text
coverage_execution_status=COMPLETED
coverage_status=OK_WITH_WARNINGS
requested_taxonomy_version=DC_TAXONOMY_FULL_V2
dc_source_taxonomy_match=true
dc_ticker_count=257
taxonomy_ticker_count=257
unexpected_dc_tickers=[]
missing_primary_membership_tickers=[]

parity_execution_status=COMPLETED
parity_status=OK_WITH_WARNINGS
total_mismatch_count=0
ticker/group/synthetic/index target rows=257/54/53/54
```

## Whole-Range Validation Failure

The full V2 EC fact heads reached the requested range:

```text
ec_ticker_signal_daily              2025-08-01..2026-07-31 rows=64507 dates=251
ec_group_signal_daily               2025-08-01..2026-07-31 rows=13554 dates=251
ec_group_synthetic_ohlc_daily       2025-08-01..2026-07-31 rows=13303 dates=251
ec_group_index_daily                2025-08-01..2026-07-31 rows=13554 dates=251
```

Duplicate-key validation after the failed attempt:

```text
ec_ticker_signal_daily              duplicate_keys=0
ec_group_signal_daily               duplicate_keys=0
ec_group_synthetic_ohlc_daily       duplicate_keys=0
ec_group_index_daily                duplicate_keys=0
```

Whole-range validation failed:

```text
whole_range_validation_status=FAILED
coverage_status=OK
parity_status=OK
total_mismatch_count=0
blocking_errors=["stale rows block whole-range validation"]
```

Stale-row validation details:

```text
stale_validation_status=BLOCKED_STALE_ROWS
stale_dc_rows={}
stale_ec_rows:
  ec_ticker_signal_daily=12272
  ec_group_signal_daily=2808
  ec_group_synthetic_ohlc_daily=2756
  ec_group_index_daily=2808
```

The stale EC counts are produced by the current validation rule for same
ecosystem/date-range EC rows whose `taxonomy_version_id` is not V2. Existing V1
EC rows therefore block whole-range validation. No cleanup or restore was
performed during this task.

## Watermarks, Deployment, And Activation

Watermark finalization did not run:

```text
watermark_finalization_status=NOT_RUN
watermark_finalization_performed=false
```

DATACENTER canonical EC watermark rows remained without V2 lineage:

```text
dc_ticker_swing_signal_daily          taxonomy_version_id=NULL latest_signal_date=2026-07-31 status=OK
dc_group_swing_signal_daily           taxonomy_version_id=NULL latest_signal_date=2026-07-31 status=OK
dc_group_synthetic_ohlc_daily         taxonomy_version_id=NULL latest_signal_date=2026-07-31 status=OK
dc_group_index_daily                  taxonomy_version_id=NULL latest_signal_date=2026-07-31 status=OK
```

Deployment state after failure:

```text
status=VALIDATION_REQUIRED
dc_rebuild_status=OK
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
blocking_errors:
  EC watermark lineage does not belong to proposed taxonomy
  configured scheduler taxonomy CSV does not match proposed taxonomy
  configured scheduler taxonomy version does not match proposed taxonomy
  coverage is not accepted
  full EC rebuild is incomplete
  parity is not accepted
```

Final taxonomy and scheduler state:

```text
DC_TAXONOMY_FULL_V1 status=ACTIVE is_active=1
DC_TAXONOMY_FULL_V2 status=INACTIVE is_active=0

skip_next_run=false
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V1
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V1
datacenter_stage2_incremental_enabled=true
datacenter_stage2_overlap_trading_days=5
```

## Actions Not Performed

The following actions were intentionally not performed:

```text
Datacenter pipeline rerun
Stage 2 rerun
manual chunk execution
automatic EC rebuild retry
ordinary stock scheduler run
ordinary EC latest refresh
ordinary EC backfill
external data fetch
taxonomy CSV modification
watchlist modification
V2 activation
V1 deactivation
scheduler taxonomy switch
unrelated migration
new full production DB backup
automatic backup restore
cleanup of stale or partial rows
apply_datacenter_taxonomy_rebuild_evidence
test suite
```

## Operational Conclusion

Retry 6 proves that the taxonomy-scoped loaders and audits can rebuild the V2
DATACENTER EC facts across the accepted historical range with zero parity
mismatches. The remaining blocker is not loader coverage or fact parity; it is
the whole-range stale-row rule, which currently treats same-ecosystem non-V2 EC
rows in the rebuild range as blocking stale rows.

The production state remains conservative:

```text
V1 remains active
V2 remains inactive
scheduler remains on V1
deployment ec_rebuild_status=FAILED
activation_status=NOT_ACTIVE
retry_required=true
```
