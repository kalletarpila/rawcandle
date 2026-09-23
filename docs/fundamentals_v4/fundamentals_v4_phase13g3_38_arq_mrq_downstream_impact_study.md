# Phase 13G.3.38 ARQ vs MRQ Downstream Impact Study

## Decision

Keep ARQ as the only canonical financial authority and do not introduce an MRQ overlay into the current V2 runtime model.

MRQ remains valuable as provider evidence: Refresh acquires and validates it independently, and its companion history helps distinguish a rolling source-window boundary from an ambiguous source removal. No MRQ financial field has yet demonstrated a correctness benefit that justifies changing canonical, TTM, Score, Valuation, RP, RV, or historical semantics.

Option A, **keep ARQ-only**, is therefore the recommended production architecture. A separate, provenance-rich MRQ comparison/current-state research layer is the only acceptable next experiment. It must not feed production results unless field semantics and point-in-time availability are independently proven.

Phase 13G.3.38 is a design and impact study only. It does not change ARQ/MRQ runtime semantics.

## Scope And Method

The study inspected the provider ingestion and Refresh contracts, ARQ canonical reconciliation, TTM construction, and V2/Relative Position/Relative Valuation readers. The quantitative work used only the local production-shaped provider, canonical, and analysis databases opened with SQLite `mode=ro` and `query_only=ON`.

For comparisons, provider observations were joined to canonical company identity and one row per `(company_id, dimension, fiscal_year, fiscal_quarter)` was selected with the exact canonical reconciliation authority and precedence: valid parsed `fiscalperiod`, resolved `company_id`, then the existing ticker/fiscal ordering with latest `reportperiod`, latest `COALESCE(lastupdated, date)`, and observation identity. A deliberately naive shadow overlay replaced non-null ARQ canonical fields with authority-matched MRQ values in memory, then called the real TTM, Score, and Valuation calculation functions. It did not write a database and is an impact upper bound, not a proposed merge policy.

No network request, Admin workflow, scheduler operation, or production write was performed.

## Current Source Authority

### Provider and Refresh

- `fundamentals_provider.db.sharadar_fundamental_observation` stores both ARQ and MRQ.
- Refresh treats `("ARQ", "MRQ")` as two required, independently validated complete histories. The durable provider identity includes ticker, dimension, date, and report period.
- Refresh comparison, rolling-window retention, and source-removal classification inspect both dimensions. Conflicting companion evidence can turn a removal into `AMBIGUOUS_SOURCE_REMOVAL` / `REVIEW_REQUIRED`.
- Refresh candidate replacement persists both dimensions. An MRQ-only source change can therefore affect Refresh discovery, source fingerprints, and rebuild orchestration even though it cannot supply a canonical financial value.

### Canonical and downstream

- Canonical winner selection explicitly filters `dimension='ARQ'`.
- The canonical fiscal key is stable `(company_id, fiscal_year, fiscal_quarter)`, parsed from ARQ `fiscalperiod`. Winner precedence collapses overlapping provider observations by report period, update/date, and observation identity.
- Every current canonical quarter identifies `SHARADAR_ARQ` / `SHARADAR_ARQ_PRIMARY` as its authority.
- TTM reads canonical quarter rows only. Flow values are sums over four contiguous quarters; cash, total debt, and shares outstanding come from the endpoint quarter.
- Score V2 and Lifecycle consume canonical TTM history. Valuation consumes canonical TTM plus market prices and classification. Delta and Diagnostics consume those V2 histories. RP V2 consumes Score and Valuation. RV consumes Valuation and canonical timing/source context.
- Snapshot/reporting reads the persisted V2 package. It has no MRQ financial read path.

Consequently, no economic downstream component currently reads MRQ, directly or indirectly. The only indirect MRQ role is operational: source validation or change classification may cause or block an ARQ-derived rebuild.

## Fiscal Identity And Overlap

ARQ and MRQ are separate provider observations, not interchangeable revisions of one canonical row. They can share `fiscalperiod` while disagreeing on `reportperiod`, `calendardate`, dates, and values. Multiple observations can also exist for the same ticker/dimension/fiscal period and must be collapsed before comparison.

Local winner-level evidence:

| Measure | Result |
| --- | ---: |
| ARQ winners | 89,872 |
| MRQ winners | 92,575 |
| shared company/fiscal keys | 89,661 |
| ARQ-only historical keys | 211 |
| MRQ-only historical keys | 2,914 |
| latest fiscal quarter aligned | 2,540 / 2,540 authority-resolved companies |
| shared keys with report-period mismatch | 181 (0.202%) |
| shared keys with calendar-date mismatch | 125 (0.139%) |
| ARQ duplicate fiscal groups | 2,149; 2,520 extra rows; max 7 versions |
| MRQ duplicate fiscal groups | 491; 515 extra rows; max 4 versions |

