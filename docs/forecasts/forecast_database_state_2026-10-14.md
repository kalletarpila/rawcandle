# Forecast database state — 2026-10-14

Decision: **FORECAST_HISTORY_RESEARCH_NEEDS_FIX**. Collection is healthy and the exact publication-overlap cohort has grown from 7 to 27 events. However, the unchanged research engine accepts two PRE/POST pairs with conflicting provider target dates (MU and NKE), and its transition timing follows delayed fiscal-link changes rather than the first provider horizon change. Correct this bounded analysis defect before interpreting revision-versus-return results. No production data or source code was changed.

## Scope, provenance and contract review

Analysis began before today’s 14:00 Europe/Helsinki collection; measurement timestamp: `2026-10-14T10:29:01.618928+00:00`. All 21 completed runs and all persisted history were examined through October 13. The history covers 17 observed calendar dates, 12 observed US equity trading dates (SPY OHLC rows), and approximately 15.8 elapsed days. October 14 is not a missed scheduler day.

Canonical input is the pinned active generation `refresh_20261014T095401Z_refresh_fundamentals_43db1c8371f6_production_6917d617`. The legacy `data/fundamentals_v4.db` was not used. The forecast operator resolves that logical path through `resolve_requested_role_path`; a legacy-looking scheduler configuration therefore does not itself establish stale input. The active pointer and schedulers were only read.

Relevant contracts inspected: `rawcandle/forecasts/{schema,contracts,linking,operator}.py`, `rawcandle/research/forecast_revision_research.py`, the publication research exporter/service and event-window implementation, and the persistence, mixed-row, fiscal-linker, and October 4 validated-cohort documents. No general repository scan or external provider requests were performed.

Definitions: an observation is a successful fetch dereferencing its snapshot; a snapshot is distinct whole-family semantic content, which can be reused later. A metric revision is an adjacent numeric value change for the same reconstructed fiscal target. Daily depth counts distinct UTC collection dates, not intraday fetches. EPS/revenue series are kept separate; annual targets are explicitly separate from quarterly targets. Missing numeric values are not zero. Canonical FY/FQ labels are accepted only from fetch-specific AS_KNOWN reconstruction, never a current-link join.

## 1. Database health and read-only verification

| Input | Bytes | SHA-256 before = after | quick_check | foreign_key_check |
| --- | --- | --- | --- | --- |
| data/forecasts.db | 1324658688 | 9dc1548bd9a7d07972c28012fd41da1e53b5187da8a5d7e4fc11e0913e25423b | ok | 0 violations |
| data/fundamentals_generations/refresh_20261014T095401Z_refresh_fundamentals_43db1c8371f6_production_6917d617/fundamentals_v4.db | 749371392 | aec33d93fdcb060c8986a4b5fa6fbb8d70bf8aa94cc3da909c993f66239c64fa | ok | 0 violations |

`forecasts.db` exists; size is 1.234 GiB. No WAL sidecar was present at initial inspection. Connections used SQLite `mode=ro` plus `PRAGMA query_only=ON`. Both required whole-file hashes remained unchanged; the existing engine separately verified unchanged forecasts, canonical and OHLC hashes.

First run: `2026-09-27T16:27:26.310737Z`. Latest run, also latest SUCCESS: `2026-10-13T11:00:36.736899Z`, completed `2026-10-13T12:01:56.294937Z`. Run statuses: {'SUCCESS': 15, 'FAILED': 1, 'PARTIAL': 5}. RUNNING/stale runs: 0. All non-success runs are terminal historical records.

## 2. Collection volume

| Family | Fetches | Snapshots | Snapshot tickers |
| --- | --- | --- | --- |
| EARNINGS_HISTORY_REFERENCE | 44144 | 2498 | 2379 |
| FISCAL_ESTIMATE | 44144 | 9254 | 2302 |
| PRICE_TARGET | 44144 | 28248 | 2441 |

Totals: 21 runs; 132,432 fetches; 40,224 raw evidence rows; 40,000 semantic snapshots. Normalized rows: 849,620 fiscal fields, 141,240 price-target fields, 9,833 earnings-history reference rows. Fiscal normalized occurrences: 36,940. Since October 4: +9 runs, +65,907 fetches, +18,216 snapshots, +4,296 fiscal snapshots, +21,969 fiscal fetches.

All 2,441 fetched tickers have at least one family snapshot; there are zero repeatedly fetched symbols with no semantic snapshots across all families. Fiscal estimate averages are usable for 2,302 tickers; 139 tickers have no fiscal snapshot. Price-only success is not fiscal coverage. Fetches/ticker across all families: minimum 54, median 54, mean 54.253, maximum 63.

Current directly derived bounded universe: 2,441 ACTIVE_SINGLE_SECURITY members, matching every full run and universe version `3b8121b74c852f08575fa1e2b70004e6`. The active member table also contains 11 ACTIVE_MULTI_SECURITY and 16 HISTORICAL_RETAINED_NO_ACTIVE_SECURITY records; these are not extra selected forecast symbols.

## 3. Whole collection run history

UTC start times below. Success means SUCCESS_CHANGED + SUCCESS_UNCHANGED; no-data is a valid provider observation but supplies no estimate. “Bad” counts transient/schema failures. Inserted counts use snapshot.first_fetch_id, not SUCCESS_CHANGED (which can reuse earlier content). All rows are explicit OPERATOR invocations, including scheduled invocations.

