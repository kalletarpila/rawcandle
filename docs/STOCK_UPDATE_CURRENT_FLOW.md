# STOCK_UPDATE_CURRENT_FLOW

This document describes the current implementation flow behind the UI action `Päivitä osaketiedot` / `Update stock data`.

It is an inspection snapshot of the current codebase. It is intentionally concrete so the logic can later be extracted into a shared service layer without changing behavior by accident.

## 1. Entry point

- UI file: [main.py](/home/kalle/projects/rawcandle/main.py)
- Class: `RawCandleApp`
- UI control wiring:
  - `self.update_stock_button = ft.ElevatedButton(..., on_click=self.update_stock_data, ...)`
  - Defined around [main.py](/home/kalle/projects/rawcandle/main.py)
- Method triggered by the button:
  - `RawCandleApp.update_stock_data(self, e)`
  - Defined in [main.py](/home/kalle/projects/rawcandle/main.py)
- Short description:
  - Reads existing tickers from `osakedata.db`
  - Filters them by selected market
  - Fetches missing OHLCV data from Yahoo Finance per ticker
  - Writes new OHLCV rows into SQLite
  - Syncs splits
  - Runs per-ticker downstream analysis updates
  - Runs a batch Dow structure post-processing step at the end

## 2. Parameter sources

### Selected market

- Source widget: `self.update_market_dropdown`
- UI definition: [main.py](/home/kalle/projects/rawcandle/main.py)
- Read inside `update_stock_data()`
- Current behavior:
  - `selected_market = self.update_market_dropdown.value if ... else ""`
  - then normalized as:
    - `selected_market.strip().lower()` if provided
    - otherwise defaulted to `"omxh"`

### Default market if no market is selected

- Current default inside `update_stock_data()`:
  - `omxh`
- This default is local to the current button flow.

### Ticker universe / ticker list

- Source database:
  - `self.osakedata_db_path`
- Query used:
  - `SELECT osake, MIN(pvm) as ensimmainen_pvm, MAX(pvm) as viimeisin_pvm, MAX(market) as market FROM osakedata GROUP BY osake ORDER BY osake`
- This means the ticker universe comes from existing rows already stored in `osakedata`.

### Database path

- Main OHLCV database path:
  - `self.osakedata_db_path`
- Analysis database path used indirectly:
  - `self.analysis_db_path`
- Additional hardcoded paths are also used inside helper methods:
  - `_calculate_and_save_divergences()` builds:
    - `data/osakedata.db`
    - `data/analysis.db`
  - The final batch Dow post-processing also builds:
    - `data/osakedata.db`
    - `data/analysis.db`
- This means the current flow is not fully parameter-pure.

### User-selected options

- `self.update_start_input`
  - optional manual start override
  - expected format: `YYYY-MM-DD`
- `self.update_market_dropdown`
  - market filter for the update

### Hardcoded defaults

- Default market when no market is selected:
  - `omxh`
- Fallback ticker market if a DB market is missing:
  - `usa`
- If `validate_market(...)` fails for a ticker market:
  - market is reset to `usa`
- Long Yahoo fetch ranges are chunked at:
  - `730` days check
  - then split into chunks of `365` days
- Sleep delays:
  - `0.5` seconds between large-range Yahoo chunks
  - `1.0` or `1.5` seconds between ticker updates
  - `30` seconds after each `500` tickers

## 3. Ticker selection flow

### Where tickers are read from

- Tickers are read from SQLite table:
  - `osakedata`
- Query is executed directly in `RawCandleApp.update_stock_data()`
- Tickers do not come from UI manual input in this flow.

### Source of ticker universe

- Existing stored OHLCV data only
- Not from configuration
- Not from a market master table
- Not from an external ticker list

### How market filter is applied

- The SQL query reads all grouped tickers first.
- Market filtering happens in Python after the query:
  - rows are kept only if `row[3]` (`MAX(market)`) matches `selected_market`
- If no rows remain after filtering:
  - UI shows `❌ Ei osakkeita markkinalle <MARKET>`
  - method returns

### How already up-to-date tickers are detected

- For each grouped ticker:
  - `last_date = MAX(pvm)` from the grouped SQL result
- Current date is computed as:
  - `today = datetime.now().strftime("%Y-%m-%d")`
- Up-to-date check:
  - `needs_update = last_date < today`
- If `needs_update` is false:
  - ticker is skipped
  - skip counter increments
  - every 10th skipped ticker may update UI status text

### How the latest stored trading date per ticker is determined

- Directly from the grouped query:
  - `MAX(pvm) as viimeisin_pvm`
