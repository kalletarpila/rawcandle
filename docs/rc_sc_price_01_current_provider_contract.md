# RC-SC-PRICE-01: current RawCandle provider contract

Study date: 2026-11-01, Europe/Helsinki. Investigation only; no provider, scheduler,
database or analysis changes. See [compatibility](rc_sc_price_01_stockcore_data_compatibility.md),
[plan](rc_sc_price_01_implementation_plan.md) and [evidence](rc_sc_price_01_acceptance_evidence.md).

## Repository and authority

RawCandle inspected HEAD: `4d06c793cb6d1feb6120473955f7da2c9d4b500b`, branch
`chore/ignore-backups`, one worktree `/home/kalle/projects/rawcandle`.
StockCore inspected HEAD: `20d3cdcddf82fdfac29ae652219fd1725eea4b7b`, branch
`main`, one worktree `/home/kalle/projects/stockcore`, strictly read-only.
No applicable RawCandle/ancestor AGENTS.md was found. StockCore's AGENTS.md was
read, including its Source ownership, Ordinary-default, Temp, scoped hold, external
consumer activation and focused-test rules. Relevant architecture §6/P02 and
Q02/Q03/Q06/Q08/Q23/consumer acceptance-map sections were read; later implemented
Source contracts supersede historical planning statements. No identity handoff,
G-CONSUMERS activation or mathematical change is implied by this study.

## Actual scheduled path

The installed user unit `/home/kalle/.config/systemd/user/stock-update-scheduler.service`
contains:

```text
WorkingDirectory=/home/kalle/projects/rawcandle
Environment=PYTHONPATH=/home/kalle/projects/rawcandle
ExecStart=/usr/bin/python3 /home/kalle/projects/rawcandle/rawcandle/cli/run_stock_update_scheduler.py --config /home/kalle/projects/rawcandle/scheduler_config.json
```

The unit description still says omxh + omxs; the actual config enables **omxh,
usa**, in that order. The timer file and JSON currently say **04:30**. JSON timezone
is Europe/Helsinki; the installed `OnCalendar` has no explicit timezone suffix.
The host timer's loaded/enabled/active state was not queried. These files were only
read. The user's 04:30/06:30 examples are not installed by this task.

Execution:

1. `rawcandle/cli/run_stock_update_scheduler.py:main` calls
   `rawcandle/scheduler/runner.py:run_scheduler_config` (line 2378).
2. Runner reads/validates config, acquires running-job exclusion, honors skip-next,
   takes host-local `today` and `_today_exclusive_end_date()`, and sequentially calls
   `_run_one_market` (line 2299) for each enabled market.
3. `_build_app` constructs an uninitialized `RawCandleApp` with configured paths;
   `_run_one_market` calls `app._run_stock_update_via_service` (runner line 2319).
4. `main.py:_run_stock_update_via_service` (line 352) builds adapters using
   `_build_stock_update_service_adapters` (line 299) and injects callbacks into
   `services/stock_update_service.py:run_stock_data_update` (line 1068).
5. `stock_factory(ticker)` is `yf.Ticker(ticker)`. Batch invokes
   `execute_ticker_update_flow` → `execute_ticker_ohlcv_update_plan` →
   `fetch_history_for_date_ranges` → **`stock.history(start=..., end=...)`** (line 579).

`rawcandle/cli/run_scheduled_stock_update.py` is a manually runnable service CLI;
despite its name, it is **not** the installed timer entrypoint.

## Universe and dates

`load_grouped_stock_update_candidates` groups **existing osakedata rows** by ticker:
`MIN(pvm), MAX(pvm), MAX(market)`. It does not use a UI watchlist, Fundamentals
active universe or StockCore membership. It groups across markets first, then
filters `(market or '').strip().lower()`. Preserve that behavior; do not silently
replace it with security-master membership. A mixed-market ticker would inherit
lexical MAX(market), a legacy limitation.

`plan_ticker_update` skips `last_date >= today` as `already_current`. Otherwise:

```text
start = max(last_date + one calendar day, optional start_override)
end   = fetch_until_exclusive = host-local today + one calendar day
```

