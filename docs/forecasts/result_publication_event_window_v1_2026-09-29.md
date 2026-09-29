# Result-publication event-window research V1

Date: 2026-09-29

Version: `result_publication_event_window_v1`

Decision: `EVENT_WINDOW_RESEARCH_V1_READY`

## 1. Purpose

Event-Window Research V1 is a descriptive, read-only daily-OHLC study of usable quarterly result-publication boundaries. It measures pre-event context, the D0 gap and move, forward returns, volume/range context, SPY-relative returns, and a simple D0-versus-D1 alignment diagnostic. It does not create a strategy or signal.

## 2. Input artifact

The only event input is:

```text
exports/result_publication/result_publication_daily_research_fy2025plus_2026-09-29.csv
```

Its validated SHA-256 is `76c6b5bb01e0849fbdfcc76058f6e14a997d84d86d332f75275c31a9b4d7cf52`. The sidecar SHA is `547e7b2c52212d61a0d3de227577a16182ba2d0d4183c236e9af1d3f891bf5a3`.

Preflight requires the sidecar version, recorded output path/hash, projection rule `result_publication_daily_research_v1`, usable-only filter, exported row count, and per-status counts to match. It also validates every row through `ResultPublicationResearchDataset`. Hash or count drift stops the build.

## 3. Event boundary

Stable identity is `(company_id, fiscal_year, fiscal_quarter)`. Ticker is OHLC lookup metadata only. D0 is exactly the exported `first_full_post_result_trading_date`; neither canonical timestamps nor elapsed calendar dates are reinterpreted downstream.

Offsets `D-5..D+5`, `D+10`, and `D+20` are positions in each ticker's ordered observed `osakedata.db` rows. There is no nearest-date fallback. Every offset includes its actual calendar date.

## 4. Metrics

V1 calculates:

- D-5 to D-1 and D-3 to D-1 close returns;
- D0 gap, close return from D-1, intraday return, and high/low range;
- cumulative close returns from D-1 through D0, D+1, D+2, D+3, D+5, D+10, and D+20;
- incremental D0-to-D+5/D+10/D+20 returns;
- D0 volume, pre-event average volume, and their ratio;
- pre-event average daily range and D0 range ratio;
- SPY and stock-minus-SPY returns through D0, D+5, D+10, and D+20;
- absolute D0 and D1 close moves and which is larger.

Return values are percentages. Volume/range averages use up to 20 observed pre-event rows and require at least 15 usable observations.

## 5. Data quality

All 13,352 input events remain in output. Each row exposes missing offsets, D-1/D0/D+5/D+10/D+20 flags, volume-history sufficiency, SPY availability, and an event-window status.

Four events lack D0. CYCN 2026-Q2 is `PENDING_D0` because its 2026-09-14 boundary is after its latest OHLC row, 2026-09-08. QVCG 2025-Q1/Q2/Q3 are `BOUNDARY_UNAVAILABLE` because the retained publication projection has no first-full-day. No substitute date was used.

Future offsets remain null without dropping the event. D+5 is available for 13,340 rows, D+10 for 13,334, and D+20 for 13,247.

## 6. Market-relative method

SPY history is loaded once from the same read-only `osakedata.db`. Each SPY return uses the stock event's actual D-1 and target offset dates. If SPY lacks either exact date, SPY and relative fields remain null; the stock boundary does not move.

## 7. Output artifact

Runtime artifacts are:

```text
exports/result_publication/result_publication_event_window_v1_2026-09-29.csv
exports/result_publication/result_publication_event_window_v1_2026-09-29.metadata.json
```

CSV SHA-256: `85eda92a912299d7beea3b3e11da2d118cd5d53a682b2735983f2b0a7d732af1`.

Metadata SHA-256: `cc53b01ce41624e61f2f0d01551a2d64ad2378cb5ab4d363a84947fe20c635c7`.

The CSV contains 13,352 data rows plus its header. A separate rebuild produced an identical CSV hash. Both generated artifacts remain ignored by Git under the existing `exports/` policy.

## 8. Validation counts

| Measure | Count |
|---|---:|
| Publication input | 13,352 |
| Joined D0 | 13,348 |
| Missing D0 | 4 |
| D+5 available | 13,340 |
| D+10 available | 13,334 |
| D+20 available | 13,247 |
| EXACT | 12,782 |
| HEURISTIC_HIGH | 570 |

Methods are 12,782 `CANONICAL_VERIFIED`, 483 `YAHOO_NEAR_UNIQUE_SEC`, 76 `SEC_V2_STRONG_INITIAL`, and 11 `ALL_CANDIDATES_SAME_EFFECTIVE_DAY`.

## 9. Descriptive summary

All-event medians are:

| Metric | Median % |
|---|---:|
| Gap | 0.021 |
| D0 return | -0.158 |
| D+5 return | 0.086 |
| D+10 return | 0.109 |
| D+20 return | 0.429 |
| Relative D+5 | -0.869 |
| Relative D+20 | -1.187 |

Positive D+5 returns occur in 50.28% of complete observations. Metadata retains p10, p25, p50, p75, and p90 for gap, D0/D+5/D+10/D+20, and relative D+5/D+20 across every requested grouping.

