# Datacenter Incremental Execution and EC Sync Contract

This document defines the target design contract for a Stage 2 incremental
execution pilot in the Datacenter swing pipeline.

Primary evidence source:

- `docs/current_datacenter_pipeline_dependency_map.md`

This is a design-level contract only. It does not implement runtime behavior,
schema changes, scheduler changes, watermark changes, or EC loader changes.

## Architectural Framing

This document has two deliberately separate parts:

```text
Part A - Permanent Datacenter Incremental Execution Contract
Part B - Transitional Current DC -> EC Synchronization Bridge
```

The Datacenter incremental execution model is intended to be a permanent
improvement to the current Datacenter pipeline.

The current `dc_* -> ec_*` loading path is transitional architecture. Future EC
watermark, dirty-range, invalidation, and materialization design will be based
on EC's own raw-data or durable shared source-layer dependencies. The
transitional DC-to-EC bridge must not become the foundation of the future
multi-ecosystem EC architecture.

Pilot scope is limited to Stage 2, `Ticker swing base snapshots`.

Pilot acceptance statement:

> Stage 2 can be executed using a trading-day-based incremental model with
> correct warmup and overlap, without allowing the current EC source layer to
> become silently out of sync.

The pilot must not introduce full incremental execution across all 16 stages.

## Part A - Permanent Datacenter Incremental Execution Contract

## 1. Goals and Non-Goals

Goals:

- Avoid recalculating Stage 2 from the fixed pipeline start date on every daily
  run.
- Use `dc_pipeline_watermark` as one planner input, not as a naive execution
  gate.
- Preserve calculation correctness.
- Keep current write semantics compatible with `replace-date`.
- Propagate the Stage 2 dirty output range conservatively to required downstream
  Datacenter stages.
- Report the range actually materialized by the execution.

Non-goals for the pilot:

- Full pipeline-wide incremental optimization.
- Minimal downstream ranges.
- Changed-row hashes or checksums.
- Sparse affected-date sets.
- Partial dirty-range resolution.
- Generic EC invalidation architecture.
- Permanent DC-specific EC synchronization-debt schema.

## 2. Core Terminology

`requested_range`

The full logical range requested by scheduler, CLI, operator, or configured
pipeline defaults. For the current daily Datacenter flow this can still begin at
the configured historical start date.

`input_range`

The date range read by the stage to provide enough history for correct
calculation.

`output_range`

The date range whose materialized output rows are replaced or updated.

```text
input_range != output_range
```

The input range supplies sufficient calculation history. The output range
defines the dates whose materialized rows are replaced.

`calculation_input_start`

The first valid date that must be read to calculate the first output date
correctly.

`materialization_start`

The first date whose output rows must be written or replaced.

`materialization_end`

The last date whose output rows must be written or replaced.

`watermark_start`

The start date recorded in the existing `dc_pipeline_watermark` row for a
component.

`watermark_end`

The end date recorded in the existing `dc_pipeline_watermark` row for a
component.

`overlap_trading_days`

The number of valid market/signal dates before the newest unprocessed date that
are recalculated and rematerialized to cover recent-history effects.

`warmup_trading_days`

The number of valid market/signal dates read before `materialization_start` to
provide sufficient calculation history. Warmup dates are read as input, but are
not necessarily written as output.

`dirty_from_date`

An explicit invalidation date for a component caused by known changes in its own
inputs, algorithm, parameters, or source corrections.

`dependency_dirty_from_date`

An invalidation date propagated from an upstream dependency.

`FULL`

Run the component across the full requested range required by component policy.

`INCREMENTAL`

Run only the required output range, with sufficient trading-day overlap and
warmup input history.

`SKIP`

Do not execute the component because the planner can prove it is already current
for the requested target and no invalidation applies.

## 3. Trading-Day Semantics

Normative rules:

- Lookback, overlap, and warmup must be based on valid market/signal dates.
- They must not be calculated with naive calendar-day subtraction.
- The initial implementation may use the current Datacenter valid-date logic
  identified in the dependency map.
- A calendar abstraction should prevent planner policy from becoming
  permanently coupled to the temporary date source.
