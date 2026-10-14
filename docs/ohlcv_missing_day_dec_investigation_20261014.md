# DEC missing-day rejection — 2026-10-14

## Conclusion

**VERIFIED FACT:** The production report rejects DEC on **2023-06-30** with `status=invalid_data`, `reason=INVALID_OHLCV`. This is the final numerical validation branch, after Yahoo acquisition, conversion, symbol/market checks and first-trade validation. A narrowly scoped live reproduction establishes a concrete mechanism: Yahoo supplies **Adj Close = 0**, and yfinance's default automatic adjustment turns positive OHLC into **four zero prices**. These fail RawCandle's strictly-positive-price requirement. The original rejected numerical bar was not persisted, so its exact values cannot be independently recovered from that report; today's matching reproduction and stored zero-price neighbors strongly support this explanation of the original rejection.

**RECOMMENDATION:** Keep the rejection. Do not insert a raw-price exception or change global `auto_adjust`. Existing DEC history is already invalid over an extended interval, and compatibility of a positive raw target with a consistent historical price basis has not been demonstrated. No fix is implemented in this investigation.

## Production report and application path

Inspected report: `reports/missing_day_recovery/missing_day_20261014T125809930507Z_8c37299e.json`.

Verified totals: 4,524 examined, 2,598 initially missing, 1,865 inserted, one invalid record (DEC), 730 unavailable, two identity holds, zero provider/database failures and 733 still missing. It records verified writes, zero existing rows modified/deleted and no backup created. These are the earlier recovery's results, not this investigation's writes.

Exact DEC entry:

```json
{"ticker":"DEC","date":"2023-06-30","market":"usa","status":"invalid_data","reason":"INVALID_OHLCV","provider_identity":{"symbol":"DEC","instrumentType":"EQUITY","exchangeTimezoneName":"America/New_York","firstTradeDate":1609770600}}
```

Call chain at inspected HEAD `b30eb362` (later than `15f0873f`):

1. `main.RawCandleApp.recover_missing_day` invokes `run_missing_day_recovery` with its normal `yf.Ticker` factory.
2. `missing_day_recovery.history_rows` calls `stock_update_service.fetch_history_for_date_ranges`: `stock.history(start=..., end=...)`, with no explicit adjustment arguments.
3. `convert_histories_to_ohlcv_rows` / `convert_history_to_ohlcv_rows` format the date and convert OHLC to floats and volume to integer. Missing OHLC can be skipped; **zero is not missing** and survives conversion.
4. `provider_identity` and first-trade validation precede `valid_bar`. The reported `INVALID_OHLCV` proves those preceding branches did not reject DEC. The report's exact symbol, EQUITY type and New York timezone are compatible with USA; the first-trade timestamp precedes the target.
5. `valid_bar` requires finite positive OHLC, finite nonnegative volume and valid low/open/close/high ordering. Four zeros violate positivity even though they are finite and satisfy ordering. The writer is not reached.

A conversion failure would instead have a conversion-specific reason; incomplete target OHLC would have `INCOMPLETE_PROVIDER_OHLC`. Neither appears here. The original report lacks the failed bar, so it alone does not identify whether positivity, finiteness, volume or ordering failed.

## Observed Yahoo values

Exactly **two narrow history invocations**, DEC only, were executed starting **2026-10-14 15:10:05 UTC (18:10:05 Helsinki)**, with yfinance **0.2.66**:

- Normal RawCandle defaults: `history(start='2023-06-28', end='2023-07-07')`.
- Same dates, only `auto_adjust=False` added.

End is exclusive, so this includes June 28 through July 6. Both use the existing fetch helper; the explicit-raw diagnostic wraps the same Ticker's history call to add that one option. Existing range and legacy ticker pauses were reused, under the existing nonblocking stock-update operation lock. No `stock.actions`, `stock.splits`, full-history or other-provider retrieval was performed. Two history invocations do not imply exactly two upstream HTTP requests: yfinance manages its own transport/cache.

Values below are rounded for readability; diagnostics retained full floating-point values locally.

