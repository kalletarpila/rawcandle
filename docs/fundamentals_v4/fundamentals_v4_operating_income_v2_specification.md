# Fundamentals V4 Operating-Income V2 Specification

Status: `PURE_ENGINES_IMPLEMENTED_NOT_PRODUCTION_ACTIVE`

Model family: `OPERATING_INCOME_MODEL_FAMILY_V2`

## Objective and lineage

V2 corrects the operating-profit semantics used by Fundamentals V4. V1 remains historically valid as an EBIT-based model. V2 uses only:

`Sharadar opinc -> canonical operating_income -> four exact consecutive fiscal quarters -> ttm_operating_income`

There is no EBIT or EBITDA fallback, no zero substitution, no imputation and no ticker-specific exception. Availability and field readiness remain independent. Missing operating income makes the affected result missing or not ready according to the existing layer-specific status precedence.

## Fundamental Score V2

Model identifier: `SIMPLE_FUNDAMENTAL_SCORE_V2`

| Component | Maximum | Formula or policy |
|---|---:|---|
| Revenue Growth | 20 | V1 unchanged |
| Operating Profitability | 15 | `ttm_operating_income / ttm_revenue` |
| Operating Margin Direction | 15 | current operating margin minus fiscal Q-4 margin |
| FCF Margin | 15 | V1 unchanged |
| Balance Sheet Resilience | 15 | positive operating income: `(debt-cash)/ttm_operating_income`; V1 nonpositive-profit branches unchanged |
| Dilution | 10 | V1 unchanged |
| Fundamental Trajectory | 10 | revenue, operating-margin and FCF legs |

The anchors and continuous interpolation are unchanged. Operating profitability uses `0%=0`, `10%=7.5`, `25%=15`. Direction uses `-5pp=0`, `0pp=7.5`, `+5pp=15`. The direct sum of the seven components is the total; there is no dynamic reweighting.

Trajectory requires five consecutive TTM observations and four QoQ transitions. Each leg uses `clamp(5 + 5*x/T, 0, 10)`. Operating-margin `T=0.05`; zero change gives 5/10. Revenue and FCF legs retain their V1 formulas and tolerances.

## Lifecycle V2

Model identifier: `V4_FUNDAMENTAL_LIFECYCLE_V2`

Lifecycle substitutes operating income in `M` and `DeltaM`. PRE_REVENUE, DISTRESSED, STARTUP, SCALING, GROWTH, MATURE, DECLINING, STRUGGLING and TRANSITION retain all V1 thresholds, exact operators and waterfall order. UNCLASSIFIED remains the technical not-ready result. Initial confirmation, two-observation debounce, immediate DISTRESSED entry, two-matching-state exit and UNCLASSIFIED candidate reset are unchanged.

## Absolute Valuation V2

Model identifier: `ABSOLUTE_VALUATION_SCORE_V2`

The components remain 40/40/20:

- Operating income / EV: anchors `0%=0`, `2%=6`, `4%=14`, `6%=22`, `9%=31`, `15%=40`.
- FCF / Market Cap: V1 unchanged.
- GAAP common earnings / Market Cap: V1 unchanged and may contain non-operating gains or losses.

Nonpositive operating income receives zero operating-income points. Nonpositive EV, pricing, split, applicability and exclusion rules remain unchanged.

## Downstream V2 contracts

- `CURRENTLY_REVISED_FUNDAMENTAL_DELTA_V2` calculates signed QoQ, 2Q and YoY changes only between complete, model-identical V2 Score endpoints. Seven component deltas must reconcile to total Delta.
- `CURRENT_REVISED_SNAPSHOT_RELATIVE_POSITION_V2` ranks V2 Score and V2 Valuation independently in universe, sector, industry and ecosystem scopes. Source model mixing is rejected.
- `CURRENTLY_REVISED_DIAGNOSTIC_FLAGS_V2` replaces EBIT in abrupt shift, valuation-yield outlier and recent margin deceleration. Other flags and all thresholds remain unchanged.
- `CURRENT_REVISED_COMPANY_SNAPSHOT_V2` defines pre-persistence terminology and rejects mixed model bundles. Operating income is primary. Sharadar EBIT is allowed only as an explicitly labelled diagnostic reconciliation.

## Coexistence and limitations

Every calculated V2 layer has a distinct deterministic fingerprint under one family fingerprint. V1 and V2 may coexist, but readers must select one complete bundle. V2 Score with V1 Lifecycle or Valuation, V2 Delta with V1 Score, and V2 Relative Position with V1 sources are forbidden.

| Contract | Fingerprint |
|---|---|
| Model family | `634824f179652da81ea6f38962d9a7c87df37c0627fed089a918ce9efa83d8e9` |
| Fundamental Score V2 | `271585e4136f6733c047e89dac7646f2ff91f8c84b10f88c56356ad495970360` |
| Lifecycle V2 | `0502822c20501c1487d09a20a378e86c0908a0953dfcb13b384428822fc4e175` |
| Absolute Valuation V2 | `9675c2d947a86d2115f366424eab7454ec013cc100c7548af004c19c691c9aeb` |
| Fundamental Delta V2 | `c65062c1ac66f1e98ab239404dba96c43060708a35a84bcfd2ed01c30d5e2f11` |
| Relative Position V2 | `993a3cfbbfd7d724852cf78466a91edf0a1adca8cd08c35e8bcc2891a5cbe30f` |
| Diagnostic Flags V2 | `d5434e139b68ee8af44dffce34cb9225538f0badb61d5d1074fb976a4de3185d` |
| Company Snapshot V2 | `7bfa88aa64f3897ea610894a1b7a3613abfc7881d9b9ea8e26912ef0426e7ee8` |

Phase 9C contains no schema, persistence, backfill, production reader, pipeline, Scheduler UI or production report activation. Those remain Phase 9D work requiring separate authorization.
