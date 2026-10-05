# Phase 13G.3.64: Persistent-Open Publication Audit

Date: 2026-10-05. Audit only; no publication decisions or production writes.

## Executive Summary

The exact accepted recent-open cohort is unchanged: **278 cases: 53 UNRESOLVED, 199 NOT_FOUND, 26 AMBIGUOUS**, across 276 companies. Inspection used current durable authority/evidence rows, the actual production-drain diagnostics, and bounded SEC metadata/document reads for these cases only.

**94 cases (33.81%) have likely resolver coverage gaps**, **22 (7.91%) remain genuinely ambiguous under the current authority contract**, and **162 (58.27%) have insufficient evidence for a stronger primary classification**. Each case has exactly one primary category, priority, evidence summary and next action in the [278-row CSV](fundamentals_v4_phase13g3_64_persistent_open_publication_cases.csv).

The highest-payoff confirmed patterns are missing exhibit quarter context (49), overly strict Item 2.02 heading recognition (39), non-result/repeated-event context accepted as candidates (4), reversed fiscal wording (1), and unsupported 8-K/A results evidence (1). These are opportunities for future engineering, not permission to assign timestamps now. Recognition improvements may produce additional conflicts rather than VERIFIED outcomes.

**No case was confidently classified as genuine global publication absence.** This is not a claim that all 162 uncertain cases have a publication. Metadata-only inspection cannot establish that no official issuer release exists. Accordingly, the expected/no-authoritative-publication count is **0 proven, actual count unknown**, not 199. No blocking fiscal-link mismatch, identity-mapping gap, upstream-history anomaly or stale-resolved state was proven. Zero in those categories is a finding bounded by the inspected evidence, not a completeness guarantee.

## Current Population

Audit starting HEAD: `1f04b22d94f4dc61329fa8fe99a3b83cc85f26a5`.
Active generation: `publication_drain_20261005T064921Z_43a1e040`.
Drain diagnostics: `fundamental_reports/publication_drains/publication_drain_20261005T064921Z_43a1e040/result.json`.

Exact selector: `select_candidate_scope(active_canonical, [], as_of_date='2026-10-05', retry_days=60, retry_max_quarters=None)`, used for enumeration only, never enrichment. The audit deliberately enumerates the entire cohort; this does not change the normal production cap of 100.

- Recent context is `max(coalesce(first_public_result_date,''), coalesce(source_availability_date,''))` between **2026-08-06 and 2026-10-05 inclusive**.
- Included authority states: missing authority, UNRESOLVED, NOT_FOUND, AMBIGUOUS. The actual cohort has no missing-authority rows and excludes VERIFIED rows.
- The selector does not itself filter CIK eligibility. The downstream resolver requires a unique active CIK; security is a left join there. Selector ordering is missing authority, UNRESOLVED, NOT_FOUND, AMBIGUOUS, newest source context first, then stable company/fiscal identity.
- Natural identity is `(company_id, fiscal_year, fiscal_quarter)`. All 278 authority quarter IDs equal their current canonical quarter IDs; all canonical identities are ACCEPTED and have one active CIK.
- All 278 canonical publication timestamps remain NULL. 252 have no stored evidence rows; 26 have two each, totaling 52. No issuer evidence is stored for this cohort.
- Sorted `company_id:fiscal_year:fiscal_quarter:status` lines, joined by LF without a terminal LF, SHA-256: `18d9bde0bb5bde1c332de3f5d03279002c9c11d041adef403c9c80f8618e1179`.

The scope dates are provider/canonical context, **not publication authority**. For example, PSQL's December 31, 2025 quarter is selected because its provider context is August 28, 2026. This is not automatically a fiscal defect or authority date.

## Contracts Reviewed

Inspection was restricted to the current publication implementation (`rawcandle/fundamentals/result_publication.py`), candidate selector, active-generation binding, publication table schema, actual drain report, and relevant documentation:

- [Publication authority V1](../forecasts/result_publication_timestamp_v1_implementation_2026-09-28.md).
- [Accepted production backlog drain](../forecasts/result_publication_backlog_drain_production_2026-10-05.md).

