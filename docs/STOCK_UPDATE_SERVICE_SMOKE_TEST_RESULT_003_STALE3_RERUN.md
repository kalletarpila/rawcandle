# STOCK_UPDATE_SERVICE_SMOKE_TEST_RESULT_003_STALE3_RERUN

This document records the stale3 rerun result after the Dow `rows_inserted` summary mapping fix and defines the next controlled UI opt-in test plan.

Source of truth:

- [docs/STOCK_UPDATE_SERVICE_SMOKE_TEST_PLAN.md](/home/kalle/projects/rawcandle/docs/STOCK_UPDATE_SERVICE_SMOKE_TEST_PLAN.md)
- [docs/STOCK_UPDATE_SERVICE_SMOKE_TEST_RESULT_002_STALE3.md](/home/kalle/projects/rawcandle/docs/STOCK_UPDATE_SERVICE_SMOKE_TEST_RESULT_002_STALE3.md)
- [docs/STOCK_UPDATE_SERVICE_CONTRACT.md](/home/kalle/projects/rawcandle/docs/STOCK_UPDATE_SERVICE_CONTRACT.md)
- [docs/STOCK_UPDATE_DOWNSTREAM_ADAPTER_CONTRACT.md](/home/kalle/projects/rawcandle/docs/STOCK_UPDATE_DOWNSTREAM_ADAPTER_CONTRACT.md)

## Purpose of rerun

The purpose of this rerun was to verify that the small `rows_inserted` to `dow_structures_updated` summary mapping fix changed only the visible Dow summary projection and did not change the rest of the stale3 smoke-test behavior.

## Prior issue

In the earlier stale3 smoke test:

- the real Dow summary contained `rows_inserted`
- but `SUMMARY dow_structures_updated` was empty

This happened because the service summary mapping only looked for:

- `updated`
- `inserted`

and did not map:

- `rows_inserted`

## Mapping fix summary

Current intended mapping behavior:

1. use `dow_summary["updated"]` if present
2. else use `dow_summary["inserted"]` if present
3. else use `dow_summary["rows_inserted"]` if present
4. else leave `dow_structures_updated` empty / `None`

This does not map:

- `rows_deleted`
- `tickers_processed`
- `tickers_outdated`

## Rerun SUMMARY output

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
SUMMARY dow_structures_updated=621
SUMMARY warnings=0
SUMMARY errors=0
SUMMARY status=OK
```

## UI-style summary observation

Observed UI-style formatted summary included:

- `Dow-rakenteet päivitetty: 621`

This confirms the visible summary field now reflects the Dow `rows_inserted` value in this stale3 rerun.

## Post-run SQL / check conclusions

Observed after the rerun:

- copied OMXH row count returned to `189944`
- duplicate `osake+pvm` query returned no rows

This means:

- missing OMXH OHLCV rows were restored
- no duplicate OHLCV rows were introduced

## Interpretation

The rerun confirms:

- the `rows_inserted` mapping change worked as intended
- visible Dow summary behavior improved
- the rest of the stale3 smoke-test result stayed effectively the same

Stale3 rerun expectations were met:

- `SUMMARY ohlcv_rows_inserted=294`
- `SUMMARY dow_structures_updated=621`
- `SUMMARY status=OK`
- no duplicates

Recommendation from this rerun:

- proceed to a controlled UI opt-in test
- do not make the service path default yet

## Controlled UI opt-in test plan

Purpose:

- verify that the actual UI wrapper path works when `_use_stock_update_service=True`
- verify `loading_text` and button state restore correctly
- verify the update button can still call `update_stock_data(...)`, which delegates only under explicit opt-in
- verify copied DBs are used
- verify the legacy default path is still available by leaving `_use_stock_update_service` unset or `False`

## UI opt-in test safety checklist

- use copied `osakedata.db` and `analysis.db`
- set `app.osakedata_db_path` to copied `osakedata.db`
- set `app.analysis_db_path` to copied `analysis.db`
- set `app.data_dir` to the copied data directory
- set `app._use_stock_update_service = True` only for the controlled test
- do not add a visible UI toggle yet
- do not make the flag default `True`
- run only one update at a time
- back up / copy data before the test

## Expected UI opt-in behavior

- `update_stock_data(...)` is still the button handler
- with `_use_stock_update_service=True`, `update_stock_data(...)` delegates immediately to `_update_stock_data_via_service_ui_flow(...)`
- the service UI flow uses `_run_stock_update_via_service(...)`
- `loading_text` eventually contains the formatted service result
- `update_stock_button.disabled` is restored to `False`
- `_stock_update_in_progress` is restored to `False`
- errors are shown in `loading_text` rather than escaping to the UI loop

## Before/after checks for UI opt-in test

Use the same key SQL checks as in the service smoke plan:

- row count by market
- latest `pvm` per OMXH ticker
- duplicate `osake+pvm` check
- optional Dow structure status / event check if relevant

Do not invent new schema checks for this stage.

## Pass/fail criteria

Pass if:

- UI opt-in path completes without uncaught exception
- copied OMXH row count is restored after stale data test
- duplicate check returns no rows
- `loading_text` shows the expected summary
- button disabled state is restored
- `_stock_update_in_progress` is `False` after completion
- service path remains opt-in only

Fail if:

- uncaught exception reaches the UI test harness
- copied DB row counts are inconsistent
- duplicates appear
- button remains disabled
- `_stock_update_in_progress` remains `True`
- service path becomes default unintentionally

## Recommended next implementation step

Add a developer-only UI opt-in smoke harness or manual test instructions that instantiate or drive `RawCandleApp` with copied DB paths and `_use_stock_update_service=True`, without changing default UI behavior.
