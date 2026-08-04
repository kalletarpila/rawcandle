# Datacenter EC Taxonomy Replacement Cleanup And Finalization

## Purpose

`DC_TAXONOMY_FULL_V2` EC facts can be fully rebuilt without rerunning the
seven-chunk rebuild if the only remaining blocker is old DATACENTER EC rows in
the replacement range. The recovery path is:

```text
plan old-taxonomy cleanup
-> apply old-taxonomy cleanup
-> validate existing rebuilt V2 facts
-> finalize canonical EC watermarks
-> update rebuild evidence
-> plan activation
```

No production cleanup, watermark finalization, deployment evidence update,
activation, scheduler run, Datacenter pipeline run, EC loader, EC backfill, EC
rebuild, migration apply, backup, restore, taxonomy CSV change, watchlist change,
or scheduler config change occurred as part of this backend implementation.

## Cleanup Scope

The cleanup is limited to canonical DATACENTER EC fact rows in the confirmed
taxonomy replacement range:

```text
ecosystem_id = DATACENTER
taxonomy_version_id <> target_taxonomy_version_id
signal_date >= rebuild_start_date
signal_date <= required_signal_date
```

Tables:

```text
ec_ticker_signal_daily
ec_group_signal_daily
ec_group_synthetic_ohlc_daily
ec_group_index_daily
```

The cleanup must not delete:

```text
target V2 rows
another ecosystem
dates outside the replacement range
noncanonical EC tables
DC facts
taxonomy metadata
entity or membership rows
watchlists
scheduler configuration
watermarks
```

## Planner

The read-only planner is:

```bash
python3 -m rawcandle.cli.plan_ec_taxonomy_replacement_cleanup \
  --db data/analysis.db \
  --ecosystem DATACENTER \
  --target-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --deployment-id 1 \
  --date-from 2025-08-01 \
  --date-to 2026-07-31 \
  --format json
```

It reports per table:

```text
target_v2_row_count
old_version_row_count
old_version_taxonomy_ids
old_version_min_date
old_version_max_date
delete_candidate_count
delete_candidate_key_hash
unexpected_target_rows
unexpected_other_ecosystem_rows
safe_to_apply
blocking_errors
warnings
```

The combined `delete_candidate_hash` is the production confirmation value for
the apply command.

## Apply

The guarded apply command requires exact confirmations:

```bash
python3 -m rawcandle.cli.apply_ec_taxonomy_replacement_cleanup \
  --db data/analysis.db \
  --ecosystem DATACENTER \
  --target-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --deployment-id 1 \
  --date-from 2025-08-01 \
  --date-to 2026-07-31 \
  --confirm-db data/analysis.db \
  --confirm-ecosystem DATACENTER \
  --confirm-target-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --confirm-deployment-id 1 \
  --confirm-date-from 2025-08-01 \
  --confirm-date-to 2026-07-31 \
  --confirm-delete-candidate-hash <planner delete_candidate_hash> \
  --format json
```

The delete is one SQLite transaction covering all four canonical tables. Either
all four table deletes commit, or none commit. Before writing, apply re-plans the
candidate set, verifies the hash, verifies the deployment identity, verifies V2
is loaded but inactive, verifies V1 remains active, verifies DC rebuild status,
checks V2 fact heads and duplicate/range state, and hashes V2 rows. After the
delete, V2 row hashes must be unchanged.

Cleanup evidence is written to the taxonomy deployment evidence JSON with:

```text
deployment_id
ecosystem_code
target_taxonomy_version
target_taxonomy_version_id
date_from
date_to
cleanup_plan_hash
delete_candidate_hash
started_at_utc
completed_at_utc
status
per_table_candidate_counts
per_table_deleted_counts
old_taxonomy_ids
pre_cleanup_fact_hashes
post_cleanup_fact_hashes
invocation_source
error
```

## Validation-Only Recovery

The validation-only CLI is:

```bash
python3 -m rawcandle.cli.finalize_ec_taxonomy_rebuild_validation \
  --db data/analysis.db \
  --ecosystem DATACENTER \
  --target-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --taxonomy-csv data/datacenter_taxonomy_full_v2.csv \
  --deployment-id 1 \
  --date-from 2025-08-01 \
  --date-to 2026-07-31 \
  --coverage-status OK \
  --parity-status OK \
  --total-mismatch-count 0 \
  --finalize-watermarks \
  --update-deployment-evidence \
  --format json
```

It does not rerun loaders or chunks:

```text
validation_mode=EXISTING_REBUILT_FACTS
loaders_rerun=false
chunks_rerun=false
```

It blocks if any stale row remains, V2 fact heads are incomplete, V2 facts have
duplicates or rows outside range, coverage/parity are not accepted, mismatch
count is nonzero, or the loaded taxonomy source hash differs from the supplied
CSV.

## Watermarks And Evidence

Watermark finalization is allowed only after validation succeeds. It updates
only the canonical DATACENTER EC watermark scopes:

```text
TICKER_SWING_BASE -> dc_ticker_swing_signal_daily
GROUP_SWING_BASE -> dc_group_swing_signal_daily
SYNTHETIC_OHLC_BASE -> dc_group_synthetic_ohlc_daily
GROUP_INDEX -> dc_group_index_daily
```

Required final values:

```text
latest_signal_date=2026-07-31
taxonomy_version_id=2
status=OK
```

Equal latest dates still update lineage from V1 or NULL to V2. Noncanonical
watermarks and other ecosystems remain unchanged.

After watermark finalization, rebuild evidence can transition the deployment to:

```text
dc_rebuild_status=OK
ec_rebuild_status=OK
coverage_status=OK
parity_status=OK
status=READY_TO_ACTIVATE
activation_status=NOT_ACTIVE
```

## Retry Policy

The intended recovery policy is:

```text
NO_REBUILD_RETRY_NEEDED_VALIDATION_ONLY_AFTER_FIX
```

The original full production backup remains rollback evidence:

```text
temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/analysis_before_datacenter_v2_full_rebuild.sqlite
sha256=ef63868f55073dd3a9eedccea5097871446b02af1577f8c4659fe6dd325db3ea
```

This backend implementation neither creates nor modifies that backup.
