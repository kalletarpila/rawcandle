# Fundamentals V4 Score V1 Candidate Specification

Version: `V4_FUNDAMENTAL_SCORE_V1`
Fingerprint: `c8353716be861c15754c133d4ed7f08ae0bd789ebae84219ace1ff23ad371a0c`

Objective: estimate the strength, durability and direction of a company's fundamental condition. Stock returns, OHLCV returns, Lifecycle output and Valuation output are not inputs.

Top-level weights are locked at 25/15/15/15/10/15/5 for a total of 100 points.

Time split uses `ttm_source_available_date`; `period_end` remains the economic quarter label and is not used as the primary split key.

Future validation states use absolute thresholds: EBIT growth +/-5%, EBIT margin change +/-1 percentage point, and FCF margin change +/-1 percentage point.

## Growth and earnings development (25 points)

Economic purpose: measure revenue expansion and EBIT development without double-counting price momentum.

Raw inputs and scoring curves:

- `revenue_growth_yoy_ttm`: piecewise_linear, 10 points, higher is better; low=-0.1, neutral=0.0, high=0.25
- `ebit_growth_yoy_ttm`: piecewise_linear, 10 points, higher is better; low=-0.15, neutral=0.0, high=0.3
- `ebit_transition`: ordered_state, 5 points, ordered transition mapping {"CROSSING_TO_POSITIVE": 4.5, "FLAT_ZERO_REGION": 2.0, "NEGATIVE_AND_DETERIORATING": 0.0, "NEGATIVE_BUT_IMPROVING": 3.0, "POSITIVE_AND_DECLINING": 3.5, "POSITIVE_AND_GROWING": 5.0, "POSITIVE_TURNING_NEGATIVE": 1.0}

History requirement: current TTM plus same fiscal quarter one year earlier.
Missing-data treatment: component can be partial, but readiness/confidence records missing material inputs; missing values are never converted to zero.
Denominator guard: ratios return missing when denominator is null, zero, near zero, or economically invalid for that ratio.
Outlier treatment: bounded curves cap the score impact; valid distressed or high-growth observations remain in the sample.

## Profitability level (15 points)

Economic purpose: measure current EBIT margin strength on normalized TTM fundamentals.

Raw inputs and scoring curves:

- `ebit_margin_ttm`: piecewise_linear, 15 points, higher is better; low=-0.05, neutral=0.05, high=0.2

History requirement: current ready TTM.
Missing-data treatment: component can be partial, but readiness/confidence records missing material inputs; missing values are never converted to zero.
Denominator guard: ratios return missing when denominator is null, zero, near zero, or economically invalid for that ratio.
Outlier treatment: bounded curves cap the score impact; valid distressed or high-growth observations remain in the sample.

## Margin direction (15 points)

Economic purpose: measure direction of profitability separately from absolute margin level.

Raw inputs and scoring curves:

- `ebit_margin_yoy_change`: piecewise_linear, 10 points, higher is better; low=-0.05, neutral=0.0, high=0.05
- `ebit_margin_seq_change`: piecewise_linear, 5 points, higher is better; low=-0.02, neutral=0.0, high=0.02

History requirement: current TTM, previous sequential TTM, and same fiscal quarter one year earlier.
Missing-data treatment: component can be partial, but readiness/confidence records missing material inputs; missing values are never converted to zero.
Denominator guard: ratios return missing when denominator is null, zero, near zero, or economically invalid for that ratio.
Outlier treatment: bounded curves cap the score impact; valid distressed or high-growth observations remain in the sample.

## Cash-flow quality (15 points)

Economic purpose: measure conversion of accounting earnings into free cash flow with explicit positive-EBIT guards.

Raw inputs and scoring curves:

- `fcf_to_ebit`: piecewise_linear, 10 points, higher is better; low=0.0, neutral=0.6, high=1.2
- `fcf_margin_ttm`: piecewise_linear, 5 points, higher is better; low=-0.05, neutral=0.0, high=0.12

History requirement: current ready TTM.
Missing-data treatment: component can be partial, but readiness/confidence records missing material inputs; missing values are never converted to zero.
Denominator guard: ratios return missing when denominator is null, zero, near zero, or economically invalid for that ratio.
Outlier treatment: bounded curves cap the score impact; valid distressed or high-growth observations remain in the sample.

## Development consistency (10 points)

Economic purpose: measure durability and volatility of recent fundamental development.

