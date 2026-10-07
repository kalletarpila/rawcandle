# P/B.1 — Book Value / Price-to-Book Investigation and Data-Contract Audit

Audit date: 2026-10-07, Europe/Helsinki. Research only. No production implementation.

## Executive Summary

**Reliable P/B feasible: PARTIAL.** Existing accepted Sharadar observations contain parent equity (`equity`, `equityusd`) in raw JSON, but canonical financials have no equity field. Parent equity must not be silently renamed common equity. Preferred capital adjustments are unavailable.

Recommended initial use: **REPORTING_ONLY**, labelled price to parent book equity. Recommend a restricted `PB_CURRENT_PARENT_EQUITY_V1 = current validated ownership-adjusted market capitalization USD / latest accepted parent equity USD`. For verified single-class ordinary shares with factor 1, this reduces to `latest close × sharesbas / equityusd`. ADRs and uncertain multiple classes remain unavailable pending ownership validation.

Current operational universe: **2468 companies**, all USA; 2547 company identities exist in canonical storage. Numeric research P/B: **2123 (86.02%)**. This is an arithmetic ceiling, not production reliability certification. Fresh price/fundamental arithmetic cohort: 2,105. Conservative factor/class/date candidate cohort: **1,696 (68.72%)**; preferred capital and adjustment evidence still need review. Production canonical-only P/B availability today: zero, because equity is not canonical.

Risks: parent versus common equity, ADR ownership factors, revised split bases, weighted-average BVPS, filing-cover rather than balance-sheet-date shares, stale prices, and partial raw payloads. Current reporting can be valid after the stated gates; historical P/B is **not certified PIT-safe**.

## Existing Data

### Database authority and scope

The active-generation manifest resolves provider/canonical/analysis to `data/fundamentals_generations/publication_drain_20261007T093516Z_fd654a20/`. Reading the historical top-level filenames without this resolution would audit a different generation. Market data is `data/osakedata.db`. All SQLite connections used `mode=ro`. The manifest was read without modification.

Provider owns observations and JSON; canonical owns accepted quarters, values and provenance; analysis owns rebuildable outputs. Taxonomy comes only from `osakedata.db.ticker_meta`. No V1 source was used.

Universe denominator is the active `fundamentals_operational_universe_member` version, one row per company: 2,441 active single-security, 11 active multiple-security, 16 retained historical companies. All 2,468 are `usa`; OMXS/OMXH coverage is zero members, not missing Nordic financials. Canonical identities additionally include companies outside this operational version; they are not added to the denominator.

Provider contains 192,576 SHARADAR observations only: ARQ 92,413; MRQ 93,117; ART 2,814; MRT 2,540; ARY 967; MRY 725. All 89,914 canonical quarter identities say SHARADAR_ARQ. No SEC/Yahoo equity source exists in this generation.

### Exact field inventory

All JSON-only fields below live in `provider_observation.payload_json`, linked by `observation_id`. The typed native table is `sharadar_fundamental_observation`; canonical table is `v4_quarter_financials`. Coverage counts use the exact accepted latest-quarter shares provenance observation, not the latest unrelated provider row. Zero counts as present. No richer-snapshot fallback was needed.

