# Modality-safe lexical result recognition: implementation and detached validation

Date: 2026-10-28. Starting HEAD: `b0507eab48bd3cea68fd056cc3029399cd5b2388`. Governing [14-case specification](publication_authority_actual_result_context_review_2026-10-28.md); governing [latest-50 audit](publication_authority_latest_50_review_2026-10-28.md).

**Implemented the safe lexical subset only.** Detached replay improves GE, GM and MMM from 0 to 1 candidate; all other 11 members of the frozen 14 remain UNRESOLVED. No authority is applied, even on a copy. Source acquisition is identical for all 19 frozen companies (14 positives + five controls). ABAT/WOR/XTIA, BRC and all 22 legacy ambiguity fixtures are preserved. The exact 13,130 VERIFIED authorities, 13,153 evidence rows and 81 governing controls remain unchanged. Focused tests: **324 passed, 54 deliberately deselected**; full suite not run.

Two limitations are explicit. The unhyphenated year-before-quarter family, including AYTU’s primary wording, was stopped/deferred after it made BRC uniquely resolvable in an intermediate detached rehearsal. It is absent from the final implementation. TSLA retains its pre-existing false future/disclaimer candidate and stays at 2, not the desired 1. Section F of this task permits this separate existing defect to remain if lexical changes do not worsen it; exact candidate payloads are unchanged. This is a no-worsening PASS, not a claimed TSLA semantic fix or proof that all passive future wording is correctly handled.

## 1. Exact scope recovered before implementation

The specification maps R2 directly to **AYTU, GE, GM, HELE and MMM**. DXLG/PVH/TLRY are secondary lexical observations and hold controls, not additional promised resolutions. TLRY’s ready-recognition proposal depended on R1; the present request narrows scope to lexical normalization and requires other primitives to stop. All 14 original keys are retained below; no newer run population was substituted. The exact lexical forms and baseline failures were recorded before edits in `/tmp/publication_modality_safe_lexical/spans_before.json` and `replay_before.json`.

| Form in specification | Final treatment | Reason |
| --- | --- | --- |
| fiscal YYYY <ordinal> quarter | DEFERRED; not added | Intermediate primary matching bypassed BRC’s frozen hold. Preserving that hold needs guard/acquisition-related work outside this lexical phase. |
| YYYY <ordinal> quarter (unhyphenated) | DEFERRED; not added | The generic form also matches the fiscal-prefixed family. No prefix/ticker special case was added to disguise the conflict. |
| YYYY <ordinal>-quarter | ADDED | Exact observed GM headline order/hyphenation. |
| <ordinal>-quarter YYYY | ADDED | Exact observed GE/MMM hyphenation. |
| <ordinal> quarter [of] fiscal YYYY | ADDED | Observed HELE/DXLG wording; no inferred word year or canonical FY remap. |
| Qn Fiscal YYYY | ADDED | Observed AYTU/TLRY secondary title form; context still requires the existing quarter/result gates. |

Ordinals remain first/second/third/fourth and n remains 1–4; years are explicit four-digit source values. Existing recognized forms remain recognized. No synonym expansion, date-to-token inference, two-digit year inference, annual-to-Q4, six-month-to-quarter conversion or provider-based fiscal renumbering was introduced.

## 2. Defect reproduction and measured lexical leverage