Raw inputs and scoring curves:

- `consistency_positive_share`: piecewise_linear, 6 points, higher is better; low=0.0, neutral=0.5, high=1.0
- `consistency_margin_volatility`: piecewise_linear, 4 points, lower is better; low=0.0, neutral=0.03, high=0.1

History requirement: at least three recent ready TTM observations; four preferred.
Missing-data treatment: component can be partial, but readiness/confidence records missing material inputs; missing values are never converted to zero.
Denominator guard: ratios return missing when denominator is null, zero, near zero, or economically invalid for that ratio.
Outlier treatment: bounded curves cap the score impact; valid distressed or high-growth observations remain in the sample.

## Balance-sheet resilience (15 points)

Economic purpose: measure debt/cash resilience conditional on profitability and cash burn.

Raw inputs and scoring curves:

- `balance_metric`: piecewise_linear, 15 points, higher is better; low=-4.0, neutral=0.0, high=2.0

History requirement: current ready TTM and endpoint cash/debt.
Missing-data treatment: component can be partial, but readiness/confidence records missing material inputs; missing values are never converted to zero.
Denominator guard: ratios return missing when denominator is null, zero, near zero, or economically invalid for that ratio.
Outlier treatment: bounded curves cap the score impact; valid distressed or high-growth observations remain in the sample.

## Dilution (5 points)

Economic purpose: penalize material share issuance while avoiding excessive reward for buybacks.

Raw inputs and scoring curves:

- `share_change_yoy`: piecewise_linear, 5 points, lower is better; low=-0.03, neutral=0.0, high=0.1

History requirement: current endpoint shares plus same fiscal quarter one year earlier.
Missing-data treatment: component can be partial, but readiness/confidence records missing material inputs; missing values are never converted to zero.
Denominator guard: ratios return missing when denominator is null, zero, near zero, or economically invalid for that ratio.
Outlier treatment: bounded curves cap the score impact; valid distressed or high-growth observations remain in the sample.

## Readiness

`SCORE_READY` requires current TTM readiness, availability date, and at least 80 available component weight. `SCORE_READY_WITH_LIMITED_COMPONENT` requires at least 65 available component weight. Otherwise the row is `SCORE_NOT_READY`.

Known gaps are propagated through blocker/readiness flags. CIK NULL and permaticker NULL do not automatically block scoring; historical gaps block only windows whose required feature history is affected.


## Calibration Evidence

Development score distribution: median `43.159591500000005`, p10 `22.6860063`, p25 `30.759539750000002`, p75 `56.058526`, p90 `67.7244247`, floor saturation `0.0%`, ceiling saturation `0.0%`.

Component independence: highest Pearson correlation `0.6081198611083947` for `growth_earnings_development:development_consistency`; highest Spearman correlation `0.6146627350653602` for `growth_earnings_development:development_consistency`. Redundant component pairs: `[]`.

Readiness: `{'SCORE_NOT_READY': 13432, 'SCORE_READY': 30335, 'SCORE_READY_WITH_LIMITED_COMPONENT': 6818}` with readiness pct `59.96837`. Top blockers: `{'YOY_TTM_HISTORY_NOT_READY': 17802, 'CURRENT_TTM_NOT_READY': 8079, 'AVAILABILITY_DATE_MISSING': 7707, 'CONSISTENCY_HISTORY_INSUFFICIENT': 4902}`.

Development 2021-2023 4Q outcome separation: `NON_MONOTONIC_REVIEW`. Material defects: `['future_4q_improving_state_not_monotonic_by_score_band']`.

2024 validation 4Q outcome separation: `MOSTLY_MONOTONIC`. Refinements made: `[]`.

2025 locked OOS 4Q outcome separation: `MOSTLY_MONOTONIC`. Thresholds modified after viewing 2025: `NO`.

2026 forward validation: observations `7127`, fully observable 4Q targets `0`, censored/missing 4Q targets `6572`. Thresholds modified after viewing 2026: `NO`.

Final classification: `V4_SCORE_V1_CALIBRATION_COMPLETE_WITH_REVIEW_ITEMS`.

Next action: `KEEP PRODUCTION SCORE WRITES FROZEN AND RESOLVE ONLY THE MATERIAL CALIBRATION / REDUNDANCY / BIAS ISSUES BEFORE LOCKING V4_FUNDAMENTAL_SCORE_V1`.