Authority remains issuer exact reliable release timestamp, SEC Item 2.02 8-K acceptance, explicitly reviewed official fallback, otherwise NULL. Yahoo remains secondary. V1 automatically acquires only Item 2.02 **8-K primary documents**; it does not automatically acquire issuer releases, earnings exhibits or 6-K results. An unsupported source shape is not automatically a bug or permission to expand authority.

The concrete implementation conflicts are recognition/context gaps: metadata Item 2.02 still requires a literal heading regex, primary-only text loses the result-period context, and whole-document date matching can accept cover dates or pro forma references. This audit proves reproductions but does not repair them.

## Evidence Method And Limitations

1. Read the active canonical database with SQLite `mode=ro` and `query_only=ON`. Capture existing identity/provenance, authority, evidence and production-drain diagnostics before external reads.
2. For non-AMBIGUOUS cases, inspect SEC submissions metadata only within canonical period end through `min(period end + 180 days, 2026-10-05)`. Relevant archived metadata chunks are read only when that window intersects. Form inventory is 8-K/A, 6-K/A, 10-Q/A, 10-K/A, 20-F and 40-F, plus their ordinary forms.
3. Read existing ambiguous candidate URLs and relevant Item 2.02 primary documents. Follow up to two recognizable linked earnings/exhibit URLs per primary document. No all-company issuer crawl, production resolver retry or authority writer was invoked.
4. Compare downloaded text with current pure recognition/matching functions. Store URLs and SHA-256 of downloaded HTML in the CSV, never raw documents. External text matches are audit observations, not inserted evidence or authoritative timestamps.

The external helper used the existing SEC client's HTTP read primitives only. No `enrich_database` or `apply_resolution` call occurred. Raw temporary metadata/text and helpers are outside the repository and are not committed. Issuer searches are **not exhaustive**. In particular, a 6-K metadata row without document-content verification remains C8, not C1 or a proven C2.

The authority schema does not record first-seen or a cumulative retry count. CSV `first_seen` and `retry_count` are therefore `NOT_RECORDED`. `confirmed_drain_attempts=1` is a lower bound from drain membership, not a fabricated lifetime counter. `last_seen` and `latest_retry_result_timestamp` are the durable authority `updated_at_utc` proxy. Evidence observation/fetch timestamps are NULL for the stored SEC candidates; evidence creation timestamps are recorded separately and are not substituted for observation time. External request timestamps were not individually recorded; the CSV records audit start and explicitly marks per-request observation time unavailable.

CSV SEC candidate metadata is a bounded inventory, not a claim that every filing is a publication. Up to 12 relevant metadata candidates per row are listed with an explicit omitted count; both durable ambiguity candidates are always listed in full with form, acceptance timestamp, accession and matching method. `candidate_count` is the production drain's matched candidate count, distinct from external metadata counts and audit text matches. `fiscal_link_state` describes the accepted canonical/authority relationship; forecast-link tables are explicitly NOT_AUDITED because they are outside this result-publication cohort.

## Root-Cause Distribution

| Root cause | Cases | % of 278 | Priority | Future code likely? |
| --- | ---: | ---: | --- | --- |
| C1 NO_AUTHORITATIVE_PUBLICATION_FOUND | 0 | 0.00 | P3 if later proven | Not established |
| C2 RESOLVER_COVERAGE_GAP | 94 | 33.81 | P1 | Yes; copy validation first |
| C3 FISCAL_LINK_MISMATCH | 0 | 0.00 | P1 if proven | Not established |
| C4 IDENTITY_MAPPING_GAP | 0 | 0.00 | P1 if proven | Not established |
| C5 TRUE_AMBIGUOUS_PUBLICATION | 22 | 7.91 | P2 | Only after explicit event-policy review |
| C6 PROVIDER_OR_SOURCE_HISTORY_ANOMALY | 0 | 0.00 | P2 if proven | Not established |
| C7 STALE_OPEN_STATE / ALREADY_EFFECTIVELY_RESOLVED | 0 | 0.00 | P0 if proven | Not established |
| C8 INSUFFICIENT_EVIDENCE | 162 | 58.27 | P2 | Research required before choosing a fix |

Percentages are independently rounded. No P0 defect assigning incorrect persisted timestamps was demonstrated: affected rows remain NULL. Event-context false positives are nevertheless correctness risks to include in future negative fixtures. No uncertain case is assigned P3/no-action on the unsupported assumption that publication is absent.

