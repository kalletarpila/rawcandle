# Yahoo-only missing-day recovery

Updated 2026-10-14. This supersedes the original neighbor-anchor validation and collect-then-write design. The earlier HELD investigation remains historical evidence, not the current acceptance specification.

## Operator flow

The existing **Hae puuttuva päivä** controls retain one date, the existing market selector, **Hae puuttuvan päivän tiedot**, progress and a final summary. Choose a completed weekday and one market: USA, OMX Helsinki, OMX Stockholm or Xetra. No page redesign or production recovery was performed during implementation.

The ticker universe is exactly normal RawCandle's existing market selection: `load_stock_update_candidates_for_market`, grouping stored tickers with their first/last dates and `MAX(market)`. Equities, ETFs, indices and other existing instrument types are included. Fundamentals membership, active status, missing security-start metadata and adjacent-history quality are not eligibility gates. The tool does not expand the universe or qualify instruments for SetupMaster research.

For each ticker, an existing `(ticker, date)` key is skipped before Yahoo acquisition, regardless of market; an occupied key in another market is reported as held. Missing keys are checked again immediately before acquisition and inside the insert transaction. The progress denominator is all examined market tickers, not the Yahoo request count.

For a missing key, request just `[selected day, next day)` through the existing app `stock_factory`, `stock_update_service.fetch_history_for_date_ranges` and `convert_histories_to_ohlcv_rows`. There is no new downloader, batching implementation or provider fallback. History options remain the normal `stock.history(start=..., end=...)` defaults; no explicit adjustment transformation is introduced. Yahoo pacing/retries and normal daily collection are unchanged: the shared range pause and legacy ticker/batch sleeps are reused. A propagated `YFRateLimitError` stops subsequent requests without a new retry scheme.

A valid target is committed immediately. The operation does not wait to collect all accepted tickers. It never requests neighbors to approve an otherwise valid target, compares no adjacent prices/volumes and requires no following stored row. Missing or invalid stored anchors and uncorrected-split flags are not insertion gates.

## Target validation and identity

Only the selected date and market can be inserted. The converted row must retain the requested ticker and market; duplicate provider dates are rejected. The Yahoo metadata symbol must exactly match the ticker, and its exchange timezone must match the established market mapping (USA indices additionally allow Chicago, as documented below). Missing provider identity on a returned bar is reported as unverified, separately from a demonstrated mismatch. There is no `instrumentType=EQUITY` restriction. Metadata cannot independently distinguish every exchange or reused ticker; this is operational validation, not a point-in-time security master.

OHLC must be finite and positive, `low <= open <= high` and `low <= close <= high`; volume must be finite and nonnegative. The normal converter's numeric conventions are preserved, including integer volume conversion. A requested raw bar skipped by that converter for incomplete OHLC is reported as invalid, rather than as absent. Zero volume is accepted. No price interpolation, scaling or existing-history correction takes place.

Known identity protection uses only dated **APPROVED** records in the existing read-only `rawcandle/fundamentals/admin/identity_resolutions.json` registry. A successor ticker before its reviewed effective date, or a predecessor at/after that date, is held with the exact transition and supporting evidence in the report. No aliases are joined into continuity. Pending reviews and missing/undated metadata alone do not prove a conflict. Canonical Fundamentals databases are not opened by this recovery path. A returned bar contradicting a usable Yahoo `firstTradeDate` is held with that evidence; absence of the field is allowed. A malformed established registry fails the operation rather than silently ignoring known evidence.

The existing normal updater's split behavior is preserved: `main.RawCandleApp._maybe_backfill_splits_for_ticker` checks uncorrected splits, deletes/refetches history from 2018, recomputes analysis and marks successful corrections. Service adapters and legacy UI still invoke that path. Missing-day recovery neither calls it nor implements a second split-repair system. Consequently different adjustment vintages elsewhere in the database can remain; a successful missing-day insert is not certification of globally uniform historical adjustments.

## No-data diagnostics

If Yahoo returns no converted target bar, do not invent a row. Missing metadata in an empty response is allowed; an explicitly wrong symbol or market is held. Local dates within a maximum 14-calendar-day window are inspected. If they already bracket the target, report `NO_TRADING_DATA` without a further context request. Otherwise at most one diagnostic history request covers `[target - 6 days, target + 8 days)` (14 calendar dates, exclusive end).

Diagnostic reasons are `PRE_LISTING_POSSIBLE`, `POST_DELISTING_POSSIBLE`, `NO_TRADING_DATA` and `UNKNOWN`. One-sided nearby history or a provider first-trade hint can suggest a boundary, but does not establish an exchange-effective IPO/delisting date. No context bars are inserted. A target appearing only in the second, diagnostic response is reported `UNKNOWN`; restart can retrieve it through the normal one-day path. Invalid or absent context cannot justify synthetic continuity. A context retrieval failure is reported as a provider error, rather than inventing a classification.

There is no separate global calendar-index Yahoo probe or index-presence gate. Completed weekdays are checked up front; actual returned date and provider market identity constrain insertion. Holidays with no target bars remain diagnostic absences. Index and exchange calendars can differ, and this function is not an authoritative exchange-calendar service.

## Persistence, interruption and backups

The normal stock service already uses a per-ticker plain `INSERT` writer and commits incrementally, not UPSERT. Missing-day recovery keeps that pattern in its existing small insert-only adapter, adding `BEGIN IMMEDIATE` around the final key check and insert. Direct reuse of the normal helper would leave a separate-connection check/write race and would not enforce the selected date/market boundary; normal service code is therefore unchanged.

