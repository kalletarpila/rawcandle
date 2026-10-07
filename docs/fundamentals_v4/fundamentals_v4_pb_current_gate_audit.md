# P/B.4 — Current P/B Coverage Reconciliation and Gate Audit

Audit date/as-of: **2026-10-07**. Source implementation: **6fbf22ef**. Audit only; no rollout or implementation changes.

## Executive Summary

**1595 IS TOO CONSERVATIVE. PAUSE_AND_CORRECT_GATES.** The exact 101 additional exclusions comprise **3 JUSTIFIED, 96 LIKELY_OVERFILTERED, 2 NEEDS_MORE_EVIDENCE**. “Likely” means the stated gate lacks independent contradictory ownership evidence in the bounded stored inputs; it does not certify every issuer's real-world economic share structure.

The biggest problematic rule is the hard **abs(sharesbas / shareswa − 1) > 25%** cutoff. Of 60 additional exclusions breaching it, 57 have no other implemented gate failure; one of these is the previously identified extreme KALA discontinuity. Ordinary endpoint stock and period EPS averages are different quantities. A second problem affects **40 matching historical closes**: rejecting the historical evidence because open/high/low geometry is invalid conflates the quality of a corroborating close with eligibility of the current valuation bar.

All 101 reproduce provider marketcap within 1% and have a valid same-row provider P/B. Three demonstrate incompatible historical price bases (BRTX, IESC, MNST). KALA and FTFT warrant review rather than an unsupported automatic verdict. With warning-only EPS-average differences, close-only historical corroboration and unresolved-case quarantine, the measured candidate is **1,691**. The conditional upper bound is **1,693** if both quarantined cases are independently cleared. This recommendation keeps ownership holds unchanged; their possible future resolution is excluded from that range.

## Coverage Funnel

### Apples-to-apples baseline

P/B.1 investigation/coverage, P/B.2 timing report and P/B.3 reporting/coverage/validation were inspected together with the exact current `book_value.py` and accepted-parent-equity contract. Existing P/B.3 candidate `/tmp/rawcandle_pb3/fundamentals_v4.db` is derived from active generation **publication_drain_20261007T093516Z_fd654a20**. Production canonical/provider/analysis and existing market data were opened SQLite **mode=ro**. Candidate was also opened read-only; no migration rerun.

A deterministic per-company query reproduced every P/B.3 primary reason in the committed coverage CSV. Operational company-ID sets match P/B.1, P/B.3 and candidate exactly; candidate and active universe membership tables match. Each company's selected fiscal year/quarter, accepted provider observation ID where present, USD equity and latest current price date match P/B.1. All 2,468 prices use USA market, as-of 2026-10-07, latest positive complete valid OHLC on/before that date; freshness is at most three calendar days. Equity freshness is at most 180 calendar days from own accepted source availability. Bound provider dates and source availability agree for all 1,696 strict candidates. No alternate richer observation was needed in P/B.1.

**Cohort/as-of/quarter/equity/current-price drift: 0 companies.** Metadata representation differs for 13 companies: 10 already MISSING_PRICE, two MISSING_EQUITY and one NEGATIVE_EQUITY. These are composite ticker/no-metadata representations and have **zero impact on the arithmetic, age, strict or final cohorts**. P/B.2's 1,848 authority-eligible latest rows plus supplementary reviewed quarters are a timing sample, not a replacement operational universe. Its close-only diagnostic differs from P/B.3's historical full-OHLC gate; that difference is expressly audited below.

| Stage | Input | Excluded | Remaining | Exact rule |
| --- | ---: | ---: | ---: | --- |
| Operational universe | 2,468 | 0 | 2,468 | Same active operational version, retained members included |
| Usable positive parent equity USD | 2,468 | 335 | 2,133 | 120 missing, 215 negative, zero zero balances |
| Valid accepted outstanding shares | 2,133 | 0 | 2,133 | Finite positive canonical sharesbas; two missing shares universe-wide already lack equity |
| Valid current price / arithmetic ceiling | 2,133 | 10 | 2,123 | Latest full valid positive OHLC, positive finite price × shares / equity |
| Age gates | 2,123 | 18 | 2,105 | 12 price age >3 days; six equity availability age >180 days |
| P/B.1 strict candidate | 2,105 | 409 | 1,696 | No factor/ADR/class/date quality notes and ACTIVE_SINGLE_SECURITY membership |
| P/B.3 ownership applied after P/B.1 strict | 1,696 | 0 | 1,696 | Allowed ordinary category, factor=1, one active target, no official conflict |
| P/B.3 share/basis checks | 1,696 | 101 | 1,595 | EPS-average, native cap and provider-date historical price gates |