- `CONFIRMED_FROM_CODE`: current Stage 2 uses
  `max_valid_price_rows=220` as its implementation history limit.
- `REQUIRES_VERIFICATION`: the exact pilot overlap and warmup policy must be
  confirmed before implementation.

The contract must not infer a final overlap value only from the current
`max_valid_price_rows=220` implementation detail.

## 4. Planner Contract

The planner decides what a stage should do. Stages execute a planner decision;
they must not independently implement conflicting ad hoc incremental policies.

Planner inputs include at least:

```text
component
market
taxonomy_version
signal_version
calc_version
requested_start
requested_end
watermark_start
watermark_end
dirty_from_date
dependency_dirty_from_date
version_status
trading_calendar
overlap policy
warmup policy
force mode
```

Planner outputs include at least:

```text
mode: FULL | INCREMENTAL | SKIP
requested_start
requested_end
materialization_start
materialization_end
calculation_input_start
calculation_input_end
overlap_trading_days
warmup_trading_days
write_mode
reason_code
reason_details
```

`calculation_input_end` normally equals the requested or selected target date,
unless component policy explicitly narrows it.

## 5. Initial Decision Rules

Conservative design-level rules:

- Missing usable watermark -> `FULL`.
- Relevant version or taxonomy incompatibility -> `FULL` or an explicit
  invalidation path.
- New signal dates -> `INCREMENTAL` with trading-day overlap.
- Explicit dirty range -> materialization begins no later than that dirty date,
  subject to stage-specific policy.
- Dependency dirty range -> materialization begins no later than the propagated
  dependency dirty date, subject to stage-specific policy.
- No new dates and no invalidation -> `SKIP`.
- Forced full execution overrides automatic planning.
- Forced range execution overrides automatic planning within the requested
  operator-provided range.
- Watermark advancement occurs only after successful stage completion and
  validation.

This document does not claim that all invalidation mechanisms already exist.
Where invalidation state is missing today, the implementation plan must define
the smallest safe pilot mechanism or explicitly defer it.

## 6. Stage 2 Contract

Evidence status: `CONFIRMED_FROM_CODE` unless marked otherwise.

Current Stage 2:

- Name: `Ticker swing base snapshots`.
- CLI: `run_datacenter_ticker_swing_signals.py`.
- Function:
  `analysis.datacenter_indices.swing_ticker_persistence.persist_datacenter_ticker_swing_snapshots_for_dates`.
- Output table: `dc_ticker_swing_signal_daily`.
- Current orchestrator passes `--write-mode replace-date`.
- Range execution resolves valid price dates, then calls per-date persistence.
- Per-date `replace-date` deletes matching
  `(signal_date, signal_version, taxonomy_version)` rows and inserts freshly
  built rows.
- Range mode already separates effective price-history input from selected
  output dates through bounded history preload.
- Current implementation history limit is `max_valid_price_rows=220`.
- Current orchestrator execution does not use `dc_pipeline_watermark` to skip or
  narrow Stage 2.

Partial-write risk:

- Each per-date write commits inside the Stage 2 persistence function.
- If range execution fails after earlier dates have completed, earlier per-date
  writes may remain while later dates are not processed.
- The orchestrator watermark is written only if the whole Stage 2 CLI returns
  success.
- Therefore the pilot must distinguish planned range from actual completed and
  validated materialized range.

Illustrative plan output, not final policy:

```text
mode: INCREMENTAL
watermark_end: 2026-07-24
requested_end: 2026-07-27
materialization_start: <derived valid trading date>
materialization_end: 2026-07-27
calculation_input_start: <earlier valid trading date required for warmup>
calculation_input_end: 2026-07-27
write_mode: replace-date
reason_code: NEW_SIGNAL_DATES_WITH_LOOKBACK_OVERLAP
```

## 7. Conservative Downstream Propagation

The pilot does not optimize every downstream stage to its minimal safe range.
Stage 2's dirty output range is propagated conservatively.

Stage ordering must be distinguished from proven data dependency. The dependency
map confirms the following Stage 2 effects:

- Stage 3 group swing base metrics read `dc_ticker_swing_signal_daily`.
- Stage 7 group timing is affected through Stage 3 outputs.
- Stage 9 ticker scanners read `dc_ticker_swing_signal_daily` and same-date
  subindustry timing state from `dc_group_swing_signal_daily`.
