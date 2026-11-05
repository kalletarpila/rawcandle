# PRICE-11 — OMXH daily-session finality, 2026-11-05

Status: exact price correction and targeted Dow recovery completed; other derived-state obligations remain open. This report does not certify the entire daily pipeline current.

## Proven provisional scope

The manual November 4 run (`logs/stock_update_scheduler_summary_20261104T111703Z.json`) ran 11:17:03–14:18:16 UTC, ending at 16:18:16 Helsinki time, before the 18:30 cash-market close. Exactly 96 identified OMXH November 4 rows were retained intraday. The November 5 insert-only run inserted zero OMXH rows and preserved these provisional observations.

PRICE-11 retained each original row's ID, ticker, date, market and all five OHLCV values. It requested only November 4 through exclusive November 5, once for each of these 96 tickers, using the existing Yahoo history/conversion path: `auto_adjust=True`, `actions=True`, `repair=False`. All returned one valid completed-session bar. Ninety-five frames used Europe/Helsinki; the `^OMXH25` index frame used Europe/Stockholm, mapping to the same Helsinki session date. No returned November 4 bar contained a split.

| Changed field | Tickers |
| --- | ---: |
| Open | 1 |
| High | 70 |
| Low | 16 |
| Close | 90 |
| Volume | 96 |

All 96 rows changed at least Volume. The maximum individual price difference was approximately 5.8%; no common unit multiplier was established. These are intraday-versus-completed observations, rather than evidence for arbitrary historical price replacement.

## Guard and correction owner

`services/market_sessions.py` uses the explicitly reviewed Nasdaq Helsinki cash-market holiday lists for 2024–2027, Europe/Helsinki daylight-saving rules, and a conservative 19:00 local eligibility boundary (18:30 close plus 30 minutes). The calendar is independent of the USA calendar. Years outside this reviewed horizon fail closed and require calendar review. The official [Nasdaq European trading-hours and holiday schedule](https://www.nasdaq.com/da/european-market-activity/trading-hours) is the primary reference.

Both `run_stock_data_update` and the legacy `RawCandleApp.update_stock_data` UI path now cap OMXH history's exclusive end to the day after the latest completed Helsinki session. The legacy path skips empty ranges. Native summaries expose the completed-session cutoff. Service schedules, Source acquisition, the USA bridge's calendar and Fundamentals are unchanged. A completed provider vintage can still receive later provider corrections; this guard does not assert that a bar can never be revised.

`services/price_history_maintenance.py` provides an explicitly invoked bounded owner path, not a new daily overwrite mode. Its plan accepts at most 96 exact rows on one Helsinki session; it rejects USA replacement, identity changes, invalid values, suspicious common price multipliers and unsupported clocks. The plan binds retained provisional evidence and completed provider evidence to content hashes.

Application acquires the existing RC scheduler lock, runs mandatory fresh operational admission, durably fsyncs exact originals before the transaction, and uses `BEGIN IMMEDIATE` plus ID/ticker/date/market/value compare-and-swap. All rows commit atomically. Interruption after original-evidence creation requires explicit recovery; no unattended retry exists. Restoration also checks the exact current after-state. Successful replay verifies existing final values and writes zero additional price rows. A restored plan cannot silently reapply.

## Actual production publication

- Exactly **96 November 4 OMXH rows replaced**; original IDs and ticker/date/market identities preserved.
- Retained provisional rows: **0**. Unresolved final observations: **0**.
- No OMXH dates inserted, no other historical OMXH dates changed, and no USA history replacement.
- Independent postflight checked all 96 exact final rows.
- Second execution: **0 replacements**, all 96 already final; original restoration evidence preserved.

Durable ignored evidence is in `data/price_history_reconciliation/price11/`: `omxh_plan.json`, `provider_evidence.json`, `omxh/<plan_id>.original.json`, `omxh/<plan_id>.result.json`, `omxh_noop_result.json` and `price_postflight.json`. Bounded retained provider responses are in `provider/`; disposable working evidence is under `/tmp/stockcore-price11/Temp/`. None belongs in Git.

## Derived-state recovery and remaining obligation

Native `analysis.stock_dow_structure.run_stock_dow_structure` was called for exactly these 96 tickers with `recalc_from_date=2026-11-04`, radius 3, and no forced/full replay. Each had a reconstructable prior state. All statuses now cover the actual latest OHLCV date; events before the explicit boundary remained byte-equivalent in deterministic row hashes. The accompanying USA repair adds 409 other ticker recalculations; combined totals are 505 tickers, 33 deleted suffix events and 215 inserted events, zero errors, no schema change.

The pre-recovery inventory found 96 divergence rows on changed dates across the affected scope, 161 candlestick findings and 60 EC ticker rows; these numbers are existing rows, not a count of proven incorrect signals. Most relate to the provisional OMXH day; precise ticker/date inventories are retained. Relevance had no rows whose confirmation dates reached the changed boundaries, which does not establish current coverage.

Divergence has a targeted native function, but it commits deletion before a separate save and is not a qualified atomic correction publisher. The candlestick path inserts findings without removing patterns that cease to qualify. Running either blindly would not prove corrected historical coverage. Their exact pending scopes, subsequent relevance refresh, and affected DC/EC membership/report review are durably tracked in `derived_obligations.json`. No output was manually marked current. No full daily scheduler, group pipeline or Fundamentals workflow was run.

## Validation

The focused price/revision group passed 329 tests before price application. Native Dow's 38 focused tests passed before its production recovery. The UI/finality group passed 60 tests after adding the legacy UI guard, followed by 18 finality/evidence tests after hardening evidence serialization. Groups overlap; together with the unchanged tested bridge tests, including three additional persistent-unit threshold counterexamples, there are 399 distinct RC tests and 5 native StockCore quality-hold tests. Full suite: NO.

Tests include Helsinki holidays and DST, local close boundaries, exact replacement and restoration, idempotent replay, missing final observations, admission refusal, CAS conflicts, transaction rollback, commit-before-receipt explicit recovery, denial of USA replacement, invalid evidence leaving no empty original, and prevention of an intraday legacy-UI Yahoo request.