| Case | Lexical scope | Natural key | Exact frozen clause | Tokens before | Tokens after | Candidates before → after | Mechanism / remaining boundary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AYTU | primary R2 | (265, 2026, 'Q4') | announcing its fiscal 2026 fourth quarter operational and financial results | [] | [] | 0 → 0 | Primary fiscal 2026 fourth quarter form deferred because the same lexical family resolves BRC. Exhibit context also has multiple quarter tokens; no scoping change. |
| GE | primary R2 | (931, 2026, 'Q3') | released its third-quarter 2026 financial results | [] | ['2026:Q3'] | 0 → 1 | Actual primary third-quarter 2026 now yields the exact 2026:Q3 token. Existing exhibit date-method precedence is unchanged and still fails its old non-conclusive-date path. |
| GM | primary R2 | (955, 2026, 'Q3') | GM releases 2026 third-quarter results | [] | ['2026:Q3'] | 0 → 1 | Acquired result exhibit headline 2026 third-quarter now yields the exact 2026:Q3 token; parent/source/acceptance and exhibit hash unchanged. |
| HELE | primary R2 | (1023, 2027, 'Q2') | second quarter of fiscal 2027 | [] | ['2027:Q2'] | 0 → 0 | Token improves to 2027:Q2; primary anticipates boilerplate still triggers the unchanged global veto. No R1 event-veto narrowing. |
| MMM | primary R2 | (1440, 2026, 'Q3') | reporting third-quarter 2026 financial results | [] | ['2026:Q3'] | 0 → 1 | New match comes from the explicit actual primary third-quarter 2026 clause, as explicitly permitted in the specification. Comparative exhibit still retains both 2026:Q3 and 2025:Q3; no comparative filter or preference. |
| DXLG | secondary hold control | (726, 2027, 'Q2') | today reported operating results for the second quarter of fiscal 2026 | [] | ['2026:Q2'] | 0 → 0 | Issuer FY2026 Q2 token improves, but canonical FY2027 Q2 is not remapped; comparative/scope and deep quarterly table proof remain held. |
| PVH | secondary hold control | (1819, 2027, 'Q2') | PVH CORP. REPORTS 2026 SECOND QUARTER RESULTS | [] | [] | 0 → 0 | Unhyphenated year-before-quarter form remains deferred; deep-table target proof and window limits unchanged. |
| TLRY | secondary hold control | (2174, 2027, 'Q1') | Q1 Fiscal 2027 | [] | ['2027:Q1'] | 0 → 0 | Q1 Fiscal 2027 token improves, but the business-line Distribution veto remains unchanged. This case was assigned to R1, not a standalone lexical resolution. |

Primary R2 metric: **4/5 token recognitions improve** (GE/GM/HELE/MMM); AYTU’s primary form is deferred. **3/5 candidate counts improve and become unique** (GE/GM/MMM). **1 improved-token case remains held by a separate current guard** (HELE); **1 further primary case is deferred** (AYTU). Both remain open. Secondary metrics are separate: DXLG and TLRY gain lexical tokens but remain held; PVH’s unhyphenated title form is deferred. Across the full 14-case cohort, 3 become hypothetical unique proposals and 11 stay held. Expected counts were not used as targets.

## 3. Small implementation surface

Source changes are confined to [sec_result_context.py](../../rawcandle/fundamentals/sec_result_context.py) and the two additive context-matching functions in [result_publication.py](../../rawcandle/fundamentals/result_publication.py).

`lexical_result_fiscal_tokens` unions the original vocabulary with only the four added families. It is a token extractor, not an actual/future event classifier. `result_context(..., allow_lexical_variants=True)` lets post-acquisition matching use that vocabulary only after the unchanged lead/event safety checks and existing bounded event-pattern/quarter checks. The default remains False; acquisition keeps calling the original behavior. The resolver’s additive primary/exhibit matching opts in and uses the same token set for conflicts and target-key comparison.

`_new_context_method` accepts a normalized fiscal token only when there is exactly one token equal to the existing canonical year/quarter **and the unchanged legacy matcher found no method**. A non-conclusive exact-date method does not fall through to this token branch. GE’s old ending/ended date mismatch is therefore not repaired; GE improves through its separately proven hyphenated primary fiscal clause. Existing multi-token/multi-period and primary/exhibit conflict gates remain in place. No legacy primary matching, writer, schema, Policy V1, Form 6-K, core Production or financial logic was refactored.

The intermediate broad family was removed rather than inventing a BRC-specific exception, raising the link bound or adding acquisition metadata. A generic new primary fiscal match could bypass BRC’s current lack of acquired exhibits even though its >2 result-link set stayed rejected. Final tests explicitly require that form and the frozen BRC primary to remain held. That guard-dependent subcase is left for a separate phase, per the task’s stop rule.

## 4. Modality, comparative and fiscal-identity safety

The lexical helper can correctly extract an explicit token from future wording; that does not authorize a candidate. Existing unsafe_new_event, 1,200-character lead, actual-result expression, first-6,000-character search, -100/+650 event context, required quarter/context checks, same-accession validation, source/form/items and 180-day window are unchanged. No R1 boilerplate/business-line exceptions, passive-future repair, R5 comparison scoping, R6 window extension, R7 date-method fallback or R8 link addition was implemented.

New fixtures distinguish token extraction from context acceptance for will/expect-to/plan-to/anticipated releases, scheduled announcement wording, passive future wording without a current report, preliminary/partial/pro-forma and distribution/cash-only events. Negatives also cover missing/malformed years/quarters, unrelated ordinal use, prior-only tokens, annual-only and six-month-only text. Some older recognition contracts still have semantic limitations, including TSLA’s cross-clause passive disclaimer; unchanged guards and tested no-worsening must not be presented as a general NLP guarantee.

