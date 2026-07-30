# Datacenter Transitional EC Bridge Implementation

This document records the implemented scheduler bridge for the current
Datacenter Stage 2 incremental pilot. It is implementation evidence, not a
future EC architecture contract.

## Scope

The bridge is transitional:

```text
successful Datacenter materialized range
  -> current EC latest refresh or historical backfill
  -> existing coverage/parity acceptance
  -> scheduler-visible status
```

The future EC materialization, dirty-range, invalidation, and watermark model
remains separate and should be based on EC's own raw-data or durable shared
source dependencies, not on Datacenter table copies.

## Decision Rules

The scheduler builds a deterministic `EcBridgeDecision` from the Datacenter
post-step result and the selected signal date.

- Stage 2 incremental disabled: use the existing latest-date EC refresh path.
- Datacenter pipeline not successful: skip EC bridge materialization.
- Stage 2 incremental enabled but no successful materialized range is reported:
  skip EC bridge materialization.
- Successful materialized range exactly equals the selected signal date: use
  existing latest-date EC refresh.
- Successful materialized range spans multiple dates ending at or containing the
  selected signal date: use existing EC historical backfill for that range.

The historical backfill range comes from
`stage2_actual_materialized_start..stage2_actual_materialized_end`, not from the
planner-only requested range.

## Execution Paths

Single-date mode calls the existing `run_ec_source_layer_refresh` function with
the current scheduler arguments and preserves existing EC watermark refresh
behavior.

Multi-date mode calls the existing `run_ec_source_layer_backfill` function with
`allow_replace_existing=True` for the conservative materialized range. It does
not run an additional latest refresh.

After the entire historical backfill succeeds and coverage/fact parity are
accepted with zero mismatches, the backfill performs one final canonical EC fact
watermark advancement. This is a forward-only update using the actual latest
completed selected date, not the requested `date_to`.

The historical backfill advances only these canonical fact heads:

```text
TICKER_SWING_BASE -> ec_ticker_signal_daily
GROUP_SWING_BASE -> ec_group_swing_signal_daily
SYNTHETIC_OHLC_BASE -> ec_group_synthetic_ohlc_daily
GROUP_INDEX -> ec_group_index_daily
```

It does not copy the full `dc_pipeline_watermark` table and does not update
UNKNOWN/report/audit rows or derived synthetic OHLC relative/structure
watermarks.

## Status and Retry

Bridge success requires an accepted loader/backfill result and acceptable
existing coverage/parity evidence. For backfill, per-date coverage and parity
statuses are aggregated and total mismatches must be zero.

For historical backfill, bridge success also requires successful final
canonical fact watermark advancement or validation. If that final step fails,
the backfill is reported as failed even though selected-date fact rows may
already have been committed.

Bridge failure is scheduler-visible:

```text
ec_bridge_status=FAILED
ec_bridge_retry_required=true
```

If the market update and Datacenter pipeline otherwise succeeded, bridge failure
degrades the scheduler result to `OK_WITH_WARNINGS`. It does not downgrade an
existing primary scheduler failure.

This increment does not implement automatic retry or a durable pending queue.
The retry range is retained in the scheduler summary/log so an operator can run
the existing EC backfill manually.

## Deferred Production Repair Plan

If production canonical EC fact watermarks lag after a previously successful
historical backfill, the preferred repair is to rerun the corrected historical
backfill for the affected range, for example `2026-07-22..2026-07-29`, using
the supported backfill CLI and its normal coverage/parity gates.

A supported watermark-only repair may be used later only if the codebase
provides an audited CLI or function for that purpose. Do not repair production
watermarks with ad hoc SQL.

## Summary Fields

The scheduler summary and EC post-step log include additive bridge fields:

```text
ec_bridge_mode
ec_bridge_reason
ec_bridge_required_start
ec_bridge_required_end
ec_bridge_status
ec_bridge_load_status
ec_bridge_coverage_status
ec_bridge_parity_status
ec_bridge_retry_required
ec_bridge_exit_code
ec_bridge_error
ec_bridge_log
ec_bridge_watermark_refresh_performed
```

Existing `ec_source_layer_*` fields remain present for compatibility.

The historical backfill summary also exposes:

```text
watermark_policy=ADVANCE_CANONICAL_FACT_HEADS_AFTER_VALIDATED_BACKFILL
watermark_refresh_performed
watermark_advanced
watermark_candidate_latest_signal_date
watermark_rows_inserted
watermark_rows_updated
watermark_rows_unchanged
watermark_rows_total
watermark_advance_status
```

## Tests

Covered by focused scheduler/config, EC refresh/backfill, and Datacenter
orchestrator regression tests using mocks and temporary files/databases only.