A unique `(osake, pvm)` index is required, and tables with triggers are refused. Existing keys are skipped within the transaction. No UPDATE, DELETE, REPLACE, migration or downstream operation is executed. Failed active transactions roll back; previous committed ticker inserts survive later failure or interruption. Network work occurs outside write transactions. Each committed insert is read back, and final inserted-value verification and SQLite integrity verification run after writes. A post-commit verification failure is reported as `committed_unverified`; the committed count is preserved, not described as rolled back.

The database itself is the restart checkpoint: restarting enumerates current keys and fetches only missing ones. Atomic JSON progress is saved after each successful commit and periodically during other processing. Handled interruptions save an `interrupted` report and propagate. A hard process kill or report-file failure can leave the last report behind the database; restart reconciles database keys without overwriting them. Successful writes are never relabeled as provider failures merely because report persistence fails.

**No database backup is created.** SQLite transactions provide rollback for these strictly insert-only writes; a full recovery copy is unnecessary. Reports explicitly show `backup.state=not_created`. No production database was copied, backed up or written during implementation/tests. No unrelated backup or WAL/SHM file is deleted; Restic retention is unchanged. If a future operation actually requires a temporary backup, it must use the established facilities, delete only its operation-specific backup after conclusive verification, and retain/report its exact location on failure or uncertainty. This implementation introduces no backup creation or cleanup path.

The existing scheduler operation lock, UI duplicate-submission guard and disabled controls remain. No scheduler configuration, running process, normal update path or daily split logic was changed. Separate external tools must still respect the operation lock; atomic key rechecks protect against competing inserts.

## Status and reports

Reports: `reports/missing_day_recovery/missing_day_<run_id>.json`.

Per-ticker statuses follow existing lower-case conventions: `existing`, `inserted`, `unavailable` (with the diagnostic reason above), `held` (specific identity/key conflict), `invalid_data`, `provider_failure`, `database_failure`, and exceptionally `committed_unverified`. `pending` denotes work not reached. Progress now reports actual `inserted`, rather than a pre-write `validated` promise. The summary includes examined tickers, initially missing keys, existing skips, inserts, unavailable responses, identity holds, invalid records, provider/database failures and remaining missing rows.

The JSON field `identity_adjustment_holds` is retained for report/UI compatibility but now counts identity/key holds only; there is no adjacent adjustment comparator. Terminal outcomes remain `completed`, `partial`, `failed`, with `interrupted` for a caught process interruption. No-data boundaries remain diagnostic, and known local identity evidence is not exhaustive. Yahoo adjustment vintage, silently swallowed provider throttling and incomplete identity metadata remain limitations of the reused acquisition path.

## Focused validation and changed files

All acquisition is mocked; all database fixtures are small synthetic SQLite files. Coverage includes existing-key request skipping, equities/ETFs/indices/other types, absent Fundamentals/start metadata, missing/invalid/different neighbors, malformed OHLCV, wrong symbol/date/market, reviewed transitions, no-data diagnostics and 14-day limits, independent peer failures, progressive commits, rollback, interruption/restart, concurrent keys, report failure after commit, rate-limit stopping, unchanged pacing, UI flow and normal stock-service regressions.

```text
venv/bin/python -m pytest -q tests/test_missing_day_recovery.py tests/test_missing_day_recovery_ui.py tests/test_stock_update_main_service_runner.py tests/test_stock_update_service_history_fetch.py tests/test_stock_update_service_ohlcv_write.py tests/test_stock_update_main_adapters.py --override-ini addopts='' --tb=short
```

Final focused result: **104 passed**, zero failed. The existing test database guard rejected writable production connections and its protected-database inventory check passed. No live provider calls or production database copies were made.

Changed files: `services/missing_day_recovery.py`, `main.py` (missing-day invocation/summary only), `tests/test_missing_day_recovery.py`, `tests/test_missing_day_recovery_ui.py`, and this document. `services/stock_update_service.py` is reused without changes. No full-suite or live recovery runs, provider requests, production database writes/copies/backups, application restarts or push.

## USA index timezone correction — 2026-10-14

The completed local report `reports/missing_day_recovery/missing_day_20261014T090019076691Z_345a4561.json` shows `^VIX` rejected as `PROVIDER_MARKET_MISMATCH` despite exact symbol, type `INDEX` and timezone `America/Chicago`. Targeted read-only inspection found three stored USA index symbols: `^GSPC`, `^NDX` and `^VIX`; the same report records New York for the first two. Normal collection assigns the selected/stored market through its usual conversion and has no Yahoo instrument/timezone acceptance gate. No live Yahoo requests were needed for this finding.

Recovery now accepts **America/New_York or America/Chicago only for USA Yahoo INDEX responses**. This is an instrument-specific allowance, not a VIX-only exception. Other US index timezones require additional established evidence before being added. Equities, ETFs and other instruments retain their existing per-market timezone requirement. Exact Yahoo symbol matching, missing-provider-identity holds, requested ticker/date/market validation, reviewed historical identity protection, acquisition/options/pacing/retries/conversion and incremental insert-only persistence are unchanged. Missing `instrumentType` does not qualify for the Chicago allowance.

Changed files for this correction: `services/missing_day_recovery.py`, `tests/test_missing_day_recovery.py` and this document. Mocked/synthetic tests cover the observed indices, a synthetic second Chicago index, New York equities/ETFs, wrong symbols/markets, unsupported/missing timezones, insertion exactly once, existing-key request skipping and restart. Normal updater regression tests remain included in the focused command above. Production database changes/copies/backups and live provider requests: **0**; no recovery job, scheduler restart or push.

Correction validation: **121 targeted tests passed**, zero failed, using the command above. The production database isolation guard and protected-file inventory checks passed.