## 10. EXACT versus HEURISTIC_HIGH

| Median % | EXACT | HIGH |
|---|---:|---:|
| Gap | 0.044 | -0.267 |
| D0 | -0.141 | -0.797 |
| D+5 | 0.116 | -1.422 |
| D+10 | 0.161 | -0.844 |
| D+20 | 0.464 | -0.664 |
| Relative D+5 | -0.830 | -1.709 |
| Relative D+20 | -1.166 | -2.061 |

All 570 HIGH events have D0 and D+5; 569 have D+20. EXACT has 12,778 D0, 12,770 D+5, and 12,678 D+20 observations. HIGH is somewhat more negative across these descriptive medians, but its D0/D1 alignment is close to EXACT and does not indicate a catastrophic one-day date shift. Selection and company-population differences remain plausible confounders; no equality claim is made.

## 11. Method-level QA

| Method | N | Median gap % | Median D0 % | Median D+5 % | Median D+20 % |
|---|---:|---:|---:|---:|---:|
| CANONICAL_VERIFIED | 12,782 | 0.044 | -0.141 | 0.116 | 0.464 |
| YAHOO_NEAR_UNIQUE_SEC | 483 | -0.280 | -1.048 | -1.892 | -1.126 |
| SEC_V2_STRONG_INITIAL | 76 | -0.152 | 0.483 | 1.375 | 2.884 |
| ALL_CANDIDATES_SAME_EFFECTIVE_DAY | 11 | -2.210 | -0.585 | 0.291 | -0.481 |

The 11-event same-effective-day method is explicitly a small sample and must not be over-interpreted. Its D1-heavy diagnostic warrants continued observation, not a heuristic change in this task. Yahoo and V2 populations differ descriptively but neither shows an implausible systematic displacement.

## 12. Event-day shift diagnostic

Among available EXACT events, D0 has the larger absolute close move in 9,460 cases and D1 in 3,311, with seven ties. This is approximately 74.0% D0 versus 25.9% D1.

Among HIGH events, D0 is larger in 407 cases and D1 in 163: 71.4% versus 28.6%. By method, V2 is 60/16, Yahoo 343/140, and same-effective-day 4/7. The broad EXACT/HIGH similarity argues against an obvious global one-day shift. The diagnostic is a QA signal, not proof of timestamp correctness.

## 13. Representative examples

| Event | D-1 date / close | D0 open / close | D+1 date / close | Gap % | D0 % | D+5 % | Method / canonical |
|---|---|---|---|---:|---:|---:|---|
| AAPL 2026-Q3 | 07-30 / 333.43 | 304.81 / 308.91 | 08-03 / 303.42 | -8.58 | -7.35 | -6.03 | canonical / yes |
| NVDA 2027-Q2 | 08-26 / 209.66 | 222.86 / 227.98 | 08-28 / 217.55 | 6.30 | 8.74 | 8.96 | canonical / yes |
| CF 2025-Q1 | 05-07 / 78.86 | 82.30 / 79.47 | 05-09 / 80.54 | 4.36 | 0.78 | 7.49 | same-effective / no |
| ABG 2025-Q1 | 04-28 / 224.45 | 212.16 / 216.26 | 04-30 / 218.14 | -5.48 | -3.65 | -1.86 | Yahoo / no |
| ORN 2025-Q3 | 10-28 / 8.67 | 8.67 / 10.21 | 10-30 / 11.31 | 0.00 | 17.76 | 26.87 | Yahoo / no |
| DTE 2025-Q1 | 04-30 / 132.56 | 133.53 / 131.44 | 05-02 / 131.94 | 0.73 | -0.85 | -0.94 | V2 / no |
| GSIT 2026-Q2 | 10-30 / 11.06 | 10.00 / 9.09 | 11-03 / 9.70 | -9.58 | -17.81 | -21.97 | V2 / no |

Every D0 date equals the retained publication boundary.

## 14. Performance

The retained production build measured 0.064 seconds for publication preflight/load, 7.528 seconds for event-window construction, and 0.328 seconds for summary generation. OHLC is read through one read-only connection, SPY is loaded once, and each ticker history is loaded once. No concurrency was required.

## 15. Safety and limitations

All SQLite access uses URI `mode=ro` and `query_only=ON`. Output is limited to runtime export paths. No path writes to Fundamentals, forecasts, publication authority, or scheduler state.

V1 limitations:

- observations are unadjusted beyond the values already present in `osakedata.db`;
- this is current-snapshot descriptive research, not a point-in-time history of OHLC revisions;
- SPY is a broad market comparator, not a sector or risk-model adjustment;
- method groups differ in composition and size, so descriptive differences are not causal evidence;
- the D0/D1 diagnostic cannot independently establish correct publication timing;
- future incomplete windows naturally fill only after a new explicit rebuild.

## 16. Recommendation

Keep this V1 frozen and use it for descriptive stratification only. The next reviewed step should investigate the 11 same-effective-day events and matched-sample EXACT-versus-HIGH differences while controlling for event year, market capitalization proxy, and absolute gap bucket. Do not alter publication heuristics or create a trading signal from the aggregate differences alone.

Gate: `EVENT_WINDOW_RESEARCH_V1_READY`.
