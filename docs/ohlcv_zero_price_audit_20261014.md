# OHLCV zero and negative price audit — 2026-10-14

Historical October 14 audit snapshot, before the [targeted NULL-row repair](ohlcv_negative_and_null_repair_20261014.md). The counts below were not recomputed when this document was committed; generated audit evidence remains outside this documentation commit.

## Executive summary

RawCandle can continue preserving provider observations unchanged while keeping **storage**, **quality diagnostics** and **calculation eligibility** separate. Under the policy supplied for this audit, storing a Yahoo zero is intentional preservation, not itself a defect. A preserved observation is not automatically suitable for returns, chart interpretation or SetupMaster research.

**Verified:** 8,869,834 stored rows; 754 with at least one zero OHLC field (40 tickers), 1,583 with at least one negative OHLC field (two further tickers), and 692 with all four prices zero. Zero/negative row sets do not overlap: **2,337 nonpositive rows across 42 tickers**. DEC, NFE and VATE account for 2,275 of them (**97.35%**), and all three are current canonical Fundamentals US equity routes. No live provider retrieval, recalculation or production change was performed.

**Conclusion:** Preserve source data and current behavior. Recommend a separate, feature-specific quality mask and interval diagnostics for selected calculations/research. Do not delete observations, replace prices, interpolate, convert zeros to NULL or change global Yahoo adjustment settings.

## Scope, evidence and definitions

`data/osakedata.db` was opened with URI `mode=ro` and `PRAGMA query_only=ON`. The main audit used a single read transaction for a consistent price snapshot: grouped SQL aggregation, then indexed histories of only the 42 affected tickers. Entire market history was not loaded into Python. Per-ticker history was reduced to date/quality flags for sequence analysis. Subsequent targeted checks identified NULL rows and corroborated three universe identities.

- **Zero row:** any of open/high/low/close equals zero, not volume zero.
- **Negative row:** any OHLC field is below zero. Count is per row, not per failing field.
- **Sequence:** consecutive affected **stored observations within ticker/market**, interrupted by an observed unaffected row. It does not mean consecutive exchange sessions. Missing dates can occur within a sequence and are not counted as zero observations.
- **Isolated:** a sequence of one stored observation; endpoints are not necessarily surrounded by good observations or verified sessions.
- **Operationally bracketed quality span:** between first and last stored rows with finite positive OHLC, proper high/low ordering and finite nonnegative volume. This is a descriptive, hindsight quality proxy, not certified historical listing or complete trading coverage.

Database-wide NULL and numerical checks distinguish NULL, nonnumeric storage classes and infinity. SQLite commonly converts bound NaN to NULL, so a NULL cannot be classified as an original NaN versus genuinely missing input from present storage alone. Source rows lack per-row provider/adjustment/acquisition provenance; causes must not be inferred from values alone.

## Database-wide counts and distributions

| Metric | Rows / tickers |
|---|---:|
| Total stored OHLCV rows | 8,869,834 |
| Any zero OHLC | 754 / 40 tickers |
| Any negative OHLC | 1,583 / 2 tickers |
| All four OHLC zero | 692 / 1 ticker (DEC) |
| Some but not all OHLC zero | 62 |
| Any zero or negative OHLC | 2,337 / 42 tickers |
| Any NULL OHLC | 2 |
| Nonnumeric OHLC / infinite OHLC | 0 / 0 |
| Negative / NULL / nonnumeric / infinite volume | 0 / 0 / 0 / 0 |
| Strict high/low ordering violations | 13,407 |

Zero prices comprise **0.00850%** of stored rows. Fieldwise zero counts are open 753, high 750, low 751 and close 692; these overlap. All zero closes belong to DEC's all-zero rows. Partial-zero bars elsewhere can therefore have usable positive closes but unsuitable open/high/low for other calculations.

The strict ordering diagnostic is `low > min(open,close) OR high < max(open,close) OR low > high`. Its 13,407 matches overlap nonpositive-price findings and are not added to 2,337. They include potential numerical/provider rounding differences and negative-price inversions; their materiality/provenance was not investigated here. A strict relation failure does not establish a storage-policy violation or warrant rewriting a row.

| Market | Stored rows | Any zero | Any negative | All-zero | Zero tickers | Negative tickers |
|---|---:|---:|---:|---:|---:|---:|
| usa | 8,094,053 | 738 | 1,583 | 692 | 38 | 2 |
| omxh | 201,657 | 13 | 0 | 0 | 1 | 0 |
| omxs | 574,124 | 3 | 0 | 0 | 1 | 0 |

Only these three market values occur in the audited table. There are no stored Xetra rows in this snapshot; this does not imply the application lacks Xetra support.