| Native field | Latest accepted-quarter numeric coverage | Canonical location | Units / interpretation |
|---|---:|---|---|
| equity | 2348 | None; provider JSON | Reporting currency; parent equity stock |
| equityusd | 2348 | None; provider JSON | USD; parent equity stock |
| equityavg | 0 | None; provider JSON | Currency; period average, reject for endpoint book equity |
| bvps | 2348 | None; provider JSON | Currency/share; weighted-average share basis |
| assets | 2466 | v4_quarter_financials.total_assets; native typed assets | Currency; endpoint total assets |
| assetsavg | 0 | None; provider JSON | Currency; average assets, reject |
| assetsc | 2185 | None; provider JSON | Currency; current assets stock |
| assetsnc | 2185 | None; provider JSON | Currency; noncurrent assets stock |
| liabilities | 2348 | None; provider JSON | Currency; total liabilities stock |
| liabilitiesc | 2185 | None; provider JSON | Currency; current liabilities stock |
| liabilitiesnc | 2185 | None; provider JSON | Currency; noncurrent liabilities stock |
| taxassets | 2348 | None; provider JSON | Currency; tax assets stock |
| taxliabilities | 2348 | None; provider JSON | Currency; tax liabilities stock |
| accoci | 2348 | None; provider JSON | Currency; AOCI stock, included in equity |
| tangibles | 2348 | None; provider JSON | Currency; assets less intangibles, NOT tangible common equity |
| intangibles | 2348 | None; provider JSON | Currency; goodwill plus intangibles stock |
| tbvps | 2348 | None; provider JSON | Currency/share; tangible ASSETS per weighted-average share |
| sharesbas | 2466 | v4_quarter_financials.shares_outstanding; typed native sharesbas | Units; split-adjusted filing-cover outstanding shares |
| shareswa | 2466 | Typed native shareswa; not canonical | Units; weighted-average basic EPS denominator |
| shareswadil | 2195 | Typed native shareswadil; not canonical | Units; diluted weighted-average EPS denominator |
| sharefactor | 2348 | None; provider JSON | Ratio; ownership adjustment, may be rounded to zero |
| prefdivis | 2342 | None; provider JSON | Currency; preferred dividend income impact, NOT preferred equity |
| netincnci | 2342 | None; provider JSON | Currency; noncontrolling income, NOT noncontrolling equity |
| marketcap | 2348 | None; provider JSON | USD; source-price-date market capitalization |
| price | 2348 | None; provider JSON | USD/share; provider adjusted source-date price |
| fxusd | 2348 | None; provider JSON | Currency/USD in observed rows |
| pb | 2348 | None; provider JSON | Ratio; source-date provider P/B |

There is **no separate common equity, preferred equity stock, or noncontrolling/minority equity stock** in the observed payload key inventory or typed/canonical schemas. `netincnci` and `prefdivis` are flows and cannot substitute. `total_debt` is not total liabilities. Assets minus liabilities is not guaranteed parent common equity; a difference can contain noncontrolling interests or other presentation components.

All candidates share row-level `fiscalperiod`, `reportperiod`, `dimension`, `date`, `lastupdated`, source availability, fetched time and hash. Quarter fiscal identity and publication evidence are canonical in `v4_quarter` and result-publication tables. Monetary stocks are endpoint balances, not sums or annualized values; weighted-average shares/earnings describe a duration. Same endpoint stock may appear in Q/Y/T dimensions. Annual data cannot manufacture missing intermediate quarter balances.

### External provider definitions, separated from repository facts

Sharadar describes equity as parent-attributable stockholders' equity; equityusd is its USD conversion. Sharesbas uses split-adjusted filing-cover outstanding units, whereas shareswa/shareswadil are EPS averages. BVPS uses equity and shareswa with sharefactor; marketcap uses price × sharesbas × sharefactor. Tangibles is assets minus intangibles; tbvps uses tangibles, so it is not tangible common book equity. AR excludes restatements and is filing-indexed; MR includes restatements. These definitions do not establish preferred-equity exclusion. [Sharadar fundamentals documentation](https://sharadar.com/docs/fundamentals).

Sharadar's documented ADR-ratio corporate action explicitly references sharefactor. [Sharadar provider documentation](https://sharadar.com/). Its description metadata endpoint is documented separately, but the public request was inaccessible during this audit; no authenticated provider refresh was attempted. [Indicator descriptions](https://sharadar.com/docs/descriptions).

The observed USD conversion direction was independently established from data: `equityusd ≈ equity / fxusd`, not multiplication. ASML: EUR 21.8254bn / 0.88 = USD 24.8016bn; BABA: CNY 1,049.038bn / 6.716 = USD 156.1952bn. Direct BVPS is converted with the same division. No generic currency conversion convention was guessed. Displayed FX precision causes approximately 0.003% residual in BABA/BIDU; the authoritative equityusd is used rather than reconstituting it from rounded FX. Sample FX assertions allow 0.01% tolerance; A/B arithmetic assertions remain 1e-12.

## Accounting Semantics

Use parent equity as a clearly named reporting denominator. A future true common-book metric requires preferred stock carrying value and its treatment, including redeemable/temporary capital. Parent attribution excludes equity attributable to other owners by definition, but the current fields do not support independent reconciliation of those balances.