Current/prior tokens are both retained, including newly spelled variants; neither first token nor newest year is selected. MMM’s improvement uses the explicit single-period primary clause, which the governing specification explicitly allows; its comparative exhibit still has both fiscal tokens and remains non-unique if used on its own. ZUMZ’s multiple comparative period ends remain held. Issuer FY2026 Q2 is not mapped to canonical FY2027 Q2 for any of CURV/DXLG/KR/PLAY/PVH/ZUMZ. Nearby cash dates, deep tables and source availability do not repair those keys.

## 5. Frozen real-input before/after rehearsal

Both runs use the original hash-verified SEC submissions/primary/exhibit payloads retained by the governing review. SecClient uses frozen fetch callbacks, not the network. The same ordered requests and complete acquired SecFiling payloads are asserted equal for every one of the 19 companies, including exact form/items, source references, full sections/exhibits and acceptance times. The updated resolver is run twice for determinism. Diagnostic-only releases were not inserted into the default source inputs. No enrich_database or apply_resolution call occurred.

| Case | Frozen natural key | Period end | Before candidates | After candidates | Before status | Detached after status | Unique proposal? | Other guard / outcome |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AYTU | (265, 2026, Q4) | 2026-06-30 | 0 | 0 | UNRESOLVED | UNRESOLVED | NO | Primary fiscal 2026 fourth quarter form deferred because the same lexical family resolves BRC. Exhibit context also has multiple quarter tokens; no scoping change. |
| CURV | (605, 2027, Q2) | 2026-08-01 | 0 | 0 | UNRESOLVED | UNRESOLVED | NO | Strong-primary-token exhibit suppression, issuer/provider FY naming and clipped period clause unchanged. |
| DXLG | (726, 2027, Q2) | 2026-08-01 | 0 | 0 | UNRESOLVED | UNRESOLVED | NO | Issuer FY2026 Q2 token improves, but canonical FY2027 Q2 is not remapped; comparative/scope and deep quarterly table proof remain held. |
| GE | (931, 2026, Q3) | 2026-09-30 | 0 | 1 | UNRESOLVED | VERIFIED | YES, hypothetical only | Actual primary third-quarter 2026 now yields the exact 2026:Q3 token. Existing exhibit date-method precedence is unchanged and still fails its old non-conclusive-date path. |
| GM | (955, 2026, Q3) | 2026-09-30 | 0 | 1 | UNRESOLVED | VERIFIED | YES, hypothetical only | Acquired result exhibit headline 2026 third-quarter now yields the exact 2026:Q3 token; parent/source/acceptance and exhibit hash unchanged. |
| HELE | (1023, 2027, Q2) | 2026-08-31 | 0 | 0 | UNRESOLVED | UNRESOLVED | NO | Token improves to 2027:Q2; primary anticipates boilerplate still triggers the unchanged global veto. No R1 event-veto narrowing. |
| KR | (1239, 2027, Q2) | 2026-08-15 | 0 | 0 | UNRESOLVED | UNRESOLVED | NO | Target-aware acquisition and FY naming review remain separate; no new exhibit acquired. |
| MMM | (1440, 2026, Q3) | 2026-09-30 | 0 | 1 | UNRESOLVED | VERIFIED | YES, hypothetical only | New match comes from the explicit actual primary third-quarter 2026 clause, as explicitly permitted in the specification. Comparative exhibit still retains both 2026:Q3 and 2025:Q3; no comparative filter or preference. |
| NEE | (1524, 2026, Q3) | 2026-09-30 | 0 | 0 | UNRESOLVED | UNRESOLVED | NO | Exhibit 99/news-release link shapes, stage/scope and lexical context behind that unfetched source remain out of scope. |
| PLAY | (1745, 2027, Q2) | 2026-08-04 | 0 | 0 | UNRESOLVED | UNRESOLVED | NO | Strong-primary-token suppression and issuer/provider FY naming unchanged; no source acquisition extension. |
| PVH | (1819, 2027, Q2) | 2026-08-02 | 0 | 0 | UNRESOLVED | UNRESOLVED | NO | Unhyphenated year-before-quarter form remains deferred; deep-table target proof and window limits unchanged. |
| TLRY | (2174, 2027, Q1) | 2026-08-31 | 0 | 0 | UNRESOLVED | UNRESOLVED | NO | Q1 Fiscal 2027 token improves, but the business-line Distribution veto remains unchanged. This case was assigned to R1, not a standalone lexical resolution. |
| TXN | (2233, 2026, Q3) | 2026-09-30 | 0 | 0 | UNRESOLVED | UNRESOLVED | NO | Exhibit 99 link shape remains excluded by unchanged acquisition. No new source read. |
| ZUMZ | (2453, 2027, Q2) | 2026-08-01 | 0 | 0 | UNRESOLVED | UNRESOLVED | NO | Multiple comparative ends and FY convention remain held; no first/newest-date selection. |