The scheduled call supplies no start override. **There is no daily overlap window.**
The override cannot force an earlier overlap either. A range longer than 730 calendar
days is divided into contiguous 365-day half-open chunks; shorter ranges use one
call. Weekends can therefore cause a fetch returning no rows despite needs_update.
`expected_dates` defaults to empty; fallback is disabled by default and the app does
not supply a recovery callback. StockCore's six-session overlap is an acquisition
contract of StockCore, not RawCandle's requested range.

## Effective Yahoo output

Both the installed service interpreter `/usr/bin/python3` and repo `venv/bin/python`
have yfinance **0.2.66**, pandas **2.3.3**. The service imports yfinance from
`/home/kalle/.local/lib/python3.10/site-packages/yfinance`; requirements only says
`yfinance>=0.2.60`, so recheck before implementation. No network call was made.

| Parameter | Effective value in installed PriceHistory.history |
| --- | --- |
| period / interval | None / 1d |
| auto_adjust | True (implicit library default) |
| back_adjust / repair | False / False |
| actions | True |
| prepost / keepna / rounding | False / False / False |
| timeout / raise_errors | 10 seconds / False |

`yfinance.utils.auto_adjust` computes the float ratio `Adj Close / Close`, multiplies
**Open, High, Low** by it, and assigns **Close = Adj Close** directly. Volume is
not multiplied by this dividend factor. Yahoo ordinary historical prices are already
generally split-adjusted; neither path multiplies historical OHLC by split ratios.
`back_adjust` does not execute. Repair is off. Library cleanup fills missing volume
with zero and converts to int64; rounding is disabled. `keepna=False` removes rows
whose retained price/volume/action fields are all zero or missing. Repeated timestamps
are removed by yfinance before this return. Returned daily timestamps use the exchange
timezone, with index name Date; ETF/fund frames can include Capital Gains.

The consumer's minimal contract is a single-instrument DataFrame with a date-like
index supporting `strftime('%Y-%m-%d')`, `empty`, `iterrows()`, and named columns
**Open, High, Low, Close, Volume**. It accesses by name, not position; extra action
columns are ignored by conversion. Conventional output order is those five columns,
then Dividends, Stock Splits and optional Capital Gains; Adj Close is removed by
auto_adjust. OHLC become Python float, volume Python int or None, session ISO date,
and the selected RC market is attached. Noncomplete OHLC rows are discarded; the
RC converter itself does not comprehensively reject infinities, negative prices
or invalid units. The bridge must qualify those before returning a frame.

There is no retained price-basis/vintage field in RC osakedata. Current code establishes
the ingestion expectation, not a proof every historical row had the same basis or
capture vintage. Stored overlap comparisons show differences; see compatibility.

## Writes, no new rows and downstream behavior

`insert_missing_ohlcv_rows` loads existing dates for the ticker and inserts only
missing dates; it never updates changed values on an existing date. The local table
has UNIQUE index `idx_osake_pvm(osake,pvm)`. The in-memory date set also prevents
duplicate input dates in one call. First input occurrence wins. There is no numeric
unchanged-row comparison and no source-revision reconciliation.

| Input/result | Current behavior |
| --- | --- |
| already_current | No stock construction/history call; ticker skipped |
| empty/None/all incomplete OHLC | Zero converted rows; `no_history_data`; no per-ticker downstream |
| nonempty history, all dates already stored | Zero inserts, but ticker counts updated; split sync/backfill and divergence still run |
| one or more inserted rows | Split sync/backfill, divergence, incremental candlesticks |
| exception | Batch catches per ticker, records failure, continues |

`execute_ticker_downstream_updates` first synchronizes splits, then calls possible
split backfill. If backfill recomputed, incremental divergence is skipped; otherwise
divergence runs with only_missing=True, even when inserts are zero. Candlesticks
require positive inserts and receive the requested date range, not just inserted
dates. Final market Dow calculation runs after the batch **even if every ticker
was skipped**, followed by existing scheduler technical-relevance/DC/EC/Fundamentals
poststeps as configured. A provider adapter cannot promise zero market-level analysis
on a no-data run without changing existing behavior.

