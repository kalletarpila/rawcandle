# Yahoo-near result-publication composition analysis V1

Date: 2026-10-03

Version: `result_publication_yahoo_near_composition_v1`

Decision: `YAHOO_NEAR_DIFFERENCE_LOOKS_COMPOSITIONAL`

## 1. Objective

This read-only descriptive study compares `YAHOO_NEAR_UNIQUE_SEC` events with stronger matched `CANONICAL_VERIFIED` EXACT controls. It asks whether the Yahoo-near negative post-result profile looks like observable or residual population composition rather than publication-boundary error. It does not change authority, heuristic rules, event dates, or trading signals.

## 2. Frozen input proof

The event input is `exports/result_publication/result_publication_event_window_v1_2026-09-29.csv`, SHA-256 `85eda92a912299d7beea3b3e11da2d118cd5d53a682b2735983f2b0a7d732af1`. Preflight confirms 13,352 rows, event-window contract V1, and 483 Yahoo-near rows. No publication or event-window artifact was rebuilt.

The prior matched input is `exports/result_publication/result_publication_exact_vs_high_matched_v1_2026-10-03.csv`, SHA-256 `0e7725604a547fb62f5d5e0936554c492afc355c1ffc6d1608cb628bb9b54e7a`. Preflight confirms 556 pairs and 471 Yahoo-near pairs.

## 3. Sector source

Current Sector and Industry come only from `data/osakedata.db.ticker_meta`, opened through SQLite `mode=ro` with `query_only=ON`. All 483 Yahoo-near rows have both values. Ticker is lookup metadata, while event identity remains `(company_id, fiscal_year, fiscal_quarter)`.

Sector is an exact matching dimension. Industry has 78 categories; only 11 have at least 10 Yahoo-near events and 207 events belong to categories below 10. Industry is therefore retained for descriptive QA but not matching, which avoids excessive sparsity.

## 4. Liquidity proxy

Liquidity is median daily dollar volume, `close * volume`, over the latest 20 observed rows strictly before D0. At least 15 valid positive-close, nonnegative-volume observations are required. Missing values remain null. The tertiles among Yahoo-near plus EXACT matching-population events are:

- LOW: below 10,155,234 dollars;
- MID: 10,155,234 to below 72,726,157 dollars;
- HIGH: at or above 72,726,157 dollars.

All 483 Yahoo-near events have a usable proxy.

## 5. Volatility proxy

Volatility is sample standard deviation of daily close-to-close percentage returns, using up to 20 returns ending at D-1. Computing the earliest return may read the immediately preceding close, but no D0 or later price is read. At least 15 valid returns are required.

Tertiles are LOW below 2.089%, MID from 2.089% to below 3.420%, and HIGH at or above 3.420%. All 483 Yahoo-near events have a usable proxy.

## 6. Matching algorithm

The treatment population is only `YAHOO_NEAR_UNIQUE_SEC`; the control pool is only EXACT `CANONICAL_VERIFIED`. Matching is deterministic 1:1 without replacement.

Event year, market-cap bucket, absolute-gap bucket, pre-event-trend bucket, and Sector are never relaxed. Candidate controls are attempted in this order:

1. `A_EXACT_ALL`: same liquidity and volatility bucket;
2. `B_ADJACENT_LIQUIDITY`: volatility exact, liquidity at most one adjacent bucket;
3. `C_ADJACENT_LIQUIDITY_AND_VOLATILITY`: each at most one adjacent bucket.

Constrained treatment rows are processed first. Within a level, controls minimize absolute-gap distance, trend distance, log-dollar-volume distance, volatility distance, and stable identity in that order.

## 7. Match coverage

| Stage | Yahoo-near rows |
|---|---:|
| Total | 483 |
| Existing year/cap/gap/trend controls available | 471 |
| Plus Sector | 471 |
| Plus liquidity | 471 |
| Plus volatility; fully eligible | 471 |
| Successfully matched | 461 |
| Unmatched after eligibility | 10 |
| Ineligible, all missing market cap | 12 |