| Year | Stored rows | Any zero | Any negative | All-zero | NULL OHLC | Strict ordering failures |
|---|---:|---:|---:|---:|---:|---:|
| 2018 | 802,606 | 0 | 251 | 0 | 0 | 1,457 |
| 2019 | 843,864 | 0 | 484 | 0 | 0 | 1,568 |
| 2020 | 891,466 | 0 | 345 | 0 | 0 | 1,187 |
| 2021 | 984,785 | 232 | 252 | 231 | 0 | 894 |
| 2022 | 1,051,126 | 238 | 251 | 238 | 0 | 729 |
| 2023 | 1,079,053 | 223 | 0 | 223 | 0 | 303 |
| 2024 | 1,127,529 | 0 | 0 | 0 | 0 | 133 |
| 2025 | 1,187,888 | 0 | 0 | 0 | 0 | 36 |
| 2026 | 901,517 | 61 | 0 | 0 | 2 | 7,100 |

The two NULL-OHLC rows are **SKHY and SPCX, both 2026-07-28 / USA**, with all four OHLC NULL and volumes 44,965,601 and 80,968,276. They are present keys with missing field values, not missing dates. Their origin is unresolved; do not attribute them to the inspected normal converter, which skips incomplete OHLC.

## Isolated observations, sequences and concentration

There are **57 zero sequences**: 52 single-observation sequences (52 rows) and five multi-observation sequences (702 rows). Including negative prices gives **59 nonpositive sequences**: the same 52 singletons and seven multi-observation sequences totaling 2,285 rows.

| Ticker / market | Condition | Sequence start | Sequence end | Stored affected observations |
|---|---|---|---|---:|
| NFE / usa | negative | 2019-01-31 | 2022-12-30 | 988 |
| DEC / usa | zero | 2021-01-04 | 2023-11-29 | 692 |
| VATE / usa | negative | 2018-01-02 | 2020-05-13 | 595 |
| GTI / usa | zero | 2026-05-15 | 2026-07-07 | 3 |
| ^OMXH25 / omxh | zero | 2026-10-05 | 2026-10-07 | 3 |
| ^OMXH25 / omxh | zero | 2026-08-03 | 2026-08-04 | 2 |
| ^OMXHPI / omxs | zero | 2026-05-20 | 2026-05-21 | 2 |

DEC alone accounts for **91.78%** of zero-price rows. Its sequence includes real missing dates: the preceding DEC investigation confirms 2023-06-30 is absent despite stored zeros before/after. The 692 count measures preserved observations, not a claim of 692 complete consecutive sessions. GTI's three affected observations span almost two months; do not mistake this for a three-day outage.

There are **51 zero rows within operationally bracketed quality spans**, across the table. This proves that checking only first/last good dates would not remove isolated internal quality conditions. None of the 2,275 nonpositive rows in the three canonical equity routes is bracketed by good observations on both sides: these affected blocks precede the first numerically qualified row. This is not proof those periods were unlisted or economically irrelevant.

A separate cross-sectional cluster contains **33 zero-price rows on 2026-05-15**, versus 61 zero rows in all of 2026. This deserves source/context investigation, but no provider request or cause attribution was made. Example CTLP on that date has open 0, high/low/close ~11.20 and volume 0: it is not an all-zero candle.

## Acquisition and persistence policy

**Verified implementation:** `main.py` normal collection calls `yf.Ticker(...).history(start=..., end=...)`. `services/stock_update_service.py` reuses those defaults, skips incomplete/NaN OHLC through missing-value checks and converts present prices to floats and volume to integer. Neither zero nor negative numeric OHLC is treated as missing. The service's `insert_missing_ohlcv_rows` uses plain INSERT for absent dates, committing per ticker; it does not impose the missing-day validator's positivity rule. The normal legacy UI writer similarly checks missing OHLC without adding positivity filtering. Under the stated policy these paths intentionally preserve observed Yahoo prices.

The missing-day path in `services/missing_day_recovery.py` deliberately differs: after the same acquisition/conversion it requires finite positive OHLC, valid ordering and nonnegative finite volume before inserting. An existing key is skipped even if its prices are zero; this function is not a quality repair tool. Preservation by normal collection and rejection by maintenance validation are separate operational policies, not evidence that the source row should be deleted.

Installed yfinance 0.2.66 defaults to `auto_adjust=True`. Its `utils.auto_adjust` uses `Adj Close / Close` to multiply open/high/low, and uses Adj Close as adjusted close. Zero adjusted close with positive underlying close therefore produces zero OHLC. The prior [DEC investigation](ohlcv_missing_day_dec_investigation_20261014.md) reproduces that mechanism; **no new live calls were made here**. A negative factor could likewise produce negative adjusted prices and invert high/low, but attribution of NFE/VATE values to that mechanism is **a hypothesis**, not verified provider evidence.

