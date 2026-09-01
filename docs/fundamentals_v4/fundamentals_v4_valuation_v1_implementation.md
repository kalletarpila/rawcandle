# Fundamentals V4 Absolute Valuation Score V1

## Status

Phase 3B implements the canonical earnings foundation, temporary migration, read-only observation adapter, and pure calculation engine. It does not migrate production, persist valuation results, backfill history, or activate a pipeline hook.

Model version: `ABSOLUTE_VALUATION_SCORE_V1`

Model fingerprint: `17a9c388647f9e810b9a88b5de1de764a1cb9f406c0f9e4f602da87b285ef62f`

## Purpose and non-goals

Valuation Score measures how cheaply or expensively the market prices currently realized EBIT, free cash flow, and common-shareholder earnings. It is an absolute 0-100 score. It is not fair value, a return forecast, a growth adjustment, investment quality, or a guaranteed margin of safety.

The model has no Lifecycle-dependent weights, percentile ranks, sector ranks, taxonomy ranks, ecosystem ranks, own-history ranks, forward estimates, non-GAAP inputs, PEG, DCF, imputation, or weight transfer. Relative layers are deferred.

## Canonical common earnings

The additive field contract is:

```text
provider netinccmn
-> canonical net_income_common
-> ttm_net_income_common = SUM(four contiguous canonical quarters)
```

`net_income <- netinc` and `ttm_net_income` remain unchanged. `net_income_common_4q_ready` is independent from existing core TTM readiness. The valuation engine never reads provider `payload_json`; the temporary production-source rehearsal adapter uses exact existing provenance only because production has not yet received the Phase 3B schema migration.

Schema version `v4_3b_valuation_foundation` and `migrate_valuation_foundation(...)` are tested against temporary databases only.

## Date and price contract

```text
fundamental_available_date = ttm_source_available_date
price_date = latest complete valid OHLC date <= fundamental_available_date
maximum fallback = 3 calendar days
```

The adapter never searches forward. All OHLC fields must be finite and positive, high must be the row maximum bound, and low the row minimum bound. The selected `close` is used as stored without a dividend transformation. Price and shares are treated as retrospectively split-compatible under the project policy.

Dates have no trusted intraday filing timestamp. History is revised economic history and must not be described as exact investor-visible PIT history. Sector and industry metadata are also current/revised rather than historical PIT taxonomy.

## Controlled formulas

```text
market_cap = selected_close * shares_outstanding
net_debt = total_debt - cash
enterprise_value = market_cap + total_debt - cash

ebit_yield = ttm_ebit / enterprise_value
fcf_yield = ttm_free_cashflow / market_cap
earnings_yield = ttm_net_income_common / market_cap
```

Sharadar ready-made price, market cap, EV, P/E, and valuation ratios are not engine inputs.

## Absolute anchors

Scores use continuous piecewise-linear interpolation and clamp only at the documented first and last anchors.

| Yield | EBIT /40 | FCF /40 | Common earnings /20 |
|---:|---:|---:|---:|
| 0% | 0 | 0 | 0 |
| 2% | 6 | 5 | 3 |
| 4% | 14 | 12 | 7 |
| 6% | 22 | 20 | 11 |
| 9% | 31 | - | 16 |
| 10% | - | 30 | - |
| 15% | 40 | - | 20 |
| 20% | - | 40 | - |

Values between listed anchors interpolate. Values below or equal to zero receive zero points. Values above a component's last anchor receive its maximum. Total score is exactly EBIT points + FCF points + earnings points.

## Applicability

Applicability is separate from mathematical scoring and uses normalized exact `ticker_meta.sector` and `ticker_meta.industry` values.

