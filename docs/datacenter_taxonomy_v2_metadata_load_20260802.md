# Datacenter V2 Taxonomy Metadata Load - 2026-08-02

## Final Classification

`DATACENTER_V2_METADATA_LOADED_NOT_ACTIVE`

This was a controlled production metadata deployment only. V2 was loaded as
metadata and deployment evidence, but it was not activated. No Datacenter facts,
EC facts, DC watermarks, EC watermark row values, scheduler taxonomy settings, or
canonical pipeline outputs were rebuilt or switched to V2.

## Repository And Source State

- Repository: `/home/kalle/projects/rawcandle`
- Branch: `chore/ignore-backups`
- Backend commit: `36c8f738fd0804db92cf2b3be53f71264b8cb682`
- Short commit: `36c8f73 Implement Datacenter taxonomy replacement foundation`
- `origin/chore/ignore-backups` before deployment: `36c8f738fd0804db92cf2b3be53f71264b8cb682`
- V2 CSV: `data/datacenter_taxonomy_full_v2.csv`
- V2 CSV SHA-256: `178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1`
- V2 CSV repository policy: ignored by `.gitignore` rule `*.csv`, not tracked
- Existing working tree before deployment: `M watchlists/datacenter_watchlist.txt`
- `data/datacenter_taxonomy_full_v2.csv:Zone.Identifier`: not present at deployment time

## Evidence Directory

Evidence was captured under:

`temp/datacenter_taxonomy_v2_metadata_load_20260802T200059Z/`

Key evidence files:

- `plan_stdout.json`
- `plan_stderr.txt`
- `plan_exit_code.txt`
- `scheduler_config.before_guard.json`
- `scheduler_config_guard_validation.json`
- `active_writer_check.json`
- `pre_deployment_snapshot.json`
- `pre_deployment_snapshot.sha256`
- `production_db_backup.json`
- `post_migration_026_verification.json`
- `metadata_load_command.txt`
- `metadata_load_stdout.json`
- `metadata_load_stderr.txt`
- `metadata_load_exit_code.txt`
- `post_metadata_load_verification.json`
- `post_metadata_load_verification.sha256`
- `activation_plan_stdout.json`
- `activation_plan_stderr.txt`
- `activation_plan_exit_code.txt`
- `scheduler_config_restore_validation.json`

## Read-Only Plan

The read-only planner was re-run against the exact production files before any
production write.

Result:

```text
exit_code=0
taxonomy_plan_status=READY_TO_LOAD
safe_to_load=True
blocking_errors=[]
warnings=[]
proposed_source_sha256=178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1
requires_new_taxonomy_version=True
requires_full_historical_rebuild=True
rebuild_start_date=2025-08-01
```

V2 plan counts:

```text
rows=350
unique_tickers=257
layers=16
subindustries=37
primary_memberships=257
secondary_memberships=93
```

## Scheduler Guard

`scheduler_config.json` already had:

```text
skip_next_run=true
```

Therefore the guard was already active. A backup was captured before production
writes:

```text
backup_path=temp/datacenter_taxonomy_v2_metadata_load_20260802T200059Z/scheduler_config.before_guard.json
backup_sha256=6c7602cdbf2a0eb36ccbad1d4f9fc99a392c049fcd8e1ca63407a78996b5510b
unexpected_changed_keys=NONE
```

The scheduler taxonomy configuration remained on V1:

```text
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V1
datacenter_taxonomy_csv=data/datacenter_ecosystem_taxonomy_full_v1.csv
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V1
ec_source_layer_taxonomy_csv=/home/kalle/projects/rawcandle/data/datacenter_ecosystem_taxonomy_full_v1.csv
```

After deployment, normal scheduler execution was restored by changing only:

```text
skip_next_run=true -> false
unexpected_changed_keys=NONE
```

## Active Writer Check

No active production DB writer was found before writes:

```text
active_writer_count=0
fuser_exit_code=1
fuser_stdout_bytes=0
interpretation=NO_ACTIVE_WRITER_FOUND
```

Checked process classes included stock update scheduler, Datacenter pipeline,
EC source-layer work, taxonomy loader/activation, and migration runner.

## Pre-Deployment State

Precondition was satisfied:

```text
V1 active=true
V2 not loaded=true
```

Active taxonomy:

```text
taxonomy_version_id=1
taxonomy_version_code=DC_TAXONOMY_FULL_V1
status=ACTIVE
is_active=1
source_hash=1ad6ef41b91ef429174090bfcd338acf1e79680d939b4b788c834a79c73e9e5d
```

V1 counts:

```text
taxonomy_version_rows=1
entity_count=290
membership_count=382
ticker_membership_count=329
```

`ec_taxonomy_change_deployment` did not exist before migration 026.

Pre-deployment checksums:

```text
canonical_fact_heads_counts=ee113f2cf154a76fb943896dc76645a0d6c4190bca2d9c28bdefb6736898689b
dc_pipeline_watermark=9a349265bc3a051dba8256670a84a96084eb715109479925f53248431f424719
ec_pipeline_watermark=d3dfeaf196d378e8bb6414052bc39a1ec49b458fc23570ad584d67ca024523d2
```

## Production DB Backup

SQLite-consistent production backup:

```text
backup_path=temp/datacenter_taxonomy_v2_metadata_load_20260802T200059Z/analysis_pre_datacenter_taxonomy_v2_metadata_load.sqlite
size=7539904512
mtime=2026-08-02T20:03:14.260527+00:00
sha256=004c931a38948cdae9987c0f7e1bbc333c35085b61d4515c611fc86213aa7fb8
started_at_utc=2026-08-02T20:03:06.160099+00:00
completed_at_utc=2026-08-02T20:03:19.050703+00:00
```

## Migration 026

Applied exactly:

```text
sqlite3 data/analysis.db ".read rawcandle/sqlite/migrations/026_create_taxonomy_replacement_audit.sql"
```

Result:

```text
exit_code=0
```

Post-migration verification:

```text
ec_taxonomy_change_deployment exists=true
ec_taxonomy_change_deployment row_count=0
v1_remains_active=true
v2_not_loaded_yet=true
v1_memberships_unchanged=true
canonical_facts_unchanged=true
dc_watermark_unchanged=true
ec_watermark_unchanged=true
```

Migration 026 defines the deployment table and its unique constraint. It does
not define separate indexes.

## Metadata Load

Command:

```text
python3 -m rawcandle.cli.apply_datacenter_taxonomy_version --analysis-db /home/kalle/projects/rawcandle/data/analysis.db --current-taxonomy-version DC_TAXONOMY_FULL_V1 --current-taxonomy-csv /home/kalle/projects/rawcandle/data/datacenter_ecosystem_taxonomy_full_v1.csv --proposed-taxonomy-version DC_TAXONOMY_FULL_V2 --proposed-taxonomy-csv /home/kalle/projects/rawcandle/data/datacenter_taxonomy_full_v2.csv --confirm-proposed-taxonomy-version DC_TAXONOMY_FULL_V2 --ecosystem DATACENTER --invocation-source CONTROLLED_PRODUCTION_METADATA_LOAD_20260802 --rebuild-start-date 2025-08-01 --format json
```

Result:

```text
exit_code=0
stderr_bytes=0
taxonomy_apply_status=LOADED_NOT_ACTIVE
taxonomy_version_id=2
taxonomy_version_code=DC_TAXONOMY_FULL_V2
source_sha256=178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1
row_count=350
ticker_count=257
layer_count=16
subindustry_count=37
membership_count=350
primary_membership_count=257
secondary_membership_count=93
rebuild_required=true
rebuild_start_date=2025-08-01
activation_status=NOT_ACTIVE
```

Loader internal hierarchy summary:

```text
load_summary.status=OK
load_summary.membership_count=403
load_summary.taxonomy_rows=350
load_summary.multi_membership_ticker_count=76
load_summary.warnings=[]
```

The loader summary membership count includes hierarchy memberships in addition
to the 350 ticker memberships from the CSV.

## Deployment Row

Deployment evidence row:

```text
taxonomy_change_id=1
ecosystem_code=DATACENTER
previous_taxonomy_version=DC_TAXONOMY_FULL_V1
proposed_taxonomy_version=DC_TAXONOMY_FULL_V2
status=LOADED_NOT_ACTIVE
rebuild_required=1
rebuild_start_date=2025-08-01
dc_rebuild_status=NOT_STARTED
ec_rebuild_status=NOT_STARTED
coverage_status=NOT_STARTED
parity_status=NOT_STARTED
activation_status=NOT_ACTIVE
loaded_at_utc=2026-08-02 20:04:10
created_at_utc=2026-08-02 20:04:10
invocation_source=CONTROLLED_PRODUCTION_METADATA_LOAD_20260802
added_ticker_count=36
removed_ticker_count=15
membership_change_count=63
group_change_count=42
```

## CSV-To-DB Parity

Exact V2 parity passed:

```text
CSV-only entities=NONE
DB-only entities=NONE
CSV-only memberships=NONE
DB-only memberships=NONE
primary membership mismatches=NONE
role weight mismatches=NONE
report group status mismatches=NONE
hierarchy mismatches=NONE
duplicate V2 memberships=0
ticker_without_primary_count=0
```

Count parity:

```text
csv_ticker_membership_count=350
db_ticker_membership_count=350
csv_layer_count=16
db_layer_count=16
csv_subindustry_count=37
db_subindustry_count=37
csv_ticker_count=257
db_ticker_count=257
```

## Activation Isolation

V1 remains the only active taxonomy:

```text
active_taxonomy_count=1
V1 status=ACTIVE
V1 is_active=1
```

V2 remains inactive:

```text
V2 taxonomy_version_id=2
V2 status=INACTIVE
V2 is_active=0
V2 activation_status=NOT_ACTIVE
```