The canonical database contains 89,872 quarters for 2,540 companies. Exact equality with the 89,872 ARQ authority winners confirms that the study uses the same accepted company/fiscal winner contract as canonical reconciliation.

## Date And Freshness Semantics

MRQ must not be treated as newer merely because it is named "most recent". In the local data:

- MRQ `date` equals `reportperiod` for 93,090 / 93,090 raw MRQ rows.
- ARQ `date` equals `reportperiod` for 0 / 92,392 raw ARQ rows.
- Across shared winners, `MRQ date - ARQ date` has median -38 days and mean -43.9 days.
- For each ticker's latest shared fiscal quarter, the median is -37 days, with range -240 to -10 days.
- `MRQ lastupdated - ARQ lastupdated` has median 0 days and mean +0.76 days.

Thus the negative date lag is principally a dimension/date-definition difference, not evidence that MRQ became knowable earlier. Using MRQ `date` as a public availability date would introduce look-ahead. Any future MRQ layer needs an explicit availability policy separate from period end and must preserve both dimension-specific dates and provider observation identities.

## Field Classification

Classification is for downstream runtime use under the current evidence.

Flow metrics are revenue/profit and cash-flow-period measures that participate in four-quarter sums. Stock metrics are quarter-end balance-sheet and share-count levels used only from the endpoint quarter. They must not share an overlay rule: OCF, capex, and FCF in particular remain flow metrics even when an MRQ row appears more current.

| Field group | Classification | Decision |
| --- | --- | --- |
| Revenue and gross profit | `ARQ_ONLY_PREFERRED` | Keep the four-quarter flow chain coherent. Historical disagreement exists, while the latest shared quarter adds no different value. |
| Operating income, EBIT, EBITDA | `ARQ_ONLY_PREFERRED` | These drive Score, Lifecycle, Diagnostics, Valuation, RP, and RV. Mixing dimensions would change margins and ranking universes. |
| Net income and common net income | `ARQ_ONLY_PREFERRED` | Preserve the same fiscal chain used by earnings valuation. |
| Operating cash flow, capex, free cash flow | `ARQ_ONLY_PREFERRED` | Cumulative/YTD versus discrete-quarter ambiguity can contaminate all four quarters of TTM. No dimension mixing is acceptable without a proven provider contract. |
| Cash and total debt, including debt components | `MRQ_UNSAFE_OR_REDUNDANT` | Endpoint stock candidates in theory, but latest ARQ/MRQ values were identical for every comparable company; MRQ adds no demonstrated information and has unsafe availability semantics. |
| Receivables, inventory, payables, deferred revenue, assets | `MRQ_UNSAFE_OR_REDUNDANT` | Latest values were identical across all 2,540 comparable companies. They are canonical/diagnostic inputs but provide no demonstrated current-state gain. |
| `sharesbas` (canonical shares outstanding) | `MRQ_UNSAFE_OR_REDUNDANT` | Latest values disagreed for 2,443 / 2,540 companies (96.18%). This is a dimension/timing-definition conflict, not safe freshness. It materially changes dilution and valuation denominators. |
| `shareswa` | `MRQ_UNSAFE_OR_REDUNDANT` | Latest values disagreed for 268 / 2,540 companies (10.55%); it is a support field, not a safe replacement for endpoint shares. |
| `shareswadil` | `MRQ_UNSAFE_OR_REDUNDANT` | It is a provider support field, not a current canonical input. Latest values added no difference, and dimension mixing would not improve current dilution semantics. |
| Period end / latest-quarter identity | `MRQ_UNSAFE_OR_REDUNDANT` | Latest fiscal identities align, but report/calendar mismatches exist historically and MRQ `date` is period-end-like, not an availability authority. |

No field currently qualifies as `MRQ_OVERLAY_CANDIDATE` or `MRQ_PREFERRED_CURRENT_STATE` for production. Cash, debt, balance-sheet levels, and share counts are legitimate subjects for a future separate comparison layer, but they do not pass a runtime precedence gate today.

## Quantitative Findings

### Historical field disagreement

Among 89,661 shared winner keys, disagreement rates for comparable values were:

