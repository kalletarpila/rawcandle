# Actual-result context review: frozen 14-case recognition specification

Date: 2026-10-28. **Review/specification only; no implementation or authority change.** Governing audit: [latest 50 review](publication_authority_latest_50_review_2026-10-28.md), commit `c2c7f42c2d3b833776cd7549b1cc3bab3f9ed8be`.

The exact 14 positive-scope keys are frozen. Actual financial reporting is demonstrated for all 14, and target-period evidence is sufficient for human review for all 14; those statements do **not** assert that all 14 qualify for automatic authority. Dispositions are **6 safe minimal recognition candidates, 4 targeted acquisition candidates, 1 period-spec candidate, 1 intentionally held, 2 manual-review holds, 0 insufficient-evidence cases**. Eleven have a conditional one-candidate expectation under the complete applicable draft; DXLG, NEE and PVH stay held. TSLA is a negative control only. No future rule described here is an adopted runtime contract.

## 1. Exact scope and identity freeze

Membership comes only from the named audit, not from a newer Production population. Each case has one eligible 8-K Item 2.02 parent, zero currently matched candidates, one plausible parent, current status UNRESOLVED and reason QUARTER_MATCH_FAILED. No selected source, timestamp or evidence ID exists. All 14 source identities are SHARADAR_ARQ; publication authority has no ARQ/MRQ dimension in its natural key. Security/ticker are context; the stable authority key is the company/fiscal tuple. quarter_id is generation-local.

| Ticker | Authority natural key | Security ID | CIK | Frozen quarter_id | Period end | Provider fiscal period | Provider report period | Provider availability date |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AYTU | (265, 2026, Q4) | 265 | 0001385818 | 9452 | 2026-06-30 | 2026-Q4 | 2026-06-30 | 2026-09-22 |
| CURV | (605, 2027, Q2) | 606 | 0001792781 | 21376 | 2026-08-01 | 2027-Q2 | 2026-08-01 | 2026-09-10 |
| DXLG | (726, 2027, Q2) | 727 | 0000813298 | 25643 | 2026-08-01 | 2027-Q2 | 2026-08-01 | 2026-09-09 |
| GE | (931, 2026, Q3) | 934 | 0000040545 | 33069 | 2026-09-30 | 2026-Q3 | 2026-09-30 | 2026-10-20 |
| GM | (955, 2026, Q3) | 958 | 0001467858 | 33934 | 2026-09-30 | 2026-Q3 | 2026-09-30 | 2026-10-20 |
| HELE | (1023, 2027, Q2) | 1027 | 0000916789 | 36364 | 2026-08-31 | 2027-Q2 | 2026-08-31 | 2026-10-08 |
| KR | (1239, 2027, Q2) | 1243 | 0000056873 | 44228 | 2026-08-15 | 2027-Q2 | 2026-08-15 | 2026-09-18 |
| MMM | (1440, 2026, Q3) | 1449 | 0000066740 | 51429 | 2026-09-30 | 2026-Q3 | 2026-09-30 | 2026-10-20 |
| NEE | (1524, 2026, Q3) | 1533 | 0000753308 | 54519 | 2026-09-30 | 2026-Q3 | 2026-09-30 | 2026-10-21 |
| PLAY | (1745, 2027, Q2) | 1755 | 0001525769 | 62344 | 2026-08-04 | 2027-Q2 | 2026-08-04 | 2026-09-14 |
| PVH | (1819, 2027, Q2) | 1829 | 0000078239 | 64961 | 2026-08-02 | 2027-Q2 | 2026-08-02 | 2026-09-02 |
| TLRY | (2174, 2027, Q1) | 2184 | 0001731348 | 77370 | 2026-08-31 | 2027-Q1 | 2026-08-31 | 2026-10-08 |
| TXN | (2233, 2026, Q3) | 2243 | 0000097476 | 79543 | 2026-09-30 | 2026-Q3 | 2026-09-30 | 2026-10-23 |
| ZUMZ | (2453, 2027, Q2) | 2465 | 0001318008 | 87604 | 2026-08-01 | 2027-Q2 | 2026-08-01 | 2026-09-10 |

Canonical company_key is `SEC_CIK:` plus the displayed CIK. Active company/CIK/security bindings are frozen from the audit; provider first_public_result_date equals the displayed availability date for every case. Those provider dates are not UTC publication evidence. Governing result is `20261027T184515Z_refresh_fundamentals_f3c7e2a627f5_production_72bba2f3`; its 50-case membership contains these 14. The regression generation remains the audit-bound `refresh_20261028T054130Z_refresh_fundamentals_f0854217d4df_production_14d59fd7`, not a newly selected cohort.

## 2. Source payloads and reproducibility

Current contract references: [authority V1](../forecasts/result_publication_timestamp_v1_implementation_2026-09-28.md), [bounded recognition](fundamentals_v4_phase13g3_65_sec_recognition_improvements.md), [Policy V1](fundamentals_v4_phase13g3_72_publication_event_policy_v1.md), [resolver](../../rawcandle/fundamentals/result_publication.py), [context guards](../../rawcandle/fundamentals/sec_result_context.py), and [explicit reviewed Form 6-K](../../rawcandle/fundamentals/form6k_authority.py). The proposed draft is confined to additive recognition; these existing contracts remain authoritative.

| Frozen existing implementation | SHA-256 |
| --- | --- |
| rawcandle/fundamentals/result_publication.py | 3007a390ee065728e3c421c6a0cfa134acb6600d7fccebbbc191a40977a6dfd5 |
| rawcandle/fundamentals/sec_result_context.py | b115f6bc162d7f9454fe47d059d43fc898bf70e385127a72d872b11f9132d25d |
| rawcandle/fundamentals/schema/result_publication.py | 0908aeb97197eead805edbf0b2708f01ba768a037abfa27f46042199c638458d |
| rawcandle/fundamentals/publication_event_policy.py | 7686211d903365791137b2bcaf21d80f9af9e1e5d5c3e6e99107536cf6b23018 |
| rawcandle/fundamentals/form6k_authority.py | 68f9d6c6925eb48eb3bdb5e1a4d01a48e7b4d0b7e70e33b89acf16b2b3238a5c |


The original temporary audit artifacts were available and hash-verified before reuse. Only the 14 positives and five explicit controls (TSLA, ABAT, WOR, XTIA, BRC) were copied into `/tmp/publication_actual_result_context_review`. Their **71 original payloads** retain original URLs, SHA-256 and capture times. No online reacquisition was needed or performed. Therefore “unchanged” below means byte-identical to the governing captured observation; this report makes no claim about unobserved current online bytes. No governing observation was silently replaced.

