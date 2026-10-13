# Missing-day HELD root-cause investigation — 2026-10-13

Investigation status: **PARTIAL**. Counts, control flow, local history boundaries and cross-provider diagnostics are verified. The rejected Yahoo comparison values were not retained, so the actual price-only/volume-only causes of all 475 mismatches remain unresolved. No application changes or recovery operations were performed.

## Evidence and scope

The frozen [completed report](../reports/missing_day_recovery/missing_day_20261013T174310150787Z_a166a775.json) covers **2026-09-22 / USA**. Implementation inspected at repository HEAD `81a944ee`: [validation and recovery](../services/missing_day_recovery.py), [Yahoo conversion and acquisition](../services/stock_update_service.py). Targeted current SQLite inspection used `mode=ro` and `query_only=ON`; no production database copies were made. Small independent analysis summaries were written under `/tmp`.

Additional evidence consists of already retained `outputs/ohlcv_gap_repair_20261013/massive_2026-09-{21,22,23}.json`, eight Yahoo probes in that directory, and the active Fundamentals generation manifest. These provider artifacts are local, uncommitted evidence; this commit contains only this report. No live provider retrieval was performed.

Labels throughout distinguish **VERIFIED FACT**, **SUPPORTED INFERENCE**, and **UNRESOLVED**. Current database observations are distinguished from the frozen recovery report.

## Verified counts

**VERIFIED FACT:** 4,524 examined = 429 existing + 4,095 missing; 4,095 = 3,043 inserted + 1,034 HELD + 17 unavailable + 1 legitimately unavailable. The original run reports zero existing rows modified/deleted, verified writes, and 1,052 remaining missing rows. These are historical run results, not writes performed by this investigation.

| Focus group | Cases | Established explanation | Actual rejected Yahoo comparisons retained | Canonical securities |
|---|---:|---|---:|---:|
| Adjustment/anchor mismatch | 475 | At least one neighboring comparison failed or was absent | 0 | 223 |
| No two-sided basis evidence | 265 | Following **stored** session absent in all 265 current histories | Not requested by this branch | 10 |

The complete frozen HELD distribution is:

| Reason | Count |
|---|---:|
| `ADJUSTMENT_OR_ANCHOR_MISMATCH` | 475 |
| `PROVIDER_IDENTITY_MARKET_MISMATCH` | 248 |
| `NO_TWO_SIDED_BASIS_EVIDENCE` | 265 |
| `FORMER_TICKER_REQUIRES_REVIEW` | 5 |
| `INVALID_STORED_ANCHOR` | 30 |
| `UNDATED_OR_CROSSING_ALIAS_BOUNDARY` | 3 |
| `CONTEXT_WINDOW_TOO_WIDE` | 2 |
| `IDENTITY_REVIEW_UNRESOLVED` | 1 |
| `MISSING_EXCHANGE_IDENTITY` | 5 |
| **Total** | **1,034** |

## A. The 475 mismatch cases

### What the implementation actually requires

**VERIFIED FACT:** `valid_bar` requires finite positive OHLC, finite nonnegative volume and `low <= min(open, close) <= max(open, close) <= high`. `same_basis` requires both bars valid, each OHLC field passing `math.isclose(rel_tol=1e-6, abs_tol=1e-6)`, and **exact volume equality**. The relative tolerance is **0.0001%**, not 0.01%; the absolute tolerance is 0.000001 price units. Python accepts a difference up to the larger of the relative and absolute allowances.

All 475 report entries retain stored anchors for September 21 and September 23 and Yahoo identity metadata. Before this reason can be assigned, the target Yahoo bar must have survived conversion, identity/first-trade checks and target OHLCV validation. However, the rejection expression also checks whether each neighboring date exists in the converted Yahoo dictionary. It short-circuits: a first failure need not evaluate the other neighbor. Conversion can omit bars with incomplete OHLC.

**UNRESOLVED:** The report does not retain rejected Yahoo neighboring OHLCV, neighbor-presence flags, per-field comparisons, rejected target OHLCV, raw versus adjusted values/actions, retrieval timestamps or the adjustment/library configuration for these records. Consequently the actual numbers of price-only, volume-only, combined, invalid-Yahoo-anchor and missing-Yahoo-anchor rejections are **unknown**, not zero. No historical revision, corporate action or volume-only cause can be attributed to an individual rejection solely from this reason code.

The eight retained Yahoo probes concern AAPL, NVDA, AMD and TSLA, none in either focus group. They provide **zero direct comparisons** for the 740 cases.

