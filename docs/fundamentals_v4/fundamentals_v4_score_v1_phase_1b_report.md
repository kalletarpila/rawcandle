# Fundamentals V4 Score V1 Phase 1B Report

> Historical phase report. Later owner-approved V4-4 revisions removed the Dilution upstream blocker and replaced the level-stability Consistency component with Fundamental Trajectory. The active contract is `fundamentals_v4_score_v1_specification.md`.

Status: `COMPLETE_WITH_DILUTION_UPSTREAM_BLOCKER`

Artifact root: `/home/kalle/projects/rawcandle/temp/fundamentals_v4_3b_score_methodology/20260831T_PHASE1B_LOCKED_V2`

The Phase 1B run was research-only. It opened `fundamentals_v4.db`, `fundamentals_provider.db`, and `osakedata.db` read-only; wrote only the artifact root above; did not run a production pipeline; and did not change a production database or schema.

## Locked decisions

- Active methodology identifier: `SIMPLE_FUNDAMENTAL_SCORE_V1`.
- Components: Revenue Growth 20, EBIT Profitability 15, EBIT Margin Direction 15, FCF Margin 15, Balance Sheet Resilience 15, Dilution 10, and Consistency 10.
- Continuous piecewise-linear absolute anchors remain unchanged from the Phase 1B candidates.
- Consistency uses three equally weighted normalized-instability metrics with tolerances 0.20, 0.05, and 0.10.
- Balance Sheet Resilience retains the conservative `net_debt / EBIT >= 4` zero-point floor.
- Maximum snapshot age is 180 calendar days.
- Consistency median imputation is fixed at `6.988540590181791` points.
- Dilution production scoring and imputation are blocked pending split-normalized period-end basic-share history.
- No dynamic reweighting to 100 is allowed.

## Corrected as-of cross-sections

For each quarter-end cutoff, the run selected the latest TTM snapshot per security whose `ttm_source_available_date` was no later than the cutoff. Current active status was not a filter. `ready` below means core-TTM-ready and no more than 180 days old.

| Cutoff | Eligible | TTM ready | Score ready | Growth non-null | Consistency non-null | Age P50 | Age P90 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2021-12-31 | 29 | 5 | 5 | 0 | 0 | 49 | 52 |
| 2022-03-31 | 96 | 89 | 89 | 0 | 0 | 9 | 36 |
| 2022-06-30 | 2,260 | 2,180 | 2,180 | 0 | 0 | 55 | 63 |
| 2022-09-30 | 2,304 | 2,260 | 2,259 | 0 | 0 | 56 | 64 |
| 2022-12-31 | 2,328 | 2,286 | 2,278 | 3 | 0 | 57 | 65 |
| 2023-06-30 | 2,358 | 2,335 | 2,329 | 2,028 | 3 | 56 | 64 |
| 2023-09-30 | 2,374 | 2,356 | 2,351 | 2,090 | 74 | 54 | 65 |
| 2023-12-31 | 2,396 | 2,366 | 2,356 | 2,104 | 1,989 | 54 | 66 |
| 2024-03-31 | 2,401 | 2,385 | 2,377 | 2,127 | 2,045 | 37 | 60 |
| 2024-06-30 | 2,415 | 2,389 | 2,377 | 2,140 | 2,065 | 54 | 66 |
| 2024-09-30 | 2,428 | 2,407 | 2,399 | 2,156 | 2,099 | 54 | 66 |
| 2024-12-31 | 2,441 | 2,423 | 2,410 | 2,168 | 2,112 | 54 | 67 |
| 2025-03-31 | 2,441 | 2,435 | 2,420 | 2,187 | 2,117 | 34 | 55 |
| 2025-06-30 | 2,442 | 2,438 | 2,427 | 2,204 | 2,136 | 54 | 66 |
| 2025-09-30 | 2,443 | 2,440 | 2,427 | 2,215 | 2,159 | 55 | 64 |
| 2025-12-31 | 2,446 | 2,439 | 2,430 | 2,211 | 2,170 | 55 | 64 |

The earlier availability-quarter grouping was not a valid cross-section. The corrected evidence also shows that 2021-2023 is not three complete development years. Growth and Margin Direction become broad only in 2023-Q2, and Consistency becomes broad only in 2023-Q4.