| Case | Eligible parent accession | Parent acceptance UTC | Form / metadata items | Parent path | Parent payload SHA-256 | Same-accession result document | Result payload SHA-256 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AYTU | 0001437749-26-030900 | 2026-09-22T20:05:55Z | 8-K / 2.02,9.01 | [aytu20260502_8k.htm](https://www.sec.gov/Archives/edgar/data/1385818/000143774926030900/aytu20260502_8k.htm) | 65baa11b18e0479111d9a258dec354b1063711d89b601d3a819f1e6428cf4590 | [ex_955176.htm](https://www.sec.gov/Archives/edgar/data/1385818/000143774926030900/ex_955176.htm) | 36fb10fb07c3046a4a1cc26f767238acb175b5b3ebb2b81cb8a7d5fcdf90f969 |
| CURV | 0001792781-26-000036 | 2026-09-03T20:06:08Z | 8-K / 2.02,9.01 | [thi-20260903.htm](https://www.sec.gov/Archives/edgar/data/1792781/000179278126000036/thi-20260903.htm) | bf0e51258e76959d92da6085196d1413915d24de25d013102578b88f7635b7f7 | [q22026earningsrelease.htm](https://www.sec.gov/Archives/edgar/data/1792781/000179278126000036/q22026earningsrelease.htm) | 0d493f7d305330149e7a2a98027fa27134bc5bb7c4b8aceae807b53ba51ecb1c |
| DXLG | 0001193125-26-385888 | 2026-09-09T11:14:05Z | 8-K / 2.02,9.01 | [dxlg-20260909.htm](https://www.sec.gov/Archives/edgar/data/813298/000119312526385888/dxlg-20260909.htm) | fc869c341f82c94bf44a5735059d2f835869a159cf0a78dee8cb52fea514fff1 | [dxlg-ex99_1.htm](https://www.sec.gov/Archives/edgar/data/813298/000119312526385888/dxlg-ex99_1.htm) | 3dd9378b144f2b2684bd17592fa8fddd967be5680c1c34554010201048f422b0 |
| GE | 0000040545-26-000063 | 2026-10-20T10:30:57Z | 8-K / 2.02,9.01 | [ge-20261020.htm](https://www.sec.gov/Archives/edgar/data/40545/000004054526000063/ge-20261020.htm) | 0832a3a1dc2436fe7beb4dbacabaa54e6893a84a14a470290cd643bd386e4b5d | [ge3q2026earningsrelease.htm](https://www.sec.gov/Archives/edgar/data/40545/000004054526000063/ge3q2026earningsrelease.htm) | c1baa05998be095074a525c2e5564ed29ab71e3d05b18619157e41b3019605f7 |
| GM | 0001467858-26-000056 | 2026-10-20T11:30:18Z | 8-K / 2.02,9.01 | [gm-20261020.htm](https://www.sec.gov/Archives/edgar/data/1467858/000146785826000056/gm-20261020.htm) | 1f9f17374afbf9ec91121b4771f3179ca4f9256fa3a807c19d78df8f0a260e63 | [gmq32026pressreleaseandfin.htm](https://www.sec.gov/Archives/edgar/data/1467858/000146785826000056/gmq32026pressreleaseandfin.htm) | 95297ccfe37212db992fb9052fdbce8663c89aec3203fc7f315f84d3c1cab646 |
| HELE | 0000916789-26-000137 | 2026-10-08T10:50:14Z | 8-K / 2.02,9.01 | [hele-20261008.htm](https://www.sec.gov/Archives/edgar/data/916789/000091678926000137/hele-20261008.htm) | 51206e355d34ba1c450b48835479b5051fabb8e3fcbe0e03fa7eaadcd18130fa | [fy27_q2xex-991.htm](https://www.sec.gov/Archives/edgar/data/916789/000091678926000137/fy27_q2xex-991.htm) | 992fcaed1374fff08ca913e23b8141e9c6a42befe79f68e4cbedad3ea577968b |
| KR | 0001104659-26-106890 | 2026-09-11T10:59:48Z | 8-K / 2.02,9.01 | [tm2625060d1_8k.htm](https://www.sec.gov/Archives/edgar/data/56873/000110465926106890/tm2625060d1_8k.htm) | 8d29d25b64736cd1fa33f62c1db366ed6e86600ee3b4eb99719549b94adf6046 | [tm2625060d1_ex99-1.htm](https://www.sec.gov/Archives/edgar/data/56873/000110465926106890/tm2625060d1_ex99-1.htm) | 6b97198dc7667cd4293bf332557d8f8739b6f1a02a78bde539d8ba7f4585e1c1 |
| MMM | 0000066740-26-000308 | 2026-10-20T10:35:38Z | 8-K / 2.02,9.01 | [mmm-20261020.htm](https://www.sec.gov/Archives/edgar/data/66740/000006674026000308/mmm-20261020.htm) | 72f8ee4edfe376698b445b5afd7b7d99c347b9770aa725815f78a1e91938041b | [q32026-8kerexx991.htm](https://www.sec.gov/Archives/edgar/data/66740/000006674026000308/q32026-8kerexx991.htm) | efd170e0ccede056bd36e7d2764d4cd94d9a06c118e7d79771d1d7e6ff962679 |
| NEE | 0000753308-26-000077 | 2026-10-21T11:40:10Z | 8-K / 2.02,9.01 | [nee-20261021.htm](https://www.sec.gov/Archives/edgar/data/753308/000075330826000077/nee-20261021.htm) | 58286e00ff9ba0b114fe10cef99cde5f9b34621338e2780ceda8349e952230d5 | [neeq32026exhibit99.htm](https://www.sec.gov/Archives/edgar/data/753308/000075330826000077/neeq32026exhibit99.htm) | 98230055f2a8c9a7fa51757c1f4f8e9fbec2f4ed30eb5d78e73e79bf65b45c4e |
| PLAY | 0001525769-26-000039 | 2026-09-14T20:13:28Z | 8-K / 2.02,9.01 | [play-20260914.htm](https://www.sec.gov/Archives/edgar/data/1525769/000152576926000039/play-20260914.htm) | 88dd1ab11c2b8610cc826e7ff5a2fedd7e0295468953e3d6a370512fc2740ef6 | [play-2026q2er8kxexx991.htm](https://www.sec.gov/Archives/edgar/data/1525769/000152576926000039/play-2026q2er8kxexx991.htm) | 92f9877679f7e3db564bbf75ae59e72bc2db337449c4a4d82a4ca568eb334db6 |
| PVH | 0000078239-26-000055 | 2026-09-02T20:23:55Z | 8-K / 2.02,9.01 | [pvh-20260902.htm](https://www.sec.gov/Archives/edgar/data/78239/000007823926000055/pvh-20260902.htm) | 94a65ffcaf7197c89f5ad2bbe6e860f7d53dfc387a99285281c4f065dfbd5e12 | [ex99120262q8k.htm](https://www.sec.gov/Archives/edgar/data/78239/000007823926000055/ex99120262q8k.htm) | 36900482c3ec908064c57de62217c4bb7adedd702dc8f5eef439e612c0be0f24 |
| TLRY | 0001171843-26-006527 | 2026-10-08T11:00:19Z | 8-K / 2.02,9.01 | [f8k_100826.htm](https://www.sec.gov/Archives/edgar/data/1731348/000117184326006527/f8k_100826.htm) | af5fe913bfd7574064b4000c05610302c6ee25c33138181077b0c1d374172081 | [exh_991.htm](https://www.sec.gov/Archives/edgar/data/1731348/000117184326006527/exh_991.htm) | 91f8505436512529ff1e2904feb6aeb3124cd4430e76c5c550771813a5901183 |
| TXN | 0000097476-26-000165 | 2026-10-21T20:04:14Z | 8-K / 2.02,9.01 | [txn-20261021.htm](https://www.sec.gov/Archives/edgar/data/97476/000009747626000165/txn-20261021.htm) | 399e89c3d93acb8951018584dbf6b96200bcca50c4536525c2274fd105155427 | [q32026txnex99-eredgar.htm](https://www.sec.gov/Archives/edgar/data/97476/000009747626000165/q32026txnex99-eredgar.htm) | b78bfcf18a679a47e16ff4ab772717096e2a58ff02a2f80fbbff47512eaf6ac9 |
| ZUMZ | 0001171843-26-005980 | 2026-09-10T20:15:17Z | 8-K / 2.02,9.01 | [f8k_091026.htm](https://www.sec.gov/Archives/edgar/data/1318008/000117184326005980/f8k_091026.htm) | 68be285050ec0813ff4e0e995390fd0cf4bd8ee0c1d909286acc1432f8d21fa0 | [exh_991.htm](https://www.sec.gov/Archives/edgar/data/1318008/000117184326005980/exh_991.htm) | bbc315113a1ed6431a1855c9f029f9b9c10bffc9468a4ff6409829e655da77b0 |

Each result document has exactly the parent CIK/accession directory. The parent acceptance above remains the only proposed SEC authority timestamp; no date/time from an exhibit, provider, headline, conference call or body replaces it. Every parent is accepted on/after its target end and within 180 days. All source references in this cohort are HTTPS www.sec.gov without redirects/query/cross-accession traversal. Default acquisition currently returns the result documents for AYTU, DXLG, GE, GM, MMM, PVH, TLRY and ZUMZ; the other six are diagnostic captures, not automatically acquired inputs.

The full governing audit source-manifest SHA-256 is `8c7ba4b3cb3957b174c9bab7be6baad59169a886cf680c11c6c3fec7f433768c`; its replay SHA-256 is `8b1499e5bd266d388ef2c142b972923151be6dcc6cb50040bf2699bc580f3641`. Source drift observed since that audit: **none in reused bytes; live drift not measured**. The already known TSLA historical-to-audit hash difference is preserved in section 10, not concealed. The new subset manifest and replay-input fingerprints are listed in section 14.

## 3. Frozen actual-result and target-period evidence

Every excerpt below is an exact, reviewer-selected substring of `filing_text` output, not proposed parser output. Coordinates are zero-based half-open Unicode character offsets in the complete normalized document (including its filing-text prefix). Raw source identity is the payload hash in section 2; normalized-document and individual-span hashes are in `evidence_spans.json`. Reusing an offset against changed bytes is forbidden. Human review may inspect a full same-accession statement; that permission does not enlarge the automatic 6,000-character result-event search. A sufficient human target proof may still be insufficient for bounded automatic matching.

### AYTU — (265, 2026, Q4)


| Evidence role | Exact frozen text / location | Source |
| --- | --- | --- |
| actual | “announcing its fiscal 2026 fourth quarter operational and financial results” (`[2210:2285]`) | parent |
| fiscal | “fiscal 2026 fourth quarter” (`[2225:2251]`) | parent |
| period | “Three Months Ended Twelve Months Ended June 30, June 30, 2026 2025 2026 2025” (`[7285:7361]`) | same-accession result document |
| financial | “Net loss was approximately break-even at less than ($0.1) million” (`[1631:1696]`) | same-accession result document |

**ACTUAL_RESULT_EVIDENCE = SUFFICIENT.** **Target-period evidence = SUFFICIENT_FOR_REVIEW; classification: EXACT_PERIOD_SAME_ACCESSION.** The parent explicitly announces FY2026 Q4, and the release separately reports Q4 revenue and approximately break-even GAAP net loss. Its three-month and twelve-month columns are separately present: Q4 is not inferred by subtracting annual and nine-month values. Normalizing year/quarter order is sufficient only after an actual-event clause is isolated; full-year-only language must never substitute for Q4. Unlike ABAT, a separate Q4 net-result statement is present.

**Current path:** FISCAL_TOKEN_FORM_UNRECOGNIZED. Legacy primary quarter method = None; the unchanged detailed resolver returns 0 matched / 1 plausible, UNRESOLVED / QUARTER_MATCH_FAILED. These diagnostic documents were not added to the default replay. **Disposition:** SAFE_MINIMAL_RECOGNITION_CANDIDATE. **Draft dependency:** R1 + R2. **Confidence:** HIGH on the evidence/mechanism; hypothetical outcome is unimplemented.

### CURV — (605, 2027, Q2)


| Evidence role | Exact frozen text / location | Source |
| --- | --- | --- |
| actual_period | “today announced its financial results for the second quarter ended August 1, 2026” (`[684:765]`) | same-accession result document |
| issuer_fiscal | “second quarter of fiscal year 2026” (`[2216:2250]`) | parent |

**ACTUAL_RESULT_EVIDENCE = SUFFICIENT.** **Target-period evidence = SUFFICIENT_FOR_REVIEW; classification: FISCAL_CONVENTION_TRANSLATION_REQUIRED.** Primary and release both use issuer FY2026 Q2, while the canonical key is FY2027 Q2. They agree on the quarter/end economically. The strong primary token suppresses the exhibit. Fetching alone is insufficient: the existing exhibit result_context returns text[0:758], clipping the end of the August 1, 2026 clause. Finish that already-started reporting sentence within the existing 6,000-character search bound; do not scan later dates or translate the canonical key.

**Current path:** ISSUER_PROVIDER_FY_CONVENTION_CONFLICT; PRIMARY_STRONG_TOKEN_SUPPRESSES_EXHIBIT; EVENT_WINDOW_TOO_NARROW. Legacy primary quarter method = None; the unchanged detailed resolver returns 0 matched / 1 plausible, UNRESOLVED / QUARTER_MATCH_FAILED. These diagnostic documents were not added to the default replay. **Disposition:** NEEDS_TARGETED_SOURCE_ACQUISITION_CHANGE. **Draft dependency:** R1 + R3 + R4 + R6. **Confidence:** HIGH on the evidence/mechanism; hypothetical outcome is unimplemented.

### DXLG — (726, 2027, Q2)


| Evidence role | Exact frozen text / location | Source |
| --- | --- | --- |
| actual | “today reported operating results for the second quarter of fiscal 2026” (`[431:501]`) | same-accession result document |
| period | “For the Three Months Ended For the Six Months Ended August 1, 2026 August 2, 2025 August 1, 2026 August 2, 2025” (`[36349:36460]`) | same-accession result document |
| non_period_date_trap | “Total cash and investments were $20.1 million at August 1, 2026” (`[1421:1484]`) | same-accession result document |

**ACTUAL_RESULT_EVIDENCE = SUFFICIENT.** **Target-period evidence = SUFFICIENT_FOR_REVIEW; classification: COMPARATIVE_CONTEXT_REQUIRES_SCOPING.** The release proves actual issuer FY2026 Q2 results, but its nearby August 1 date describes a cash/investment balance, not a quarter end. There is no quarter-ended date clause in the inspected normalized release. The valid quarterly end is in the explicitly three-month table at character 36,357, well beyond the 6,000-character result-event search. The six-month and prior-year columns must also be bound. Lexical normalization alone cannot safely map the canonical FY2027 key. Human period proof is sufficient; minimal automatic proof is not.

**Current path:** ISSUER_PROVIDER_FY_CONVENTION_CONFLICT; FISCAL_TOKEN_FORM_UNRECOGNIZED; FINANCIAL_TABLE_ONLY_TARGET_BINDING; NON_PERIOD_DATE_TRAP. Legacy primary quarter method = None; the unchanged detailed resolver returns 0 matched / 1 plausible, UNRESOLVED / QUARTER_MATCH_FAILED. These diagnostic documents were not added to the default replay. **Disposition:** MANUAL_REVIEW_STILL_REQUIRED. **Draft dependency:** R2 is insufficient; R3 stops at the table boundary. **Confidence:** HIGH on the evidence/mechanism; hypothetical outcome is unimplemented.

### GE — (931, 2026, Q3)


| Evidence role | Exact frozen text / location | Source |
| --- | --- | --- |
| actual_period | “announced results today for the third quarter ending September 30, 2026” (`[674:745]`) | same-accession result document |
| fiscal | “THIRD QUARTER 2026” (`[74:92]`) | same-accession result document |
| parent_actual | “released its third-quarter 2026 financial results” (`[2798:2847]`) | parent |

**ACTUAL_RESULT_EVIDENCE = SUFFICIENT.** **Target-period evidence = SUFFICIENT_FOR_REVIEW; classification: EXACT_PERIOD_SAME_ACCESSION.** The current exhibit context has exactly 2026:Q3 and a September 30 date. match_quarter_context chooses EXACT_PERIOD_END, but result_periods recognizes ended, not ending, so _new_context_method returns None instead of establishing a valid period. A GE-only fix should prefer narrow completed-event ending recognition over changing global method priority. The proposed lexical group also has an independent actual primary third-quarter 2026 clause; it can establish the same key without a generic fallback or interpreting a cover date.

**Current path:** DATE_METHOD_PRECEDENCE; FISCAL_TOKEN_FORM_UNRECOGNIZED (hyphenated primary). Legacy primary quarter method = None; the unchanged detailed resolver returns 0 matched / 1 plausible, UNRESOLVED / QUARTER_MATCH_FAILED. These diagnostic documents were not added to the default replay. **Disposition:** SAFE_MINIMAL_RECOGNITION_CANDIDATE. **Draft dependency:** R1 + R2 primary route; R1 + R7 is a smaller GE-only alternative. **Confidence:** HIGH on the evidence/mechanism; hypothetical outcome is unimplemented.

### GM — (955, 2026, Q3)


| Evidence role | Exact frozen text / location | Source |
| --- | --- | --- |
| actual_headline | “GM releases 2026 third-quarter results” (`[132:170]`) | same-accession result document |
| actual_financial | “today reported third-quarter 2026 revenue of $50.0 billion, net income attributable to stockholders of $3.3 billion” (`[335:450]`) | same-accession result document |
| period | “Three Months Ended September 30, 2026 Three Months Ended September 30, 2025” (`[7696:7771]`) | same-accession result document |
| future_only_contrast | “The company expects net income attributable to stockholders to be $8.9 billion to $9.5 billion” (`[575:669]`) | same-accession result document |

**ACTUAL_RESULT_EVIDENCE = SUFFICIENT.** **Target-period evidence = SUFFICIENT_FOR_REVIEW; classification: EXACT_PERIOD_SAME_ACCESSION.** An actual-result headline uses 2026 third-quarter; the body reports current revenue and GAAP net income. A later sentence expects future full-year net income and is not the actual Q3 result. Preserve that distinction rather than deleting every sentence containing guidance or allowing guidance to donate period proof. The same-accession quarterly statements separately corroborate September 30, 2026.

**Current path:** FISCAL_TOKEN_FORM_UNRECOGNIZED (year order/hyphenation); actual/result versus guidance clause boundary. Legacy primary quarter method = None; the unchanged detailed resolver returns 0 matched / 1 plausible, UNRESOLVED / QUARTER_MATCH_FAILED. These diagnostic documents were not added to the default replay. **Disposition:** SAFE_MINIMAL_RECOGNITION_CANDIDATE. **Draft dependency:** R1 + R2. **Confidence:** HIGH on the evidence/mechanism; hypothetical outcome is unimplemented.

### HELE — (1023, 2027, Q2)


| Evidence role | Exact frozen text / location | Source |
| --- | --- | --- |
| actual_period | “reported results for the three-month period ended August 31, 2026” (`[798:863]`) | same-accession result document |
| fiscal | “second quarter of fiscal 2027” (`[2311:2340]`) | parent |
| boilerplate | “Generally, the words “anticipates”, “assumes”, “believes”, “expects”” (`[3044:3112]`) | parent |

**ACTUAL_RESULT_EVIDENCE = SUFFICIENT.** **Target-period evidence = SUFFICIENT_FOR_REVIEW; classification: EXACT_PERIOD_DIRECT.** The actual primary announces issuer/canonical FY2027 Q2. Later boilerplate quotes anticipates in the first 1,200 characters, making the entire section unsafe and preventing exhibit acquisition. The same-accession release reports the three-month period ended August 31 and full GAAP results. Removing that veto alone is not sufficient: the primary fiscal form of fiscal 2027 is not recognized, and the release combines three-month phrasing with current/prior fiscal summary wording. Use the unambiguous primary actual-event unit for the minimal lexical path; do not globally ignore the later source text.

**Current path:** GLOBAL_FUTURE_EVENT_VETO; FISCAL_TOKEN_FORM_UNRECOGNIZED. Legacy primary quarter method = None; the unchanged detailed resolver returns 0 matched / 1 plausible, UNRESOLVED / QUARTER_MATCH_FAILED. These diagnostic documents were not added to the default replay. **Disposition:** SAFE_MINIMAL_RECOGNITION_CANDIDATE. **Draft dependency:** R1 + R2 (R1 alone is insufficient). **Confidence:** HIGH on the evidence/mechanism; hypothetical outcome is unimplemented.

### KR — (1239, 2027, Q2)


| Evidence role | Exact frozen text / location | Source |
| --- | --- | --- |
| actual_period | “today reported results for its second quarter ended August 15, 2026” (`[474:541]`) | same-accession result document |
| issuer_fiscal | “second quarter 2026” (`[2101:2120]`) | parent |
| malformed_date | “On September 11, 202,” (`[2016:2037]`) | parent |

**ACTUAL_RESULT_EVIDENCE = SUFFICIENT.** **Target-period evidence = SUFFICIENT_FOR_REVIEW; classification: FISCAL_CONVENTION_TRANSLATION_REQUIRED.** The directly linked release supplies the exact canonical August 15 end and actual results. Running the existing _new_context_method on its captured context already returns CIK_ITEM_2_02_EXACT_PERIOD_END. Thus the main runtime opportunity is bounded acquisition, not a new period inference. Primary and release agree on issuer FY2026 Q2; only provider naming differs. The malformed parent announcement date is retained verbatim and never repairs or replaces the SEC acceptance timestamp.

**Current path:** ISSUER_PROVIDER_FY_CONVENTION_CONFLICT; PRIMARY_STRONG_TOKEN_SUPPRESSES_EXHIBIT. Legacy primary quarter method = None; the unchanged detailed resolver returns 0 matched / 1 plausible, UNRESOLVED / QUARTER_MATCH_FAILED. These diagnostic documents were not added to the default replay. **Disposition:** NEEDS_TARGETED_SOURCE_ACQUISITION_CHANGE. **Draft dependency:** R1 + R3 + R4. **Confidence:** HIGH on the evidence/mechanism; hypothetical outcome is unimplemented.

### MMM — (1440, 2026, Q3)


| Evidence role | Exact frozen text / location | Source |
| --- | --- | --- |
| actual | “reporting third-quarter 2026 financial results” (`[3409:3455]`) | parent |
| current_headline | “3M Reports Third-Quarter 2026 Results” (`[62:99]`) | same-accession result document |
| comparative | “Third-quarter highlights: Q3 2026 Q3 2025” (`[1250:1291]`) | same-accession result document |
| period | “Three months ended September 30, Nine months ended September 30, 2026 2025 2026 2025” (`[12008:12092]`) | same-accession result document |

**ACTUAL_RESULT_EVIDENCE = SUFFICIENT.** **Target-period evidence = SUFFICIENT_FOR_REVIEW; classification: COMPARATIVE_CONTEXT_REQUIRES_SCOPING.** The current exhibit context covers characters 550–1,330 and contains Q3 2026 and Q3 2025. The parent itself explicitly reports third-quarter 2026 financial results. Narrow lexical normalization can use that current actual primary clause; it must not collapse a table by choosing its first/newest year. If a later implementation instead relies on the exhibit, it needs explicit current/prior column roles under R5. Two current-result statements with different periods remain held.

**Current path:** MULTIPLE_COMPARATIVE_FISCAL_TOKENS; FISCAL_TOKEN_FORM_UNRECOGNIZED (primary hyphen). Legacy primary quarter method = None; the unchanged detailed resolver returns 0 matched / 1 plausible, UNRESOLVED / QUARTER_MATCH_FAILED. These diagnostic documents were not added to the default replay. **Disposition:** SAFE_MINIMAL_RECOGNITION_CANDIDATE. **Draft dependency:** R1 + R2 primary route; R5 only for an exhibit-table fallback. **Confidence:** HIGH on the evidence/mechanism; hypothetical outcome is unimplemented.

### NEE — (1524, 2026, Q3)


| Evidence role | Exact frozen text / location | Source |
| --- | --- | --- |
| actual_financial | “today reported 2026 third-quarter net income attributable to NextEra Energy on a GAAP basis of $4.775 billion” (`[827:936]`) | same-accession result document |
| period_stage | “Preliminary Three Months Ended September 30, 2026” (`[33552:33601]`) | same-accession result document |
| scope | “Net Income (Loss) Attributable to NextEra Energy, Inc.” (`[34858:34912]`) | same-accession result document |

**ACTUAL_RESULT_EVIDENCE = SUFFICIENT.** **Target-period evidence = SUFFICIENT_FOR_REVIEW; classification: EXACT_PERIOD_SAME_ACCESSION.** The release explicitly reports current parent GAAP net income, so an actual financial-report event is proven. Its three-month statements, far later in the release, are labeled Preliminary and include FPL, NEER, corporate/other and parent columns. The review does not silently decide whether that label denotes an additive-ineligible preliminary event or ordinary unaudited statement status. Source discovery alone is not eligibility: keep the case held until the event-stage and consolidated-parent proof are reviewed. This is a refinement of the prior audit’s link-coverage opportunity, not a claim that no financial results exist.

**Current path:** LINK_SHAPE_NOT_RECOGNIZED; FISCAL_TOKEN_FORM_UNRECOGNIZED; PRELIMINARY_STAGE_AND_PARENT_SUBSIDIARY_SCOPE. Legacy primary quarter method = None; the unchanged detailed resolver returns 0 matched / 1 plausible, UNRESOLVED / QUARTER_MATCH_FAILED. These diagnostic documents were not added to the default replay. **Disposition:** MANUAL_REVIEW_STILL_REQUIRED. **Draft dependency:** R8 + R2 can expose context; R1/financial-scope gate keeps qualification held. **Confidence:** MEDIUM on event-stage eligibility; HIGH on source exclusion and actual reporting.

### PLAY — (1745, 2027, Q2)


| Evidence role | Exact frozen text / location | Source |
| --- | --- | --- |
| actual_period | “today announced financial results for its second quarter of fiscal 2026 ended August 4, 2026” (`[334:426]`) | same-accession result document |
| issuer_fiscal | “second quarter 2026 results” (`[2628:2655]`) | parent |

**ACTUAL_RESULT_EVIDENCE = SUFFICIENT.** **Target-period evidence = SUFFICIENT_FOR_REVIEW; classification: FISCAL_CONVENTION_TRANSLATION_REQUIRED.** The issuer FY2026 Q2 release explicitly reports a quarter ended August 4, matching the provider/canonical FY2027 Q2 key. Its existing captured context already returns CIK_ITEM_2_02_EXACT_PERIOD_END through _new_context_method. Preserve separate six-month cash-flow and prior-year comparisons; they do not replace the exact current quarterly event.

**Current path:** ISSUER_PROVIDER_FY_CONVENTION_CONFLICT; PRIMARY_STRONG_TOKEN_SUPPRESSES_EXHIBIT. Legacy primary quarter method = None; the unchanged detailed resolver returns 0 matched / 1 plausible, UNRESOLVED / QUARTER_MATCH_FAILED. These diagnostic documents were not added to the default replay. **Disposition:** NEEDS_TARGETED_SOURCE_ACQUISITION_CHANGE. **Draft dependency:** R1 + R3 + R4. **Confidence:** HIGH on the evidence/mechanism; hypothetical outcome is unimplemented.

### PVH — (1819, 2027, Q2)


| Evidence role | Exact frozen text / location | Source |
| --- | --- | --- |
| actual_headline | “PVH CORP. REPORTS 2026 SECOND QUARTER RESULTS” (`[45:90]`) | same-accession result document |
| actual | “today reported its 2026 second quarter results and reaffirmed its 2026 outlook” (`[1612:1690]`) | same-accession result document |
| period | “Quarter Ended Six Months Ended 8/2/26 8/3/25 8/2/26 8/3/25” (`[31345:31403]`) | same-accession result document |
| period_english | “periods ended August 2, 2026 and August 3, 2025” (`[32745:32792]`) | same-accession result document |
| table_heading | “Consolidated GAAP Statements of Operations” (`[31265:31307]`) | same-accession result document |

**ACTUAL_RESULT_EVIDENCE = SUFFICIENT.** **Target-period evidence = SUFFICIENT_FOR_REVIEW; classification: COMPARATIVE_CONTEXT_REQUIRES_SCOPING.** The headline and actual statement are real, and the latter is at character 1,612, already inside 6,000. The exact numeric quarter header starts at 31,345 and the English date at 32,759. A bounded headline/sentence expansion cannot bridge that gap. The table proves the target for human review, but automatically scanning that far for a matching date would defeat the recognition bound and comparative-quarter/six-month protections. Keep held; the simple long-headline hypothesis is insufficient.

**Current path:** EVENT_WINDOW_TOO_NARROW (hypothesis only); ISSUER_PROVIDER_FY_CONVENTION_CONFLICT; FINANCIAL_TABLE_ONLY_TARGET_BINDING. Legacy primary quarter method = None; the unchanged detailed resolver returns 0 matched / 1 plausible, UNRESOLVED / QUARTER_MATCH_FAILED. These diagnostic documents were not added to the default replay. **Disposition:** GUARD_IS_INTENTIONAL_KEEP_HELD. **Draft dependency:** R2 + R6 are insufficient; R3 cannot bind a date outside the proposed bound. **Confidence:** HIGH on the evidence/mechanism; hypothetical outcome is unimplemented.

### TLRY — (2174, 2027, Q1)


| Evidence role | Exact frozen text / location | Source |
| --- | --- | --- |
| actual_period | “today reported financial results for its first fiscal quarter ended August 31, 2026” (`[1439:1522]`) | same-accession result document |
| fiscal | “Q1 Fiscal 2027” (`[91:105]`) | same-accession result document |
| business_line | “International Cannabis, Beverage and Pharmaceutical Distribution” (`[242:306]`) | same-accession result document |
| gaap | “net loss was $40.0 million in the first quarter” (`[5118:5165]`) | same-accession result document |

**ACTUAL_RESULT_EVIDENCE = SUFFICIENT.** **Target-period evidence = SUFFICIENT_FOR_REVIEW; classification: EXACT_PERIOD_SAME_ACCESSION.** Distribution is part of the pharmaceutical business-line description, while the actual reporting sentence states first fiscal quarter ended August 31, 2026 and the package reports revenue and GAAP net loss. That reporting sentence is inside 6,000 and contains direct quarter-end proof. A case-insensitive exception for the word Distribution alone is not acceptable; distribution-only announcements still fail for lack of actual quarterly earnings evidence.

**Current path:** BUSINESS_LINE_DISTRIBUTION_FALSE_VETO; unrecognized headline Q1 Fiscal form is secondary. Legacy primary quarter method = None; the unchanged detailed resolver returns 0 matched / 1 plausible, UNRESOLVED / QUARTER_MATCH_FAILED. These diagnostic documents were not added to the default replay. **Disposition:** SAFE_MINIMAL_RECOGNITION_CANDIDATE. **Draft dependency:** R1 (R2 is not necessary to use its exact ended-period clause). **Confidence:** HIGH on the evidence/mechanism; hypothetical outcome is unimplemented.

### TXN — (2233, 2026, Q3)


| Evidence role | Exact frozen text / location | Source |
| --- | --- | --- |
| actual_headline | “TI reports third quarter 2026 financial results and shareholder returns” (`[60:131]`) | same-accession result document |
| period | “For Three Months Ended September 30, (In millions, except per-share amounts) 2026 2025” (`[2232:2318]`) | same-accession result document |
| financial | “today reported third quarter revenue of $6.06 billion, net income of $2.43 billion” (`[268:350]`) | same-accession result document |

**ACTUAL_RESULT_EVIDENCE = SUFFICIENT.** **Target-period evidence = SUFFICIENT_FOR_REVIEW; classification: EXACT_PERIOD_SAME_ACCESSION.** The parent explicitly furnishes a news release as Exhibit 99, but its label and filename miss the 99.1/99.2 or press-release/earnings/results shapes. The existing _new_context_method on the diagnostically captured release already returns EXPLICIT_FISCAL_QUARTER for unique 2026:Q3; the quarter statement also corroborates September 30. No new provider or source hierarchy is needed. Arbitrary Exhibit 99 documents remain excluded.

**Current path:** LINK_SHAPE_NOT_RECOGNIZED. Legacy primary quarter method = None; the unchanged detailed resolver returns 0 matched / 1 plausible, UNRESOLVED / QUARTER_MATCH_FAILED. These diagnostic documents were not added to the default replay. **Disposition:** NEEDS_TARGETED_SOURCE_ACQUISITION_CHANGE. **Draft dependency:** R1 + R8. **Confidence:** HIGH on the evidence/mechanism; hypothetical outcome is unimplemented.

### ZUMZ — (2453, 2027, Q2)


| Evidence role | Exact frozen text / location | Source |
| --- | --- | --- |
| actual_period | “today reported results for the second quarter ended August 1, 2026” (`[299:365]`) | same-accession result document |
| comparative | “second quarter ended August 2, 2025 (13 weeks)” (`[492:538]`) | same-accession result document |
| future_heading | “Fiscal 2026 Third Quarter Outlook” (`[3082:3115]`) | same-accession result document |
| future_period | “three months ending October 31, 2026” (`[3160:3196]`) | same-accession result document |

**ACTUAL_RESULT_EVIDENCE = SUFFICIENT.** **Target-period evidence = SUFFICIENT_FOR_REVIEW; classification: COMPARATIVE_CONTEXT_REQUIRES_SCOPING.** The first actual reporting clause declares August 1, 2026. A following sales comparison refers to August 2, 2025; a later separately headed Q3 outlook refers to October 31, 2026. The actual Q2 event, prior comparison and future outlook are distinct roles in the same document. Match the exact canonical end via the actual clause without renumbering FY2027 or globally ignoring older/newer dates. If those roles cannot be established, retain the current hold.

**Current path:** MULTIPLE_COMPARATIVE_PERIOD_ENDS; ISSUER_PROVIDER_FY_CONVENTION_CONFLICT. Legacy primary quarter method = None; the unchanged detailed resolver returns 0 matched / 1 plausible, UNRESOLVED / QUARTER_MATCH_FAILED. These diagnostic documents were not added to the default replay. **Disposition:** NEEDS_PERIOD_MATCHING_SPEC. **Draft dependency:** R1 + R3 + R5. **Confidence:** HIGH on the evidence/mechanism; hypothetical outcome is unimplemented.

## 4. Guard matrix: intent, safe narrowing and risk


| Case | Blocking guard(s) | Intentional protection? | Safe to narrow? | Positive scope / negative-regression risk |
| --- | --- | --- | --- | --- |
| AYTU | FISCAL_TOKEN_FORM_UNRECOGNIZED | NO (unsupported equivalent word order); Q4/annual scope protection remains YES | YES, only an actual Q4 clause with matching issuer/canonical FY | R1 + R2; same fiscal key and false-future/financial-scope protections remain mandatory |
| CURV | ISSUER_PROVIDER_FY_CONVENTION_CONFLICT; PRIMARY_STRONG_TOKEN_SUPPRESSES_EXHIBIT; EVENT_WINDOW_TOO_NARROW | YES for real fiscal conflicts; PARTIAL for target-blind fetch suppression and mid-date clipping | YES, conditional on the exact same-event August 1 end and coherent source naming | R1 + R3 + R4 + R6; same fiscal key and false-future/financial-scope protections remain mandatory |
| DXLG | ISSUER_PROVIDER_FY_CONVENTION_CONFLICT; FISCAL_TOKEN_FORM_UNRECOGNIZED; FINANCIAL_TABLE_ONLY_TARGET_BINDING; NON_PERIOD_DATE_TRAP | YES for date/quarter-grain protection; NO for equivalent fiscal wording omission | UNKNOWN for automatic table binding; NO for using the nearby cash date | R2 is insufficient; R3 stops at the table boundary; keep held; no date proximity, window extension or stage inference |
| GE | DATE_METHOD_PRECEDENCE; FISCAL_TOKEN_FORM_UNRECOGNIZED (hyphenated primary) | YES for rejecting an incidental date; PARTIAL for the ending grammar and non-conclusive method selection | YES for completed-result ending grammar or a proven primary fiscal token; NO for blanket fallback after any date conflict | R1 + R2 primary route; R1 + R7 is a smaller GE-only alternative; same fiscal key and false-future/financial-scope protections remain mandatory |
| GM | FISCAL_TOKEN_FORM_UNRECOGNIZED (year order/hyphenation); actual/result versus guidance clause boundary | NO for lexical omission; YES for future-guidance rejection | YES within the actual current-result unit; never import forecast net income | R1 + R2; same fiscal key and false-future/financial-scope protections remain mandatory |
| HELE | GLOBAL_FUTURE_EVENT_VETO; FISCAL_TOKEN_FORM_UNRECOGNIZED | PARTIAL: future-event protection YES, treating a quoted boilerplate keyword as the announced event NO | YES with full actual-event/modality proof and isolated boilerplate | R1 + R2 (R1 alone is insufficient); same fiscal key and false-future/financial-scope protections remain mandatory |
| KR | ISSUER_PROVIDER_FY_CONVENTION_CONFLICT; PRIMARY_STRONG_TOKEN_SUPPRESSES_EXHIBIT | YES for material conflicts; PARTIAL for suppressing bounded acquisition before target assessment | YES with same-company actual quarter and August 15, 2026 end proof | R1 + R3 + R4; same fiscal key and false-future/financial-scope protections remain mandatory |
| MMM | MULTIPLE_COMPARATIVE_FISCAL_TOKENS; FISCAL_TOKEN_FORM_UNRECOGNIZED (primary hyphen) | YES for multiple actual periods; PARTIAL when one actual current-period clause is flattened with comparison columns | YES via the explicit current primary unit; comparative extraction remains fail-closed | R1 + R2 primary route; R5 only for an exhibit-table fallback; same fiscal key and false-future/financial-scope protections remain mandatory |
| NEE | LINK_SHAPE_NOT_RECOGNIZED; FISCAL_TOKEN_FORM_UNRECOGNIZED; PRELIMINARY_STAGE_AND_PARENT_SUBSIDIARY_SCOPE | PARTIAL for link shapes; YES for financial-stage/perimeter protection | YES for bounded discovery only; UNKNOWN for automatic qualification while the stage/scope flag remains | R8 + R2 can expose context; R1/financial-scope gate keeps qualification held; keep held; no date proximity, window extension or stage inference |
| PLAY | ISSUER_PROVIDER_FY_CONVENTION_CONFLICT; PRIMARY_STRONG_TOKEN_SUPPRESSES_EXHIBIT | YES for real conflicts; PARTIAL for a target-blind suppression rule | YES with explicit August 4, 2026 current-quarter clause | R1 + R3 + R4; same fiscal key and false-future/financial-scope protections remain mandatory |
| PVH | EVENT_WINDOW_TOO_NARROW (hypothesis only); ISSUER_PROVIDER_FY_CONVENTION_CONFLICT; FINANCIAL_TABLE_ONLY_TARGET_BINDING | YES for the bounded event/period search; NO for lexical omission alone | NO to widening the result window to the 31k/32k table; UNKNOWN for a separately designed structured-table path | R2 + R6 are insufficient; R3 cannot bind a date outside the proposed bound; keep held; no date proximity, window extension or stage inference |
| TLRY | BUSINESS_LINE_DISTRIBUTION_FALSE_VETO; unrecognized headline Q1 Fiscal form is secondary | PARTIAL: distribution-only rejection YES; business-line name veto NO | YES only when a separate actual financial-result clause proves company/quarter/end | R1 (R2 is not necessary to use its exact ended-period clause); same fiscal key and false-future/financial-scope protections remain mandatory |
| TXN | LINK_SHAPE_NOT_RECOGNIZED | PARTIAL: conservative direct-link selection YES; excluding this explicit news release is overly narrow | YES, exact Exhibit 99/news-release row plus all existing URL and count bounds | R1 + R8; same fiscal key and false-future/financial-scope protections remain mandatory |
| ZUMZ | MULTIPLE_COMPARATIVE_PERIOD_ENDS; ISSUER_PROVIDER_FY_CONVENTION_CONFLICT | YES for unresolved multiple actual periods; PARTIAL for flattening an explicit current/comparison relation | YES if explicit current reporting and comparison roles are retained; otherwise NO | R1 + R3 + R5; same fiscal key and false-future/financial-scope protections remain mandatory |

Labels here are report-only. A lexical omission is not proof that an independent financial-scope, acquisition, comparative or period guard should be removed. “YES” is a conditional specification conclusion, not implementation approval. The per-case evidence-confidence assessment is in section 3. No default reason/status enum, source hierarchy or existing reviewed-policy rule is changed.

## 5. Six issuer/provider fiscal conventions and target-aware acquisition


| Case | Issuer naming | Canonical naming | Common economic end | Can coexist safely? | Disposition |
| --- | --- | --- | --- | --- | --- |
| CURV | issuer FY2026 Q2 | canonical/provider FY2027 Q2 | 2026-08-01 | YES, with explicit event-bound end; no key change | NEEDS_TARGETED_SOURCE_ACQUISITION_CHANGE |
| DXLG | issuer FY2026 Q2 | canonical/provider FY2027 Q2 | 2026-08-01 | Human proof YES; automatic binding held at the deep-table boundary | MANUAL_REVIEW_STILL_REQUIRED |
| KR | issuer FY2026 Q2 | canonical/provider FY2027 Q2 | 2026-08-15 | YES, with explicit event-bound end; no key change | NEEDS_TARGETED_SOURCE_ACQUISITION_CHANGE |
| PLAY | issuer FY2026 Q2 | canonical/provider FY2027 Q2 | 2026-08-04 | YES, with explicit event-bound end; no key change | NEEDS_TARGETED_SOURCE_ACQUISITION_CHANGE |
| PVH | issuer FY2026 Q2 | canonical/provider FY2027 Q2 | 2026-08-02 | Human proof YES; automatic binding held at the deep-table boundary | GUARD_IS_INTENTIONAL_KEEP_HELD |
| ZUMZ | issuer FY2026 Q2 | canonical/provider FY2027 Q2 | 2026-08-01 | YES, with explicit event-bound end; no key change | NEEDS_PERIOD_MATCHING_SPEC |

The existing authority V1 contract permits exact canonical period-end evidence as an alternative to matching fiscal wording. A different issuer FY label is not itself a new canonical identity. R3 below makes that precedence explicit only when the same company and same economic quarter/end are proven; it never increments/decrements a fiscal year or ignores a genuine issuer-period conflict. Different quarter number, different explicit end, uncertain perimeter, annual/six-month substitution or two unresolved current periods remain held. The issuer’s FY label is preserved verbatim as source context.

For CURV/KR/PLAY, the primary token is 2026:Q2, which does not prove the requested FY2027 Q2 key. Current acquisition nonetheless stops at token presence. The smallest proposed R4 rule supplies only the already selected canonical target context to the eligible-parent acquisition decision: if no primary actual-result unit proves any requested target, and its only fiscal disagreement is the reviewable naming convention (no explicit different end), inspect the existing bounded same-accession result links. If an explicit wrong economic period or unsafe/unknown result event exists, fail closed; do not use a missing match as a reason to crawl. No other companies/quarters/parents, link cap, archive scope or retry policy are added.

The suggested sentence in the task is therefore accepted only with these restrictions. It is rejected as an unconditional “fiscal conflict means fetch” rule. The original three cases each have exactly one permitted link. KR and PLAY already pass the current pure context matcher on their diagnostic release: exact-period matching code does not need to be relaxed. CURV additionally needs its truncated actual sentence completed under R6. The two-link bound and evaluation of conflicting acquired evidence apply before a unique result can be proposed.

## 6. Minimal lexical forms and GE method choice

R2’s complete proposed lexical vocabulary is the following finite set of observed fiscal-order forms, inside an independently proven actual-result unit:

| Observed form (YYYY is an explicit four-digit source year) | Observed cases | Restriction |
| --- | --- | --- |
| fiscal YYYY <ordinal> quarter | AYTU | Ordinal remains Q1–Q4; no full-year-to-Q4 inference. |
| YYYY <ordinal>-quarter / YYYY <ordinal> quarter | GM; PVH source wording; AYTU title context | Normalize only the observed year/quarter order and hyphen; target-key equality or R3 proof still required. |
| <ordinal>-quarter YYYY | GE, MMM | Hyphen/space equivalence; do not borrow year from acceptance/cover date. |
| <ordinal> quarter [of] fiscal YYYY | HELE; DXLG source wording | An optional word year must not be mandatory. Fiscal convention differences do not become equality automatically. |
| Qn Fiscal YYYY | AYTU/TLRY source titles (secondary) | Equivalent lexical evidence only. TLRY already has a sufficient exact ended-period clause; this form alone is not its fix. |

Ordinals mean first/second/third/fourth; no other synonym, two-digit year, inferred year or ticker-specific dictionary is proposed. Lexical tokens alone are insufficient. AYTU, GE, GM, HELE and MMM can benefit directly within actual units; DXLG/PVH still fail target binding. Extending result_fiscal_tokens globally and assuming everything else works is **not sufficient**: the matching method must consume the same normalized token, event modality must pass, and the acquisition-side strong-token gate must not change accidentally. The first proposed implementation group should use post-acquisition recognition over existing selected inputs, preserving the original acquisition decision/outputs; any induced fetch change is an out-of-scope discrepancy, not an accepted side effect.

**GE alternatives:** the existing exhibit context [0:750] contains one 2026:Q3 token. Its date method wins, while the ended-only grammar returns no period and _new_context_method rejects. A general “try fiscal token after every failed exact date” fallback is too broad: it could override a real explicit period conflict or incidental cover/balance date. For a GE-only date-path change, R7 should recognize ending only inside an already completed reported-results clause, with the exact canonical end at/before parent acceptance, no contradictory end and the 180-day guard intact. That is smaller and safer than changing global method priority. In the recommended lexical group, GE’s separate actual primary fiscal clause can instead qualify through R2, so R7 is an optional later alternative, not a required extra patch. No method priority changes are implemented here.

## 7. Comparative, event-veto, window and link boundaries

**MMM/ZUMZ:** keep all source tokens and dates. R5 must assign roles from an explicit current reported-result declaration and its same-event comparisons, not select first/latest tokens. MMM can use its single explicit current primary fiscal clause via R2 without parsing the comparative table; a fallback to its exhibit must retain current/prior column roles. ZUMZ has an explicit current reporting sentence, prior-year sales comparison and separately headed future outlook. Two independent actual-current declarations, conflicting current ends, ambiguous table layout or contradictory same-accession documents stay held. Existing conflicting-quarter/exhibit negatives remain rejecting.

**HELE/TLRY:** R1 separates an actual reporting unit from unrelated boilerplate/business-line naming only when source structure and full modality are unambiguous. A literal case-insensitive Distribution exception or a global deletion of anticipates is rejected. HELE still needs R2’s fiscal wording; R1 alone does not resolve it. TLRY can use its explicit first-quarter ended-period sentence once the business-line veto is correctly scoped. A financial-result announcement that also contains independent outlook remains an actual result only for the already reported quarter; it cannot borrow forecast measures or periods. Preliminary/partial, monthly, guidance-only, cash/distribution-only, investor-presentation and pro-forma event units remain ineligible on the additive path. Legacy candidates are outside this new filtering boundary.

**PVH/CURV:** R6 may complete one already recognized reporting sentence within the same block, up to 256 additional normalized characters and at most 1,024 characters for that unit, while staying inside the original first 6,000-character search and stopping at the next heading. It may not truncate a modifier or cross a financial/outlook/other-event boundary to manufacture certainty. CURV needs only the clipped end of its existing sentence. PVH’s actual statement is already within 6,000, but its target date is at 31k/32k; it remains held. DXLG’s nearby cash date also fails quarter-grain proof. No whole-document date search, arbitrary window increase or automatic numeric-date/table inference is proposed.

**NEE/TXN:** R8 is discovery only. It may add a same-accession HTML/text link explicitly bound by the parent’s Exhibit 99 table row to an issuer/registrant news release describing the actual results, when the link label or exact exhibit99/ex99 filename corresponds to that row. A bare number 99, generic exhibit label, unrelated loan/investor document, PDF, issuer-site link, encoded/query URL, different accession or recursive link does not qualify. Retain original candidate links plus any newly recognized ones, deduplicate before counting, and reject the union if more than two remain. Never select two from a larger set. The downloaded document must independently pass actual-event, target, scope and conflict gates. TXN’s existing context already has a valid fiscal match; NEE still needs lexical and financial-stage/perimeter work and stays a manual-review hold.

| Case | Exact link filename | Exact parsed link label fragments | Before | Bounded discovery expectation | Clearly result evidence / remaining qualification |
| --- | --- | --- | --- | --- | --- |
| NEE | neeq32026exhibit99.htm | NextEra Energy, Inc. News Release dated  / October 21, 2026 | 0 permitted links / 0 acquired exhibits | 1 distinct direct result link; two-document bound retained | Actual reporting YES; automatic stage/scope qualification remains held |
| TXN | q32026txnex99-eredgar.htm | Registrant’s News Release | 0 permitted links / 0 acquired exhibits | 1 distinct direct result link; two-document bound retained | YES |


## 8. Eight proposed generic recognition primitives


| ID | Primitive | Exact affected cases / opportunity | Acquisition versus matching | Confidence, implementation risk and controls |
| --- | --- | --- | --- | --- |
| R1 | Modality-safe actual-event units | HELE, TLRY; mandatory safety prerequisite for every other primitive; TSLA negative | Matching/event gates; keep acquisition outputs frozen in first group | Shared additive-path result_context/unsafe_new_event surface; HIGH evidence, MEDIUM implementation risk. Must distinguish future/passive scheduling, reported event, quoted boilerplate and business-line naming; no legacy candidate removal. |
| R2 | Finite fiscal-token order/hyphen normalization | AYTU, GE, GM, HELE, MMM directly; secondary vocabulary in DXLG/PVH/TLRY | Matching only in first group; do not change acquisition suppression through shared helpers | Shared lexical/context methods; HIGH evidence, MEDIUM risk. Preserve distinct FY/end conflicts, no inferred years or annual/Q4 mapping. |
| R3 | Exact same-event period target binding and issuer/provider naming preservation | All six convention cases reviewed; CURV/KR/PLAY/ZUMZ may qualify; DXLG/PVH remain held | Matching/target validation; do not rewrite fiscal keys | Exact key/end/perimeter; HIGH human evidence, MEDIUM/HIGH implementation risk. Require declared quarter grain and explicit same-package end; no cash/balance/date-proximity proof. |
| R4 | Target-aware bounded acquisition despite an unproven strong primary token | CURV, KR, PLAY | Acquisition YES, only same selected parents/targets and original allowed links/count/window | HIGH evidence; MEDIUM risk. Request scope/target context changes require explicit bounded integration. Reject true end conflicts, unsafe parents and arbitrary exhibits. |
| R5 | Current event versus comparative/outlook roles | MMM exhibit fallback, ZUMZ; diagnostic guards for all convention cases | Matching only; no acquisition or timestamp change | HIGH evidence for exact examples, MEDIUM/HIGH risk. Preserve all evidence and unresolved current/current conflicts; never first/latest selection. |
| R6 | Finish a recognized event sentence within the existing document search | CURV; PVH investigated and explicitly not resolved | Matching only; same 6,000-character search, +256 sentence completion / 1,024 unit cap | HIGH CURV evidence, LOW/MEDIUM risk. No deep-table scan; preserve clauses/modifiers and heading boundaries. |
| R7 | Completed-result ending grammar (GE-only alternative) | GE | Matching only; parent acceptance and calendar guard unchanged | HIGH evidence, LOW/MEDIUM bounded risk. Prefer this over generic method fallback if date path is implemented; reject future-only ending contexts. |
| R8 | Explicit same-accession Exhibit 99 issuer/registrant news-release links | TXN; NEE discovery only, qualification held | Acquisition YES; unchanged two-link/text/host/accession/no-recursion constraints | HIGH link evidence, MEDIUM source risk. Bare Exhibit 99 never grants authority; count the complete union, and protect BRC >2 links. |

“Eight” counts design primitives, not eight approved changes or a single required rewrite. R7 is an alternative. A primitive has no valid acceptance expectation unless the R1/TSLA negative contract passes with it; a stand-alone token, window, link or comparative patch leaving October 2 TSLA qualifying is **rejected**. Not every primitive requires a new function or runtime enum; no such implementation decision is made in this review.

## 9. Minimal normative draft for a later implementation

The following SHALL/MUST conditions are a proposed future specification over frozen/copied inputs. They do not supersede the current contract or authorize a writer. A later implementation must document any approved change explicitly rather than presenting this draft as already deployed.
1. Keep all pre-existing legacy primary candidates and their immutable method/hash/source/acceptance identity. Apply these new recognition gates only to additive recognition paths. Preserve genuine ambiguity and all existing reviewed Policy V1/Form 6-K dispatch boundaries.

2. Require the accepted parent to be the existing mapped canonical company/CIK, form 8-K, metadata Item 2.02 and confirmed document heading, under the unchanged source hierarchy. Parent acceptance must be on/after the exact period end and no more than 180 days later. No provider date, acceptance year inference, issuer-site clock, exhibit date or manual assumption substitutes for this proof.

3. Require an unambiguous actual financial-result event unit, not simply the words results, quarter or an ended date. Bind its subject/perimeter, reported-result assertion, modality, quarter grain, fiscal token/explicit end and supporting same-package evidence. Preserve unknown financial stage or consolidated-versus-subsidiary scope as a hold; NEE is such a hold in this draft. Annual-only/Q4 or six-month-to-quarter inference is forbidden.

4. Reject additive future/passive/scheduled-only references, including will post, will be announced, will be released/reported, when we announce and the same negative meaning in an otherwise dated clause. A cited future 10-Q period cannot create a current event. Keep preliminary/partial, distribution/cash-only, monthly, investor-presentation, pro-forma and guidance-only event negatives. Do not apply a document-wide keyword exception that makes these shapes qualify.

5. For naming-only issuer/provider FY disagreement, retain the canonical natural key and original source label. Require the same company and explicitly stated economic quarter end, quarter grain and coherent parent/exhibit event. A contradictory explicit end, different current quarter, unknown table role or unresolved issuer-perimeter conflict must stay held. No numeric-year shifting or implicit canonical remapping is allowed.

6. Acquisition additions may inspect only an already eligible selected parent, current bounded target context, and its direct allowed same-accession result links. Deduplicate the full union before enforcing at most two. Preserve HTTPS host/path, textual format, no query/encoded/recursive/cross-accession rules and original date scope. If any required document fetch fails, do not qualify from an incomplete set or discard a legacy candidate.

7. Preserve every parsed/source observation and the role of comparative, outlook and current-result units. A unique result requires one target event and no unresolved competing actual-result unit/parent or material same-accession conflict. Never delete a competing candidate to satisfy uniqueness. If independent eligible parents remain, retain both and AMBIGUOUS; if context is insufficient, retain the existing unresolved hold. Rejection means rejection of automatic qualification, not erasure of evidence.

8. Use only the finite R2 forms after actual-event proof; keep the lexical interpretation consistent with the method that consumes it. Complete sentences only within R6 bounds. Do not borrow dates from cash balances, compare years by magnitude, infer numeric table columns or expand to the full document. R7 cannot override a genuine contradictory end via a weaker fiscal token.

9. Retain source provenance for any hypothetical new candidate: exact natural key, parent accession/document/acceptance/source, actual unit and period roles, raw payload and span hashes, and exact exhibit URL/hash if used. Do not invent a new runtime enum solely for report labels or let a hash stand in for semantic proof.

10. Do not mutate/reselect any established VERIFIED authority/evidence row. The frozen 13,130/13,153 cohort and 81 controls are hard preservation contracts, not re-enrichment targets. Any extra historical candidate from pure replay is diagnostic only. No refresh-existing, historical scan/drain, default Policy V1 or Form 6-K activation is authorized.

11. Require all explicit negative/regression fixtures below to pass together. In particular TSLA must have only its actual October 21 qualifying parent, ABAT/WOR/XTIA must retain their held candidate sets, and BRC must reject its >2-link set. Any proposed primitive failing that combination must be rejected rather than partially deployed.

Authority may only be considered through a separately authorized normal workflow after the implementation and exact source/candidate/financial checks pass. A hypothetical one-candidate status is not an approval or a promise of verification here. No standalone parser fix is permitted to turn an unknown financial stage, scope or event relationship into certainty.

## 10. TSLA mandatory negative control


| Parent accession | Acceptance UTC | Primary source | Primary payload SHA-256 | Mandatory future classification |
| --- | --- | --- | --- | --- |
| 0001628280-26-064366 | 2026-10-02T13:04:26Z | [tsla-20261002.htm](https://www.sec.gov/Archives/edgar/data/1318605/000162828026064366/tsla-20261002.htm) | efa537fff12b49185a5eaca399000fb9883fb22a24a0dcb44365fa3d71a56b31 | NOT_A_CURRENT_ACTUAL_RESULT_EVENT |
| 0001628280-26-066738 | 2026-10-21T20:41:42Z | [tsla-20261021.htm](https://www.sec.gov/Archives/edgar/data/1318605/000162828026066738/tsla-20261021.htm) | e9c3a1ca8c6e780411c691601ee2efe80e0def3683ae881a36fbc73f0f0e2833 | VALID_ACTUAL_RESULT_EVENT |

Control natural key `(2216, 2026, Q3)`, CIK `0001318605`, period end `2026-09-30`; it is not a positive-scope member. Current detailed replay retains exactly the two parents and AMBIGUOUS / MULTIPLE_VALID_CANDIDATES. October 2 matches only through SEC_LINKED_EXHIBIT future/disclaimer context; October 21 matches the legacy exact period end. The required future qualifying-candidate count is **1**; authority remains unmodified in this task.

| Role | Exact frozen clause / location | Source |
| --- | --- | --- |
| future_passive | “Our net income and cash flow results will be announced along with the rest of our financial performance” (`[1466:1569]`) | [exhibit991111111.htm](https://www.sec.gov/Archives/edgar/data/1318605/000162828026064366/exhibit991111111.htm) |
| future_scheduling | “Tesla will post its financial results for the third quarter of 2026” (`[538:605]`) | [exhibit991111111.htm](https://www.sec.gov/Archives/edgar/data/1318605/000162828026064366/exhibit991111111.htm) |
| non_result_scope | “Tesla vehicle deliveries and storage deployments represent only two measures of the Company’s financial performance” (`[1600:1715]`) | [exhibit991111111.htm](https://www.sec.gov/Archives/edgar/data/1318605/000162828026064366/exhibit991111111.htm) |
| referenced_period_not_event | “10-Q for the quarter ended on September 30, 2026” (`[1942:1990]`) | [exhibit991111111.htm](https://www.sec.gov/Archives/edgar/data/1318605/000162828026064366/exhibit991111111.htm) |
| actual_later | “released its financial results for the quarter ended September 30, 2026” (`[2026:2097]`) | [tsla-20261021.htm](https://www.sec.gov/Archives/edgar/data/1318605/000162828026066738/tsla-20261021.htm) |

The October 2 exhibit URL is [exhibit991111111.htm](https://www.sec.gov/Archives/edgar/data/1318605/000162828026064366/exhibit991111111.htm). Governing audit captured payload SHA-256 `ab3489cea7df455ed0af0f75f9257b4559a72b23684674d4c651452df4fb2baf`, verified and retained here. The governing October 27 result also retains an earlier source observation with hash `8abe12f6cc7c1359dcf701962761de59240e6352c91cfd1e954a9c358793585b`. Those older raw bytes are unavailable in the audit cache; their hash/method observation is preserved in the original result and frozen control record, never reconstructed or substituted. Both source identities are recorded. No fresh source hash or acceptance timestamp was written.

A valid R1 gate must recognize future modality before treating the passive verb as an actual report. Production/deliveries/storage metrics, an earnings-calendar entry and a reference to a quarter-ended 10-Q do not establish the actual financial event. The October 21 actual parent and its unchanged acceptance must survive. R2–R8 are explicitly rejected as standalone improvements if this early candidate remains qualifying under their proposed combination.

## 11. VERIFIED preservation and ambiguity contracts

The originally bound cohort is reused verbatim, not regenerated from the current latest rows:

| Frozen preservation artifact | Rows | Exact SHA-256 |
| --- | --- | --- |
| verified_regression.json | 13130 | 174ad43e6110d6eff2577bcc48a85f436726300dd179e317621b63b9becda6ad |
| verified_evidence.json | 13153 | da30778b0b9f2fdeda0c7fe2f1113f640bc03cba018368262fc356ec12f33969 |
| latest81_verified_controls.json | 81 | 9aec1d5196e932cb5b36e393df81ec533b1e837d087782baa4ac5e7aed676f09 |

The retained canonical generation file is `data/fundamentals_generations/refresh_20261028T054130Z_refresh_fundamentals_f0854217d4df_production_14d59fd7/fundamentals_v4.db`, SHA-256 `11ad0c3106a80bd8583a317f595e5d21f49a5431ec9dfc99fc4db8bb7eccd35e`. It remains available and hash-matches. The exact ordered queries and JSON serialization defining these files are in the governing audit. Protect natural key, status, selected source, UTC timestamp, selected evidence ID and retained evidence identity; no reselect, destructive migration, override or refresh-existing is permitted. Additional code-level historical candidates cannot rewrite this cohort. The 81 controls are the governing October 27 result rows originally VERIFIED, joined by natural key, including WFRD FY2026 Q3. The prior generation-local quarter_id rebindings are already documented; this review neither repeats that rebuild nor changes bindings.

| Control | Exact key | Period end | Current and required held status | Matched | Plausible | Frozen qualifying parent set | Future expectation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ABAT | (9, 2026, Q4) | 2026-06-30 | AMBIGUOUS | 2 | 2 | 0001493152-26-039500 @ 2026-08-20T21:00:28Z; 0001493152-26-042948 @ 2026-09-16T21:05:56Z | unchanged; held / no selected authority |
| WOR | (2392, 2027, Q1) | 2026-08-31 | AMBIGUOUS | 2 | 2 | 0001193125-26-397953 @ 2026-09-22T20:20:20Z; 0001193125-26-402803 @ 2026-09-25T20:01:39Z | unchanged; held / no selected authority |
| XTIA | (2430, 2026, Q2) | 2026-06-30 | AMBIGUOUS | 2 | 3 | 0001213900-26-108698 @ 2026-10-13T11:00:12Z; 0001213900-26-111088 @ 2026-10-20T21:25:15Z | unchanged; held / no selected authority |
| BRC | (358, 2026, Q4) | 2026-07-31 | UNRESOLVED | 0 | 1 | none | unchanged; held / no selected authority |

ABAT’s component/annual-Q4 scope, WOR’s release/repeat/transcript relationship and XTIA’s preliminary/completion scope remain unresolved in the default path. No first/latest, timestamp normalization or typed relation is inferred. XTIA’s third plausible Q3 parent `0001213900-26-111632` remains unmatched to its Q2 control. Existing alternate four-hour timestamp observations are retained in the governing audit/control snapshots and never treated as extra economic parents or repaired here. BRC’s three distinct result-shaped links must still yield no automatic exhibit set; R8 must count the complete union and must not select an arbitrary two.

Existing fixture bindings, inspected and compared with the unchanged pure resolver:

| Fixture / coverage | Frozen result / protection | SHA-256 |
| --- | --- | --- |
| tests/fixtures/sec_result_recognition/positive.json | 3 AVT/CPB/ORCL fixtures retain one candidate each | 6a36db5e1fcad58b479e6c9595c33af73cfa0e7db2823927c3a0e4a3a7774415 |
| tests/fixtures/sec_result_recognition/true_ambiguous.json | 22 legacy ambiguity fixtures retain both original parents, methods and acceptance boundaries | 6bd3536ffa020e55dbf27ae8811dad417c96c363ead43d4b35b2a254fc4224c6 |
| tests/fixtures/publication_event_policy_v1.json | 26 reviewed cases / 52 events remain a separate explicit Policy V1 route; no apply/evaluation authorization | 899ed0f8e5a61f7b8159632c0d5ab74640d6c8805cd69ad75fbaa9e771a54a3e |

Required negative fixture extensions for a later implementation are specifications only: active/passive future reports and future 10-Q references; true distribution/cash-only versus business-line naming; preliminary/partial (including late preliminary); annual-only Q4 and semiannual substitution; current/current conflicting quarters; primary/exhibit explicit different end; same-event FY naming differences versus genuine period/perimeter conflict; current/prior comparisons versus mixed current events; date proximity/cash balance traps; malformed or unbound table columns; non-2.02/foreign forms; unsafe/different-accession URLs; incomplete exhibit fetch; recursive and >2-link sets; retained higher-priority/VERIFIED authority. Existing tests inspected: `test_sec_result_recognition.py`, `test_result_publication_authority.py`, `test_publication_event_policy_v1.py`. No tests were edited or run with pytest; no apply_resolution/enrich_database/DB writer was called, even in a copy.

## 12. Per-case disposition and before/after specifications

“After” below is an unexecuted design expectation on the frozen evidence after the complete stated dependency set and all mandatory negatives pass. It is not a result of implemented code. Before is 0 candidates / 1 plausible / UNRESOLVED / QUARTER_MATCH_FAILED for all 14. A hypothetical unique proposal may be called VERIFIED by the pure resolver status formula; no authority is written, selected or approved by this specification. Proposed existing source hierarchy and parent acceptance stay unchanged. None of these 14 has two distinct eligible parents in its frozen input. Matched-parent AMBIGUOUS status is expected for none of the 14 before or after this draft: the three zero-candidate cases instead retain UNRESOLVED context/scope holds. Genuine added competing actual events would invalidate any unique expectation and must remain ambiguous/held.

| Case | Exactly one primary disposition | Confidence | Complete proposed dependency set | Before count / status | Hypothetical after count / status | Unique expected? | Separate review still required? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AYTU | SAFE_MINIMAL_RECOGNITION_CANDIDATE | HIGH | R1 + R2 | 0 / UNRESOLVED | 1 conditional / unique proposal | YES, hypothetical | No extra case-specific review if every draft gate and future implementation validation passes; this report is not apply authorization |
| CURV | NEEDS_TARGETED_SOURCE_ACQUISITION_CHANGE | HIGH | R1 + R3 + R4 + R6 | 0 / UNRESOLVED | 1 conditional / unique proposal | YES only after the complete bundle | Period-convention specification and acquisition/window fixtures must pass before a unique proposal |
| DXLG | MANUAL_REVIEW_STILL_REQUIRED | HIGH | R2 is insufficient; R3 stops at the table boundary | 0 / UNRESOLVED | 0 qualifying / UNRESOLVED held | NO qualifying candidate under this draft | YES: exact quarterly table/column binding remains a separate reviewed evidence task |
| GE | SAFE_MINIMAL_RECOGNITION_CANDIDATE | HIGH | R1 + R2 primary route; R1 + R7 is a smaller GE-only alternative | 0 / UNRESOLVED | 1 conditional / unique proposal | YES, hypothetical | No extra case-specific review after all unchanged guards and regression gates pass |
| GM | SAFE_MINIMAL_RECOGNITION_CANDIDATE | HIGH | R1 + R2 | 0 / UNRESOLVED | 1 conditional / unique proposal | YES, hypothetical | No extra case-specific review after exact entity/quarter scope and fixtures pass |
| HELE | SAFE_MINIMAL_RECOGNITION_CANDIDATE | HIGH | R1 + R2 (R1 alone is insufficient) | 0 / UNRESOLVED | 1 conditional / unique proposal | YES only after both primitives | No extra case-specific review after the two-primitive gate; a veto-only patch is rejected |
| KR | NEEDS_TARGETED_SOURCE_ACQUISITION_CHANGE | HIGH | R1 + R3 + R4 | 0 / UNRESOLVED | 1 conditional / unique proposal | YES, hypothetical | FY-convention and bounded fetch conditions must be specified, not a canonical relabel |
| MMM | SAFE_MINIMAL_RECOGNITION_CANDIDATE | HIGH | R1 + R2 primary route; R5 only for an exhibit-table fallback | 0 / UNRESOLVED | 1 conditional / unique proposal | YES via primary, hypothetical | No extra case-specific review for the proven primary clause; unresolved table roles may not be guessed |
| NEE | MANUAL_REVIEW_STILL_REQUIRED | MEDIUM on qualification | R8 + R2 can expose context; R1/financial-scope gate keeps qualification held | 0 / UNRESOLVED | 0 qualifying / UNRESOLVED held | NO qualifying candidate under this draft; one possible only after separate stage/scope review | YES: bind the Preliminary tables to the parent consolidated current result, not subsidiary-only or preliminary-stage inference |
| PLAY | NEEDS_TARGETED_SOURCE_ACQUISITION_CHANGE | HIGH | R1 + R3 + R4 | 0 / UNRESOLVED | 1 conditional / unique proposal | YES, hypothetical | Exact-end/FY-convention and fetch proof must pass |
| PVH | GUARD_IS_INTENTIONAL_KEEP_HELD | HIGH | R2 + R6 are insufficient; R3 cannot bind a date outside the proposed bound | 0 / UNRESOLVED | 0 qualifying / UNRESOLVED held | NO under this minimal draft | YES if a separate reviewed quarter-table evidence path is pursued |
| TLRY | SAFE_MINIMAL_RECOGNITION_CANDIDATE | HIGH | R1 (R2 is not necessary to use its exact ended-period clause) | 0 / UNRESOLVED | 1 conditional / unique proposal | YES, hypothetical | No extra case-specific review after business-line/actual-event negative fixtures pass |
| TXN | NEEDS_TARGETED_SOURCE_ACQUISITION_CHANGE | HIGH | R1 + R8 | 0 / UNRESOLVED | 1 conditional / unique proposal | YES, hypothetical | No extra case-specific semantic review after link provenance and mandatory negatives pass |
| ZUMZ | NEEDS_PERIOD_MATCHING_SPEC | HIGH | R1 + R3 + R5 | 0 / UNRESOLVED | 1 conditional / unique proposal | YES only with explicit comparison roles | Comparative-current period specification must pass; no latest/first-date preference |


| Disposition | Cases |
| --- | --- |
| SAFE_MINIMAL_RECOGNITION_CANDIDATE | 6 |
| NEEDS_TARGETED_SOURCE_ACQUISITION_CHANGE | 4 |
| NEEDS_PERIOD_MATCHING_SPEC | 1 |
| GUARD_IS_INTENTIONAL_KEEP_HELD | 1 |
| MANUAL_REVIEW_STILL_REQUIRED | 2 |
| INSUFFICIENT_EVIDENCE | 0 |
| Total | 14 |

Component-only expectations prevent overclaiming: R2 without R1 is rejected because it leaves TSLA’s early candidate qualifying. R1 alone can expose TLRY’s exact-period actual clause but does not fix HELE fiscal wording. R4 alone can expose existing exact-period matches for KR/PLAY but is not accepted without the R1 negative gate and R3 naming restrictions; it still fails CURV’s clipped period. R8 can expose TXN’s already valid context but does not complete NEE’s lexical/stage work. R6 alone does not solve PVH, DXLG or a suppressed exhibit. R5 alone is invalid if it simply discards prior/current tokens or leaves TSLA qualifying. None of the proposed combinations performs a global same-priority tie-break.

## 13. Ranked implementation groups and exactly one next phase


| Rank | Bounded implementation group | Direct case leverage | Confidence / regression risk | Acquisition impact / negative-control ease |
| --- | --- | --- | --- | --- |
| 1 | R1 modality-safe event units + R2 finite lexical recognition | 6 ready recognition candidates: AYTU, GE, GM, HELE, MMM, TLRY; TSLA required negative | High source confidence; medium shared matching risk. GE uses explicit primary fiscal path; no global fallback. MMM uses an actual primary unit, not a first/latest table token. | Keep original acquisition outputs and scope unchanged in this group. Strong, explicit passive-future, boilerplate, business-line, lexical, legacy-ambiguity controls. |
| 2 | R3 target binding + R4 bounded target-aware fetch, with R6 only for CURV | 3 acquisition cases: CURV, KR, PLAY | High exact evidence; medium source-target integration risk. Explicit end/quarter and source coherence required. | Acquisition changes for same selected parents only; test wrong ends, genuine FY conflicts, >2 links, incomplete fetch and clipping. |
| 3 | R3 + R5 current/prior comparison roles | ZUMZ; MMM exhibit fallback is optional, not an additional case | High reviewed examples; medium/high generic table/event-role risk. | No acquisition change; false first/latest or dropped current event must fail. Keep DXLG/PVH outside automatic deep-table handling. |
| 4 | R8 strict explicit news-release link shape | TXN: 1; NEE discovery only, still held | High link proof; medium acquisition risk; NEE stage/perimeter remains unresolved. | One existing direct same-accession link each; unchanged two-link cap. Bare Exhibit 99 and BRC >2 negatives mandatory. |
| 5 | R7 completed-event ending grammar (alternative) | GE: 1, if its date path still needs work after rank 1 | High evidence, low/medium narrow matching risk. | No acquisition change; pair future-only ending and explicit conflicting-end negatives. Do not combine redundantly without need. |

Primitive-level top three by opportunities are **R3 exact target/convention binding: six reviewed convention cases (two remain held)**; **R2 lexical normalization: five direct positive opportunities (AYTU, GE, GM, HELE, MMM)**; **R4 bounded target-aware acquisition: three cases (CURV, KR, PLAY)**. Opportunities overlap and are not disposition counts. Readiness and the mandatory TSLA correctness gate make rank 1 the recommended next phase even though R3 has more review opportunities.

**Exactly one recommended next implementation phase: PUBLICATION-AUTHORITY-MODALITY-SAFE-LEXICAL-RECOGNITION-1.** Implement only the R1/R2 bounded matching group for the frozen AYTU, GE, GM, HELE, MMM and TLRY inputs, with TSLA’s two-parent negative contract, the exact VERIFIED preservation set, ABAT/WOR/XTIA/BRC and existing frozen fixtures as mandatory regressions. Proposed expectation: six one-candidate opportunities; the other eight positive-scope holds remain unchanged in that first phase. Keep acquisition outputs/scope unchanged; do not add R3–R8, automatic period translation, new link shapes, table/window expansion, authority writes, reviewed overrides or Production to that phase. If a lexical/event change cannot preserve the stated boundaries, stop the affected case and retain its hold. This recommendation is not started or authorized by this review.

## 14. Verification, artifact identities and no mutation

Read-only replay ran the current resolver twice on each of 19 frozen company inputs (14 positives + five controls), obtaining identical diagnostics/candidate sets to the governing audit. Pure fixture comparisons preserved three known positives and 22 two-parent legacy ambiguity sets; the separate Policy V1 fixture remains hash-bound at 26/52. The helper also inspected existing context/period/method functions on diagnostic documents; it did not insert those documents into default acquired inputs. No proposed recognition primitive or hypothetical after-state was executed. Source-payload hashes and literal spans were verified against the cached originals. **No network requests, pytest/full suite, source/test edits, apply_resolution, enrich_database, Preview/Test/Production, drain, reviewed decision, authority/evidence writer or backup cleanup occurred.**

Original and final safety captures use the existing UI-operation/Production/scheduler kernel locks through read-open handles without changing lock contents/owner text. All runtime SQLite access is read-only; the helper’s mutable files are only under /tmp. Current generation and the original regression generation are distinguished and both are preserved. All source/test/fixture files read for this review are hash-bound, and existing unrelated worktree changes remain excluded.

| New temporary artifact (not committed) | SHA-256 |
| --- | --- |
| cases.json | a6999229ac70f93f48fcbc3fa6a01e26a13c0826e5031b0a4fc7a7fac867f35a |
| controls.json | 79263fba8c45dd40701f98302831f36efe262035d770c85818695965f2beaa4b |
| replay_inputs.json | ea7862d367419309313ed7e011f8ac349b6604007fd0acb76b4f3c21bedcf119 |
| source_manifest.json | b1b290a08130a5017f4be7ca8a03473f454729984d15d738e9e2725fd7c97b45 |
| evidence_spans.json | f293b87dd4f7d84c77ec7eff35522ecb3fb44b89995f3be3f35620595677f4ff |
| current_trace.json | f287f3c4515f515eeff4ac0607842a94560e6b74dcb36d50b12823f232784b01 |
| fixture_checks.json | 44eb4f7b80d8ffbb4dac7ed67c25a60b4d19a2048e67adc979258c03262d4645 |
| review_dispositions.json | 20ead0b56f93d7b67002cf730faba6e0e241275f76ce2b7f6e4e8dae3ca8d101 |

Final verification at `2026-10-28T07:37:14.147926+00:00`: **PASS**. All nine runtime artifact hashes and all 11 implementation/test/fixture hashes match this review’s baseline; the original regression generation still matches its bound canonical hash. All 71 source payloads and 52 exact spans verify; the 14 keys/dispositions reconcile exactly. Current-code frozen replay is deterministic for the 14 plus five controls; all 22 legacy fixture parent/acceptance identity sets are preserved. The 13,130/13,153 cohort and 81 controls are the original exact snapshots. All local links exist; unrelated worktree changes remain unchanged. No proposed algorithm, network request, pytest/full suite, workflow, authority/evidence mutation or push occurred. Detailed temporary check record: `/tmp/publication_actual_result_context_review/verification.json`.

Exact 22-fixture candidate baseline (temporary, not committed): `legacy_fixture_candidate_baseline.json`, SHA-256 `f929cc30368cf29da4ea24c0b955f4ba987051a935cc089fe2d03313105d01ec`. This records each natural key and complete current candidate payload for later non-destructive comparisons.
