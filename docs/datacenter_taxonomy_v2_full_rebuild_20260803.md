# Datacenter Taxonomy V2 Full Rebuild - 2026-08-03

## Summary

Final classification:

```text
DATACENTER_V2_FULL_REBUILD_FAILED_V1_REMAINS_ACTIVE
```

The first controlled production full rebuild for `DC_TAXONOMY_FULL_V2` was
started with the guarded backend from:

```text
48b35be Implement Datacenter V2 rebuild backend safeguards
da52920 Add EC taxonomy full rebuild orchestrator
88bb13f Allow EC taxonomy rebuild to reuse production backup
```

The Datacenter pipeline materialized V2 data through Stage 15, then failed in
Stage 16 while copying reports to the Windows report directory:

```text
ERROR [Errno 30] Read-only file system: '/mnt/d/swing_reports/datacenter_daily_2026-07-31_1327_full.md'
```

Per the failure policy, the run stopped immediately. EC full rebuild, watermark
lineage finalization, deployment evidence finalization, activation planning, and
V2 activation were not run.

## Repository And Sources

Repository preflight:

```text
branch=chore/ignore-backups
HEAD=88bb13fd2e0f97b049cf14198d3cea491f13dff7
origin/chore/ignore-backups=88bb13fd2e0f97b049cf14198d3cea491f13dff7
existing_working_tree_change= M watchlists/datacenter_watchlist.txt
```

Taxonomy source hashes:

```text
V1_SHA256=1ad6ef41b91ef429174090bfcd338acf1e79680d939b4b788c834a79c73e9e5d
V2_SHA256=178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1
```

The watchlist working-tree change was left untouched and unstaged.

## Deployment Row

Initial deployment row:

```text
taxonomy_change_id=1
ecosystem_code=DATACENTER
previous_taxonomy_version=DC_TAXONOMY_FULL_V1
proposed_taxonomy_version=DC_TAXONOMY_FULL_V2
source_sha256=178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1
status=LOADED_NOT_ACTIVE
rebuild_required=1
rebuild_start_date=2025-08-01
dc_rebuild_status=NOT_STARTED
ec_rebuild_status=NOT_STARTED
coverage_status=NOT_STARTED
parity_status=NOT_STARTED
activation_status=NOT_ACTIVE
```

Post-failure deployment row:

```text
taxonomy_change_id=1
status=REBUILD_IN_PROGRESS
dc_rebuild_status=IN_PROGRESS
ec_rebuild_status=NOT_STARTED
coverage_status=NOT_STARTED
parity_status=NOT_STARTED
activation_status=NOT_ACTIVE
last_error=
```

No ad hoc deployment failure update was applied after the pipeline failure.

## Rebuild Range

Signal-date resolution used the existing production valid-price-date logic:

```text
requested_calendar_signal_date=2026-08-03
resolved_signal_date=2026-07-31
signal_date_source=load_valid_price_dates_for_market
signal_date_resolution=latest_valid_signal_date_at_or_before_requested_calendar_date
ticker_valid_date_count=251
group_valid_date_count=251
REBUILD_START_DATE=2025-08-01
REBUILD_END_DATE=2026-07-31
```

## Safety Gates

Evidence root:

```text
temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z
```

Scheduler guard:

```text
pre_guard_backup=temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/backups/scheduler_config.pre_guard.20260803T102454Z.json
changed_keys=skip_next_run
unexpected_changed_keys=NONE
skip_next_run=true during rebuild
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V1
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V1
```

Active-writer check:

```text
analysis.db active handles=false
analysis.db-wal exists=false
analysis.db-shm exists=false
UI process holding analysis.db=false
```

The scheduler guard was restored after the failed DC run:

```text
restore_status=OK
changed_keys=skip_next_run
unexpected_changed_keys=NONE
skip_next_run=false
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V1
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V1
datacenter_stage2_incremental_enabled=true
datacenter_stage2_overlap_trading_days=5
```

