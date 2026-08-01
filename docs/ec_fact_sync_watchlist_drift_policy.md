# EC Fact Sync Watchlist Drift Policy

## Purpose

Canonical Datacenter -> EC fact synchronization is full-universe data movement. It must not be blocked by drift in the user-managed Datacenter watchlist membership.

The affected canonical fact mappings are:

```text
dc_ticker_swing_signal_daily -> ec_ticker_signal_daily
dc_group_swing_signal_daily -> ec_group_signal_daily
dc_group_synthetic_ohlc_daily -> ec_group_synthetic_ohlc_daily
dc_group_index_daily -> ec_group_index_daily
```

The watchlist tables are separate selection state:

```text
ec_watchlist
ec_watchlist_member
```

## Previous Behavior

The EC source-layer refresh and historical backfill planners compared the current source watchlist file with stored `ec_watchlist_member` rows. Any membership difference returned `BLOCKED_WATCHLIST_SOURCE`.

That was too strong for canonical fact synchronization because the canonical facts are not selected by watchlist membership.

## New Policy

Watchlist membership drift is a non-blocking diagnostic condition for canonical EC fact refresh and historical backfill.

When taxonomy/source checks, source fact availability, mapping checks, and replacement safety checks pass, the planner remains ready even if the source watchlist and stored EC watchlist membership differ.

The planner and execution summaries expose structured fields:

```text
watchlist_membership_status=MATCH|DRIFT_DETECTED
watchlist_sync_required=true|false
watchlist_source_member_count=<n>
watchlist_loaded_member_count=<n>
watchlist_missing_in_loaded_count=<n>
watchlist_loaded_only_count=<n>
watchlist_missing_in_loaded=[...]
watchlist_loaded_only=[...]
```

Scheduler bridge summaries additionally expose:

```text
ec_bridge_watchlist_membership_status
ec_bridge_watchlist_sync_required
ec_bridge_watchlist_missing_in_loaded_count
ec_bridge_watchlist_loaded_only_count
```

Watchlist drift alone must not make the Datacenter pipeline or EC bridge fail. If fact synchronization succeeds, the bridge may report:

```text
ec_bridge_status=OK
ec_bridge_retry_required=false
```

## Still Blocking

Unrelated safety gates remain blocking, including:

```text
missing or invalid taxonomy source
taxonomy source hash mismatch
missing required canonical DC source data
unsupported date range
unsafe replacement conditions
unclear taxonomy/entity mapping
database or schema failures
```

## Deferred Work

This phase does not automatically update:

```text
ec_watchlist
ec_watchlist_member
```

Intentional membership changes require a later explicit watchlist plan/apply workflow and UI support with preview, validation, audit evidence, and controlled membership writes.

After this code is deployed, the current production EC fact lag still requires a controlled EC bridge recovery/backfill task. This policy change only removes the incorrect planner block.