| Start UTC | Status | Selected | Attempts | Success | No data | Bad | Inserted | Unchanged | Minutes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-09-27T16:27:26 | SUCCESS | 6 | 18 | 18 | 0 | 0 | 18 | 0 | 0.14 |
| 2026-09-27T18:52:04 | FAILED | 100 | 300 | 0 | 0 | 300 | 0 | 0 | 17.52 |
| 2026-09-27T19:14:19 | PARTIAL | 100 | 300 | 291 | 3 | 6 | 285 | 6 | 2.5 |
| 2026-09-27T19:39:34 | PARTIAL | 2441 | 7323 | 7109 | 203 | 11 | 6807 | 302 | 61.1 |
| 2026-09-28T04:30:12 | PARTIAL | 2441 | 7323 | 7109 | 203 | 11 | 22 | 7087 | 61.15 |
| 2026-09-28T11:00:12 | PARTIAL | 2441 | 7323 | 7109 | 203 | 11 | 221 | 6888 | 61.15 |
| 2026-09-29T11:00:16 | SUCCESS | 2441 | 7323 | 7120 | 203 | 0 | 2700 | 4420 | 61.18 |
| 2026-09-30T11:00:17 | SUCCESS | 2441 | 7323 | 7121 | 202 | 0 | 2703 | 4399 | 61.31 |
| 2026-10-01T11:01:03 | SUCCESS | 2441 | 7323 | 7120 | 203 | 0 | 2778 | 4299 | 61.19 |
| 2026-10-02T11:01:04 | PARTIAL | 2441 | 7323 | 7118 | 204 | 1 | 2612 | 4459 | 61.6 |
| 2026-10-03T11:00:23 | SUCCESS | 2441 | 7323 | 7119 | 204 | 0 | 2768 | 4291 | 61.41 |
| 2026-10-04T11:00:24 | SUCCESS | 2441 | 7323 | 7117 | 206 | 0 | 870 | 6247 | 61.13 |
| 2026-10-05T11:00:25 | SUCCESS | 2441 | 7323 | 7117 | 206 | 0 | 985 | 6132 | 61.19 |
| 2026-10-06T11:00:27 | SUCCESS | 2441 | 7323 | 7117 | 206 | 0 | 2840 | 4209 | 61.3 |
| 2026-10-07T11:00:29 | SUCCESS | 2441 | 7323 | 7116 | 207 | 0 | 2823 | 4206 | 61.13 |
| 2026-10-08T11:00:30 | SUCCESS | 2441 | 7323 | 7117 | 206 | 0 | 2861 | 4170 | 61.15 |
| 2026-10-09T11:00:42 | SUCCESS | 2441 | 7323 | 7117 | 206 | 0 | 2723 | 4306 | 61.17 |
| 2026-10-10T11:00:33 | SUCCESS | 2441 | 7323 | 7117 | 206 | 0 | 2695 | 4304 | 61.3 |
| 2026-10-11T11:00:34 | SUCCESS | 2441 | 7323 | 7117 | 206 | 0 | 5 | 7112 | 61.74 |
| 2026-10-12T11:00:37 | SUCCESS | 2441 | 7323 | 7117 | 206 | 0 | 22 | 7095 | 61.19 |
| 2026-10-13T11:00:36 | SUCCESS | 2441 | 7323 | 7117 | 206 | 0 | 3262 | 3743 | 61.33 |

No missing completed daily collection dates: full runs exist September 27–October 13 inclusive. Every full run attempted 7,323 family fetches (2,441 × 3). The six-symbol pilot and two 100-symbol trials on September 27 explain low-volume runs. No abnormal truncation of a full run was found. October 11/12 had only 5/22 changed observations but full attempt volumes: low novelty is not low collection volume.

Errors: the September 27 failed trial recorded 300 TRANSIENT_FAILURE outcomes (100 per family), all DNS resolution errors (`DNSError`, guce.yahoo.com); September 27/28 retained 39 fiscal schema failures from the old parser. The only later failure is one earnings-history `OPERATOR_EXCEPTION` / SQLite `database is locked` on October 2. No rate-limited or unavailable-symbol outcomes are persisted. Recent daily runs September 29–October 13 are SUCCESS except October 2 PARTIAL.

## 4. FISCAL_ESTIMATE coverage and completeness

44,144 fiscal fetches: 9,262 SUCCESS_CHANGED, 32,193 SUCCESS_UNCHANGED, 2,550 VALID_NO_DATA, 100 TRANSIENT_FAILURE, 39 MALFORMED_OR_SCHEMA_MISMATCH. There are 41,455 successful persisted fetch observations, 9,254 fiscal snapshots and 36,940 normalized occurrence observations; these are different denominators.

| Provider horizon | Normalized occurrences | Field rows | Distinct snapshots containing horizon |
| --- | --- | --- | --- |
| +1q | 9225 | 212175 | 9225 |
| +1y | 9235 | 212405 | 9235 |
| 0q | 9228 | 212244 | 9228 |
| 0y | 9252 | 212796 | 9252 |

| Metric | Statistic | Persisted fields | Numeric fields |
| --- | --- | --- | --- |
| EARNINGS_ESTIMATE_GROWTH | VALUE | 36940 | 36363 |
| EPS_ANALYST_COUNT | VALUE | 36940 | 36866 |
| EPS_ESTIMATE | AVG | 36940 | 36866 |
| EPS_ESTIMATE | HIGH | 36940 | 36866 |
| EPS_ESTIMATE | LOW | 36940 | 36866 |
| EPS_ESTIMATE | YEAR_AGO | 36940 | 36363 |
| EPS_REVISION_COUNT | DOWN_30D | 36940 | 36866 |
| EPS_REVISION_COUNT | DOWN_7D | 36940 | 36866 |
| EPS_REVISION_COUNT | DOWN_90D | 36940 | 0 |
| EPS_REVISION_COUNT | UP_30D | 36940 | 36866 |
| EPS_REVISION_COUNT | UP_7D | 36940 | 36866 |
| EPS_TREND | 30D_AGO | 36940 | 36866 |
| EPS_TREND | 60D_AGO | 36940 | 36866 |
| EPS_TREND | 7D_AGO | 36940 | 36866 |
| EPS_TREND | 90D_AGO | 36940 | 36866 |
| EPS_TREND | CURRENT | 36940 | 36866 |
| REVENUE_ANALYST_COUNT | VALUE | 36940 | 36940 |
| REVENUE_ESTIMATE | AVG | 36940 | 36940 |
| REVENUE_ESTIMATE | HIGH | 36940 | 36940 |
| REVENUE_ESTIMATE | LOW | 36940 | 36940 |
| REVENUE_ESTIMATE | YEAR_AGO | 36940 | 36608 |
| REVENUE_ESTIMATE_GROWTH | VALUE | 36940 | 36606 |
| YAHOO_ROW_GROWTH | VALUE | 36940 | 35360 |

Occurrence completeness: EPS AVG + Revenue AVG both numeric 36,866; EPS-only 0; Revenue-only 74; neither 0. EPS analyst count missing in 74 occurrences; revenue analyst count missing in 0. Missing EPS is retained as a field state. Revenue analyst count is numeric zero in 102 normalized fields; zero coverage is not proof of a dependable consensus.

9,209 fiscal snapshots use V1, 45 use V2 mixed-empty-targets. Those 45 preserve 76 exact empty placeholder rows alongside usable rows; placeholders have no normalized fiscal estimates or fiscal links. There are no all-empty semantic fiscal snapshots. The 2,550 valid no-data fiscal fetches contain 10,200 empty placeholder row observations; six historical malformed all-empty fetches add 24, and 33 historical malformed mixed payloads add 84 (10,308 total empty-row observations in snapshotless raw fetches). These fetch-expanded counts must not be added to distinct snapshot-row counts.

Persistent fiscal no-snapshot tickers (139; each repeatedly attempted):

