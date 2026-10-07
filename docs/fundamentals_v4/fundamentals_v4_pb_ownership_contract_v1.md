# P/B.7 — Reviewed ownership basis contract V1

As of **2026-10-07**; baseline P/B.5 **c10d19bf** and P/B.6 audit **9e3d178e**. Active generation **publication_drain_20261007T093516Z_fd654a20**. Validation used a fresh inactive canonical copy, not Production rollout.

## Result

Implemented **PB_OWNERSHIP_BASIS_V1** as bounded evidence for the existing **PB_CURRENT_PARENT_EQUITY_V1** reporting calculation. Coverage is **1722 / 2468 = 69.77309562%**, exactly **+31** over **1,691**. Releases are **16 ordinary/common, six exact ADS-factor, nine official direct-common identity overrides**. The newly valid company/observation set equals the P/B.6 independently-supported set, not Policy B. No unreviewed Primary Class mass release occurred.

The original ownership cohort has **378** remaining invalid cases. There are **355** literal OWNERSHIP_BASIS_UNVERIFIED results, **16 MULTI_CLASS_UNVERIFIED**, and **seven NEWER_SHARE_COUNT_REQUIRED**. Do not mistake the refined 355 reason count for the total residual 378 population.

## Evidence Registry and Binding

`rawcandle/fundamentals/ownership_reviews_v1.json` is versioned, reviewable source evidence: **63 records**, comprising 31 supported records and 32 explicit holds. The remaining 346 unaudited scopes have no registry release. The original audit's 347 more-evidence cases include one explicitly reviewed PCG perimeter hold. Calculations contain no ticker-specific formulas, lists of calculation exceptions or provider-metadata rewrite.

Every record binds company_id, canonical company_key, security_id, canonical ticker, accepted observation_id and content_hash. It retains reviewed security type, economic perimeter, share-count/source date and its basis, effective interval, unit effective date, review timestamp/version, source URL/reference, exact factor numerator/denominator where applicable, accepted sharesbas, provider-declared factor, review notes and supported/held disposition. The review's canonical JSON SHA-256 is exposed in detailed output for reproducibility.

A company/security/ticker/observation candidate with incomplete or changed binding fails closed with OWNERSHIP_REVIEW_UNVERIFIED rather than falling back to the legacy ordinary gate. Changed observation/hash, company mapping, active target security or raw shares/factor cannot reuse evidence. No accepted provider fields or source hashes are rewritten. Result metadata is copied so modifying a returned diagnostic cannot mutate the registry's evidence.

The registry is a rebuildable reporting input loaded by the calculator; it does not create a canonical schema/table, production migration or second publishing path. Normal accepted field provenance still supplies raw sharesbas and parent equity from the same ARQ observation. Missing/revised field provenance still blocks the existing projection.

## Validity and Carry-Forward

The P/B.6 evidence review covers **October 7 only**. Every record therefore has effective_from = effective_to = **2026-10-07**. These are calculation-review boundaries, not inferred first listing dates. Unit-effective dates are separate: SCNI's ratio begins **August 21**, and other supported records conservatively anchor unit evidence to their share source date. Review timestamp and evidence version are retained. No future absence of corporate actions is inferred from missing provider observations.

Supported reviews expire after October 7 and return OWNERSHIP_REVIEW_STALE even if equity and price remain fresh. A later day requires explicitly reviewed evidence through that day and the same immutable binding or a new observation-bound record. This narrow validity is intentional: there is no complete current action/issuance feed in the existing reporting architecture.

Share source date must be on/before provider date and current price date; review/unit dates must cover the calculation and accepted observation. Maximum carry-forward is **180 calendar days**, matching the existing equity availability ceiling, but measured separately from the actual share source date. Share dates are retained even when filing availability is later. ARM uses the officially reported May 21 count as dated approximate evidence; the provider's rounded 1,068,000,000 differs from 1,068,078,760 by 0.007374%. This does not certify an independently observed October share count. NEGG/CAMT use accepted count dates with already reviewed official identity evidence; SCNI uses the accepted ordinary count with separately established official ratio. The registry labels these evidence distinctions explicitly.

Known unresolved issuance, repurchase, split, ADS-ratio or class events after share source date and through as-of block with NEWER_SHARE_COUNT_REQUIRED. Generic event handling blocks any post-source share-change evidence through as-of; a reconciled Boolean alone does not establish a new settled base. A refreshed observation-bound review and share-source date must cover that change; the bounded registry separately holds all seven P/B.6 newer-base cases without inferring settled counts from registrations, authorizations, ATM capacity, warrants or partial weekly sales. No automatic split adjustment is applied twice.

