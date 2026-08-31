# Fundamentals V4 Score V1 Locked Specification

Version: `V4_FUNDAMENTAL_SCORE_V1`
Fingerprint: `68601dda8d4e873e58a134c286f5d0468bfefa58dfec84920d4596412371b3ff`

Score semantic: `CURRENT_FUNDAMENTAL_STATE`.

Delta Score semantic: `CHANGE_IN_FUNDAMENTAL_STATE`.

Objective: estimate how strong the company's fundamental condition is now. Stock returns, OHLCV returns, future fundamental improvement, Lifecycle output and Valuation output are not inputs or optimization targets.

Top-level weights are locked at 25/15/15/15/10/15/5 for a total of 100 points.

Each component is an independent continuous absolute scale from 0 to its component maximum. Missing components are not reweighted to 100; total Score is the direct sum of component points.

Time split uses `ttm_source_available_date`; `period_end` remains the economic quarter label and is not used as the primary split key.

Future validation states are retained as diagnostics only. They are not an acceptance criterion and are not used to fit scoring curves.

## Growth and earnings development (25 points)

Economic purpose: measure revenue expansion and EBIT development without double-counting price momentum.

Raw inputs and scoring curves:

- `revenue_growth_yoy_ttm`: piecewise_linear, 10 points, higher is better; low=-0.1, neutral=0.0, high=0.25
- `ebit_development_quality`: piecewise_linear, 15 points, higher is better; low=0.0, neutral=0.5, high=1.0

History requirement: current TTM plus same fiscal quarter one year earlier.
Missing-data treatment: component can be partial, but readiness/confidence records missing material inputs; missing values are never converted to zero.
Denominator guard: ratios return missing when denominator is null, zero, near zero, or economically invalid for that ratio.
Outlier treatment: bounded curves cap the score impact; valid distressed or high-growth observations remain in the sample.

## Profitability level (15 points)

Economic purpose: measure current EBIT margin strength on normalized TTM fundamentals.

Raw inputs and scoring curves:

- `ebit_margin_ttm`: piecewise_linear, 15 points, higher is better; low=0.0, neutral=0.1, high=0.25

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

`SCORE_READY` requires current TTM readiness, availability date, and at least 80 available component weight. `SCORE_READY_WITH_LIMITED_COMPONENT` requires at least 65 available component weight. Otherwise the row is `SCORE_NOT_READY`. Available component points are summed directly and are never scaled up to 100.

Known gaps are propagated through blocker/readiness flags. CIK NULL and permaticker NULL do not automatically block scoring; historical gaps block only windows whose required feature history is affected.

## Delta Score

`delta_score_1q = current_total_score - prior_quarter_total_score` when both observations are comparable scored observations for the same company. `delta_score_2q` and `delta_score_4q` follow the same arithmetic over comparable prior scored observations. Delta Score is not a separate weighted component.


## Calibration Evidence

Development score distribution: median `33.74305`, p10 `16.406353600000003`, p25 `22.484935`, p75 `47.908379249999996`, p90 `62.4683189`, floor saturation `0.0%`, ceiling saturation `0.0%`.

Component independence: highest Pearson correlation `0.6262527311515318` for `growth_earnings_development:margin_direction`; highest Spearman correlation `0.6305750150176495` for `growth_earnings_development:margin_direction`. Redundant component pairs: `[]`.

Readiness: `{'SCORE_NOT_READY': 13432, 'SCORE_READY': 30335, 'SCORE_READY_WITH_LIMITED_COMPONENT': 6818}` with readiness pct `59.96837`. Top blockers: `{'YOY_TTM_HISTORY_NOT_READY': 17802, 'CURRENT_TTM_NOT_READY': 8079, 'AVAILABILITY_DATE_MISSING': 7707, 'CONSISTENCY_HISTORY_INSUFFICIENT': 4902}`.

Development 2021-2023 4Q outcome separation: `NON_MONOTONIC_REVIEW`. Material defects: `[]`.

2024 validation 4Q outcome separation: `MOSTLY_MONOTONIC`. Refinements made: `[]`.

2025 locked OOS 4Q outcome separation: `NON_MONOTONIC_REVIEW`. Thresholds modified after viewing 2025: `NO`.

2026 forward validation: observations `7127`, fully observable 4Q targets `0`, censored/missing 4Q targets `6572`. Thresholds modified after viewing 2026: `NO`.

Final classification: `V4_SCORE_V1_CONTINUOUS_SCALING_LOCKED_IMPLEMENTATION_READY`.

Next action: `PROCEED TO V4-4: IMPLEMENT THE LOCKED V4_FUNDAMENTAL_SCORE_V1 PRODUCTION ENGINE IN RAWCANDLE, WRITE VERSIONED CONTINUOUS 0..N COMPONENT SCORES AND 0..100 TOTAL SCORES TO fundamentals_analysis.db, IMPLEMENT DELTA SCORE AS A SEPARATE DERIVED CHANGE METRIC, AND PROVE EXACT PARITY WITH THE LOCKED V4-3A SPECIFICATION BEFORE MIGRATING LIFECYCLE OR VALUATION`.
