# P/B.9 — Current market cap and share-action source audit

Audit as-of **2026-10-08**, Europe/Helsinki. Active generation **pb_reporting_20261007T193505Z**; source implementation/registry unchanged from P/B.8/P/B.8A. **Research complete; do not implement a DAILY numerator or resume P/B.8A durability from this evidence.**

Sharadar DAILY is obtainable and useful as a dated provider valuation reference, but **not an independent current-share count**. The authenticated indicator definition explicitly bases DAILY marketcap on the latest SEC Form 10 cover-count input. Daily price updates and split/ADR adjustments do not make intervening issuance, retirement or treasury movements complete. The safe approval count for a **new continuous current-share/marketcap contract is zero**. Existing Production remains on its approved reporting approximation, measured at **1,690 / 2,468**, without an ownership mass release.

## Scope, acquisition and evidence limits

Inspected only the three active Fundamentals role DB schemas, relevant market tables, existing Sharadar client/metadata bootstrap, Fundamentals refresh/reconciliation and the authoritative P/B.6/P/B.8/P/B.8A reports. All DB connections were mode=ro. The schema-only check of the existing taxonomy analysis DB found derived price/signal outputs, not a Sharadar DAILY or current share table; no unrelated data contents were scanned.

Local Production has **zero DAILY rows**. Research fetched **268,939 DAILY rows** for **2026-05-01 through 2026-10-07**, covering **2,449 provider tickers / 2,449 operational members**. **2,446** have positive latest cap observations; **AREB, CDT and WHLR have raw latest cap zero**, retained in the CSV rather than confused with missing data. There are 2,468 member records but **2,479 query ticker tokens**, because 11 canonical ticker strings contain two comma-separated securities. Those members retain ambiguity; a primary token is not automatically a whole-company identity approval.

The existing client authenticated with the configured key, which was not printed or written into artifacts. Successful extraction used **83 batches**, at most 30 tickers, ≤190 ticker characters and 10,000 JSON rows per call. Each returned batch was below the row cap, unique by ticker/date and within the requested dates/tickers. Initial rejected requests established server limits of 200 ticker characters, 30 tickers and 10,000 JSON rows; subsequent extraction honored all three. No bulk download, entitlement change or production ingestion occurred. Raw responses and acquisition manifests remain under `/tmp/rawcandle_pb9`, outside Git. The sorted raw research-input hash manifest has SHA-256 **3e91ea3d37ed2f47735c8579f60d7480c44c926f554151e915256aa0ae8043c6** (83 DAILY responses, indicator definitions, paginated actions and maximum-date probe). DAILY batch fetch timestamps range **2026-10-08T06:04:31.099359+00:00 through 2026-10-08T06:09:09.497447+00:00**.

**stocks/SEP requests returned HTTP 403 FREE_TIER_LIMIT / entitlement restriction.** No alternate endpoint was used to bypass that restriction. Thus there is no independently fetched Sharadar daily-close/unadjusted-close series in this audit. Same-filing-date tests use original native SF1 Price; time-series/current-date diagnostics use exact-date existing local Yahoo closes. Cross-vendor quote/revision differences can look like unit changes and are explicitly not certified share events.

## Local source inventory

Dates below describe stored observations, not semantic completeness. Universe coverage counts members with at least one relevant row/token, rather than certified eligibility.

