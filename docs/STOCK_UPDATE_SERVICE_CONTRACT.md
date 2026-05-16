# STOCK_UPDATE_SERVICE_CONTRACT

This document defines the extraction contract for the future stock update service.

Source of truth for the current behavior:

- [docs/STOCK_UPDATE_CURRENT_FLOW.md](/home/kalle/projects/rawcandle/docs/STOCK_UPDATE_CURRENT_FLOW.md)

This document does not implement the service. It locks down what the future extraction must preserve.

## 1. Purpose

The future stock update service exists to make the current stock update flow reusable by both:

- the current UI button flow
- a future headless CLI / scheduled run

The service must preserve the current behavior of the UI stock update flow.

The goal is reuse through extraction, not behavior redesign.

## 2. Definition of behavior parity

Behavior parity is strict.

Behavior parity means the future shared service must preserve:

- the same ticker universe source
- the same market default behavior
- the same market filtering behavior
- the same start override behavior
- the same per-ticker update decision
- the same Yahoo Finance fetch behavior
- the same OHLCV insert behavior
- the same duplicate avoidance behavior
- the same split synchronization behavior
- the same split correction behavior
- the same divergence update behavior
- the same candlestick update behavior
- the same final batch Dow structure update behavior
- the same error-continuation behavior
- the same final outcome semantics

Behavior parity does not mean:

- improving the logic
- changing defaults
- normalizing helper paths
- changing market scope
- changing ticker selection scope
- changing helper implementations
- redesigning progress handling
- changing update side effects

Behavior parity specifically does not authorize:

- path cleanup
- helper rewrites
- SQL strategy changes
- update policy changes
- optionality changes

If a future refactor changes any of the items listed above, that is a behavior change, not a parity extraction.

## 3. Future service boundary

Planned future service entrypoint:

- `run_stock_data_update(...)`

This entrypoint is not implemented in this step.

Planned parameters based on the current flow:

- `osakedata_db_path`
- `analysis_db_path`
- `market`
- `start_override`
- `progress_callback`
- `data_dir`
- `dry_run`:
  - not currently supported in the UI flow
  - may be supported later
  - currently future-only

Additional parameters that appear likely to be required from the current flow:

- `quarter_detection_run_id`:
  - UNCLEAR whether this should be a service-internal generated value or explicit input
- `checked_at_utc` / time source:
  - UNCLEAR whether service should own time generation or receive injected timestamps
- `sleep_enabled` or equivalent:
  - UNCLEAR
  - current flow includes hardcoded sleeps
  - future service may need a way to preserve or bypass them, but this is not yet defined
- `market_validator` or equivalent dependency injection:
  - UNCLEAR
  - current flow directly uses `validate_market(...)`
- `today_exclusive_end_date` provider:
  - UNCLEAR
  - current flow calls `_today_exclusive_end_date()`

No parameter beyond the current flow should be introduced unless a later prompt explicitly requires it.

## 4. What moves into the service

The future service should move the orchestration currently inside `RawCandleApp.update_stock_data()` into a shared non-UI execution path.

The following responsibilities should move into the future service:

- grouped ticker loading from `osakedata`
- market defaulting and filtering
- per-ticker latest date comparison
- start override application
- Yahoo OHLCV fetch orchestration
- insertion of missing OHLCV rows
- duplicate avoidance through current existing-date checks
- split sync orchestration
- split correction orchestration
- divergence update orchestration
- candlestick update orchestration
- final batch Dow structure update orchestration
- summary counting
- non-UI error handling behavior
- pause / throttling behavior currently inside the update loop
- quarter-state detection side effects currently mixed into the ticker loop

This does not mean rewriting helper implementations.

The future service should orchestrate the same currently used helpers unless a later prompt explicitly says otherwise.

That includes current helper/function usage such as:

- `yfinance.Ticker(...).history(...)`
- `stock.splits.sync_splits_for_ticker(...)`
- `_maybe_backfill_splits_for_ticker(...)` or an extracted equivalent with the same behavior
- `_calculate_and_save_divergences(...)` or an extracted equivalent with the same behavior
- `_run_incremental_candlestick_analysis(...)` or an extracted equivalent with the same behavior
- `analysis.stock_dow_structure.calculate_missing_or_outdated_stock_dow_structures(...)`

## 5. What stays in the UI layer

The following responsibilities should remain in the UI layer:

- reading values from UI widgets
- disabling the update button before execution
- enabling the update button after execution
- writing to `loading_text`
- changing UI colors
- calling `page.update()`
- converting service progress events into UI messages
- displaying final result to the user
- handling any direct Flet widget references

The future UI should become a thin wrapper around the shared service, but must preserve current user-visible behavior.

The future service must not directly manipulate:

- `self.loading_text`
- `self.page`
- `self.update_stock_button`
- `self.update_market_dropdown`
- `self.update_start_input`
- any Flet widget

## 6. Side effects that must remain part of the stock update contract

The future service must preserve the current full update flow, not only OHLCV fetching.

Required side effects in the future contract:

- Yahoo OHLCV fetch
- `osakedata` insert
- split sync through `stock.splits.sync_splits_for_ticker(...)`
- possible split correction through `_maybe_backfill_splits_for_ticker(...)` or an equivalent extracted helper
- divergence update
- candlestick analysis update
- batch Dow structure update after the ticker loop

Quarter / fundamentals related behavior:

- quarter-state detection during ticker update:
  - UNCLEAR whether this is part of the intended long-term stock update contract
  - It is clearly part of the current runtime behavior
  - Therefore extraction must preserve it unless a later prompt explicitly removes it

Quarter behavior contract status for extraction:

- Current extraction status:
  - REQUIRED for behavior parity
- Product-level long-term ownership:
  - UNCLEAR

## 7. Progress callback contract

The future service should not directly call:

- `self.loading_text`
- `self.page.update()`
- `self.update_stock_button`
- any Flet UI widget

Instead, the future service may emit progress messages through a callback such as:

- `progress_callback(event)`

This callback is not implemented in this step.

Conceptual future event types may include:

- `started`
- `ticker_started`
- `ticker_skipped`
- `ticker_updated`
- `ticker_error`
- `pause_started`
- `pause_completed`
- `dow_started`
- `dow_completed`
- `completed`
- `warning`

Conceptual event payload areas may include:

- ticker
- index / position
- total tickers
- rows inserted
- divergence result
- candlestick result
- warning text
- error text
- summary counts

This callback contract is meant to remove direct UI coupling from the future service without changing runtime semantics.

## 8. Result object contract

Future conceptual result object:

- `StockUpdateResult`

This is not implemented in this step.

Expected conceptual fields:

- `market`
- `tickers_checked`
- `tickers_updated`
- `tickers_skipped`
- `tickers_failed`
- `ohlcv_rows_inserted`
- `splits_synced`
- `divergences_updated`
- `candlesticks_updated`
- `dow_structures_updated`
- `dow_summary`
- `warnings`
- `errors`
- `status`

Notes:

- `splits_synced`:
  - likely numeric, but exact semantics are UNCLEAR
  - current flow prints split insertion information but does not maintain a dedicated aggregate counter
- `divergences_updated`:
  - likely numeric, but exact aggregate semantics are UNCLEAR
- `candlesticks_updated`:
  - likely numeric, but exact aggregate semantics are UNCLEAR
- `dow_structures_updated` versus `dow_summary`:
  - `dow_summary` is closer to the current flow because the Dow step already returns a summary dictionary

Possible future statuses:

- `OK`
- `OK_WITH_WARNINGS`
- `FAILED`
- `SKIPPED_ALREADY_RUNNING`
- `DRY_RUN`

Status notes:

- `SKIPPED_ALREADY_RUNNING`:
  - future-only
  - relevant only if locking is implemented later
- `DRY_RUN`:
  - future-only
  - no dry-run exists in the current UI flow

## 9. CLI scope contract