Balance-sheet-date outstanding economic ownership would be ideal. Existing `sharesbas` is filing-cover shares and may be later than quarter end; that distinction must remain visible. It is the existing market-cap convention and avoids automatically reusing weighted-average EPS shares. It remains a proxy for current shares until an authoritative newer outstanding count exists. Do not use diluted potential ownership for a book balance.

Current code retains total assets for working-capital analysis and sharesbas for TTM endpoint/valuation market capitalization. No equity/BVPS/tbvps canonical consumer was found in the narrowly inspected mappings and valuation paths. Additional raw keys are retained without semantic promotion. Sharadar `FUNDAMENTALS_REQUIRED_FIELDS` does not require equity, so future reduced payloads can legitimately omit it.

## Price / Date Semantics

Audit as-of date is 2026-10-07. Prices are the latest valid complete positive OHLC row on/before as-of, matching ticker and market. 2,437 companies have 2026-10-06 price; six have 2026-10-05; 14 have older prices; 11 have no valid price. Close is used without introducing a dividend transformation. Age greater than three calendar days is flagged and rejected for the proposed current contract.

Latest equity quarter is the latest canonical fiscal endpoint whose source availability is on/before as-of. Source equity is taken through accepted shares provenance for that same quarter. Publication/availability dates must remain separate from period end. A publication timestamp is not proof that every balance-sheet field appeared in that release: equity cannot be released earlier than its own supported source evidence. Canonical availability alone must not move filing-sourced equity to an earlier earnings date.

Existing filing valuation selects latest close on/before TTM availability with a three-day fallback. Relative valuation reevaluates at as-of and uses 180-day fundamental freshness. Proposed current P/B adopts those age bounds but does not require four ready flow quarters: one eligible balance sheet suffices. Fiscal labels come from fiscalperiod; do not use calendar quarter identity, TTM sum equity, or annual-minus-nine-month equity.

Quarter-end P/B is a different historical description; the quarter's own published equity is usually unavailable then. Publication-date P/B needs intraday publication/market-close ordering. Daily PIT P/B needs first-known field values, observation vintage, availability timestamps and compatible corporate-action bases. None should be conflated with current reporting.

## Formula Comparison

A: `close / (equityusd / canonical shares_outstanding)`.
B: `current RawCandle market_cap / equityusd`, with market_cap reconstructed as `close × canonical shares_outstanding`.

Across all **2,123** positive-equity calculable rows, A and B agree to deterministic floating tolerance; median absolute percentage difference is effectively **0%**. This is an algebraic identity, **not independent accuracy validation**. Existing market cap cannot repair an ADR mismatch because it uses the same unadjusted ownership base.

C, diagnostic only: `close × sharesbas × sharefactor / equityusd`. The existing code does not use sharefactor. Direct provider BVPS comparison uses `close / (bvps / fxusd)`; across 2,123 rows median absolute percentage difference from A is **0.437510%**, with **213 above 10%**. Factor-adjusted C versus direct BVPS median is 0.428873%, reflecting remaining share-average and rounding differences. C does not automatically become reliable merely because it matches another provider formula.

Provider source-date marketcap/price/pb are retained in the validation CSV. They cannot serve as current numerator; source-date prices differ from current prices. Current stored analysis market caps likewise require matching snapshot dates before comparison. The research A/B uses the current engine's actual formula, not a historical stored numerator.

## Coverage

| Measure | Count | Percentage of 2,468 |
|---|---:|---:|
| Positive equity USD | 2,133 | 86.43% |
| Zero equity USD | 0 | 0.00% |
| Negative equity USD | 215 | 8.71% |
| Missing equity USD | 120 | 4.86% |
| Numeric equity available | 2,348 | 95.14% |
| Positive shares available | 2,466 | 99.92% |
| Latest valid price available, before age gate | 2,457 | 99.55% |
| Missing/nonpositive shares | 2 | 0.08% |
| Missing valid price | 11 | 0.45% |
| Arithmetic positive P/B | 2,123 | 86.02% |
| Arithmetic positive P/B with age gates | 2,105 | 85.29% |
| Conservative factor/class/date candidate | 1,696 | 68.72% |

Exclusion counts overlap. `calculable` in CSV means research arithmetic, not approved production display. `strict_candidate` rejects every note, unknown/nonunit factors, ADR/category class flags and nonsingle membership; it is deliberately conservative and **not a preferred-capital certification**.

