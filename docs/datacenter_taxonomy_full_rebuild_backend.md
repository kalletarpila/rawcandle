# Datacenter Taxonomy Full Rebuild Backend

This document describes the backend safety mechanisms added for the first full
`DC_TAXONOMY_FULL_V2` Datacenter and DATACENTER EC rebuild.

No production Datacenter pipeline, Stage 2 run, EC rebuild, taxonomy rebuild,
activation, migration apply, scheduler run, scheduler config change, production
database write, or watermark update occurred as part of this implementation.

## Final Backend Classification

```text
DATACENTER_EC_TAXONOMY_REBUILD_ORCHESTRATOR_IMPLEMENTED
```

The next step is a controlled production replacement run using the chunked EC
taxonomy full-rebuild orchestrator, not another backend change.

## Full-Range EC Rebuild

Ordinary historical EC backfill keeps the existing 60 calendar day range limit.
A full taxonomy range is handled only by the high-level chunked orchestrator:

```bash
python3 -m rawcandle.cli.plan_ec_taxonomy_full_rebuild \
  --db /home/kalle/projects/rawcandle/data/analysis.db \
  --ecosystem DATACENTER \
  --taxonomy-version DC_TAXONOMY_FULL_V2 \
  --taxonomy-csv data/datacenter_taxonomy_full_v2.csv \
  --watchlist watchlists/datacenter_watchlist.txt \
  --deployment-id <taxonomy_change_id> \
  --date-from 2025-08-01 \
  --date-to <required-head-date> \
  --backup-dir temp/<controlled-run>/backups \
  --evidence-output-root temp/<controlled-run>/evidence \
  --confirm-db /home/kalle/projects/rawcandle/data/analysis.db \
  --confirm-ecosystem DATACENTER \
  --confirm-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --confirm-deployment-id <taxonomy_change_id> \
  --confirm-date-from 2025-08-01 \
  --confirm-date-to <required-head-date> \
  --expected-active-taxonomy-version DC_TAXONOMY_FULL_V1 \
  --scheduler-config scheduler_config.json \
  --repo-root /home/kalle/projects/rawcandle
```

Execution uses the same arguments with:

```bash
python3 -m rawcandle.cli.run_ec_taxonomy_full_rebuild \
  <same guarded arguments> \
  --existing-backup-path temp/<controlled-run>/backups/analysis_before_v2_rebuild.sqlite \
  --confirm-existing-backup-path temp/<controlled-run>/backups/analysis_before_v2_rebuild.sqlite
```

The orchestrator emits:

```text
rebuild_mode=TAXONOMY_FULL_REBUILD
backup_mode=EXISTING_BACKUP | ORCHESTRATOR_CREATED
backup_created_by_orchestrator=true|false
backup_reused=true|false
backup_validation_status=OK
backup_schema_compatibility_status=EXACT_MATCH|COMPATIBLE_ADDITIVE_DRIFT
backup_schema_exact_match=true|false
backup_schema_compatible_with_live=true|false
backup_schema_critical_mismatch_count
backup_schema_allowed_difference_count
backup_restore_requires_forward_schema_reapply=true|false
requested_start
requested_end
chunk_count
chunk_plan_hash
deployment_id
taxonomy_version
taxonomy_version_id
```

Each chunk is then executed through `run_ec_source_layer_backfill` with
`--taxonomy-rebuild` semantics, no per-chunk DB backup, and deferred watermark
finalization.

## DATACENTER EC Replacement

In taxonomy-rebuild mode, the chunk runner deletes old DATACENTER canonical EC
facts for that chunk before loading V2 rows. The delete predicate is scoped by
`ecosystem_id` and `signal_date` for:

```text
ec_ticker_signal_daily
ec_group_signal_daily
ec_group_synthetic_ohlc_daily
ec_group_index_daily
```

Other ecosystems are not touched. V2 is not activated by this step. The
orchestrator either creates exactly one full DB backup before the first chunk or
reuses the pre-existing full DB backup created before the DC rebuild. In the
controlled V2 production sequence, the backup is created before the first DC
write and passed to the EC orchestrator with `--existing-backup-path`.

The existing-backup validator treats that file as a pre-DC-rebuild restore
point. It must pass path, confirmation, mtime, SHA-256 recording, read-only
SQLite open, `PRAGMA integrity_check`, critical table presence, and structured
schema compatibility checks. Canonical EC/DC facts, sidecar identity tables, and
pipeline watermarks require exact compatible identity. Additive columns in those
canonical structures are blocking.

The validator can accept later live-only nullable/defaulted operational columns
on `ec_taxonomy_change_deployment`, including:

```text
prepared_at_utc
validation_completed_at_utc
rebuild_evidence_json
rebuild_evidence_sha256
validation_evidence_json
validation_evidence_sha256
last_error
```

That result is reported as `COMPATIBLE_ADDITIVE_DRIFT` and
`backup_restore_requires_forward_schema_reapply=true`. A manual restore must
therefore restore the original backup, reapply the current forward schema
preparation, verify schema and integrity, and then restore or reconstruct any
post-backup deployment evidence. The orchestrator does not restore
automatically, does not mutate the original backup, and does not create a
fallback full backup when an existing backup is rejected.

## EC Watermark Lineage

Canonical EC watermark identity remains:

```text
ecosystem_id
pipeline_name
source_table
```

The lineage field is:

```text
taxonomy_version_id
```

