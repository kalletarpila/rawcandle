# Fundamental Delta V1 Specification

## Meaning

`CURRENTLY_REVISED_FUNDAMENTAL_DELTA_V1` is the signed change in the complete locked Fundamental Score between comparable fiscal endpoints. Its semantic mode is `CURRENTLY_REVISED_FUNDAMENTAL_HISTORY_DELTA`. A positive value is improvement in Score points, a negative value is deterioration, and exact zero means no point change. Missing or non-comparable data is always an explicit status, never zero.

The canonical horizons are:

```text
QOQ         = Score(t) - Score(t-1)
TWO_QUARTER = Score(t) - Score(t-2)
YOY         = Score(t) - Score(t-4)
```

`TWO_QUARTER` may be displayed as "2Q change" or "6M change". It is not named `HOH`, because the endpoints are TTM-based Score observations rather than two six-month financial statements.

There is no weighted horizon aggregate, 0-100 Delta Score, combined Fundamental and Valuation Delta, or imputation.

## Fiscal Chain

Stable `company_id` and fiscal identity select endpoints. Ticker and physical row order do not. QoQ requires sequences `t-1...t`, 2Q requires `t-2...t`, and YoY requires `t-4...t`. Every intermediate fiscal observation must exist. The resolver supports non-calendar years, year-end transitions and 52/53-week period ends because adjacency uses fiscal year and quarter identity while dates are used only for chronology validation.

Period-end dates must increase and source availability dates must be valid ISO dates and be nondecreasing across the chain. Invalid or reversed availability chronology returns `DELTA_AVAILABILITY_CHRONOLOGY_INVALID`; endpoints are not silently changed. Duplicate company and fiscal-sequence identities are rejected before calculation.

Availability date controls when a revised-history Delta can be displayed. The calculation is not PIT replay: restatements or accepted source corrections can retrospectively change old endpoints and Deltas.

## Strict Total Eligibility

Each endpoint must:

- use Score model `SIMPLE_FUNDAMENTAL_SCORE_V1` and its exact locked fingerprint;
- be `SCORE_FULL` and `TTM_READY`;
- have a finite, non-boolean total;
- contain all seven locked components as observed finite values;
- contain no imputed or reweighted component;
- use the locked component identities and maxima on the direct 100-point denominator;
- reconcile the component sum to total within absolute tolerance `1e-9`;
- satisfy the complete fiscal-chain and availability chronology contract.

These rules are Phase 5A Candidate A. Limited, normalized, estimated, reweighted, partial and common-weight comparisons are not canonical total Delta.

## Component Contributions

Each component is calculated independently as `points(t) - points(prior)` for all three horizons. It can be ready when total Delta is unavailable if the same component is observed, finite, model-identical and maximum-identical at both endpoints and the chain is valid. Component readiness never promotes total readiness. Missing is not zero.

Every strict-ready total requires the seven component Deltas to sum to total Delta within `1e-9`. `FUNDAMENTAL_TRAJECTORY` Delta is only the change in Trajectory component points. It is not the current Fundamental Trajectory value.

## Separate Contexts

Lifecycle Change Context is categorical. It exposes current and prior final states, horizon change flags, raw state, status, persisted candidate fields, latest confirmed transition and current-state streak. It performs no ordinal arithmetic. `LIFECYCLE_NOT_READY` remains explicit and `last_confirmed_state` is only historical context.

Filing-Date Valuation Change Diagnostic subtracts persisted `VALUATION_FULL` scores at the same fiscal horizons. It requires model-identical endpoints, a valid chain, coherent price dates, finite persisted values and reconciliation of EBIT, FCF and common-earnings component changes. It combines price, shares, cash, debt, EV, TTM numerators and score saturation; it is not a pure valuation trend and does not calculate current-day Valuation.

Relative Position, peer percentiles, taxonomy changes and historical rank movement are excluded.

## Status And Provenance

The compact endpoint result retains current identity, fiscal identity, availability date, source Score status and fingerprint, three independently ready horizon records, prior endpoint references, total changes, component contributions, reconciliation and deterministic reason codes. Model, source and result fingerprints are separate. Lifecycle and Valuation use their own provenance. A combined rehearsal fingerprint is an audit package identity only, not an economic model.

## Persistence Separation And Production Boundary

Phase 5B provides the pure calculation and context engines. Phase 5C.2's non-production V2 persistence stores only Fundamental total and seven component histories. Lifecycle Change Context and filing-date Valuation Change Diagnostic are derived on demand from their authoritative revised histories; they are not copied into Delta tables and Valuation explanatory JSON is not persisted by Delta.

Phase 5C.2 created no production migration, backfill or pipeline hook. Phase 5D deployed the locked V2 layout on 2026-09-02 and activated Delta after Valuation and before Relative Position. The deployment evidence is recorded in `fundamentals_v4_delta_v1_phase5d_deployment.md`.