The 409 ownership holds occur **before** the strict cohort: they are exactly the 409 age-eligible non-strict company IDs. Thus subtracting them again from 1,696 would double-count. Set checks: final-valid ⊂ P/B.1 strict, strict minus final = 101, final minus strict = 0, ownership minus age-eligible non-strict = 0 in both directions. The 101 all have SHARE_BASIS_UNVERIFIED, with no additional ownership loss.

### 2,123 → 2,105: only age

Mutually exclusive exclusions: **STALE_PRICE 12, STALE_EQUITY 6**; overlap zero, other date reasons zero. Price: APGE, AVB, CRNX, CYCN, GBTG, HLX, HWH, LBRDA, LEG, RMAX, TALK, TBPH. Equity: AREB, HUBG, MAPS, NOTE, SSKN, VSTD. Ownership notes can coexist, but are not counted at this stage.

### 2,105 → 1,696: exact P/B.1 reconstruction

Original predicate is arithmetic calculable AND no quality notes AND membership_status == ACTIVE_SINGLE_SECURITY. Notes are same-period alternate equity (zero here), factor !=1, category contains ADR, category contains Class OR active_security_count>1, current price >3 days old, canonical source >180 days old. No EPS-average, native-marketcap or historical-price hard gate was present. Known KALA/FTFT concerns were narrative/sample diagnostics and **did not enter this predicate**. P/B.1 was a research candidate count, not certified clean endpoint ownership.

On the 2,105 age-eligible rows overlapping diagnostics are class/multiple **391**, ADR **23**, nonunit/missing/zero factor **10**, stale **0**, alternate-source **0**, non-single membership **0**. Deterministic primary order ADR → class/multiple → factor → membership gives **23 + 383 + 3 + 0 = 409**. Exact overlap combinations:

| Notes | Count |
| --- | ---: |
| None | 1,696 |
| Class only | 382 |
| ADR only | 11 |
| ADR + class | 6 |
| ADR + factor | 4 |
| Factor only | 3 |
| ADR + class + factor | 2 |
| Class + zero factor | 1 |

Universe-wide missing-factor rows number 120 and already lack usable equity; none reaches this age cohort. Multiple active-security memberships remain in the universe, but none reaches the arithmetic age cohort. Retained inactive identities similarly contribute zero age-stage exclusions. “One active security” must not be read as proof that no unlisted economic class exists.

## Ownership Gate

**409** holds reconcile exactly. Mutually exclusive priority: official ordinary/provider-type conflict → remaining provider ADR evidence → zero factor → class metadata → remaining factor → other. This diagnostic decomposition differs from function short-circuit order but does not change eligibility.

| Primary ownership cause | Count | Evidence/confidence | Can whole-company cap be safely derived now? | Future contract |
| --- | ---: | --- | --- | --- |
| ADR/ADS provider category, without independent official ordinary override | 21 | Provider ADR metadata; not 21 independently verified depositary structures | Not established by this audit; factor 1 also does not prove no ADS ratio | Explicit depositary/underlying unit ratio and issuer perimeter |
| Provider ADR label but official ordinary/common | 2 | NEGG and CAMT; selected canonical 6-K frozen identity explicitly says common shares, is_adr_or_ads=false, provider_type_conflict=true | Same-row cap, factor 1 and historical close support it; current contract cannot adjudicate metadata override | Reviewed official identity override, provenance and temporal validity |
| Primary/multiple-class metadata, factor 1 | 382 | 381 Domestic Common Stock Primary Class, one Canadian Common Stock Primary Class; one active quoted security each | Not certified; active count does not enumerate all economic classes | Explicit outstanding units/class prices or validated whole-company cap factor |
| Zero/rounded sharefactor | 1 | SCNI, also primary class; rounded zero cannot encode an economic ratio | No: multiplying by zero gives zero despite positive provider cap | Higher-precision independently established factor and split base |
| Remaining nonunit factor | 3 | GPCR .333, MREO .2, ONC .077, labelled Domestic Common Stock | No under factor-one formula; provider formulas show substantial scaling | Explicit unit/factor contract and temporal basis |
| Multiple active securities | 0 | Eleven such members in universe, none reaches this reason | Outside usable-price cohort | Class ownership/perimeter mapping |
| Missing factor | 0 | Missing-factor/equity rows blocked earlier | No evidence in this cohort | Authoritative factor |
| Retained historical/inactive identity | 0 | Retained members blocked earlier | Not established | Verified active security identity |
| Other identity/category uncertainty | 0 | None after the above decomposition | — | — |

