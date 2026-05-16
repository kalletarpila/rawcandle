# STOCK_UPDATE_SERVICE_SMOKE_TEST_RESULT_002_STALE3

This document records the stale-3-day service-path smoke test result and inspects summary/parity semantics before any default switch.

Source of truth:

- [docs/STOCK_UPDATE_CURRENT_FLOW.md](/home/kalle/projects/rawcandle/docs/STOCK_UPDATE_CURRENT_FLOW.md)
- [docs/STOCK_UPDATE_SERVICE_CONTRACT.md](/home/kalle/projects/rawcandle/docs/STOCK_UPDATE_SERVICE_CONTRACT.md)
- [docs/STOCK_UPDATE_DOWNSTREAM_ADAPTER_CONTRACT.md](/home/kalle/projects/rawcandle/docs/STOCK_UPDATE_DOWNSTREAM_ADAPTER_CONTRACT.md)
- [docs/STOCK_UPDATE_SERVICE_SMOKE_TEST_PLAN.md](/home/kalle/projects/rawcandle/docs/STOCK_UPDATE_SERVICE_SMOKE_TEST_PLAN.md)

## Smoke test setup

Copied databases used:

- `osakedata` copy:
  - `/home/kalle/projects/rawcandle/data_smoke_stale3/osakedata.db`
- `analysis` copy:
  - `/home/kalle/projects/rawcandle/data_smoke_stale3/analysis.db`

Market:

- `omxh`

Removed from copied `osakedata.db` before the run:

- `2026-05-15`
- `2026-05-13`
- `2026-05-12`

## Before smoke runner

Copied row counts before the service-path run:

- `omxh: 189650`
- `omxs: 570892`
- `usa: 7599523`

Observed latest `pvm` for the first OMXH tickers before the run:

- around `2026-05-11`

Example first rows before the run:

- `ACG1V.HE -> 2026-05-11`
- `AKTIA.HE -> 2026-05-11`
- `ALBBV.HE -> 2026-05-11`

## Command run

```bash
PYTHONPATH=. python3 dev_tools/run_stock_update_service_smoke.py \
  --osakedata-db /home/kalle/projects/rawcandle/data_smoke_stale3/osakedata.db \
  --analysis-db /home/kalle/projects/rawcandle/data_smoke_stale3/analysis.db \
  --market omxh
```

## Runner SUMMARY output

```text
SUMMARY market=omxh
SUMMARY tickers_checked=98
SUMMARY tickers_updated=98
SUMMARY tickers_skipped=0
SUMMARY tickers_failed=0
SUMMARY ohlcv_rows_inserted=294
SUMMARY splits_synced=0
SUMMARY divergences_updated=0
SUMMARY candlesticks_updated=0
SUMMARY dow_structures_updated=
SUMMARY warnings=0
SUMMARY errors=0
SUMMARY status=OK
```

## UI-style Dow summary

Observed from the UI-style formatted result:

- `rows_inserted=621`
- `rows_deleted=603`
- `tickers_processed=54`
- `tickers_outdated=54`

Full relevant Dow summary pattern:

```text
Dow-yhteenveto: ... rows_deleted=603, rows_inserted=621, ... tickers_outdated=54, tickers_processed=54, ...
```

## After smoke runner

Copied row counts after the service-path run:

- `omxh: 189944`
- `omxs: 570892`
- `usa: 7599523`

Observed latest `pvm` for the first OMXH tickers after the run:

- back to `2026-05-15`

Duplicate check result:

- no duplicate `osake+pvm` rows were returned

Run completion:

- completed with `status=OK`
- no warnings
- no errors

## Interpretation

OHLCV behavior looks good in this stale-3-day test:

- removed OMXH rows were restored
- `SUMMARY ohlcv_rows_inserted=294`
- no duplicate `osake+pvm` rows were created

Dow behavior also looks active:

- Dow summary clearly shows non-zero `rows_inserted` and `rows_deleted`
- Dow processed outdated tickers in this run

However, summary semantics still require inspection before default switch:

- `SUMMARY dow_structures_updated` was empty even though Dow clearly changed rows
- `SUMMARY tickers_updated=98` needs comparison to the legacy counter meaning

Recommendation at this point:

- do not make the service path default yet until these summary/parity questions are inspected

## Legacy counter semantics inspection

Observed from `RawCandleApp.update_stock_data(...)` in [main.py](/home/kalle/projects/rawcandle/main.py).

### A. Ticker is already current before Yahoo fetch

- `updated_count`:
  - not incremented
- `skipped_count`:
  - incremented by `1`
- `error_count`:
  - not incremented
- downstream steps reached:
  - no
- candlestick reached:
  - no

### B. Yahoo returns all-empty history / no accumulated `all_hist`

- `updated_count`:
  - not incremented
- `skipped_count`:
  - incremented by `1`