### Measured local Massive proxy — not the Yahoo rejection distribution

**VERIFIED FACT:** Retained Massive grouped responses have `status=OK`, `adjusted=true`. Same-symbol bars provide both anchors for 467/475 cases, totaling 941 pairs (467 previous, 474 following); all these proxy bars pass the OHLCV validity rule. Eight cases lack complete proxy anchors: AXINU, BLZRU, CSAN, DRDB, NPACU, OTGAU, PMTRU, TACOU. CSAN lacks both; the other seven lack September 21.

For this diagnostic only, Massive volumes are rounded to integers, following the retained standalone fallback draft's convention; 923/941 raw volumes are fractional. This is not a claim that rounding makes the volume semantics equivalent. Compare each stored anchor with Massive using the production `same_basis` thresholds:

| Proxy outcome across both anchors | Complete cases |
|---|---:|
| Volume only | 209 |
| OHLC and volume | 258 |
| OHLC only | 0 |
| Neither | 0 |
| Incomplete, excluded above | 8 |

Thus **209 is a measured cross-provider volume-only count**, and must not be reported as the actual Yahoo volume-only count. Previous-session pairs have 180 price failures and 465 volume failures; following pairs have 152 and 463, respectively. These pair counts overlap and are not case totals.

For the following tables, absolute difference is `abs(Massive - stored)` and relative difference is that amount divided by `abs(stored)`. Percentages multiply the latter by 100. Bins use the worst relative OHLC difference per session, or across both sessions for the complete-case column; volume is excluded from these bins.

| Maximum OHLC relative difference | Previous pairs (467) | Following pairs (474) | Complete cases (467) |
|---|---:|---:|---:|
| At most 0.01% | 359 | 381 | 316 |
| Above 0.01% to 0.1% | 89 | 64 | 112 |
| Above 0.1% to 0.5% | 10 | 27 | 29 |
| Above 0.5% | 9 | 2 | 10 |

Small differences need not pass the stricter production comparator, and magnitude alone does not establish safe adjustment or identity equivalence.

All fieldwise minimum absolute and relative differences are zero. The following gives their ranges via maxima and their typical magnitudes via medians. OHLC absolute differences use price units; volume uses shares after the stated rounding. Maximum absolute and maximum relative values can concern different securities.

| Session | Field | Median absolute | Maximum absolute | Median relative % | Maximum relative % |
|---|---|---:|---:|---:|---:|
| previous | open | 3.43323e-07 | 0.22208878 | 1.91607e-06 | 1.1840635 |
| previous | high | 6.86646e-07 | 0.22353115 | 2.66646e-06 | 1.1840697 |
| previous | low | 6.86646e-07 | 0.21889969 | 2.49094e-06 | 1.2166385 |
| previous | close | 3.8147e-07 | 0.21999931 | 2.29111e-06 | 1.1840693 |
| previous | volume | 38 | 9706 | 0.00826957 | 16.137097 |
| following | open | 3.8147e-07 | 1.2799951 | 2.16608e-06 | 0.38554217 |
| following | high | 4.57764e-07 | 0.13000305 | 2.26336e-06 | 0.61031776 |
| following | low | 4.19617e-07 | 0.060099716 | 2.29936e-06 | 1.3870975 |
| following | close | 3.43323e-07 | 0.0028999857 | 2.28821e-06 | 0.84375225 |
| following | volume | 135 | 1022860 | 0.0233805 | 1138.2067 |

Examples: A's previous/following volumes differ by +110/+327 shares while OHLC passes; AAP's following high differs by approximately −0.0050003 and volume by +56. TAOP's following volume is 35,800 stored versus 443,278 rounded Massive (+1,138.21%). These are proxy observations, not explanations proven against Yahoo.

### Adjustment and corporate actions

**VERIFIED FACT:** Testing `stored/Massive` across the four prices, with within-bar ratio spread and between-session mean difference each limited to 1e-5 relative, finds 235 complete cases with near-unit uniform ratios and **zero consistent non-unit uniform ratios across both sessions**. Previous-session-only uniform non-unit ratios occur for AGD (~0.9901072), AOD (~0.9895833) and ASGI (~0.9890000); their following ratios are near one. No stored split records were found for these 475 tickers during September 18–25.

**SUPPORTED INFERENCE:** The three session-specific ratios are compatible with an adjustment-vintage or cash-distribution difference, warranting targeted action evidence. They do not establish a split, dividend or Yahoo rejection cause. No common scaling correction is supported. Absence of a stored split record does not prove absence of corporate actions.