Every case has one plausible parent and before reason QUARTER_MATCH_FAILED. New reason is VERIFIED only for the three one-candidate detached proposals. All 14 live authority rows remain UNRESOLVED with NULL selected evidence/time. “VERIFIED” in this table is the pure resolver’s hypothetical status formula; no copy or live authority result was persisted.

| New unique proposal | Parent accession | Unchanged SEC acceptance UTC | Method / immutable source context |
| --- | --- | --- | --- |
| GE | 0000040545-26-000063 | 2026-10-20T10:30:57Z | NORMALIZED_ITEM_2_02_HEADING:CIK_ITEM_2_02_EXPLICIT_FISCAL_QUARTER |
| GM | 0001467858-26-000056 | 2026-10-20T11:30:18Z | SEC_LINKED_EXHIBIT; same-accession gmq32026pressreleaseandfin.htm, raw SHA-256 95297ccfe37212db992fb9052fdbce8663c89aec3203fc7f315f84d3c1cab646; explicit fiscal-quarter method |
| MMM | 0000066740-26-000308 | 2026-10-20T10:35:38Z | NORMALIZED_ITEM_2_02_HEADING:CIK_ITEM_2_02_EXPLICIT_FISCAL_QUARTER |

All use SEC_8K_ITEM_2_02, unchanged hierarchy/rank/rule version and parent acceptance. No issuer timestamp, date preference or multiple-parent selection is introduced.

## 6. TSLA mandatory negative control and exception

Key `(2216, 2026, Q3)`, period end 2026-09-30. The current separate defect remains: October 2 deliveries/storage disclosure qualifies through a future-financial-results disclaimer; October 21 is the actual result parent. Before and after retain exactly the same two complete candidate payloads (including evidence hashes, methods, sources and times), not merely the same count.

| Parent | Acceptance UTC | Required semantic meaning | Observed before → after |
| --- | --- | --- | --- |
| 0001628280-26-064366 | 2026-10-02T13:04:26Z | NOT_A_CURRENT_ACTUAL_RESULT_EVENT | Existing false candidate retained unchanged; not added or strengthened by lexical normalization |
| 0001628280-26-066738 | 2026-10-21T20:41:42Z | VALID_ACTUAL_RESULT_EVENT | Actual legacy exact-period candidate retained unchanged |

Observed candidate count **2 → 2**, AMBIGUOUS. Desired later result is **1**. **No-worsening control PASS under the task’s explicit section-F exception; strict future-disclaimer rejection is NOT implemented or claimed.** No authority is selected. The governing audit’s early-exhibit source hash ab3489cea7df455ed0af0f75f9257b4559a72b23684674d4c651452df4fb2baf and older retained 8abe12f6cc7c1359dcf701962761de59240e6352c91cfd1e954a9c358793585b observation remain distinct; this phase downloads/replaces neither.

## 7. Ambiguity and legacy positive compatibility


| Frozen control | Before → after candidates | Preservation |
| --- | --- | --- |
| ABAT FY2026 Q4 | 2 → 2 | Full original candidate payloads and distinct parent acceptance times identical; no annual/Q4 inference. |
| WOR FY2027 Q1 | 2 → 2 | Full payloads identical; no same-result-repeat/first-event relation inferred. |
| XTIA FY2026 Q2 | 2 → 2 | Full payloads identical; preliminary/completion and extra plausible Q3 context unchanged. |
| BRC FY2026 Q4 | 0 → 0 | Three-link conservative rejection and primary hold preserved; broad year-before family deferred. |
| 22 legacy ambiguity fixtures | 44 → 44 | Full before/after candidate payloads identical, not just counts. |
| AVT/CPB/ORCL | 3 → 3 | Full before/after candidate payloads identical under unchanged frozen acquisition. |
| 26 Policy V1 legacy inputs | 52 → 52 | Full before/after legacy candidate payloads identical; separate reviewed-policy behavior unchanged. |

