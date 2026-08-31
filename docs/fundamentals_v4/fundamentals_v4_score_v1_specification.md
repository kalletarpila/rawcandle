# Fundamentals V4 Score V1 Specification

Status: `IMPLEMENTED`

Model identifier: `SIMPLE_FUNDAMENTAL_SCORE_V1`

This specification supersedes the V4-3A `V4_FUNDAMENTAL_SCORE_V1` design. Git history preserves that design; it is not an alternative active Score V1 specification.

## Purpose

Score V1 measures current absolute fundamental strength, direction, cash generation, balance-sheet resilience, ownership dilution, and operating stability. It is not a percentile rank and is not optimized against stock returns or future fundamental outcomes.

| Component | Maximum |
|---|---:|
| Revenue Growth | 20 |
| EBIT Profitability | 15 |
| EBIT Margin Direction | 15 |
| FCF Margin | 15 |
| Balance Sheet Resilience | 15 |
| Dilution | 10 |
| Consistency | 10 |
| Total | 100 |

All ratios are decimal fractions. For example, `0.10` means 10%, and a margin change of `0.05` means five percentage points. Component calculations retain full floating-point precision. Presentation rounding does not change stored or downstream values.

## Common scoring rule

Each anchor table defines a bounded continuous piecewise-linear function. Values between adjacent anchors are linearly interpolated. Values outside the first and last anchors receive the endpoint score. Missing is distinct from zero.

The canonical score is the direct sum of observed and explicitly imputed component points. It must never use `100 * observed_points / available_weight` or otherwise dynamically reweight available components to 100.

## Revenue Growth: 20 points

`revenue_growth_yoy_ttm = revenue_ttm_current / revenue_ttm_4q_ago - 1`

The snapshots must be exactly four fiscal quarters apart in one continuous canonical fiscal chain. Both revenue values must be positive and observed.

| Revenue growth | Points |
|---:|---:|
| `<= -0.10` | 0 |
| `0.00` | 7 |
| `0.10` | 12 |
| `0.20` | 16 |
| `>= 0.30` | 20 |

## EBIT Profitability: 15 points

`ebit_margin_ttm = ebit_ttm / revenue_ttm`

Revenue must be positive and observed. There is no EBITDA fallback.

| EBIT margin | Points |
|---:|---:|
| `<= 0.00` | 0 |
| `0.10` | 7.5 |
| `>= 0.25` | 15 |

## EBIT Margin Direction: 15 points

`ebit_margin_direction = ebit_margin_ttm_current - ebit_margin_ttm_4q_ago`

The unit is a decimal-fraction difference. The snapshots must be exactly four fiscal quarters apart in one continuous canonical fiscal chain. There is no separately scored sequential margin metric.

| YoY EBIT-margin change | Points |
|---:|---:|
| `<= -0.05` | 0 |
| `0.00` | 7.5 |
| `>= 0.05` | 15 |

## FCF Margin: 15 points

`fcf_margin_ttm = free_cash_flow_ttm / revenue_ttm`

Canonical `free_cash_flow` is provider FCF and reconciles to operating cash flow plus signed capex. Revenue must be positive and observed. `fcf_to_ebit` is not a Score V1 input.

| FCF margin | Points |
|---:|---:|
| `<= -0.05` | 0 |
| `0.00` | 3 |
| `0.05` | 7 |
| `0.10` | 11 |
| `>= 0.20` | 15 |

## Balance Sheet Resilience: 15 points

`net_debt = total_debt - cash`

When `ebit_ttm > 0`, calculate `net_debt_to_ebit = net_debt / ebit_ttm`:

| Net debt / EBIT | Points |
|---:|---:|
| `<= 0` | 15 |
| `1` | 12 |
| `2` | 8 |
| `3` | 4 |
| `>= 4` | 0 |

When `ebit_ttm <= 0`, use exactly these branches:

| Condition | Points |
|---|---:|
| `net_debt <= 0` and `free_cash_flow_ttm >= 0` | 10 |
| `net_debt <= 0` and `free_cash_flow_ttm < 0` | 5 |
| `net_debt > 0` | 0 |

Cash, total debt, EBIT, and FCF must all be observed. No cash-runway model or alternate balance ratio is part of Score V1.

The 4x zero-point floor is intentionally conservative and locked. Development sensitivity was 42.29% at 4x, 35.25% at 5x, and 30.23% at 6x. In the 4x-or-higher group, median net debt/revenue was 88.78% versus 11.09% below 4x. This supports an economic leverage distinction rather than a distribution-fitting relaxation.

## Dilution: 10 points

Scored metric:

`share_change_yoy = stored_period_end_basic_shares_current / stored_period_end_basic_shares_4q_ago - 1`

Provider field semantics are:

- `sharesbas`: actual period-end basic common shares outstanding;
- `shareswa`: period weighted-average basic shares used for Basic EPS;
- `shareswadil`: period weighted-average diluted shares used for Diluted EPS.

`sharesbas` is the correct economic field family. `shareswa` and `shareswadil` must not replace it because that would change the component into an EPS-denominator measure.

| YoY share change | Points |
|---:|---:|
| `<= -0.02` | 10 |
| `0.00` | 8 |
| `0.02` | 5 |
| `0.05` | 2 |
| `>= 0.10` | 0 |

### Locked local-data policy

The local V4 `shares_outstanding <- sharesbas` values are used directly. The local examples reviewed around known splits were already on a comparable stored basis, so the Score engine must not apply a second mechanical split adjustment. `osakedata.db.splits_data` events in the YoY comparison interval are retained in component evidence only.