Raw metadata categories: 1,958 domestic common; 460 domestic primary class; 29 ADR common/primary; eight Canadian common/primary; 13 unknown. 131 have missing/nonunit factor (120 coincide with missing equity payload); 482 need class review, 12 stale fundamentals and 14 stale prices. Sector/industry was used only to choose the financial sample. The active universe has financial exchanges/data firms but no bank/insurer sample; JPM/BAC/TSM/GOOG/GOOGL/BRK.B are absent from these members, so no values were fabricated.

Near-zero diagnostic: positive equity at most USD 1m occurs in **three** companies: DBGI 540,031; POLA 857,000; SLXN 44,000. This is a transparent research threshold, not a proposed universal materiality policy. Other relative materiality definitions need separate calibration. Negative examples include AAL, ABBV, AMC, MCD and SBUX. Negative/zero equity returns NULL with explicit reason, never a cheap negative P/B. Small positive equity stays numeric with a warning; do not cap or boost a score.

## Validation Sample

20 diverse companies, computed directly from raw accepted inputs and canonical shares, with USD-compatible numerator/denominator. Banks and Nordic issuers are unavailable in the operational universe. CME/COIN provide financial examples; ASML/BABA/BIDU provide foreign/ADR examples; CAT/DE/F/XOM provide asset-heavy examples. Negative equity cases deliberately retain NULL P/B.

| Ticker | Price | Price date | Equity USD | Shares | BVPS USD | P/B A = B | Direct BVPS (local currency) | Direct P/B (USD converted) |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| AAPL | 333.6300 | 2026-10-06 | 107,520,000,000.0000 | 14,594,180,000.0000 | 7.3673 | 45.2851 | 7.3360 | 45.4785 |
| AMD | 649.4200 | 2026-10-06 | 67,224,000,000.0000 | 1,632,475,042.0000 | 41.1792 | 15.7706 | 41.1910 | 15.7661 |
| CAT | 863.4400 | 2026-10-06 | 19,394,000,000.0000 | 459,674,889.0000 | 42.1907 | 20.4652 | 42.1240 | 20.4976 |
| CME | 270.1800 | 2026-10-06 | 26,520,400,000.0000 | 359,577,412.0000 | 73.7544 | 3.6632 | 73.5280 | 3.6745 |
| COIN | 185.7400 | 2026-10-06 | 13,079,665,000.0000 | 263,836,923.0000 | 49.5748 | 3.7467 | 49.6550 | 3.7406 |
| DE | 682.7900 | 2026-10-06 | 27,990,000,000.0000 | 269,625,412.0000 | 103.8107 | 6.5773 | 103.7440 | 6.5815 |
| F | 12.2800 | 2026-10-06 | 35,719,000,000.0000 | 3,987,595,667.0000 | 8.9575 | 1.3709 | 8.9590 | 1.3707 |
| IBM | 221.2900 | 2026-10-06 | 34,452,000,000.0000 | 942,134,390.0000 | 36.5680 | 6.0515 | 36.6040 | 6.0455 |
| KALA | 0.3640 | 2026-10-06 | 9,044,000.0000 | 19,339,786.0000 | 0.4676 | 0.7784 | 121.9540 | 0.0030 |
| MCD | 232.4500 | 2026-10-06 | -1,023,000,000.0000 | 707,641,531.0000 | -1.4456 | — | -1.4430 | — |
| MSFT | 529.3000 | 2026-10-06 | 442,387,000,000.0000 | 7,425,545,491.0000 | 59.5764 | 8.8844 | 59.5730 | 8.8849 |
| NVDA | 239.2400 | 2026-10-06 | 228,984,000,000.0000 | 24,100,000,000.0000 | 9.5014 | 25.1794 | 9.4660 | 25.2736 |
| QNRX | 4.7200 | 2026-10-06 | 3,932,671.0000 | 70,294,615.0000 | 0.0559 | 84.3677 | 1.1190 | 4.2181 |
| SBUX | 96.1100 | 2026-10-06 | -7,674,300,000.0000 | 1,140,000,000.0000 | -6.7318 | — | -6.7340 | — |
| SCNI | 1.2200 | 2026-10-06 | 11,732,000.0000 | 22,800,887,584.0000 | 0.0005 | 2,371.0436 | 15.5440 | 0.0785 |
| WMT | 107.2000 | 2026-10-06 | 98,238,000,000.0000 | 7,933,746,241.0000 | 12.3823 | 8.6575 | 12.3510 | 8.6795 |
| XOM | 164.4800 | 2026-10-06 | 259,380,000,000.0000 | 4,111,911,960.0000 | 63.0801 | 2.6075 | 63.0800 | 2.6075 |
| ASML | 1,834.1000 | 2026-10-06 | 24,801,590,909.0000 | 384,500,000.0000 | 64.5035 | 28.4341 | 56.7630 | 28.4342 |
| BABA | 109.2600 | 2026-10-06 | 156,195,169,888.0000 | 18,671,000,000.0000 | 8.3657 | 13.0605 | 449.4830 | 1.6325 |
| BIDU | 87.0500 | 2026-10-06 | 40,354,013,840.0000 | 2,716,000,000.0000 | 14.8579 | 5.8588 | 800.4480 | 0.7323 |