ABVC, AEI, AIFF, AIMD, AIV, AMST, AQB, AQMS, ARAY, ARTL, ATER, ATPC, AUID, AUUD, AVD, BCTX, BGLC, BGMS, BIAF, BJDX, BMRA, BOC, BTBD, BZFD, CDT, CELU, CISO, CLRO, COKE, CPIX, CYCN, DBGI, DJT, DMLP, DOUG, ELAB, ELME, EPSN, EVC, FCUV, FF, FIEE, FNGR, FOXX, FPH, FRGT, FTFT, GCTK, GDC, GEOS, GITS, GNLN, HOLO, HOUR, HWH, IEP, ILLR, IMKTA, INDP, INHD, INM, IPDN, ISPC, IVDA, JAGX, JOE, KALA, KITT, KODK, KOSS, LASE, LITS, LNAI, LRHC, LTBR, LUCY, LVWR, MBIO, MDIA, MGRX, MLGO, MVIS, MX, MYSE, MYSZ, NEGG, NEON, NIXX, NLOP, NMAD, NNDM, NXDT, OCC, OMEX, ONCO, OPTX, ORBS, PBYI, PHUN, POLA, PPCB, QCLS, REBN, RENT, REX, RIME, RNAZ, SCLX, SCNI, SEB, SEGG, SGLY, SHPH, SMXT, SNOA, SOBR, SPOK, SPRU, SQFT, SRG, SSTK, SUNE, TAOX, TGL, TONX, TR, TRON, UP, VAI, VATE, VIVS, VS, WHLR, WMK, WRAP, XPON, XXII, YYAI, ZEO.

## 5. Fiscal-link identity quality

| Knowledge mode | LINKED | UNRESOLVED | AMBIGUOUS |
| --- | --- | --- | --- |
| AS_KNOWN | 165021 | 144 | 0 |
| CURRENT_RECONCILED | 165021 | 0 | 0 |

There are 330,186 append-only link records in total. Authoritative AS_KNOWN: 165,021 LINKED and 144 UNRESOLVED. The 849,620 reserved estimate.link_status columns all remain UNLINKED by contract and are not failed authoritative links. No authoritative UNLINKED status exists. BATRK and BELFB account for all unresolved rows (72 each, INSUFFICIENT_FISCAL_CONTEXT); 36 successful fiscal fetches cannot be reconstructed.

Research-linkable snapshots with at least one numeric EPS/revenue average: 9,251/9,254 (99.968%). This means structurally reconstructable under the current contract, not independently validated target continuity. Three usable snapshots lack a research identity. There are 4,615 distinct expected quarterly identities and 4,600 annual identities. Expected quarterly labels range FY2025/Q4–FY2028/Q2; annual labels FY2025–FY2029. Distinct attached canonical_quarter_id values: 0.

All 82,398 linked AS_KNOWN quarterly rows have nullable canonical IDs and valid expected-successor identity under the present linker contract; the other 82,623 linked AS_KNOWN rows are annual, where a quarter ID is not required. CURRENT_RECONCILED repeats those counts with null IDs. None should be “repaired” by inventing future actual quarters. No persisted skip/gap/TARGET_CONFLICT/MULTIPLE_VALID_TARGETS rejection was found. 1,379 links carry END_DATE_OUTSIDE_TOLERANCE but remain LINKED by current design; 163,642 carry END_DATE_SUPPORT.

Material identity caveat: 149 of 9,215 expected targets carry multiple provider end dates (137 with two, 12 with three). A moving horizon can retain a stale or contradictory provider date as the canonical fiscal knowledge frontier advances. Therefore LINKED alone is not sufficient evidence that all values in a target series are comparable.

## 6. Revision-history depth

The following is the actual distribution reconstructed by the existing fetch-specific engine, including annual and quarterly targets. It is **provisional where provider-date continuity is contradictory**; the 149 mixed-date targets need bounded QA. Identical successful fetches count toward daily observation depth and do not count as metric revisions. Whole-family snapshots can change because of another horizon, EPS trend, revision counters, or row metadata; they do not automatically represent AVG changes for this target.

| Measure | EPS | Revenue |
| --- | --- | --- |
| Targets | 9170 | 9215 |
| Targets with AVG revisions | 4541 | 4669 |
| Targets with analyst changes | 2388 | 2446 |
| Targets with high/low endpoint changes | 2708 | 2733 |
| Median AVG changes | 0 | 1 |
| Median metric semantic changes | 0 | 1 |

| Distinct collection dates threshold | EPS targets | Revenue targets |
| --- | --- | --- |
| Exactly 1 | 0 | 0 |
| 2+ | 9170 | 9215 |
| 3+ | 9168 | 9200 |
| 5+ | 9157 | 9185 |
| 10+ | 9117 | 9145 |
| 14+ | 9071 | 9104 |

| Metric | Quarterly / annual targets | Days min / median / max | Elapsed span days min / median / max | Family snapshots min / median / max | Metric states min / median / max |
| --- | --- | --- | --- | --- | --- |
| EPS | 4596 / 4574 | 2 / 17.0 / 17 | 0.369 / 15.640 / 15.800 | 1 / 3.0 / 15 | 1 / 1.0 / 12 |
| Revenue | 4615 / 4600 | 2 / 17 / 17 | 0.369 / 15.640 / 15.800 | 1 / 3 / 15 | 1 / 2 / 14 |

| Distinct family snapshots per target | EPS targets | Revenue targets |
| --- | --- | --- |
| 1 | 2238 | 2268 |
| 2 | 1501 | 1516 |
| 3 | 1079 | 1075 |
| 4 | 1072 | 1075 |
| 5 | 750 | 750 |
| 6 | 677 | 675 |
| 7 | 522 | 524 |
| 8 | 462 | 462 |
| 9 | 333 | 333 |
| 10 | 229 | 229 |
| 11 | 149 | 149 |
| 12 | 76 | 77 |
| 13 | 47 | 47 |
| 14 | 23 | 23 |
| 15 | 12 | 12 |

| Metric | AVG changed ≥1 | Analyst count changed ≥1 | High/low changed ≥1 |
| --- | --- | --- | --- |
| EPS | 49.52% | 26.04% | 29.53% |
| Revenue | 50.67% | 26.54% | 29.66% |

Conservative single-provider-date subset (exclude all 149 mixed-date target histories): EPS 9,021 targets, 4,410 with numeric AVG revisions (48.89%); Revenue 9,066 targets, 4,540 with numeric AVG revisions (50.08%). This is a continuity screen, not independent fiscal validation.

| Single-provider-date targets: daily threshold | EPS | Revenue |
| --- | --- | --- |
| Exactly 1 | 0 | 0 |
| 2+ | 9021 | 9066 |
| 3+ | 9019 | 9051 |
| 5+ | 9010 | 9038 |
| 10+ | 8983 | 9010 |
| 14+ | 8956 | 8988 |

These proportions use all usable metric targets as denominator; absent analyst/range values do not fabricate revisions. Metric semantic signatures are (AVG, LOW, HIGH, analyst count). Missing values are skipped for numeric comparisons; no interpolation or claim about provider change time is made. EPS has 4,606 targets with one distinct metric signature, Revenue 4,478. Snapshot deduplication is not equivalent to target-level stability.

## 7. Illustrative genuine numeric revisions