Legacy primary matches still run before additive context recognition and intentionally retain their existing preliminary/partial compatibility. New lexical safety checks do not retroactively filter those candidates or revise evidence identity. Comparative, non-result and source-bound negatives remain independent of automatic authority writes.

## 8. Exact VERIFIED regression protection


| Original frozen artifact | Rows | Exact SHA-256 |
| --- | --- | --- |
| verified_regression.json | 13130 | 174ad43e6110d6eff2577bcc48a85f436726300dd179e317621b63b9becda6ad |
| verified_evidence.json | 13153 | da30778b0b9f2fdeda0c7fe2f1113f640bc03cba018368262fc356ec12f33969 |
| latest81_verified_controls.json | 81 | 9aec1d5196e932cb5b36e393df81ec533b1e837d087782baa4ac5e7aed676f09 |

The hash-bound retained canonical generation remains `refresh_20261028T054130Z_refresh_fundamentals_f0854217d4df_production_14d59fd7`, canonical SHA-256 `11ad0c3106a80bd8583a317f595e5d21f49a5431ec9dfc99fc4db8bb7eccd35e`. No different latest cohort was regenerated. Read-only queries compare **all fields** of the original 13,130 authority rows and 13,153 associated evidence rows against the frozen snapshots; all are identical. All 81 governing-run controls are exact members with identical selected source/time/evidence/status/natural key. Current generation hashes are also unchanged.

Full raw historical filing contexts for all 13,130 rows are not stored in these authority/evidence snapshots. This phase therefore does **not** claim a complete historical before/after parser replay, nor reacquire a historical universe. Protection consists of exact full-row/evidence comparisons, unchanged writer/precedence code and unchanged default VERIFIED-skip path, plus the available frozen source replays. No additional hypothetical historical candidates were demonstrated in the replayed controls; unobserved historical contexts remain a regression consideration for any later broader dispatch or refresh-existing change. Default VERIFIED rows are never re-enriched by this task.

AST comparisons confirm that SecClient, match_quarter_context, resolve_sec_filings_detailed, apply_resolution, enrich_database, _evidence_payload and the explicit reviewed-policy dispatch are unchanged. In sec_result_context, unsafe_new_event, result_periods, the original acquisition token function, same-accession and link selection are unchanged. The only existing resolver definitions changed are _new_sec_context_matches and _new_context_method; the only existing context definition changed is result_context’s opt-in vocabulary. No writer function was invoked.

## 9. Focused tests and reviewed-route invariance

Five-file focused regression run: **324 passed, 54 deselected**. After tightening compact fixture parent identities/paths, the final lexical test file was also rechecked: **114 passed**. Only these directly relevant files were selected:

```text
tests/test_sec_result_lexical_recognition.py
tests/test_sec_result_recognition.py
tests/test_result_publication_authority.py
tests/test_publication_event_policy_v1.py
tests/test_form6k_authority_v1.py
```

The new file contributes 114 cases covering each added form in isolation and actual context; explicit active/passive/scheduled/anticipated negatives; malformed, annual-only, six-month-only, prior/comparative, distribution/pro-forma/preliminary shapes; actual GE/GM/MMM clauses; HELE/TLRY holds; deferred AYTU/BRC family; unchanged GE date precedence; fiscal convention and primary/exhibit conflicts; acquisition isolation; legacy compatibility; 22 pure ambiguity controls; and the TSLA unchanged-defect control. Compact text clauses and reconstructed test frames are committed; full SEC payloads and temporary frozen fixtures are not.

The initial focused run had one fixture failure: Q1 Fiscal 2027 was supplied without the existing required quarter/context word. The fixture was corrected to include an explicit quarter statement; the context guard was not relaxed. The separate intermediate BRC replay failure caused removal of the unsafe lexical family. Neither finding justified a full-suite run.

To obey the explicit no-apply_resolution/no-enrichment instruction, eight existing writer/schema test functions (54 parameterized items) were intentionally deselected:
- `test_all_22_true_ambiguities_retain_pre_change_candidate_sets`
- `test_schema_is_additive_idempotent_and_preserves_existing_dates`
- `test_known_official_sec_item_202_samples_resolve_without_sharadar_fallback`
- `test_statuses_precedence_conflict_and_verified_restart_preservation`
- `test_yahoo_history_is_stored_as_secondary_evidence_and_never_selected`
- `test_exact_26_case_replay_preserves_all_52_legacy_candidates`
- `test_copy_universe_no_financial_identity_authority_or_unrelated_state_mutation`
- `test_rank_and_version_do_not_change_default_production_semantics`