| Field | Different | Rate | Differences over 5% of ARQ |
| --- | ---: | ---: | ---: |
| revenue | 7,344 | 8.31% | 3,468 |
| operating income | 13,230 | 14.96% | 7,031 |
| EBIT | 12,442 | 14.07% | 5,909 |
| net income common | 6,583 | 7.44% | 3,447 |
| operating cash flow | 8,390 | 9.54% | 3,475 |
| capex | 8,108 | 9.22% | 4,076 |
| free cash flow | 12,140 | 13.80% | 5,580 |
| cash | 1,944 | 2.17% | 1,043 |
| total debt | 2,366 | 2.64% | 890 |
| `sharesbas` | 81,978 | 91.51% | 8,933 |
| `shareswa` | 15,476 | 17.26% | 2,487 |

SUI, CCO, PPSI, TRMB, and GE were the leading local revision-heavy proxies after excluding all share-count fields, with economic-field disagreements in 33-35 historical fiscal quarters each. This identifies useful future review cases; it does not establish which dimension is economically correct.

### Latest-quarter comparison

All 2,540 authority-resolved companies had the same latest ARQ and MRQ fiscal identity. At that latest identity, every comparable economic flow, cash, debt, and other balance-sheet value was equal. Differences were confined to `sharesbas` and `shareswa`; `shareswadil` was equal where present.

The selected financial-sector probes JPM and BAC were absent from this local provider/canonical study universe, so this dataset cannot establish financial-sector MRQ suitability. The other representative probes included large caps (AAPL, MSFT, NVDA, AMZN, GOOGL), datacenter-related names (NVDA, AMD, AVGO, VRT, ANET), recent IPO CRWV, and smaller/structural names (FLWS, LOVE, KRSA, PSQL, QVCG).

### Naive overlay impact

This is a **what-if sensitivity analysis only**, not a corrected representation of production truth or a candidate publication result.

The in-memory full-history overlay changed 81,634 canonical share cells and thousands of historical flow cells. At the latest TTM endpoint it changed shares outstanding for 2,428 companies, but cash and debt for none. It changed only 8-20 latest TTM flow outputs per measured flow, because most historical disagreements were outside the current four-quarter window. One TTM readiness status changed.

Despite limited current flow changes, share-count replacement propagated broadly:

- 1,762 latest Score rows changed; among 1,761 comparable numeric deltas, median absolute change was 0.383 points, mean 1.728, 95th percentile 7.570, and maximum 45.0.
- 1,574 latest Valuation rows changed; among 1,566 comparable numeric deltas, median absolute change was 0.087 points, mean 0.382, 95th percentile 1.241, and maximum 30.571.
- AAPL, MSFT, NVDA, AMD, AVGO, VRT, and ANET had identical latest economic fields but changed Score and/or Valuation through MRQ `sharesbas`.
- LOVE's shadow Score moved from 41.83 to 39.63 and Valuation from 80.27 to 79.87 despite identical latest flow/balance values; QVCG had no latest field or score change.
- KRSA and PSQL had share differences but no ready current Score/Valuation result on which to measure a numeric delta. CRWV remained at Score 0 and Valuation 0.

This result is precisely why a naive overlay is unsafe: apparent recency in one denominator can re-rank many companies without improving the underlying latest-quarter economics.

## Semantic Risks

- **Mixed-quarter semantics:** an MRQ field cannot be injected unless fiscal identity, period end, observation version, and availability all match the ARQ row under an explicit policy.
- **Restatements:** ARQ and MRQ have independent duplicate/revision histories. Taking the newest value per field can create a row that never existed in either source dimension.
- **YTD versus quarterly flows:** revenue, profit, cash flow, capex, and FCF may represent different accumulation semantics. Summing a mixed chain can double-count or annualize incorrectly.
- **Availability/look-ahead:** local MRQ `date` is always the report period. It cannot authorize point-in-time use.
- **TTM contamination:** one overwritten historical quarter affects four rolling TTM endpoints and their Score, Lifecycle, Delta, Diagnostics, and valuation histories.
- **Share timing and splits:** `sharesbas` disagreement is pervasive. Without a proved as-of definition and split policy, replacement corrupts dilution and market-cap denominators.
- **Provider definitions:** local equality/disagreement proves behavior, not the provider's intended economic definition. Runtime precedence requires an explicit source contract.
- **Backtest continuity:** the model is currently a consistently ARQ-derived, currently revised history. Retrofitting MRQ selectively would create a new model generation and invalidate direct historical comparisons.

## Architecture Options

