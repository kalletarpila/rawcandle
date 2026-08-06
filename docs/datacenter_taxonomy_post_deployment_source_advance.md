# Datacenter Taxonomy Post-Deployment Source Advance

## Purpose

`POST_DEPLOYMENT_SOURCE_ADVANCE_ONLY` is a guarded catch-up scope for
Datacenter `REPORT_STATUS_ONLY` taxonomy deployments. It is used when the
currently active source taxonomy receives new canonical signal dates after the
proposed taxonomy was materialized, but before activation.

The activation policy is:

```text
active_source_advance_policy=TARGET_MUST_CATCH_UP_BEFORE_ACTIVATION
```

The proposed taxonomy must contain complete canonical DC and EC facts through
the active source head before cleanup, whole-range validation, watermark
finalization, `READY_TO_ACTIVATE`, or activation.

## Scope

The source-advance backend is deliberately narrower than normal delta
carry-forward and EC rebuild:

```text
DC_REPAIR_SCOPE=POST_DEPLOYMENT_SOURCE_ADVANCE_ONLY
EC_RESUME_ACTION=COPY_POST_DEPLOYMENT_SOURCE_ADVANCE
```

It copies only already computed active-taxonomy facts for the exact missing
post-deployment source dates into the proposed taxonomy lineage.

It does not run:

```text
Datacenter pipeline
Stage 2
ticker/group/synthetic/index calculations
EC rebuild orchestration
EC loaders
EC chunks
broad historical recopy
```

`SEMANTIC_ROW_ONLY`, `ECOSYSTEM_AGGREGATE_ONLY`, and
`POST_DEPLOYMENT_SOURCE_ADVANCE_ONLY` have separate candidate sets, hashes,
confirmation contracts, and validation.

## Planner Contract

The planner derives:

```text
deployment original date_to
active source DC head
active source EC head
proposed target DC head
proposed target EC head
required activation head
source advance date range
source advance trading dates
DC candidate counts
EC candidate counts
candidate hash
```

Dates come from canonical source facts, not calendar-day continuity.

The planner blocks rather than widening scope if source dates are inconsistent,
target rows conflict, duplicates exist, computational recalculation is required,
or the execution class is not `REPORT_STATUS_ONLY`.

## DC Catch-Up

Canonical DC tables:

```text
dc_ticker_swing_signal_daily
dc_group_swing_signal_daily
dc_group_synthetic_ohlc_daily
dc_group_index_daily
```

The DC candidate model includes ticker rows, layer rows, subindustry rows, and
ecosystem aggregate rows. Unknown sentinel rows are excluded from the candidate
universe.

Apply is transactional and idempotent. Already copied source-advance rows return
`NO_CHANGE`; partial exact-date target state is repaired by deterministic
replace within the source-advance date range.

## EC Catch-Up

The EC implementation copies accepted active EC fact rows for the exact
source-advance dates and rewrites only the required target taxonomy lineage.
For `REPORT_STATUS_ONLY`, entity mappings are stable because ticker and group
membership structure is unchanged.

Canonical EC tables:

```text
ec_ticker_signal_daily
ec_group_signal_daily
ec_group_synthetic_ohlc_daily
ec_group_index_daily
```

`source_run_id` and related operation identifiers are handled by the existing
RSO parity policy as visible operational metadata drift. Semantic values and
required taxonomy lineage remain strict.

## Remaining Sequence

For deployment-2-like recovery, the intended sequence is:

```text
AGGREGATE_REPAIR_ALREADY_APPLIED
AGGREGATE_REPAIR_SCOPE_REVALIDATED
SEMANTIC_ROW_ONLY_REPAIR
COMPLETE_DC_TARGET_VALIDATED_THROUGH_ORIGINAL_RANGE
POST_DEPLOYMENT_SOURCE_ADVANCE_PLANNED
DC_SOURCE_ADVANCE_CARRIED_FORWARD
DC_SOURCE_ADVANCE_VALIDATED
EC_SOURCE_ADVANCE_CARRIED_FORWARD
EC_SOURCE_ADVANCE_VALIDATED
COMPLETE_DC_TARGET_VALIDATED_THROUGH_ACTIVATION_HEAD
COMPLETE_EC_TARGET_VALIDATED_THROUGH_ACTIVATION_HEAD
OLD_EC_CLEANED
WHOLE_RANGE_VALIDATED
WATERMARKS_FINALIZED
READY_TO_ACTIVATE
```

Cleanup cannot start before DC and EC targets cover the activation head.
Watermarks cannot be finalized before catch-up validation passes.

## Deployment 2 Read-Only Preflight

Implementation preflight was read-only and wrote evidence under:

```text
temp/datacenter_v2_1_source_advance_preflight/
```

Derived state:

```text
active_source_advance_policy=TARGET_MUST_CATCH_UP_BEFORE_ACTIVATION
semantic_row_repair_required=true
semantic_row_candidate_count=1
source_advance_catchup_required=true
source_advance_date_from=2026-08-05
source_advance_date_to=2026-08-05
dc_source_advance_candidate_count=418
ec_source_advance_candidate_count=418
ec_resume_action=COPY_POST_DEPLOYMENT_SOURCE_ADVANCE
ec_rebuild_required=false
ec_loaders_required=false
ec_chunks_required=false
safe_to_resume=true
```

No production resume, semantic repair, source catch-up, cleanup, watermark
finalization, activation, Scheduler run, pipeline run, Stage 2 run, EC rebuild,
backup, restore, migration, config change, taxonomy CSV change, or database
write occurred during implementation.
