# Datacenter Watchlist Production Reconciliation 2026-08-02

## Final Classification

```text
DATACENTER_WATCHLIST_PRODUCTION_RECONCILIATION_VERIFIED
```

Deployment commit:

```text
e0385a0 Reconcile Datacenter watchlist at run start
e0385a07a74d4b85a2c08f4b92bebf307ee34f62
```

Branch and repository state before production writes:

```text
branch=chore/ignore-backups
HEAD=e0385a07a74d4b85a2c08f4b92bebf307ee34f62
origin/chore/ignore-backups=e0385a07a74d4b85a2c08f4b92bebf307ee34f62
initial_git_status=" M watchlists/datacenter_watchlist.txt"
```

The 37-member TXT watchlist was intentionally left modified and unstaged.

## Scope

Performed only:

```text
1. Apply migration 025_create_ec_watchlist_reconciliation_audit.sql
2. Run one controlled Datacenter watchlist reconciliation
3. Verify exact membership, audit evidence, entity behavior, and canonical non-impact
4. Document production evidence
```

Explicitly not run:

```text
stock update scheduler
Datacenter pipeline
Stage 2
EC latest refresh
EC historical backfill
canonical fact loaders
watermark update jobs
unrelated migrations
tests
```

## Production Execution Guard

Temporary scheduler guard:

```text
config=scheduler_config.json
temporary_change=skip_next_run:true
backup=temp/datacenter_watchlist_reconciliation_20260802T065117Z/scheduler_config_before_skip_20260802T065117Z.json
backup_sha256=6abeddc7cac2d91107eda65e9dbc05b7085c55a1e1bd79edca7ebd9f68a3b983
unexpected_changed_keys=NONE
validated_skip_next_run=true
```

After verification, the config was restored from the backup:

```text
normal_production_execution_enabled=true
current_skip_next_run=false
changed_keys_vs_backup=[]
unexpected_changed_keys=NONE
```

Active-writer checks:

```text
host ps: no stock update scheduler, Datacenter pipeline, EC refresh/backfill, migration runner, or watchlist reconciliation process
lsof analysis.db: no open handle reported
analysis.db-wal: absent
analysis.db-shm: absent
```

VS Code/editor processes were present, but no active production DB write handle was found.

## Selected Commands

Implementation inspection found:

```text
plan command:
python3 -m rawcandle.cli.plan_datacenter_watchlist_reconciliation ...

apply command:
python3 -m rawcandle.cli.apply_datacenter_watchlist_reconciliation ...

apply backup behavior:
transaction-only rollback plus audit evidence; no full DB backup is created by the apply CLI

migration runner:
rawcandle.ec_sidecar_migration.apply_ec_sidecar_migration applies the whole ec sidecar migration list
```

Because the runner applies all migration SQL paths and does not maintain a migration registry, production used the exact single migration SQL file:

```text
sqlite3 /home/kalle/projects/rawcandle/data/analysis.db \
  ".read rawcandle/sqlite/migrations/025_create_ec_watchlist_reconciliation_audit.sql"
```

This applied only migration 025. There is no separate migration tracking table in this repository path; verification is based on `sqlite_master`, `PRAGMA table_info`, `PRAGMA index_list`, and row-count evidence.

## Pre-Deployment Evidence

Production database:

```text
db=/home/kalle/projects/rawcandle/data/analysis.db
size=7537520640
mtime_utc=2026-08-02T03:31:21.376433+00:00
sha256=9edaeda54f4013f7475dce9b085ec072c2547d5660ff5a2318537f79b4d8c7c0
analysis.db-wal=absent
analysis.db-shm=absent
```

Watchlist source:

```text
source=/home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt
source_sha256=5dfa86d390202fb6bd561fad43967a382de9012ccfbb01f5a725042eefd087e8
source_member_count=37
```

Pre-reconciliation membership:

```text
stored_active_member_count=16
source_member_count=37
added_count=28
removed_count=7
unchanged_count=9
audit_table_exists=false
audit_row_count=0
```

Added tickers:

```text
AAPL, ALAB, AMBA, AMD, AMZN, ANET, AVGO, CNC, DT, FTNT, GFS, LITE, MU, NNE,
ORCL, PANW, PLTR, POET, SEZL, SIMO, SKHY, SMCI, SMH, SNDK, SPCX, STX, WST, ZBRA
```

Removed tickers:

```text
AEHR, AEIS, AXTI, DIOD, PRIM, TXN, VSH
```

Unchanged tickers:

```text
CLS, CRDO, CRGY, ECG, LRCX, MRVL, NVDA, NVT, VRT
```

Pre canonical fact heads and row counts:

