# Datacenter Taxonomy Full Rebuild Backend

This document describes the backend safety mechanisms added for the first full
`DC_TAXONOMY_FULL_V2` Datacenter and DATACENTER EC rebuild.

No production Datacenter pipeline, Stage 2 run, EC rebuild, taxonomy rebuild,
activation, migration apply, scheduler run, scheduler config change, production
database write, or watermark update occurred as part of this implementation.

## Final Backend Classification

```text
DATACENTER_V2_REBUILD_BACKEND_READY
```

The next step is a controlled production replacement run, not another backend
change.

## Full-Range EC Rebuild

Ordinary historical EC backfill keeps the existing 60 calendar day range limit.
A full taxonomy range is accepted only with explicit taxonomy-rebuild mode:

```bash
python3 -m rawcandle.cli.run_ec_source_layer_backfill \
  --db /home/kalle/projects/rawcandle/data/analysis.db \
  --ecosystem DATACENTER \
  --taxonomy-version DC_TAXONOMY_FULL_V2 \
  --date-from 2025-08-01 \
  --date-to <required-head-date> \
  --taxonomy-csv data/datacenter_taxonomy_full_v2.csv \
  --watchlist watchlists/datacenter_watchlist.txt \
  --backup-dir temp/<controlled-run>/backups \
  --confirm-db /home/kalle/projects/rawcandle/data/analysis.db \
  --confirm-ecosystem DATACENTER \
  --confirm-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --taxonomy-rebuild \
  --deployment-id <taxonomy_change_id> \
  --confirm-rebuild-start 2025-08-01 \
  --confirm-rebuild-end <required-head-date> \
  --allow-replace-existing \
  --skip-watchlist-reconciliation
```

The planner emits:

```text
rebuild_mode=TAXONOMY_FULL_REBUILD
deployment_id
taxonomy_version_id
taxonomy_version_code
requested_start
requested_end
selected_date_count
```

## DATACENTER EC Replacement

In taxonomy-rebuild mode, the runner creates a backup first and then deletes old
DATACENTER canonical EC facts in the requested range before loading V2 rows.
The delete predicate is scoped by `ecosystem_id` and `signal_date` for:

```text
ec_ticker_signal_daily
ec_group_signal_daily
ec_group_synthetic_ohlc_daily
ec_group_index_daily
```

Other ecosystems are not touched. V2 is not activated by this step.

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

Taxonomy-rebuild mode updates canonical DATACENTER watermark rows to V2 even
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

The evidence command verifies database state before changing deployment status:

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
2. Create production DB and scheduler-config backups.
3. Run prepare_datacenter_taxonomy_rebuild.
4. Run full DC pipeline for DC_TAXONOMY_FULL_V2 from 2025-08-01.
5. Run run_ec_source_layer_backfill with --taxonomy-rebuild.
6. Run apply_datacenter_taxonomy_rebuild_evidence.
7. Run plan_datacenter_taxonomy_activation.
8. Run apply_datacenter_taxonomy_activation with --scheduler-config.
9. Verify active taxonomy, config keys, fact heads, watermarks, coverage, parity,
   and final git/operational evidence.
```