Sample limited to targets with a single provider end date, at least two numeric AVG changes, and at least three EPS analysts at baseline. These are observed estimate changes, not trading signals or assertions about economic cause. Percent change follows the existing guard: suppress negative/near-zero baselines and sign crossings. Near-zero positive EPS can still make rankings unstable; absolute changes are shown. No new significance threshold is introduced.

| Ticker / fiscal target | Provider end | EPS first → latest | EPS Δ / % | Revenue first → latest | Revenue % | EPS analysts first → latest | EPS AVG / semantic changes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ALK 107/FY2026/Q4 | 2026-12-31 | 0.01213 → -1.11614 | -1.12827 / — | 4,127,406,780 → 4,104,328,080 | -0.55916 | 15 → 15 | 10 / 10 |
| CBRL 412/FY2027/Q1 | 2026-10-31 | 0.00877 → -0.11251 | -0.12128 / — | 818,366,670 → 814,880,240 | -0.42602 | 5 → 7 | 4 / 4 |
| SEDG 1973/FY2026/Q4 | 2026-12-31 | 0.00247 → -0.0254 | -0.02787 / — | 324,702,960 → 319,817,110 | -1.50471 | 20 → 19 | 6 / 6 |
| WY 2408/FY2026/Q4 | 2026-12-31 | 0.00724 → -0.01885 | -0.02609 / — | 1,707,008,560 → 1,698,377,510 | -0.50562 | 10 → 11 | 6 / 6 |
| ZYME 2458/FY2026/Q4 | 2026-12-31 | 0.05254 → -0.05325 | -0.10579 / — | 89,768,240 → 63,955,130 | -28.75528 | 7 → 7 | 5 / 5 |
| AAL 3/FY2026/Q4 | 2026-12-31 | 0.33083 → -0.31474 | -0.64557 / — | 16,331,160,280 → 16,515,498,319 | 1.12875 | 19 → 18 | 11 / 11 |
| MP 1456/FY2026/Q3 | 2026-09-30 | 0.00524 → -0.00172 | -0.00696 / — | 120,035,160 → 118,871,820 | -0.96917 | 15 → 15 | 2 / 2 |
| CVI 609/FY2026/YEAR | 2026-12-31 | 1.22454 → 2.55941 | 1.33487 / 109.00991 | 8,928,131,740 → 9,105,767,900 | 1.98962 | 5 → 6 | 3 / 3 |

| Ticker | First observation UTC | Latest EPS change UTC | Latest observation UTC |
| --- | --- | --- | --- |
| ALK | 2026-09-27T19:42:14.087725Z | 2026-10-10T11:03:14.670273Z | 2026-10-13T11:03:17.898147Z |
| CBRL | 2026-09-27T19:49:44.585674Z | 2026-10-13T11:10:50.597896Z | 2026-10-13T11:10:50.597896Z |
| SEDG | 2026-09-27T20:28:21.775835Z | 2026-10-13T11:49:37.933507Z | 2026-10-13T11:49:37.933507Z |
| WY | 2026-09-27T20:39:09.735065Z | 2026-10-13T12:00:25.178388Z | 2026-10-13T12:00:25.178388Z |
| ZYME | 2026-09-27T20:40:23.319482Z | 2026-10-08T12:01:21.952977Z | 2026-10-13T12:01:38.809501Z |
| AAL | 2026-09-27T19:14:22.565571Z | 2026-10-13T11:00:39.826121Z | 2026-10-13T11:00:39.826121Z |
| MP | 2026-09-27T20:15:32.760548Z | 2026-10-08T11:36:31.903652Z | 2026-10-13T11:36:39.276460Z |
| CVI | 2026-09-27T19:54:37.387627Z | 2026-10-10T11:15:38.192159Z | 2026-10-13T11:15:43.759646Z |

HELE, KBH, MU annual and LEN were deliberately excluded from this sample because their reconstructed target histories include multiple provider dates. Their large apparent changes should not be described as validated same-period revisions.

## 8. Moving-horizon transitions: provider evidence versus linker changes

Two measurements must be separated. The AS_KNOWN target assigned to 0q changes 39 times (39 tickers), all to the immediate expected fiscal successor and all with a preceding +1q link to that successor. But 37/39 have **unchanged provider 0q endDate across that assigned-identity switch**. Their intervals time a linker-context change, not the first provider rollover. An unchanged 0q snapshot can be relabeled later; that is allowed by the persistence contract, but is not a new Yahoo transition.

Direct provider evidence shows 86 changes of numeric-usable 0q endDate across 63 tickers: 74 forward changes and 12 backward changes. Of the 74 forward changes, 37 have an immediately preceding +1q row with the identical new provider date; 37 lack that immediately preceding provider-date match. These are observed date-roll episodes, not 74 unique publication events. Provider dates are supporting evidence, not newly inferred canonical identities.

For the 37 forward, same-provider-date episodes, observation interval hours: min 23.989, median 24.001, max 24.013. The actual switch lies in (last old observation, first new observation]; acquisition time is not provider update time.

Within the exact publication cohort, 25/27 have a forward provider-date transition after publication, with a preceding +1q matching the new date and old provider date within the existing 45-day fiscal tolerance of the reported period. This is a diagnostic continuity check, not a substitute fiscal linker. Publication → first provider-new-0q hours: min 10.355, median 19.531, max 35.560. Observed ticker OHLC trading-day lag: min 0.000, median 1.000, max 2.000. Trading-day counts use observed OHLC dates, not a weekday proxy.