## Status Breakdown

### UNRESOLVED: 53

All 53 drain diagnostics are `QUARTER_MATCH_FAILED`. **50 likely coverage gaps**: 49 have recognizable quarter context in an official linked results exhibit but not the primary document; AYTU's primary document itself explicitly announces its fiscal 2026 fourth quarter, but year-before-quarter wording is not recognized. **3 insufficient-evidence cases**: ASPI, PAA and PAGP. ASPI's shareholder letter anticipates an announcement; PAA/PAGP's inspected plausible filings concern pro forma information. None should receive authority merely because a text matcher can find a quarter token.

Fiscal offsets alone are not the demonstrated cause: exact canonical period ends match 48 of the 49 exhibit cases; SPWR matches explicit fiscal-quarter context in a preliminary Q2 results release. SPWR still needs preliminary-event eligibility review before any future authority assignment.

### NOT_FOUND: 199

All 199 drain diagnostics are `NO_ITEM_2_02_FOUND`. **40 likely coverage gaps**: 39 quarter-specific result filings rejected by literal heading recognition, and XRAY's quarter-specific 8-K/A rejected by the form filter. The heading defects include dashes, fragmented words, singular Operation/Result and other nonliteral heading structures. These are false absence signals, not missing public evidence.

**159 remain insufficiently evidenced**: 134 domestic/other metadata-only cases across 132 tickers, 23 with 6-K metadata whose publication content was not verified, WKSP's monthly-metrics amendment, and PSQL's old-period/recent-source-context case. Genuine evidence absence is **0 proven / unknown among these 159**. Absence of recognized Item 2.02 is not absence of an official issuer publication, foreign result filing or another reviewed fallback.

### AMBIGUOUS: 26

All 26 drain diagnostics are `MULTIPLE_VALID_CANDIDATES`; durable authority reason is `SAME_PRIORITY_AUTHORITATIVE_EVIDENCE_CONFLICT`. Every case has **two different 8-K accessions**, not duplicate evidence rows. No original/8-K/A candidate pair was found in this stored ambiguous set.

**22 are true current-contract ambiguities**: preliminary/partial/cash/operating disclosures versus later result releases, subsidiary/parent disclosure overlap, or initial versus later revised results. The CSV records each pair's exact SEC form, UTC acceptance, accession, URLs, hashes and ambiguity dimension. It also states why no earliest/latest preference can safely be applied under existing rules. These are not claims that adjudication is forever impossible; the missing event-eligibility policy requires explicit review.

**4 likely context/eligibility gaps**: MOVE (pro forma merger information versus actual results), CF (same-results presentation versus release), DMLP (distribution/cash receipts versus earnings release), and KLXE (investor presentation whose cover date equals quarter end versus actual results). Do not automatically resolve even these four: future event-scoped matching needs negative fixtures and an approved interpretation of publication eligibility.

## High-Leverage Clusters

| Rank / cluster | Cases | Tickers | Dominant status | Primary category | Future remediation / payoff |
| --- | ---: | ---: | --- | --- | --- |
| 1 EXHIBIT_QUARTER_CONTEXT | 49 | 49 | UNRESOLVED | C2 | Read bounded earnings exhibit context tied to its parent filing; 49 recognition opportunities |
| 2 ITEM202_HEADING_VARIANTS | 39 | 39 | NOT_FOUND | C2 | Normalize/recognize real Item 2.02 headings without accepting arbitrary body mentions; 39 recognition opportunities |
| 3 NON_RESULT_OR_REPEATED_EVENT_CONTEXT | 4 | 4 | AMBIGUOUS | C2 | Event-scoped context, cover-date exclusion, pro forma/presentation/distribution policy; reduce spurious candidate sets |
| 4 FISCAL_WORD_ORDER | 1 | 1 | UNRESOLVED | C2 | Recognize AYTU year-before-quarter wording; exact fiscal identity guard |
| 5 ITEM202_AMENDMENT | 1 | 1 | NOT_FOUND | C2 | Explicit original/amendment event treatment for XRAY; never silently widen authority |
| PARTIAL_PRELIMINARY_REVISION_VS_RESULTS | 22 | 22 | AMBIGUOUS | C5 | Policy/operator review, not automatic first/last selection |
| DOMESTIC_OR_OTHER_METADATA_ONLY | 134 | 132 | NOT_FOUND | C8 | Target actual issuer/SEC publication documents before estimating code payoff |
| FOREIGN_6K_METADATA_ONLY | 23 | 23 | NOT_FOUND | C8 | Verify quarter-specific official 6-K/exhibits; only then propose reviewed fallback coverage |
| UNRESOLVED_NON_RESULT_CONTEXT | 3 | 3 | UNRESOLVED | C8 | ASPI/PAA/PAGP actual-result evidence search |
| MONTHLY_METRICS_AMENDMENT | 1 | 1 | NOT_FOUND | C8 | WKSP monthly-versus-quarter event review |
| OLD_PERIOD_RECENT_CONTEXT | 1 | 1 | NOT_FOUND | C8 | PSQL reporting history and scope/acceptance-window research |