The companion CSV includes native shareswa/shareswadil, source price/cap/PB, FX, factor, observation identifiers and class/date flags for reproducibility.

Discrepancy evidence:

- AAPL/AMD/NVDA and buyback-heavy firms: basic cover shares differ from duration averages; direct BVPS rounds to three decimals.
- **BABA/BIDU**: sharefactor 0.125 in accepted raw data; A is approximately eight times factor-adjusted C. This is direct stored ownership evidence, not an invented ADR ratio. USD/local currency conversion is additionally required.
- **QNRX**: factor 0.05; missing it explains approximately 20× scale before rounding.
- **SCNI**: enormous split-adjusted shares and factor stored as 0.0; current factor precision cannot represent an usable ownership base. Do not invert or impute a ratio. Block.
- **KALA**: sharesbas 19,339,786 versus shareswa 74,159 (about 261×). Direct BVPS matches the smaller average base, whereas marketcap matches cover shares. A capital change or split-basis inconsistency needs source reconciliation; the data proves denominator mismatch, not a precise event cause.
- **FTFT**: sharesbas 8,061,611 versus shareswa 382,016 (about 21×). This is another denominator discontinuity requiring review.
- **ASML**: parent equity reports EUR; USD conversion is mandatory. Factor is one but foreign ownership still needs validation.

Largest direct differences are SCNI, KALA, FTFT, QNRX, ONC, MOVE, EDBL, ZLAB, SLXN and BIDU. They are explained at the observable level by factors, share base discontinuity and rounding; exact unobserved corporate-action causes remain unresolved. No broad external price benchmarking was needed.

## ADR / Multi-Class Issues

Equity is issuer-level parent equity; the quoted security may be a depositary instrument. Raw shares can be underlying ordinary shares. Source factor bridges these units, but neither canonical schema nor current valuation inputs contains it or a validated ADR/ADS ownership contract. No independent canonical ADR ratio exists in the inspected schema.

MarketCap/Equity is more robust **only if numerator is an authoritative whole-company, same-currency, same-date market cap**. RawCandle's present price × shares numerator does not meet this condition for affected ADRs. Proposed V1 excludes ADRs until factor precision, security identity, effective dates, share ownership and price bases are verified. Factor zero is invalid. Multiple classes also require reviewed total economic ownership; do not sum company-level duplicate security market caps.

## PIT Safety

Provider AR is advertised as as-reported and MR as restated; this does not certify RawCandle's current accepted quarter table. Provider observations retain hashes and timestamps, but canonical quarter financials are current accepted state. Existing valuation history is explicitly `REVISED_HISTORY`; relative valuation is `CURRENTLY_REVISED_NOT_PIT`. Canonical shares and market prices have retrospective split conventions.

Classify current available history as **current reconstructed/accepted history with AR provenance and revised adjustment bases**, not demonstrated vintage-complete PIT. Historical PIT-safe P/B: **NO** under current contracts. Current P/B validity: **YES conditionally**, after matching currency, ownership, adjustments, availability and freshness. Source `lastupdated` is not first historical market availability; fetched time is evidence acquisition, not filing publication. A 6-K authority row resolves result publication and does not itself supply equity/share-denominator evidence.

## Valuation Score Assessment