| Ticker | Publication UTC | Last old provider 0q UTC | First new provider 0q UTC | Old → new endDate | Pre +1q EPS / Revenue | First new 0q EPS / Revenue | Hours / trading days |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AIR | 2026-09-28T20:58:22Z | 2026-09-28T11:02:21.626036Z | 2026-09-29T11:02:26.051928Z | 2026-08-31 → 2026-11-30 | 1.3625 / 892,080,250 | 1.3625 / 892,080,250 | 14.07 / 1 |
| ANGO | 2026-10-08T15:17:49Z | 2026-10-08T11:04:27.604727Z | 2026-10-09T11:04:38.715344Z | 2026-08-31 → 2026-11-30 | -0.08333 / 84,075,000 | -0.095 / 84,017,500 | 19.78 / 1 |
| APLD | 2026-10-08T00:43:31Z | 2026-10-07T11:04:49.284691Z | 2026-10-08T11:04:50.133223Z | 2026-08-31 → 2026-11-30 | -0.34784 / 170,895,830 | -0.29478 / 118,750,000 | 10.36 / 1 |
| APOG | 2026-10-06T17:44:57Z | 2026-10-06T11:04:49.793159Z | 2026-10-07T11:04:52.290530Z | 2026-08-31 → 2026-11-30 | 0.8 / 365,774,000 | 0.8 / 365,774,000 | 17.33 / 1 |
| BYRN | 2026-10-08T16:10:10Z | 2026-10-08T11:10:02.614142Z | 2026-10-09T11:10:13.722551Z | 2026-08-31 → 2026-11-30 | -0.13 / 26,475,330 | -0.13 / 20,822,000 | 19.00 / 1 |
| CAG | 2026-09-30T11:32:13Z | 2026-09-30T11:10:01.514500Z | 2026-10-01T11:10:46.647095Z | 2026-08-31 → 2026-11-30 | 0.40418 / 2,945,630,120 | 0.36361 / 2,922,740,350 | 23.64 / 1 |
| CALM | 2026-09-30T10:07:27Z | 2026-09-30T11:10:07.506073Z | 2026-10-01T11:10:52.669038Z | 2026-08-31 → 2026-11-30 | -0.385 / 618,536,500 | -0.7 / 621,348,670 | 25.06 / 1 |
| CCL | 2026-09-29T13:16:12Z | 2026-09-29T11:10:40.027759Z | 2026-09-30T11:10:40.576926Z | 2026-08-31 → 2026-11-30 | 0.24453 / 6,426,522,240 | 0.19955 / 6,424,123,110 | 21.91 / 1 |
| CNXC | 2026-09-30T00:10:45Z | 2026-09-29T11:13:04.312393Z | 2026-09-30T11:13:04.875671Z | 2026-08-31 → 2026-11-30 | 3.05 / 2,518,133,150 | 3.05 / 2,518,133,150 | 11.04 / 1 |
| DAL | 2026-10-09T14:30:47Z | 2026-10-09T11:16:27.609263Z | 2026-10-10T11:16:17.242808Z | 2026-09-30 → 2026-12-31 | 1.42034 / 18,656,501,290 | 1.41368 / 18,656,501,290 | 20.76 / 0 |
| HOVR | 2026-10-09T15:24:51Z | 2026-10-09T11:26:42.830073Z | 2026-10-10T11:26:31.586106Z | 2026-08-31 → 2026-11-30 | -0.165 / 0 | -0.165 / 0 | 20.03 / 0 |
| IDT | 2026-09-28T20:31:47Z | 2026-09-28T11:27:26.107634Z | 2026-09-29T11:27:32.510459Z | 2026-07-31 → 2026-10-31 | 0.98 / 317,000,000 | 0.98 / 317,000,000 | 14.93 / 1 |
| KMX | 2026-09-29T11:00:30Z | 2026-09-29T11:30:43.510237Z | 2026-09-30T11:30:44.392683Z | 2026-08-31 → 2026-11-30 | 0.44004 / 6,129,464,140 | 0.31 / 6,138,700,000 | 24.50 / 1 |
| LEVI | 2026-10-08T00:12:53Z | 2026-10-07T11:32:17.086876Z | 2026-10-08T11:32:19.563045Z | 2026-08-31 → 2026-11-30 | 0.47883 / 1,840,022,240 | 0.384 / 1,825,155,860 | 11.32 / 1 |
| LW | 2026-10-06T16:02:01Z | 2026-10-06T11:33:58.783191Z | 2026-10-07T11:33:51.713275Z | 2026-08-31 → 2026-11-30 | 0.76571 / 1,617,780,620 | 0.85897 / 1,640,899,010 | 19.53 / 1 |
| MKC | 2026-10-01T11:31:11Z | 2026-10-01T11:36:27.076382Z | 2026-10-02T11:36:26.803159Z | 2026-08-31 → 2026-11-30 | 0.88169 / 2,120,304,810 | 0.83969 / 2,118,707,880 | 24.09 / 1 |
| MTN | 2026-09-28T20:06:47Z | 2026-09-28T11:36:53.895624Z | 2026-09-29T11:37:00.858233Z | 2026-07-31 → 2026-10-31 | -5.40543 / 271,289,400 | -5.40543 / 271,289,400 | 15.50 / 1 |
| MU | 2026-10-01T00:02:22Z | 2026-09-30T11:37:15.193470Z | 2026-10-01T11:38:01.712363Z | 2026-08-31 → 2026-11-30 | 35.92457 / 57,933,826,550 | 38.02027 / 61,315,076,040 | 11.59 / 1 |
| NEOG | 2026-10-07T00:05:19Z | 2026-10-07T11:38:16.190819Z | 2026-10-08T11:38:18.552026Z | 2026-08-31 → 2026-11-30 | 0.09333 / 228,625,000 | 0.08 / 229,266,670 | 35.55 / 2 |
| NKE | 2026-10-01T20:15:15Z | 2026-10-01T11:39:18.334506Z | 2026-10-02T11:39:18.606339Z | 2026-08-31 → 2026-11-30 | 0.50502 / 11,796,665,600 | 0.445 / 11,796,665,600 | 15.40 / 1 |
| PEP | 2026-10-08T01:57:44Z | 2026-10-08T11:43:03.932945Z | 2026-10-09T11:43:17.342661Z | 2026-09-30 → 2026-12-31 | 2.42853 / 30,303,667,830 | 2.39281 / 30,339,048,460 | 33.76 / 2 |
| PRGS | 2026-09-30T20:07:19Z | 2026-09-30T11:44:29.003994Z | 2026-10-01T11:45:14.476264Z | 2026-08-31 → 2026-11-30 | 1.44677 / 258,346,050 | 1.34236 / 286,448,320 | 15.63 / 1 |
| RGP | 2026-10-08T00:05:26Z | 2026-10-07T11:47:00.377571Z | 2026-10-08T11:47:02.745464Z | 2026-08-31 → 2026-11-30 | -0.16333 / 105,577,670 | -0.16333 / 100,244,330 | 11.69 / 1 |
| RPM | 2026-10-06T14:53:29Z | 2026-10-06T11:48:01.241170Z | 2026-10-07T11:47:54.461618Z | 2026-08-31 → 2026-11-30 | 1.31398 / 2,027,572,100 | 1.28385 / 2,006,085,430 | 20.91 / 1 |
| STZ | 2026-10-07T00:18:54Z | 2026-10-07T11:52:27.802514Z | 2026-10-08T11:52:30.213006Z | 2026-08-31 → 2026-11-30 | 2.81998 / 2,218,678,460 | 2.75495 / 2,202,690,210 | 35.56 / 2 |

All earlier seven tickers remain present, but the earlier validated report’s lag interpretation needs qualification. Example AIR: true observed provider 0q endDate rollover first appears September 29 11:02:26Z, 14.07 hours after publication; the existing engine instead chooses October 2 11:03:13Z when the assigned fiscal link catches up, reporting 86.08 hours.

Two additional matched forward episodes repeat tickers already in the cohort; episodes must not be counted as independent events.