- This is date-string based current stored max date per ticker.

## 4. Yahoo Finance fetch flow

### Main fetch path

- File: [main.py](/home/kalle/projects/rawcandle/main.py)
- Method:
  - `RawCandleApp.update_stock_data()`
- Yahoo client usage:
  - direct `yfinance` usage
  - `stock = yf.Ticker(ticker)`
- There is no dedicated wrapper around the main OHLCV fetch in this flow.

### Start date and end date

- Per ticker base update start:
  - `last_date + 1 day`
- Optional user override:
  - `effective_start = max(update_start, start_override)` if override exists
- Fetch end:
  - `fetch_until_exclusive = _today_exclusive_end_date()`
- Fetch is expressed as one or more `(start_date, end_date)` ranges in `date_ranges`

### Whether only missing data is fetched

- Yes, current intent is incremental fetch only.
- It fetches from the day after the latest stored date.
- Existing DB dates are also rechecked before insert:
  - `SELECT pvm FROM osakedata WHERE osake = ?`
  - existing dates are skipped during insert

### Chunking logic

- If one fetch range is longer than `730` days:
  - it is split into `365` day chunks
  - each chunk uses `stock.history(start=..., end=...)`
- Otherwise one direct `history(start=..., end=...)` call is used

### Empty / no-new-data handling

- If all fetched history is empty:
  - ticker is counted as skipped
  - loop continues to next ticker
- No error is shown for that ticker in this branch.

### Failed ticker fetch handling

- The main per-ticker body is inside one broad `try/except`
- Any exception increments `error_count`
- UI status becomes:
  - `❌ {idx}/{total_stocks}: {ticker} - Virhe: {str(ex)}`
- Processing then continues to the next ticker

## 5. OHLCV write flow

### Target database and table

- Database:
  - `self.osakedata_db_path`
- Table:
  - `osakedata`

### Columns written

- `osake`
- `pvm`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `market`

### Insert / upsert behavior

- Plain `INSERT INTO osakedata (...) VALUES (...)`
- No explicit `INSERT OR IGNORE`
- No explicit `ON CONFLICT DO UPDATE`

### Duplicate handling

- Duplicates are avoided in application logic before insert:
  - existing dates are read for the ticker
  - if `date_str in existing_dates`, row is skipped
- This is pre-insert duplicate avoidance, not SQL upsert logic

### Transaction handling

- Uses `with sqlite3.connect(db_path) as conn:`
- Inserts are executed through one cursor
- Explicit `conn.commit()` only if `rows_added > 0`
- Transaction scope is per ticker write block

### Error handling

- Write errors are caught by the outer per-ticker `try/except`
- On failure:
  - ticker counts as error
  - UI error text is shown
  - loop continues

## 6. Split synchronization flow

### Where split sync is triggered

- File: [main.py](/home/kalle/projects/rawcandle/main.py)
- Trigger point:
  - immediately after OHLCV insert block
  - inside `update_stock_data()`

### Function(s) involved

- Imported in `main.py`:
  - `from stock.splits import sync_splits_for_ticker`
- Implementation file:
  - [stock/splits.py](/home/kalle/projects/rawcandle/stock/splits.py)
- Main function:
  - `sync_splits_for_ticker(db_path, ticker, yf_ticker=stock)`

### Whether it runs per ticker or per market

- Per ticker

### Whether it is optional or always executed

- Always attempted for each ticker after OHLCV fetch/write block
- But failure is swallowed locally:
  - exception is caught
  - warning is printed
  - ticker processing continues

### Split DB write behavior

- Split rows are written into:
  - `splits_data`
- `stock/splits.py` creates `splits_data` if missing
- Insert behavior:
  - `INSERT OR IGNORE`
- Unique key:
  - `UNIQUE(osake, split_date)` on the created table definition

### Additional split correction path

- File: [main.py](/home/kalle/projects/rawcandle/main.py)
- Helper:
  - `RawCandleApp._maybe_backfill_splits_for_ticker(ticker)`
- Current behavior:
  - checks `has_uncorrected_splits(conn, ticker)`
  - if needed, deletes prices from `2018-01-01`
  - refetches prices from Yahoo from `2018-01-01`
  - deletes analysis rows for the ticker
  - recomputes divergence with `only_missing=False`
  - marks splits corrected if successful
- This is additional corrective logic beyond the ordinary split sync.

## 7. Downstream analysis update flow

### 7.1 Divergence update

- Trigger point:
  - after split sync and split backfill decision
- File: [main.py](/home/kalle/projects/rawcandle/main.py)
- Method:
  - `RawCandleApp._calculate_and_save_divergences(ticker, only_missing=True)`
