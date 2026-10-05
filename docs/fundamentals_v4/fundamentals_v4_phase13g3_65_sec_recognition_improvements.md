# Phase 13G.3.65: Bounded SEC Recognition Improvements

Date: 2026-10-05. Implementation and pure copy-equivalent simulation only.
Starting HEAD: `8b6240730e31294c174ee59664c8831090906a19`.
Active generation unchanged: `publication_drain_20261005T064921Z_43a1e040`.

## Scope And Authority

Design evidence is the [13G.3.64 audit](fundamentals_v4_phase13g3_64_persistent_open_publication_audit.md) and its exact 278-row cohort. The approved clarification restricts this change to **additive heading/exhibit recognition**, not publication-event policy.

Linked SEC exhibits provide bounded fiscal/result context only. The authoritative publication timestamp remains the eligible parent Item 2.02 8-K SEC acceptance timestamp.

Recognition improvement does not imply automatic verification; existing candidate conflict and ambiguity rules remain authoritative.

SEC acceptance semantics unchanged. Authority hierarchy unchanged. No issuer acquisition, 6-K or 8-K/A authority, timestamp preference, fiscal-identity remapping, publication status-machine change, or candidate filtering was introduced.

`filing_text`, `is_item_2_02` and `match_quarter_context` retain their pre-phase semantics. Legacy primary matches run first and bypass all new event-safety filters. Their evidence hashes are unchanged. In particular, existing preliminary/partial candidates and even accepted cover-date/non-result shapes are **not retroactively rejected**. This is intentional compatibility, not an endorsement of those shapes. A separate publication-event eligibility phase is required to change them.

## Recognition Implementation

`sec_result_context.py` adds deterministic HTML block extraction. Inline text fragments are joined without inserting spaces into split words; paragraph/table-row boundaries are retained. The new Item 2.02 matcher requires the heading at a block start and recognizable results/operations wording. It tolerates whitespace, Unicode dashes, punctuation, singular/plural wording, the audited "Results of Financial Operations" variant, and the audited combined Items 2.02/7.01 heading. Unrelated Item numbers and narrative mentions do not open this new path. An unchanged literal legacy body match is still governed by legacy semantics.

Only metadata-confirmed 8-K Item 2.02 parents enter acquisition. When the recognized section lacks strong period/fiscal context, inspect at most **two** directly linked result/exhibit shapes under the exact parent SEC CIK/accession directory. Links are deduplicated and restricted to HTTPS `www.sec.gov`, a recognized results/earnings/press-release/99.1/99.2 shape and a text/HTML document. Cross-accession, issuer-site, query, encoded-path, unrelated and recursive traversal is excluded. More than two plausible links is rejected rather than selecting an arbitrary subset. HTTP caching and the existing request pacing/retry/deadline remain in use.

The new paths require an actual reported/announced/released result event with strong fiscal or ended-period context. A date somewhere in the document is insufficient. Event gates apply to the lead and the matched event window. Preliminary/partial, anticipated releases, guidance-only, pro forma, investor-presentation, distribution/cash-receipt and monthly-metric shapes cannot gain a candidate through these additions. Parent/exhibit fiscal conflicts and multiple conflicting result contexts do not yield a selected candidate; they remain open under existing resolver semantics. No extra authority writer or ambiguity-resolution preference was added.

Optional exhibit request failure clears the incomplete context set without discarding a legacy primary candidate. Acquisition records `result_context_exhibits_fetched` and `result_context_exhibit_failures` separately. This phase adds bounded reads, not a new network concurrency policy.

## Provenance

No schema migration. Parent accession, document, source reference and acceptance timestamp keep their existing evidence fields. New heading methods use `NORMALIZED_ITEM_2_02_HEADING:`. Exhibit methods use `SEC_LINKED_EXHIBIT:` followed by versioned canonical JSON in the existing `matching_method` column: parent accession, matched company/fiscal identity, exhibit URL, UTF-8 HTML-content SHA-256 and context match method. Existing evidence fingerprinting includes this value. No raw HTML enters production evidence. `SOURCE_RANK`, rule version and `apply_resolution` are unchanged.

## Focused Validation

Final focused run:

```text
venv/bin/python -m pytest -q tests/test_sec_result_recognition.py tests/test_result_publication_authority.py
61 passed in 8.90s
```

This includes 49 new focused cases and 12 existing authority/resolver regressions. Compact AVT/CPB/ORCL audit excerpts are frozen with reconstructed HTML formatting and exact SEC acceptance/accession references; fixtures require no network. The 22 true ambiguity cases have 44 compact extracted primary excerpts, original document hashes and exact parent identities. Every previous candidate is retained, and repeated resolution in an in-memory SQLite database remains AMBIGUOUS for all 22 cases.