**VERIFIED FACT / LIMIT:** RawCandle's helper calls `stock.history(start, end)` without explicit adjustment arguments. The retained handover documents the installed Yahoo default as auto-adjusted, whereas Massive `adjusted=true` is split-adjusted. These bases cannot be assumed identical, particularly around distributions. Stored-row provenance/vintage and rejected Yahoo actions are unavailable here. Historical revisions, trade-coverage differences, inconsistent stored values and dividends remain alternative explanations; the proxy cannot distinguish them.

## B. The 265 missing-two-sided cases

**VERIFIED FACT:** Targeted queries for each named ticker's nearest stored USA row before and after September 22 reproduce:

| Structural or secondary finding | Cases | Interpretation |
|---|---:|---|
| Missing following stored row | 265 | Direct branch condition |
| Missing previous stored row | 0 | Includes zero cases missing both sides |
| Yahoo comparison-bar failure as this reason's cause | 0 | Branch exits before Yahoo acquisition |
| 14-day limit as this reason's cause | 0 | Limit checked only after both sides exist |
| Invalid last stored anchor | 17 | Additional overlapping blocker; not original branch cause |
| Metadata supports delisted historical endpoint | 126 | Qualified listing evidence, not proven exchange-effective delisting dates |
| Listing/feed endpoint unresolved | 139 | 8 active metadata + 131 without exact stocks metadata |

The frozen report retains neither side flags nor neighboring values for this group; the side attribution above uses current read-only histories and agrees with the original code path. All latest stored dates precede the target and range from **2018-02-22 to 2026-09-11**. Thus this is not an ordinary missing row enclosed by existing later history.

Exact stocks metadata is available for 134/265. Of these, 126 have `isdelisted=Y` and provider last-price dates before the target; eight have `isdelisted=N` but stale last-price dates in August. Some stored endpoints extend beyond provider last-price dates, so that field is not an authoritative delisting timestamp. The eight active-metadata cases are APGE, ATAI, CRNX, HLX, IPCX, JFB, LPSN and TWO. A stale feed, delisting/transition not reflected in metadata, suspension or incomplete coverage cannot be distinguished from these fields alone.

**VERIFIED FACT:** No exact symbol from this group appears in any of the three retained Massive sessions (September 21–23). Therefore **zero of the 265 can be directly filled from those local target-day bars**. This does not prove absence of issuer trading under a successor symbol or another venue. All 265 have earlier stored history; none of the 134 metadata records has a first-price date after the target. No simple first-trading-day explanation is demonstrated. IPO/successor boundaries, mergers and suspension status remain unresolved where dated evidence is missing.

The 17 invalid preceding anchors are ACLX, CCCX, CGCTU, CTLP, CVGW, EKSO, EM, EWCZ, FCT, FFIC, GDEN, GTI, LNW, MCW, PLYM, STKL and TERN. All violate the OHLC range rule; CTLP, EWCZ, FCT, GTI and LNW also have nonpositive OHLC. None fails volume validity. Supplying a following bar alone would not make these cases ready for insertion. These 17 overlap the listing buckets above and must not be added to 265.

The complete recovery report separately contains two `CONTEXT_WINDOW_TOO_WIDE` and 30 `INVALID_STORED_ANCHOR` cases, outside this 265-case group. Changing the 14-day cap would resolve none of this group's immediate failures. Requiring a future stored anchor does constrain recovery at historical endpoints, but one-sided agreement alone cannot establish a safe historical price basis or target-day listing.

## Fundamentals overlap and historical identity

The currently active generation is `refresh_20261013T042603Z_refresh_fundamentals_3d9f10e1f3f2_production_25d220d5`, located under `data/fundamentals_generations/`; canonical `fundamentals_v4.db`, corresponding `fundamentals_provider.db`, selected by `data/fundamentals_active_generation.json`.

Matching used `security.current_ticker` and `ticker_alias` to resolve `security_id`, and cross-checked canonical SHARADAR `provider_security_identity` against exact `sharadar_ticker_metadata` stocks `permaticker`. All matches are unique current routes, with matching stable provider IDs; there are no alias-only or multiple-security matches in these groups.

For this diagnostic, **dated, locally unambiguous** requires an explicit security start no later than the target, no conflicting end/retirement/inactive/alias/review evidence and corroborating provider identity. This means support from inspected local records, not exhaustive historical listing certification. An undated start is an evidence gap, not proof of a wrong identity.