- Stage 10 audit reads Datacenter facts for validation.
- Stage 11 technical relevance uses selected-date ticker snapshots for report
  context, but remains outside the core pilot unless implementation verification
  shows it is required for correctness.
- Stages 12-15 reports read the Datacenter facts and produce artifacts.
- Current EC source-layer facts are loaded from the four canonical/current
  Datacenter source tables.

The confirmed materialization chain is at least:

```text
Stage 2
  -> Stage 3
     -> Stage 7
        -> Stage 9
  -> Stage 9
```

`REQUIRES_VERIFICATION`: exact downstream ranges for Stage 6-8 and any
additional stateful behavior must be confirmed before later pipeline-wide
incremental optimization. The Stage 2 pilot may use a wider conservative range
for downstream execution.

## 8. Materialized-Range Reporting

The pilot should produce a lightweight structured run artifact or structured
summary. A new database schema is not required at this stage.

The artifact should report at least:

```text
pipeline_run_id
stage
component
source/output table
planned mode
planned input range
planned output range
actual materialized start
actual materialized end
status
validation status
reason code
```

Successful watermark update must correspond to validated stage completion, not
merely to earlier per-date commits. If partial physical writes occurred but the
stage did not complete validation, the run artifact must not describe the stage
as successfully materialized for the whole planned output range.

## 9. Status and Failure Semantics

Design-level statuses:

`UP_TO_DATE`

The component is validated through the requested target date for the relevant
version and no known invalidation applies.

`OUT_OF_DATE`

The component lacks validated coverage for the requested target date or has a
known dirty dependency.

`PARTIAL`

Some physical writes may exist, but the stage did not complete and validate the
entire required materialization range.

`FAILED`

The stage or required post-step failed, and the system cannot report the
requested work as cleanly completed.

Important distinctions:

- An old or missing watermark means the planner cannot prove current validated
  coverage.
- An old or missing watermark does not prove that no physical writes occurred.
- Partial physical writes are not equivalent to a completed and validated
  materialized range.
- A completed and validated materialized range is the only state that can safely
  support watermark advancement.

This document does not define a full new status persistence schema.

## Part B - Transitional Current DC -> EC Synchronization Bridge

## 10. Transitional Architecture Statement

Evidence status: `CONFIRMED_FROM_CODE`

Current EC facts are loaded from:

- `dc_ticker_swing_signal_daily`
- `dc_group_swing_signal_daily`
- `dc_group_synthetic_ohlc_daily`
- `dc_group_index_daily`

This is a temporary bridge for the current Datacenter ecosystem pilot.

Current target grouping:

```text
ec_ticker_signal_daily
  <- dc_ticker_swing_signal_daily

ec_group_signal_daily
  <- dc_group_swing_signal_daily

ec_group_synthetic_ohlc_daily
  <- dc_group_synthetic_ohlc_daily

ec_group_index_daily
  <- dc_group_index_daily
```

The current source tables themselves combine fields from several Datacenter
stages. For example, `dc_ticker_swing_signal_daily` contains Stage 2 base fields
and Stage 9 scanner fields.

## 11. Bridge Execution Rule

Minimal bridge rule:

```text
If the Datacenter execution materializes only the selected signal date:
    use the existing EC latest-date refresh path.

If the Datacenter execution rewrites more than the selected signal date:
    use the existing EC historical backfill/date-based replace path
    for the same conservative affected range.
```

The EC bridge range must be based on successfully materialized Datacenter
outputs, not merely on the initially planned range.

For the pilot, a single conservative affected range is acceptable even if
component-level ranges could later differ.

## 12. EC Bridge Validation

Evidence status: `CONFIRMED_FROM_CODE`

Current EC refresh/backfill tooling already runs coverage and fact parity
audits. The bridge must use those existing checks.

Rules:

- A bridge load is not successful merely because loader execution returned.
- The affected range must pass the existing parity and coverage checks
  appropriate to the current tools.
- Historical EC refresh must not move the EC latest watermark backwards.
- Current historical backfill behavior intentionally skips
  `ec_pipeline_watermark` refresh and must be acknowledged in scheduler/post-step
  status.