Other 10 provider-date-matched forward episodes outside the 27 publication cohort: ACN 2026-10-02, AYI 2026-10-01, FDS 2026-10-01, HELE 2026-10-09, JBL 2026-10-01, LPTH 2026-10-03, PENG 2026-10-08, SIG 2026-10-03, TLRY 2026-10-09, WKHS 2026-10-01. All remaining forward episodes without immediate +1q continuity are listed by ticker/date to keep the complete observed scope visible: ACN 2026-10-13, AEO 2026-10-03, ALZN 2026-10-03, ASO 2026-10-03, AVAV 2026-10-03, AYI 2026-10-13, BRZE 2026-10-03, CAG 2026-10-13, CAL 2026-10-03, CALM 2026-10-13, CNM 2026-10-03, CPRT 2026-10-03, CRMT 2026-10-03, DBI 2026-10-03, DXLG 2026-10-03, FDS 2026-10-13, FEIM 2026-10-03, FLWS 2026-10-03, GME 2026-10-03, IBEX 2026-10-03, JBL 2026-10-13, JILL 2026-10-03, KFY 2026-10-03, KMX 2026-10-13, KR 2026-10-03, LAKE 2026-10-03, LOVE 2026-10-03, M 2026-10-03, MIND 2026-10-03, MTN 2026-10-13, NB 2026-10-13, NKE 2026-10-13, ORCL 2026-10-03, RH 2026-10-03, UNFI 2026-10-03, VNCE 2026-10-03, ZUMZ 2026-10-03.

| Provider backward-date anomaly | Old → new date | First observed UTC |
| --- | --- | --- |
| ACN | 2026-11-30 → 2026-08-31 | 2026-10-03T11:01:14.536475Z |
| AYI | 2026-11-30 → 2026-08-31 | 2026-10-03T11:06:53.896392Z |
| CAG | 2026-11-30 → 2026-08-31 | 2026-10-03T11:10:06.268268Z |
| CALM | 2026-11-30 → 2026-08-31 | 2026-10-03T11:10:12.288412Z |
| FDS | 2026-11-30 → 2026-08-31 | 2026-10-03T11:21:21.982174Z |
| IDT | 2026-10-31 → 2026-07-31 | 2026-10-03T11:27:37.616445Z |
| JBL | 2026-11-30 → 2026-08-31 | 2026-10-03T11:29:49.104433Z |
| KMX | 2026-11-30 → 2026-08-31 | 2026-10-03T11:30:49.280690Z |
| MTN | 2026-10-31 → 2026-07-31 | 2026-10-03T11:37:07.300776Z |
| MU | 2026-11-30 → 2026-08-31 | 2026-10-03T11:37:20.817161Z |
| NB | 2026-09-30 → 2026-06-30 | 2026-10-03T11:37:50.842565Z |
| NKE | 2026-11-30 → 2026-08-31 | 2026-10-03T11:38:37.395900Z |


## 9. Publication overlap and bounded cohort rerun

Used the current pinned production publication authority, with VERIFIED exact timestamps, HIGH confidence and official selected evidence, inside the first/latest fiscal fetch timestamp. Publication projection ran with Yahoo mode none and no heuristic/V2 provider. All 27 exported overlap rows are EXACT. Authority is used retrospectively to label observed events; verification time is not substituted for publication time and is not claimed known at forecast acquisition. Forecast values remain strictly acquisition-specific AS_KNOWN evidence.

Existing unchanged engine results: overlap 27; PRE 26; POST 25; both 25; observed link transitions 25; comparable linked targets 25. SMXT has no usable fiscal 0q and no usable PRE/POST; WS has PRE only under this reconstruction, even though later provider fetches can exist. This is an identity-qualified coverage statement, not a scheduler failure.

Old cohort = 7; current exact overlap = 27, newly added 20: ANGO, APLD, APOG, BYRN, CAG, CCL, CNXC, DAL, HOVR, KMX, LEVI, LW, MU, NEOG, PEP, RGP, RPM, SMXT, STZ, WS.

| Ticker / reported FY/FQ | Exact publication UTC | Engine transition | Engine pair provider dates | Endpoint QA | D5 / D20 outcome |
| --- | --- | --- | --- | --- | --- |
| AIR FY2027/Q1 | 2026-09-28T20:58:22Z | OBSERVED | 2026-11-30 → 2026-11-30 | MATCH only | True / False |
| ANGO FY2027/Q1 | 2026-10-08T15:17:49Z | OBSERVED | 2026-11-30 → 2026-11-30 | MATCH only | False / False |
| APLD FY2027/Q1 | 2026-10-08T00:43:31Z | OBSERVED | 2026-11-30 → 2026-11-30 | MATCH only | False / False |
| APOG FY2027/Q2 | 2026-10-06T17:44:57Z | OBSERVED | 2026-11-30 → 2026-11-30 | MATCH only | False / False |
| BYRN FY2026/Q3 | 2026-10-08T16:10:10Z | OBSERVED | 2026-11-30 → 2026-11-30 | MATCH only | False / False |
| CAG FY2027/Q1 | 2026-09-30T11:32:13Z | OBSERVED | 2026-11-30 → 2026-11-30 | MATCH only | True / False |
| CALM FY2027/Q1 | 2026-09-30T10:07:27Z | OBSERVED | 2026-11-30 → 2026-11-30 | MATCH only | True / False |
| CCL FY2026/Q3 | 2026-09-29T13:16:12Z | OBSERVED | 2026-11-30 → 2026-11-30 | MATCH only | True / False |
| CNXC FY2026/Q3 | 2026-09-30T00:10:45Z | OBSERVED | 2026-11-30 → 2026-11-30 | MATCH only | True / False |
| DAL FY2026/Q3 | 2026-10-09T14:30:47Z | OBSERVED | 2026-12-31 → 2026-12-31 | MATCH only | False / False |
| HOVR FY2027/Q1 | 2026-10-09T15:24:51Z | OBSERVED | 2026-11-30 → 2026-11-30 | MATCH only | False / False |
| IDT FY2026/Q4 | 2026-09-28T20:31:47Z | OBSERVED | 2026-10-31 → 2026-10-31 | MATCH only | True / False |
| KMX FY2027/Q2 | 2026-09-29T11:00:30Z | OBSERVED | 2026-11-30 → 2026-11-30 | MATCH only | True / False |
| LEVI FY2026/Q3 | 2026-10-08T00:12:53Z | OBSERVED | 2026-11-30 → 2026-11-30 | MATCH only | False / False |
| LW FY2027/Q1 | 2026-10-06T16:02:01Z | OBSERVED | 2026-11-30 → 2026-11-30 | MATCH only | False / False |
| MKC FY2026/Q3 | 2026-10-01T11:31:11Z | OBSERVED | 2026-11-30 → 2026-11-30 | MATCH only | True / False |
| MTN FY2026/Q4 | 2026-09-28T20:06:47Z | OBSERVED | 2026-10-31 → 2026-10-31 | MATCH only | True / False |
| MU FY2026/Q4 | 2026-10-01T00:02:22Z | OBSERVED | 2026-11-30 → 2026-08-31 | REJECT mismatch | True / False |
| NEOG FY2027/Q1 | 2026-10-07T00:05:19Z | OBSERVED | 2026-11-30 → 2026-11-30 | MATCH only | False / False |
| NKE FY2027/Q1 | 2026-10-01T20:15:15Z | OBSERVED | 2026-11-30 → 2026-08-31 | REJECT mismatch | True / False |
| PEP FY2026/Q3 | 2026-10-08T01:57:44Z | OBSERVED | 2026-12-31 → 2026-12-31 | MATCH only | False / False |
| PRGS FY2026/Q3 | 2026-09-30T20:07:19Z | OBSERVED | 2026-11-30 → 2026-11-30 | MATCH only | True / False |
| RGP FY2027/Q1 | 2026-10-08T00:05:26Z | OBSERVED | 2026-11-30 → 2026-11-30 | MATCH only | False / False |
| RPM FY2027/Q1 | 2026-10-06T14:53:29Z | OBSERVED | 2026-11-30 → 2026-11-30 | MATCH only | False / False |
| SMXT FY2026/Q2 | 2026-10-10T01:05:28Z | NO_USABLE_0Q | — → — | NO PAIR | False / False |
| STZ FY2027/Q2 | 2026-10-07T00:18:54Z | OBSERVED | 2026-11-30 → 2026-11-30 | MATCH only | False / False |
| WS FY2027/Q1 | 2026-10-07T14:30:19Z | INSUFFICIENT_POST_HISTORY | 2026-11-30 → — | NO PAIR | False / False |