The 461 pairs use 461 unique EXACT controls. Maximum reuse is one. Relaxation distribution is 388 A, 40 B, and 33 C. Ten fully eligible events had no unused control after C; the protected dimensions were not weakened.

## 8. Balance

Post-match categorical total-variation distance is zero for event year, Sector, market-cap bucket, gap bucket, and trend bucket. It is 1.518 percentage points for both liquidity and volatility because B/C permit adjacent buckets.

| Continuous control | Pre-match SMD | Post-match SMD |
|---|---:|---:|
| Market cap | -0.135 | -0.084 |
| Absolute gap | -0.121 | 0.015 |
| Pre-event trend | 0.020 | 0.036 |
| Median dollar volume | -0.105 | -0.084 |
| Realized volatility | 0.039 | 0.127 |

Post-match medians are 3.855% versus 3.846% absolute gap, 0.098% versus 0.521% trend, 25.21M versus 25.81M dollar volume, and 3.224% versus 3.177% volatility for Yahoo-near versus EXACT. Volatility balance is acceptable but weaker after the documented adjacent-bucket relaxation.

## 9. Outcome comparison

Returns are percentages. Primary interpretation uses medians and IQR; means are secondary.

| Outcome / group | N | Median | P25 | P75 | Mean | Positive % |
|---|---:|---:|---:|---:|---:|---:|
| Gap Yahoo-near | 461 | -0.507 | -4.412 | 3.067 | -0.574 | 44.47 |
| Gap EXACT | 461 | 0.000 | -3.727 | 3.846 | 0.020 | 49.24 |
| D0 Yahoo-near | 461 | -1.115 | -6.473 | 4.277 | -1.128 | 44.90 |
| D0 EXACT | 461 | -0.625 | -5.084 | 5.348 | 0.099 | 44.69 |
| D+5 Yahoo-near | 461 | -2.050 | -9.438 | 5.248 | -1.782 | 43.38 |
| D+5 EXACT | 461 | 0.259 | -6.724 | 7.767 | 1.048 | 51.41 |
| D+10 Yahoo-near | 461 | -1.550 | -11.024 | 6.848 | -1.605 | 44.47 |
| D+10 EXACT | 460 | 0.073 | -8.369 | 9.635 | 1.426 | 50.65 |
| D+20 Yahoo-near | 460 | -1.498 | -12.128 | 9.690 | -0.922 | 45.65 |
| D+20 EXACT | 456 | 1.758 | -9.178 | 14.502 | 3.438 | 53.07 |
| Relative D+5 Yahoo-near | 461 | -2.204 | -9.417 | 5.241 | -2.037 | 41.21 |
| Relative D+5 EXACT | 461 | -0.904 | -7.352 | 7.059 | 0.138 | 45.99 |
| Relative D+20 Yahoo-near | 460 | -3.118 | -11.624 | 8.777 | -1.247 | 41.09 |
| Relative D+20 EXACT | 456 | -0.072 | -9.620 | 12.570 | 2.094 | 49.56 |
| Post-D0 to D+5 Yahoo-near | 461 | -0.375 | -6.061 | 4.574 | -0.486 | 47.94 |
| Post-D0 to D+5 EXACT | 461 | 0.580 | -4.352 | 5.241 | 0.932 | 53.58 |
| Post-D0 to D+10 Yahoo-near | 461 | -0.785 | -7.670 | 5.985 | -0.325 | 45.99 |
| Post-D0 to D+10 EXACT | 460 | 0.315 | -5.702 | 5.841 | 1.176 | 51.96 |
| Post-D0 to D+20 Yahoo-near | 460 | -0.700 | -10.073 | 8.742 | 0.331 | 48.04 |
| Post-D0 to D+20 EXACT | 456 | 2.256 | -7.163 | 10.637 | 3.050 | 57.89 |

Stronger matching does not remove the later descriptive difference. Its wide overlapping IQRs and heterogeneous sectors remain important.