Sum **21+2+382+1+3 = 409**. Overlapping flags: original ADR labels 23, class warnings 391, factors !=1 ten. Among those ten, six are ADR-labelled, SCNI is zero/primary-class, three are remaining nonunit factors. Do not call every provider ADR label an actual ADS or every Primary Class label a proven capital mismatch. These are justified **unverified-contract holds**, not independently proved bad market caps. NEGG/CAMT are concrete candidates for a future reviewed identity contract, not silent exemptions in this audit. BTDR has similar stored ordinary/provider conflict evidence but MISSING_EQUITY, so contributes zero to the 409. No official-source acquisition or class discovery was performed.

## Share-Basis Gate

The CSV contains exactly one row for every strict-candidate rejection, all 101 company IDs, no successful rows. It includes original quality notes (empty for all), category, target-active count, sharesbas/wa/wadil, factor, native price/cap, reconstructed cap, historical full-OHLC and raw closes, current price date, secondary diagnostics, independent inconsistency count, assessment and explanation. All are category ordinary/common, factor 1, one active target, no selected official ADR conflict. Shares match canonical accepted sharesbas. Diluted EPS averages are retained evidence, never substituted for ownership shares.

| Overlapping gate combination | Count | Assessment |
| --- | ---: | --- |
| EPS-average deviation >25% only | 57 | 56 likely overfiltered; KALA needs evidence |
| Historical full-OHLC unavailable only | 39 | Likely overfiltered; raw closes reconcile |
| EPS-average >25% + historical full-OHLC unavailable | 2 | BROS likely overfiltered; FTFT needs evidence |
| Historical price mismatch only | 2 | IESC/MNST justified hold |
| EPS-average >25% + historical price mismatch | 1 | BRTX justified hold |
| Marketcap reconstruction failure | 0 | None |

Sum **101**; assessments **3 + 96 + 2 = 101**. Proven inconsistent evidence count is three, not 44: 41 missing full-OHLC rows are unavailable corroboration, not proved erroneous shares. Forty of those have matching raw historical closes; FTFT has no stored same-date close. KALA/FTFT's prior extreme diagnostic designation adds review priority, not a claimed independent split fact.

