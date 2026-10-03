# Result-publication EXACT vs HEURISTIC_HIGH matched comparison V1

Date: 2026-10-03

Version: `result_publication_exact_vs_high_matched_v1`

Decision: `MATCHED_COMPARISON_SUPPORTS_CURRENT_HEURISTIC`

## 1. Objective

This read-only study tests whether the descriptive EXACT versus HEURISTIC_HIGH differences in the frozen Event-Window Research V1 remain after matching observable event composition. It also rechecks all 11 `ALL_CANDIDATES_SAME_EFFECTIVE_DAY` events. It does not change publication authority, the heuristic, the event boundary, or any trading signal.

## 2. Frozen input proof

The sole outcome input was `exports/result_publication/result_publication_event_window_v1_2026-09-29.csv`. Its SHA-256 is `85eda92a912299d7beea3b3e11da2d118cd5d53a682b2735983f2b0a7d732af1`, it has 13,352 rows, its statuses are exactly `EXACT` and `HEURISTIC_HIGH`, and its adjacent metadata identifies `result_publication_event_window_v1`. The module rejects hash, row-count, status, version, column, and duplicate-identity drift. It never rebuilds the frozen input.

## 3. Market-cap proxy

The proxy is the latest positive `valuation_revised_result.market_cap` by `fiscal_sequence` for each company in the active generation's `fundamentals_analysis.db`. The database was opened with SQLite `mode=ro` and `query_only=ON`. This is a current stable company-level proxy, not event-date market capitalization.

The proxy covers 2,088 distinct event companies and 556 of 570 HIGH events. Tertiles are based on one value per covered event company: SMALL below 1,057,977,282.48; MID from that boundary to below 6,497,210,151.67; LARGE at or above the second boundary.

## 4. Bucket definitions

- Event year is the actual `D0_date` year.
- Absolute gap uses `abs(gap_pct)`: `[0,1)`, `[1,3)`, `[3,5)`, `[5,10)`, and `[10,infinity)` percent.
- Pre-event trend uses `return_Dm5_to_Dm1`: strong negative `<=-5`, negative `(-5,-1)`, flat `[-1,1]`, positive `(1,5)`, and strong positive `>=5` percent.
- Market cap uses the three broad proxy buckets above.

## 5. Matching algorithm

Each eligible HIGH event receives one EXACT control from exactly the same event year, market-cap bucket, absolute-gap bucket, and trend bucket. HIGH rows and tie-break identities are sorted by `(company_id, fiscal_year, fiscal_quarter)`. Within a stratum the selected unused control minimizes absolute-gap distance, then pre-event-trend distance, then stable identity. Matching is 1:1 without replacement; ticker is never identity.

## 6. Match coverage

| Measure | Count |
|---|---:|
| HIGH total | 570 |
| HIGH eligible | 556 |
| HIGH matched | 556 |
| HIGH unmatched | 14 |
| EXACT controls used | 556 |
| Controls reused | 0 |
| Maximum control uses | 1 |

All 14 unmatched HIGH events lack the market-cap proxy. Every otherwise eligible HIGH event has an unused same-stratum EXACT control.

## 7. Balance before and after

Categorical total-variation distance in percentage points fell as follows:

| Variable | Before | After |
|---|---:|---:|
| Event year | 11.068 | 0.000 |
| Market-cap bucket | 5.439 | 0.000 |
| Absolute-gap bucket | 6.991 | 0.000 |
| Pre-event-trend bucket | 2.342 | 0.000 |

Continuous standardized mean differences were:

| Variable | Before | After |
|---|---:|---:|
| Market-cap proxy | -0.120 | -0.091 |
| Absolute gap | -0.127 | 0.002 |
| Pre-event trend | 0.028 | -0.033 |

The post-match median absolute gap is 3.791% for HIGH and 3.830% for EXACT. Median pre-event trend is 0.172% versus 0.399%. Broad cap buckets are exact, while residual within-bucket cap imbalance remains small but nonzero.

## 8. Matched outcome comparison

Values are percentages. `N` can differ at D+10/D+20 because the frozen event windows retain incomplete future offsets.