| Option | Correctness and integrity | Complexity | Decision |
| --- | --- | --- | --- |
| A. Keep ARQ-only | One fiscal authority, coherent TTM chain, stable V2 history and provenance | Lowest | **Selected** |
| B. Field-level MRQ overlay | High mixed-version, availability, share, and YTD risk; provenance becomes field-granular | Medium | Reject |
| C. MRQ-first latest-current-state layer | Isolates history, but needs a new availability contract and separate consumers; current local values show no economic-field gain | Medium | Research contingency only, not runtime |
| D. Full ARQ/MRQ reconciliation | Could model both dimensions explicitly, but requires winner, conflict, lineage, backtest, and migration contracts throughout the stack | Highest | Reject for current need |

Option A preserves correctness with no lost demonstrated downstream information. If future evidence establishes a genuine MRQ current-state advantage, option C should be evaluated before either overlay or full reconciliation.

## Downstream Impact If An Overlay Were Enabled

| Component | Impact | What would change |
| --- | --- | --- |
| canonical quarterly state | Direct | Financial values, per-field provenance, source policy, fingerprints, and possibly period identity would need a new model generation. |
| TTM builder | Direct | Four-quarter sums, endpoint cash/debt/shares, readiness, source dates, and input fingerprints could change. |
| Score V2 | Indirect | Growth, margins, balance resilience, dilution, trajectory, readiness, and total score could change. |
| Lifecycle | Indirect | Revenue growth, operating margin/direction, FCF margin, state transitions, and confirmation history could change. |
| Valuation | Indirect | Market cap, enterprise value, earnings/FCF/operating yields, readiness, and score could change. |
| Delta | Indirect | Current and lagged component deltas, comparability, and package fingerprints could change. |
| Diagnostics | Indirect | Margin, cash conversion, capex, leverage, valuation, working-capital, and chronology flags could change. |
| RP V2 | Indirect | Score and Valuation ranking inputs, eligibility, ranks, percentiles, and peer snapshots could change. |
| RV | Indirect | Absolute valuation inputs, filing/current comparisons, ranking, eligibility, and snapshots could change. |
| snapshot/reporting | Indirect | Every revised downstream value and model/source fingerprint could differ; mixed model packages must remain rejected. |
| source binding / production parity | Direct operational | Test and Production must bind the same ARQ/MRQ winner policy, provenance, availability, and candidate generation. Existing fingerprints/contracts would need versioning. |
| historical backtests | Direct | Revised histories and signal timing would change; MRQ period-end dates would cause look-ahead unless replaced by proven availability dates. |

With the selected ARQ-only architecture, all listed economic outputs have **no change**. MRQ continues to affect only Refresh source evidence, completeness, retention, review gating, and provider/source fingerprints.

## Recommended Contract

1. ARQ remains the sole winner source for every canonical quarter field.
2. MRQ remains an independently complete provider dimension and companion removal/reconciliation signal.
3. MRQ never fills an ARQ null, replaces an ARQ value, changes fiscal identity, or supplies an availability date in the production model.
4. A disagreement is evidence to study, not authority to merge.
5. Existing ARQ source policy, TTM model, V2 package fingerprints, and revised-history semantics remain unchanged.
6. Future experiments must preserve dimension, observation identity, fiscal identity, report period, period end, provider update time, and a separately justified public-availability time for every compared value.

## Staged Research Plan

No runtime migration is authorized. If MRQ is revisited:

1. Specify explicit ARQ/MRQ provenance and provider field/date definitions without changing canonical schema.
2. Turn the read-only comparison into a reproducible fixture-backed audit, including the 181 report-period and 125 calendar mismatches.
3. Validate cash, debt, balance items, `sharesbas`, `shareswa`, and `shareswadil` on filing/source evidence, split events, and a supported financial-sector sample.
4. Build a separate shadow current-state layer; never mutate ARQ canonical rows or TTM inputs.
5. Compare shadow Score/Valuation and readiness deltas, with special gates for denominator changes and look-ahead.
6. Run historical point-in-time/backtest and full Production-parity acceptance under a newly versioned model contract.
7. Enable a runtime consumer only if the field-specific correctness gain is demonstrated and ARQ fallback, staleness, provenance, and mixed-quarter rejection are all fail-closed.

## Unresolved Questions

- What exact provider definitions distinguish ARQ and MRQ `sharesbas` and `shareswa`, and to what time within the quarter/reporting cycle do they refer?
- Is a reliable public/source availability timestamp available for MRQ independently of `date`, which locally equals `reportperiod`?
- Which historical economic disagreements are restatements versus dimension-definition differences?
- Can a supported financial-sector sample establish different field behavior from this current universe?
- Would any proposed current-state value improve a real decision after split normalization, rather than merely change it?

Until these are answered with source-level evidence, MRQ is companion evidence, not a downstream financial authority.
