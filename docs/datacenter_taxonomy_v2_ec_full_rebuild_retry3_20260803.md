# Datacenter Taxonomy V2 EC Full Rebuild Retry 3 - 2026-08-03

## Final Classification

```text
DATACENTER_EC_V2_FULL_REBUILD_FAILED_V1_REMAINS_ACTIVE
```

The controlled production DATACENTER EC full historical rebuild for
`DC_TAXONOMY_FULL_V2` was retried once after:

```text
4672e7b Scope EC ticker loader by taxonomy
```

The retry did not complete. Chunk 1 failed on the first selected date,
`2025-08-01`, while inserting `ec_group_signal_daily` rows. No chunk completed,
whole-range validation did not run, canonical EC watermark finalization did not
run, V2 was not activated, and V1 remained the active scheduler taxonomy.

## Source And Repository Verification

Repository state before the retry:

```text
branch=chore/ignore-backups
HEAD=4672e7b0680699f50236c502925ee6f11f6c35c5
origin/chore/ignore-backups=4672e7b0680699f50236c502925ee6f11f6c35c5
working_tree_expected_change= M watchlists/datacenter_watchlist.txt
```

Relevant backend commits present in history:

```text
174de0e Implement Datacenter V2 DC rebuild acceptance
da52920 Add EC taxonomy full rebuild orchestrator
88bb13f Allow EC taxonomy rebuild to reuse production backup
ba68865 Allow compatible EC rebuild backup schema drift
e9567fe Fix EC rebuild proposed taxonomy validation
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
previous_last_error=Ticker fact loader returned FAILED
```

Taxonomy state before and after the retry:

```text
DC_TAXONOMY_FULL_V1 status=ACTIVE is_active=1
DC_TAXONOMY_FULL_V2 status=INACTIVE is_active=0
```

Scheduler config after guard restoration:

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

V2 EC facts before the retry:

```text
ec_ticker_signal_daily              rows=0 dates=0
ec_group_signal_daily               rows=0 dates=0
ec_group_synthetic_ohlc_daily       rows=0 dates=0
ec_group_index_daily                rows=0 dates=0
```

No Datacenter pipeline or DC stage was run during this retry.

## Evidence Directory

Evidence was written under:

```text
temp/datacenter_taxonomy_v2_ec_full_rebuild_retry3_20260803T153541Z/
```

Important evidence files:

```text
backup_validation.json
ec_full_rebuild_plan.stdout
ec_full_rebuild_plan.stderr
ec_full_rebuild_run.stdout
ec_full_rebuild_run.stderr
ec_taxonomy_full_rebuild_progress.json
progress_summary.json
deployment_before.csv
deployment_after_failure.csv
dc_fact_summary_before.csv
ec_fact_summary_before.csv
ec_fact_summary_after_failure.csv
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
sha256=de7b18d6224ad254058fb27e85cdd1750b062c4b57e0a6e6e273d85e05ebcb70

progress_summary.json
sha256=36034c315f19068ad0c47e2936d2aeebb5def78a2c6c2fe228adc17f55cfb819

backup_validation.json
sha256=500b4336b1b201554c552dd97a5cd6ea2b765ef02a79d04c78d91f39e99c5f7b
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
handle. `data/analysis.db-wal` existed and was 0 bytes.

After the failed retry, `scheduler_config.json` was restored byte-for-byte from
the pre-guard copy:

```text
skip_next_run=false
diff scheduler_config.before_guard.json scheduler_config.json => no diff
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
watermark_finalization_performed=False
deployment_id=1
taxonomy_version=DC_TAXONOMY_FULL_V2
requested_start=2025-08-01
requested_end=2026-07-31
chunk_count=7
backup_mode=EXISTING_BACKUP
backup_validation_status=OK
```

Failed chunk:

```text
chunk_index=1
chunk_range=2025-08-01..2025-09-29
status=BACKFILL_FAILED
failed_date=2025-08-01
completed_chunks=[]
completed_dates=[]
failed_date_completed_steps=["load_ec_ticker_signal_daily_from_dc"]
watermark_finalization_status=NOT_RUN
whole_range_validation_status=NOT_RUN
```

Error:

```text
UNIQUE constraint failed: ec_group_signal_daily.ecosystem_id,
ec_group_signal_daily.taxonomy_version_id,
ec_group_signal_daily.signal_date,
ec_group_signal_daily.entity_id,
ec_group_signal_daily.signal_version
```

The deployment row `last_error` was updated to the same
`ec_group_signal_daily` unique-constraint failure.

## Ticker Loader Scope Verification

The previous retry failed before ticker loading completed. This retry shows that
the ticker loader now selected the proposed V2 taxonomy:

```text
requested_taxonomy_version=DC_TAXONOMY_FULL_V2
source_taxonomy_version=DC_TAXONOMY_FULL_V2
source_taxonomy_match=true
source_row_count=257
source_distinct_ticker_count=257
duplicate_source_ticker_count=0
unexpected_taxonomy_version_count=0
mapped_row_count=257
unresolved_membership_count=0
duplicate_target_key_count=0
null_target_key_count=0
loaded_row_count=257
loader_status=OK_WITH_WARNINGS
loader_error_code=NONE
```

The failed first date left a partial V2 EC write:

```text
ec_ticker_signal_daily taxonomy_version_id=2 date=2025-08-01 rows=257
ec_group_signal_daily taxonomy_version_id=2 rows=0
ec_group_synthetic_ohlc_daily taxonomy_version_id=2 rows=0
ec_group_index_daily taxonomy_version_id=2 rows=0
```

No duplicate primary-key groups were present in any EC fact table after the
failure:

```text
ec_ticker_signal_daily duplicate_key_groups=0
ec_group_signal_daily duplicate_key_groups=0
ec_group_synthetic_ohlc_daily duplicate_key_groups=0
ec_group_index_daily duplicate_key_groups=0
```

Read-only source checks for `dc_group_swing_signal_daily` on `2025-08-01`
showed:

```text
source_rows=54
distinct_groups=54
duplicate group_type/group_name/signal_version keys=0
mapped duplicate EC entity_id/signal_version keys=0
```

The precise code-level cause of the group loader uniqueness failure therefore
remains unresolved after this retry. The next investigation should focus on
`ec_group_signal_daily` loader replace/insert scope and rebuild partial-state
handling for the first failed date.

## Post-Failure Production State

Deployment row after the retry:

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
last_error=UNIQUE constraint failed: ec_group_signal_daily.ecosystem_id, ec_group_signal_daily.taxonomy_version_id, ec_group_signal_daily.signal_date, ec_group_signal_daily.entity_id, ec_group_signal_daily.signal_version
```

Taxonomy state after the retry:

```text
DC_TAXONOMY_FULL_V1 status=ACTIVE is_active=1
DC_TAXONOMY_FULL_V2 status=INACTIVE is_active=0
```

EC canonical watermarks remained on the existing non-V2 rows. No V2
taxonomy-scoped canonical EC watermark was finalized:

```text
TICKER_SWING_BASE latest_signal_date=2026-07-31 taxonomy_version_id=NULL
GROUP_SWING_BASE latest_signal_date=2026-07-31 taxonomy_version_id=NULL
SYNTHETIC_OHLC_BASE latest_signal_date=2026-07-31 taxonomy_version_id=NULL
GROUP_INDEX latest_signal_date=2026-07-31 taxonomy_version_id=NULL
```

## Actions Not Performed

This retry did not:

```text
run the Datacenter pipeline
run any Datacenter stage
activate DC_TAXONOMY_FULL_V2
switch scheduler taxonomy to V2
run the ordinary scheduler
run EC latest refresh outside the orchestrator
run a separate EC backfill outside the orchestrator
fetch external data
run migrations
create another full production DB backup
restore a backup
run apply_datacenter_taxonomy_rebuild_evidence
run plan_datacenter_taxonomy_activation
commit or stage watchlist changes
```

## Operational Conclusion

The final production classification is:

```text
DATACENTER_EC_V2_FULL_REBUILD_FAILED_V1_REMAINS_ACTIVE
```

The `4672e7b` ticker-scope fix was effective for the ticker loader, but the
full EC rebuild is still blocked by a subsequent `ec_group_signal_daily`
uniqueness failure. V1 remains active and V2 is not ready for activation.
