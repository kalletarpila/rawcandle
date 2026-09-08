# Fundamentals V4 Relative Valuation V1 Specification

## Identity and boundary

- Model: `CURRENTLY_REVISED_RELATIVE_VALUATION_V1`
- Fingerprint: `76c2974108b2c5085b7dfa102acd4bb04eea36a5267bbdb1930a2bc7dc8cb35e`
- Semantic mode: `CURRENTLY_REVISED_NOT_PIT`
- Authoritative absolute model: `ABSOLUTE_VALUATION_SCORE_V2`
- This model is separate from Fundamental Score, Lifecycle, Absolute Valuation,
  Fundamental Delta, Diagnostic Flags, and filing-date Relative Position.
- It does not produce a combined opportunity score or predict returns.

Phase 11B is calculation and candidate-report work only. It creates no
production schema, persistence, activation, report publication, or UI default.

## Current-price valuation

The current calculation calls the authoritative Absolute Valuation Score V2
engine. It does not copy its scoring curves.

```text
Market Cap = selected current close * endpoint shares outstanding
EV = Market Cap + endpoint total debt - endpoint cash
Operating yield = TTM Operating Income / EV
FCF yield = TTM FCF / Market Cap
Reported Common Earnings yield = TTM Reported Common Earnings / Market Cap
```

All fundamental values come from one latest eligible TTM endpoint. Price is the
latest complete, finite, positive OHLC close on or before the explicit as-of
date. Its maximum age is seven calendar days. Future prices, an eight-day or
older fallback, a second split adjustment, currency inference, EBIT/EBITDA
fallback, dividends, forward estimates, P/B, normalized earnings, and
missing-component reweighting are forbidden.

## Current peer percentiles

Only current-fresh `VALUATION_FULL` observations enter cohorts. Current
fundamental freshness is at most 180 calendar days. The scopes and minimum
counts are:

| Scope | Minimum peers |
| --- | ---: |
| Universe | 2 |
| Sector | 20 |
| Industry | 10 |
| Ecosystem | 20 |

For an exact score tie:

```text
average_rank = (rank_low + rank_high) / 2
percentile = 100 * (average_rank - 1) / (peer_count - 1)
```

Values are not rounded before ranking. A company appears once in an ecosystem,
even with duplicate qualifying memberships. Only active `CORE` and `EXTENDED`
memberships qualify. Missing identity or classification, non-membership, and a
small cohort are explicit. There is no broader-group fallback and no taxonomy
layer rank.

## Own positive-yield history

History is currently revised fiscal history, not reconstructed PIT history.
Every endpoint uses its own eligible filing-date close, shares, cash, debt, and
TTM numerator. Filing-price fallback remains three calendar days.

The window is the trailing five calendar years through the explicit as-of date,
then the latest 20 eligible endpoints by authoritative fiscal sequence. February
29 subtracts to February 28 when the target year is not a leap year. Endpoints
may be nonconsecutive; missing quarters are neither interpolated nor replaced.
Fiscal gaps are counted.

Each component independently classifies every selected endpoint:

- positive finite numerator and positive denominator: positive history
- zero or negative finite numerator and positive denominator: nonpositive
  exclusion
- missing/nonfinite numerator, missing/nonfinite denominator, or nonpositive
  denominator: missing or invalid exclusion.

Operating yield requires positive EV. FCF and Reported Common Earnings yields
require positive Market Cap. The three positive populations need not contain
the same quarters. For each component the result records total selected
observations, positive/nonpositive/invalid counts, full observation bounds,
positive-history bounds, current yield, positive-history median, percentile,
status, and reason. Even-size medians are the arithmetic mean of the two middle
binary64 values.

The current observation is external to history:

```text
component percentile = 100 * (less_count + 0.5 * equal_count) / n
```

Thus the range is 0 to 100 and equality with every historical observation is
50. Full binary64 values are used without pre-rounding.

## Readiness

Component statuses:

| Condition | Status |
| --- | --- |
| At least 12 positive observations | `COMPONENT_HISTORY_READY` |
| 8 to 11 positive observations | `COMPONENT_HISTORY_LIMITED` |
| Fewer than 8 positive observations | `COMPONENT_HISTORY_INSUFFICIENT` |
| Current yield is zero or negative | `CURRENT_YIELD_NONPOSITIVE` |
| Current component is absent | `CURRENT_COMPONENT_MISSING` |
| Current component is nonfinite | `CURRENT_COMPONENT_NONFINITE` |
| Current valuation/freshness is not ready | `CURRENT_VALUATION_NOT_READY` |
| Absolute valuation is not applicable | `VALUATION_NOT_APPLICABLE` |

A component percentile is emitted only from eight positive observations onward
and a finite, strictly positive current yield. Signed nonpositive current yields
remain visible with component-specific reason codes.

Aggregate formula:

```text
Own-History Valuation Percentile =
    0.40 * Operating-yield percentile
  + 0.40 * FCF-yield percentile
  + 0.20 * Reported Common Earnings-yield percentile
```

Aggregate precedence is `NOT_APPLICABLE`, `CURRENT_VALUATION_NOT_READY`,
`CURRENT_YIELD_NOT_COMPARABLE`, `INSUFFICIENT_HISTORY`, `LIMITED_HISTORY`, then
`READY`. `READY` requires all components to have at least 12 positive values.
`LIMITED_HISTORY` requires every component to have at least 8 and at least one
to have 8-11. No aggregate is emitted for any earlier status. Missing or
noncomparable components are never reweighted, while independently valid
component evidence remains available.

## Interpretation

A high peer percentile means a company is cheap relative to current eligible
peers under Absolute Valuation Score V2. A high own-history percentile means it
is cheap relative to its own positive, economically comparable historical
yields. Neither implies fundamental strength or predicts a price increase.