- `error_count`:
  - not incremented
- downstream steps reached:
  - no
- candlestick reached:
  - no

Reason:

- after fetch, if `all_hist.empty`, legacy code does:
  - `skipped_count += 1`
  - `continue`

### C. Yahoo returns non-empty history but all rows already exist in `osakedata`, so `rows_added == 0`

- `updated_count`:
  - incremented by `1`
- `skipped_count`:
  - not incremented
- `error_count`:
  - not incremented
- downstream steps reached:
  - yes
- candlestick reached:
  - no

Reason:

- downstream split/divergence path still runs after the insert block
- candlestick block is guarded by `if rows_added > 0`
- `updated_count += 1` happens after downstream work regardless of `rows_added`

### D. Yahoo returns non-empty history and `rows_added > 0`

- `updated_count`:
  - incremented by `1`
- `skipped_count`:
  - not incremented
- `error_count`:
  - not incremented
- downstream steps reached:
  - yes
- candlestick reached:
  - yes

### E. Ticker raises an exception

- `updated_count`:
  - not incremented
- `skipped_count`:
  - not incremented in the exception branch itself
- `error_count`:
  - incremented by `1`
- downstream steps reached:
  - UNCLEAR in the abstract
  - practically depends on where the exception occurs
- candlestick reached:
  - UNCLEAR in the abstract
  - practically depends on where the exception occurs

Important nuance:

- the broad per-ticker `try/except` means an exception can happen:
  - before downstream
  - during downstream
  - during candlestick
- if the exception happens before reaching later stages, those later stages are not reached

## Service vs legacy counter parity

### Already-current tickers

- Legacy:
  - count as skipped
- Service:
  - `plan.needs_update=False` returns skipped
- Conclusion:
  - parity-compatible

### All-empty Yahoo history

- Legacy:
  - `skipped_count += 1`
  - downstream not reached
- Service:
  - `ohlcv_rows_converted == 0` becomes skipped with `skip_reason="no_history_data"`
  - downstream not reached
- Conclusion:
  - parity-compatible

### Zero-insert but non-empty history

- Legacy:
  - counts as updated
  - split/divergence downstream still runs
  - candlestick does not run
- Service:
  - counts as updated
  - downstream still runs
  - candlestick does not run because `ohlcv_rows_inserted == 0`
- Conclusion:
  - parity-compatible

### Stale copied DB test where OHLCV rows were inserted

- Legacy expectation:
  - each ticker with non-empty fetched history should count as updated
  - inserted rows should restore missing dates
- Service stale3 result:
  - `tickers_checked=98`
  - `tickers_updated=98`
  - `tickers_skipped=0`
  - `ohlcv_rows_inserted=294`
  - copied OMXH row count restored to original level
- Conclusion:
  - parity-compatible for the observed stale3 case

### Remaining parity risk

- Counter semantics themselves look compatible from code inspection
- The main remaining parity risk is not ticker counter logic
- The main remaining parity risk is summary/display semantics around Dow update totals

Overall conclusion:

- counter semantics: parity-compatible
- Dow summary projection: parity-risk

## Dow summary mapping inspection

Actual Dow summary keys observed in the stale3 smoke test:

- `rows_inserted`
- `rows_deleted`
- `tickers_processed`
- `tickers_outdated`

Current service mapping behavior in [services/stock_update_service.py](/home/kalle/projects/rawcandle/services/stock_update_service.py):

- if `dow_summary` contains key `updated`:
  - `dow_structures_updated = dow_summary["updated"]`
- else if `dow_summary` contains key `inserted`:
  - `dow_structures_updated = dow_summary["inserted"]`
- else:
  - `dow_structures_updated = None`

Current mapping does not handle:

- `rows_inserted`
- `rows_deleted`
- `tickers_processed`
- `tickers_outdated`

Why `SUMMARY dow_structures_updated` was empty:

- the stale3 Dow summary used `rows_inserted`
- the current service mapping only checks `updated` and `inserted`
- therefore `StockUpdateResult.dow_structures_updated` stayed `None`
- `format_stock_update_summary_lines(...)` renders that as an empty value

Assessment:

- this is a summary/display issue
- it is not evidence of a functional Dow update failure
- functional Dow behavior clearly occurred in the stale3 smoke test

Recommendation for later code change:

- a later small service-result mapping adjustment should likely map `rows_inserted` to `dow_structures_updated`
- `rows_deleted` should probably remain visible only in detailed summary, not be merged into `dow_structures_updated`

## Recommended next step

### B. Summary semantics need a small service-result mapping adjustment before more smoke tests

Reason:

- counter semantics look parity-compatible from both code inspection and the stale3 smoke test
- the remaining visible mismatch is the empty `SUMMARY dow_structures_updated` field even when Dow clearly inserted rows
- this is small and localized enough to fix before any wider UI opt-in smoke rollout
