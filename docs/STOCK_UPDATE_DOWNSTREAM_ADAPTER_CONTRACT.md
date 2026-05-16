# STOCK_UPDATE_DOWNSTREAM_ADAPTER_CONTRACT

This document defines the downstream side-effect adapter boundary needed before the future shared stock update service can preserve the current `Päivitä osaketiedot` behavior end-to-end.

Source of truth:

- [docs/STOCK_UPDATE_CURRENT_FLOW.md](/home/kalle/projects/rawcandle/docs/STOCK_UPDATE_CURRENT_FLOW.md)
- [docs/STOCK_UPDATE_SERVICE_CONTRACT.md](/home/kalle/projects/rawcandle/docs/STOCK_UPDATE_SERVICE_CONTRACT.md)

This step does not implement adapters.
This step does not move code.
This step does not modify `main.py`.

## 1. Purpose

The stock update service now has isolated helpers for:

- ticker selection
- date planning
- OHLCV row conversion
- history fetch orchestration
- OHLCV insert orchestration
- per-ticker OHLCV-only execution

However, the current UI flow also performs downstream side effects that are required for behavior parity:

- split sync
- possible split correction / historical backfill
- divergence update
- candlestick update
- final batch Dow structure update

These downstream side effects must later be called through a UI-independent adapter / port boundary so the future shared service can preserve the current flow without importing or depending on Flet/UI objects.

Clarification:

- quarter / fundamentals-related side effects are currently part of the overall update flow
- they are documented here as current-flow coupling / risk
- they are not treated as the primary downstream adapter boundary target in this document unless the current execution order clearly makes them part of the same downstream orchestration contract

## 2. Current downstream execution order

Observed from `RawCandleApp.update_stock_data()` in [main.py](/home/kalle/projects/rawcandle/main.py):

### Per ticker, after OHLCV fetch and insert block

1. split sync is attempted
2. split correction / backfill helper is called
3. divergence update is either:
   - skipped if split correction already recomputed divergence
   - or called normally with `only_missing=True`
4. candlestick analysis is called only if `rows_added > 0`
5. ticker-level success / warning UI message is constructed

### After the full ticker loop

6. final batch Dow structure update is attempted once

### Exact observed order in code

Inside the per-ticker `try` block, after OHLCV writes:

1. `sync_splits_for_ticker(db_path, ticker, yf_ticker=stock)`
2. `split_recomputed = self._maybe_backfill_splits_for_ticker(ticker)`
3. divergence path:
   - if `split_recomputed` is `True`:
     - `div_success, div_days, div_error = (True, 0, "")`
   - else:
     - `self._calculate_and_save_divergences(ticker, only_missing=True)`
4. if `rows_added > 0`:
   - `self._run_incremental_candlestick_analysis(ticker, analysis_start, analysis_end)`
5. after the loop:
   - `calculate_missing_or_outdated_stock_dow_structures(...)`

Nothing in the inspected code indicates that split/divergence/candlestick are run after the full loop. They are per-ticker.

## 3. Current downstream trigger conditions

### A. Split sync

Observed behavior:

- attempted for every ticker that reaches the post-insert part of the per-ticker `try` block
- attempted even if Yahoo returned only empty history and `rows_added == 0`, as long as the code reached the post-write area with an empty/non-empty `all_hist` path that did not early-continue
- not attempted for already-current skipped tickers
- not attempted for tickers that early-continue before the downstream section

Important nuance:

- if `all_hist.empty` after the Yahoo fetch stage, the code does:
  - `skipped_count += 1`
  - `continue`
- in that branch, split sync is not reached

Therefore the practical rule is:

- split sync is attempted for tickers that enter the per-ticker update path and produce a non-empty accumulated history object
- it is not attempted for already-current skipped tickers
- it is not attempted for all-empty-history tickers because that branch continues earlier

### B. Split correction / backfill

Observed behavior:

- called immediately after split sync
- current call:
  - `split_recomputed = self._maybe_backfill_splits_for_ticker(ticker)`
- return value controls later flow

If it returns `True`:

- normal divergence update is skipped
- code sets:
  - `div_success=True`
  - `div_days=0`
  - `div_error=""`

If it returns `False`:

- normal divergence update is called with:
  - `only_missing=True`

### C. Divergence update

Observed behavior:

- called after split correction
- current call:
  - `self._calculate_and_save_divergences(ticker, only_missing=True)`
- skipped only when split correction already recomputed divergence and returned `True`

### D. Candlestick update

Observed behavior:

- called only when `rows_added > 0`
- current call:
  - `self._run_incremental_candlestick_analysis(ticker, analysis_start, analysis_end)`
- start/end values passed:
  - `analysis_start = min(start for start, _ in date_ranges)`
  - `analysis_end = max(end for _, end in date_ranges)`

### E. Final batch Dow structure update

Observed behavior:

- called after the entire ticker loop finishes
- current call target:
  - `calculate_missing_or_outdated_stock_dow_structures(...)`
- market scope:
  - `selected_market.strip().lower() if selected_market else None`