D5 outcomes exist for 12/27 events; D20 for 0/27, using the existing event-window implementation and actual OHLC rows. All windows remain PARTIAL. Returns were computed only to test availability; no revision/return relation or inference was fitted. The 25 nominal pairs reduce to 23 passing endpoint provider-date equality, still not a fully validated research cohort.

## 10. Concrete bounded analysis defects

The current `reconstruct_fetch` correctly enforces fetch-specific identity, accepted rule versions, snapshot equality and knowledge cutoffs. The material gap is downstream: `analyze_event` selects old/new 0q by derived fiscal identity and accepts PRE +1q / POST 0q equality of those derived labels without checking contradictory persisted provider-date evidence. Sequence-first linking intentionally permits END_DATE_OUTSIDE_TOLERANCE, so the research layer cannot assume LINKED proves continuity.

| Ticker | PRE +1q target/date/EPS | Accepted POST 0q target/date/EPS | Persisted contradiction |
| --- | --- | --- | --- |
| MU | FY2027/Q1; 2026-11-30; 35.92457 | FY2027/Q1; 2026-08-31; 38.21061 | POST END_DATE_OUTSIDE_TOLERANCE; provider date went backward |
| NKE | FY2027/Q2; 2026-11-30; 0.50502 | FY2027/Q2; 2026-08-31; 0.43689 | POST END_DATE_OUTSIDE_TOLERANCE; provider date went backward |

Both NKE and MU have earlier genuine provider forward transitions that the current engine misses while waiting for canonical knowledge to advance. Their later accepted 0q rows carry the prior result-period date; the persisted evidence therefore does not justify same-target interpretation. This also affects the earlier seven-event report through NKE. It is not a reason to rewrite snapshots, change daily collection, attach fake canonical quarter IDs, or use CURRENT_RECONCILED as PIT evidence.

A conservative reporting guard would reject these two pairs and mark transition timing as derived-link timing unless corroborated by provider horizon evidence. A production source fix was not attempted: this task is read-only investigation first, and the bounded defect is separately documented here for review. Endpoint date equality is only a contradiction check; it does not make provider endDate permanent fiscal identity.

## 11. PRICE_TARGET history

2,441 tickers; 28,248 snapshots; median 18 successful fetch observations/ticker, 17 collection dates and 12 distinct snapshots/ticker. There are 1237 tickers with a changed (mean, median, high, low) target vector; median changes 1 across all tickers, 2 among changing tickers. currentPrice is excluded from that vector. The much higher snapshot total includes daily market-price movement.

| Target statistic | Numeric changed steps | Min step % | Median step % | Mean step % | Max step % |
| --- | --- | --- | --- | --- | --- |
| mean | 3155 | -92.5 | -0.18039 | 0.64018 | 1,100.00119 |
| median | 1501 | -92.5 | -0.24971 | 1.54938 | 1,100.00039 |
| high | 635 | -92.5 | -0.02241 | 4.50797 | 1,100.0005 |
| low | 811 | -92.5 | -0.24885 | 3.27231 | 1,400 |

| Ticker | Target-vector changes | Mean first → latest | Low first → latest | High first → latest | Current price first → latest |
| --- | --- | --- | --- | --- | --- |
| GUTS | 1 | 5.03333 → 60.40002 | 2 → 24 | 8 → 96.00004 | 0.4856 → 4.41 |
| TRUG | 1 | 6 → 60 | 6 → 60 | 6 → 60 | 0.2843 → 1.88 |
| GPMT | 2 | 1.375 → 11.5 | 1.25 → 8 | 1.5 → 15 | 0.9151 → 5.97 |
| JTAI | 1 | 80 → 6 | 80 → 6 | 80 → 6 | 1.56 → 1.47 |
| KOD | 3 | 64 → 121.66667 | 36 → 103 | 85 → 145 | 32.35 → 99.26 |
| BRTX | 1 | 160 → 300 | 20 → 300 | 300 → 300 | 2.55 → 1.75 |
| CTVA | 7 | 92.6 → 16.98608 | 78 → 13.65291 | 103 → 20 | 78.52 → 13.3 |
| HCWB | 2 | 29.99999 → 8 | 29.99999 → 8 | 29.99999 → 8 | 1.93 → 1.48 |

Of 2,441 price-family snapshot tickers, 2,290 ever have numeric mean targets; 151 have no numeric target fields. Independent adjacent-numeric comparison identifies 1,234 tickers with actual target-price changes; the 1,237 vector-state count also includes three tickers whose only changes are target availability states. Median numeric changes remain 1 across all tickers and 2 among changing tickers.

Extreme scale moves such as GUTS (~12× targets), TRUG (10×), GPMT and CTVA require corporate-action/provider-unit QA before economic interpretation. No split explanation was verified from an external source, and no claim that these are analyst revisions is made. `numberOfAnalystOpinions` appears only as an excluded schema-drift/raw field in this contract; price-target analyst counts are not normalized or semantic-hashed, so no comparable analyst-count revision series is claimed.

## 12. Material data quality and failure patterns

