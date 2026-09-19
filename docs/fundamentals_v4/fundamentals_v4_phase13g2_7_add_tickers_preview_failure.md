# Phase 13G.2.7 - Add Tickers Preview failure and failed-run reporting

## 1. Outcome

Phase 13G.2.7 succeeded. The original failure was recovered, the 25-ticker run limit is now validated before source resolution, failed runs produce durable reports, and the separate UI input-state defect is covered.

## 2. Original failed run

- Run ID: `20260919T082307Z_add_tickers_724afde5dd5b`
- Requested count: 39, consisting of 36 retained symbols plus the newly entered `STM`, `TECK`, and `TEM`
- Recorded failure stage: `SOURCE_RESOLUTION`
- Exception: `ValueError: PHASE13D_TOO_MANY_TICKERS`
- Start/end: `2026-09-19T08:23:07Z` / `2026-09-19T08:23:32Z`
- The run copied databases for Preview but never crossed a write boundary. No production database write occurred.
- The surviving request, error, traceback, progress, status, and heartbeat artifacts were captured before any retry.
- Recovered `result.json` and `operation_report.md` now make the original run visible and downloadable in normal Administration history.

## 3. Root cause

No ticker-specific source lookup ran. The backend received 39 symbols and the Phase 13D compatibility parser rejected the request at its explicit maximum of 25. The UI had retained the previous completed Add Tickers batch while displaying the newly edited three-symbol value, so the submitted request did not match the operator-visible scope.

`STM`, `TECK`, and `TEM` were not the cause. Targeted read-only inspection found one unambiguous active provider identity for each, USA price history, complete `ticker_meta` classification, no existing canonical identity, and verified archive fundamentals.

## 4. Source-resolution fix

One Administration run remains limited to 25 normalized tickers. Add Tickers now validates that limit in `PREVIEW_VALIDATION`, before copy-lane creation and `SOURCE_RESOLUTION`. A 26+ request returns a durable `FAILED` Preview with the user message: `Preview accepts at most 25 tickers. Shorten the list and try again.` The legacy Phase 13D guard remains unchanged as defense in depth; requests are not automatically chunked.

## 5. Batch semantics

Normal ticker data outcomes remain item-level results. Missing provider rows or identity evidence produce `REVIEW_REQUIRED`/`REJECTED` for that ticker while the rest of the batch continues. Provider timeout, malformed response, or another unexpected backend exception remains an operation-level `FAILED` outcome with retained technical evidence.

## 6. Failed-run evidence architecture

The run directory, request, progress stream, and status exist before validation and source resolution. Add Tickers Preview now catches both copy-lane preparation and source-resolution failures, records `error.json`, writes terminal `result.json`, creates `operation_report.md`, updates the manifest, records an exit code, and cleans any copy lane. `AdminRunWriter.write_manifest()` also guarantees a report for every finalized Administration result that does not already have one.

## 7. UI changes

- Add Tickers guidance states the 1-25 ticker limit.
- Failed Preview keeps the concise failed progress event and shows a visible Final summary.
- Technical details include run ID, operation, mode, failure stage, exception type/message, artifact directory, and report SHA-256.
- Failed report download is available both for the current result and its Run history row.
- The original row now reads `Add Tickers | Preview | Failed | 39 items | Administration run`.
- The current editable ticker value is submitted exactly. The batch remains stable through Preview, Test on copies, and Production update, then the field is cleared after a successful Add Tickers Production update.

## 8. Failed report

The report contains Executive Summary, Requested Inputs, Failure, Database Safety, Completed Work, Actions Performed, Downstream Impact, Final Result, and Technical Appendix. The final recovered report SHA-256 is `5abb88ebe62e77968b21dd95355c17bdb223955bc06cb78b52add2248473a521`.

## 9. STM / TECK / TEM rerun

Preview-only run: `20260919T084727Z_add_tickers_c8719229e2aa`.

| Ticker | Result | Identity | Market/classification | Fundamentals |
| --- | --- | --- | --- | --- |
| STM | `ELIGIBLE` | STMicroelectronics NV, NYSE ADR, permaticker 190148, unambiguous | USA; Technology / Semiconductors | verified archive, 186 rows / 42 ARQ |
| TECK | `ELIGIBLE` | Teck Resources Ltd, NYSE Canadian common stock, permaticker 124615, unambiguous | USA; Basic Materials / Other Industrial Metals & Mining | verified archive, 211 rows / 50 ARQ |
| TEM | `ELIGIBLE` | Tempus AI Inc, NASDAQ domestic common stock, permaticker 641935, unambiguous | USA; Healthcare / Health Information Services | verified archive, 58 rows / 11 ARQ |

Provider network was allowed but made zero requests. Preview fingerprint: `2770e33e528249bc8069a84542ed2e4e3f6b0e16ad8398013033b019bbfd7114`.

## 10. Tests

- `pytest -q tests/test_fundamentals_admin_batch_add_tickers.py tests/test_fundamentals_admin_ui.py`: 63 passed, 0 skipped, 0 failed.
- `pytest -q tests/test_fundamentals_admin_*.py`: 170 passed, 0 skipped, 0 failed.
- Focused five-test run for the new failure, limit, exact tickers, report/UI, and input reset contracts: 5 passed.

## 11. Safety

No Test on copies or Production update was executed for `STM`, `TECK`, or `TEM`. Pre/post SHA-256 values were identical for provider `5eb5b258...`, canonical `90c7b375...`, analysis `fedbb50a...`, market `2eccf090...`, and taxonomy `c7625e28...`. No taxonomy or market write occurred.

## 12. Cleanup

The new Preview copy lane was removed by the backend. Only the phase-owned empty temp parents for the original failed run and the successful rerun were removed. Durable request/result/error/progress/report/manifest evidence was retained. Production rollback backups were untouched.

## 13. Remaining issues

None material for Preview. `STM`, `TECK`, and `TEM` are only Preview-eligible; they have not been tested on copies or added to production.

## 14. Git

The implementation, focused tests, and this closure report are committed together on `chore/ignore-backups`. No push was performed.