| Group | Matching distinct security IDs | Dated, locally unambiguous | With historical identity concerns | Outside canonical |
|---|---:|---:|---:|---:|
| 475 mismatch | 223 | 6 | 217 | 252 |
| 265 no two-sided | 10 | 0 | 10 | 255 |

The six dated matches are GFS, INTU, P, SHOE, UPST and WDH. All 217 other mismatch matches lack a dated `security.valid_from`; no additional identity conflict was found by the inspected checks. Their eligibility is not disproven by that missing date.

The ten missing-two-sided canonical routes are APGE (172), AVB (242), CRNX (570), HLX (1042), LBRDA (1274), LBRDK (1275), LEG (1285), LPSN (1330), RMAX (1906) and TALK (2134), with security IDs in parentheses. All lack dated starts; AVB, LBRDA, LBRDK, LEG, RMAX and TALK additionally have inactive canonical status and delisted-before-target provider history evidence. APGE, CRNX, HLX and LPSN have active provider metadata but unresolved endpoints.

These are current-generation membership counts, not a historical point-in-time universe. Availability, current membership and dated research eligibility remain separate. Current Fundamentals selection retains survivorship/selection limitations. This comparison does not restrict the general administration recovery tool to Fundamentals securities.

## Minimal recommendations — no changes implemented

### A. Existing local evidence; no provider requests needed

1. Separate the reporting of missing stored left/right evidence, OHLC disagreement, volume disagreement and missing/invalid converted provider bars. Design persistence of compared values, presence flags, per-field deltas, source/retrieval identity, library/options and adjustment evidence for future runs already making requests. This is a small observability change, not a reason to run acquisition again. Existing reports cannot retroactively supply absent Yahoo values.
2. Use local identity/metadata to distinguish the 126 delisted-endpoint-supported cases from the 139 unresolved cases, retaining evidence confidence. Stable IDs, dated transitions and source freshness must accompany any future eligibility decision; do not convert `lastpricedate` alone into a definitive delisting date. Keep undated identity separate from demonstrated conflict.
3. Flag the 17 invalid preceding anchors independently. No insertion or silent correction is justified by their current histories. Retained Massive data supports triage of the 475, but does not by itself establish a consistent Yahoo/stored basis or authorize inserts. None of the 265 has a retained exact-symbol Massive target bar.

Exact volume equality demonstrably gates many proxy comparisons and may conflate traded-volume conventions with price-adjustment consistency. It merits separating diagnostic flags, but **evidence does not yet justify a looser acceptance rule, ignoring volume, changing tolerances or accepting one-sided anchors**.

### B. Additional targeted evidence — separate authorization required

Before changing acceptance logic, investigate a bounded **12-symbol sample**, not all 475: A and ABEV (proxy volume-only); AAP (small high difference plus volume); AXINU (missing Massive previous anchor); AGD, AOD and ASGI (session-specific ratios); TAOP (extreme volume); APGE, CRNX, HLX and LPSN (canonical active-metadata endpoints).

For mismatch cases, retain raw and converted Yahoo bars for both anchors and target, explicit adjustment/actions options, Adj Close/actions, identity, timestamp and library version. For the four unresolved endpoints, first establish target-day listing/trading and dated identity; a query returning no bar is not proof of ineligibility. Obtain only the narrow necessary dates, under existing bounded pacing/throttle protection, without disrupting daily collection. New responses are new observations and cannot exactly reconstruct an earlier Yahoo revision. Compare against retained local evidence and explain corporate-action/volume conventions before proposing any rule change. No such requests were made here.

### C. Remain HELD

Keep cases held where basis, target-day trading, identity intervals, successor mapping, invalid anchors or unexplained provider disagreement remains unresolved. Do not infer successor continuity from related ticker strings, copy predecessor bars, scale prices empirically, or treat old history endpoints as recoverable missing trading days. In particular, no present evidence supports blanket release of the 209 proxy volume-only cases or the 139 unresolved endpoints.

**Decision:** Further targeted evidence is required before changing acceptance code. Minimal diagnostic/reporting improvements can be specified from existing findings without new provider calls; implementing them is a separate task. This investigation does not recommend loosening the 14-day limit or two-sided requirement.

## Completion and safety

Report-only change. Production database changes **0**; source-code changes **0**; provider requests **0**; recovery jobs/restarts **0**; database copies/backups **0**. No full test suite was run. Existing evidence and unrelated working-tree changes were preserved. Only this report is to be committed; **no push**.