`stock/splits.py` synchronizes split events. `main._maybe_backfill_splits_for_ticker` and `analysis/splits_price_backfill.py` refresh applicable history with the same default Yahoo options, skipping missing values but preserving zeros/negatives. A refresh may alter observations as Yahoo's series changes; it does not guarantee positive prices or diagnose bad adjustment factors. Neither split synchronization nor refresh was run or modified.

## Downstream consumers: verified behavior versus mathematical risks

| Inspected consumer | Verified handling | Calculation implication |
|---|---|---|
| `analysis/run_analysis.py` and `candlestick_patterns.py` | Drop incomplete OHLC, not nonpositive OHLC; pattern-specific guards differ. Trend filters average prices; several candle helpers guard nonpositive range. | Positive-close partial-zero bars and negative/zero bars can reach detectors. Some patterns return false, others can have distorted comparisons; no blanket false-signal claim. |
| `analysis/chart_patterns.py` | Moving averages include zero/negative closes. `_pct_change(0,end)` returns 0; denominators in range helpers have floors. | Finite output can conceal an undefined ratio. SMA/shape features may be biased without an exception. |
| `analysis/divergence_engine.py`, `divergence_v1.py` | Numeric coercion/drop-NaN before Wilder RSI; per-date and price-pair checks reject nonpositive prices in several event branches. | Guards protect those events, but unsuitable values still enter RSI history and candidate neighborhoods, affecting later otherwise-positive rows. |
| `analysis/stock_dow_structure.py` | Loader excludes NULL close/date, not nonpositive OHLC. Local pivot comparisons use high/low values without a global positivity filter. | Partial-zero or negative bars can affect extrema/pivot context. No production state was recalculated and no specific wrong transition is alleged. |
| `compute_new_features.py` | Gap uses `(open-prev_close)/(prev_close+1e-6)`; body uses zero-range-to-NaN denominator; index volatility is lagged rolling **price-level standard deviation**. | Epsilon can turn zero-denominator gaps into enormous finite values. Zero range is handled for body ratio, but this is not full observation qualification. Level volatility and rolling means remain sensitive to stored values. |

For planned SetupMaster features, additional **mathematical risks**, not verified claims about an implemented research engine: daily returns through `[10,0,11]` are -100% followed by infinity; logs at zero/negative prices are undefined; negative-price returns can be finite but economically misleading. ATR's true-range terms can spike at zero/positive boundaries or be depressed during all-zero periods; ATR-normalized ratios can divide by zero. Gaps, range compression, breakout highs/lows and momentum measurements require qualified inputs and consistent corporate-action basis. No active ATR implementation was assumed from the inspected paths.

Pure in-memory diagnostics confirmed: normal conversion preserves an all-zero synthetic bar, missing-day validation rejects it, pandas returns through `[10,0,11]` produce -100%/infinity, chart `_pct_change(0,11)` returns 0, Wilder RSI on all-zero closes can return neutral 50, and an all-zero candle **does not** match `is_dragonfly_doji`. An initial test expectation of that last pattern matching was false and was corrected; do not generalize that every zero candle yields a signal. All final assertions passed. No production consumer/job was executed.

## SetupMaster universe relevance

Active canonical generation: `refresh_20261014T095401Z_refresh_fundamentals_43db1c8371f6_production_6917d617`, **2,547 companies / 2,560 securities**. Matching used current ticker and ticker aliases to security IDs, then corroborated the three matches against canonical provider identities and the corresponding local provider stocks metadata. No aliases were joined to manufacture history. All three are unique current routes, active, US-listed common-stock categories with matching SHARADAR permatickers:

| Ticker | Security ID | Provider permaticker | Zero rows | Negative rows | First numerically qualified stored row | Provider first price |
|---|---:|---:|---:|---:|---|---|
| DEC | 657 | 640849 | 692 | 0 | 2023-11-30 | 2023-12-18 |
| NFE | 1543 | 111638 | 0 | 988 | 2023-01-03 | 2019-01-31 |
| VATE | 2300 | 197117 | 0 | 595 | 2020-05-14 | 2011-06-23 |

Thus **one zero-affected canonical equity route** (692 rows), **two negative-affected routes** (1,583 rows), and **three affected canonical securities total** (2,275 rows). The other 39 affected tickers are outside this current canonical route match; the administrative market universe remains broader and includes indices/units. This is diagnostic membership, not permission to expand SetupMaster to unrelated instruments.