| Outcome / group | N | Median | P25 | P75 | Mean | Positive % |
|---|---:|---:|---:|---:|---:|---:|
| Gap HIGH | 556 | -0.304 | -4.248 | 3.087 | -0.430 | 45.50 |
| Gap EXACT | 556 | 0.000 | -3.728 | 3.864 | 0.023 | 49.28 |
| D0 HIGH | 556 | -0.842 | -6.260 | 4.152 | -0.890 | 46.22 |
| D0 EXACT | 556 | -0.066 | -5.332 | 5.097 | 0.011 | 48.02 |
| D+5 HIGH | 556 | -1.574 | -8.682 | 5.491 | -1.183 | 45.50 |
| D+5 EXACT | 556 | 0.390 | -6.729 | 7.143 | 3.233 | 51.26 |
| D+10 HIGH | 556 | -0.970 | -10.325 | 7.062 | -0.865 | 46.22 |
| D+10 EXACT | 555 | 0.613 | -7.444 | 9.246 | 3.740 | 51.71 |
| D+20 HIGH | 555 | -1.122 | -11.715 | 9.899 | 0.551 | 47.03 |
| D+20 EXACT | 549 | 0.514 | -9.413 | 11.020 | 5.038 | 51.37 |
| Relative D+5 HIGH | 556 | -1.775 | -8.867 | 5.519 | -1.460 | 42.81 |
| Relative D+5 EXACT | 556 | -0.120 | -7.308 | 5.950 | 2.446 | 48.92 |
| Relative D+20 HIGH | 555 | -2.519 | -10.804 | 9.068 | 0.062 | 42.52 |
| Relative D+20 EXACT | 549 | -0.138 | -10.678 | 9.765 | 3.709 | 49.73 |

The group-median difference remains, especially after D0. Wide overlapping interquartile ranges, residual unobserved composition, and a few large observations make the means unsuitable as causal evidence.

## 9. Paired differences

Median paired `HIGH - EXACT` differences are:

| Outcome | Paired N | Median difference |
|---|---:|---:|
| D0 | 556 | 0.031 |
| D+5 | 556 | -1.335 |
| D+10 | 555 | -1.079 |
| D+20 | 548 | -1.834 |
| Relative D+5 | 556 | -1.218 |
| Relative D+20 | 548 | -1.655 |

The near-zero paired D0 median does not support systematic boundary displacement. The later negative differences remain descriptive and are not explained fully by the four matching dimensions.

## 10. HIGH method-level results

| Method | Matched N | D0 median HIGH / EXACT | D+5 median HIGH / EXACT | D+20 median HIGH / EXACT |
|---|---:|---:|---:|---:|
| `YAHOO_NEAR_UNIQUE_SEC` | 471 | -1.103 / -0.023 | -2.027 / 0.381 | -1.371 / 0.897 |
| `SEC_V2_STRONG_INITIAL` | 74 | 0.483 / -0.611 | 1.258 / 1.134 | 2.487 / 0.209 |
| `ALL_CANDIDATES_SAME_EFFECTIVE_DAY` | 11 | -0.585 / -3.520 | 0.291 / -1.887 | -0.481 / -0.262 |

The broad negative result is concentrated in the Yahoo-near population. V2 and the 11-case group do not reproduce it consistently. The 11-case group is too small for generalization.

## 11. Same-effective-day QA

Every case has two SEC Item 2.02 conflict rows. Candidate timestamps were converted to America/New_York and independently mapped to the frozen D0. The QA CSV retains both complete source references, accessions, D-1/D0/D+1 dates and prices, Yahoo evidence, and the classification.