| DB / table | Fields and meaning | Rows / field coverage | Date and universe coverage | Ingestion and assurance |
|---|---|---|---|---|
| Active provider / provider_observation | Original fundamentals JSON: price, marketcap, sharefactor, sharesbas, ncfcommon; hash, fetched_at, source availability | 192,576 fundamentals observations; 183,850 JSON payloads have marketcap/sharefactor/ncfcommon keys | Latest fetched 2026-10-04T17:38:40Z; native table is exclusively fundamentals | Sharadar backfill + normal ARQ/MRQ refresh; not DAILY, not a share-action feed; key presence does not mean finite positive value |
| Active provider / sharadar_fundamental_observation | Typed sharesbas, shareswa, shareswadil; filing `date`, period, lastupdated | 192,576 rows: ARQ 92,413; MRQ 93,117; ART 2,814; ARY 967; MRT 2,540; MRY 725 | ARQ 2,541 provider tickers, latest filing date 2026-10-02; latest lastupdated 2026-10-03 | Normal refresh updates ARQ/MRQ observations. Other dimensions are not substituted for accepted P/B quarters |
| Active canonical / v4_parent_equity_source | Same accepted ARQ price/cap/sharefactor/sharesbas plus quarter/hash/availability | 89,912 rows; cap/price non-null 83,724; sharesbas 89,912; sharefactor 85,655 | Latest provider date 2026-10-02; projected from accepted shares provenance | Rebuilt by accept_parent_equity inside normal reconciliation; dated filing evidence only |
| Active canonical / v4_quarter_financials | shares_outstanding is accepted sharesbas, not EPS average; parent equity denominator | 89,914 rows; outstanding count 89,912 | Accepted company/fiscal-quarter context | Normal reconciliation; no independently dated daily share-count field |
| Active provider / sharadar_ticker_metadata | table, ticker, permaticker, category, exchange, relatedtickers, listed/delisted flags and price ranges | 74,075 rows; fundamentals 17,828; stocks 20,949; funds 9,833; other insider/investor metadata 25,465 | Fundamentals metadata token coverage **2,466 / 2,468**; fetched 2026-08-31T06:24:31Z, max lastpricedate 2026-08-28 | Metadata bootstrap, not continuously refreshed by Fundamentals history refresh; relatedtickers is not a complete class inventory |
| Active provider / sharadar_action_metadata | date/action/value/ticker/contra identity and fetched_at | **156 rows, 77 direct tickers**, 71 operational members via ticker/contra | 2025-09-02–2026-08-31; fetched 2026-08-31T06:24:31Z | Bootstrap imports only flagged tickers/contra-tickers; no current event coverage assurance |
| Market osakedata.db / osakedata | Local OHLCV; **no marketcap or shares field** | 8,846,804 rows, 4,914 tickers; USA subset 8,071,407 rows / 4,524 tickers | All-market/USA maximum stored date 2026-10-08; audit exact-date diagnostics stop October 7 | Existing stock-update service/Yahoo path and scheduler; price/split data does not establish whole-company shares |
| Market / splits_data | split_date, split_ratio, correction flag, created_at | 6,423 rows / 2,267 tickers | 1962-10-31–2026-10-07; latest created_at 2026-10-08 03:51:08 | Stock update split sync/backfill; not issuance/buyback/class/treasury completeness |
| Market / ticker_meta | market/sector/industry routing | 5,068 rows | Routing identity, no source-completeness timestamp | Existing market metadata; not ownership or ADR-ratio authority |
| Research only / DAILY JSON | USD-million marketcap, ticker, date, lastupdated | 268,939 rows, 2,449 operational members; **19 absent** | Maximum date **2026-10-07**; 2,431 selected native-series endpoints are October 7, four October 6, 14 older, 19 missing | New read-only audit fetch only; no local production table/update/watermark |

The normal `sharadar_refresh_state` watermark is **2026-10-03 for fundamentals**, completed October 4. It does not apply to DAILY, ACTIONS or ticker metadata. `fresh_rebuild_canonical → reconcile_canonical → accept_parent_equity` refreshes accepted parent equity and its source normally. No action/DAILY acquisition or current share witness is introduced by that flow.

## Provider-defined facts

