# Fundamentals V4 Lifecycle V1 Specification

Status: `PURE_METHODOLOGY_IMPLEMENTED_NOT_PRODUCTION_ACTIVE`

Model version: `V4_FUNDAMENTAL_LIFECYCLE_V1`

Model fingerprint: `db72e072fc2f0d9e3ceb13db1ee4cc92045383a5f44bfb65d21858b80190832f`

## Purpose and exclusions

Lifecycle V1 describes a company's current operational economic phase. It is independent of Fundamental Score and does not measure investment quality. Score, price, returns, valuation, leverage, debt, dilution, sector ranks, percentiles and future outcomes are not inputs.

The economic states are `STARTUP`, `DISTRESSED`, `SCALING`, `GROWTH`, `MATURE`, `DECLINING`, `STRUGGLING` and `TRANSITION`. `UNCLASSIFIED` is a technical result, not an economic state. Startup profiles are `PRE_REVENUE` and `REVENUE_GENERATING`.

## Metrics

For positive current TTM Revenue:

```text
G      = RevenueTTM_t / RevenueTTM_t_minus_4 - 1
M      = EBITTTM_t / RevenueTTM_t
DeltaM = M_t - M_t_minus_4
F      = FCFTTM_t / RevenueTTM_t
```

Lag4 is the exact fiscal predecessor four canonical fiscal quarters earlier. `G` and `DeltaM` require a valid canonical fiscal chain plus positive current and lag4 Revenue TTM. `M` requires observed current EBIT TTM. `F` requires observed current FCF TTM. Internal percentages are decimal fractions. Rule comparisons use decimal arithmetic from source values so strict boundaries are not changed by binary-float artifacts. Returned metrics are not rounded before classification.

## Raw-state priority

Rules are evaluated in this exact order. The first eligible matching rule wins.

### 1. PRE_REVENUE STARTUP

Before any margin division, classify `STARTUP / PRE_REVENUE` only when TTM is core-ready, exactly four input-quarter Revenue values are observed, every one is exactly zero, current EBIT TTM is strictly negative and current FCF TTM is strictly negative. A negative quarterly or TTM Revenue does not qualify. Zero TTM Revenue that fails any condition is `UNCLASSIFIED`.

### 2. DISTRESSED

Requires positive current Revenue TTM and observed current EBIT and FCF. Lag4 is not required.

```text
M < -0.20 and F < -0.20
```

### 3. Revenue-generating STARTUP

Requires `G`, `M` and `F`.

```text
G > 0.30 and M < -0.05 and F < 0
```

Result profile: `REVENUE_GENERATING`.

### 4. SCALING

Requires `G`, `M` and `DeltaM`.

```text
G > 0.10 and M >= 0 and DeltaM > 0
```

SCALING intentionally precedes GROWTH.

### 5. GROWTH

Requires `G`, `M` and `DeltaM`.

```text
G > 0.20 and M < 0.10 and DeltaM >= -0.05
```

### 6. MATURE

Requires all four metrics.

```text
M >= 0.15 and F >= 0.05 and G >= -0.05 and DeltaM >= -0.05
```

### 7. DECLINING

Requires `G`, `M` and `DeltaM`.

```text
G < -0.05 or DeltaM < -0.05
```

DECLINING intentionally precedes STRUGGLING.

### 8. STRUGGLING

Requires all four metrics.

```text
(M < 0 or F < 0) and G >= -0.05 and DeltaM >= -0.05
```

### 9. TRANSITION

TRANSITION is the residual economic class only when all four metrics are valid and no earlier rule matched. It never absorbs incomplete observations.

## Missing-data matrix

| Class | Required inputs |
|---|---|
| PRE_REVENUE STARTUP | Four observed exact-zero Revenue quarters, negative EBIT TTM and negative FCF TTM |
| DISTRESSED | Positive current Revenue TTM, current EBIT TTM and current FCF TTM |
| Revenue-generating STARTUP | `G`, `M`, `F` |
| SCALING | `G`, `M`, `DeltaM` |
| GROWTH | `G`, `M`, `DeltaM` |
| MATURE | `G`, `M`, `DeltaM`, `F` |
| DECLINING | `G`, `M`, `DeltaM` |
| STRUGGLING | `G`, `M`, `DeltaM`, `F` |
| TRANSITION | `G`, `M`, `DeltaM`, `F` |

