# Datacenter Taxonomy V2 EC Full Rebuild Retry 4 - 2026-08-03

## Final Classification

```text
DATACENTER_EC_V2_FULL_REBUILD_FAILED_V1_REMAINS_ACTIVE
```

The controlled production DATACENTER EC full historical rebuild for
`DC_TAXONOMY_FULL_V2` was retried once after:

```text
4672e7b Scope EC ticker loader by taxonomy
73a25ab Scope EC group loader by taxonomy
```

The retry did not complete. Chunk 1 failed on the first selected date,
`2025-08-01`, with a uniqueness violation in
`ec_group_synthetic_ohlc_daily`. Whole-range validation did not run, canonical
EC watermark finalization did not run, V2 was not activated, and V1 remained
the active scheduler taxonomy.

No second rebuild attempt, manual chunk execution, cleanup of partial V2 EC
rows, Datacenter pipeline run, scheduler run, Stage 2 run, EC refresh/backfill,
migration, restore, or activation was performed.

## Source And Repository Verification

Repository state before the retry:

```text
branch=chore/ignore-backups
HEAD=73a25ab4dbf371e94547360698c1b219daedf2b3
origin/chore/ignore-backups=73a25ab4dbf371e94547360698c1b219daedf2b3
working_tree_expected_change= M watchlists/datacenter_watchlist.txt
```

Recent history:

```text
73a25ab Scope EC group loader by taxonomy
09b1b38 Document Datacenter V2 EC rebuild retry 3
4672e7b Scope EC ticker loader by taxonomy
c12c84d Document Datacenter V2 EC rebuild retry 2
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
previous_last_error=UNIQUE constraint failed: ec_group_signal_daily.ecosystem_id, ec_group_signal_daily.taxonomy_version_id, ec_group_signal_daily.signal_date, ec_group_signal_daily.entity_id, ec_group_signal_daily.signal_version
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

V2 EC facts before the retry contained partial rows from an earlier failed
attempt:

```text
ec_ticker_signal_daily taxonomy_version_id=2 signal_date=2025-08-01 rows=257 distinct_entities=257
```

## Evidence Directory

Evidence was written under:

```text
temp/datacenter_taxonomy_v2_ec_full_rebuild_retry4_20260803T162157Z/
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
ec_fact_summary_before.csv
ec_fact_summary_after_failure.csv
ec_v2_rows_by_date_after_failure.csv
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
sha256=5b1b5abe73e81fffee76479ce7637fe2a8a4a344aae5e2917e6b4adb9b76cd76

backup_validation.json
sha256=500b4336b1b201554c552dd97a5cd6ea2b765ef02a79d04c78d91f39e99c5f7b

ec_full_rebuild_run.stdout
sha256=4d1b4922d3edda4745c7f54cd886c5c1bbb0b2416e94b877ee7f4ec53801db71
```

## Scheduler Guard And Writer Check

Before production EC writes, `skip_next_run` was set to `true`. The taxonomy
config keys remained on V1:

```text
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V1
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V1
```

The pre-write host checks found no active scheduler, Datacenter pipeline, EC
refresh/backfill, taxonomy activation, migration, or open `analysis.db` file
handle. The `fuser` host check returned no open DB handles.

After the failed retry, `scheduler_config.json` was restored byte-for-byte from
the pre-guard copy:

```text
skip_next_run=false
config_matches_before_guard=0
```

In the `cmp` check above, exit code `0` means the restored config matched the
pre-guard file exactly.

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

## Read-Only Plan

Plan result:

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
watermark_finalization_status=NOT_RUN
whole_range_validation_status=NOT_RUN
deployment_id=1
taxonomy_version=DC_TAXONOMY_FULL_V2
requested_start=2025-08-01
requested_end=2026-07-31
chunk_count=7
failed_chunk_index=1
failed_chunk_range=2025-08-01..2025-09-29
failed_date=2025-08-01
status=BACKFILL_FAILED
total_mismatch_count=0
```

Failure details:

```text
error=UNIQUE constraint failed: ec_group_synthetic_ohlc_daily.ecosystem_id, ec_group_synthetic_ohlc_daily.taxonomy_version_id, ec_group_synthetic_ohlc_daily.signal_date, ec_group_synthetic_ohlc_daily.entity_id, ec_group_synthetic_ohlc_daily.ohlc_calc_version
failed_step=load_ec_group_signal_daily_from_dc
failed_date_completed_steps=load_ec_ticker_signal_daily_from_dc, load_ec_group_signal_daily_from_dc
loader_status=OK_WITH_WARNINGS
loader_error_code=NONE
loader_error=Group signal fact loader returned FAILED
warning=Partial selected-date ec_ writes may exist; no automatic rollback was attempted
```

The progress artifact reports the failed step in the group-loader context, but
the database constraint in the same artifact names
`ec_group_synthetic_ohlc_daily`. This document records both facts without
collapsing them into a single inferred root cause.

Group-loader V2 scoping evidence for the failed date:

```text
requested_taxonomy_version=DC_TAXONOMY_FULL_V2
source_taxonomy_version=DC_TAXONOMY_FULL_V2
source_taxonomy_match=True
source_row_count=54
source_distinct_group_count=54
duplicate_source_group_count=0
unexpected_taxonomy_version_count=0
unexpected_signal_version_count=0
mapped_row_count=54
distinct_target_key_count=54
duplicate_target_key_count=0
null_target_key_count=0
unresolved_group_count=0
multiple_source_to_same_target_count=0
loaded_row_count=54
failed_row_count=0
```

Watchlist reconciliation did not change production watchlists:

```text
watchlist_membership_status=MATCH
watchlist_sync_required=False
watchlist_reconciliation_status=SKIPPED
watchlist_added_count=0
watchlist_removed_count=0
```

## Post-Failure Production State

The deployment row remained failed and not active:

```text
taxonomy_change_id=1
status=VALIDATION_REQUIRED
dc_rebuild_status=OK
ec_rebuild_status=FAILED
coverage_status=NOT_STARTED
parity_status=NOT_STARTED
activation_status=NOT_ACTIVE
last_error=UNIQUE constraint failed: ec_group_synthetic_ohlc_daily.ecosystem_id, ec_group_synthetic_ohlc_daily.taxonomy_version_id, ec_group_synthetic_ohlc_daily.signal_date, ec_group_synthetic_ohlc_daily.entity_id, ec_group_synthetic_ohlc_daily.ohlc_calc_version
```

V2 taxonomy state after the retry:

```text
DC_TAXONOMY_FULL_V1 status=ACTIVE is_active=1
DC_TAXONOMY_FULL_V2 status=INACTIVE is_active=0
```

V2 EC facts after the failed retry:

```text
ec_ticker_signal_daily              2025-08-01..2025-08-01 rows=257 dates=1
ec_group_signal_daily               2025-08-01..2025-08-01 rows=54 dates=1
ec_group_synthetic_ohlc_daily       rows=0 dates=0
ec_group_index_daily                rows=0 dates=0
```

Rows by date after failure:

```text
ec_ticker_signal_daily              2025-08-01 rows=257 distinct_entities=257
ec_group_signal_daily               2025-08-01 rows=54 distinct_entities=54
```

Canonical EC V2 watermarks were not finalized. The `ec_pipeline_watermark`
snapshot still showed existing DATACENTER canonical rows with
`taxonomy_version_id` empty and `latest_signal_date=2026-07-31`; no V2
taxonomy-specific canonical EC watermark advancement was recorded by this
failed run.

## Not Performed

The following operations were intentionally not performed:

```text
no Datacenter pipeline run
no Stage 2 run
no ordinary scheduler run
no EC latest refresh or separate EC backfill
no migration
no taxonomy activation
no scheduler taxonomy switch to V2
no V1 deactivation
no cleanup of partial V2 EC rows
no automatic restore from backup
no second rebuild attempt
no tests
```

## Next Required Action

Investigate and fix the retry4 failure before another production rebuild
attempt:

```text
failure_table=ec_group_synthetic_ohlc_daily
failure_constraint=ecosystem_id,taxonomy_version_id,signal_date,entity_id,ohlc_calc_version
failed_date=2025-08-01
partial_v2_ec_rows_present=true
retry_required=true
```

Any next retry must account for the existing partial V2 EC rows on
`2025-08-01`. V1 remains the active production taxonomy until a later rebuild
completes, whole-range validation passes, canonical EC watermarks are
finalized, and a separate activation step is explicitly performed.
