# Phase 13G.3.76: Foreign / Form 6-K C8 Evidence Audit

Date: 2026-10-06 (Europe/Helsinki). Evidence research only; no Production apply.
Starting HEAD: `4cc1b3b79c4180c752ff5f068e3e37f97da91d17`.

## Executive Summary

The exact Phase 13G.3.64 `FOREIGN_6K_METADATA_ONLY` / `INSUFFICIENT_EVIDENCE` cohort contains **23 canonical quarters**. All remain `NOT_FOUND`, timestamp NULL, with zero stored publication evidence and unchanged authority update times. Of these, **21** are inside the current 60-day recent-open selection and **2** (NVMI, CLLS) are outside. Operational age does not determine evidence validity.

Fresh bounded document review found **24 exact-quarter result-bearing 6-K filings across 18 quarters**: **12 unique cases**, **6 multiple-filing cases**, and **5 wrong-period cases**. The 24 filings are not 24 independent economic publication events; repeats/statement republications require relationship review. There are no cohort-level wrong-entity, no-authoritative-event, still-insufficient-evidence, or already-resolved outcomes. Negative cases describe the observed wrong-period packages, not proof that a quarter was never published anywhere.

**Option B: a bounded Form 6-K source-authority extension is required.** Eleven unique cases require that extension. IQMX has independently exact issuer publication evidence under the existing issuer-source hierarchy, recorded as the explicit additional label `ISSUER_UNIQUE_EXISTING_AUTHORITY`; it is not an existing-authority 6-K case. Existing-authority 6-K cases: **0**. Existing-authority issuer cases: **1**. Current reviewed-plan implementation readiness: **0** for this cohort.

Nine unique SEC cases have consistent acceptance evidence. BABA and BIDU have fresh metadata/index/full-submission timestamp disagreement and no proposed timestamp. IQMX has the same SEC discrepancy, but its independent issuer timestamp is stronger evidence. Thus **10 conditional research proposals** are presently supported (9 after a 6-K extension plus 1 after an issuer handoff); **12** is only a potential ceiling if the two held timestamps are resolved. No proposal is authorized for immediate Production apply.

ADR identity checks examined **20 ADR-like cases** (provider ADR label or officially proven ADS): **11 actual ADS/ADR securities** and **9 officially ordinary/common-share securities despite provider ADR labels**. All 11 current underlying-company chains are supported; no actual ADR case has an unproven current issuer mapping or a depositary-bank SEC filer. Nine actual ADR cases have exact-quarter result evidence. IQMX's historical security start date remains a separate temporal-identity limitation.

## Current Contract

Relevant contracts: [timestamp V1](../forecasts/result_publication_timestamp_v1_implementation_2026-09-28.md), [Phase 13G.3.64 audit](fundamentals_v4_phase13g3_64_persistent_open_publication_audit.md), and the current resolver, Policy V1, and reviewed-plan implementations. No broad repository scan or resolver redesign was performed.

`rawcandle/fundamentals/result_publication.py:30` ranks exact issuer earnings release above Item 2.02 8-K acceptance, above explicitly reviewed official filing fallback. `SEC_FILING_FALLBACK` in the generic ranking/storage is not blanket permission for any foreign filing. SEC acquisition at line 192 filters to `8-K` / Item 2.02. Policy V1 at `publication_event_policy.py:120` requires `SEC_8K_ITEM_2_02`, form `8-K`, and document-confirmed Item 2.02. `admin/reviewed_publication_plan.py:85` also rejects other forms; the Policy V1 handoff is built around that source contract.

Consequently, neither an arbitrary 6-K nor a good foreign earnings exhibit can be relabeled an 8-K. This audit uses event terminology descriptively, not domestic Policy V1 authorization. No source enum, rank, schema, frozen plan, or authority state was changed. IQMX's issuer timestamp is supported by the hierarchy, but the existing reviewed SEC handoff does not safely represent that issuer-source operation; no fabricated evidence payload was passed into it.

