# Datacenter Watchlist Start-of-Run Reconciliation

## Purpose

`watchlists/datacenter_watchlist.txt` is the transitional source of truth for the Datacenter user watchlist. At the start of a Datacenter or standalone Datacenter EC production run, the stored EC watchlist membership is reconciled to match that file before canonical processing starts.

This keeps:

```text
ec_watchlist
ec_watchlist_member
```

current without making canonical facts depend on watchlist membership.

## Canonical Fact Independence

Watchlist reconciliation must not restrict or invalidate canonical full-universe facts:

```text
dc_ticker_swing_signal_daily
dc_group_swing_signal_daily
dc_group_synthetic_ohlc_daily
dc_group_index_daily

ec_ticker_signal_daily
ec_group_signal_daily
ec_group_synthetic_ohlc_daily
ec_group_index_daily
```

Changing watchlist membership alone does not recompute historical facts and does not advance canonical fact watermarks.

## Start-of-Run Flow

Production entry points call the shared reconciliation service before the main Datacenter or EC operation:

```text
read TXT file
normalize and validate tickers
read active stored EC watchlist membership
compute added and removed tickers
apply one SQLite transaction when membership differs
record audit evidence for applied changes
verify the active DB membership exactly matches the file
continue the main run
```

Possible statuses:

```text
NO_CHANGE
APPLIED
FAILED
```

`FAILED` stops the applicable production run before canonical processing begins.

## Validation

The reconciliation service validates that the file exists, is readable, has a non-empty effective membership, contains unique normalized tickers, and uses accepted ticker syntax. Tickers are normalized to uppercase and sorted deterministically.

Ticker membership is not required to exist in the current Datacenter taxonomy. The watchlist may contain user-selected watchlist-only tickers, and the loader uses the existing EC watchlist-only ticker entity creation path instead of creating taxonomy membership.

Ambiguous active EC ticker entities are refused before membership mutation.

## Transaction And Audit

Membership changes are all-or-nothing in one SQLite transaction. Removed tickers are explicitly deleted from active membership, added tickers are inserted, and the post-state is checked against the normalized file.

Applied changes are recorded in:

```text
ec_watchlist_reconciliation_audit
```

The audit row stores source path, source SHA-256, previous and new counts, deterministic added and removed ticker lists, invocation source, status, and timestamp. `NO_CHANGE` runs do not create audit rows.

Automatic daily reconciliation does not create a full `analysis.db` backup. Rollback safety comes from the transaction, post-state verification, and durable audit evidence for applied changes.

## Entry Points

Scheduled Datacenter runs pass the configured watchlist file to:

```text
run_datacenter_swing_pipeline.py
```

The Datacenter CLI reconciles once before canonical pipeline execution when `--watchlist-file` is supplied and the run is not a dry run.

Standalone EC commands also reconcile by default:

```text
rawcandle.cli.run_ec_source_layer_refresh
rawcandle.cli.run_ec_source_layer_backfill
```

The scheduler Datacenter -> EC bridge calls those EC functions with reconciliation disabled because the overall Datacenter run has already reconciled the watchlist.

Manual plan/apply boundaries are available for later UI reuse:

```text
rawcandle.cli.plan_datacenter_watchlist_reconciliation
rawcandle.cli.apply_datacenter_watchlist_reconciliation
```

The plan command is read-only. The apply command requires explicit confirmation arguments.

## Run Summary

Datacenter, EC, and scheduler summaries expose structured reconciliation fields:

```text
watchlist_reconciliation_attempted
watchlist_reconciliation_status
watchlist_source_reference
watchlist_source_sha256
watchlist_source_member_count
watchlist_previous_member_count
watchlist_current_member_count
watchlist_added_count
watchlist_removed_count
watchlist_added_tickers
watchlist_removed_tickers
watchlist_reconciliation_error
```

After successful reconciliation, EC planners should normally observe:

```text
watchlist_membership_status=MATCH
watchlist_sync_required=false
```

Those diagnostic fields remain distinct from reconciliation status.

## Deferred

The UI is intentionally not implemented here. It should reuse the same plan/apply service boundary.

This is also not the future permanent ecosystem watchlist source model. The current TXT file workflow is transitional and can later be replaced by an ecosystem-native source layer without changing canonical fact independence.