## Economic Unit Rules

For reviewed ordinary/common whole-parent common units:

```
economic_units = accepted sharesbas
```

A reviewed direct-common identity override uses the same rule and preserves the original provider ADR category as evidence. It is company/security/date/observation-bound and cannot relabel another issuer or revision.

For reviewed ADS:

```
reviewed_factor = positive integer numerator / positive integer denominator
economic_units = accepted ordinary sharesbas * reviewed_factor
current_market_cap_proxy = current complete valid quote * economic_units
Current P/B = current_market_cap_proxy / accepted positive parent_equity_usd
```

Supported exact ratios are GPCR 1/3, MREO 1/5, ONC 1/13, ZLAB 1/10, ARM 1/1 and SCNI 1/40,000. Whole-company ADS equivalents include ordinary shares held outside depositary certificates and controlling shareholders; they are not depositary float. Price must be the matching quoted security unit.

SCNI's declared factor stays **zero**; the official Nasdaq ratio dated August 21 supplies **0.000025**. The calculator never obtains that ratio from marketcap, pb or a replacement by one. GPCR/ONC use exact official factors while retaining rounded provider .333/.077 in diagnostics. Native price × reviewed economic units must still reconcile native cap within the existing **1%** tolerance. Provider P/B is never the current numerator/denominator.

The denominator remains parent equity with **preferred-capital exclusion unproven**, exactly as P/B.5. This is a common-market-value proxy against parent book equity, not a newly certified common-only book value. It does not value listed preferred shares or remove preferred equity. Known treasury/subsidiary/LLC/perimeter contradictions remain held; the existing general caveat is preserved rather than guessed away.

| Ticker | Basis | Declared / reviewed factor | Share source date | Economic units | Current P/B |
|---|---|---|---|---:|---:|
| BA | ORDINARY_COMMON | 1.0 / 1 | 2026-07-21 | 790,370,020.000000 | 24.59476115 |
| PSA | ORDINARY_COMMON | 1.0 / 1 | 2026-07-21 | 175,621,134.000000 | 5.46243447 |
| APTV | IDENTITY_OVERRIDE | 1.0 / 1 | 2026-07-31 | 207,633,331.000000 | 1.06082061 |
| NEGG | IDENTITY_OVERRIDE | 1.0 / 1 | 2026-06-30 | 20,974,000.000000 | 1.45949775 |
| CAMT | IDENTITY_OVERRIDE | 1.0 / 1 | 2026-08-10 | 46,668,177.000000 | 10.15621329 |
| GPCR | ADR_FACTOR | 0.333 / 0.3333333333333333 | 2026-07-31 | 71,309,857.333333 | 1.44630534 |
| MREO | ADR_FACTOR | 0.2 / 0.2 | 2026-08-10 | 159,690,972.800000 | 1.95071337 |
| ONC | ADR_FACTOR | 0.077 / 0.07692307692307693 | 2026-07-31 | 113,701,877.307692 | 7.97231984 |
| ZLAB | ADR_FACTOR | 0.1 / 0.1 | 2026-07-31 | 112,266,228.000000 | 4.73079912 |
| ARM | ADR_FACTOR | 1.0 / 1.0 | 2026-05-21 | 1,068,000,000.000000 | 37.44311441 |
| SCNI | ADR_FACTOR | 0.0 / 2.5e-05 | 2026-06-30 | 570,022.189600 | 0.05927609 |


## Remaining Holds

| P/B.6 classification | Remaining count |
|---|---:|
| MUST_REMAIN_HELD | 4 |
| REQUIRES_ADR_FACTOR_CONTRACT | 1 |
| REQUIRES_MORE_EVIDENCE | 347 |
| REQUIRES_MULTI_CLASS_CONTRACT | 16 |
| REQUIRES_NEWER_SHARE_COUNT | 7 |
| REQUIRES_OFFICIAL_IDENTITY_OVERRIDE | 3 |

Multi-class cases remain held: no aggregation at primary-class price, no rights-equivalence assumption from declared dividend parity, no inference from one canonical active ticker. PCG cross-holding, BHP treasury, SDRL repurchased/retired units and CWEN LLC/NCI conflicts remain unresolved. ASML/CLS retain identity/count evidence requirements. MSTR/BABA/DBVT/QNRX/BIAF/BRCC/BTCT need reconciled newer shares. GPMT/LEXX/NRDY/SEGG remain held, with original historical price warnings preserved. KALA/FTFT and BRTX/IESC/MNST retain the P/B.5 hard share-basis holds.

## Coverage and Provider Gap