The future CLI must call the same service entrypoint as the UI.

The future CLI must not duplicate:

- Yahoo fetch logic
- DB write logic
- split logic
- split correction logic
- divergence logic
- candlestick logic
- Dow update logic

The CLI must be a wrapper around the shared service, not a second implementation.

CLI `SUMMARY` lines must be explicitly defined before CLI implementation begins.

This step does not implement the CLI.

## 10. Locking scope contract

Future locking should protect the shared service entrypoint, not only the CLI.

Reason:

- the UI button and scheduled CLI could otherwise run concurrently
- the current `_stock_update_in_progress` flag only protects the current UI process context
- it does not provide shared-process or shared-host protection

This step does not implement locking.

## 11. Explicit non-goals

Non-goals for the service extraction project:

- no new data provider
- no new ticker universe model
- no database schema changes
- no SQL upsert conversion unless explicitly requested later
- no market calendar implementation
- no retry redesign
- no async/threading redesign
- no analysis logic changes
- no UI redesign
- no market filter redesign
- no helper path normalization unless explicitly requested later
- no change to current side effects
- no replacement of current helper functions unless explicitly requested later

## 12. Risks and open questions

The following risks and open questions are present based on the current flow documentation.

### Hardcoded helper paths

- `_calculate_and_save_divergences()` reconstructs:
  - `data/osakedata.db`
  - `data/analysis.db`
- Final Dow batch update also reconstructs:
  - `data/osakedata.db`
  - `data/analysis.db`
- Risk:
  - future service extraction may appear parameterized while some downstream steps still use hardcoded paths
- Status:
  - UNCLEAR how these should be handled in later steps without changing behavior

### Split correction behavior

- `_maybe_backfill_splits_for_ticker(...)` may:
  - delete prices from `2018-01-01`
  - refetch prices from Yahoo
  - delete analysis rows
  - recompute divergence
- Risk:
  - this is a large destructive side effect relative to the surrounding incremental update flow
- Status:
  - REQUIRED for behavior parity
  - but risky during extraction

### Quarter / fundamentals side effects

- Quarter detection runs during stock update
- It writes into market-specific fundamentals-related state
- Risk:
  - unclear ownership boundary between OHLCV update and fundamentals state maintenance
- Status:
  - REQUIRED for parity
  - product-level contract remains UNCLEAR

### UI threading model

- Current UI method does not use a background thread
- It directly performs the full update loop
- Risk:
  - extracting to a service must not accidentally imply a threading redesign
- Status:
  - no redesign allowed in the extraction step

### Market filtering after grouped SQL

- Current market filtering is Python-side after grouped SQL
- Risk:
  - changing it into SQL in a later step could change behavior
- Status:
  - REQUIRED to preserve as-is unless a later prompt explicitly changes it

### Dow batch update scope

- Dow batch update runs after the full ticker loop
- It is market-scoped through the selected market value
- Risk:
  - moving this call earlier, per ticker, or widening/narrowing scope would change behavior
- Status:
  - REQUIRED to preserve as-is

### Sleep / throttling semantics

- Current flow sleeps:
  - between Yahoo chunks
  - between tickers
  - every 500 tickers
- Risk:
  - extraction may accidentally remove or relocate these delays
- Status:
  - REQUIRED for parity unless a later prompt explicitly changes them
- Contract shape:
  - UNCLEAR whether later service should expose these as configurable or keep them internal

### Running guard semantics

- Current UI method uses `_stock_update_in_progress`
- Risk:
  - later service extraction plus external locking may create overlapping guard semantics
- Status:
  - future locking design is not defined yet
- Contract:
  - UNCLEAR

### Summary semantics

- Current UI flow has:
  - `updated_count`
  - `skipped_count`
  - `error_count`
  - quarter summary print lines
  - Dow summary appended to UI text
- Risk:
  - service result and future CLI summary could drift from existing semantics
- Status:
  - exact future `StockUpdateResult` aggregate definitions are still UNCLEAR
