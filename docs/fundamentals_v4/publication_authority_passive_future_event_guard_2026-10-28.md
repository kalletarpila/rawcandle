# Passive/future result-event guard: implementation and detached validation

Date: 2026-10-28. Starting HEAD: `53bc60dea6f0e3ba9b13cf86fe8afa652dfebf8c`. Governing [lexical implementation](publication_authority_modality_safe_lexical_recognition_2026-10-28.md), [actual-result specification](publication_authority_actual_result_context_review_2026-10-28.md) and [latest-50 audit](publication_authority_latest_50_review_2026-10-28.md).

**Implemented a local pending-event guard. TSLA’s frozen detached result changes exactly from 2 AMBIGUOUS candidates to 1 hypothetical VERIFIED candidate.** October 2 is rejected before period matching; October 21’s complete candidate payload is unchanged. All 14 other reviewed cases and every explicit ambiguity/positive control retain their complete candidate payloads. Acquisition is identical for all 19 frozen companies. **387 focused tests passed; 54 writer/schema items were deliberately deselected; full suite not run.** No authority was applied or evidence written, including on a copy. Live TSLA remains AMBIGUOUS and unmodified.

## 1. Exact frozen TSLA defect reproduced before editing

Natural key `(2216, 2026, Q3)`, period end `2026-09-30`, CIK `0001318605`, frozen generation-local quarter_id `78864`. The baseline was collected using the code at the governing lexical commit before any source change. Original review payloads were available and hash-verified; no network refresh or alternative population was used. Both parents are metadata-eligible 8-K Item 2.02 sources inside the unchanged 180-day window, but only one is an actual financial-result event.