The proposed history method must enforce its requested half-open interval. Existing
SC rows older than start should produce an empty frame; returning overlap merely to
exercise duplicate handling would change downstream triggers.

## Split side effects: central safety constraint

`stock/splits.py:fetch_splits_for_ticker` accesses the supplied object's **`.splits`**;
omitting that property can yield a swallowed warning/empty result. Default Yahoo
splits access can load max history. `sync_splits_for_ticker` writes new dates using
INSERT OR IGNORE, marking new splits uncorrected; revised ratios on an existing date
are not corrected by this writer.

`main.py:_maybe_backfill_splits_for_ticker` (line 221) checks uncorrected RC splits,
then **deletes and commits all RC prices since 2018 before refetching from Yahoo**
via `analysis/splits_price_backfill.py:refetch_prices_from_yahoo`. It also cleans and
recomputes analyses. That refetch constructs a new `yf.Ticker`, independent of the
injected factory. Merely adding `.splits` does not solve this path. This study ran
none of those operations. A scheduled bridge must withhold a ticker before insertion
if split reconciliation would reach this path. New/revised splits cannot safely be
supported under the current no-history-rewrite constraint.

There is no analogous dividend-ledger synchronization in this service path;
dividends affect auto-adjusted prices. Existing historical dividend factors are not
refreshed by the ordinary daily append.

## Errors, counters, logs and exclusion

Existing summaries report checked/updated/skipped/failed tickers, inserted OHLCV,
fallback counters, splits_synced, divergences_updated, candlesticks_updated, Dow,
warning/error counts and status. The service currently returns **zero placeholders**
for splits_synced/divergences_updated/candlesticks_updated rather than aggregating
the actual callback outcomes. `progress_callback` is accepted but not used in the
inspected service implementation. Do not interpret these fields as import evidence.
Per-market logs contain SUMMARY lines and formatted UI summary; runner also writes
run JSON/status and separate poststep logs. A bridge needs bounded reason counts
and dependency/cutoff evidence in the existing scheduler log boundary.

History-range pause is 0.1s; successful ticker pause 0.25s, skipped/error 0.1s,
every 500 tickers 5s. Leave these service timings unchanged for the temporary bridge.
There is no application retry loop around history. Split-sync errors become warnings;
other ticker errors reach the batch failure catch. Any failed ticker yields
OK_WITH_WARNINGS; the scheduler CLI exits zero only for overall OK.

Runner's exclusion is a nonblocking exclusive flock on
`logs/stock_update_scheduler.lock`. Current FULL_WORKFLOW mode additionally enters
Fundamentals production_lock, which also acquires that scheduler lock. Selected UI
price operations use a different `stock_update_operation_lock`; do not assume the
scheduler lock excludes every manual mutation. StockCore's existing daily Source
owner takes a shared flock on this very scheduler lock for acquisition. Details
and the resulting concurrent-run blocker are in the plan.

## Narrow substitution point and manual isolation

The substitution seam is **`runner._run_one_market`**'s call to
**`RawCandleApp._run_stock_update_via_service`**. The runner is also called by the
scheduler UI's Run now button (`dev_tools/stock_update_scheduler_ui.py`, line 1435),
so an unconditional change there would affect a manual UI action. Select the
StockCore factory explicitly from the installed **run_stock_update_scheduler.py:main**
entrypoint, passing an optional per-run adapter factory through run_scheduler_config
and _run_one_market. Default runner/UI calls retain Yahoo. Add an optional per-call
adapter dictionary at the app method if needed; preserve its default builder.
Override only the explicit scheduled entrypoint's factory and required safety guards.
Do not change `main.yf`, `_build_stock_update_service_adapters`' default factory,
the generic history helper or environment-wide provider settings.

Manual UI legacy history loops (e.g. main.py line 3056 and later update paths), UI
service opt-in, scheduler UI Run now's default call, missing-day recovery's shared
builder, manual service CLI, forecast and Fundamentals acquisition must retain
Yahoo and their existing callbacks. A person directly invoking the installed scheduler
CLI would invoke the same selected workflow as the timer; no origin guess is made.
The study changes only these four documents, so isolation is currently structural;
future scheduled wiring requires explicit regression tests.