Scheduler taxonomy remains V1:

```text
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V1
datacenter_taxonomy_csv=data/datacenter_ecosystem_taxonomy_full_v1.csv
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V1
ec_source_layer_taxonomy_csv=/home/kalle/projects/rawcandle/data/datacenter_ecosystem_taxonomy_full_v1.csv
```

Read-only activation plan result:

```text
exit_code=1
activation_plan_status=BLOCKED
safe_to_activate=false
required_signal_date=2026-07-31
```

Blocking reasons:

```text
DC fact head incomplete for dc_group_index_daily
DC fact head incomplete for dc_group_swing_signal_daily
DC fact head incomplete for dc_group_synthetic_ohlc_daily
DC fact head incomplete for dc_ticker_swing_signal_daily
EC fact head incomplete for ec_group_index_daily
EC fact head incomplete for ec_group_signal_daily
EC fact head incomplete for ec_group_synthetic_ohlc_daily
EC fact head incomplete for ec_ticker_signal_daily
EC watermark lineage does not belong to proposed taxonomy
coverage is not accepted
full DC rebuild is incomplete
full EC rebuild is incomplete
parity is not accepted
```

No activation apply command was run.

## Canonical Fact Non-Impact

Canonical fact heads and row counts were unchanged:

```text
dc_ticker_swing_signal_daily: head=2026-07-31 row_count=93286
dc_group_swing_signal_daily: head=2026-07-31 row_count=21414
dc_group_synthetic_ohlc_daily: head=2026-07-31 row_count=22144
dc_group_index_daily: head=2026-07-31 row_count=90564
ec_ticker_signal_daily: head=2026-07-31 row_count=12272
ec_group_signal_daily: head=2026-07-31 row_count=2808
ec_group_synthetic_ohlc_daily: head=2026-07-31 row_count=2756
ec_group_index_daily: head=2026-07-31 row_count=2808
```

Verification:

```text
canonical_facts_unchanged=true
canonical_fact_heads_counts=ee113f2cf154a76fb943896dc76645a0d6c4190bca2d9c28bdefb6736898689b
```

## Watermark Non-Impact

DC watermark rows were unchanged:

```text
dc_pipeline_watermark_unchanged=true
dc_pipeline_watermark_checksum=9a349265bc3a051dba8256670a84a96084eb715109479925f53248431f424719
```

EC watermark existing row values were unchanged:

```text
ec_pipeline_watermark_common_columns_unchanged=true
ec_pipeline_watermark_common_columns_checksum=d3dfeaf196d378e8bb6414052bc39a1ec49b458fc23570ad584d67ca024523d2
```

The metadata loader added the nullable lineage column required by the taxonomy
replacement implementation:

```text
ec_pipeline_watermark_columns_before=ecosystem_id,pipeline_name,source_table,latest_signal_date,latest_run_id,status,created_at_utc,updated_at_utc
ec_pipeline_watermark_columns_after=ecosystem_id,pipeline_name,source_table,latest_signal_date,latest_run_id,status,created_at_utc,updated_at_utc,taxonomy_version_id
```

No DC or EC watermark row was reset or advanced.

## CBRS History Limitation

CBRS price history in `data/osakedata.db`:

```text
first_date=2026-05-14
latest_date=2026-07-31
row_count=54
```

This does not block metadata loading. The later historical rebuild must treat
pre-listing or no-source dates before `2026-05-14` as expected unavailable data
for CBRS. The rebuild must not fabricate rows and must not fail the entire
taxonomy rebuild solely because CBRS has no source data before its first
available trading date.

## Explicit Non-Actions

The deployment did not:

- modify V1 or V2 taxonomy CSV contents
- modify `watchlists/datacenter_watchlist.txt`
- stage or commit the watchlist
- run the scheduler
- run the Datacenter pipeline
- run Stage 1-16
- run Stage 2 or downstream stages
- run EC refresh or EC backfill
- rebuild DC or EC facts
- activate V2
- mark V1 inactive
- reset or advance DC watermarks
- reset or advance EC watermark row values
- change scheduler taxonomy path or version
- fetch market data
- apply unrelated migrations
- run tests
- stage or commit backup, runtime, DB, WAL, SHM, temp, or log files

## Final State

```text
repair_classification=DATACENTER_V2_METADATA_LOADED_NOT_ACTIVE
DC_TAXONOMY_FULL_V1 active=true
DC_TAXONOMY_FULL_V2 loaded=true
DC_TAXONOMY_FULL_V2 active=false
DC_TAXONOMY_FULL_V2 activation_status=NOT_ACTIVE
rebuild_required=true
rebuild_start_date=2025-08-01
scheduler_taxonomy_version=DC_TAXONOMY_FULL_V1
scheduler_skip_next_run=false
canonical_facts_unchanged=true
dc_pipeline_watermark_unchanged=true
ec_pipeline_watermark_row_values_unchanged=true
```
