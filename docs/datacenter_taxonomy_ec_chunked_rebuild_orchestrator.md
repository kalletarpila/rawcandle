# Datacenter Taxonomy EC Chunked Rebuild Orchestrator

This document describes the high-level EC taxonomy full-rebuild orchestrator
added after the single-range taxonomy-aware backfill support.

No production scheduler, Datacenter pipeline, Stage 2 run, EC rebuild, taxonomy
rebuild, activation, migration apply, production database write, watermark
update, scheduler config change, or external data fetch occurred as part of
this implementation.

## Purpose

Ordinary EC historical backfill remains bounded to:

```text
MAX_RANGE_DAYS=60
```

A taxonomy full rebuild can cover a longer requested range, but only through an
explicit opt-in orchestrator:

```text
full requested range
-> deterministic bounded chunk plan
-> one SQLite-consistent backup or validated pre-existing rebuild backup
-> sequential guarded chunk execution
-> stop on first failure
-> whole-range validation
-> delayed canonical EC watermark finalization
-> existing deployment evidence service
```

The orchestrator reuses the existing taxonomy-aware single-range services:

```text
rawcandle.cli.plan_ec_source_layer_backfill
rawcandle.cli.run_ec_source_layer_backfill
```

It does not duplicate canonical EC loader logic.

## CLIs

Read-only plan:

```bash
python3 -m rawcandle.cli.plan_ec_taxonomy_full_rebuild \
  --db /home/kalle/projects/rawcandle/data/analysis.db \
  --ecosystem DATACENTER \
  --taxonomy-version DC_TAXONOMY_FULL_V2 \
  --taxonomy-csv /home/kalle/projects/rawcandle/data/datacenter_taxonomy_full_v2.csv \
  --watchlist /home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt \
  --deployment-id <taxonomy_change_id> \
  --date-from 2025-08-01 \
  --date-to <required-head-date> \
  --backup-dir /home/kalle/projects/rawcandle/temp/<run>/backups \
  --evidence-output-root /home/kalle/projects/rawcandle/temp/<run>/evidence \
  --confirm-db /home/kalle/projects/rawcandle/data/analysis.db \
  --confirm-ecosystem DATACENTER \
  --confirm-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --confirm-deployment-id <taxonomy_change_id> \
  --confirm-date-from 2025-08-01 \
  --confirm-date-to <required-head-date> \
  --expected-active-taxonomy-version DC_TAXONOMY_FULL_V1 \
  --scheduler-config /home/kalle/projects/rawcandle/scheduler_config.json \
  --repo-root /home/kalle/projects/rawcandle
```

Run:

```bash
python3 -m rawcandle.cli.run_ec_taxonomy_full_rebuild \
  <same arguments as the plan command>
```

Run while reusing the production backup already created before DC rebuild
writes:

```bash
python3 -m rawcandle.cli.run_ec_taxonomy_full_rebuild \
  <same guarded arguments> \
  --existing-backup-path /home/kalle/projects/rawcandle/temp/<run>/analysis_before_v2_rebuild.sqlite \
  --confirm-existing-backup-path /home/kalle/projects/rawcandle/temp/<run>/analysis_before_v2_rebuild.sqlite
```

Resume after a diagnosed failure:

```bash
python3 -m rawcandle.cli.run_ec_taxonomy_full_rebuild \
  <same arguments as the original run> \
  --resume
```

The confirmations must match the requested DB, ecosystem, taxonomy version,
deployment ID, and date range exactly. The orchestrator never widens the
requested range.

## Chunk Planning

Chunks are calendar-day spans with inclusive boundaries. Each chunk is at most
60 days, chronological, deterministic, gapless, and non-overlapping. Non-trading
dates remain part of the chunk input range; the existing per-chunk planner
selects valid source dates and records skipped dates.

The plan output includes:

```text
rebuild_mode=TAXONOMY_FULL_REBUILD
requested_start
requested_end
chunk_count
chunk_index
chunk_start
chunk_end
chunk_span_days
deployment_id
taxonomy_version
taxonomy_version_id
chunk_plan_hash
```

The `chunk_plan_hash` is part of the resume contract.

## Preconditions

Before backup or fact writes, the orchestrator verifies:

```text
deployment row exists
deployment ID matches ecosystem and proposed taxonomy
proposed taxonomy is loaded but not active
deployment rebuild_required=1
active taxonomy matches the expected current version when supplied
taxonomy CSV hash matches loaded metadata and deployment source hash
ecosystem is DATACENTER
requested range is compatible with deployment rebuild_start_date
backup and evidence paths are under repository temp/
scheduler config is not already switched to the proposed taxonomy when supplied
watchlist and taxonomy source files exist
```

Any precondition failure returns `BLOCKED_BEFORE_WRITES`.

## Backup Policy

Without `--existing-backup-path`, the orchestrator creates exactly one
SQLite-consistent DB backup before the first chunk. With
`--existing-backup-path`, it validates and records the supplied backup and
creates no new full DB backup.

The supplied backup must:

```text
exist
be a regular non-empty file
resolve under repository temp/
not be the live DB
not be a WAL or SHM file
open read-only as SQLite
pass PRAGMA integrity_check
contain expected critical EC and DC tables
pass structured schema compatibility checks against the live DB
have an mtime no later than orchestrator start
match --confirm-existing-backup-path after normalization
```

Schema compatibility distinguishes exact matches from compatible additive
operational drift. Canonical EC/DC facts, sidecar identity tables, and pipeline
watermarks remain strictly validated: missing tables, removed columns, changed
primary keys, changed uniqueness/index identity, changed required column
definitions, or arbitrary additive columns in canonical tables are blocking.

The pre-DC-rebuild restore point can still be valid when the live DB later gains
nullable or safely defaulted operational/audit columns on
`ec_taxonomy_change_deployment`. The current allowed live-only deployment
columns are:

```text
prepared_at_utc
validation_completed_at_utc
rebuild_evidence_json
rebuild_evidence_sha256
validation_evidence_json
validation_evidence_sha256
last_error
```

These differences are reported as:

```text
backup_schema_compatibility_status=COMPATIBLE_ADDITIVE_DRIFT
backup_schema_exact_match=false
backup_schema_compatible_with_live=true
backup_restore_requires_forward_schema_reapply=true
```

This means the backup is a valid rollback source, not that it already contains
the later deployment/audit columns. A manual restore must restore the original
backup, reapply the current forward schema preparation, verify schema and
integrity, and then restore or reconstruct post-backup deployment evidence as
appropriate. The orchestrator does not perform restore automatically and never
creates a fallback backup when an existing backup fails validation.

If validation fails, the orchestrator refuses before EC fact writes and does not
silently create a fallback backup. The user must either provide a valid backup
or rerun without the existing-backup option.

The backup evidence includes:

```text
backup_mode
backup_path
backup_created_by_orchestrator
backup_reused
backup_validation_status
backup_size
backup_mtime
backup_sha256
backup_schema_compatibility_status
backup_schema_exact_match
backup_schema_compatible_with_live
backup_schema_critical_mismatch_count
backup_schema_allowed_difference_count
backup_schema_allowed_differences
backup_schema_blocking_differences
backup_restore_requires_forward_schema_reapply
backup_error
```

Per-chunk execution reuses this backup reference and does not create another
multi-gigabyte DB copy.

## Execution

Chunks run sequentially in ascending date order. For each chunk the orchestrator:

```text
1. calls the existing taxonomy-aware planner
2. requires a ready taxonomy rebuild plan
3. calls the existing bounded runner with taxonomy_rebuild=true
4. disables per-chunk backup creation
5. defers per-chunk watermark finalization
6. requires coverage OK or OK_WITH_WARNINGS
7. requires parity OK or OK_WITH_WARNINGS
8. requires total_mismatch_count=0
9. persists chunk evidence
```

Chunks are not retried automatically and are not run concurrently.

## Failure Behavior

On first chunk failure:

```text
overall_status=FAILED
failed_chunk_index=<n>
retry_required=true
watermark_finalization_performed=false
```

The orchestrator stops immediately, leaves V2 inactive, does not switch
scheduler config, does not finalize canonical EC watermarks, and preserves the
backup and progress evidence.

Whole-range validation failure follows the same no-finalization rule.

## Resume

Progress is persisted as:

```text
temp/<run>/evidence/ec_taxonomy_full_rebuild_progress.json
```

Resume requires the same:

```text
deployment_id
taxonomy_version
taxonomy_source_sha256
requested_start
requested_end
chunk_plan_hash
backup_path
backup_sha256
```

Already completed chunks are skipped only after verification against current DB
state. Changed ranges, source hashes, chunk boundaries, backup paths, or backup
SHA-256 values block resume. If the original run used an existing backup, resume
also requires the same `--existing-backup-path` and confirmation path.

## Whole-Range Validation

After all chunks complete, one final range-level validation checks:

```text
all chunk coverage statuses accepted
all chunk parity statuses accepted
total_mismatch_count=0
stale-row validation OK
source taxonomy hash still matches
```

The existing deployment evidence service then verifies DC fact heads, EC fact
heads, EC watermark lineage, stale rows, coverage, parity, and mismatch count
before marking the deployment ready.

## Watermark Finalization

Canonical EC watermarks are not finalized after intermediate chunks. Only after
every chunk and whole-range validation succeeds does the orchestrator finalize:

```text
TICKER_SWING_BASE -> dc_ticker_swing_signal_daily
GROUP_SWING_BASE -> dc_group_swing_signal_daily
SYNTHETIC_OHLC_BASE -> dc_group_synthetic_ohlc_daily
GROUP_INDEX -> dc_group_index_daily
```

Finalization uses taxonomy rebuild mode so lineage changes from V1 to V2 are
written even when the latest date is unchanged.

Ordinary bounded backfill keeps its existing canonical watermark behavior.

## Deployment Evidence

The orchestrator updates EC rebuild status to `IN_PROGRESS` when execution
starts and `FAILED` on chunk or whole-range validation failure. On success it
calls the existing verified rebuild evidence service. `READY_TO_ACTIVATE` is
written only if that service verifies the full activation evidence.

No taxonomy activation is performed by this orchestrator.