- No foreign-key failures, duplicate semantic identity/content keys, successful fetches lacking snapshots, or link/fetch snapshot/knowledge-cutoff mismatches were found. SUCCESS_CHANGED can reuse prior content: 40,728 changed fetches versus 40,000 distinct snapshots is expected content-addressed reuse, not duplicate evidence.
- All 39 historical schema failures are September 27/28: current read-only parser recognizes 33 as mixed usable payloads and 6 as valid no-data. These explain usable raw data without snapshots; the V2 contract was subsequently deployed. All 3,689 originally VALID_NO_DATA raw fetches remain no-data under the current parser. No current collection loss requiring a historical rewrite was established.
- Fiscal unresolved context is limited to BATRK/BELFB; 139 symbols persistently lack fiscal estimates. Mixed placeholders and absent fields are preserved rather than invented. Unknown PRICE_TARGET financialData fields are expected contract exclusions (including analyst opinions), not evidence of a newly broken schema. Fiscal and earnings-history snapshots report no drift paths.
- Negative revenue provider fields: 2 AVG, 26 LOW, 5 YEAR_AGO entries, across AMLX, KYMR, GWH and OCGN. AMLX +1q average is −37,820 in two snapshots; negative low/year-ago values need domain review before any scoring. No negative price-target field or negative/fractional analyst count was found.
- Inverted ranges: EPS FIZZ +1q (LOW 0.45397 > HIGH 0.40755), IDT +1q (1.03 > 1); revenue EXE 0q (LOW 1.994bn > HIGH 0) in two snapshots. Four normalized range cases in total; preserve evidence and flag/exclude range-based interpretation.
- The material research blocker is provider/fiscal target continuity and transition timing: 149 mixed-date targets, 12 provider date regressions, 2 demonstrably contradictory engine endpoint pairs. This is distinct from valid null future canonical IDs.

## 13. Research-readiness assessment

| Area | Assessment | Evidence |
| --- | --- | --- |
| A. Collection health | READY | Complete daily full scope; checks pass; recent SUCCESS runs; unchanged DB hashes |
| B. Snapshot/revision depth | EARLY_BUT_USABLE | 17 observation dates; thousands of numeric changes; 149 target histories need continuity QA |
| C. Publication overlap | EARLY_BUT_USABLE | 27 exact overlap events; 25 nominal pairs, 23 without endpoint date contradictions |
| D. 0q transition evidence | EARLY_BUT_USABLE | 25 publication-linked provider rollovers; existing engine timing needs correction |
| E. Broader revision-vs-return research | NOT_YET_READY | Concrete pair/timing defect; fewer than 30–50 good events; D20 available for none |

Even before rejecting contradictory pairs, 27 overlap events / 25 nominal pairs are below the earlier 30–50 good publication-linked-event guidance. No thresholds were optimized and no statistical significance or predictive signal is claimed. Waiting alone will increase sample size but will not correct the demonstrated pairing/timing defect.

## 14. Exact next bounded step

Fix and regression-test only the existing revision research analysis: retain provider horizon/endDate in fetch reconstruction, reject contradictory same-target PRE/POST pairs (NKE/MU fixtures), and distinguish first observed provider 0q rollover from a later AS_KNOWN link relabel (AIR fixture). Rerun the same bounded 27-event QA. Keep passive daily collection unchanged; defer broader revision-vs-return interpretation until 30–50 quality-approved publication-linked events and required follow-up outcomes exist. Do not modify historical forecasts, publication authority, canonical future quarters, schedulers or scoring.

## 15. Artifacts, commands and final safety

Compact cohort CSV: `exports/forecasts/forecast_revision_research_state_2026-10-14.csv` (24,690 bytes, 27 rows); SHA-256 `809faecf7abb55e555a6061fae68b55efbdbbd99bffa2c439c91b170eacb8fe7`. It retains original engine results, PRE/POST fetch/snapshot/link/resolution IDs, adds endpoint QA and separate provider transition timing, and D5/D20 availability. `REJECT_PROVIDER_DATE_MISMATCH` rows must not be interpreted as valid revisions. Large embedded state/checkpoint JSON is omitted from this compact CSV.

Direct commands executed: read-only SQLite quick_check/foreign_key_check; streaming SHA-256 before/after; bounded Python SQL aggregations and `reconstruct_fetch` over fiscal fetches; current-parser reclassification of snapshotless raw evidence; existing `run_research_export(ExportRequest(..., yahoo_mode="none", exact_timestamp_from=history_start))`; unchanged `build_forecast_revision_research(...)`; existing `validate_publication_input(...)` and `build_event_window_rows(...)`; provider date/transition cross-checks; CSV count/value assertions and `git diff --check`. No broad pytest run, provider fetch, migration, link/reconciliation write, authority enrichment or scheduler command ran.

The temporary analysis wrapper initially used an incorrect dataset-row attribute for the optional outcome join; this was corrected to `row.key.company_id/fiscal_year/fiscal_quarter` and the existing outcome function reran successfully. Initial environment probes found no `python` command and Python 3.10 lacks `hashlib.file_digest`; all completed analysis used `python3` with streaming hashlib. These were investigation-wrapper issues, not production defects.

Existing engine independently reports source hashes unchanged: forecasts `9dc1548bd9a7d07972c28012fd41da1e53b5187da8a5d7e4fc11e0913e25423b`; canonical `aec33d93fdcb060c8986a4b5fa6fbb8d70bf8aa94cc3da909c993f66239c64fa`; OHLC `aa66e4c609a41255ce97dc2af44b8696635895757864fab7d0cfd8969612c0d5`. All three quick_check results were `ok`. Required task-wide forecasts and active canonical pre/post hashes agree. No source-code changes; only this report and the compact CSV were prepared. Unrelated pre-existing workspace changes were left untouched.

Reproduction uses the pinned generation and read-only connections. Aggregate run/family totals directly from forecast_run/fetch/snapshot; resolve successful fiscal observations with the existing `reconstruct_fetch` accepted rule/cutoff checks; group by (company, expected FY, expected FQ or annual null); compare numeric AVG/range/count signatures in fetch order; count distinct UTC dates separately. Provider diagnostic episodes independently compare consecutive usable 0q provider end dates, requiring the immediately preceding +1q date to match for a comparable episode. Publication coverage uses exact event timestamps inside the complete fiscal history window, not result period_end or authority verification time.

```python
from rawcandle.fundamentals.result_publication_research_export import ExportRequest, run_research_export
from rawcandle.research.forecast_revision_research import build_forecast_revision_research
# Pin canonical_db to the active generation path recorded above.
# Select VERIFIED/HIGH authority company IDs with timestamps inside history.
run_research_export(ExportRequest(canonical_db=canonical_db, ohlc_db=ohlc_db,
    output=publication_csv, company_ids=overlap_company_ids,
    from_fiscal_year=2025, yahoo_mode="none", exact_timestamp_from=history_start))
build_forecast_revision_research(publication_csv, publication_metadata,
    forecasts_db, canonical_db, ohlc_db, temporary_engine_csv, temporary_metadata)
# Cross-check pre/post_link_id provider_end_date and actual provider 0q episodes.
```

**FORECAST_HISTORY_RESEARCH_NEEDS_FIX**
