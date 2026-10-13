# RawCandle missing day recovery UI

Task: RAWCANDLE-OHLCV-MISSING-DAY-01. Implementation date: 13 October 2026. Baseline: `09f5e959`.

## Outcome and production boundary

The stock-data page now contains **Hae puuttuva päivä**, immediately below the existing update row. It uses that row's existing market selector, one `YYYY-MM-DD` date field and **Hae puuttuvan päivän tiedot**. Progress, terminal counters and the detailed report location appear in the same section. The operation is independent of SetupMaster.

Implementation validation uses small synthetic SQLite fixtures and mocked Yahoo objects only. Neither historical example was recovered in production. No production database was copied, snapshotted, backed up, restored or modified. No live provider requests, app/server restart, scheduled job, rollout or push was performed. The prior standalone draft and its evidence were preserved and not executed or staged.

## Existing path and minimal shared changes

The normal main-app entry is `main.RawCandleApp.update_stock_data`, connected to the existing button. Unless `_use_stock_update_service` is enabled, it follows the legacy UI updater. The opt-in UI and scheduler use `_run_stock_update_via_service` and `services.stock_update_service.run_stock_data_update`.

Both select existing tickers using `osakedata`, grouped by ticker with first/last stored dates and `MAX(market)`, then filter the selected market. Missing-day recovery reuses `load_stock_update_candidates_for_market`; Fundamentals is not its universe. The existing selector's **Kaikki** value is rejected for this one-market operation; normal selector behavior is unchanged.

Yahoo acquisition is reused through the existing app stock factory, `fetch_history_for_date_ranges` and `convert_histories_to_ohlcv_rows`. Requests retain the existing `stock.history(start=..., end=...)` signature and adjustment defaults. There is no second downloader, `yf.download` batching layer, rate limiter or replacement retry system. The fetch helper's existing 0.1-second range pause remains unchanged.

The handover's service-delay description did not fully describe the default UI. Its legacy ticker delay is 1.0 seconds for at least 50 added rows and 1.5 seconds otherwise, with 30 seconds per 500 processed tickers. These exact expressions were extracted into shared helpers and reused by recovery. The normal updater's long-range pauses, service constants, retries, date planning, selection, writes and downstream analysis remain unchanged. The new operation stops if a rate-limit exception reaches it; it does not retry or change transport behavior. Yahoo may return an empty history instead of raising; that is reported as an unavailable response, not a proven legitimate absence.

Normal UI updates and recovery now participate in the scheduler's existing nonblocking lock. No scheduler code, timer, configuration, status writer or execution path was changed. The scheduler already calls the service directly under its lock, so it does not acquire a nested UI lock. A local submission lock and disabled controls prevent duplicate submissions. Background work and `StockUpdateProgressEvent` reuse existing UI/service conventions.

The normal UI has no configured OHLCV fallback. Recovery therefore does not newly enable Massive or Stooq or silently mix their price bases.

## Eligibility and validation

Only absent requested keys are fetched. An occupied key assigned to another market is held, never overwritten. Session evidence uses the market's stored index bar, or the same Yahoo acquisition path for a one-day index check if that bar is unavailable. Supported current market mappings are USA, OMX Helsinki, OMX Stockholm and Xetra. An unverified session stops before stock recovery; an empty calendar response is not asserted to prove a holiday. No index evidence is inserted or added to the stock universe.

For each missing stock, the nearest preceding/following stored rows form price-basis anchors. One short Yahoo request covers those anchors and the target, using an exclusive end date. Context beyond 14 calendar days, missing or invalid anchors, mixed-market history and uncorrected split history are held. Only the requested day can be inserted; context is validation-only.

Existing canonical securities, dated aliases and reviewed identity records are read-only guards. They do not filter the ticker universe to Fundamentals or create a new security master. Unknown tickers outside that database can proceed using provider evidence. Ambiguous aliases, retired/unknown identities, missing exchange evidence, dated security boundaries and successor/predecessor overlaps have explicit reasons. A malformed or unavailable established identity source fails explicitly instead of silently bypassing known evidence.

Yahoo must identify the exact ticker as an equity in the selected market's timezone and provide a usable first-trade date. A returned target contradicting its first-trade date is held. Dated local eligibility exclusions and unknown provider absences have separate counters.