The first two fixes address **88 recognition opportunities (31.65% of the cohort)**. All five C2 clusters total 94, but no number here is a guaranteed VERIFIED payoff: candidate eligibility, exact period identity and conflicts must still pass existing rules.

## Representative Cases

- **AVT, FY2026 Q4**: [primary 8-K](https://www.sec.gov/Archives/edgar/data/8858/000000885826000066/avt-20260805x8k.htm) refers to an earnings release without matching period context; [official exhibit](https://www.sec.gov/Archives/edgar/data/8858/000000885826000066/avt-20260805xex99d1.htm) matches June 27, 2026. This changes the explanation from unspecified unresolved to exhibit coverage gap, not authority state.
- **CPB, FY2026 Q4**: [primary 8-K](https://www.sec.gov/Archives/edgar/data/16732/000001673226000020/cpb-20260903.htm) has a dash between the item number and results heading. Its August 2 period context matches while the Item 2.02 predicate rejects. **ORCL** similarly has HTML text fragmentation in the [results heading](https://www.sec.gov/Archives/edgar/data/1341439/000119312526387905/orcl-20260910.htm). Both are concrete false NOT_FOUND reproductions.
- **AYTU, FY2026 Q4**: [primary 8-K](https://www.sec.gov/Archives/edgar/data/1385818/000143774926030900/aytu20260502_8k.htm) explicitly identifies fiscal year before the quarter wording. Current matching rejects it. No fiscal identity repair is justified by this evidence.
- **XRAY, FY2026 Q2**: [8-K/A](https://www.sec.gov/Archives/edgar/data/818479/000081847926000263/xray-20260806.htm) and [earnings exhibit](https://www.sec.gov/Archives/edgar/data/818479/000081847926000263/dentsply8kq22026ex991.htm) identify June 30 results. The amendment's August 7 acceptance is not automatically interchangeable with the August 6 release or an original filing; future policy must review that difference.
- **APA, FY2026 Q2**: [July 8 supplemental disclosure](https://www.sec.gov/Archives/edgar/data/1841666/000184166626000045/apa8k-20260708.htm), accession `0001841666-26-000045`, acceptance `2026-07-08T21:07:26Z`, versus [August 5 result disclosure](https://www.sec.gov/Archives/edgar/data/1841666/000184166626000050/apa8k-20260805.htm), accession `0001841666-26-000050`, acceptance `2026-08-05T20:33:08Z`. Both 8-K candidates are durable and same priority. Current rules cannot safely prefer supplemental or complete-result timing without an explicit definition of an eligible result event.
- **KLXE, FY2026 Q2**: [June 30 presentation filing](https://www.sec.gov/Archives/edgar/data/1738827/000173882726000025/klxe-20260630.htm) matches quarter end through its cover date, whereas [August 10 filing](https://www.sec.gov/Archives/edgar/data/1738827/000173882726000028/klxe-20260810.htm) explicitly announces results. This is a whole-document context weakness, not duplicate evidence.
- **MOVE, FY2026 Q2**: [actual result filing](https://www.sec.gov/Archives/edgar/data/1734750/000121390026090115/ea0302004-8k_corvex.htm) versus [later merger pro forma filing](https://www.sec.gov/Archives/edgar/data/1734750/000121390026097690/ea0304515-8k_corvex.htm). The latter explicitly distinguishes its assumptions from actual consolidated results. A name/reverse-merger transition exists, but same-CIK event context, not a proven broken identity mapping, is the primary finding.
- **ASPI, FY2026 Q2**: [shareholder letter](https://www.sec.gov/Archives/edgar/data/1921865/000119312526331596/aspi-ex99_1.htm) anticipates a result announcement. The audit text matcher recognizes fiscal wording, but that is insufficient proof of publication. Retain C8 and NULL.
- **WKSP, FY2026 Q2**: [8-K/A](https://www.sec.gov/Archives/edgar/data/1096275/000149315226035028/form8-ka.htm) adds Item 2.02 for preliminary April-June monthly performance. This is not enough to establish full-quarter publication authority; C8 rather than automatic amendment coverage classification.
- **PSQL, FY2025 Q4**: [SEC metadata](https://data.sec.gov/submissions/CIK0002119292.json) does not establish an eligible publication inside the 180-day window. Recent provider dates cannot extend the acceptance window or prove a provider defect; C8.

For zero-count C1/C3/C4/C6/C7 categories, no representative proven case exists. TALK has no active security but retains provider identity, and LLYVA has two active share classes with one CIK. Neither fact alone blocks the existing company/CIK resolver or proves C4. Their identity flags remain in the CSV for later targeted research.

## Recommended Next Phases

1. **13G.3.65 proposal: bounded exhibit context and robust Item 2.02 recognition.** Highest evidenced payoff: 88 opportunities. Freeze positive fixtures plus negatives for guidance-only statements, anticipated releases, cover dates, pro forma references and preliminary/partial disclosures. Keep authority hierarchy, SEC acceptance semantics and conflict handling unchanged. Validate on copies before requesting a controlled production operation.
2. **Publication-event eligibility audit/policy proposal.** Review the 22 materially plausible pairs and four context gaps before considering any ranking logic. Define what preliminary, partial, subsidiary, repeated presentation and revised-result disclosures mean. Never introduce earliest/latest selection implicitly.
3. **Targeted evidence completion for C8.** Prioritize 23 foreign/6-K metadata cases and clearly identified issuer releases; then the 134 domestic/other cases. Treat 6-K as an explicitly reviewed official fallback proposal only after document-level proof. Measure proven coverage and absence separately.
4. **Small fiscal-language/amendment improvements.** AYTU and XRAY have one-case recognition opportunities; WKSP requires monthly-event review first. Research PSQL's unusual period/context gap and TALK/LLYVA identity flags without asserting an existing mapping defect.

No follow-up phase is implemented or authorized to write production by this report. Blind retry of the same 278 is not recommended. Proven absence may later justify P3/no action while preserving NULL; the current audit cannot identify such cases confidently.

## Validation And No-Change Confirmation

- Exact selector reproduction: 278, 53/199/26; CSV 278 unique natural keys with exactly one category each.
- Read-only pure-function assertions checked 49 exhibit-context cases and 43 rejected Item 2.02 primary documents across the 40 coverage-gap cases; the extra documents include multiple filings, not extra cases.
- Seven focused temporary unittest reproductions passed: CPB dash, ORCL fragmentation, AVT exhibit, AYTU word order, XRAY amendment, KLXE cover date, ASPI preannouncement. These tests demonstrate current behavior, not fixes. No source helper is retained in the repository.
- `git diff --check`; no full test suite.
- Before/after SHA-256 unchanged for active provider, canonical and analysis databases, active-generation pointer, Review Queue database, scheduler configuration and publication journal. Canonical fingerprint: `6fb73fe67e9d28407012ebb76e9b57951e409898b817a4eca94e58d934d4b5c2`.
- Publication authority, resolver, retry logic/counters/cap/horizon, publication statuses/timestamps, identity/fiscal links, canonical financial data, active generation, Review Queue and scheduler configuration: **unchanged**.
- Production drain/retries, live Refresh and scheduler: **not executed**. No backups deleted; forecasts database untouched.
- Only this report and the CSV are committed. Existing dirty runtime state is preserved. Nothing pushed.