The revised split is 2023-Q4 through 2024-Q4 development, 2025 quarterly validation, and untouched 2026 forward validation. No 2026 cutoff or outcome was inspected by the Phase 1B runner.

## Development distributions

The table reports the median quarterly percentile and the minimum-to-maximum range across the five development cutoffs.

| Metric | P10 | P25 | P50 | P75 | P85 | P90 |
|---|---:|---:|---:|---:|---:|---:|
| Revenue Growth | -0.2226 [-0.2307,-0.1967] | -0.0599 [-0.0726,-0.0514] | 0.0327 [0.0288,0.0601] | 0.1427 [0.1292,0.1816] | 0.2486 [0.2178,0.2739] | 0.3471 [0.3021,0.4019] |
| EBIT Margin | -1.4470 [-1.6331,-1.2478] | -0.1094 [-0.1238,-0.1046] | 0.0636 [0.0617,0.0678] | 0.1646 [0.1617,0.1667] | 0.2299 [0.2279,0.2352] | 0.2873 [0.2810,0.2916] |
| EBIT Margin Direction | -0.2169 [-0.2285,-0.2102] | -0.0414 [-0.0486,-0.0361] | 0.0064 [0.0041,0.0078] | 0.0669 [0.0609,0.0686] | 0.1631 [0.1539,0.1778] | 0.3158 [0.2767,0.3706] |
| FCF Margin | -1.3372 [-1.5422,-1.2202] | -0.0900 [-0.1013,-0.0709] | 0.0504 [0.0477,0.0524] | 0.1268 [0.1222,0.1296] | 0.1782 [0.1729,0.1829] | 0.2236 [0.2181,0.2334] |
| Net debt / EBIT | -0.9897 [-1.0073,-0.8616] | 0.6402 [0.5287,0.6796] | 3.1172 [2.9105,3.1413] | 7.1115 [6.8517,7.4292] | 10.5141 [10.0494,10.7409] | 14.0285 [13.2020,14.8113] |
| Share change YoY | -0.0361 [-0.0368,-0.0346] | -0.0061 [-0.0078,-0.0060] | 0.0067 [0.0062,0.0069] | 0.0512 [0.0401,0.0575] | 0.1739 [0.1284,0.2015] | 0.3085 [0.2228,0.3857] |
| Consistency points | 1.8753 [1.6565,2.1242] | 4.7217 [4.4234,4.9753] | 6.9885 [6.7574,7.3466] | 8.3100 [8.1943,8.5162] | 8.7453 [8.6481,8.9284] | 8.9601 [8.8342,9.1145] |

Median quarterly anchor saturations were: Revenue Growth 18.41% at the floor and 11.82% at the ceiling; EBIT Margin 33.96% and 13.35%; EBIT Margin Direction 22.91% and 28.78%; FCF Margin 27.76% and 12.46%. These are broad but economically explainable bounded tails, so no anchor was moved to fit the distribution.

The complete per-cutoff P10/P25/P50/P75/P85/P90, non-null counts, saturations, and snapshot-age values are in `asof_cross_sections.csv`. `development_percentile_ranges.csv` contains the aggregate table.

Sector and industry composition could not be reported from reliable point-in-time columns. This does not affect the intended exclusions: the canonical `fundamentals_v4.db` universe already excludes banks, insurers, REITs, and other true financial companies upstream. The calibration applied no additional name, ticker, exchange, security-status, or current-active filter.

## Consistency validation

Across development cutoffs, Consistency had 10,310 observations and 1,609 missing values. P10/P25/P50/P75/P90 were 1.88894/4.69422/7.00875/8.35267/8.98712. Zero saturation was 2.19%; full-score saturation was 0%.

There were 8,175 equivalent new/legacy pairs. Pearson correlation was 0.398. The moderate relationship is expected: legacy used coefficient-of-variation denominators and EBITDA margin, while V1 uses bounded absolute changes and EBIT margin. The new formula better preserves the legacy intent of rewarding stability without unstable near-zero denominators.

Representative examples from the development sample:

| Type | Ticker | Consistency | Current EBIT margin | Current FCF margin | YoY EBIT-margin direction |
|---|---|---:|---:|---:|---:|
| Stable strong | AME | 9.7304 | 0.2531 | 0.2445 | -0.0008 |
| Stable weak | UNFI | 9.4903 | -0.0017 | -0.0015 | -0.0113 |
| Steadily improving | TJX | 9.7317 | 0.1107 | 0.0774 | 0.0089 |
| Steadily weakening | ACI | 9.7552 | 0.0219 | 0.0104 | -0.0049 |
| Volatile | ADAM | 0.0000 | -0.7924 | -0.2007 | 12.9568 |

Stable weak companies can score highly because Consistency measures stability, not quality. Large favorable and unfavorable changes can both reduce the component; Margin Direction separately rewards favorable EBIT-margin change.

## Dilution audit

`sharesbas` is period-end basic shares, `shareswa` is weighted-average basic shares, and `shareswadil` is weighted-average diluted shares. The latter two are useful corroboration but are not substitutes for ownership dilution.

The audit used exact fiscal YoY pairs through 2025-12-31 and local split records only when a split date fell inside the compared period-end interval:

| Finding | Count |
|---|---:|
| Provider YoY observations | 33,570 |
| Absolute change above 50% | 2,435 (7.25%) |
| Positive outliers | 2,363 |
| Negative outliers | 72 |
| Local split evidence | 893 |
| All three share fields corroborate | 986 |
| One weighted field corroborates | 110 |
| Unresolved | 446 |
| Current-active security | 2,379 |
| Inactive security | 56 |
| TTM revenue below 100 million | 1,966 |

The outlier rate, 893 exact-window split matches, and unresolved tail show that canonical history cannot yet support a split-normalized ownership-dilution metric. A 50% flag would expose some failures but would not repair the input. The provisional Dilution median of 6.990604216206412 is blocked from production use.

## Balance decision

Among 7,311 positive-EBIT development observations, the floor sensitivity was:

| Zero-point floor | Floor saturation | Median component points |
|---:|---:|---:|
| 4x | 42.29% | 3.7816 |
| 5x | 35.25% | 3.8908 |
| 6x | 30.23% | 3.9272 |

The 4x-or-higher group had median EBIT margin 10.45%, median net debt/revenue 88.78%, 69.69% at net debt/revenue of at least 50%, and 14.26% at net debt/EBIT of at least 20x. The below-4x group had median EBIT margin 13.57% and median net debt/revenue 11.09%. Cash and total debt were present for every development row used in this comparison. The 4x floor is retained for economic conservatism, not distribution shaping.

## Reproducibility

Research entry point:

`python3 -m rawcandle.fundamentals.score.methodology --repo-root /home/kalle/projects/rawcandle --timestamp 20260831T_PHASE1B_LOCKED_V2`

Focused test:

`pytest -q tests/test_fundamentals_v4_score_methodology.py`

Artifact SHA-256 values:

| Artifact | SHA-256 |
|---|---|
| `methodology_summary.json` | `c790574d2349d71024128b0ff61e4cd15ac129a7ec38e166ba3078cb81e1c7b8` |
| `asof_cross_sections.csv` | `5817787c03a3c1eface682e84802bbbea3b35a73fd1ed1bd303b1c912d98c244` |
| `development_percentile_ranges.csv` | `af8633a3c2ae40c4e0c91d0df73c3270e3a2ff93fb0c483ee02b4a153436e493` |
| `consistency_examples.csv` | `e883fd2b397da4d3d79fabd765f328e5106c600dd23451cb875acb8eb1a0d6e9` |
| `balance_sensitivity.csv` | `2a4a7d4d534f6df2eee7d9b6ccc7846363619f652a84c86929a97520d5fbb206` |
| `dilution_outlier_strata.csv` | `08353c212788df12ac63162fc9592099109bf0096943b3e30c45598ba4ffed36` |
| `dilution_outlier_sample.csv` | `15ecbdca4cfec3b9ed590b7e935431d37a2c24a014d1b31def0287eae5a8f7a5` |

The remaining upstream blocker is split-normalized period-end share history. Point-in-time sector/industry composition reporting remains unavailable, but financial-company and REIT exclusion is not a blocker because those company types are absent from the canonical universe. No production Score implementation should claim full readiness until the share-history contract exists.