- The nine reviewed `REIT - ...` industries are `UNSUPPORTED_REIT_MODEL`.
- `Banks - Diversified` and `Banks - Regional` are `UNSUPPORTED_BANK_MODEL`.
- The six reviewed insurance industries, including insurance brokers, are `UNSUPPORTED_INSURANCE_MODEL`.
- Asset Management, Capital Markets, Credit Services, Financial Conglomerates, Mortgage Finance, and Shell Companies are `UNSUPPORTED_FINANCIAL_MODEL`.
- `Financial Data & Stock Exchanges` remains supported as an operating-company model.
- Real Estate Development, Real Estate Diversified, and Real Estate Services remain supported.
- Nine named non-financial sectors remain supported.
- Missing or unrecognized classification returns `VALUATION_NOT_READY`; it is not silently included or excluded.

Unsupported company types return `VALUATION_NOT_APPLICABLE` and no numeric score. They do not receive economic zero.

## Status and edge cases

`VALUATION_FULL` requires supported classification, ready core TTM, valid fiscal chain and availability date, mapped security/ticker, a valid price within three days, positive shares and market cap, observed cash/debt, positive EV, and all three observed TTM numerators.

`VALUATION_NOT_READY` has one deterministic primary reason. `EV <= 0` returns `ENTERPRISE_VALUE_NONPOSITIVE`; it never receives full EBIT points and prevents a comparable total score. Missing common earnings returns `COMMON_EARNINGS_HISTORY_INCOMPLETE`.

Nonpositive EBIT, FCF, and common earnings are observed economic values and receive zero component points. Their weights are not transferred. Positive, zero, and negative net debt all use the same EV formula when resulting EV remains positive.

## Fingerprints and transparency

The model fingerprint hashes model version, formulas, weights, anchors, interpolation, nonpositive rules, EV rule, price rule, applicability sets, full-readiness requirements, deterministic decision precedence, statuses, no-imputation policy, and no-weight-transfer policy. It excludes paths and timestamps.

Every result exposes identity, fiscal endpoint, availability and price dates, price age, price, shares, market cap, cash, debt, net debt, EV, all TTM numerators, raw yields, component points, total score, status, reason, model fingerprint, and logical result fingerprint. Sorted compact JSON serialization is deterministic.

## Phase 3B rehearsal

The read-only production-source rehearsal generated 50,585 logical observations:

- `VALUATION_FULL`: 39,117
- `VALUATION_NOT_APPLICABLE`: 2,903, all current-universe-history REIT classifications
- `VALUATION_NOT_READY`: 8,565

The full-score median was 24.17; P10/P25/P75/P90/P99 were 0.00/0.00/48.33/70.98/99.89. Exact zero was 29.64% and exact 100 was 0.98% of full rows. The difference from Phase 3A's 41,576 formula-ready rows is primarily the newly explicit REIT applicability exclusion.

Not-ready reasons were 7,642 core TTM not ready, 862 nonpositive EV, 40 missing price, 8 missing/nonpositive shares, 7 unrecognized classifications, and 6 price fallbacks older than three calendar days. Score-band counts were 17,950 / 8,299 / 6,357 / 4,006 / 2,505 from the 0-20 band through the 80-100 band. Component-point correlations were EBIT/earnings 0.9277, EBIT/FCF 0.5610, and FCF/earnings 0.5143.

The Phase 3B artifact is under `temp/fundamentals_v4_valuation_phase3b/20260901T_phase3b/rehearsal.json`. It contains the complete component raw-value and point distributions plus representative samples. Two independent runs were byte-identical; their replay fingerprint is `d0422935f59366f602b5f397da10533af88d9aac52264db2257e4a7358f389cd`.

## Future filing-date and daily snapshot distinction

This engine constructs filing/availability-date revised-history observations. A future daily valuation snapshot may reuse the pure formulas, but it must have a separate observation-date contract and must not be mixed into this history without an explicit model contract.

## Phase 3C persistence preparation

Phase 3C adds copy-only canonical/common-earnings migration, versioned `valuation_revised_result` persistence, explicit-fingerprint readers, guarded rehearsal tooling, quick checks, a mandatory exact-zero audit and a separate current-universe distribution. Production remains unmigrated and contains no valuation rows. See `fundamentals_v4_valuation_v1_phase3c_report.md` and `fundamentals_v4_valuation_v1_phase3d_runbook.md`.