- DAILY supplies marketcap in **USD millions**, dated by the price session; its published schedule is 19:00 US Eastern, with history from December 1998. It does **not** contain close or a standalone shares-outstanding column. Marketcap must be multiplied by **1,000,000** before comparison with canonical USD equity. [DAILY documentation](https://sharadar.com/docs/daily)
- The authenticated `descriptions` records define DAILY cap from the latest SEC Form 10 SharesBas, Price and ShareFactor. SharesBas is the split-adjusted filing-cover count; weighted/basic diluted EPS averages have different meanings. ShareFactor handles ADR units and some class economics. These definitions establish a provider proxy, not completeness of current ownership. Authenticated definition capture: **386 records**, SHA-256 **e042b6db1f62af331f8fae778df40864a113be7bf5e18671c43ea6f55d121f2f**. [Indicator descriptions endpoint documentation](https://sharadar.com/docs/descriptions)
- Fundamentals covers the **primary common security** and exposes AR/MR filing dimensions; its marketcap is in USD and Price is split-adjusted. Listing coverage does not certify uniform class/perimeter treatment. [Fundamentals documentation](https://sharadar.com/docs/fundamentals)
- stocks/SEP offers split-adjusted close, unadjusted close and a separately total-adjusted close. Adjustment basis must match share units; dividend-adjusted close must not silently enter a marketcap reconstruction. This account could not fetch that table. [Stocks documentation](https://sharadar.com/docs/stocks)
- ACTIONS includes splits, ADR-ratio changes, listings/delistings, merger/acquisition and relation events. Daily delivery and broad ticker coverage do not assert a complete issuance/repurchase/treasury ledger. [ACTIONS documentation](https://sharadar.com/docs/actions)

Provider documentation describes DAILY as point-in-time/as-reported. That is a provider claim; this audit does not change RawCandle's non-PIT reporting label or certify revision-free historical replay.

## Formula audit and compatible dates

DAILY has no price field. The task's `daily_price` must be explicitly selected from a compatible price source. Two tests were kept separate:

1. **Exact accepted filing date:** `DAILY.marketcap × 1e6 / native SF1 Price` versus accepted `sharesbas × declared sharefactor`. All inputs share the original accepted provider date; current prices are not mixed into this test. Missing/nonpositive factor, price, cap or same-date DAILY rows are excluded and remain missing, not zero.
2. **Latest available DAILY date:** `DAILY.marketcap × 1e6 / local exact-date close` versus the latest accepted factor-adjusted count. This tests continued carry-forward but is cross-vendor diagnostic evidence. There are **2,445 latest exact-date pairs**, of which **2,328** also have usable accepted count/positive factor.

Absolute relative residual is `100 × abs(implied_units / accepted_factor_units − 1)`. No factor is derived or stored from cap/PB. Below, cohort memberships overlap; statistics are linear-interpolated percentiles over companies, not weighted by cap.

### Exact filing-date results

| Cohort | N | Median residual % | P95 % | ≤0.01% | >1% | >5% |
|---|---:|---:|---:|---:|---:|---:|
| all | 2327 | 0.000754 | 0.102312 | 1949 | 11 | 1 |
| factor_one | 2317 | 0.000753 | 0.101242 | 1944 | 11 | 1 |
| nonunit_positive_factor | 10 | 0.006301 | 0.116183 | 5 | 0 | 0 |
| ADR_labelled | 25 | 0.000804 | 0.097138 | 20 | 0 | 0 |
| Primary_Class | 453 | 0.001204 | 0.283712 | 341 | 3 | 0 |
| known_multi_class | 16 | 0.000285 | 0.031107 | 14 | 0 | 0 |
| reviewed_ordinary | 16 | 0.000023 | 0.000116 | 16 | 0 | 0 |
| reviewed_ADR | 5 | 0.011799 | 0.123792 | 2 | 0 | 0 |

Across the 2,327 compatible latest observations: **10** residuals are below 1e-8%, **1,949** are ≤0.01%, **2,209** ≤0.1%, and **2,316** ≤1%. Native same-row cap's tighter previous P/B.6 fit cannot be expected from DAILY's coarse rounding. Zero/missing factor cases, including SCNI, are not silently replaced by one.

### Latest-date cross-vendor results

| Cohort | N | Median residual % | P95 % | ≤0.01% | >1% | >5% |
|---|---:|---:|---:|---:|---:|---:|
| all | 2328 | 0.000815 | 0.194631 | 1922 | 32 | 6 |
| factor_one | 2318 | 0.000812 | 0.195231 | 1917 | 32 | 6 |
| nonunit_positive_factor | 10 | 0.026537 | 0.123876 | 5 | 0 | 0 |
| ADR_labelled | 25 | 0.000649 | 0.114790 | 20 | 0 | 0 |
| Primary_Class | 453 | 0.001278 | 0.398754 | 341 | 9 | 1 |
| known_multi_class | 16 | 0.000245 | 0.045341 | 14 | 0 | 0 |
| reviewed_ordinary | 16 | 0.000017 | 0.000057 | 16 | 0 | 0 |
| reviewed_ADR | 5 | 0.051603 | 0.123497 | 2 | 0 | 0 |

Current >5% outliers are **AVB, FRGT, GPMT, GUTS, VSTD, XXII**. These are diagnostics requiring reconciliation; do not invent an issuance/split cause from residual alone. The optional outlier CSV also includes filing-date, reviewed-factor and A/C differences, so its row count is not the same as this six-case threshold.

## Temporal and staleness tests

Analyzed **4,304 accepted-filing intervals** with ≥10 matched daily observations, **1,883** bounded by a following accepted ARQ and **2,421** trailing/open intervals ending at the audited cutoff. A future filing was not invented for an open interval. Local quotes and provider cap are required on the same date.

The captured DAILY caps are rounded in **0.1 million USD increments**, giving a cap-rounding allowance of **±50,000 USD**, or **±50,000 / close** implied units. Near-constant means each interval point lies within that rounding allowance plus **0.1%** of its median units; the 0.1% is a research diagnostic allowance, not a new production gate.

- Floating-point inferred units are literally constant in **0 / 4,304** intervals; this reflects rounded cap/price division and must not be called evidence of changing shares.
- **2,629 / 4,304** are near-constant; **1,675** contain larger excursions. Dropping each interval's first three sessions as a separately labelled filing-transition diagnostic changes near-constant count to **2,700**, not proof of a different source contract.
- Starting intervals on/after June 1 gives **2,415 / 2,569 (94.0054%)** near-constant. Many earlier cross-vendor spikes reverse on the following session, including common May 19–20 effects. Without entitled same-provider price history, those excursions cannot be attributed to real share changes.
- Interval endpoint absolute change median **0.001285%**, P95 **0.448059%**; **129** intervals exceed 1%, **44** exceed 5%.
- Meaningful consecutive-day proxy steps, after combined rounding allowances and 0.1%, number **9,908** across **2,418** companies. **3,427** are within three calendar days of an accepted ARQ date and **54** within three days of a relevant stored split/ratio/merger/spinoff/acquisition action; these sets may overlap. Temporal association is not causation. Remaining steps are not independently verified ownership updates.
- Conservative company classification across all qualifying intervals: **858 DAILY_UNITS_QUARTER_CARRY_FORWARD**, **1,610 MIXED/UNKNOWN** (including insufficient history/pairs). **Zero DAILY_UNITS_DYNAMIC approvals as an independently current share-count source.**

Specific verified filing alignments: BABA changes to approximately 2,333,875,000 ADS-equivalent units on August 20 and then retains that old base through October 7; MSTR changes at its August 3 filing to approximately 384,225,751 and retains that base after the disclosed October sales; SCNI's clear unit step is August 26 (new filing), not a newly observed October count. The two sides of stock/ADR splits also require adjustment-aware prices; this audit cannot certify raw pre/post split units from split-adjusted Yahoo closes alone.

**Conclusion:** there are numerical changes and filing/action adjustments, but this is largely a quarterly filing-count carry-forward series. The data does not establish a continuously refreshed actual outstanding-share ledger between filings.

## Mandatory issuer and ADR samples

Native ARQ counts/perimeters and official ratios reuse the evidence in the [P/B.6 audit](fundamentals_v4_pb_ownership_basis_audit.md) and original [V1 registry](../../rawcandle/fundamentals/ownership_reviews_v1.json); official URLs remain in the company CSV. These are dated evidence, not a new review through October 8. All 24 samples below have 110 DAILY rows ending October 7.

| Ticker | DAILY date | Implied units | ARQ sharesbas | Declared factor | Exact reviewed factor | Residual to declared % | Conclusion |
|---|---|---:|---:|---:|---:|---:|---|
| BABA | 2026-10-07 | 2,333,874,766.4 | 18,671,000,000 | 0.125 | — | 0.000010 | Old August base; August placement not incorporated |
| MSTR | 2026-10-07 | 384,225,740.9 | 384,225,751 | 1.0 | — | 0.000003 | Old 384.226m aggregate; October issuance not established |
| DBVT | 2026-10-07 | 59,211,870.3 | 296,061,497 | 0.2 | — | 0.000725 | Old 59.212m ADS proxy; post-count sales not reconciled |
| QNRX | 2026-10-07 | 3,510,638.4 | 70,294,615 | 0.05 | — | 0.116433 | Old ~3.515m ADS proxy; coarse rounding, placement unresolved |
| BTCT | 2026-10-07 | 9,537,036.7 | 9,516,975 | 1.0 | — | 0.210799 | Old ~9.517m base; registration is not proof of settlement |
| SCNI | 2026-10-07 | 530,973.5 | 22,800,887,584 | 0.0 | 2.5e-05 | N/A | Official 1/40000 interval-compatible; zero stays unusable |
| GPCR | 2026-10-07 | 71,308,095.1 | 213,929,572 | 0.333 | 0.3333333333333333 | 0.097626 | Exact ADS ratio closer than rounded .333; dated count |
| MREO | 2026-10-07 | 159,773,377.8 | 798,454,864 | 0.2 | 0.2 | 0.051603 | 1/5 ADS convention; dated count |
| ONC | 2026-10-07 | 113,667,659.1 | 1,478,124,405 | 0.077 | 0.07692307692307693 | 0.129965 | Exact 1/13 closer than rounded .077; dated count |
| ZLAB | 2026-10-07 | 112,267,880.7 | 1,122,662,280 | 0.1 | 0.1 | 0.001472 | 1/10 ADS convention; whole ordinary base proxy |
| ARM | 2026-10-07 | 1,068,000,153.6 | 1,068,000,000 | 1.0 | 1.0 | 0.000014 | 1/1 ADS; provider rounded old count persists |
| BHP | 2026-10-07 | 2,540,695,809.7 | 5,081,391,706 | 0.5 | — | 0.000002 | 1/2 convention; treasury/perimeter unresolved |
| BIDU | 2026-10-07 | 339,499,401.7 | 2,716,000,000 | 0.125 | — | 0.000176 | 1/8 convention; multiple classes remain unresolved |
| HEI | 2026-10-07 | 139,757,252.6 | 139,757,405 | 1.0 | — | 0.000109 | Primary HEI price × aggregate HEI + HEI.A shares |
| F | 2026-10-07 | 3,987,599,047.6 | 3,987,595,667 | 1.0 | — | 0.000085 | Primary price × common plus unlisted B aggregate |
| CMCSA | 2026-10-07 | 3,548,634,102.4 | 3,548,636,573 | 1.0 | — | 0.000070 | Primary A price × A+B aggregate |
| TSN | 2026-10-07 | 351,800,768.5 | 351,801,512 | 1.0 | — | 0.000211 | Primary A price × A+B with different economic allocation |
| WSO | 2026-10-07 | 41,252,079.4 | 41,252,194 | 1.0 | — | 0.000278 | Primary common price × common+B aggregate |
| BIO | 2026-10-07 | 26,738,148.6 | 26,738,175 | 1.0 | — | 0.000099 | Primary A price × A+B; asymmetric class rights |
| PCG | 2026-10-07 | 2,680,109,468.5 | 2,680,110,496 | 1.0 | — | 0.000038 | Cover count includes subsidiary-held parent shares |
| SDRL | 2026-10-07 | 62,541,424.3 | 62,541,443 | 1.0 | — | 0.000030 | Cover count/retired-unit perimeter remains unresolved |
| BA | 2026-10-07 | 790,370,084.0 | 790,370,020 | 1.0 | — | 0.000008 | Reviewed common perimeter; old filing count still used |
| GM | 2026-10-07 | 877,451,560.4 | 877,451,541 | 1.0 | — | 0.000002 | Old cover count; no continuous repurchase assurance |
| PSA | 2026-10-07 | 175,621,127.4 | 175,621,134 | 1.0 | — | 0.000004 | Reviewed common perimeter; preferred caveat unchanged |

For GPCR/ONC, exact reviewed ratios fit better than the displayed rounded provider factor; for SCNI the official ratio remains a valid comparison witness while provider zero remains unusable. SCNI's latest implied units **530,973.45** versus exact-factor **570,022.19** differ by **6.850389%**, but its cap **0.6 million USD** implies a broad **±44,247.79-unit** rounding interval: the official count falls inside it. This is **rounding-compatible**, not precise independent count evidence. No ratio was inferred from this division. The five positive declared-factor reviewed ADR cases all fit within 1%; that algebra does not establish continuing ratio or count validity.

## Known post-quarter actions

- **BABA:** the P/B.6 official August 26 return records 19,884,988,918 closing ordinary shares; DAILY still implies approximately 18,671,000,000 ordinary shares via ×8. It did not replace the stale accepted base with that disclosed newer total. Current ACTIONS has no BABA event in this window. [Official share return](https://www.sec.gov/Archives/edgar/data/1577552/000110465926101020/tm2624074d1_ex99-1.htm)
- **MSTR:** the already-reviewed October 5 filing discloses 92,894 Class A shares sold October 1–4; DAILY October 7 remains within approximately ten units of the old 384,225,751 aggregate proxy. It does not demonstrate a reconciled new settled base. ACTIONS supplies preferred-security relations, not those issuances. [Official report](https://www.sec.gov/Archives/edgar/data/1050446/000119312526413164/mstr-20261005.htm)
- **DBVT / QNRX:** the P/B.6 July ATM sale and August 31 placement evidence remains unresolved; DAILY is still approximately the old factor-adjusted count, with QNRX materially coarsened by rounding. No event-to-settled-count reconciliation can be verified. [Prior evidence and official references](fundamentals_v4_pb_ownership_basis_audit.md)
- **BTCT:** registration does not establish how many shares settled. DAILY's near-old count does not resolve the missing witness; it is not a confirmed correctly reflected issuance.
- **SCNI:** newly fetched ACTIONS records both **split 0.1** and **adrratiosplit 10** on August 21. This is useful ratio-event evidence absent from the stale local action table. Its final cap is compatible with the independently reviewed official factor after allowing cap rounding. Full pre/post adjustment and ongoing-share assurance remain unverified. Do not apply both actions to counts twice.
- **GM / SDRL:** DAILY near-equality to the last cover count does not establish post-count repurchases/retirement treatment. SDRL's prior retired-unit mismatch remains held.

**Correctly reconciled current-count replacements verified for the five newer-base scopes BABA/MSTR/DBVT/QNRX/BTCT: zero.** BABA and MSTR supply direct counterexamples to trusting a fresh cap date as a fresh count. SCNI supplies one useful ratio-event record/rounding-compatible factor example, not a newly reconciled whole-company share count. The report does not assert unknown events absent.

## Mandatory multi-class and perimeter stress test

All **16 known multi-class scopes** match the dated provider aggregate formula within 1% (median filing-date residual **0.000285%**). This confirms arithmetic convention, not safe economic equivalence.

The P/B.6 official class counts show HEI **55,241,647 quoted common + 84,515,758 HEI.A = 139,757,405** shares. DAILY matches **HEI price × that aggregate**, rather than a separately reconstructed `HEI price × HEI shares + HEI.A price × HEI.A shares`. F similarly combines 3,916,743,591 quoted common and 70,852,076 unlisted B; CMCSA combines quoted A and unlisted B. TSN, WSO and BIO also retain the known aggregate class proxy, with economically different/independently quoted classes.

Secondary-class prices HEI.A, WSO.B, BIO.B, KELYB, UHAL.B and HVT.A are absent from local quotes and were unavailable through this account's stocks entitlement. Thus **no empirical class-specific market-value sum was fabricated**. Independent dated class structures plus primary-price/aggregate reconstruction already disqualify a universal true-whole-company interpretation. CHTR's earlier quoted-A-only example and CWEN's LLC/NCI problem show that not all issuers share one aggregate convention.

For **PCG**, provider arithmetic retains the parent cover count that includes subsidiary-held parent shares; for **BHP**, the treasury perimeter is unresolved; for **SDRL**, repurchased/retired unit treatment remains unresolved. DAILY formula agreement cannot solve consolidated treasury or parent-only denominator alignment. Preferred listings must not be added to common numerator, while the canonical parent-equity denominator still has preferred-capital exclusion unproven. Identity overrides preserve official common form but cannot turn quarterly counts into current counts.

**Multi-class safe approvals: zero.** Broad direct DAILY substitution would preserve or worsen primary-price, treasury and economic-perimeter mistakes rather than cure them.

## Current ACTIONS coverage audit

Read-only paginated fetch obtained **23,122 unique action keys**, **2026-05-01–2026-10-07**, in **three pages** (10,000 + 10,000 + 3,122). This demonstrates terminal-page acquisition of that bounded query, **not semantic completeness of ownership events**. Fresh fetch timestamps are recorded in the runtime artifact. No fetched events were published into Production.

Observed categories: dividend **17,685**, relation **2,108**, listed **1,085**, split **438**, delisted **378**, tickerchangefrom/to **280 each**, acquisitionby/of **89 each**, exchangefrom/to **83 each**, spacunitseparation **80**, namechangefrom/to **78 each**, acquisitioncash **66**, regulatorydelisting **40**, sicchangefrom/to **36 each**, acquisitionstock **27**, spacmerger **16**, adrratiosplit **16**, bankruptcyliquidation **15**, spinoff/spunofffrom **8 each**, voluntarydelisting/spinoffdividend **6 each**, mergerfrom/to **3 each**, acquisitionelectcash/stock **1 each**.

No general issuance, buyback, cancellation or treasury-share-change category appears in the provider action-type definitions or this extract. Relations identify related securities, not issued-count settlement. Listings/delistings and mergers help invalidate scopes, but do not quantify the surviving company's complete current share base. Existing bootstrap filters and the stale 156-row Production subset are especially insufficient; even a new continuous full ACTIONS sync would still lack this semantic assurance.

The existing Fundamentals scheduler/refresh does not refresh actions or DAILY. There is no action coverage watermark; an endpoint fetch timestamp or final page is not a statement that every economically relevant share event is represented. Refresh's existing fundamentals watermark must not be relabelled as one.

## Three numerator paths and stale/delisted behavior

Path A is the unchanged production formula/eligibility: **1,690** valid. Path C (`DAILY cap USD / positive accepted parent equity`) has **2,125 arithmetic values**, **2,114** with a DAILY date no older than October 5. These counts deliberately do not claim ownership, accepted-equity freshness, delisting, current-price or other hard-gate eligibility. Path B (`current price × DAILY implied units / equity`) has **2,114 arithmetic values**, with **1,689** comparisons to valid A; one additional valid-A case lacks the matching DAILY-date quote.

| Comparison | N | Median absolute % | P95 % | >1% | >5% |
|---|---:|---:|---:|---:|---:|
| A versus B, isolating count-proxy difference | 1,689 | 0.000719 | 0.089056 | 13 | 2 |
| A versus C, including date/price differences | 1,690 | 0.000722 | 0.090727 | 14 | 3 |

Path B and C are **algebraically the same provider evidence** when price/date/unit match: **2,105** pairs match to a maximum **2.22e-14%** numerical residual. Nine pairs use different quote dates, so B/C equality is not asserted there. B provides no independent numerator validation.

A/B >1% cases: ARAY, ATPC, ELAB, FRGT, GNLN, GRI, HCWB, HRTX, ISPC, MYSZ, ONCO, XAIR, XXII. Microcap rounding and quote/basis differences require reconciliation, not automatic adoption of C. FRGT and XXII exceed 5%.

**QRVO is a material cross-table counterexample:** DAILY's October 6 cap is **182,653.2 million USD**, while newly fetched ACTIONS delisting/acquisition records carry a **10,072.3 million USD** final cap, stock consideration 0.96 SWKS plus 32.5 USD cash. The exact October 6 local quote is absent, and the old current report selects October 5. A/C disagreement is **1,713.4275%**. Do not choose a replacement cap, infer a count or treat the fresh date as a safe merger-adjusted company identity; reconciliation is required. This is research evidence only and no production gate was changed.

Nineteen members have no DAILY rows in the audited window: **ALUR, BATRK, BELFB, BSLK, BTAI, CERO, CYCN, DOMO, GWH, HLX, HWH, LESL, LYRA, MAPS, MSPR, NOTE, PSKY, PTIX, SSKN**. Three have latest raw cap zero (**AREB, CDT, WHLR**), and **QRVO** lacks the matching exact-date local quote; therefore these four have no usable cap/close pair. A rounded zero must not be treated as an actual zero share count. Old/delisted endpoints must not be refreshed by carrying cap forward, and a new listing's presence does not establish a fully mapped issuer perimeter.

## Coverage policies: arithmetic versus approved evidence

| Policy | Arithmetic availability | Evidence-supported new current-source approvals | Interpretation |
|---|---:|---:|---|
| A existing production | **1,690 / 2,468** | Not a new source approval | Retained approved reporting approximation; no durability recertification |
| B independently safe DAILY | **2,114** fresh positive candidates | **0** | None has an independently current count/completeness contract established here |
| C broad DAILY with obvious exceptions | **2068** mechanically screened candidates | **0** | Removing known ADR/multi-class/perimeter/ambiguous identities does not prove the rest current |
| D maximum defensible new current-source combination | No count optimization | **0** | Recommend no new numerator/lifecycle approval; existing A remains unchanged |

For C, the mechanical screen excludes ADR/ADS-labelled categories, the known 16 multi-class and three separately classified perimeter scopes, and composite canonical tickers. It intentionally does not purport to discover all hidden classes or perimeter problems. **2,068 is not a safe coverage forecast.** All existing negative/missing equity, ownership, multi-class, newer-count and KALA/FTFT share-basis holds remain unreleased. The current calendar-expiry reason masks some original V1 held reasons, as documented in P/B.8A.

P/B.8's 1,722 is historical rollout coverage. Today's 1,690 follows current inputs plus V1 expiry. Do not present the 31 original reviews or 2,114 raw DAILY arithmetic values as safe October 8 releases. **Reviewed ordinary/common safe new-source count 0; reviewed ADR safe new-source count 0; multi-class safe count 0.** A remains operationally unchanged, but is not recertified here as a complete new continuous-share contract; QRVO illustrates an additional known action concern requiring later authorized reconciliation.

## Source alternatives and required ingestion contract

Within the authenticated 386 indicator definitions, outstanding-share fields exist in **fundamentals** (`sharesbas`, `shareswa`, `shareswadil`), not DAILY, stocks, metrics or ticker metadata. Insider transaction/owned-share fields are holder-specific, not whole-company outstanding shares. Quarterly `ncfcommon` is a net cash-flow amount, not an event-complete issued/retired share count. Ticker `scalemarketcap` is a category, not a daily numeric cap.

| Candidate | Frequency/depth and availability | Required change and limitation |
|---|---|---|
| `/data/daily` | Daily; December 1998 history; Fundamentals entitlement works | New versioned observation store, USD-million normalization, complete paginated/date acquisition and correction tracking. Underlying count remains latest filing; does not solve the gap |
| `/data/fundamentals` sharesbas | Filing updates, history January 1998; already ingested | Preserve actual cover count source date and revised observation linkage; subsequent filing updates are not current daily share counts |
| `/data/stocks` close/closeunadj | EOD, December 1997 history; current account returned 403 | Entitled same-provider price history needed for exact adjustment-aware tests. A price subscription still supplies no current shares field |
| `/data/actions` + `/data/tickers` | Daily delivery, action history January 1998; research fetch works | Separate continuous acquisition, scope/watermark/corrections and invalidations; still no complete issuance/buyback/treasury settlement ledger |
| `/data/metrics` | Latest per-ticker price/statistics snapshot, not a shares ledger | Documented fields contain price/volume/technical ratios, no current numeric marketcap/shares field. It cannot replace DAILY or certify the count [Metrics documentation](https://sharadar.com/docs/metrics) |

No additional current/daily share endpoint is documented in this project's provider integration or the authenticated table/indicator catalog. This is a bounded negative finding, not a claim about every possible bespoke commercial provider product. Clarification from Sharadar could establish whether a separately contracted current-share source exists; no such contract was obtained here.

Rate/volume evidence: the audit needed 83 bounded DAILY calls for 2,479 quote tokens over 110 sessions, plus three action pages and small schema/definition/availability probes. Production should use date-filtered complete snapshots or tested bulk/delta acquisition, honor the existing 0.5-second client pacing, and verify all pages. No incremental subscription price or guaranteed quota was inferred; stocks requires an entitlement decision. Historical coverage claims do not remove revision risk or source-state preservation needs.

Before approving any new current source, require versioned identity (company/security/issuer/listing/unit), currency/scaling, event-effective versus fetched/lastupdated dates, explicit count source date, verified-through coverage scope, settled-count reconciliation, and correction/replay policy. A missing page, failed fetch, stale watermark, new security/class/perimeter or official ratio conflict must hard-hold. For a future EOD cap candidate, require the expected completed US session and ≤3 calendar-day price fallback as an outer ceiling, plus a separately justified count/event freshness rule; that price ceiling alone cannot establish count freshness. None of these proposed requirements changes Production.

## Explicit decision answers

1. **Genuinely current?** No independent current count: largely last-filing carry-forward with price and adjustment updates.
2. **Whole-company?** Partial provider proxy; primary-class pricing and inconsistent class/treasury/perimeter conventions prevent universal whole-company common-value semantics.
3. **Sharefactor incorporated?** Yes by definition and positive-factor empirical fit; do not multiply DAILY cap by it again. Displayed rounded/zero factor still needs independent official interpretation.
4. **Cap/price usable as economic units?** Partial: rounded provider-implied economic-unit proxy when date/currency/quote basis match, not a current share-count witness.
5. **Safe replacement for the current numerator?** No approval under the required continuous evidence standard.
6. **Eligible categories?** No newly approved current-source category. Dated ordinary/common, reviewed identity and reviewed ADS comparisons remain diagnostics/candidates only.
7. **Must remain held?** Multi-class, unresolved treasury/LLC/parent perimeter, unresolved identity/ratio, stale/missing count/price/equity, known intervening unsettled actions and existing share-basis holds.
8. **Solves P/B.8A?** No.
9. **Remaining prerequisite?** A genuinely dated current count/cap source with explicit issuer/unit/perimeter and intervening-event reconciliation/coverage, or a separately demonstrated automation contract that supplies those witnesses. DAILY/ACTIONS alone does not provide it.
10. **Normal daily ingestion without manual review?** It can automate data acquisition and known invalidations; it cannot supply missing semantic assurance or justify durable approvals by itself.

## Validation, production safety and artifacts

Deterministic read-only calculations checked query caps/filters/unique keys, USD conversion, finite positive exclusions, exact source-date joins, rounding diagnostics, percentile and cohort accounting, 2,468 unique CSV members, 24 mandatory/extended samples and all 16 multi-class scopes. Raw research inputs, analysis summaries and scripts remain under `/tmp/rawcandle_pb9` and `/tmp/pb9_*.py`; no helper or ingestion implementation is added to source. The compact audit CSV records native source ticker, observation/hash, DAILY fetch/date, declared/official factor, diagnostics, classification and explicit `safe_daily_approved=False`.

All source provider/canonical/analysis/market file hashes, sizes and mtimes and active manifest bytes were checked before/after analysis and stayed identical. Provider, canonical and analysis SHA-256 match the deployed P/B.8 set. Registry, scheduler configuration and Review Queue physical hashes are unchanged; no queue operation was performed. No source/test changes, score calculation, migration, reconciliation, publication or new lifecycle implementation was executed. Provider P/B/4Q functions and source data are unchanged. No test run was needed for documentation/read-only research; **full suite not run**. Compact CSV validations and git diff --check passed.

Deliverables: this report, the **2,468-row audit CSV**, **39-row outlier CSV**, and **four-policy sensitivity CSV**. Commit only these four artifacts. Runtime DBs/raw downloads/caches/logs and unrelated existing changes remain outside Git. **Production DBs changed: NO. Active generation changed: NO. Current P/B formula changed: NO. Ownership registry changed: NO. Provider P/B changed: NO. Fundamental/Valuation Score changed: NO. Scheduler changed: NO. Push: NO.**