- Internal implementation:
  - imports `recompute_divergence_for_ticker` from `analysis.divergence_recompute`
- Paths constructed internally:
  - `data/osakedata.db`
  - `data/analysis.db`

#### Whether it runs for all tickers or only updated tickers

- Runs inside the per-ticker loop only for tickers that entered the fetch/update path
- It does not run for already up-to-date skipped tickers

#### Whether it is optional or always executed

- Normally always attempted after split handling
- Exception:
  - if `_maybe_backfill_splits_for_ticker()` returned `True`
  - then divergence is not run through the normal `only_missing=True` path
  - instead the split correction helper has already recomputed divergence

#### Failure handling

- `_calculate_and_save_divergences()` catches exceptions and returns `(False, 0, error)`
- The outer flow does not abort on divergence failure
- Ticker loop continues

### 7.2 Candlestick analysis update

- Trigger point:
  - only if `rows_added > 0`
- File: [main.py](/home/kalle/projects/rawcandle/main.py)
- Method:
  - `RawCandleApp._run_incremental_candlestick_analysis(ticker, analysis_start, analysis_end)`
- Internal implementation:
  - calls `analysis.run_analysis.run_candlestick_analysis(...)`
  - then persists findings through `analysis.database_manager.DatabaseManager.insert_finding(...)`

#### Whether it runs for all tickers or only updated tickers

- Only for tickers where new OHLCV rows were added

#### Whether it is optional or always executed

- Conditional on `rows_added > 0`

#### Failure handling

- Wrapped in local `try/except`
- Errors become `analysis_error`
- Ticker update still counts as updated
- UI summary line includes `analyysivirhe`
- Loop continues

### 7.3 Dow structure update

- There are two Dow-related paths in current stock update behavior.

#### Per-ticker helper exists but is not used in the current batch button flow

- File: [main.py](/home/kalle/projects/rawcandle/main.py)
- Method:
  - `RawCandleApp._update_single_ticker_dow_structures(ticker)`
- This helper exists, but `update_stock_data()` does not call it.

#### Actual batch Dow update used by the button flow

- Trigger point:
  - after the entire ticker loop finishes
- File:
  - [main.py](/home/kalle/projects/rawcandle/main.py)
- Function called:
  - `analysis.stock_dow_structure.calculate_missing_or_outdated_stock_dow_structures(...)`
- Implementation file:
  - [analysis/stock_dow_structure.py](/home/kalle/projects/rawcandle/analysis/stock_dow_structure.py)

#### Whether it runs for all tickers or only updated tickers

- It runs once after the batch
- Scoped by market:
  - `market=selected_market.strip().lower() if selected_market else None`
- Since `selected_market` is currently defaulted to `omxh`, this batch call currently runs market-scoped to `omxh` when no explicit market is chosen

#### Whether it is optional or always executed

- Always attempted after the main ticker loop

#### Failure handling

- Wrapped in its own `try/except`
- On failure:
  - stock update summary remains visible
  - UI appends warning:
    - `⚠️ Dow-rakenteiden päivitys epäonnistui: ...`
- The overall method still completes

## 8. Progress / logging / UI coupling

The current update flow is tightly coupled to the UI.

### Direct widget coupling

- `self.loading_text.value`
- `self.loading_text.color`
- `self.page.update()`
- `self.update_stock_button.disabled`
- `self.update_market_dropdown`
- `self.update_start_input`

### Progress behavior

- No separate progress bar object found in this flow
- Progress is shown by mutating `self.loading_text`
- Examples:
  - start message
  - per-ticker fetch status
  - skip messages every 10 tickers
  - 500 ticker pause message
  - final summary
  - Dow post-processing summary

### Background worker / threading

- `update_stock_data()` itself does not create a thread
- It runs directly from the button click handler
- Therefore the UI method itself owns the loop, sleeps, and status updates

### Callbacks

- No service-style callback abstraction is used
- Progress reporting is hardwired directly to UI fields and `page.update()`

### Print / logging behavior

- Uses direct `print(...)` calls in multiple places
- Examples:
  - quarter detection summary lines
  - per-ticker update summary
  - split warnings
- No unified logger abstraction is used for the main flow

### Other side-effect coupling

- Quarter state detection is mixed into the OHLCV fetch loop
- Split correction may delete and refetch old price data
- Analysis cleanup/recompute may happen during split correction

These parts are strong signals that the current method is not a pure service boundary.

## 9. Error handling and completion behavior

### If one ticker fails

- Per-ticker exception is caught
- `error_count` increments
- UI shows ticker-specific error text
- Processing continues to next ticker