Current V2 model: 40 points operating income/enterprise value, 40 free cash flow/market cap, 20 common earnings/market cap. P/B does not duplicate a current book-equity input; enterprise value/net debt provide a different balance-sheet adjustment. Adding it would change total weights, calibration, eligibility and historical comparability/model fingerprint. Do not do that during availability work.

Recommend **REPORTING_ONLY** initially. Banks/insurers may benefit from capital-book interpretation; asset-heavy industrials can benefit with accounting context. REIT book values depend on asset depreciation/fair value; software and intangible businesses can have weak explanatory book values; buybacks can make profitable companies negative equity. These are accounting judgments, not empirically calibrated peer rules. Later diagnostic/peer research needs sector-aware validation and must preserve the current score version.

## Recommended P/B V1 Contract

Name: `PB_CURRENT_PARENT_EQUITY_V1`; explicit parent-equity label rather than a claim of common equity.

- Numerator: validated current whole-company ordinary-equivalent market capitalization in USD. Restricted initial factor-one, verified single-class coverage uses latest valid market close × accepted cover shares; describe this as reported-share market-cap proxy. No stale provider marketcap reuse.
- Denominator: finite positive `equityusd`, latest eligible canonical accepted quarter, with field provenance back to SHARADAR ARQ JSON and own supported availability. Preferred-inclusive parent equity must be disclosed; a true common-equity contract waits for preferred-stock plumbing.
- Shares: `sharesbas` mapped to shares_outstanding, split-adjusted filing-cover stock, never automatically shareswa/shareswadil. Verification must reject detected base discontinuities; balance-sheet-date shares should supersede this proxy only under a separately defined contract.
- Dates: explicit as-of and actual price date, no forward price lookup, at most three-calendar-day fallback. Fundamental age at most 180 days using accepted availability; display balance-sheet date and share-basis caveat. No reliance on a TTM readiness gate.
- Currency/basis: numerator and equity USD; `equityusd` already converts reporting currency. Match split-only price/ownership bases; reject unsupported adjustment sources rather than assume equivalence.
- Missing, nonfinite, zero/nonpositive shares/price, unavailable equity, unsupported identity/class/factor or stale source: NULL plus typed reason. Negative equity: NULL `NEGATIVE_EQUITY`; zero: NULL `ZERO_EQUITY`; near-zero positive: numeric with diagnostic flag.
- ADR/multiple-class: NULL `OWNERSHIP_BASIS_UNVERIFIED` until validated effective factor/ADR contract exists. Factor 1 alone cannot prove all class economics.
- PIT: current revised reporting only; no historical PIT claim.
- Location: accepted monetary/share inputs belong in canonical with provenance; the ratio and reasons belong in rebuildable analysis state or reporting query layer. Provider JSON must not bypass canonical authority in the production calculation. Avoid an unnecessary P/B history/version chain.

## Next Implementation Phase

1. Data plumbing: add parent equity USD/local and currency metadata as canonical accepted fields with additive provenance; require/validate ingestion presence. Establish preferred-stock limitations, field availability and adjustment evidence. No mapping change was made in this phase.
2. Calculation: small derived current metric, reason codes, date/age gates and restricted ownership cohort; diagnostic comparison to direct BVPS and provider marketcap. Reject base discontinuities.
3. Reporting: expose P/B, parent equity, as-of/price/balance dates, availability and ownership/negative/missing reasons; retain existing scores.
4. Focused tests: positive/zero/negative/missing, currencies, fiscal Q4/year-end stock, stale/forward prices, AR/MR source selection, ADR factors including zero precision, multiple classes, split mismatch and deterministic rebuild. No full-suite run in this investigation.
5. Optional later research: compare sector-relative explanatory value and independently validate common-equity adjustments before discussing any score component.

## Validation and Production Safety

Read-only schema/data queries; independent A/B calculations asserted at relative tolerance 1e-12 for every arithmetic row. CSV row counts/uniqueness, finite values, classification counts, price-date ordering and sample inclusion checked. Only this Markdown and two compact CSVs are committed. Research helper stayed under `/tmp` and is not committed. Existing unrelated worktree changes were preserved. No database mutation, live workflow, refresh, rebuild, source-code edit, score edit, publication/review/scheduler change, or full test suite. `git diff --check` is the final whitespace check. Nothing pushed.