OHLC must be finite, positive and satisfy low/open/close/high relationships; volume must be finite and nonnegative. Duplicate provider dates are rejected. Both fetched neighboring OHLC bars must match the stored anchors within `1e-6` relative/absolute numerical tolerance, and volume must match exactly. No scaling factor, interpolation, forward fill, predecessor warm-up or price replacement is performed. The historical AAPL/NVDA mismatch identified in the handover would therefore remain held unless the existing convention matches. This establishes local compatibility, not global raw/split-only/PIT certification.

## Insert and temporary backup lifecycle

Accepted rows are collected before any write transaction. If none qualify, no backup is created. Otherwise the existing RawCandle `online_backup` helper creates exactly one coherent SQLite backup, checks it and hashes it. The operation-specific name is:

`backups/missing_day_recovery/osakedata_missing_day_<run_id>.db`

Its manifest and the prepared report record the exact recovery path before insertion. No redundant persistent copy is created. Synthetic tests prove restoration through SQLite into memory.

One `BEGIN IMMEDIATE` transaction rechecks keys and anchor values and inserts accepted rows. A unique ticker/date constraint is required; tables with triggers are refused. There is no UPDATE, DELETE, REPLACE, migration or downstream call. Existing keys are skipped. Changed anchors hold only their own row. Exceptions, commit failures or interruption roll back the active transaction; repeat execution skips already-present keys.

After commit, `PRAGMA integrity_check` and exact inserted-value/market/date verification must pass. A durable result is written before cleanup. The operation then promptly deletes only its own temporary backup and manifest. Known held peers do not prevent cleanup of conclusively verified safe writes. Provider/database failures, interruption, report-write failure before cleanup or an uncertain post-commit outcome retain the backup and report its exact location. A post-commit verification failure reports known inserted rows and a failed outcome, not a fictional rollback.

Cleanup never deletes WAL/SHM files, unrelated backups or Restic retention. Reports and the UI distinguish `deleted`, `retained` and `not_created`. No production backup was created during this implementation.

## Reports and limitations

Operator reports are atomic JSON files at:

`reports/missing_day_recovery/missing_day_<run_id>.json`

The UI shows date/market, tickers examined, initial missing candidates, existing skips, insert count, documented eligibility exclusions, unavailable Yahoo responses, holds, provider/database failures, remaining missing rows and `completed`/`partial`/`failed`. Detailed per-ticker reasons, anchors, accepted values, provider identity, backup state/path and write verification remain in the report. Progress evidence is saved periodically; a disconnect does not invalidate a database transaction.

Recovery is deliberately conservative: one explicitly selected market, completed dates only, two-sided context within 14 days, matching adjustment evidence and known identity boundaries. It does not certify undated historical identities or repair inconsistent existing prices. Latest dates without a following stored anchor are held. Session evidence is operational index OHLCV, not a newly introduced exchange-calendar service. Existing separate single-ticker/import tools are not redesigned; key/anchor rechecks still protect this insert path against concurrent changes.

The live production browser was not launched because application startup can initialize production schemas. UI controls and the complete UI-to-backend flow were exercised with a synthetic database instead. Production activation and operator-triggered recovery remain separate work.

## Validation

Focused backend, UI integration and directly relevant stock-update regression tests cover invalid/future/non-session dates, exact market/date scope, occupied/missing keys, fetch success/absence/failure, numeric validation, identity/alias/successor holds, adjustment mismatches, independent peer success, duplicate requests, idempotence, stale anchors, rollback on a second insert, interruption, unchanged existing rows, backup restore/cleanup/retention, progress and terminal reporting.

Command:

```text
venv/bin/python -m pytest -q tests/test_missing_day_recovery.py tests/test_missing_day_recovery_ui.py tests/test_stock_update_main_service_runner.py tests/test_stock_update_service_history_fetch.py tests/test_stock_update_service_ohlcv_write.py tests/test_stock_update_main_adapters.py --override-ini addopts='' --tb=short
```

Final focused result: 84 passed, zero failed. The full suite was not run. The existing production SQLite test guard rejected writable production connections and its protected-file inventory checks passed. All backup, restoration and insertion exercises used small synthetic fixtures.

## Task owned files

- `main.py`
- `services/stock_update_service.py`
- `services/missing_day_recovery.py`
- `tests/test_missing_day_recovery.py`
- `tests/test_missing_day_recovery_ui.py`
- `tests/test_stock_update_main_service_runner.py`
- `docs/ohlcv_missing_day_recovery_ui.md`