### If Yahoo returns no data

- If combined `all_hist` is empty:
  - ticker is treated as skipped
  - loop continues
- No hard failure for the whole batch

### If database write fails

- Exception bubbles to outer per-ticker `try/except`
- Ticker becomes an error
- Batch continues

### If downstream analysis fails

- Split sync failure:
  - caught locally
  - warning printed
  - batch continues
- Divergence failure:
  - helper returns `(False, 0, error)`
  - batch continues
- Candlestick failure:
  - converted into `analysis_error`
  - batch continues
- Final batch Dow structure failure:
  - caught separately after ticker loop
  - warning shown in UI
  - method still completes

### Whether the whole update stops or continues

- Continues on per-ticker failures
- Stops early only on preconditions such as:
  - invalid `start_override`
  - missing `osakedata.db`
  - no stocks in DB
  - no stocks after market filter
  - already running guard via `_stock_update_in_progress`

### What the user sees in the UI at the end

- Base completion summary:
  - processed count
  - updated count
  - skipped count
  - error count
- Then either:
  - additional Dow summary appended on success
  - or Dow warning appended on failure
- Button is re-enabled in `finally`
- `_stock_update_in_progress` is reset in `finally`

## 10. Current flow summary

1. UI button `self.update_stock_button` calls `RawCandleApp.update_stock_data()`.
2. Market is resolved from `self.update_market_dropdown`, defaulting to `omxh` if blank.
3. Optional manual start override is read from `self.update_start_input`.
4. Tickers are loaded from `osakedata` in `self.osakedata_db_path` using grouped SQL.
5. Python-side market filtering keeps only tickers whose grouped `market` matches the selected market.
6. For each ticker, the latest stored date is compared to today to decide whether update is needed.
7. Missing Yahoo data is fetched directly with `yf.Ticker(ticker).history(...)`.
8. Only new dates are inserted into `osakedata`.
9. Splits are synchronized by `stock.splits.sync_splits_for_ticker(...)`.
10. Additional split correction may refetch prices from 2018 onward through `_maybe_backfill_splits_for_ticker(...)`.
11. Divergences are updated by `_calculate_and_save_divergences(...)`.
12. Candlestick analysis is updated by `_run_incremental_candlestick_analysis(...)` only if new OHLCV rows were added.
13. After the full batch, Dow structures are updated by `analysis.stock_dow_structure.calculate_missing_or_outdated_stock_dow_structures(...)`.
14. UI reports progress and completion through `self.loading_text`, button disabling/enabling, and `self.page.update()`.

## 11. Extraction notes for future service layer

### Parts that look like pure update / business logic

- grouped ticker selection from `osakedata`
- incremental date-range decision per ticker
- Yahoo OHLCV fetch orchestration
- DB insert of missing OHLCV rows
- split sync call orchestration
- divergence/candlestick/Dow downstream orchestration
- summary counting (`updated_count`, `skipped_count`, `error_count`)

### Parts that are UI-specific and should remain in the UI layer

- `self.loading_text.value`
- `self.loading_text.color`
- `self.page.update()`
- `self.update_stock_button.disabled`
- reading widget values directly from:
  - `self.update_market_dropdown`
  - `self.update_start_input`

### Likely candidates to move into a future `stock_update_service.py`

- main per-ticker update loop currently in `RawCandleApp.update_stock_data()`
- ticker selection SQL + market filtering logic
- date range generation logic
- OHLCV write logic
- orchestration of:
  - `sync_splits_for_ticker(...)`
  - `_maybe_backfill_splits_for_ticker(...)`
  - `_calculate_and_save_divergences(...)`
  - `_run_incremental_candlestick_analysis(...)`
  - final `calculate_missing_or_outdated_stock_dow_structures(...)`

### Risks / unclear areas before refactoring

- Current method mixes:
  - OHLCV update
  - split correction
  - quarter detection
  - downstream analysis
  - UI state mutation
- `_calculate_and_save_divergences()` does not use `self.analysis_db_path` directly; it reconstructs paths under `data/`
- Final Dow batch path also reconstructs paths under `data/`
- `_maybe_backfill_splits_for_ticker()` may delete historical prices and analysis rows, so it is not a small side effect
- Current market filtering is done after grouped SQL, not in SQL
- Current method does not use a background thread, so extracting it may change UI responsiveness unless the caller keeps the current execution model
- UNCLEAR:
  - whether quarter-state side effects are considered part of “stock update” contract or incidental extra behavior
  - whether future service extraction should preserve the hardcoded `data/...` helper paths exactly or normalize everything through explicit parameters