## Cohort Construction

Input: [Phase 13G.3.64 case CSV](fundamentals_v4_phase13g3_64_persistent_open_publication_cases.csv). The cohort was derived with both `cluster_id == FOREIGN_6K_METADATA_ONLY` and `root_cause_category == INSUFFICIENT_EVIDENCE`; 23 is the resulting count, not a selection limit.

Read-only URI connections with `PRAGMA query_only=ON` read the active canonical authority, evidence, quarter, company, security, and CIK rows. Current generation: `publication_drain_20261006T150551Z_9cfd3ca0`; clean publication journal. Natural keys, timestamps, status reasons, and authority update times were compared with Phase 64. All quarters have accepted canonical identities, a single active security and CIK, and matching `SEC_CIK` company keys. The broader current recent-open population is 171, but it was not researched or processed.

The bounded publication-evidence window for each issuer was **2026-06-30 through 2026-10-06 inclusive**, capped at audit time rather than extending into the future (within the existing 180-day resolver window). Fresh submissions metadata supplied **168 filings: 163 Form 6-K, 4 Form 6-K/A, 1 Form 20-F**. Relevant recent arrays covered this window; no full-history crawl was needed. Filing indices, parents, and all listed 99.x exhibits were inspected, including eight iXBRL-wrapper exhibit links recovered through their structured `doc` URL parameter. Non-result parents did not trigger speculative unrelated-exhibit crawling.