| Date | Raw Open | Raw High | Raw Low | Raw Close | Raw Adj Close | Raw volume | Default OHLC | Default volume |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| 2023-06-28 | 1.110 | 1.130 | 1.110 | 1.130 | 0 | 4,500 | all 0 | 4,500 |
| 2023-06-29 | 1.130 | 1.130 | 1.100 | 1.110 | 0 | 7,000 | all 0 | 7,000 |
| 2023-06-30 | 1.143 | 1.143 | 1.143 | 1.143 | 0 | 700 | all 0 | 700 |
| 2023-07-03 | 1.143 | 1.143 | 1.143 | 1.143 | 0 | 0 | not returned | — |
| 2023-07-05 | 1.190 | 1.190 | 1.190 | 1.190 | 0 | 1,600 | all 0 | 1,600 |
| 2023-07-06 | 1.140 | 1.165 | 1.120 | 1.120 | 0 | 15,400 | all 0 | 15,400 |

June 30 raw OHLC is exactly `1.1430000066757202` in all four fields. The normal converter preserves those values and volume 700, and `valid_bar` accepts that raw row. All six explicit-raw bars pass numerical validation; all five returned default bars fail. July 3's zero volume and differing presence are provider observations, not proof of trading or a legitimate absence. The user's UI rounds June 30 to 1.14; this agrees with the observed full-precision value.

Observed metadata: `symbol=DEC`, `instrumentType=EQUITY`, `exchangeTimezoneName=America/New_York`, `currency=USD`, `exchangeName=NYQ`, `firstTradeDate=1609770600`. This corroborates operational identity checks, but does not independently certify historical listing/security continuity or exchange-original raw-price provenance.

All returned `Dividends` and `Stock Splits` entries are zero in this narrow window. No positive action is observed here. Events outside the window were deliberately not fetched.

## Adjustment mechanism: fact versus hypothesis

**VERIFIED FACT:** Installed `yfinance.scrapers.history.PriceHistory.history` defaults include `interval='1d'`, `actions=True`, `auto_adjust=True`, `back_adjust=False`, `repair=False`, `keepna=False`, `rounding=False`. RawCandle omits overrides in both the service and normal UI collection.

Installed `yfinance.utils.auto_adjust` computes:

```text
ratio = Adj Close / Close
adjusted Open/High/Low = raw Open/High/Low * ratio
adjusted Close = Adj Close
```

For June 30, `0 / 1.1430000066757202 = 0`. Applying that installed function to the retained explicit-raw frame produces zero OHLC on every date while preserving volume, reproducing the numerical mechanism without further provider requests. This is an adjustment outcome, not an integer-volume conversion or timezone error.

**UNRESOLVED / HYPOTHESES:** Why Yahoo's adjusted-close series is zero is not established. Erroneous historical adjustment factors, cumulative distribution handling, a corporate-action data error or historical-series/identity contamination are possibilities. No specific split/dividend has been proven responsible. Narrow-window zero action fields and an empty local splits table cannot rule out earlier/later actions or missing action records. Auto-adjustment is established as the transformation producing zero OHLC; the upstream cause of Yahoo's zero Adj Close remains unknown.

The issue is not mathematically DEC-specific: any security with zero/invalid adjusted close can produce nonpositive/nonfinite adjusted OHLC through the same default path. **No broader prevalence estimate is supported.** DEC is the only `invalid_data` case in this particular missing-day report; other tickers and dates were not audited.

## Current database evidence and basis compatibility

All production connections used SQLite URI `mode=ro` plus `PRAGMA query_only=ON`.

- DEC has **1,411 stored rows**, spanning **2021-01-04–2026-10-13**.
- **692 rows have all four OHLC prices exactly zero**, spanning **2021-01-04–2023-11-29**. The count of rows with any nonpositive OHLC is also 692.
- June 30 remains absent. July 3 is also absent in the inspected neighborhood.
- The nearest stored neighbors are June 29 (OHLC all zero, volume 7,000) and July 5 (OHLC all zero, volume 1,600). June 20–29 and July 5–12 inspected rows also have zero OHLC. Thus adjacent rows exist, but their prices are **not valid anchors**.
- Earliest stored positive close is November 30, 2023: open `0.6727839453163443`, close `0.6878226399421692`. The cause of that boundary is not established by these observations.
- Local `splits_data` has **no DEC entries**.

