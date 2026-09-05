# Fundamentals V4 Diagnostic Flags V1

## Purpose

`CURRENTLY_REVISED_DIAGNOSTIC_FLAGS_V1` produces seven independent review signals from validated Fundamentals V4 observations. A flag means only that a defined numerical condition was observed. It does not allege fraud, manipulation, a one-off event, acquisition, impairment, investment quality, future return, or a buy/sell recommendation.

History mode is `CURRENTLY_REVISED_DIAGNOSTIC_FLAGS`: historical observations use the latest revised canonical winners and are not point-in-time history.

## Status contract

- `EVALUATED_FLAGGED`: all required inputs were valid and the inclusive threshold was met.
- `EVALUATED_CLEAR`: all required inputs were valid and the threshold was not met.
- `FLAG_NOT_READY`: a required input, source result, prior endpoint, or valid fiscal chain was unavailable.
- `FLAG_NOT_APPLICABLE`: the company/accounting class is unsupported, or positive revenue required by the formula is not present.

Missing and non-finite values are never imputed as zero or converted to clear. Observed zero is retained where economically valid. Each result includes a deterministic reason code, effective availability date, model identifiers, and sorted scalar evidence.

## Fiscal horizon

All comparison flags use the immediately preceding fiscal quarter by `(company_id, fiscal_year, fiscal_quarter)`. A missing quarter is not bridged. Period-end and source-availability chronology must increase. The valuation flag is a current-endpoint test and has no comparison endpoint.

Let:

`R = max((abs(Revenue_t) + abs(Revenue_t-1)) / 2, 10,000,000)`

Revenue-scaled and margin flags require positive revenue at both endpoints.

## Exact flags

### Abrupt fundamental shift

`max(abs(Revenue_t - Revenue_t-1) / R, abs(EBIT_t - EBIT_t-1) / R) >= 0.20`

Revenue and EBIT triggers are retained independently as evidence.

### Earnings/cash divergence candidate

`abs((CommonEarnings_t - CommonEarnings_t-1) - (CFO_t - CFO_t-1)) / R >= 0.20`

Common earnings uses the canonical `netinccmn -> net_income_common -> ttm_net_income_common` chain.

### CAPEX intensity shift candidate

For each endpoint:

`CapexIntensity_t = abs(CapexTTM_t) / max(RevenueTTM_t, 10,000,000)`

Flag when:

`abs(CapexIntensity_t - CapexIntensity_t-1) >= 0.10`

Both endpoint revenues must be positive. The reported CAPEX cash-flow sign is normalized with `abs`; the USD 10 million floor is applied separately at both endpoints.

### Net debt shift candidate

`NetDebt = TotalDebt - Cash`

`abs(NetDebt_t - NetDebt_t-1) / R >= 0.50`

No lease, investment, or alternate debt fields are introduced.

### Valuation yield outlier

Uses the persisted Absolute Valuation Score V1 yields without reconstruction:

- EBIT / enterprise value
- FCF / market capitalization
- common earnings / market capitalization

Flag when `median(available yields) >= 0.25` OR `max(available yields) >= 0.50`. The source must be `VALUATION_FULL`. Existing valuation not-ready and not-applicable results propagate and are not clear.

### Recent margin deceleration review

`Trajectory_t >= 7.0 AND (EBITMargin_t - EBITMargin_t-1) <= -0.02`

`EBITMargin = EBITTTM / RevenueTTM`. EBIT may be zero or negative. Thus a move such as `+1% -> -3%` is evaluated and flagged when Trajectory is at least 7.

### Working capital shift candidate

`ONWC = AccountsReceivable + Inventory - AccountsPayable - DeferredRevenue`

`AssetScale = max((TotalAssets_t + TotalAssets_t-1) / 2, 10,000,000)`

`abs(ONWC_t - ONWC_t-1) / AssetScale >= 0.10`

All four ONWC components and total assets must be observed and finite at both endpoints. Both total-assets values must be strictly positive. The signed ONWC change is retained. Provider `workingcapital` is not a fallback.

## Readiness and applicability

| Flag | Current and prior requirements | Source/applicability |
|---|---|---|
| Abrupt | TTM revenue and EBIT; positive revenue; exact prior | Supported operating class |
| Earnings/cash | TTM revenue, common earnings and CFO; positive revenue; exact prior | Supported operating class |
| CAPEX intensity | TTM revenue and CAPEX; positive revenue; exact prior | Supported operating class |
| Net debt | TTM revenue, cash and total debt; positive revenue; exact prior | Supported operating class |
| Valuation | Available persisted yields | `VALUATION_FULL`; existing valuation applicability |
| Margin deceleration | TTM revenue, EBIT and current Trajectory; positive revenue; exact prior | Supported operating class; Trajectory observed |
| Working capital | Five canonical balance fields at both endpoints; positive assets; exact prior | Supported operating class; pre-revenue is allowed |

Banks, insurers, REITs and other classes excluded by the existing valuation applicability classifier are not applicable. Non-REIT real-estate operating companies remain supported. Pre-revenue and nonpositive-revenue observations are not applicable to revenue-based formulas, but can be evaluated for working capital. Staleness is a presentation-snapshot filter and does not rewrite historical economic results.

Global TTM status is retained as evidence. Readiness is flag-specific: an unrelated missing TTM measure does not suppress a flag whose own required canonical values are observed and finite.

## Evidence and versioning

Evidence contains only fiscal identities, required availability dates, source status/classification, raw inputs, signed changes, scales, calculated metrics, thresholds, operators and trigger booleans. It excludes source JSON, filing prose, inferred causes, severity, confidence and combined score.

- Model version: `CURRENTLY_REVISED_DIAGNOSTIC_FLAGS_V1`
- Evidence schema: `DIAGNOSTIC_SCALAR_EVIDENCE_V1`
- Model fingerprint: `1d985892734c1401de55d91e06bbb1f295fe247e96bb3acbffcd6272027f26ad`
- Explicitly excluded flag: `VALUATION_YIELD_DIVERGENCE_REVIEW`

The fingerprint covers the seven-name list, formulas, thresholds, operators, fiscal policy, readiness/applicability policy, status/reason contract, evidence schema and exclusions. Paths and timestamps are excluded.

## Limitations

The model is sensitive to revised accounting data, ordinary seasonality, transactions, commodity cycles, launch effects and small economic scales. It detects numerical conditions but cannot establish their cause. Phase 6B is a read-only implementation and rehearsal; it is not production persistence or deployment.