All 12 requested negative shapes are covered, with both preliminary and partial disclosures, a late preliminary event, parent eligibility, same-accession restrictions, deduplication, link-count bounds, nonrecursive traversal and optional fetch-failure regressions. Cover dates, unrelated exhibits and conflicting exhibits never create a unique new candidate. Parent acceptance remains the timestamp in every positive fixture. Existing source precedence, same-priority conflicts, PIT and VERIFIED restart behavior pass.

Initial fixture corrections were limited to heading block termination and the in-memory test connection's `sqlite3.Row` setup. No targeted failure justified running the full suite; **full suite not run**.

## Exact Cohort Impact

Pure replay helper: `analysis/research/publication_recognition_20261005.py`. It loads the fixed audit inputs, executes the actual pre-phase module from starting HEAD in memory, and compares it with current acquisition/resolution using identical cached HTML and metadata. No `enrich_database`, production `apply_resolution`, drain, retry, Refresh or scheduler was invoked. Unit-test `apply_resolution` runs only in temporary/in-memory databases.

One bounded, read-only SEC acquisition downloaded 302 distinct documents to `/tmp` using the already granted network access: audited parent candidates and at most two same-accession linked documents per parent. No new company universe, historical scan or issuer crawl. 284 audit document observations with available cached content had their SHA-256 checked against the original audit; all matched. Remaining added documents were directly linked within the same reviewed bound. Raw cache, temporary audit inputs and detailed runtime JSON are not committed.

Scope: 53 UNRESOLVED, 199 NOT_FOUND, 26 AMBIGUOUS; **278 total**, fingerprint:
`18d9bde0bb5bde1c332de3f5d03279002c9c11d041adef403c9c80f8618e1179`.

| Recognition Cluster | Audited | Uniquely Resolvable | Newly Ambiguous | Unchanged |
| --- | ---: | ---: | ---: | ---: |
| EXHIBIT_QUARTER_CONTEXT | 49 | 28 | 0 | 21 |
| ITEM202_HEADING_VARIANTS | 39 | 32 | 0 | 7 |
| Total Target Opportunities | 88 | 60 | 0 | 28 |

These are **candidate-resolution opportunities, not production VERIFIED rows**. Each of the 49 and 39 cases, and every other cohort identity, is individually accounted for in the [278-row impact CSV](fundamentals_v4_phase13g3_65_sec_recognition_impact.csv), including old/new accessions, candidate counts, outcome, coverage note and new context provenance.

Unchanged opportunities include explicit preliminary/partial context; no permitted direct exhibit link; result descriptions outside the narrow actual-event/period window; unsupported event wording; and comparative or conflicting period/fiscal tokens for which this conservative path refuses to select context. Some are likely genuine full-result releases. Leaving them open is preferable to inventing a period or weakening the reviewed bound. "Unchanged" is not evidence of global publication absence.

All **162 INSUFFICIENT_EVIDENCE/C8 cases** have unchanged candidate sets: unexpected movement **0**. PSIX specifically remains excluded: its narrative mentions Item 2.02, but the actual section heading is Item 7.01; SEC metadata alone does not supply publication authority.

All **22 TRUE_AMBIGUOUS_PUBLICATION cases** retain both original parent candidates and distinct timestamps. Lost candidates **0**; silently collapsed ambiguities **0**. The four other existing ambiguous cases (MOVE, CF, DMLP, KLXE) also remain ambiguous; their legacy false-positive/event-policy issues were not repaired by removing candidates. AYTU word order and XRAY amendment handling remain unchanged/deferred. No ticker special cases were introduced.

Across all 278 cases, each baseline candidate set and each baseline immutable evidence-hash set is a subset of the new set. Pure resolution yields 60 unique opportunities, 26 retained ambiguous cases and 192 cases without a new candidate. It does not write these outcomes to any authority table.

## Safety And Next Step

The replay verifies current production hashes equal the audit boundary before starting and remain identical afterward for active provider, canonical and analysis DBs, active-generation pointer, publication journal, Review Queue and scheduler configuration. The active canonical hash remains `6fb73fe67e9d28407012ebb76e9b57951e409898b817a4eca94e58d934d4b5c2`. No backups were altered and no systemd operations were performed.

- Production publication state changed: NO.
- Production financial DBs changed: NO.
- Active generation changed: NO.
- Live workflows executed: NO.
- Scheduler state changed by this task: NO.
- Retry cap, 60-day horizon, NEW_THIS_REFRESH, manual drain and immutable activation contracts changed: NO.

Pre-existing runtime and unrelated chart changes are preserved and excluded from the commit. Source, compact fixtures, focused tests, replay helper and documentation only are committed; nothing is pushed.

Recommended next phase: separately authorize a controlled production application to the reviewed newly unique identities, with fresh active-generation/scope validation, existing publication locking/journal/backup contracts and separate result reporting. Do not automatically retry the entire backlog or resolve existing ambiguous pairs. This recommendation is not executed here.