A positive YoY share change above 50% is classified as `ASSUMED_GENUINE_DILUTION_BY_POLICY`, receives 0 points under the locked anchors, and is not a data-quality blocker. This is an explicit owner-approved policy for this private-use application. External event verification is not required for Score readiness.

Sequential `share_change_qoq` is stored as evidence for event timing only. It is not scored. YoY remains the scored metric so that a large issuance affects the ownership comparison for the full four-quarter window rather than only the first sequential observation.

No Dilution imputation is allowed. The historical provisional median remains diagnostic only.

## Consistency: 10 points

Use the latest four contiguous score-eligible quarterly TTM snapshots ending at the score date. If four are unavailable, use three contiguous snapshots. All snapshots must belong to one continuous canonical fiscal chain, use the same dates for all metrics, and contain Revenue Growth YoY TTM, EBIT Margin TTM, and FCF Margin TTM. Do not skip an internal missing quarter. Otherwise Consistency is missing.

For each adjacent pair and each metric:

`normalized_instability = clamp(abs(current - previous) / tolerance, 0, 1)`

| Metric | Tolerance |
|---|---:|
| Revenue Growth YoY TTM | `0.20` (20 percentage points) |
| EBIT Margin TTM | `0.05` (5 percentage points) |
| FCF Margin TTM | `0.10` (10 percentage points) |

For each metric, average its adjacent normalized-instability values. Give the three metric instabilities equal weight:

`average_instability = mean(revenue_instability, ebit_margin_instability, fcf_margin_instability)`

`consistency_points = clamp(10 * (1 - average_instability), 0, 10)`

This measures stability of metric levels. It can penalize a large favorable change; EBIT Margin Direction separately rewards favorable EBIT-margin improvement. This behavior is intentional.

Development evidence contained 10,310 observed values: P10 1.88894, P25 4.69422, median 7.00875, P75 8.35267, and P90 8.98712. Zero saturation was 2.19% and full-score saturation 0%. The tolerances are economically interpretable and non-degenerate, so they are locked unchanged.

The fixed Consistency imputation value is `6.988540590181791`. It is the median of the five development-cutoff medians, giving each cutoff equal weight.

## Point-in-time and freshness contract

The primary time key is `ttm_source_available_date`. `period_end` identifies the economic quarter and must not determine when data became knowable.

For an as-of date, select at most one snapshot per security: the latest ready canonical TTM snapshot whose source availability date is on or before the as-of date. No later information may enter the score.

A snapshot older than 180 calendar days at the as-of date is not score-eligible. This two-reporting-cycle maximum is explicit rather than inferred from `period_end`. Development P90 ages were at most 67 days, and the rule removed fewer than 1% of TTM-ready rows at each development cutoff.

Historical and delisted securities remain eligible while they have a valid, fresh point-in-time snapshot. Current active status is not a calibration filter.

## Score statuses

`SCORE_FULL` requires all seven observed components and no imputation.

`SCORE_READY_ESTIMATED` requires all five core components (Revenue Growth, EBIT Profitability, EBIT Margin Direction, FCF Margin, and Balance Sheet Resilience), observed Dilution, and missing Consistency replaced by its locked imputation.

The only locked optional imputation is Consistency at `6.988540590181791`. Dilution is never imputed.

`SCORE_LIMITED` applies when the current TTM snapshot is usable but one or more required components remain missing and the exact Consistency-only imputation rule does not produce `SCORE_READY_ESTIMATED`.

`SCORE_NOT_READY` applies when no usable current TTM snapshot exists, source-availability semantics are unusable, multiple material inputs are absent, or even a diagnostic result would be misleading.

Every result must separately expose observed points, imputed points, total points, observed component count, and status. Complete and estimated scores are canonical only under their respective statuses. Limited results are diagnostic only.

## Calibration contract

The original 2021-2023 split is not a complete three-year development sample. Revenue Growth and Margin Direction have zero observations through 2022-Q3, only three at 2022-Q4, and broad coverage beginning in 2023-Q2. Consistency has only 3 observations at 2023-Q2 and 74 at 2023-Q3, reaching 1,989 at 2023-Q4.

The smallest defensible revised split is:

- development: quarter-end as-of cutoffs from 2023-12-31 through 2024-12-31;
- validation: quarter-end as-of cutoffs from 2025-03-31 through 2025-12-31;
- untouched forward validation: 2026.

Each cutoff uses one latest known snapshot per security and the 180-day freshness rule. Anchors are absolute economic thresholds; cross-sectional percentiles only test coverage and saturation. Neither future fundamentals nor stock returns fit the model.

The canonical `fundamentals_v4.db` universe already excludes banks, insurers, REITs, and other true financial companies upstream. Score calibration therefore applies no additional sector, industry, name, ticker, exchange, security-status, or current-active filter. The absence of point-in-time sector/industry columns in the V4 contract limits composition reporting, but it is not a Score V1 readiness blocker because the excluded company types are not present in the canonical universe.

## Explicit exclusions

Score V1 excludes Lifecycle, Lifecycle multipliers, Valuation, stock-return inputs, future-fundamental optimization, production percentile scoring, `ebit_development_quality`, separately scored sequential margin direction, `fcf_to_ebit`, positive-test-based `fundamental_persistence`, complex cash-runway branches, and dynamic reweighting to 100.

## Production implementation

`rawcandle/fundamentals/score/engine.py` implements this contract and writes results to the existing `fundamentals_analysis.db` tables. It does not change the analysis, canonical-quarter, or TTM schemas. Phase 1B made no production database changes; V4-4 introduced the production Score rows.