The exact denominator is **shareswa**, so the gate is asymmetric: abs(sharesbas/shareswa−1). A 50% endpoint shortfall and a 100% endpoint excess are symmetric reciprocals economically but treated differently by this statistic. It is not a normalization against outstanding shares or maximum of the two. Endpoint filing-cover ownership and period-weighted EPS shares can differ after issuance, repurchase or changes in share participation. A difference alone proves no specific event or error. Provider lists sharesbas separately from weighted-average EPS shares and identifies its price as adjusted close. [Sharadar fundamentals schema](https://sharadar.com/docs/fundamentals). Detailed split-adjusted cover/EPS definitions and formula interpretation are inherited from the P/B.1 investigation; the public descriptions page documents the description endpoint rather than exposing every indicator definition. [Sharadar descriptions](https://sharadar.com/docs/descriptions).

| Deviation band (strict exclusions) | Count | Demonstrated independent price inconsistency | Missing historical full OHLC | No other implemented gate failure | Examples |
| --- | ---: | ---: | ---: | ---: | --- |
| >25–35% | 16 | 0 | 1 | 15 | SLDB, MGRX, CNH, BROS |
| >35–50% | 13 | 1 | 0 | 12 | BMRA, SUN, BRTX |
| >50–100% | 17 | 0 | 0 | 17 | APVO, CVNA, RRR |
| >100% | 14 | 0 | 1 | 13 | DSP, EE, KALA, FTFT |
| ≤25% | 41 | 2 | 39 | 0 | IESC, MNST, TRU |

Of 60 average-deviation exclusions, **one has demonstrated independent price inconsistency (BRTX)**, two lack full OHLC (BROS/FTFT), and 57 fail average deviation alone. All 60 have clean provider cap reconstruction. No stored evidence reviewed here proves a corporate-action date or identifies a correct split ratio. Direct native BVPS is based on the EPS-average denominator; its divergence from equity/sharesbas repeats the same difference and cannot serve as independent confirmation of bad endpoint units.

### Clean ownership cohort

Factor=1, one active target, allowed ordinary category, no selected official conflict, and provider cap reconstruction within 1% define **1,856** operational rows. Outcomes: **1,595 OK, 155 NEGATIVE_EQUITY, four STALE_PRICE, one STALE_EQUITY, 101 SHARE_BASIS_UNVERIFIED**. Total failures **261**, or **106** after excluding negative equity. Restrict positive equity and age/current-price eligibility further: **1,696**, of which all 101 failures are the cases above; 57 fail solely because of weighted-average shares. This cohort is metadata-clean, not an independently verified universal single-economic-class cohort.

## Price-Basis Gate

The current valuation still requires complete valid current OHLC and the three-day freshness rule; that rule is appropriate and should remain. Historical provider-date price is corroboration from another observation date, not a numerator of Current P/B. A **positive finite exact-date close** can corroborate native price even when historical open/high/low fails geometry. Requiring a complete historical valuation-quality OHLC row is too strong for this purpose.

Among the 101: **41** lack valid full-OHLC history; **40** have finite positive exact-date raw closes matching native price within 1% (in fact all within 0.1%), **one FTFT** has no close. Thirty-nine are excluded solely by historical full-OHLC absence; BROS and FTFT also breach the average rule. Two other companies are price-mismatch-only; BRTX also breaches the average rule. Thus implemented historical-price-only exclusions total **41 = 39 unavailable-full-OHLC + 2 demonstrated price mismatch**. Do not combine these as 41 proved split errors.

Historical disagreement supports a **conditional ownership/basis hold** when inconsistent scaling remains unresolved. Treat mere missing historical corroboration as unavailable evidence, distinct from contradiction. Initially keep unresolved mismatches blocked; a future explicit corporate-action/security basis contract may establish the current reported-share base even if past prices differ. The 40 matching closes need no neighboring-date interpolation or inferred split adjustment. A blanket warning-only change to all historical mismatches is not recommended.

BRTX: provider price 3.778, raw/full-valid close 0.188899994, 95% error (20× provider/close). IESC: 372.27 vs 744.539978, ~100% error (2× close/provider). MNST: 45.18 vs 90.3600006, ~100% (2×). These are actual scale disagreements, **not proved split diagnoses**. P/B.2 already showed IESC/MNST incompatible histories and no supported split correction. BRTX is independently identified by this exact-date audit. No new corporate-action search was used to invent a cause.

## Marketcap Reconstruction

For the allowed factor-one cohort, same-row price × sharesbas is stronger evidence of the provider's endpoint denominator than price × weighted-average shares. It establishes internal consistency of the provider convention, not an independent issuer-certified current share count. Even KALA internally reconciles, so this test is necessary corroboration, not sufficient certification.

| Cohort | Cap reconstruction pass ≤1% | Fail >1% | Missing inputs |
| --- | ---: | ---: | ---: |
| Operational 2,468, unadjusted factor-one diagnostic | 2,337 | 11 | 120 |
| Arithmetic age-eligible 2,105, unadjusted diagnostic | 2,095 | 10 | 0 |
| P/B.1 strict 1,696, genuinely factor-one | 1,696 | 0 | 0 |
| Additional exclusions 101 | 101 | 0 | 0 |
| Average deviation >25% among exclusions | 60 | 0 | 0 |

Nonunit/zero-factor rows explain apparent failures in the unadjusted universe comparison; those rows require their factor contract, not automatic failure of provider arithmetic. CSV also includes price × sharesbas × sharefactor explicitly. Strict-cohort worst relative cap error is **0.1936084413%**. Therefore **marketcap-reconstruction-only exclusions = 0** and marketcap fail overlap with the 101 = 0. All 101 also pass **abs(marketcap/equityusd − pb) ≤ .0005001**. That provider-P/B consistency is a same-row diagnostic and does not make Current P/B depend on provider P/B equality; the prices/dates differ.

## Deep-Dive Examples

The following 34 targeted cases include 31 share-basis exclusions plus SCNI/NEGG/CAMT ownership holds. All share-exclusion rows have factor 1, allowed ordinary metadata and one active target; native cap and provider P/B reconcile. “Clean close” is same-date corroboration; “geometry” means raw close matches but full OHLC fails. Percentage is absolute endpoint/average deviation. Issuance/repurchase signs below are accepted-row ncfcommon cash-flow evidence; they do not prove the cause of the denominator difference, event date, or class structure.

| Ticker | Deviation % | Historical close | Accepted-row evidence / audit interpretation |
| --- | ---: | --- | --- |
| SLDB | 25.377 | Clean close | ncfcommon 48,471,000; Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| MGRX | 25.981 | Clean close | ncfcommon 272,000; Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| VERU | 26.030 | Clean close | Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| INO | 26.683 | Clean close | ncfcommon 3,247,068; Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| ELDN | 28.487 | Clean close | ncfcommon 91,000; Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| EDIT | 28.740 | Clean close | ncfcommon 117,535,000; Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| CNH | 29.902 | Clean close | ncfcommon -36,000,000; Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| FLNC | 33.640 | Clean close | ncfcommon 1,091,000; Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| CECO | 35.232 | Clean close | Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| IIIV | 35.542 | Clean close | ncfcommon -48,107,000; Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| HCWB | 38.281 | Clean close | ncfcommon 3,511,421; Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| QTTB | 46.342 | Clean close | ncfcommon 66,852,000; Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| BMRA | 47.857 | Clean close | ncfcommon 379,000; Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| INAB | 49.359 | Clean close | ncfcommon 11,000; Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| SUN | 49.621 | Clean close | Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| APVO | 50.621 | Clean close | ncfcommon 726,000; Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| CVNA | 53.334 | Clean close | ncfcommon 3,000,000; Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| RRR | 81.413 | Clean close | Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| DSP | 237.521 | Clean close | ncfcommon 623,000; Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| EE | 257.355 | Clean close | ncfcommon -23,946,000; Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| SYM | 372.220 | Clean close | Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| MOVE | 1003.115 | Clean close | ncfcommon 96,000; Endpoint/average difference with no independent contradiction; LIKELY_OVERFILTERED. Corporate/class cause unproved. |
| KALA | 25978.812 | Clean close | Previously identified extreme discontinuity. Cap arithmetic alone does not resolve current split/ownership basis; NEEDS_MORE_EVIDENCE. |
| FTFT | 2010.281 | Missing | Previously identified extreme discontinuity. Cap arithmetic alone does not resolve current split/ownership basis; NEEDS_MORE_EVIDENCE. |
| BROS | 29.881 | Geometry; raw close clean | Historical geometry alone is not ownership inconsistency; LIKELY_OVERFILTERED. |
| BRTX | 43.719 | Scale mismatch | ncfcommon 5,000,000; Demonstrated incompatible price scales; JUSTIFIED unresolved-basis hold, event cause unknown. |
| IESC | 0.001 | Scale mismatch | ncfcommon -136,000; Demonstrated incompatible price scales; JUSTIFIED unresolved-basis hold, event cause unknown. |
| MNST | 0.088 | Scale mismatch | ncfcommon 60,894,000; Demonstrated incompatible price scales; JUSTIFIED unresolved-basis hold, event cause unknown. |
| TRU | 0.364 | Geometry; raw close clean | ncfcommon -103,700,000; Historical geometry alone is not ownership inconsistency; LIKELY_OVERFILTERED. |
| CRM | 0.366 | Geometry; raw close clean | ncfcommon -5,000,000; Historical geometry alone is not ownership inconsistency; LIKELY_OVERFILTERED. |
| COP | 0.998 | Geometry; raw close clean | ncfcommon -2,004,000,000; Historical geometry alone is not ownership inconsistency; LIKELY_OVERFILTERED. |
| SCNI | 24.475 | Clean close | ncfcommon 2,315,000; Factor zero + primary class; provider cap cannot be reconstructed with the rounded factor; ownership uncertainty. |
| NEGG | 0.000 | Clean close | Official common/ordinary evidence contradicts provider ADR label; metadata conflict, no actual ADS shown. |
| CAMT | 0.054 | Clean close | Official common/ordinary evidence contradicts provider ADR label; metadata conflict, no actual ADS shown. |

SLDB and MGRX are just above the arbitrary boundary. CNH/IIIV/EE have negative ncfcommon (net purchase of equity), while EDIT/SLDB/QTTB have positive issuance flows: these observations show why duration-average and endpoint shares cannot be required to agree universally. They do not reconcile quantities on their own. CVNA/RRR/SYM have large differences despite “ordinary” provider categories: no issuer capital-structure review was performed, so economic single-class certainty cannot be claimed from these labels. KALA sharesbas 19,339,786 vs shareswa 74,159 (~260.8×); its cap and historical close nevertheless reconcile. FTFT 8,061,611 vs 382,016 (~21.1×), but same-date market close is absent. Both remain explicit unresolved examples; no hard-coded exemption or guessed reverse split is recommended.

## Sensitivity Analysis

Offline only; no source function/constants edited. Policy A reproduces all current coverage reasons. C and the additional B_WA_ONLY isolation reuse every existing date, ownership, canonical-share, marketcap and historical full-OHLC gate; only EPS-average eligibility is relaxed on a copied in-memory evidence row. Required Policy B follows the independent-inconsistency interpretation: it preserves the date, ownership, canonical-share and native-marketcap rules but treats weighted-average differences and absent historical corroboration as diagnostics; demonstrated historical price mismatches remain blocks. It therefore also measures the risk of proceeding when corroborating history is missing. Weighted-average shares remain original in the audit CSV and never become valuation shares. Missing/nonpositive averages remain a block in these isolated simulations (none in this strict cohort).

| Policy | Valid | New | Known anomalies admitted (KALA/FTFT/SCNI) | Risk indicators |
| --- | ---: | ---: | --- | --- |
| A: 25% hard cutoff | 1,595 | 0 | 0 | Known false-hold risk: 57 average-only and 40 matching closes rejected |
| B: independent inconsistency required; deviation/missing-history diagnostics | 1,693 | 98 | 2: KALA, FTFT | 14 new >100% deviations; FTFT lacks a historical close; internally clean native arithmetic is insufficient |
| B_WA_ONLY: isolate average rule, keep all other current gates | 1,652 | 57 | 1: KALA | 13 new >100% deviations; historical full-OHLC holds retained |
| C: 50% hard cutoff sensitivity | 1,622 | 27 | 0 | Arbitrary cutoff remains; no justification for 50% as ownership threshold |
| D: recommended correction + unresolved-case quarantine | 1,691 | 96 | 0 | 12 admitted >100% deviations still require visible warning; ownership metadata is not capital-structure certification |

Policy B admits KALA and FTFT because neither has a demonstrated independent contradictory price/cap value in the stored inputs; it keeps SCNI unavailable because ownership fails. C holds all three. B retains all three demonstrated historical price mismatches but relaxes 41 missing-full-OHLC holds, including the one genuinely absent close. The additional B_WA_ONLY count of 1,652 isolates the average cutoff and retains all historical evidence requirements. Neither warning-only simulation is a recommendation to admit known unresolved discontinuities. Policy C merely moves the cliff and misses 30 B_WA_ONLY admissions. D uses positive raw exact-date close to corroborate history and retains BRTX/IESC/MNST plus unresolved KALA/FTFT. D is a deterministic counterfactual on stored evidence, not implemented production eligibility. The sensitivity CSV records A/B/C admissions and risk counts; B_WA_ONLY and D are additionally recorded for review.

If only the historical geometry requirement is corrected while the 25% cutoff remains, the measured count is **1,634** (+39). If both EPS-average and historical-geometry requirements are corrected with raw-close corroboration, but KALA is not quarantined, it is **1,692** (+97); FTFT still lacks a close. **1,691** removes that one known unresolved admission. **1,693** is conditional on independently clearing both KALA and FTFT, not the result of accepting missing evidence automatically. No estimate includes relaxing the 409 ownership holds.

## Recommended Gate Contract

1. Keep finite positive accepted parent equity/shares, exact observation binding, USD basis, own-availability/as-of limits, 180-day equity freshness, latest complete valid current OHLC and three-day price freshness. Keep current reported-share-proxy and parent-equity/preferred-capital caveats. Keep factor/class/identity holds pending an explicit reviewed ownership-factor contract; preserve score isolation.
2. Replace the unconditional **25% EPS-average hard block** with a visible diagnostic. Require hard rejection to cite an independently demonstrated share/security/price-basis contradiction or explicit unresolved corporate-action evidence review. Never substitute shareswa/shareswadil for ownership shares. Sixty additional exclusions breach 25%; **57 are average-only, one independently inconsistent, two have historical evidence unavailable**. One average-only case, KALA, remains unresolved on the prior extreme-diagnostic review; that is a bounded review hold, not proof inferred solely from the threshold.
3. Keep same-row factor-one **price × accepted sharesbas ≈ provider marketcap within 1%**. It affects zero of the 101 as an independent failure. Internally consistent provider P/B supports diagnostics, never determines current eligibility by equality to Current P/B.
4. Replace historical **full-OHLC geometry** eligibility with **positive finite exact-date close corroboration** and explicit historical-evidence diagnostics. Forty rejected historical rows already corroborate the provider price; 39 have no average failure, BROS has both. Keep unresolved substantial historical scale discrepancies as ownership/basis holds until an explicit temporal split/share-unit contract resolves them. FTFT's absent close stays an evidence hold for this audit. Do not use a neighbor close, a fitted factor or an inferred split.
5. Define a reviewable unresolved-discontinuity contract before rollout: evidence reference, observation/split basis, affected validity interval and clearing condition. KALA/FTFT need such review; a generic 25% or 50% boundary cannot substitute for it. No ticker-specific production exception is proposed. Document that ordinary-category + one active ticker does not independently verify all economic classes; if official evidence contradicts metadata, use a separate reviewed identity/ownership contract rather than a permanent generic conflict veto.

Exactly **96** of the 101 have no demonstrated contradictory evidence or prior known unresolved discontinuity in this bounded audit: 56 average-only, 39 historical-geometry-only and BROS with both. They support the 1,691 counterfactual under the stated restricted proxy contract. The other **five** are three demonstrated scale contradictions plus two unresolved known examples. Revised range **1,691–1,693**, with the upper two requiring new evidence and no ownership-gate relaxation. This is a projected gate correction for review, not a promise that unexamined economic structures are universally valid.

## Production Readiness

**PAUSE_AND_CORRECT_GATES.** Do not roll out P/B.3 as the audited final contract: the universal average cutoff and historical full-OHLC corroboration rule do not support their rejection semantics. The reporting feature and storage/score isolation are not shown unsafe by this audit; the eligibility interpretation is too conservative. Revise those two rules and make unresolved-event review explicit before the normal immutable-generation publication path. Keep the date/equity/current-price, exact accepted-source binding, same-row marketcap and unresolved ownership rules unchanged. No live rollout was authorized or executed here.

Validation performed: read-only exact per-company output reproduction, company/quarter/observation/equity/current-price comparisons, set-difference reconciliation, every additional exclusion assessed, 409 ownership causes decomposed, 34 representative cases inspected, deterministic offline policy simulations and CSV count/uniqueness/assessment/finite checks. Active manifest bytes and all active canonical/provider/analysis, market and candidate database size/mtime remained unchanged. No SQL writes, source refresh, report publishing, score rebuild, live workflow or full suite. `git diff --check` and staged artifact-only review complete before commit.

Deliverables: this report, `fundamentals_v4_pb_current_gate_audit.csv` (101 rows), and `fundamentals_v4_pb_current_gate_audit_sensitivity.csv`. Audit helpers and full evidence extracts remain in /tmp and are not committed.

Source code changed: **NO**. Production DBs changed: **NO**. Live generation changed: **NO**. Reporting behavior changed: **NO**. Valuation Score changed: **NO**. Live workflows executed: **NO**. Full suite run: **NO**. Push: **NO**.