An additional **21 latest 20-F/40-F documents** were captured solely for security/issuer identity (BHP's annual was already in the publication window; IQMX has no annual). Annual identity covers are not treated as quarter publication events. Official issuer checks were targeted at the negative cases and IQMX/CLLS, not the whole universe. Search snippets served navigation only. No historical-completeness audit, ABAT/OPTT/AMR revisit, retry drain, refresh, or scheduler job was run.

## Evidence Patterns

- Results in primary 6-K: CAMT and NVMI demonstrate that an Ex99 requirement would miss valid result packages.
- Results in Ex99.x: earnings releases coexist with financial statements, MD&A, certifications, guidance, or unrelated business announcements. VNET's CATL cooperation exhibit and IQMX's future guidance are not additional earnings candidates. PAAS and WPM have multiple documents in one accession, not multiple parent-acceptance events.
- Half-year titles are insufficient to decide quarter matching. TSEM, TSM, GDS, POET, NBIS, and CLLS have explicit three-month tables/highlights as well as interim reporting. Conversely MKDW, MLGO, HOLO, SCNI, CAN's later statements, BIDU's later interim report, and BTDR's later statements cannot supply exact-quarter net income merely through six-month totals.
- Reports furnish or incorporate result documents, but those legal verbs alone do not prove the event's period, perimeter, or completeness. Pro forma, subsidiary, dividend, ADS-ratio, production-volume, and earnings-call notices are excluded as substitute quarter-result evidence.
- GAAP, IFRS, and TIFRS reporting must retain consolidated and attributable-income perimeter distinctions. Adjusted metrics are not replacements. TSM's early provisional/Board-approval language is retained as descriptive evidence, not a new disqualification policy.

## Unique Qualifying Cases

Every SEC proposal below is **research only**, conditional on a reviewed 6-K extension. All periods end 2026-06-30; all are FY2026 Q2 except BABA FY2027 Q1. The CSV supplies exact accessions, issuer/CIK, primary/exhibit URLs, metadata and index times, original context, and SHA-256 fingerprints.

| Ticker | Result-bearing context | Research timestamp UTC | Authorization/readiness |
| --- | --- | --- | --- |
| WDH | Ex99.1, explicit Q2 consolidated GAAP income | 2026-09-08T11:30:46Z | 6-K extension required |
| CAN | Ex99.1, explicit Q2 GAAP revenue/loss | 2026-09-08T11:20:24Z | 6-K extension required |
| NEGG | Ex99.1, explicit Q2 revenue/net income | 2026-08-27T20:30:01Z | 6-K extension required |
| BABA | June-quarter consolidated results | NULL | 6-K extension + timestamp review |
| BIDU | Ex99.1, explicit Q2 GAAP attributable income | NULL | 6-K extension + timestamp review |
| VNET | Ex99.1, Q2 consolidated revenue and GAAP loss | 2026-08-18T10:16:34Z | 6-K extension required |
| IQMX | Ex99.1/99.2 and independent issuer report | 2026-08-04T05:00:00Z | Existing issuer source; reviewed issuer handoff absent |
| PAAS | Ex99.1 financials / Ex99.5 release, same accession | 2026-08-12T21:38:01Z | 6-K extension required |
| BTDR | Ex99.1, explicit Q2 revenue/net loss | 2026-08-10T11:08:07Z | 6-K extension required |
| CAMT | Primary 6-K, explicit Q2 GAAP results | 2026-08-10T11:16:13Z | 6-K extension required |
| WPM | Ex99.1 release / Ex99.3 financials | 2026-08-06T22:47:58Z | 6-K extension required |
| NVMI | Primary 6-K, explicit Q2 GAAP results | 2026-08-06T11:30:57Z | 6-K extension required; outside 60 days |

IQMX's [official issuer release](https://investors.iqm.tech/news-releases/news-release-details/iqm-quantum-computers-reports-first-earnings-public-company) explicitly gives August 4 at 08:00 EEST, independently supporting 05:00 UTC rather than the earnings-call time. Its [attached interim report](https://ml-eu.globenewswire.com/Resource/Download/4da51a85-c7d3-4032-9fe8-54e2f86ec1d5) explicitly reports Q2 revenue and IFRS loss. The download was captured; the issuer HTML was inspected through web access after the direct research downloader timed out. A search-title date is not used as authority.

### Acceptance-Time Conflict

Across all 168 inventory filings, **66 fresh metadata timestamps disagree with the index Accepted display interpreted in `America/New_York`**. The CSV preserves both rather than changing existing timestamp semantics. This includes three unique cases:

| Ticker/accession | Fresh submissions UTC | Index-derived UTC | Full-submission acceptance header |
| --- | --- | --- | --- |
| BABA / 0001104659-26-099220 | 2026-08-21T00:05:09Z | 2026-08-20T20:05:09Z | 20260820160509 |
| BIDU / 0001193125-26-355431 | 2026-08-19T00:08:11Z | 2026-08-18T20:08:11Z | 20260818160811 |
| IQMX / 0001193125-26-331538 | 2026-08-04T15:12:58Z | 2026-08-04T11:12:58Z | 20260804071258 |

The [BABA submission](https://www.sec.gov/Archives/edgar/data/1577552/000110465926099220/0001104659-26-099220.txt), [BIDU submission](https://www.sec.gov/Archives/edgar/data/1329099/000119312526355431/0001193125-26-355431.txt), and [IQMX submission](https://www.sec.gov/Archives/edgar/data/2113060/000119312526331538/0001193125-26-331538.txt) corroborate the index's local Accepted time. Phase 64 metadata also agreed with these index-derived times. This is evidence of a source inconsistency, not permission to apply a blanket four-hour correction. BABA/BIDU proposals remain NULL until a generic acceptance-authority rule is reviewed. IQMX's independent issuer proposal does not repair or override its SEC evidence.

## Unresolved / Negative Cases

**Six multiple-filing cases** remain `MULTIPLE_COMPETING_EVENTS`: TSEM, TSM, POET, GDS, NBIS, CLLS. Each has two exact-quarter result-bearing parent accessions. Same-day timing, equal values, a later financial-statement label, or provisional-versus-reviewed language does not create authorized precedence. The CSV preserves both candidates; no earliest/latest tie-breaker was invented.

CLLS illustrates why a half-year heading must not hide quarter tables: the [release](https://www.cellectis.com/en/press/cellectis-reports-financial-results-for-the-second-quarter-2026/) and separate interim statements both include Q2 results. Its later 6-K/A expressly adds XBRL without revising the financial results and is described as a supplemental repeat, not counted as a third independent event. No pre-existing candidate set or ambiguity was modified.

**Five `WRONG_PERIOD` cases**:

- MKDW: six-month group statements; acquired Landvision statements and combined pro forma figures do not establish the canonical group's Q2 result event. Official issuer site/IR attempts timed out; no authoritative Q2 release was discovered in bounded navigation.
- MLGO: six-month statements only; official site returned 502 and bounded official-domain navigation did not expose an exact-Q2 package.
- HOLO: six-month statements only; official IR release endpoint timed out, with no exact-Q2 package found through bounded official navigation.
- SCNI: H1 release and interim statements only. [Official IR](https://www.scinai.com/investorsrelations) corroborates the H1 reporting context. Technical ADS-ratio filings do not qualify as earnings.
- BHP: [official full-year release](https://www.bhp.com/news/media-centre/releases/2026/08/bhp-results-for-the-full-year-ended-30-june-2026), annual-report 6-K/20-F, and [operational review](https://www.bhp.com/news/media-centre/releases/2026/07/bhp-operational-review-for-the-year-ended-30-june-2026) establish FY results/production metrics, not exact-Q4 consolidated income. An exact annual-release time cannot be borrowed for Q4.

These findings are bounded, not exhaustive issuer-site absence proofs. No FY-minus-nine-month or H1-minus-Q1 arithmetic was used. The target canonical quarter identities were not altered to match the observed H1/FY packages.

## ADR / Depositary Identity

Required chain: traded security -> canonical underlying consolidated company -> foreign reporting issuer / CIK -> explicitly attributable exact-period results -> authorized timestamp. The bank issuing a receipt is not automatically that financial issuer. Existing provider `secfilings` provenance, canonical security/company/CIK rows, official annual security descriptions, and result-document issuer/perimeter were cross-checked. Company names that are ticker placeholders were not treated as legal-issuer proof; the existing company key and official issuer documents establish the chain.

| US security | Underlying financial reporting company | Company ID | SEC CIK | Exact-period 6-K cases |
| --- | --- | --- | --- | --- |
| WDH ADS | Waterdrop Inc. | 2541 | 0001823986 | Yes, unique |
| CAN ADS | Canaan Inc. | 2544 | 0001780652 | Yes, unique |
| SCNI ADS | Scinai Immunotherapeutics Ltd. | 1965 | 0001611747 | No, H1 only |
| BABA ADS | Alibaba Group Holding Limited | 2465 | 0001577552 | Yes, unique; time held |
| BHP ADS/ADR | BHP Group Limited | 2466 | 0000811809 | No, FY only |
| BIDU ADS | Baidu, Inc. | 2467 | 0001329099 | Yes, unique; time held |
| VNET ADS | VNET Group, Inc. | 2475 | 0001508475 | Yes, unique |
| IQMX ADS | IQM Quantum Computers Plc | 2523 | 0002113060 | Yes, unique; issuer-time proposal |
| TSM ADS | Taiwan Semiconductor Manufacturing Company Limited | 2471 | 0001046179 | Yes, competing filings |
| GDS ADS | GDS Holdings Limited | 2492 | 0001526125 | Yes, competing filings |
| CLLS ADS | Cellectis S.A. | 2506 | 0001627281 | Yes, competing filings |

The CSV provides official security-description URLs and fingerprints for every row. TSM's annual-cover footnote identifies the ADS listing despite common-share wording in the main cover table. IQMX's [combination and listing filing](https://www.sec.gov/Archives/edgar/data/2113060/000119312526292513/d61136d6k.htm) distinguishes IQM from RAAQ and BNY, expressly its depositary bank. The target Q2 statements are IQM's pre-listing consolidated operating results, not SPAC predecessor accounts. IQMX's stored security `valid_from`/provider price history predates the July 2026 IQM ADS listing: it does not prove historical ADR program validity. Current underlying attribution is supported, but historical temporal identity must remain a reviewed capability requirement.

For foreign holding/VIE structures, the matched economic perimeter is the listed issuer's consolidated reporting group, not a silently substituted operating subsidiary. No researched result filer is a depositary bank, ADR program, or unrelated subsidiary. MKDW's acquired-company/pro-forma exhibits were explicitly rejected as substitutes for group results. SCNI depositary-ratio and other technical security filings were non-result evidence.

Metrics and denominators:

- ADR-like securities inspected: **20** (19 provider-ADR labels plus officially ADS SCNI).
- Actual ADR/depositary-receipt cases audited: **11**; proven current underlying issuer mapping: **11**.
- Actual ADR cases requiring current issuer/perimeter identity review: **0**; separate IQMX historical validity limitation: **1**.
- Actual ADR cases with SEC filer other than underlying consolidated issuer: **0**.
- Actual ADR cases with qualifying exact-period 6-K result evidence: **9** (12 result-bearing filings); authorization still separate.
- Provider ADR labels contradicted by official ordinary/common-share descriptions: **9** (MKDW, MLGO, HOLO, NEGG, TSEM, NBIS, BTDR, CAMT, NVMI).
- Security-type metadata conflicts requiring review: **10**, including SCNI, officially ADS despite its provider domestic-common classification. These do not erase independently proven current issuer chains or mutate production data.

The current canonical model represents `security.company_id -> company -> company_cik`, but lacks a typed ADR/security-to-underlying edge, program/depositary attributes, time-qualified official chain witnesses, and reliable security-type semantics. Provider category alone is demonstrably insufficient. A generic future 6-K extension must require frozen, reviewed official identity-chain evidence with financial perimeter and temporal applicability, reject bank/program-only association, and return REVIEW where attribution is uncertain. It must not silently synthesize identity mappings. These are identity-capability requirements, not schema changes in this phase.

## Source-Authority Assessment

**Recommend Option B**, with a separately reviewed generic contract before implementation:

1. Explicit source/form eligibility for actual-result Form 6-K acceptance. Reuse an explicitly reviewed official fallback at its existing MEDIUM rank only if approved, or add a separately approved typed source; generic storage support alone is not eligibility. Do not grant Item 2.02/HIGH semantics by alias.
2. Freeze same-accession submissions metadata, index, parent, result exhibits, official identity chain, exact period, hashes, and observed times. Results can be in the primary document. Unrelated exhibits must not contribute false candidates.
3. Require explicit quarter-grain revenue and statutory consolidated income evidence, canonical fiscal identity, and matching issuer/perimeter. No proximity, cover-date, provider-date, arithmetic quarter inference, adjusted-income substitution, or depositary ticker association.
4. Preserve the existing stronger exact issuer-release source. SEC acceptance must not be backdated to an issuer date without independently exact, reliable issuer evidence. Review the observed metadata/index/header conflict generically; fail closed until timestamp authority is unambiguous.
5. Define foreign repeat/amendment/revised/final relationship rules explicitly, using typed evidence and witnesses rather than first/last filing. Preserve competing candidate sets until that rule is approved. XBRL-only supplements must not become new economic publication events by metadata alone.
6. Extend reviewed prepare/rehearsal/frozen apply handoff through a generic approved path, retaining natural-key allowlists, active-generation identity/state checks, journal/recovery, source hierarchy, no refetch at apply, and no network-error authority writes. Do not coerce these documents through existing domestic Policy V1.
7. Keep unresolved and ambiguous results legitimate separate outcomes. Retain the 60-day operational horizon and its bounded retry contract; evidence outside it can support later manual reviewed work without widening normal refresh.

No 6-K copy simulation was forced through an unsupported source gate. The appropriate output is `REQUIRES_SOURCE_POLICY_EXTENSION`. IQMX received contract-level issuer evidence review only, not a fictitious production-compatible plan.

## Expected Impact

Evidence completeness: 18 exact-quarter cases, of which 12 have one parent filing and 6 have two. Policy authorization: 0 authorized 6-K cases today; 1 issuer-source case in the accepted hierarchy. Implementation readiness: 0 currently supported reviewed applies.

After a bounded extension and safety validation, **9 unique SEC cases** are immediately plausible proposals without a timestamp conflict. An independent approved issuer handoff could add **IQMX**, for **10 conditional safely resolvable proposals**. BABA/BIDU raise the unique ceiling to **12** only after their timing conflicts are reviewed. The six multiple-filing cases require additional generic relationship decisions; none is counted as safely unique. Five wrong-period cases require different evidence, not relaxed period identity. These counts are not a promise of production VERIFIED transitions.

## Recommended Next Phase

**Implement bounded Form 6-K result-publication authority**, preceded by review of its explicit source/rank, acceptance-time, identity-chain, and duplicate/amendment semantics. Include a reviewed issuer-source handoff separately where the existing hierarchy already applies. Prove the generic contract on frozen copies and exact allowlists before any live application. Do not implement a ticker exception, broaden Policy V1 implicitly, alter Production identity, or expand the retry horizon.

## Validation / Production Safety

Only temporary research helpers and downloaded evidence under `/tmp` were used. No repository source edits, production SQL writes, plans, backups, live workflows, or full test suite. Read-only assertions verified exact cohort keys, current state parity, 23 CSV rows, 24 exact-period filings, 12 unique / 6 multiple / 5 wrong-period outcomes, 21 inside / 2 outside, 11 actual ADR cases, and 9 actual ADR exact-period cases. All 140 captured document references in the CSV passed SHA-256 verification. Local report links passed existence checks. The CSV preserves all 168 reviewed accession/form/acceptance/primary-document inventory records; outcome `candidate_count` is descriptive research count, not production resolver output. Event class describes the observed publication (including H1/FY results); exact-quarter eligibility is recorded separately. `CSV_CONSISTENCY_PASS`, `LOCAL_REPORT_LINKS_PASS`, `NO_CHANGE_PASS`, and `git diff --check` passed. Only the two docs are staged for the commit.

Pre/post byte fingerprints and full cohort-state equality verify that provider, canonical, analysis, active pointer, journal, Review Queue, scheduler configuration, resolver, policy, and reviewed-plan source remain unchanged. The pre-existing dirty journal and untracked research/data artifacts were not reverted or committed. Fingerprints for the active generation boundary:

| Role | SHA-256 |
| --- | --- |
| provider | `2b3a57add8b51413d98f220d4cdd313994d1a4079f987a94796bf6a2b6db5fbb` |
| canonical | `ed5f37239dcde7b012e9ba4aaaa9e00c0ad5ba91e98d23a5c1fd32525170a65d` |
| analysis | `a8dcc37e1a0e2442dd44023b63d8c6ba91ee5fdce3ab05e2fa5407413a0355ce` |
| active pointer | `318bee77209f7bb407f2490af47f8272b8f261de8f4ad9dbb564ace37c697831` |
| journal | `a545931defe2fef59d8472a951ed4c64a90729bf37a3030b5c0fc34c2aae78be` |
| Review Queue | `14f4fd5a9e98c49ec55f6e36cc1c78b7ac290a2c1d789dbf5074b70d755b393f` |
| scheduler config | `3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894` |

Deliverables: this report and [the compact 23-case CSV](fundamentals_v4_phase13g3_76_foreign_6k_c8_cases.csv). No raw SEC HTML, runtime artifacts, DBs, or unrelated changes are included in the commit. Nothing is pushed.