## 13. Visible and Persistent Failure Reporting

The pilot must not introduce the earlier heavy permanent schema:

- no `ec_sync_pending`
- no `ec_sync_run_component`
- no permanent DC-specific synchronization-debt model

Instead, the transitional bridge requires a persistent run, log, or summary
artifact with at least:

```text
ec_bridge_mode
required_refresh_start
required_refresh_end
load_status
parity_status
retry_required
error
```

Normative requirement:

> If the transitional EC bridge fails or parity is not acceptable, the overall
> Datacenter scheduler/post-step result must not be reported as a clean `OK`.

This is a temporary operational safeguard, not the future EC invalidation
architecture.

## 14. Future EC Architecture Boundary

The future EC model will be designed separately around:

```text
raw/shared input changes
  -> ecosystem component invalidation
  -> EC materialization
  -> EC validation
  -> EC watermark advancement
```

The future EC architecture must not be derived from Datacenter tables or from
the transitional bridge described here.

## Normative Requirements

`REQ-DC-PLAN-001`

Stage 2 must not use naive `watermark_end + 1` execution without overlap and
warmup.

`REQ-DC-RANGE-001`

Planner must distinguish calculation input and materialization output ranges.

`REQ-DC-CALENDAR-001`

Overlap and warmup must use valid trading/signal dates.

`REQ-DC-MATERIALIZE-001`

Actual successfully materialized range must be reported.

`REQ-DC-WATERMARK-001`

Watermark advances only after successful validated stage completion.

`REQ-DC-DOWNSTREAM-001`

Stage 2 dirty output propagates conservatively to required downstream work.

`REQ-EC-BRIDGE-001`

Historical Datacenter rewrites require transitional EC range backfill.

`REQ-EC-BRIDGE-002`

EC bridge success requires load plus parity/coverage acceptance.

`REQ-STATUS-001`

Overall status cannot be clean `OK` when the required transitional EC bridge
failed.

`REQ-ARCH-001`

The transitional DC-to-EC bridge must not define the future EC raw-data
architecture.

## Pilot Acceptance Criteria

1. Stage 2 no longer always starts at the fixed configured `2025-08-01` when a
   compatible successful watermark exists.
2. Stage 2 uses valid trading dates for overlap and warmup.
3. Planner emits separate input and output ranges.
4. Stage 2 retains `replace-date` output semantics.
5. Downstream execution is conservatively triggered from the Stage 2
   materialization range.
6. Actual materialized range is visible in structured run output.
7. A multi-date Datacenter rewrite invokes the transitional EC backfill bridge
   for the affected range.
8. EC parity/coverage failure prevents a clean overall `OK`.
9. A single-date normal run remains compatible with the current EC latest
   refresh.
10. No permanent DC-specific EC synchronization-debt schema is introduced by the
    pilot.

## Evidence and Uncertainty Handling

Stage-specific statements must use these labels consistently:

- `CONFIRMED_FROM_CODE`
- `INFERRED_FROM_FLOW`
- `REQUIRES_VERIFICATION`

Open verification items from the dependency map must not be converted into
asserted facts.

Implementation questions still requiring verification:

- `REQUIRES_VERIFICATION`: exact safe Stage 2 overlap policy.
- `REQUIRES_VERIFICATION`: how `max_valid_price_rows=220` maps to warmup versus
  output overlap.
- `REQUIRES_VERIFICATION`: actual completed-range reporting under per-date
  partial failure.
- `REQUIRES_VERIFICATION`: exact downstream stage ranges for the pilot.
- `REQUIRES_VERIFICATION`: Stage 6-8 state/lookback behavior.
- `REQUIRES_VERIFICATION`: transaction boundaries in range-update stages.
- `REQUIRES_VERIFICATION`: precise scheduler status propagation for EC bridge
  failure.

## Explicit Constraints

- Documentation only.
- Do not modify Python code.
- Do not modify tests.
- Do not modify database schemas or migrations.
- Do not modify scheduler configuration.
- Do not modify watermark behavior.
- Do not modify EC loaders.
- Do not stage or commit files unless explicitly requested later.