Taxonomy-rebuild mode updates canonical DATACENTER watermark rows to V2 only
after all chunks and whole-range validation succeed. It updates lineage even
when the latest date equals the previous V1 latest date. Ordinary same-taxonomy
backfill remains idempotent. Ordinary backfill refuses old or NULL lineage when
the requested taxonomy differs.

## DC Rebuild Preparation

The preparation command marks the loaded deployment `REBUILD_IN_PROGRESS`,
captures current V1 DC watermark evidence, confirms V2 metadata and source hash,
and confirms V2 has not inherited compatible DC watermark progress:

```bash
python3 -m rawcandle.cli.prepare_datacenter_taxonomy_rebuild \
  --analysis-db /home/kalle/projects/rawcandle/data/analysis.db \
  --ecosystem DATACENTER \
  --proposed-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --proposed-taxonomy-csv data/datacenter_taxonomy_full_v2.csv \
  --deployment-id <taxonomy_change_id> \
  --expected-active-taxonomy-version DC_TAXONOMY_FULL_V1 \
  --confirm-proposed-taxonomy-version DC_TAXONOMY_FULL_V2
```

It does not run the pipeline and does not delete facts.

## Evidence Status

The DC-only acceptance path verifies that a Datacenter rebuild completed through
canonical facts, downstream materializations, DC watermarks, and report
generation, while allowing an explicitly classified optional Windows report-copy
failure:

```bash
python3 -m rawcandle.cli.apply_datacenter_taxonomy_rebuild_evidence \
  --accept-dc-only \
  --analysis-db /home/kalle/projects/rawcandle/data/analysis.db \
  --ecosystem DATACENTER \
  --proposed-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --proposed-taxonomy-csv data/datacenter_taxonomy_full_v2.csv \
  --deployment-id <taxonomy_change_id> \
  --required-start-date 2025-08-01 \
  --required-signal-date <required-head-date> \
  --evidence-dir temp/<controlled-run> \
  --scheduler-config scheduler_config.json \
  --expected-scheduler-taxonomy-version DC_TAXONOMY_FULL_V1 \
  --windows-copy-status FAILED_OPTIONAL
```

This mode writes only DC rebuild acceptance evidence:

```text
status=VALIDATION_REQUIRED
dc_rebuild_status=OK
ec_rebuild_status unchanged
coverage_status unchanged
parity_status unchanged
activation_status=NOT_ACTIVE
```

The full evidence command is used only after EC rebuild and parity have also
completed:

```bash
python3 -m rawcandle.cli.apply_datacenter_taxonomy_rebuild_evidence \
  --analysis-db /home/kalle/projects/rawcandle/data/analysis.db \
  --ecosystem DATACENTER \
  --proposed-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --proposed-taxonomy-csv data/datacenter_taxonomy_full_v2.csv \
  --deployment-id <taxonomy_change_id> \
  --required-signal-date <required-head-date>
```

It checks DC fact heads, EC fact heads, canonical EC watermark lineage, coverage,
parity, mismatch count, and stale rows. It writes `READY_TO_ACTIVATE` only when
all activation prerequisites pass.

## Windows Report Copy Policy

Generated Markdown/CSV report files under `--output-dir` are part of controlled
taxonomy rebuild evidence. Copying those files to `/mnt/d/swing_reports` is not
part of canonical Datacenter fact correctness.

The general Datacenter pipeline keeps the historical default:

```text
windows_report_copy_enabled=true
```

Controlled taxonomy rebuild commands must opt out explicitly:

```bash
python3 run_datacenter_swing_pipeline.py ... --no-windows-report-copy
```

With copy disabled, report generation still runs and the pipeline summary records
the Windows copy as disabled/skipped. If copying is enabled and the destination is
read-only or unavailable, the copy failure remains fatal.

## Activation and Config

Activation remains blocked until rebuild evidence is complete. With
`--scheduler-config`, activation also switches only the taxonomy config keys and
creates a config backup:

```text
datacenter_taxonomy_csv
datacenter_taxonomy_version
ec_source_layer_taxonomy_csv
ec_source_layer_taxonomy_version
```

If config write or validation fails, database activation is rolled back and the
config file is restored from backup. The scheduler is not started by activation.

## Source-Data Policy

The V2 CSV is now a durable source artifact with this SHA-256:

```text
178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1
```

`.gitignore` tracks only intended taxonomy CSVs and does not unignore generated
CSV outputs.

## CBRS and WYFI

`CBRS` and `WYFI` are accepted as listing-history edge cases:

```text
CBRS first_date=2026-05-14, short history is allowed
WYFI first_date=2025-08-07, post-rebuild-start listing is allowed
```

No pre-listing rows are fabricated. Short history uses the existing Stage 2
`INSUFFICIENT_HISTORY` behavior and does not fail the whole rebuild by itself.
Unexpected missing latest-date price data remains blocking.

## Recommended Next Production Task

Run one controlled production replacement sequence:

```text
1. Confirm scheduler is paused or guarded.
2. Create one production DB backup and scheduler-config backup.
3. Run prepare_datacenter_taxonomy_rebuild.
4. Run full DC pipeline for DC_TAXONOMY_FULL_V2 from 2025-08-01.
5. Run plan_ec_taxonomy_full_rebuild.
6. Run run_ec_taxonomy_full_rebuild with --existing-backup-path pointing to the
   pre-DC-write backup.
7. Run plan_datacenter_taxonomy_activation.
8. Run apply_datacenter_taxonomy_activation with --scheduler-config.
9. Verify active taxonomy, config keys, fact heads, watermarks, coverage, parity,
   and final git/operational evidence.
```