Missing input skips only rules that require it. For example, missing FCF prevents DISTRESSED and STARTUP evaluation but does not prevent a complete SCALING, GROWTH or DECLINING classification. Missing FCF cannot fall through to TRANSITION. Missing lag4 history prevents every history-dependent class; only an already matched DISTRESSED observation can classify without lag4. No lifecycle input is imputed.

## UNCLASSIFIED and reason codes

Every technical result has:

```text
raw_state = UNCLASSIFIED
lifecycle_status = LIFECYCLE_NOT_READY
current final_state = NULL in state-machine output
```

The engine returns deterministic reason codes in these groups:

- TTM/source readiness: `TTM_NOT_READY`, `TTM_MODEL_VERSION_UNSUPPORTED`, `SOURCE_AVAILABILITY_DATE_MISSING`, `SOURCE_AVAILABILITY_DATE_INVALID`.
- Current inputs: `CURRENT_REVENUE_MISSING`, `CURRENT_REVENUE_INVALID`, `CURRENT_REVENUE_NEGATIVE`, `CURRENT_EBIT_MISSING`, `CURRENT_EBIT_INVALID`, `CURRENT_FCF_MISSING`, `CURRENT_FCF_INVALID`.
- Pre-revenue evidence: `PRE_REVENUE_QUARTER_COUNT_INVALID`, `PRE_REVENUE_QUARTER_REVENUE_MISSING`, `PRE_REVENUE_QUARTER_REVENUE_INVALID`, `ZERO_REVENUE_PRE_REVENUE_CONDITIONS_NOT_MET`.
- Lag4 evidence: `FISCAL_CHAIN_INVALID`, `LAG4_REVENUE_MISSING`, `LAG4_REVENUE_INVALID`, `LAG4_REVENUE_NONPOSITIVE`, `LAG4_EBIT_MISSING`, `LAG4_EBIT_INVALID`.
- Final fallback: `REQUIRED_METRICS_MISSING`.

Ready classifications carry a corresponding `CLASSIFIED_*` reason code. `missing_inputs` identifies the specific unavailable or invalid fields.

## State machine

The first economic raw state is confirmed immediately. Later ordinary transitions require two consecutive identical economic raw states. A first differing observation starts a candidate at count one; a repeated candidate confirms it; return to the confirmed state clears it; a different candidate replaces it and restarts at one. No adjacent-state path is forced.

DISTRESSED entry is immediate and clears any candidate. Exit from confirmed DISTRESSED requires two consecutive identical non-DISTRESSED states. Different recovery states do not combine.

UNCLASSIFIED publishes `LIFECYCLE_NOT_READY`, `final_state = NULL`, clears the candidate and does not count toward confirmation. `last_confirmed_state` is preserved only as explicit history. It must not be presented as the current reliable class.

## Replay input contract

Pure observations retain company/security identity, fiscal year/quarter, endpoint quarter id, period end, source availability date, source data version and model identity. Replay consumes a non-decreasing source-availability sequence and never mutates prior inputs or outputs. Equal availability dates retain caller-established deterministic order.

RawCandle does not preserve a complete historical lifecycle information-version chain and does not claim an investor-knowable PIT lifecycle history. The revised-history implementation replays the currently accepted canonical and TTM history in canonical fiscal-quarter order and labels it `REVISED_HISTORY`. Restatements may therefore change earlier lifecycle results retrospectively.

## Scope boundary

Phase 2A contains only the pure classifier, state machine, tests and documentation. It performs no database read or write, migration, production backfill, scheduler/report integration or activation. Lifecycle V1 does not alter Score V1 behavior, rows, version or fingerprint.

## Revised-history persistence contract

Phase 2C persists the current-canonical interpretation under the explicit mode `REVISED_HISTORY`. One active row is allowed for each company, fiscal quarter, lifecycle model fingerprint and history mode. A source restatement may change an earlier row and all later confirmed states, so refresh replays the complete affected company. Full-universe rebuild uses the same path.

Current and history readers require an explicit model fingerprint. The current reader selects the greatest canonical fiscal sequence even when it is `UNCLASSIFIED`; in that case it returns `LIFECYCLE_NOT_READY` and no current economic class. `last_confirmed_state` remains audit data only.

The persistence layer does not change the methodology contract, model version, fingerprint, thresholds, priorities, missing-data matrix or state machine.