## 10. Paired differences

Median paired `YAHOO_NEAR - EXACT` differences are:

| Outcome | Paired N | Median difference |
|---|---:|---:|
| D0 | 461 | 0.145 |
| D+5 | 461 | -2.044 |
| D+10 | 460 | -1.490 |
| D+20 | 455 | -2.615 |
| Relative D+5 | 461 | -1.162 |
| Relative D+20 | 455 | -2.407 |
| Post-D0 to D+5 | 461 | -1.115 |
| Post-D0 to D+20 | 455 | -2.295 |

These are descriptive pair contrasts, not causal estimates.

## 11. Post-D0 analysis

The paired D0 median is close to zero at +0.145 percentage points. Post-D0 paired medians are -1.115 points through D+5 and -2.295 through D+20. Group medians likewise diverge after D0: post-D0-to-D+20 is -0.700% for Yahoo-near versus +2.256% for EXACT.

The added controls do not explain away this later difference. Its timing argues against a simple one-trading-day publication-boundary error and instead leaves residual issuer, event, surprise-detail, or selection composition as plausible explanations.

## 12. Shift diagnostic

| Group | D0 larger | D1 larger | D0 share |
|---|---:|---:|---:|
| Yahoo-near | 330 | 131 | 71.58% |
| EXACT | 333 | 128 | 72.23% |

The groups are nearly identical. There is no systematic D1 displacement after stronger matching.

## 13. Sector breakdown

| Sector | N | Yahoo D0 | Yahoo D+5 | Yahoo D+20 | EXACT D+20 | Paired D+20 |
|---|---:|---:|---:|---:|---:|---:|
| Basic Materials | 19 | -2.152 | 0.579 | 8.640 | -1.802 | 10.785 |
| Consumer Cyclical | 41 | -1.971 | -2.128 | -5.306 | -2.518 | -7.527 |
| Consumer Defensive | 22 | -1.638 | -3.669 | -7.632 | 1.665 | -12.133 |
| Energy | 45 | -0.734 | 3.331 | 7.643 | 2.767 | 4.145 |
| Healthcare | 201 | -1.538 | -3.297 | -4.218 | 4.199 | -5.666 |
| Industrials | 54 | 0.135 | -1.741 | -2.421 | 1.907 | -2.113 |
| Technology | 73 | -1.048 | -2.050 | -1.124 | -2.163 | 0.032 |

Communication Services (N=5) and Utilities (N=1) are sparse and excluded from interpretation. Healthcare is 201/461 matched events and is the largest negative contributor. Consumer Defensive and Consumer Cyclical are also negative, while Energy and Basic Materials are positive. Sector concentration is substantial, but exact Sector matching shows that sector weights alone do not remove the difference.

## 14. Liquidity and volatility stratification

All 483 Yahoo-near events show a clear liquidity gradient:

| Liquidity | N | Median D0 | Median D+5 | Median D+20 |
|---|---:|---:|---:|---:|
| LOW | 155 | -2.113 | -3.193 | -2.006 |
| MID | 175 | -1.048 | -2.612 | -0.911 |
| HIGH | 153 | 0.120 | 0.784 | -0.245 |

The volatility view is strongest at D0 and D+5:

| Volatility | N | Median D0 | Median D+5 | Median D+20 |
|---|---:|---:|---:|---:|
| LOW | 95 | 0.267 | 0.793 | -1.511 |
| MID | 167 | -0.366 | -1.078 | -0.941 |
| HIGH | 221 | -1.747 | -3.136 | -1.140 |

Poor D0/D+5 outcomes concentrate in low-liquidity and high-volatility names. D+20 is less monotonic. These are compositional associations, not causes.

## 15. Earnings-surprise check

An existing clean optional field was available in `forecast_earnings_history_reference.surprise_percent`. The latest observed Yahoo provider reference was joined by `company_id` and canonical `period_end`; it was not used for matching.

