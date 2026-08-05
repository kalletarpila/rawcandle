# Datacenter Taxonomy Report Status Only Execution

## Classification

```text
DATACENTER_RSO_CLEANUP_ORDER_AND_AGGREGATE_CARRY_FORWARD_FIXED
```

This document describes the guarded execution path for taxonomy changes where
only reporting metadata changes. It is an implementation capability only. It
does not record or imply that a production V2 to V2.1 taxonomy change was
executed.

## Purpose

`REPORT_STATUS_ONLY` is a distinct taxonomy change execution class. It is used
when the proposed taxonomy keeps the computational membership graph unchanged
and changes only:

```text
taxonomy_version
report_group_status
notes
```

The goal is to create target-taxonomy lineage for DC and EC facts without
running Datacenter calculations, Stage 2, downstream derived calculations,
reports, scheduler jobs, external fetches, or production pipeline steps.

## Field Dependency Registry

The classifier assigns each CSV column to a dependency class:

```text
taxonomy_version      IDENTITY
ticker                IDENTITY
layer                 IDENTITY
subindustry           IDENTITY
is_primary            COMPUTATIONAL
role_weight           COMPUTATIONAL
report_group_status   REPORTING_ONLY
notes                 DOCUMENTATION_ONLY
```

Unknown columns block `REPORT_STATUS_ONLY` planning. Changes to computational
or membership identity fields also block this execution class.

## Planner Contract

The plan includes the explicit execution class and safety evidence:

```text
change_execution_class
report_status_only_safe
report_status_only_changed_row_count
report_status_only_changed_ticker_count
report_status_only_changed_fields
report_status_only_blocking_reasons
computational_rebuild_required
datacenter_pipeline_required
stage2_required
```

For a safe report-status-only change:

```text
change_execution_class=REPORT_STATUS_ONLY
report_status_only_safe=true
computational_rebuild_required=false
datacenter_pipeline_required=false
stage2_required=false
```

The plan hash includes `change_execution_class`. A plan prepared as
`REPORT_STATUS_ONLY` cannot be silently executed as ordinary `DELTA_REBUILD` or
`FULL_REBUILD` under the same plan hash.

## Execution Contract

The execution dispatcher handles `REPORT_STATUS_ONLY` before ordinary delta or
full rebuild execution.

The corrected guarded path:

```text
REPORT_STATUS_SCOPE_VALIDATED
BACKUP_VERIFIED
TARGET_TAXONOMY_METADATA_LOADED
DC_FACTS_CARRIED_FORWARD
DC_FACTS_VALIDATED
EC_FACTS_CONSTRUCTED
COVERAGE_PARITY_VALIDATED
OLD_EC_CLEANED
WHOLE_RANGE_VALIDATED
WATERMARKS_FINALIZED
READY_TO_ACTIVATE
```

The cleanup-before-stale invariant is mandatory:

```text
whole-range stale-row validation is valid only after old-version EC cleanup
has APPLIED or NO_CHANGE evidence for the same deployment, ecosystem, target
taxonomy, target taxonomy ID, and replacement date range.
```

If that evidence is missing or stale:

```text
whole_range_validation_status=BLOCKED_CLEANUP_NOT_COMPLETED
```

Whole-range validation must not infer cleanup success only from current zero
candidates.

The DC carry-forward is idempotent delete/replace into the target taxonomy
lineage for the canonical DC fact tables:

```text
dc_ticker_swing_signal_daily
dc_group_swing_signal_daily
dc_group_synthetic_ohlc_daily
dc_group_index_daily
```

The complete DC key-universe contract is table-specific:

```text
dc_ticker_swing_signal_daily:
  ordinary ticker keys

dc_group_swing_signal_daily:
  ordinary layer/subindustry group keys
  ecosystem aggregate key ecosystem:DC_ECOSYSTEM_TOTAL

dc_group_synthetic_ohlc_daily:
  ordinary layer/subindustry group keys
  ecosystem aggregate key only if present in the active source slice

dc_group_index_daily:
  ordinary layer/subindustry group keys
  ecosystem aggregate key ecosystem:DC_ECOSYSTEM_TOTAL
```

Unexpected sentinel keys are not copied. Target validation reports ordinary
keys, ecosystem aggregate keys, unexpected keys, duplicate keys, and semantic
mismatches separately. EC construction cannot start unless required DC
carry-forward validation is OK.

The path records no-computation evidence:

```text
datacenter_pipeline_called=false
stage2_planner_called=false
stage2_called=false
ticker_calculation_called=false
group_calculation_called=false
synthetic_ohlc_calculation_called=false
group_index_calculation_called=false
downstream_calculation_called=false
report_generation_called=false
external_fetch_called=false
```

## Scheduler UI

The Taxonomy tab shows the execution class and the derived safety flags. For
`REPORT_STATUS_ONLY`, the UI explicitly shows that Datacenter pipeline and Stage
2 are not required and that DC facts are copied to the new lineage.

The confirmation key includes `change_execution_class`, so changing from
`REPORT_STATUS_ONLY` to another execution class invalidates the confirmation.

## Constraints

This capability does not execute the production taxonomy change by itself. It
does not change taxonomy CSVs, scheduler configuration, signal algorithms,
classifications, schemas, production databases, or watermarks during
implementation.