| Event | SEC local evidence | Yahoo implies | D-1 / D0 open / D0 close / D+1 close | Larger move | Class |
|---|---|---|---|---|---|
| ARKO 2026-Q2 | Aug 6 AFTER; Aug 7 PRE -> Aug 7 | Aug 7 | 7.29 / 6.76 / 5.66 / 4.70 | D0 | CONFIRMED |
| CF 2025-Q1 | May 7 AFTER x2 -> May 8 | May 8 | 78.86 / 82.30 / 79.47 / 80.54 | D1 | CONFIRMED |
| CF 2025-Q2 | Aug 6 AFTER x2 -> Aug 7 | Aug 7 | 88.37 / 82.77 / 81.48 / 79.53 | D0 | CONFIRMED |
| CF 2025-Q3 | Nov 5 AFTER x2 -> Nov 6 | Nov 6 | 84.10 / 82.24 / 80.54 / 81.11 | D0 | CONFIRMED |
| CF 2025-Q4 | Feb 18 AFTER x2 -> Feb 19 | Feb 19 | 95.82 / 97.00 / 99.46 / 97.18 | D0 | CONFIRMED |
| CF 2026-Q1 | May 6 AFTER x2 -> May 7 | May 7 | 119.76 / 114.10 / 118.68 / 115.02 | D1 | CONFIRMED |
| CF 2026-Q2 | Aug 5 AFTER x2 -> Aug 6 | Aug 6 | 116.71 / 111.99 / 116.73 / 114.35 | D1 | CONFIRMED |
| FIS 2025-Q4 | Feb 24 PRE x2 -> Feb 24 | Feb 24 | 47.46 / 48.30 / 48.11 / 49.07 | D1 | CONFIRMED |
| MNTK 2025-Q2 | Aug 6 AFTER; Aug 7 PRE -> Aug 7 | Aug 7 | 2.08 / 1.80 / 1.95 / 1.77 | D1 | CONFIRMED |
| MNTK 2025-Q4 | Mar 11 AFTER; Mar 12 PRE -> Mar 12 | Mar 12 | 1.37 / 1.43 / 1.41 / 1.35 | D1 | CONFIRMED |
| MNTK 2026-Q2 | Aug 5 AFTER; Aug 6 PRE -> Aug 6 | Aug 6 | 1.71 / 1.69 / 1.70 / 1.79 | D1 | CONFIRMED |

Classification counts are 11 `BOUNDARY_CONFIRMED`, zero `BOUNDARY_PLAUSIBLE`, and zero `BOUNDARY_QUESTIONABLE`. No candidate implies a different first full trading day. The 7-to-4 D1-heavy split therefore fits small-sample continuation better than date misalignment.

## 12. Matched shift diagnostic

| Group | D0 larger | D1 larger | D0 share |
|---|---:|---:|---:|
| Matched HIGH | 398 | 158 | 71.58% |
| Matched EXACT | 393 | 163 | 70.68% |

Matching makes the shift diagnostic slightly closer than the prior unmatched comparison. There is no systematic one-day shift signal.

## 13. Limitations

- Matching is descriptive, deterministic, and limited to four observed dimensions; it cannot establish causality or remove sector, liquidity, issuer-quality, or method-selection differences.
- Market cap is a current revised-history proxy, not point-in-time event-date market cap.
- Fourteen HIGH events are excluded for missing market cap.
- Broad cap buckets leave modest within-bucket imbalance.
- Outcome means are sensitive to large observations; medians and interquartile ranges are the primary summaries.
- Yahoo remains secondary evidence. It corroborates these 11 daily boundaries but does not become canonical authority.

## 14. Database and scheduler safety

The active canonical `fundamentals_v4.db`, active market-cap `fundamentals_analysis.db`, `forecasts.db`, and `osakedata.db` were opened read-only. Their pre-task hashes were respectively `765a5efdc601dc99c6969ef0e3fe80c2206472b91437486cf5b6b73fa8370a89`, `6c1487278f25eb118ecfb4312966ba65b8a241ff0d20694d698f097e06c95b23`, `d31d72a7ab74340a15adfc8cdf5573f64bb2b17fd2c292a515f381b056f172cc`, and `c04c7fc523f966f649aecc3d6e58885f5cb61cc6e4a4656c45fadb8cba66e168`. Post-task hashes matched. `PRAGMA quick_check` returned `ok` for all four.

For context only, the current forecast database contains 11 runs, 59,202 fetches, and 20,914 snapshots. No forecast or scheduler state was written, and no systemd or scheduler file was changed.

## 15. Outputs and recommendation

Runtime artifacts are:

```text
exports/result_publication/result_publication_exact_vs_high_matched_v1_2026-10-03.csv
exports/result_publication/result_publication_exact_vs_high_matched_v1_2026-10-03.metadata.json
exports/result_publication/result_publication_same_effective_day_qa_2026-10-03.csv
```

The matched CSV has SHA-256 `0e7725604a547fb62f5d5e0936554c492afc355c1ffc6d1608cb628bb9b54e7a`; the QA CSV has SHA-256 `9a55071d246b223106e9e25db2a79692a8694443a8128f57237918dc45ae99b3`.

Keep the current heuristic unchanged. The exact next reviewed step is a narrow Yahoo-near subgroup analysis adding sector and liquidity/volatility controls before any interpretation of its negative D+5 to D+20 difference; continue to prohibit authority writes and trading-signal use.

Gate: `MATCHED_COMPARISON_SUPPORTS_CURRENT_HEURISTIC`.