The command was `venv/bin/python -m pytest -q` with the five paths above and `-k` equal to the conjunction of `not <name>` for those eight names. The deselected 22/26 ambiguity behaviors were independently compared with the actual previous resolver through pure detached helpers, with full candidate payload equality. Source precedence, reviewed higher-priority preservation, source-rank and default-authority invariance are covered by the selected pure Policy V1/Form 6-K regressions and unchanged writer/VERIFIED-restart code, without invoking a DB writer. Policy V1 retains its reviewed fixture partition; Form 6-K retains its 23-case/30-candidate reviewed partition, including nine unique proposals and 14 holds. No default route dispatch was added.

Additional real-input comparisons: original default acquisition is byte/field/order-identical for all 19 frozen companies; the full 14-case replay and all five controls are deterministic. Pure old/new fixture replay confirms 3 known-positive, 44 legacy-ambiguity and 52 Policy V1 legacy candidate payloads identical. No network request, live workflow, drain or mutation was needed for any of these checks. **Full suite: NOT RUN.**

## 10. Runtime invariance and artifact binding

Initial and terminal captures acquired existing UI-operation, Production and scheduler kernel locks through read-open handles without rewriting lock content/owner metadata. Runtime SQLite reads used mode=ro and query_only. Verification at `2026-10-28T11:59:41.553369+00:00` passed for all nine baseline artifact SHA-256 values. No active-generation, watermark, provider/canonical/analysis, Review Queue, journal, scheduler or backup change occurred. All unrelated pre-existing worktree changes are preserved and excluded from the commit.

| Runtime artifact | Identical before/after SHA-256 |
| --- | --- |
| active_manifest | 4ed37754c69b475bb0341eb85fd24581a49a63049f03487045f6a1da99a54198 |
| analysis | ce5a09a8782660703e5160aa44a798ea2029318732466f0aa90b28c38321e3e8 |
| canonical | 11ad0c3106a80bd8583a317f595e5d21f49a5431ec9dfc99fc4db8bb7eccd35e |
| generation_manifest | 4ed37754c69b475bb0341eb85fd24581a49a63049f03487045f6a1da99a54198 |
| journal | 8c88e3894b9376be4b56cc51041274d7ca368967e87dbf532f5c491e54190eae |
| provider | 6d0262597c4248d40ce8b7ac79b164b1f8fcdfc09fa72283e35486d94380ae81 |
| queue | 746836b89c2bc2bcf5880812bdcdd64024c2c4398e196e21746b74fbf0f68b99 |
| scheduler_config | 3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894 |


| Temporary artifact under /tmp/publication_modality_safe_lexical (not committed) | SHA-256 |
| --- | --- |
| replay_before.json | 560637df3a3bc751ff957d53332bc1f7fc4f72c469e3806fcbc30180b9339e0c |
| replay_after.json | b70ea157ac9ff66d6bed0c4818be1639da99f84fd35312b3a380f54a720beb6f |
| spans_before.json | e398bd26e47dae8b45d80e8bf04e90bbb17bce59929550d34c08b5f037b3f126 |
| spans_after.json | f3a825da3d56b0a60cf0174442ed28527cb501b7d4e917d65a830561373f8d63 |
| fixture_comparison.json | e63f16fb3f9dcb6c287ac20a3450d52cae2503bda243bd1589a3b2e2d10f61f7 |
| verification.json | eb09f36166cdb10406dd1a9a8cf085ae2928c9f8e6eba39a29159a17bb4bd577 |

The governing `/tmp/publication_actual_result_context_review` payloads, source manifest and exact spans were reused and hash-verified. No new provider downloads, raw source payloads, DBs, runtime reports, caches, manifests or journal files are committed. Commit scope is exactly two bounded source files, the focused lexical test file and this document. No push.

## 11. Exactly one recommended next phase

**PUBLICATION-AUTHORITY-PASSIVE-FUTURE-EVENT-GUARD-1 — separately implement and validate the TSLA passive/future disclaimer rejection over the exact frozen two-parent control.** Its required outcome is to reject October 2 as a current actual-result event while preserving October 21, producing one candidate without altering parent acceptance or legacy ambiguity behavior. It must keep the same VERIFIED protection and must not add period translation, acquisition expansion, comparative filtering or event precedence. This is the most direct remaining correctness defect; the deferred year-before-quarter/acquisition guard question and broader HELE/TLRY event-unit work remain separate. The recommended phase is not started here; no authority application is recommended as part of this phase.
