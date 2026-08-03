# Datacenter DC Rebuild Optional Report Copy Recovery

## Classification

```text
DATACENTER_V2_DC_REBUILD_ACCEPTANCE_PATH_IMPLEMENTED
```

This document describes the recovery path for a controlled taxonomy rebuild
where Datacenter canonical facts completed but the optional Windows report-copy
stage failed.

## Canonical Boundary

Canonical Datacenter rebuild evidence includes:

```text
dc_ticker_swing_signal_daily
dc_group_swing_signal_daily
dc_group_synthetic_ohlc_daily
dc_group_index_daily
dc_pipeline_watermark rows for required DC components
generated Markdown/CSV reports under the requested output directory
```

The Windows copy to `/mnt/d/swing_reports` is noncanonical. It is useful for
operator convenience, but it does not determine whether V2 Datacenter facts are
correct.

## Copy Policy

Normal scheduled production runs keep the existing default:

```text
windows_report_copy_enabled=true
```

Controlled taxonomy rebuilds must disable the copy explicitly:

```bash
python3 run_datacenter_swing_pipeline.py \
  --price-db data/osakedata.db \
  --analysis-db data/analysis.db \
  --taxonomy-csv data/datacenter_taxonomy_full_v2.csv \
  --taxonomy-version DC_TAXONOMY_FULL_V2 \
  --market usa \
  --signal-date 2026-07-31 \
  --start-date 2025-08-01 \
  --index-base-date 2020-01-01 \
  --output-dir temp/<controlled-run>/dc_reports \
  --expected-ticker-count 257 \
  --expected-group-count 54 \
  --expected-synthetic-ohlc-count 53 \
  --no-windows-report-copy
```

With copy disabled, reports are still generated under `--output-dir`. The
pipeline summary records the copy as skipped. If copy is enabled, failures remain
fatal.

## Existing V2 Recovery

The completed V2 Datacenter run generated all canonical facts and all eight
report artifacts under:

```text
temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/
```

It failed only when copying those generated reports to a read-only `/mnt/d`
mount. Recalculating Stages 1-15 is not required if the guarded acceptance CLI
revalidates the production facts and evidence directory.

## DC-Only Acceptance

Use:

```bash
python3 -m rawcandle.cli.apply_datacenter_taxonomy_rebuild_evidence \
  --accept-dc-only \
  --analysis-db /home/kalle/projects/rawcandle/data/analysis.db \
  --ecosystem DATACENTER \
  --proposed-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --proposed-taxonomy-csv data/datacenter_taxonomy_full_v2.csv \
  --deployment-id 1 \
  --required-start-date 2025-08-01 \
  --required-signal-date 2026-07-31 \
  --evidence-dir temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z \
  --scheduler-config scheduler_config.json \
  --expected-scheduler-taxonomy-version DC_TAXONOMY_FULL_V1 \
  --expected-ticker-rows 257 \
  --expected-group-rows 54 \
  --expected-synthetic-rows 53 \
  --expected-index-rows 54 \
  --windows-copy-status FAILED_OPTIONAL
```

The command verifies production DB state directly. It refuses acceptance when
canonical heads, row counts, duplicate keys, DC watermarks, stale-row checks,
report files, stage evidence, deployment identity, taxonomy hash, or scheduler
taxonomy state do not match.

Successful DC-only acceptance writes:

```text
status=VALIDATION_REQUIRED
dc_rebuild_status=OK
dc_rebuild_acceptance_status=ACCEPTED
dc_rebuild_canonical_status=OK
dc_rebuild_report_generation_status=OK
dc_rebuild_windows_copy_status=FAILED_OPTIONAL
dc_rebuild_windows_copy_required=false
dc_rebuild_accepted_with_noncanonical_warning=true
```

It leaves:

```text
ec_rebuild_status=NOT_STARTED
coverage_status=NOT_STARTED
parity_status=NOT_STARTED
activation_status=NOT_ACTIVE
V1 active
V2 inactive
scheduler taxonomy config on V1
```

## Next Step

After DC-only acceptance, the next controlled production task is the DATACENTER
EC V2 full rebuild. That task should reuse the preserved production backup and
must still validate EC coverage, parity, watermark lineage, and activation
readiness before V2 can be activated.