## Production Backup

Exactly one full production DB backup was created before rebuild writes:

```text
backup_path=temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/analysis_before_datacenter_v2_full_rebuild.sqlite
backup_size=7540109312
backup_sha256=ef63868f55073dd3a9eedccea5097871446b02af1577f8c4659fe6dd325db3ea
backup_integrity_check=ok
```

Backup inventory after failure:

```text
temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/analysis_before_datacenter_v2_full_rebuild.sqlite 7540109312
```

No second full production DB backup was created.

## Schema Preparation

Pre-rebuild schema verification found missing optional deployment-evidence
columns:

```text
prepared_at_utc
validation_completed_at_utc
rebuild_evidence_json
rebuild_evidence_sha256
validation_evidence_json
validation_evidence_sha256
last_error
```

The directly required schema preparation was applied with
`ensure_taxonomy_replacement_schema(conn)`:

```text
schema_preparation_status=OK
fact_or_watermark_count_changed=false
activation_changed=false
schema_preparation_sha256=78d25b4f16b1bddacd24b248c8bd0d750f06f8ef764a817d85de9c4d60ccace1
```

## Rebuild Preparation

Command:

```bash
python3 -m rawcandle.cli.prepare_datacenter_taxonomy_rebuild \
  --analysis-db /home/kalle/projects/rawcandle/data/analysis.db \
  --ecosystem DATACENTER \
  --proposed-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --proposed-taxonomy-csv /home/kalle/projects/rawcandle/data/datacenter_taxonomy_full_v2.csv \
  --deployment-id 1 \
  --expected-active-taxonomy-version DC_TAXONOMY_FULL_V1 \
  --confirm-proposed-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --format json
```

Result:

```text
exit_code=0
prepare_status=REBUILD_IN_PROGRESS
deployment_id=1
taxonomy_version_code=DC_TAXONOMY_FULL_V2
taxonomy_source_sha256=178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1
rebuild_start_date=2025-08-01
previous_dc_watermark_count=15
proposed_dc_watermark_count=0
rebuild_evidence_sha256=8e76a1628596f6d63b6b724596bc38069830cbb120643a903d5cc418097ea2db
blocking_errors=[]
```

Post-preparation verification:

```text
DC_TAXONOMY_FULL_V1 status=ACTIVE is_active=1
DC_TAXONOMY_FULL_V2 status=INACTIVE is_active=0
scheduler_datacenter_taxonomy_version=DC_TAXONOMY_FULL_V1
scheduler_ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V1
V2_fact_counts_before_dc_run=0
```

## Datacenter Command

Command:

```bash
/usr/bin/time -p env PYTHONPATH=. python3 run_datacenter_swing_pipeline.py \
  --price-db /home/kalle/projects/rawcandle/data/osakedata.db \
  --analysis-db /home/kalle/projects/rawcandle/data/analysis.db \
  --taxonomy-csv /home/kalle/projects/rawcandle/data/datacenter_taxonomy_full_v2.csv \
  --taxonomy-version DC_TAXONOMY_FULL_V2 \
  --market usa \
  --signal-date 2026-07-31 \
  --start-date 2025-08-01 \
  --index-base-date 2020-01-01 \
  --output-dir /home/kalle/projects/rawcandle/temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/dc_reports \
  --expected-ticker-count 257 \
  --expected-group-count 54 \
  --expected-synthetic-ohlc-count 53 \
  --watchlist-file /home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt
```

Result:

```text
exit_code=1
real_seconds=730.85
user_seconds=651.73
sys_seconds=67.64
failed_stage=Stage 16/16: Windows report copy
failure_error=ERROR [Errno 30] Read-only file system: '/mnt/d/swing_reports/datacenter_daily_2026-07-31_1327_full.md'
```

## DC Stage Results

Completed before failure:

```text
Stage 1  Datacenter base index                validation/write status OK
Stage 2  Ticker swing base snapshots          251 signal dates, validation OK
Stage 3  Group swing base metrics             validation OK
Stage 4  Synthetic OHLC base                  validation OK
Stage 5  Relative OHLC20                      validation OK
Stage 6  Group structure / BOS / RESET        validation OK
Stage 7  Group timing states                  validation OK
Stage 8  Group overheat risk                  validation OK
Stage 9  Ticker scanners                      validation OK
Stage 10 Pipeline audit                       validation OK
Stage 11 Automatic technical relevance        status OK
Stage 12 Daily report                         validation OK
Stage 13 Rolling 30 report                    validation OK
Stage 14 Rolling 5 report                     validation OK
Stage 15 Rolling 2 report                     validation OK
```

Failed:

```text
Stage 16 Windows report copy
```

Important write evidence from stdout:

```text
Stage 1 rows_inserted=89262 write_status=OK
Stage 3 inserted_count=13554 validation_status=OK
Stage 4 inserted_count=13303 validation_status=OK
Stage 5 updated_count=13303 validation_status=OK
Stage 6 updated_count=27815 validation_status=OK
Stage 7 updated_count=27192 validation_status=OK
Stage 8 updated_count=27192 validation_status=OK
Stage 9 updated_count=64507 validation_status=OK
Stage 10 validation_status=OK
```

## V2 DC Fact State After Failure

The failed run left V2-scoped DC rows in production:

```text
dc_group_index_daily           rows=89262 min_date=2020-01-02 max_date=2026-07-31
dc_ticker_swing_signal_daily   rows=64507 min_date=2025-08-01 max_date=2026-07-31
dc_group_swing_signal_daily    rows=13554 min_date=2025-08-01 max_date=2026-07-31
dc_group_synthetic_ohlc_daily  rows=13303 min_date=2025-08-01 max_date=2026-07-31
```

V2 DC watermarks after failure:

```text
TICKER_SWING_BASE         start_date=2025-08-01 end_date=2026-07-31 status=OK
GROUP_SWING_BASE          start_date=2025-08-01 end_date=2026-07-31 status=OK
SYNTHETIC_OHLC_BASE       start_date=2025-08-01 end_date=2026-07-31 status=OK
SYNTHETIC_OHLC_RELATIVE   start_date=2025-08-01 end_date=2026-07-31 status=OK
SYNTHETIC_OHLC_STRUCTURE  start_date=2025-08-01 end_date=2026-07-31 status=OK
GROUP_TIMING              start_date=2025-08-01 end_date=2026-07-31 status=OK
GROUP_OVERHEAT            start_date=2025-08-01 end_date=2026-07-31 status=OK
TICKER_SCANNER            start_date=2025-08-01 end_date=2026-07-31 status=OK
GROUP_INDEX               start_date=2020-01-01 end_date=2026-07-31 status=OK
DAILY_REPORT              start_date=2026-07-31 end_date=2026-07-31 status=OK
ROLLING_REPORT_30         start_date=2026-06-18 end_date=2026-07-31 status=OK
ROLLING_REPORT_5          start_date=2026-07-27 end_date=2026-07-31 status=OK
ROLLING_REPORT_2          start_date=2026-07-30 end_date=2026-07-31 status=OK
PIPELINE_AUDIT            start_date=2026-07-31 end_date=2026-07-31 status=OK
```

This is partial-success evidence, not activation readiness. The full rebuild
command returned non-zero before the workflow reached EC rebuild and final
deployment evidence.

## CBRS And WYFI Handling

Ticker special-case audit from V2 Stage 2 output:

```text
CBRS rows=251 min_date=2025-08-01 max_date=2026-07-31 ok_rows=45 non_ok_rows=206
WYFI rows=251 min_date=2025-08-01 max_date=2026-07-31 ok_rows=238 non_ok_rows=13
```

Sample dates:

```text
CBRS 2025-08-01 MISSING_AS_OF_DATE
CBRS 2025-08-07 MISSING_AS_OF_DATE
CBRS 2026-05-14 INSUFFICIENT_HISTORY close=311.070007324219
CBRS 2026-07-31 OK close=198.710006713867
WYFI 2025-08-01 MISSING_AS_OF_DATE
WYFI 2025-08-07 INSUFFICIENT_HISTORY close=16.2199993133545
WYFI 2026-05-14 OK close=29.9899997711182
WYFI 2026-07-31 OK close=23.7000007629395
```

Interpretation:

```text
pre_listing_rows_fabricated=false
latest_date_data_blocking_issue=false
CBRS_short_history_nonfatal=true
```

## EC Rebuild

EC full-rebuild planning and orchestration were not run because the DC rebuild
failed first.

```text
ec_plan_run=false
ec_orchestrator_run=false
ec_orchestrator_exit_code=NOT_RUN
existing_backup_reuse_result=NOT_RUN
per_chunk_results=NOT_RUN
whole_range_validation=NOT_RUN
ec_watermark_lineage_finalization=NOT_RUN
deployment_evidence_apply=NOT_RUN
activation_plan=NOT_RUN
```

## Active Taxonomy And Scheduler Final State

Taxonomy state after failure:

```text
DC_TAXONOMY_FULL_V1 status=ACTIVE is_active=1
DC_TAXONOMY_FULL_V2 status=INACTIVE is_active=0
```

Scheduler final state:

```text
skip_next_run=false
datacenter_taxonomy_csv=data/datacenter_ecosystem_taxonomy_full_v1.csv
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V1
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V1
datacenter_stage2_incremental_enabled=true
datacenter_stage2_overlap_trading_days=5
```

## Evidence Files

```text
pre_rebuild_snapshot=temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/pre_evidence/pre_rebuild_snapshot.json
pre_rebuild_snapshot_sha256=416764ad125918543455dc4e13195c520550eabd2e96d665ff726a8f0afd9ce7
schema_verification=temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/pre_evidence/schema_verification.json
schema_verification_sha256=4f54c0a0ed1bfe2717509764f1c70136d9fe4edd1be0874aab8ded7a815215ad
schema_preparation=temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/pre_evidence/schema_preparation.json
schema_preparation_sha256=78d25b4f16b1bddacd24b248c8bd0d750f06f8ef764a817d85de9c4d60ccace1
prepare_log=temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/logs/prepare_datacenter_taxonomy_rebuild.json
prepare_log_sha256=36b822f63287bc0182acf0206276f32946355d5ccb1ba44f77619be451f8f539
dc_stdout=temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/logs/datacenter_v2_full_rebuild.stdout
dc_stderr=temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/logs/datacenter_v2_full_rebuild.stderr
scheduler_guard_restore=temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/post_evidence/scheduler_guard_restore.json
scheduler_guard_restore_sha256=0e2f04a338a63351fc3302f290c8fd990dbed7ca184883d73fe26ef1873d1dfe
```

## Recommended Diagnostic Action

Fix or disable the Windows report copy target for controlled rebuild runs. The
Datacenter CLI was invoked with report output under `temp/`, but Stage 16 still
attempted to copy the daily report to `/mnt/d/swing_reports`, which was read-only
in this production environment.

After that fix, the next controlled attempt should decide explicitly whether to:

```text
reuse the existing partial V2 DC facts by validation and continuation
or clean/rebuild the V2-scoped partial facts from the preserved backup state
```

No automatic DB restore was performed.

## Explicit Non-Actions

```text
V2 activation=false
V1 marked inactive=false
scheduler taxonomy switch=false
ordinary scheduler run=false
external data fetch=false
EC full rebuild=false
EC latest refresh=false
EC historical backfill=false
EC watermark finalization=false
activation apply=false
activation plan=false
unrelated migration=false
unrelated cleanup=false
second full production DB backup=false
watchlist staged=false
tests_run=false
network_used_except_git_push=false
```