- database paths used there are rebuilt as:
  - `data/osakedata.db`
  - `data/analysis.db`
- its summary is rendered into UI text after the stock-summary block

## 4. Current error handling semantics

### A. Split sync

Observed behavior:

- exceptions are caught locally in a dedicated `try/except`
- ticker processing continues
- warning printed:
  - `⚠️ Splittien päivitys epäonnistui ({ticker}): {exc}`

### B. Split correction / backfill

Observed behavior:

- `_maybe_backfill_splits_for_ticker(...)` catches exceptions internally
- failure does not mark the ticker as an outer ticker error by itself
- function prints warnings internally and returns falsey behavior in failure cases
- outer ticker flow continues

Important nuance:

- inspected helper also contains non-trivial side effects:
  - deletes prices from `2018-01-01`
  - refetches prices from Yahoo
  - deletes analysis rows
  - recomputes divergence
- exceptions inside that helper are swallowed there and converted into warning prints

### C. Divergence update

Observed behavior:

- `_calculate_and_save_divergences(...)` catches exceptions internally
- return on failure:
  - `(False, 0, error_message)`
- outer flow continues
- ticker still proceeds to later message construction

### D. Candlestick update

Observed behavior:

- exceptions are caught locally around the helper call
- ticker still counts as updated because `updated_count += 1` happens afterward regardless of `analysis_error`
- `analysis_error` is represented as a string
- UI ticker message appends:
  - `| analyysivirhe: <error>`

### E. Final batch Dow structure update

Observed behavior:

- failure is caught after the ticker loop
- the whole stock update still completes
- UI warning appended:
  - `⚠️ Dow-rakenteiden päivitys epäonnistui: ...`

The main stock summary remains shown even if Dow post-processing fails.

## 5. Existing function / method signatures

### `stock.splits.sync_splits_for_ticker(...)`

- File:
  - [stock/splits.py](/home/kalle/projects/rawcandle/stock/splits.py)
- Callable:
  - `sync_splits_for_ticker(db_path: Path | str, ticker: str, yf_ticker: Optional[yf.Ticker] = None) -> int`
- Parameters currently passed by `update_stock_data()`:
  - `db_path`
  - `ticker`
  - `yf_ticker=stock`
- Return shape:
  - integer insert count
- Uses `self`:
  - no
- Hardcoded paths:
  - no, DB path is passed in
- UI coupling:
  - none observed in this function
- Prints/logs:
  - not directly in `sync_splits_for_ticker(...)`, but callers print if insert count is non-zero

### `RawCandleApp._maybe_backfill_splits_for_ticker(...)`

- File:
  - [main.py](/home/kalle/projects/rawcandle/main.py)
- Callable:
  - `_maybe_backfill_splits_for_ticker(self, ticker: str)`
- Parameters currently passed by `update_stock_data()`:
  - `ticker`
- Return shape:
  - practical boolean-like result
  - returns `True` on successful split correction + divergence recompute
  - otherwise falsey
- Uses `self`:
  - yes
- Hardcoded paths:
  - partially
  - uses `self.osakedata_db_path`
  - builds `analysis_path = os.path.join(self.data_dir, "analysis.db")`
- UI coupling:
  - no direct Flet widget mutation observed in the inspected helper body
  - however the method belongs to `RawCandleApp`
- Prints/logs:
  - yes, multiple `print(...)` warnings and status lines

### `RawCandleApp._calculate_and_save_divergences(...)`

- File:
  - [main.py](/home/kalle/projects/rawcandle/main.py)
- Callable:
  - `_calculate_and_save_divergences(self, ticker: str, only_missing: bool = True) -> tuple`
- Parameters currently passed by `update_stock_data()`:
  - `ticker`
  - `only_missing=True`
- Return shape:
  - documented in method docstring as:
    - `(success: bool, days_calculated: int, error_message: str)`
- Uses `self`:
  - yes
- Hardcoded paths:
  - yes
  - rebuilds:
    - `data/osakedata.db`
    - `data/analysis.db`
- UI coupling:
  - no direct widget mutation inside the helper
- Prints/logs:
  - no direct print in the shown helper body

### `RawCandleApp._run_incremental_candlestick_analysis(...)`

- File:
  - [main.py](/home/kalle/projects/rawcandle/main.py)
- Callable:
  - `_run_incremental_candlestick_analysis(self, ticker: str, analysis_start: str, analysis_end: str) -> tuple[int, str | None]`
- Parameters currently passed by `update_stock_data()`:
  - `ticker`
  - `analysis_start`
  - `analysis_end`
- Return shape:
  - `(analysis_total: int, analysis_error: str | None)`
- Uses `self`:
  - yes
- Hardcoded paths:
  - no hardcoded `data/...` rebuilding in the shown helper
  - uses:
    - `self.osakedata_db_path`
    - `self.analysis_db_path`
- UI coupling:
  - no direct widget mutation inside the helper
- Prints/logs:
  - none observed in the shown helper body

### `analysis.stock_dow_structure.calculate_missing_or_outdated_stock_dow_structures(...)`