All three canonical security starts are undated. Current membership and active/common-stock classifications do **not** establish historical point-in-time eligibility. Provider first-price dates are not independently verified IPO/listing timestamps. DEC's nonpositive period precedes the provider's first-price date entirely, raising additional listing/series-lineage questions. NFE and VATE's **1,583 negative rows lie within their provider first/last-price spans**, so they cannot simply be dismissed as pre-history based on those local bounds. No historical survivorship bias has been eliminated.

Answering “inside otherwise usable historical trading periods” requires explicit definitions: **0** canonical nonpositive rows are bracketed by numerically qualified stored rows on both sides, but **1,583** lie inside local provider coverage spans. Neither measure certifies fully usable sessions. Across the whole table, **51** internal zero observations show why interval qualification must check individual bars and required windows, not only ticker endpoints.

Priority investigation targets: **NFE and VATE** for long negative periods/provenance; **DEC** for known zero adjustment output and pre-current-provider history; the **2026-05-15 cluster** for a shared source condition; **GTI** for sparse terminal observations; **^OMXH25 and ^VIX** for partial-zero index bars used as context; **^OMXHPI**, currently stored under `omxs`, for identity/market evidence before assuming its symbol implies a different market. Also diagnose the two NULL-OHLC keys separately. No classifications were changed.

## Recommendations — preserve data, qualify calculations

1. **Keep current storage policy.** Retain provider observations unchanged, including zero/negative values and their existing keys. This preserves evidence and reproducibility; it does not certify tradability or approve every calculation on them.
2. Propose a separate, read-only quality view/report or research output with reason codes such as zero-open, zero-close, negative-price, missing-field, ordering condition and unknown adjustment provenance. Record intervals, source/vintage when known and denominators. Keep absent-session reasons separate from present rows with unsuitable values.
3. Apply **feature-specific** qualification in a separately reviewed change: a close-only calculation may remain usable when high/open are zero but close is valid, while ATR/candle/gap/setup features require qualified corresponding OHLC fields. Volume zero is not intrinsically the same as missing/negative volume; liquidity and research tradability rules are separate.
4. For SetupMaster, qualify event inputs, causal lookbacks, feasible entry and future label paths independently. Keep session positions; do not drop bad bars and compress trading time or substitute later endpoints. Past/current eligibility must use information available then. Future unsuitable observations should produce explicit censored/missing outcomes with retained event denominators, not retroactive silent event removal. Validate warm-up/reset policies for recursive RSI/EMA and report excluded coverage/sensitivity; do not prescribe new production states.
5. Investigate targeted instruments/provider basis before interpreting values economically. No automatic deletion, interpolation, replacement, zero-to-NULL conversion or global auto-adjust change is recommended. Existing market-state behavior remains untouched.

## Reproducibility and limitations

Commands: `venv/bin/python /tmp/zero_price_audit.py` (grouped SQL and 42 indexed histories, pinned price read transaction); `venv/bin/python /tmp/zero_audit_details.py` (field/date summaries and specific NULL rows); small read-only identity queries for DEC/NFE/VATE; pure synthetic Python assertions described above. Compact independent summaries are `/tmp/zero_price_audit.json`, `/tmp/zero_price_groups.json` and `/tmp/zero_price_details.json`; they contain aggregates/intervals and a bounded example set, not a production database copy.

Core predicates were `open=0 OR high=0 OR low=0 OR close=0`, corresponding `<0` tests, and all-field equality for all-zero rows, grouped by `market,substr(pvm,1,4)`. Results cross-check: 52 singleton zero rows + 702 multisequence zero rows = 754; 988 NFE + 595 VATE = 1,583; all market/year sums equal 8,869,834. Dates absent from storage were not inferred from weekday gaps or counted as zeros. No exchange calendar/PIT listing certification or database-wide missing-session census was performed.

Inspected files: `main.py`, `services/stock_update_service.py`, `services/missing_day_recovery.py`, `stock/splits.py`, `analysis/splits_price_backfill.py`, `analysis/run_analysis.py`, `analysis/candlestick_patterns.py`, `analysis/chart_patterns.py`, `analysis/divergence_recompute.py`, `analysis/divergence_engine.py`, `analysis/divergence_v1.py`, `analysis/stock_dow_structure.py`, `compute_new_features.py`, existing SetupMaster Phase 1 and DEC investigation documents, active generation manifest and limited canonical/provider identity tables. Fundamentals financial data and Forecasts systems were not audited. Some inspected loaders have write-capable job wrappers; only source was read, and their jobs were never invoked.

No provider requests, production database writes/copies/backups, schema migrations, scheduler runs, recalculation jobs or application-behavior changes. No full test suite. Only this requested document was added; unrelated working-tree changes were preserved.
