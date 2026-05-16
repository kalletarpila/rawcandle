# STOCK_UPDATE_SERVICE_SMOKE_TEST_PLAN

This document defines a deterministic smoke-test and parity-check plan for validating the service-based stock update path before making it the default.

Source of truth:

- [docs/STOCK_UPDATE_CURRENT_FLOW.md](/home/kalle/projects/rawcandle/docs/STOCK_UPDATE_CURRENT_FLOW.md)
- [docs/STOCK_UPDATE_SERVICE_CONTRACT.md](/home/kalle/projects/rawcandle/docs/STOCK_UPDATE_SERVICE_CONTRACT.md)
- [docs/STOCK_UPDATE_DOWNSTREAM_ADAPTER_CONTRACT.md](/home/kalle/projects/rawcandle/docs/STOCK_UPDATE_DOWNSTREAM_ADAPTER_CONTRACT.md)

This step does not change runtime behavior.
This step does not make the service path default.

## Current state

- Legacy `RawCandleApp.update_stock_data(...)` is still the default path.
- The service path is opt-in through `_use_stock_update_service=True`.
- The update button `on_click` still points to `self.update_stock_data`.
- The service path should only be used manually or in controlled tests for now.

## Smoke-test objective

The smoke-test objective is to verify that the service path:

- resolves market the same way
- loads the same ticker universe
- fetches missing Yahoo OHLCV data
- writes OHLCV rows correctly
- runs split sync
- runs split correction behavior when applicable
- runs divergence update
- runs candlestick update when rows are inserted
- runs final batch Dow update
- reports warnings/errors without crashing the UI wrapper

## Pre-test safety checklist

- Back up `osakedata.db`.
- Back up `analysis.db`.
- Use a small controlled market/ticker set if possible.
- Prefer a copy of the `data/` directory for the first test.
- Record current row counts before running.
- Record latest `pvm` per test ticker before running.
- Ensure no other stock update is running.
- Use only one test run at a time.

## Suggested first smoke test

Recommended first smoke test:

- one market only
- one or a few tickers only if the current app/test setup allows narrowing
- otherwise use a copied database with only a few tickers
- choose tickers where the latest stored `pvm` is intentionally behind the current date
- avoid split-backfill edge cases in the very first smoke test

Important:

- Do not invent a new ticker-filter feature for this test.
- If the current service path cannot narrow to one ticker, the safe way is to test on a copied database with a small ticker universe.

## Before/after SQL checks

Run these checks before and after a smoke test.

### A. Latest OHLCV date per ticker

```sql
SELECT osake, MAX(pvm) AS latest_pvm, COUNT(*) AS rows
FROM osakedata
WHERE market = '<MARKET>'
GROUP BY osake
ORDER BY osake;
```

### B. Row count by market

```sql
SELECT market, COUNT(*) AS rows
FROM osakedata
GROUP BY market
ORDER BY market;
```

### C. Recent rows for ticker

```sql
SELECT osake, pvm, open, high, low, close, volume, market
FROM osakedata
WHERE osake = '<TICKER>'
ORDER BY pvm DESC
LIMIT 10;
```

### D. Duplicate check

```sql
SELECT osake, pvm, COUNT(*) AS cnt
FROM osakedata
GROUP BY osake, pvm
HAVING COUNT(*) > 1
ORDER BY osake, pvm;
```

Analysis-table clarification:

- Only include analysis-table SQL checks when the exact table names are directly verifiable from current code or schema references.
- Do not infer table names from helper names or assumptions.
- If exact table names are not directly confirmed, mark them as `UNCLEAR`.

### E. Divergence rows for ticker

Exact table name directly confirmed from current code: `divergence_data`.

```sql
SELECT ticker, date
FROM divergence_data
WHERE ticker = '<TICKER>'
ORDER BY date DESC
LIMIT 20;
```

### F. Candlestick / findings rows for ticker

Exact table name directly confirmed from current code: `analysis_findings`.

```sql
SELECT ticker, date, pattern, signal_strength, rsi14
FROM analysis_findings
WHERE ticker = '<TICKER>'
ORDER BY date DESC, pattern
LIMIT 20;
```

### G. Dow structure events for ticker

Exact table name directly confirmed from current code: `stock_dow_structure_events`.

```sql
SELECT ticker, event_date, event_type, confirmed_as_of_date
FROM stock_dow_structure_events
WHERE ticker = '<TICKER>'
ORDER BY event_date DESC
LIMIT 20;
```

### H. Dow structure status for market

Exact table name directly confirmed from current code: `stock_dow_structure_status`.

```sql
SELECT ticker, market, calculated_through_date, calc_version
FROM stock_dow_structure_status
WHERE market = '<MARKET>'
ORDER BY ticker
LIMIT 50;
```

### I. UNCLEAR areas

- `results_data` is referenced in split-cleanup helper paths, but it is not part of the primary smoke-test checks here.
- If a smoke test specifically needs `results_data`, confirm its exact schema/table role separately first.

## Expected result patterns

- already-current tickers should be skipped
- tickers with missing newer data should get new OHLCV rows
- all-empty Yahoo responses should skip downstream
- non-empty history with no new inserts may still run split/divergence downstream
- candlestick should run only when OHLCV rows were inserted
- Dow should run after the ticker loop
- Dow failure should appear as warning, not a fatal crash
- the service path should not leave `_stock_update_in_progress=True` after completion

## Parity checklist

Use this checklist when comparing service-path behavior to the legacy flow:

- default market behavior
- market filtering behavior
- start override behavior
- `today` / `fetch_until_exclusive` behavior
- Yahoo date range behavior
- OHLCV insert / duplicate behavior
- split sync behavior
- split backfill behavior
- divergence behavior
- candlestick behavior
- Dow behavior
- warning/error behavior
- UI completion message behavior

## Rollback procedure

- Because `_use_stock_update_service` defaults to `False`, removing or not setting the flag keeps legacy behavior.
- Restore backed-up `osakedata.db` and `analysis.db` if the smoke test modified real data unexpectedly.
- Do not make the service path default until parity checks pass.

## Recommended next implementation step

Add a controlled developer-only smoke runner or test harness that can run the service path against a copied database and a small ticker universe, without changing default UI behavior.