Among matched rows, surprise is available for 305 Yahoo-near and 272 EXACT events. Positive surprises are 200/305 (65.6%) versus 181/272 (66.5%), and median surprise is 0.068 versus 0.072. This partial current-reference sample does not explain the later difference and is not point-in-time event evidence.

## 16. Foreign and calendar composition

All 483 Yahoo-near tickers have `ticker_meta.market=usa`, and none has a dotted foreign-market suffix. Current local metadata has no reliable issuer-domicile or ADR flag, so foreign-issuer and ADR over-representation cannot be asserted or excluded.

Canonical period-end patterns are 401 calendar-quarter month ends, 38 nonstandard month ends, and 44 week-based/non-month-end observations. Nonstandard calendars are present but are not the majority.

## 17. Manual QA

The deterministic sample covers low/high liquidity, low/high volatility, the strongest negative and positive sector medians, and a one-trading-day Yahoo-edge case. It selected XPON, IBM, MPLX, GME, STZ, MLM, and ADSK.

Five cases have D0 as the larger move and two have D1. The one-day-edge case, ADSK 2025-Q1, has D0 as the larger move and positive D+5/D+20 returns. Price sequences and retained boundaries show heterogeneous continuation/reversal behavior, not a repeated one-day alignment error.

## 18. Limitations

- Market cap, Sector, Industry, and forecast surprise use current revised metadata rather than historical point-in-time classifications.
- Twelve Yahoo-near events lack market cap; ten more cannot receive an unused control without weakening protected dimensions.
- Liquidity and volatility buckets are broad; B/C leave small bucket imbalance and volatility SMD 0.127.
- Sector matching does not control fine industry, issuer quality, guidance, event content, or detailed surprise composition.
- The optional surprise check has incomplete coverage and Yahoo-provider semantics.
- Issuer domicile and ADR status are unavailable locally.
- Outcomes remain descriptive and must not be interpreted as a strategy or causal effect.

## 19. Safety

The active `fundamentals_v4.db`, active `fundamentals_analysis.db`, `osakedata.db`, and `forecasts.db` were opened read-only. Their pre/post SHA-256 hashes were unchanged: canonical `765a5efdc601dc99c6969ef0e3fe80c2206472b91437486cf5b6b73fa8370a89`, analysis `6c1487278f25eb118ecfb4312966ba65b8a241ff0d20694d698f097e06c95b23`, OHLC `c04c7fc523f966f649aecc3d6e58885f5cb61cc6e4a4656c45fadb8cba66e168`, and forecasts `d31d72a7ab74340a15adfc8cdf5573f64bb2b17fd2c292a515f381b056f172cc`. Each `PRAGMA quick_check` returned `ok`.

Forecast context is 11 runs, 59,202 fetches, and 20,914 snapshots. No scheduler, systemd, authority, forecast, Fundamentals, or OHLC state was written.

## 20. Recommendation

The later difference persists after stronger matching, so the measured controls do not explain it away. Nevertheless, D0 paired alignment, the nearly identical D0/D1 diagnostic, post-D0 onset, sector/liquidity/volatility heterogeneity, and manual QA provide no evidence of systematic publication-boundary error. The result therefore looks like residual composition or selection, especially in Healthcare and lower-liquidity/higher-volatility names, rather than date displacement.

Retain the current heuristic. The exact next reviewed step is a descriptive within-Healthcare and low-liquidity Yahoo-near analysis using fine Industry and available earnings-surprise sign as stratifiers, while keeping event boundaries frozen and making no authority or signal changes.

Runtime outputs:

```text
exports/result_publication/result_publication_yahoo_near_composition_v1_2026-10-03.csv
exports/result_publication/result_publication_yahoo_near_composition_v1_2026-10-03.metadata.json
```

CSV SHA-256: `cb74d5f11bf9756e7bd5941cc1ba88e5c4aa9bcd974a0828005210541d540134`.

Gate: `YAHOO_NEAR_DIFFERENCE_LOOKS_COMPOSITIONAL`.