Provider P/B remains available for **2,133** companies. Current P/B is **1,722**, leaving **411**. Ownership contributes **378 / 411 = 91.97080292%**; freshness/price contributes **28** (12 stale price, 10 missing price, six stale equity), and the other hard share-basis holds contribute **five**. Negative/missing equity contributes zero within this specific provider-available gap, while remaining an unavailable reason elsewhere in the universe.

| Current reason | Count |
|---|---:|
| MISSING_EQUITY | 120 |
| MISSING_PRICE | 10 |
| MULTI_CLASS_UNVERIFIED | 16 |
| NEGATIVE_EQUITY | 215 |
| NEWER_SHARE_COUNT_REQUIRED | 7 |
| OK | 1722 |
| OWNERSHIP_BASIS_UNVERIFIED | 355 |
| SHARE_BASIS_UNVERIFIED | 5 |
| STALE_EQUITY | 6 |
| STALE_PRICE | 12 |

Coverage CSV contains one row per 2,468 operational companies, baseline reason, newly-valid flag, refined reason, evidence release type, dates, raw/reviewed factor, economic units and review hash. Validation CSV contains **40** representative released and held companies. Original P/B.5 and P/B.6 artifacts remain historical evidence.

## Output and Architecture

Current P/B adds an ownership_basis detail object with contract, interpretation, release type, source date/basis, raw and exact reviewed factor, effective dates, immutable identity/observation binding, evidence status/URLs/reference, review version/hash and economic units. The compact section adds only **Ownership basis: Reviewed** and **Share source date** for supported evidence. Unreviewed legacy output stays identical. Current-price lookup still chooses latest complete positive valid OHLC on/before as-of with a maximum three-calendar-day fallback. Historical-close mismatch, incomplete-OHLC and missing-history diagnostics are unchanged.

Provider-reference output and 4Q history use their original projection/function and ignore current ownership reviews. Reporting-only snapshot attachment remains outside score and existing valuation calculations. No production/schema/scheduler/publication code was altered.

## Validation

Fresh inactive copy: `/tmp/rawcandle_pb7/fundamentals_v4.db`, backed up from the active canonical DB using a read-only source connection. Existing parent migration bound **89,912 quarters** and promoted **171,304 finite fields**. Logical SHA-256 of every original canonical table and all original financial columns matched before/after; foreign-key check passed.

Full-universe P/B.5 baseline reproduced 1,691 valid, and the candidate reproduced **exactly the 31 supported P/B.6 observation-bound releases**. All 2,468 Provider P/B reference objects and full 4Q history objects match baseline exactly. Every existing valid Current P/B value, accepted parent equity and current price date is unchanged. Exact reviewed-unit formulas were independently recalculated for released rows.

Complete real snapshot comparison passed for **14 companies**: AAPL, NVDA, BA, PSA, GPCR, ONC, SCNI, ARM, CAMT, MSTR, CWEN, SDRL, MCD, KALA. All non-book_value fields, financial/valuation history, score objects/fingerprints and unrelated valuation outputs equal baseline, and candidate rebuilds are deterministic. NEGG has a pre-existing broader snapshot limitation: both baseline and candidate fail with NO_FUNDAMENTAL_ENDPOINT_ON_OR_BEFORE_REPORT_DATE. Its direct P/B query, reviewed identity release and compact P/B rendering pass; this phase does not change the broader endpoint requirement. Any other baseline/candidate endpoint failures are listed here: `{"NEGG": "NO_FUNDAMENTAL_ENDPOINT_ON_OR_BEFORE_REPORT_DATE:NEGG:2026-10-07"}`.

Focused ownership/P/B tests: **80 passed**. Relevant Fundamentals/reporting regression group: **88 passed** across snapshot UI, V2 snapshot and additive provenance. Tests cover ordinary/Primary release, immutable diagnostics, scoped identity override, exact/nonunit/rounded/zero/missing provider factors, observation/hash/company/security/ticker binding, effective dates, future expiry, carry-forward age, all intervening action types, explicit newer/multi-class/perimeter holds, invalid ratios, active-security multiplicity, current-price constraints, unchanged provider/history and deterministic rebuild. Initial failures involved minimal test fixture identity schema and test import setup, fixed locally; no shared-core failure or full-suite escalation.

Production role DBs/market file sizes and mtimes and active manifest SHA-256/bytes remained unchanged. Read-only Production connections were used; only the inactive copy was migrated. CSV uniqueness/count/category checks and git diff --check passed before commit. **Full suite: NO. Production rollout: NO. Active generation change: NO. Score change: NO. Provider/4Q change: NO. Scheduler change: NO. Push: NO.**