| Parent | Acceptance UTC | Form / metadata items | Primary source | Raw primary SHA-256 |
| --- | --- | --- | --- | --- |
| 0001628280-26-064366 | 2026-10-02T13:04:26Z | 8-K / 2.02,9.01 | [tsla-20261002.htm](https://www.sec.gov/Archives/edgar/data/1318605/000162828026064366/tsla-20261002.htm) | efa537fff12b49185a5eaca399000fb9883fb22a24a0dcb44365fa3d71a56b31 |
| 0001628280-26-066738 | 2026-10-21T20:41:42Z | 8-K / 2.02,9.01 | [tsla-20261021.htm](https://www.sec.gov/Archives/edgar/data/1318605/000162828026066738/tsla-20261021.htm) | e9c3a1ca8c6e780411c691601ee2efe80e0def3683ae881a36fbc73f0f0e2833 |

October 2’s directly linked [exhibit991111111.htm](https://www.sec.gov/Archives/edgar/data/1318605/000162828026064366/exhibit991111111.htm) has governing audit payload SHA-256 `ab3489cea7df455ed0af0f75f9257b4559a72b23684674d4c651452df4fb2baf`. It discloses production, deliveries and storage deployments and says financial results are pending. The exact frozen source words include:

> Our net income and cash flow results will be announced along with the rest of our financial performance when we announce Q3 earnings.

A later disclaimer refers to a 10-Q for the quarter ended September 30, 2026. The reference is to a future/reporting context, not a current earnings release. The baseline current-code resolver nonetheless retained both the October 2 additive exhibit candidate and October 21 legacy exact-period candidate; reason MULTIPLE_VALID_CANDIDATES, status AMBIGUOUS, with no authority selected.

## 2. Exact false-positive mechanism


| Observed baseline operation | Frozen outcome |
| --- | --- |
| unsafe_new_event on document lead | False. The pending paragraph is beyond the 1,200-character lead; passive will be and conditional when we are not the original direct will announce shape. |
| Actual regex trigger | announce in when we announce Q3 earnings, at normalized character 1578. |
| Matched trigger-to-results span | [1578:1790]; the 0–240-character bridge crosses the next sentence and reaches the disclaimer’s quarterly financial results. |
| Existing bounded context | Begins at 1478 (100 characters before the trigger), then uses the unchanged +650 tail bound. |
| unsafe_new_event on that context | False; the same missing passive/dependent-clause distinction applies. |
| Fiscal context | No fiscal token in the chosen context; result_periods returns september 30, 2026 from the referenced 10-Q. |
| Matching method | SEC_LINKED_EXHIBIT, with CIK_ITEM_2_02_EXACT_PERIOD_END context; parent/source/acceptance are still October 2. |
| False candidate evidence ID / hash | rpe_0eb915051fb665185045a137 / 0eb915051fb665185045a137452cf4bf8bbc678b08a2dc0cb9762cde968ad055 |

The immediate governing prefix ends in `when we `; this is a present-tense dependent future/pending clause, not an assertion that results have been announced. The broad trigger span then borrows result wording across a sentence and the period from a referenced future report. This is a modality error before candidate creation, not an SEC timestamp discrepancy, source-rank issue or tie between two valid current events. No earlier/later preference can repair that semantics.

## 3. Small normative rule and event-unit boundary

A pending, scheduled, expected or dependent future trigger SHALL NOT establish an actual current result event merely because financial-result words, fiscal tokens or an ended date occur nearby. The implementation examines only the **at-most-100-character prefix immediately governing the matched announce/report/release trigger**, restricted to its last punctuation-delimited clause (`. ! ? ;`). It recognizes bounded future auxiliaries (including passive will be), expected/scheduled-to forms, expect/plan/intend/prepare-to forms, and present dependent when/once/until/before/after clauses. Past declarations are not rejected merely for occurring after a past-tense when/after prefix.

This is not a whole-document future-keyword ban. An actual reports/reported/released/announced predicate remains valid when independent outlook, call scheduling or other future language occurs elsewhere. The existing 6,000-character trigger search, 240-character result bridge, -100/+650 context bounds and period/token checks are unchanged. A rejected pending trigger must not consume a separate actual assertion inside its broad matched span: matching resumes after the rejected verb, allowing that separate predicate to be evaluated in the same bounded search. There is no new sentence/window expansion, comparison filtering or event precedence.

## 4. Implementation surface

Only [sec_result_context.py](../../rawcandle/fundamentals/sec_result_context.py) changes runtime source. It adds `_pending_result_trigger(prefix, verb)` and applies it in the existing post-acquisition matching mode of `result_context`. A named verb capture supplies the exact predicate; a progress-bounded regex search resumes after rejected verbs without skipping possible actual assertions. Token extraction remains purely lexical; no token, fiscal key or date rule is changed.

Acquisition continues to call the default context mode and receives its prior behavior. This separation is deliberate: SecClient, its metadata/source/link eligibility, strong-primary-token suppression, two-link bound and source payloads must remain unchanged in this phase. The original global unsafe_new_event check is also untouched. The full result_publication module—including additive resolver, legacy primary matcher, timestamp normalization, rank, evidence hashing, writer, VERIFIED skip/restart and reviewed dispatch—is byte-identical to the starting version. No schema, policy, provider, Production or canonical-fundamentals change was needed.

The existing compact TSLA test in [test_sec_result_lexical_recognition.py](../../tests/test_sec_result_lexical_recognition.py) now requires strict early-parent rejection rather than the previous temporary no-worsening exception. New [test_sec_result_modality_guard.py](../../tests/test_sec_result_modality_guard.py) holds the focused local-modality and mixed-event tests. No ticker/CIK/accession exception exists in runtime code.

## 5. Exact TSLA before/after and immutable identity


| Parent / role | Before candidates | After candidates | Result |
| --- | --- | --- | --- |
| 0001628280-26-064366 — NOT_A_CURRENT_ACTUAL_RESULT_EVENT | 1 | 0 | Rejected by local pending/dependent trigger recognition before period matching; no fallback resurrects it. |
| 0001628280-26-066738 — VALID_ACTUAL_RESULT_EVENT | 1 | 1 | Complete original candidate payload identical; legacy exact-period recognition retained. |
| Combined detached outcome | 2 | 1 | AMBIGUOUS → VERIFIED / hypothetical unique proposal; no apply. |


| Retained actual candidate field | Identical value |
| --- | --- |
| company_id | 2216 |
| fiscal_year | 2026 |
| fiscal_quarter | Q3 |
| quarter_id | 78864 |
| accession_number | 0001628280-26-066738 |
| source_type | SEC_8K_ITEM_2_02 |
| source_timestamp_utc | 2026-10-21T20:41:42Z |
| source_reference | https://www.sec.gov/Archives/edgar/data/1318605/000162828026066738/tsla-20261021.htm |
| document_id | tsla-20261021.htm |
| matching_method | CIK_ITEM_2_02_EXACT_PERIOD_END |
| rule_version | result_publication_v1 |
| evidence_id | rpe_5fb30e63fc916111e4ed1104 |
| evidence_hash | 5fb30e63fc916111e4ed11043b3297b98f467eb83e346087f2c903c5e37702dc |

The early and actual parents were also resolved individually from the real frozen inputs: exactly 0 and 1 candidate respectively. The combined after list equals the original October 21 candidate as a complete dictionary, not just its accession/time. Existing October 2 evidence records are not deleted or rewritten; only the detached candidate output changes. The rejected candidate’s original hash remains in the baseline artifact. The retained October 21 time is `2026-10-21T20:41:42Z`, source SEC_8K_ITEM_2_02 and evidence hash `5fb30e63fc916111e4ed11043b3297b98f467eb83e346087f2c903c5e37702dc`.

The governing early-exhibit observation `ab3489cea7df455ed0af0f75f9257b4559a72b23684674d4c651452df4fb2baf` remains distinct from the older retained `8abe12f6cc7c1359dcf701962761de59240e6352c91cfd1e954a9c358793585b` source observation described in the prior reports. Neither is replaced or normalized in this task. No timestamp ordering, stronger-word-count ranking, evidence mutation or authority selection is used to obtain the one-candidate result.

## 6. HELE and TLRY controls

**HELE remains held: 0 → 0, UNRESOLVED.** Exact frozen primary `0000916789-26-000137` announces actual results for second quarter of fiscal 2027, but its later standard boilerplate includes anticipates within the existing 1,200-character lead. That pre-existing global veto fires before the new local trigger guard. Its token remains 2027:Q2; no source or financial-period interpretation changes. No HELE resolution is claimed, and no unexpected change occurred.

**TLRY remains held: 0 → 0.** Its business-line Distribution wording still triggers the old veto. Safely narrowing those broad keyword checks is separate from rejecting a future predicate. This phase does not implement either boilerplate or business-line exceptions, does not acquire HELE’s diagnostic exhibit through a new path, and does not weaken distribution-only negatives.

## 7. Future-only negative controls

New fixtures require zero additive current-result candidates for future/passive announcements, including results will be announced, results will be reported later, financial performance will be released, earnings will be discussed, and results are expected/scheduled to be announced. They also cover active expect-to-report, management will discuss results, a conference-call-only reference, preliminary production metrics/financial results forthcoming and passive disclaimers. Each is paired with a concrete fiscal token or exact September 30 period end; nearby identity evidence cannot cure pending modality. Present dependent when/once/until/before/after references are rejected without dropping genuine past assertions.

The original direct future, scheduled announcement, preliminary/partial/pro-forma, distribution/cash-only, malformed/annual/semiannual and source/conflict negatives continue to pass. These are additive-path tests; intentionally retained legacy primary compatibility is unchanged. No new runtime status/reason enum or reviewed override was introduced.

## 8. Positive mixed-modality controls

Positives retain actual reports/releases/announcements of current-quarter results with separate FY-growth expectations, future calls, conference-call discussion and a later pending-results reference. A pending reference before a separate actual assertion is also accepted: rejecting its broad regex span cannot swallow the genuine current report. Completed past declarations remain valid even after past when/after wording. Current-period fiscal evidence and existing conflict checks still have to pass; the guard does not remove competing current periods to create uniqueness.

A real current-result heading followed later by forward-looking boilerplate remains recognized when it passed the existing lead/context checks. The positive anticipates fixture places that boilerplate beyond the original lead/context veto, preserving the prior contract. This is deliberately distinguished from HELE’s existing within-lead global hold: no claim is made that the present fix solves all mixed-document boilerplate semantics. The new local rule introduces no whole-filing ban on expects, anticipates, outlook, guidance, calls or future discussion.

## 9. Frozen 14-case rehearsal and lexical preservation

Before and after are detached resolver outcomes on the exact prior lexical-phase inputs, not live authority statuses. The resolver ran twice on each frozen input, with identical complete return values. All 14 complete candidate/diagnostic payloads are identical across this phase. GE/GM/MMM remain unique hypothetical proposals; live authority rows remain unmodified.

| Case | Frozen natural key | Before count | After count | Detached before | Detached after | Complete payload identical? | Boundary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AYTU | (265, 2026, 'Q4') | 0 | 0 | UNRESOLVED | UNRESOLVED | YES | Year-before-quarter family remains deferred. |
| CURV | (605, 2027, 'Q2') | 0 | 0 | UNRESOLVED | UNRESOLVED | YES | Existing source/FY/comparative/period hold unchanged. |
| DXLG | (726, 2027, 'Q2') | 0 | 0 | UNRESOLVED | UNRESOLVED | YES | Existing source/FY/comparative/period hold unchanged. |
| GE | (931, 2026, 'Q3') | 1 | 1 | VERIFIED | VERIFIED | YES | Lexical primary 2026:Q3; original acceptance/evidence identity retained. |
| GM | (955, 2026, 'Q3') | 1 | 1 | VERIFIED | VERIFIED | YES | Same acquired result exhibit; parent acceptance/evidence payload retained. |
| HELE | (1023, 2027, 'Q2') | 0 | 0 | UNRESOLVED | UNRESOLVED | YES | Old global anticipation veto remains. |
| KR | (1239, 2027, 'Q2') | 0 | 0 | UNRESOLVED | UNRESOLVED | YES | Existing source/FY/comparative/period hold unchanged. |
| MMM | (1440, 2026, 'Q3') | 1 | 1 | VERIFIED | VERIFIED | YES | Same actual primary fiscal clause; comparative exhibit handling unchanged. |
| NEE | (1524, 2026, 'Q3') | 0 | 0 | UNRESOLVED | UNRESOLVED | YES | Existing source/FY/comparative/period hold unchanged. |
| PLAY | (1745, 2027, 'Q2') | 0 | 0 | UNRESOLVED | UNRESOLVED | YES | Existing source/FY/comparative/period hold unchanged. |
| PVH | (1819, 2027, 'Q2') | 0 | 0 | UNRESOLVED | UNRESOLVED | YES | Existing source/FY/comparative/period hold unchanged. |
| TLRY | (2174, 2027, 'Q1') | 0 | 0 | UNRESOLVED | UNRESOLVED | YES | Old business-line Distribution veto remains. |
| TXN | (2233, 2026, 'Q3') | 0 | 0 | UNRESOLVED | UNRESOLVED | YES | Existing source/FY/comparative/period hold unchanged. |
| ZUMZ | (2453, 2027, 'Q2') | 0 | 0 | UNRESOLVED | UNRESOLVED | YES | Existing source/FY/comparative/period hold unchanged. |

CURV/DXLG/KR/PLAY/PVH/ZUMZ retain their issuer/provider fiscal-convention behavior, source suppression and comparative/period holds. No FY2026→FY2027 translation, target-period binding, numeric table inference, comparative role selection, GE date-method change or acquisition expansion is added. Existing lexical token functions and methods are AST-identical.

## 10. Ambiguity and known-positive preservation


| Control | Before → after | Evidence |
| --- | --- | --- |
| ABAT FY2026 Q4 | 2 → 2 AMBIGUOUS | Complete candidate payloads identical; component/annual-Q4 scope not resolved. |
| WOR FY2027 Q1 | 2 → 2 AMBIGUOUS | Complete payloads identical; no release/repeat relationship or timing preference inferred. |
| XTIA FY2026 Q2 | 2 → 2 AMBIGUOUS | Complete payloads identical; preliminary/completion and extra plausible Q3 filing unchanged. |
| BRC FY2026 Q4 | 0 → 0 UNRESOLVED | Complete payloads identical; >2-link and deferred primary-family behavior retained. |
| 22 legacy ambiguity fixtures | 44 → 44 candidates | Complete original candidate dictionaries identical. |
| AVT/CPB/ORCL fixtures | 3 → 3 candidates | Complete original candidates identical under unchanged frozen acquisition. |
| 26 Policy V1 legacy input fixtures | 52 → 52 candidates | Complete legacy payloads identical; reviewed eligibility/relationship semantics untouched. |

The predicate guard is in the additive event context only. It does not filter already qualifying legacy primary candidates or turn real two-parent ambiguity into a one-parent result. No selected evidence ID, source, time or original immutable candidate hash changes in the preserved controls.

## 11. Exact VERIFIED regression protection


| Original hash-bound snapshot | Rows | SHA-256 |
| --- | --- | --- |
| verified_regression.json | 13130 | 174ad43e6110d6eff2577bcc48a85f436726300dd179e317621b63b9becda6ad |
| verified_evidence.json | 13153 | da30778b0b9f2fdeda0c7fe2f1113f640bc03cba018368262fc356ec12f33969 |
| latest81_verified_controls.json | 81 | 9aec1d5196e932cb5b36e393df81ec533b1e837d087782baa4ac5e7aed676f09 |

The original retained canonical generation is available: `refresh_20261028T054130Z_refresh_fundamentals_f0854217d4df_production_14d59fd7`, canonical file SHA-256 `11ad0c3106a80bd8583a317f595e5d21f49a5431ec9dfc99fc4db8bb7eccd35e`. No different latest cohort was generated. Read-only comparison confirms all fields of 13,130 authority rows and 13,153 evidence rows equal the frozen snapshots, including selected source/time/evidence ID, status and natural key. All 81 governing-run controls remain exact members with identical fields.

No historical source universe was reacquired. Full raw contexts are not stored for every historical VERIFIED row, so this is not a claimed complete historical parser replay. Protection is the full frozen row/evidence comparison, unchanged writer/default VERIFIED-skip behavior and the available source-bound fixture/detached replays. The current live TSLA row is independently still AMBIGUOUS with NULL selected authority/time; the hypothetical one-candidate result has not been written.

## 12. Acquisition and reviewed-route invariance

The complete result_publication source file is byte-identical to the starting version. SecClient, Item 2.02 eligibility, same-accession/link rules, strong-token suppression, Exhibit 99 handling, two-link bound, 180-day window, source rank, method precedence, writer, VERIFIED restart and reviewed dispatch are unchanged. On all 19 frozen companies, ordered fetch requests and complete acquired SecFiling payloads are exactly equal before/after. Those are frozen callback reads, not network requests. The default acquisition context still uses its previous recognition behavior; only post-acquisition matching invokes the local pending check.

Policy V1 and Form 6-K source and fixture files are unchanged. Selected pure reviewed-policy, Form 6-K, higher-priority/source-precedence and invariant tests pass. Their explicit reviewed routes are not dispatched by this new guard. The normal authority schema and status machine are unchanged. No fallback/earlier/later rule, ranking based on more financial words or ticker-specific branch exists in runtime code.

## 13. Focused validation

**387 passed, 54 deselected in the six directly relevant test files below. Full suite NOT RUN.** The new modality file contributes 63 focused cases; the existing 114 lexical cases retain the lexical/control behavior with the TSLA expectation updated from temporary no-worsening to strict one-candidate rejection.

```text
tests/test_sec_result_modality_guard.py
tests/test_sec_result_lexical_recognition.py
tests/test_sec_result_recognition.py
tests/test_result_publication_authority.py
tests/test_publication_event_policy_v1.py
tests/test_form6k_authority_v1.py
```

The command was `venv/bin/python -m pytest -q` with those six paths and `-k` equal to the conjunction of `not <name>` for the following eight existing writer/schema functions (54 parameterized items):
- `test_all_22_true_ambiguities_retain_pre_change_candidate_sets`
- `test_schema_is_additive_idempotent_and_preserves_existing_dates`
- `test_known_official_sec_item_202_samples_resolve_without_sharadar_fallback`
- `test_statuses_precedence_conflict_and_verified_restart_preservation`
- `test_yahoo_history_is_stored_as_secondary_evidence_and_never_selected`
- `test_exact_26_case_replay_preserves_all_52_legacy_candidates`
- `test_copy_universe_no_financial_identity_authority_or_unrelated_state_mutation`
- `test_rank_and_version_do_not_change_default_production_semantics`

They were excluded to honor the explicit prohibition on apply_resolution/enrichment writers even in copies. Their candidate-preservation requirements are additionally checked through pure full-payload comparisons (3 known positives, 44 legacy ambiguities and 52 Policy V1 legacy candidates), exact VERIFIED snapshots and unchanged writer/restart source. No apply_resolution, enrichment writer, DB schema writer, Preview/Test/Production or drain was called. No targeted failure justified a full suite. Only compact test excerpts/frames are committed; raw payloads remain outside the repository.

## 14. Runtime invariance and frozen artifacts

Before/after snapshots use the normal UI-operation, Production and scheduler kernel lock files through read-open handles without rewriting owner metadata or file contents. No recovery or workflow runs. SQL uses mode=ro and query_only. Verification at `2026-10-28T12:38:04.574942+00:00` passed for all eight baseline hashes and the exact frozen regression generation. Unrelated pre-existing worktree changes are preserved.

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


| Temporary artifact under /tmp/publication_passive_future_event_guard (not committed) | SHA-256 |
| --- | --- |
| replay_before.json | 4eee0c11733323883d1b6cb89de2be89a4a86df0b5fd7dc022c377b89f0df5fd |
| replay_after.json | 21fbc22b7cb702031a71252c0e8f6ce29e3013495138cc142b083af1d150f3ae |
| defect_trace_before.json | be070901914610bd5c218c4cc88194c66cde6a55ed3daccb736a8125b48e85f9 |
| tsla_parent_after.json | ba5c787dada9f36fceab4fecde3cbe3e9129502436fa8c5df88322b8df538b42 |
| fixture_comparison.json | 458b51afda338a8fad8c5a8bbae68520b8fcb033cb0d13d5bef2d8b3453c56b5 |
| verification.json | 0864b5cd283b0ec77980d65e471f93a22dbaa9d2b35ab438e74513d609ab2f7a |

The baseline preserves both complete TSLA candidates and the source-text trace before edits. The after artifacts preserve the exact retained candidate and per-parent rejection checks. The original review payload hashes/capture identities are reused; no network refresh, source substitution, timestamp correction or payload mutation occurred. No provider/canonical/analysis, active generation, watermark, Review Queue, journal, scheduler or backup mutation was performed. No live evidence/authority or reviewed decision was written.

## 15. Git scope

Commit only the bounded sec_result_context source change, the updated compact lexical TSLA test, the new focused modality tests and this report. No DB, raw SEC payload, temporary fixture, runtime artifact, cache, log, manifest, journal, queue, unrelated worktree change or push is included.

## 16. Exactly one recommended next phase

**PUBLICATION-AUTHORITY-HELE-TLRY-EVENT-VETO-REVIEW-1 — review the exact actual-result unit versus forward-looking boilerplate/business-line keyword veto for the two still-held cases.** Reuse the frozen HELE and TLRY evidence, the strict TSLA one-candidate negative, lexical gains and VERIFIED preservation contract. Determine a separately reviewable boundary for the old global anticipation/distribution veto without changing acquisition, financial scope, period matching or genuine future/distribution-only rejection. This recommendation does not implement or authorize that later change, and does not apply the current TSLA proposal.