- File:
  - [analysis/stock_dow_structure.py](/home/kalle/projects/rawcandle/analysis/stock_dow_structure.py)
- Callable:
  - `calculate_missing_or_outdated_stock_dow_structures(*, analysis_db_path, osakedata_db_path, ticker=None, market=None, pivot_radius=..., bounded_initial_from_date=..., recalc_tail_trading_days=..., dry_run=False, run_id=None, created_at_utc=None) -> dict[str, int | str]`
- Parameters currently passed by `update_stock_data()`:
  - `analysis_db_path=_analysis_path`
  - `osakedata_db_path=_osakedata_path`
  - `market=_dow_market`
  - `pivot_radius=DEFAULT_PIVOT_RADIUS`
  - `bounded_initial_from_date=DEFAULT_BOUNDED_INITIAL_FROM_DATE`
  - `recalc_tail_trading_days=DEFAULT_RECALC_TAIL_TRADING_DAYS`
  - `dry_run=False`
- Return shape:
  - dict-like summary
- Uses `self`:
  - no
- Hardcoded paths:
  - the function itself accepts explicit paths
  - but `update_stock_data()` rebuilds `data/...` paths before calling it
- UI coupling:
  - none in the function signature
- Prints/logs:
  - UNCLEAR from the inspected snippet whether internal printing occurs

## 6. Proposed future adapter / port boundary

The future service should receive callable ports rather than import `RawCandleApp` or Flet.

Conceptual future ports:

- `sync_splits_for_ticker(ticker, stock) -> int` or warning/exception semantics matching current usage
- `maybe_backfill_splits_for_ticker(ticker) -> bool`
- `calculate_and_save_divergences(ticker, only_missing=True) -> tuple[bool, int, str]`
- `run_incremental_candlestick_analysis(ticker, analysis_start, analysis_end) -> tuple[int, str | None]`
- `calculate_missing_or_outdated_stock_dow_structures(...) -> dict[str, int | str]`

Important boundary requirements:

- service must not depend on `RawCandleApp`
- service must not depend on Flet widgets
- service must preserve current exception-catch / exception-propagation placement
- service must preserve current return-shape assumptions

UNCLEAR items that should not be silently fixed in adapter design:

- whether split sync adapter should return only count or a richer warning/result structure
- whether backfill adapter should keep exactly bool semantics or expose richer diagnostics
- whether divergence and candlestick adapters should preserve tuple shapes exactly or wrap them later

## 7. Future service orchestration notes

Likely future orchestration shape:

1. execute one ticker’s OHLCV update
2. preserve split sync behavior
3. preserve split correction behavior
4. preserve divergence behavior
5. preserve candlestick behavior
6. after the full ticker loop, preserve final batch Dow behavior
7. keep exception catching / propagation in the same places as current `main.py`
8. report warnings and errors through service result/progress structures rather than UI widgets

Important:

- split sync local exception catching must remain local if parity is required
- split correction internal swallow/print semantics must be preserved unless a later step explicitly changes them
- divergence failure remains helper-return-based, not outer-exception-based
- candlestick failure remains local-error-string-based, not ticker-fatal
- Dow failure remains post-loop warning behavior, not whole-run fatal behavior

## 8. Non-goals

- no downstream logic rewrite
- no change to split correction behavior
- no change to divergence calculation
- no change to candlestick analysis
- no change to Dow structure calculation
- no change to hardcoded helper paths yet
- no Flet dependency in service
- no CLI implementation
- no locking implementation
- no retry redesign
- no threading redesign

## 9. Risks and open questions

- split correction deletes and refetches historical data from `2018-01-01`
- hardcoded `data/osakedata.db` and `data/analysis.db` paths exist in helper methods / call sites
- quarter / fundamentals side effects are still mixed into the current update flow
- exact candlestick return/error shape is known at the helper signature level, but downstream aggregate semantics are still UNCLEAR
- exact divergence return shape is documented as tuple-like `(bool, int, str)`, but downstream aggregate semantics are still UNCLEAR
- split sync currently returns insert counts; whether the future adapter should preserve raw counts only or also capture warnings is UNCLEAR
- how to aggregate downstream counts into `StockUpdateResult` is UNCLEAR
- how to represent the Dow summary inside `StockUpdateResult` is still UNCLEAR
- whether `_maybe_backfill_splits_for_ticker(...)` should remain a method-shaped adapter or be wrapped into a pure callable boundary first is UNCLEAR
- the inspected `_maybe_backfill_splits_for_ticker(...)` body belongs to `RawCandleApp` and still carries application-context coupling

## 10. Recommended next implementation step

Recommended next safe step:

- **B. add a tested per-ticker downstream orchestration helper using fake callables**

Reason:

- the current downstream ordering and trigger conditions are now concrete enough
- helper signatures and return shapes are known well enough to fake in tests
- this allows the service layer to preserve downstream orchestration behavior without first moving existing `RawCandleApp` methods out of the UI class
- extracting helper bodies into standalone functions first would be a larger behavior-risk step than introducing callable ports around current behavior