**ASSESSMENT:** Current defaults reproduce nearby stored zero OHLC and their volumes, consistent with an auto-adjusted acquisition path. This is compatibility with **invalid values**, not evidence of a valid global basis or definitive original-row provenance. Inserting raw June 30 at 1.143 into surrounding zeros would introduce a different observed basis and would not repair the historical series; returns involving zero neighbors are undefined or misleading. No safe raw fallback has been demonstrated. `auto_adjust=False` means no yfinance dividend auto-adjustment; it does not certify that Yahoo's supplied historical OHLC is unadjusted for every split or corporate action.

## Does existing split refresh address this?

**VERIFIED FACT:** `stock/splits.py` synchronizes Yahoo split events. `main._maybe_backfill_splits_for_ticker` acts on uncorrected local splits, deletes/refetches history from 2018, recomputes analysis and marks successful corrections. `analysis/splits_price_backfill.refetch_prices_from_yahoo` uses the **same default** `stock.history(start, end)` call. It skips missing OHLC but does not reject zero prices before writing.

Consequently this mechanism is **not a remedy for persistently zero Yahoo adjusted close**: DEC currently has no local split trigger, and even if refresh ran it could reproduce the zero values while Yahoo still supplies them. It is not a dividend/adjusted-close repair system. No refresh or split synchronization was executed or modified.

## Risk and recommended next action

1. **Keep missing-day positivity validation and leave DEC June 30 unfilled.** The current rejection is correct for the values returned by normal acquisition.
2. **Do not switch global adjustment options or add an automatic raw fallback.** A single numerically valid raw bar does not establish basis compatibility, and copying the invalid neighboring zero convention is unacceptable.
3. In a separate authorized task, investigate DEC's adjustment-series provenance and dated security/action history around the zero-to-positive boundary. Preserve raw/Adj Close/action evidence and establish a consistent, valid basis before proposing any DEC history repair. Prefer provider correction followed by a separately reviewed refresh if that resolves the series; verify returned values first, since the current refresh permits zeros.
4. The smallest potential code improvement is diagnostic only: retain failed OHLCV and explicit adjustment configuration in `INVALID_OHLCV` evidence so future original failures need not be reconstructed. This is a recommendation, not implemented here. Broader normal-writer validation deserves separate review given the existing zero rows; do not change production collection as part of this investigation.

## Files inspected and diagnostics executed

Repository files:

- `reports/missing_day_recovery/missing_day_20261014T125809930507Z_8c37299e.json` — exact DEC entry and counters.
- `services/missing_day_recovery.py` — conversion wrapper, identity/first-trade guards, final validator and rejection reason.
- `services/stock_update_service.py` — normal fetch and OHLCV conversion.
- `main.py` — recovery invocation, Ticker factory, normal UI history options and split-refresh trigger.
- `analysis/splits_price_backfill.py` — refresh options, filtering and persistence.
- `stock/splits.py` — split synchronization and correction flag.
- `data/osakedata.db` — DEC-only read-only queries.

Installed sources inspected: `venv/lib/python3.10/site-packages/yfinance/scrapers/history.py` (`PriceHistory.history` signature) and corresponding `yfinance/utils.py` (`auto_adjust`), with actual installed paths resolved by Python inspection; these are environment evidence, not repository changes.

Commands/diagnostics executed:

- `git status --short`, `git rev-parse --short HEAD`, targeted `sed`/`rg` reads of the files above; JSON selection for `ticker == 'DEC'`.
- DEC-only SQL: nearby rows for June 20–July 12; `MIN(pvm), MAX(pvm), COUNT(*)`; count/range with any OHLC <= 0 and with all four OHLC = 0; earliest positive and latest zero examples; `splits_data WHERE osake='DEC'`; target-day count. All through read-only connections.
- `PYTHONPATH=/home/kalle/projects/rawcandle venv/bin/python /tmp/dec_yahoo_diagnostic_20261014.py` — the two history invocations described above. Small provider-only results retained at `/tmp/dec_yahoo_diagnostic_20261014.json`; neither file duplicates a production database.
- Local Python assertions over that retained JSON: raw target positivity/volume, zero Adj Close, default zero OHLC, six valid raw/five invalid default bars; `utils.auto_adjust` reproduction and unchanged volume. **All passed.** No additional live calls for these assertions.

No full test suite or recovery job was run. **Production database writes: 0. Production database copies/backups: 0.** No application, scheduler, split logic, adjustment settings or existing OHLCV values changed. Only this investigation document is committed; unrelated worktree changes and evidence are preserved. No push.