```text
dc_ticker_swing_signal_daily:        max_date=2026-07-31 row_count=93286
dc_group_swing_signal_daily:         max_date=2026-07-31 row_count=21414
dc_group_synthetic_ohlc_daily:       max_date=2026-07-31 row_count=22144
dc_group_index_daily:                max_date=2026-07-31 row_count=90564
ec_ticker_signal_daily:              max_date=2026-07-31 row_count=12272
ec_group_signal_daily:               max_date=2026-07-31 row_count=2808
ec_group_synthetic_ohlc_daily:       max_date=2026-07-31 row_count=2756
ec_group_index_daily:                max_date=2026-07-31 row_count=2808
```

Canonical source-table watermark rows were unchanged at deployment start. The current table contains five rows over four canonical source tables because `dc_group_synthetic_ohlc_daily` has both `SYNTHETIC_OHLC_BASE` and `SYNTHETIC_OHLC_RELATIVE`.

Evidence files:

```text
temp/datacenter_watchlist_reconciliation_20260802T065117Z/pre/
```

## Production DB Backup

Backup command:

```text
sqlite3 /home/kalle/projects/rawcandle/data/analysis.db \
  ".backup 'temp/datacenter_watchlist_reconciliation_20260802T065117Z/analysis_before_watchlist_reconciliation_20260802T065117Z.db'"
```

Backup evidence:

```text
path=temp/datacenter_watchlist_reconciliation_20260802T065117Z/analysis_before_watchlist_reconciliation_20260802T065117Z.db
size=7537520640
mtime_utc=2026-08-02T06:56:26.970931+00:00
sha256=1fa9245c17859b19c9fc940e2d79c9540afc7bcafdaf6b3a7af799bde860ac0e
```

## Migration 025

Migration command:

```text
sqlite3 /home/kalle/projects/rawcandle/data/analysis.db \
  ".read rawcandle/sqlite/migrations/025_create_ec_watchlist_reconciliation_audit.sql"
```

Result:

```text
exit_code=0
audit_table_exists=true
audit_index_exists=true
audit_row_count=0
membership_count_after_migration=16
canonical_fact_heads_and_counts_unchanged=true
watermarks_unchanged=true
```

Created table:

```text
ec_watchlist_reconciliation_audit
idx_ec_watchlist_reconciliation_audit_lookup
```

Evidence files:

```text
temp/datacenter_watchlist_reconciliation_20260802T065117Z/migration_post/
```

## Read-Only Plan Before Apply

Plan command:

```text
python3 -m rawcandle.cli.plan_datacenter_watchlist_reconciliation \
  --db /home/kalle/projects/rawcandle/data/analysis.db \
  --watchlist /home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt \
  --ecosystem DATACENTER \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --watchlist-code DATACENTER_WATCHLIST \
  --format json
```

Plan result:

```text
exit_code=0
watchlist_reconciliation_status=PLAN_READY
watchlist_plan_apply_safe=True
watchlist_source_member_count=37
watchlist_previous_member_count=16
watchlist_current_member_count=16
watchlist_added_count=28
watchlist_removed_count=7
watchlist_reconciliation_error=None
```

The prompt's expected `CHANGES_REQUIRED` status maps to the implemented status name `PLAN_READY`.

Captured output:

```text
temp/datacenter_watchlist_reconciliation_20260802T065117Z/plan_before_apply.stdout.json
temp/datacenter_watchlist_reconciliation_20260802T065117Z/plan_before_apply.stderr.txt
temp/datacenter_watchlist_reconciliation_20260802T065117Z/plan_before_apply.exitcode
```

## Controlled Apply

Apply command:

```text
python3 -m rawcandle.cli.apply_datacenter_watchlist_reconciliation \
  --db /home/kalle/projects/rawcandle/data/analysis.db \
  --watchlist /home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt \
  --ecosystem DATACENTER \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --watchlist-code DATACENTER_WATCHLIST \
  --confirm-db /home/kalle/projects/rawcandle/data/analysis.db \
  --confirm-ecosystem DATACENTER \
  --confirm-watchlist /home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt \
  --invocation-source CONTROLLED_PRODUCTION_DEPLOYMENT_20260802 \
  --format json
```

Apply result:

```text
exit_code=0
stderr=""
watchlist_reconciliation_attempted=True
watchlist_reconciliation_status=APPLIED
watchlist_source_reference=/home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt
watchlist_source_sha256=5dfa86d390202fb6bd561fad43967a382de9012ccfbb01f5a725042eefd087e8
watchlist_source_member_count=37
watchlist_previous_member_count=16
watchlist_current_member_count=37
watchlist_added_count=28
watchlist_removed_count=7
watchlist_reconciliation_error=None
```

Watchlist-only entities created:

```text
watchlist_created_watchlist_only_ticker_count=10
watchlist_created_watchlist_only_tickers=AAPL, CNC, NNE, PLTR, POET, SEZL, SKHY, SMH, SPCX, WST
```

Captured output:

```text
temp/datacenter_watchlist_reconciliation_20260802T065117Z/apply.stdout.json
temp/datacenter_watchlist_reconciliation_20260802T065117Z/apply.stderr.txt
temp/datacenter_watchlist_reconciliation_20260802T065117Z/apply.exitcode
```

## Post-Apply Membership Verification

Post state:

```text
source_membership_count=37
database_membership_count=37
source_only_tickers=[]
database_only_tickers=[]
duplicate_active_memberships=[]
removed_tickers_still_active=[]
unrelated_watchlists_unchanged=true
```

Exact active membership after apply:

```text
AAPL, ALAB, AMBA, AMD, AMZN, ANET, AVGO, CLS, CNC, CRDO, CRGY, DT, ECG, FTNT,
GFS, LITE, LRCX, MRVL, MU, NNE, NVDA, NVT, ORCL, PANW, PLTR, POET, SEZL,
SIMO, SKHY, SMCI, SMH, SNDK, SPCX, STX, VRT, WST, ZBRA
```

## Watchlist-Only Entity Verification

The reconciliation created active EC ticker entities for:

```text
AAPL, CNC, NNE, PLTR, POET, SEZL, SKHY, SMH, SPCX, WST
```

For these entities:

```text
entity_type=TICKER
entity_role_code=TICKER
status=ACTIVE
taxonomy_membership_count=0
alias_count=0
active_entity_duplicates=[]
```

No Datacenter taxonomy membership was implicitly created for those watchlist-only tickers.

## Audit Verification

Audit table state:

```text
audit_row_count=1
reconciliation_id=1
status=APPLIED
source_type=TXT
source_reference=/home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt
source_sha256=5dfa86d390202fb6bd561fad43967a382de9012ccfbb01f5a725042eefd087e8
source_member_count=37
previous_member_count=16
new_member_count=37
added_count=28
removed_count=7
invocation_source=CONTROLLED_PRODUCTION_DEPLOYMENT_20260802
taxonomy_version_code=DC_TAXONOMY_FULL_V1
applied_at_utc=2026-08-02 06:58:06
```

No no-op audit row was created before apply. The single audit row corresponds to the single production apply.

## Canonical Non-Impact

Post-apply comparison against the pre-write backup:

```text
canonical_fact_heads_and_counts_unchanged=true
watermarks_unchanged=true
```

Canonical fact heads and row counts after apply:

```text
dc_ticker_swing_signal_daily:        max_date=2026-07-31 row_count=93286
dc_group_swing_signal_daily:         max_date=2026-07-31 row_count=21414
dc_group_synthetic_ohlc_daily:       max_date=2026-07-31 row_count=22144
dc_group_index_daily:                max_date=2026-07-31 row_count=90564
ec_ticker_signal_daily:              max_date=2026-07-31 row_count=12272
ec_group_signal_daily:               max_date=2026-07-31 row_count=2808
ec_group_synthetic_ohlc_daily:       max_date=2026-07-31 row_count=2756
ec_group_index_daily:                max_date=2026-07-31 row_count=2808
```

No canonical DC or EC fact rows were inserted, deleted, replaced, or re-counted by the watchlist reconciliation. No canonical fact watermark changed. No report regeneration occurred.

## Idempotent Second Plan

Only a read-only plan was run after apply.

Result:

```text
exit_code=0
watchlist_reconciliation_status=NO_CHANGE
watchlist_source_member_count=37
watchlist_previous_member_count=37
watchlist_current_member_count=37
watchlist_added_count=0
watchlist_removed_count=0
watchlist_reconciliation_error=None
audit_row_count_after_second_plan=1
```

Captured output:

```text
temp/datacenter_watchlist_reconciliation_20260802T065117Z/plan_after_apply.stdout.json
temp/datacenter_watchlist_reconciliation_20260802T065117Z/plan_after_apply.stderr.txt
temp/datacenter_watchlist_reconciliation_20260802T065117Z/plan_after_apply.exitcode
```

## Evidence Directory

Runtime evidence was written under:

```text
temp/datacenter_watchlist_reconciliation_20260802T065117Z/
```

This includes pre-snapshots, migration-post snapshots, apply output, second-plan output, post snapshots, config backup/restore verification, production DB backup info, and snapshot checksums.

## Final Non-Actions

Confirmed:

```text
watchlists/datacenter_watchlist.txt was not modified by this deployment
watchlists/datacenter_watchlist.txt was not staged
stock update scheduler was not run
Datacenter pipeline was not run
Stage 2 was not run
EC latest refresh was not run
EC historical backfill was not run
canonical fact tables were not updated
canonical watermarks were not updated
unrelated migrations were not applied
scheduler configuration was restored with unexpected_changed_keys=NONE
no unrelated cleanup was performed
no network operation was used before documentation push
```
