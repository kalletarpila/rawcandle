# WFRD Test on copies — 2026-10-27

Task: WFRD-TEST-AUTHORIZATION-1. Starting HEAD: `302468110463196adf3e1af0e7babfff3c6d070b`.

**Result: Test COMPLETED on copies. Production authorization measured AUTHORIZED / MATCHING_SUCCESSFUL_TEST_VALIDATED, and not exercised. WFRD candidate checks PASS. Active financial state, generation, watermark, scheduler configuration, and WFRD approval are unchanged.**

Governing evidence: [combined approval/history](wfrd_combined_preservation_approval.md), [OPEN receipt binding](wfrd_open_receipt_binding.md), and [approval confirmation contract](wfrd_approval_confirmation_contract.md). This phase authorizes Test on copies only. No Production, Full workflow, replacement Preview, publication cleanup, or backup acceptance is authorized or invoked.

## Exact Preview and approved resolution

The sole Preview authority is `20261027T101828Z_refresh_fundamentals_052a88da4fba`, fingerprint `777f76d7ba4750772307fdb39f1545bfd6ce760e2fe78cd952e2f7069ab715e9`. The stored outcome is COMPLETED, trigger MANUAL, workflow mode PREVIEW_ONLY, with 94 safe effective changes, 0 global blockers, 0 local holds, 0 review required, and Test authorized with reason SAFE_CHANGES_TEST_AUTHORIZED. The count was checked, not forced. No older scheduler Preview was used.

The live WFRD item remains APPROVED under operator `kalle`, with no stale/rejection reason:

- Resolution: `boundary_3446e01f1422ebb5f7b3ea9e4a7e0f194cb5c8503669e5ed06b515659d0d1f5d`.
- Proposal: `0ddf1bdf2b398145521d990ed4a468e7a23a38e58ebfaf719f5f1484efc5ce34`.
- Registered V2 receipt: `b154760b9e948ce98e5515a661e1df8b87de91fddf2dffe92b934804bcdb07b3`.
- Decision: `be718f56947cc3774bcd4fa9567620d4bf94511a704b503d59ffc9e086b71865`.
- Ordered actions: PRESERVE_ACCEPTED_FISCAL_IDENTITY; RETAIN_REMOVED_ACCEPTED_MRQ_AS_HISTORICAL_SOURCE.

Current decision and durable receipt-binding verifiers pass. The exact Preview embeds the same approved decision with applied true / stale false.

## Operational and source preflight

The scheduler's status reports no active run. The administration operation lock and the production/scheduler exclusion locks were acquired without contention and held for preflight and Test. Acquiring exclusion locks is a guard, not a Production update. The taxonomy operation lock was available and successfully probed through its normal context; the Test later owns its normal protected taxonomy-read lifecycle.

Active generation resolves cleanly. No `.preparing` generation or blocking Refresh Test lane exists. Twenty-five old unrelated temporary lane entries were recorded and left untouched. The publication journal is terminal: COMPLETED, activation ACTIVATED_AND_VERIFIED, postflight PASSED, rollback/recovery NOT_REQUIRED. No recovery path was invoked.

`refresh_copy_runtime._load_bound_preview()` accepted the exact saved Preview and fingerprint. Before starting Test, the existing `revalidate_bound_source()` mechanism fetched/recompared the complete authorized source set, including schema, discovery, state, all source histories, merge/partition evidence, and approved accounting decisions. It returned the exact Preview refresh-set fingerprint and 94 changed tickers. WFRD remained NEW_QUARTER_AND_REVISION, applied true / stale false, with its exact approved decision. No custom source comparison, replacement Preview, new approval, or source override was used.

The normal Test then performs its own fresh source revalidation before copying. Market/taxonomy evidence is governed by the existing stable market-source bundle and protected direct taxonomy-read contracts; final measured binding evidence is recorded below with the terminal result.

## Normal Test execution

The normal `refresh_copy_runtime.run_apply()` path ran with the exact Preview path/fingerprint, `confirm_apply=True`, trigger MANUAL, the normal Sharadar client, and normal run/temp roots. Test run ID: `20261027T105748Z_refresh_fundamentals_f3c7e2a627f5_test`.

A read-only progress callback captures WFRD candidate invariants after canonical validation and again before normal cleanup, retaining the evidence in the Test's `wfrd_candidate_validation.json`. It does not replace source authorization, alter candidate data, or invoke another workflow. The normal backend remains responsible for full provider/canonical/downstream validation, Production-authorization measurement, and removal of its own disposable lane. Terminal outcome and measured candidate results follow below.

## Measured provider and canonical candidate validation

Test's own fresh source revalidation passed the exact authorized refresh-set binding before creating copies. Provider replacement/validation passed. Independent read-only checks on the actual Test provider candidate verified SQLite quick/FK integrity, exact installed approved WFRD decision, and these source meanings:

| Observation | Candidate state |
| --- | --- |
| `(WFRD, ARQ, 2020-03-16, 2019-12-31)` | Native raw 2020-Q4 retained; exact reviewed effective 2019-Q4 |
| Genuine `(WFRD, ARQ, 2021-02-19, 2020-12-31)` | Separate native observation / genuine 2020 Q4 |
| Old `(WFRD, MRQ, 2019-12-31, 2019-12-31)` | Exact original acquisition/native evidence archived in reviewed_historical_provider_observation; HISTORICAL_ONLY / SUCCESSOR_YEAR_END_STOCKS; calculation eligible false; absent from current/native history |
| Current `(WFRD, MRQ, 2019-12-13, 2019-12-13)` | Present in 32-row current MRQ view; PREDECESSOR / PARTIAL_PERIOD_FLOW; all bound calculation eligibility flags false |

The archive's original record equals the approved proposal's accepted evidence, including its original identifiers/content and legacy nulls. Current MRQ's normalized native row equals the bound incoming row; every context field matches. No null filling, share fallback, stock fallback, or MRQ hybrid was constructed. The candidate's installed decision equals the approved live queue decision. These installations are confined to the Test copies.

After canonical rebuild, independent candidate quick/FK and duplicate-key checks passed. Both required Q4s survive:

| Quarter | Period end | Availability / first-public date |
| --- | --- | --- |
| 2019 Q4 | 2019-12-31 | 2020-03-16 / 2020-03-16 |
| 2020 Q4 | 2020-12-31 | 2021-02-19 / 2021-02-19 |

All 27 pre-existing WFRD quarter identity/value/date projections remain unchanged, allowing only the implementation's internal ID/timestamp/raw-label differences. WFRD has 28 quarters after the legitimate new 2026 Q3 is added under normal current-source rules. Its addition is not a preservation side effect.

Across the full authorized set, canonical impact is 89,792 unchanged existing quarters, 178 changed existing quarters, 86 new quarters, 0 removed quarters, and 0 unexplained unaffected changes. All 89,970 established first-public dates were preserved; historical bootstrap changes and repairs are 0. There are 21 source-availability changes across independently authorized fresh source revisions; WFRD's established quarter availability/first-public dates do not drift. New-quarter first-public dates are initialized 86 times through the existing canonical policy.

## Parent-equity / P/B and review evidence

Every one of WFRD's 327 candidate financial provenance rows joins to ARQ, including shares. Candidate 2019 Q4 shares are 69,999,966 from the exact ARQ observation, not the predecessor MRQ weighted-share value 1,004,000,000. The shares and P/B source observation IDs agree for each required Q4 and differ across the two genuine source periods.

The 2019 Q4 P/B source remains ARQ with raw 2020-Q4, effective 2019-Q4, and exact resolution ID. Genuine 2020 Q4 remains an independent ARQ/effective 2020-Q4 binding without the old-period resolution. No MRQ P/B/share authority, P/B formula change, ownership-policy change, Policy V1 change, or resolver change was introduced.

The normal canonical refresh has generated an unrelated DHR ownership continuation case: `02d04d87dd80c0a3dab8dd153bc1f32afe8191e9eda8c1b016bab3a713f948d3`, status OPEN, classification CONTINUATION_CANDIDATE, current P/B status OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED. Its quarter/provenance changed; shares changed by 544,761 (0.0774924%), with no identity/category/provider-factor change. The normal recommendation is separate inspection and explicit continuation approval or continued hold. This task does not approve it. Five ownership cases are now OPEN in total (GM, GE, RTX, T, DHR); no WFRD case was generated. Existing GM case observation metadata was refreshed by the normal Test; WFRD's combined approval is a separate unchanged decision.

The actual copy checks are retained in `wfrd_provider_validation.json`, `wfrd_candidate_validation.json`, and `wfrd_shares_pb_validation.json` in the Test run directory. They are runtime evidence, excluded from the documentation commit.

## Full package and current read-only source bindings

The normal Test completed its source binding and full V2/RP/RV rebuild using the existing contracts, with no source override:

| Binding | Measured evidence |
| --- | --- |
| Fundamentals refresh set | Exact Preview fingerprint `777f76d7ba4750772307fdb39f1545bfd6ce760e2fe78cd952e2f7069ab715e9`; 94 authorized changed tickers |
| Market mode / contract | STABLE_SOURCE_BUNDLE / FUNDAMENTALS_READ_ONLY_SOURCE_V1 |
| Market as-of date | 2026-10-27 |
| Market semantic fingerprint | `70ac1b42b6258e69a9e2ab8da86db0112172dc4e68f94cc0769adf9d7788796c` |
| Market schema fingerprint | `e2119e82a1fddbada8d486b4faaa0b0f22f3ad50823034171a561fa8ff68826f` |
| Compact bundle coverage | 157,901 price rows; 6,447 split rows; 5,068 ticker metadata rows |
| Candidate canonical market binding | `4767840493558e35b09c760c3f5ca5bc8705aaf8c9d8b28e865a97e4d199d2f6` |
| Taxonomy mode | DIRECT_LOCKED_READ, authoritative lock held for consumer lifetime |
| Taxonomy domain / version | dc_ecosystem / DC_TAXONOMY_FULL_V2_1 |
| Taxonomy semantic fingerprint | `801698f6b352c445cc8e6f5fd51a1cac2779d11f6ce72a1c10bf71bb8aae4559` |
| Taxonomy membership rows | 350 |

The market bundle is 15,212,544 bytes and was built/validated through the current stable read-only contract. Taxonomy stayed protected by the actual Test's direct-read lock; it was not independently copied or edited. These are the normal Test's current consumer bindings, not invented additional source comparisons or a replacement Preview. The durable Test source-binding evidence matches its result and the normal Production-authorization reader accepts the recorded contract/binding evidence.

Full downstream result is READY. Invocation counts are exactly one each for full_v2_rebuild, package, relative_position, and relative_valuation. V2 package outcome is APPLIED **inside the candidate**. Package validation reports ok true, quick_check ok, 0 duplicates, 0 orphans, and no foreign-key violations. Independent final candidate analysis quick/FK checks also pass.

RP snapshot `c9152b1f63cd2efb4bddee0de67149df7d635283f0ae69e968045fc45d0d41ba` was built and validated. RV snapshot `99e8d0da082ad9bc6d5b614aaa8d149d99091232c606d2ce79906cbc9916f69d` has outcome ACTIVATED **inside the candidate**, with 2,443 company results. Active model family remains OPERATING_INCOME_MODEL_FAMILY_V2. No P/B formula, ownership policy, structural resolver, or scoring formula was changed.

The final pre-cleanup WFRD inspection repeated every provider/canonical/analysis invariant successfully. The candidate provider/canonical/analysis were healthy, the exact approved decision was installed only on the provider copy, both MRQ observations remained calculation-ineligible in their separate roles, and all required Q4/date/P/B checks remained PASS.

## Terminal Test and Production authorization measurement

| Field | Exact terminal result |
| --- | --- |
| Test run ID | `20261027T105748Z_refresh_fundamentals_f3c7e2a627f5_test` |
| Bound Preview run ID | `20261027T101828Z_refresh_fundamentals_052a88da4fba` |
| Bound Preview fingerprint | `777f76d7ba4750772307fdb39f1545bfd6ce760e2fe78cd952e2f7069ab715e9` |
| Mode / trigger | COPY_ONLY_APPLY / MANUAL |
| Test start / result completion | 2026-10-27T10:57:48Z / 2026-10-27T11:13:45Z |
| Normal cleanup / terminal checkpoint | Completed at 2026-10-27T11:13:49Z |
| Outcome / operational decision | COMPLETED / TEST_COMPLETED |
| Effective changed tickers | 94 |
| Held/local / global blockers / refresh review required | 0 / 0 / 0 |
| Source revalidation | PASS, exact refresh-set/partition/schema/source/approval binding |
| WFRD resolution applied / stale | YES / NO |
| V2 / RP / RV | READY package / validated RP snapshot / candidate RV ACTIVATED |
| Production authorization | AUTHORIZED |
| Production authorization reason | MATCHING_SUCCESSFUL_TEST_VALIDATED |
| Production writes | 0 |
| Production executed | NO |

The existing normal Test path measured Production authorization. A separate read-only `load_production_authorization()` call also accepted the exact saved Preview/Test pair after terminal cleanup. No Production workflow function was called and no publication write boundary was crossed. The normal recommended action is REVIEW_PRODUCTION_AUTHORIZATION, not automatic publication.

The refresh review-required/hold counts are distinct from the typed P/B ownership cases reported above. DHR's newly OPEN P/B case remains unapproved under its existing presentation/ownership policy; it did not change WFRD's combined approval or this measured normal Production gate. No unrelated review approval was granted.

## Production invariance and cleanup

Before/after full file hashes and published-state reads confirm the following authorities are unchanged:

| Authority | Unchanged SHA-256 |
| --- | --- |
| Provider | `cadd3a90f40e0320558b7a6e4de14deb06c77373b9cf3ed81fbb22d26d69dac8` |
| Canonical | `02a13632b45008734ff6078e4e8ba717778bc261471febae504908f951c66b6b` |
| Analysis | `e984fe99df5a3683e76ad9fe9a3dd5c6f55f87d530ef7ca0a30ac5cbb9436adf` |
| Active / generation manifest | `f07a6022eb747f10dc4211b996ffd4fa52bcc5a3393fcc57f32c4cc931a47401` |
| Publication journal | `855a3619dc5bc109abc6f74d7705d6237a1ee0c779da4b5fe9f7824a0979b9f2` |
| Scheduler config | `3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894` |

Active generation remains `refresh_20261022T043408Z_refresh_fundamentals_bb23ca223d59_production_eb6f648d`; watermark remains `2026-10-21`. Published Q4 rows, established dates, identity, WFRD P/B/field provenance, and journal state match the baseline. No historical MRQ archive or reviewed ARQ decision was installed in active provider storage. WFRD's live queue item and decision are exactly unchanged, APPROVED/non-stale under operator kalle.

The queue hash changed from `b3955d6c874113b9db9e6067a61517a4fa22d45485f702a08d040d314ae738b0` to `d92e21f51d002fe6d9093f1db0da0b02d062fe466217b7285d19ddbbb680c17d` through normal typed P/B case creation/observation updates. This is operational review evidence, not a change to WFRD approval or a financial publication.

Normal Test cleanup removed only its own phase-owned lane, including the provider/canonical/analysis candidates and compact market bundle. All 25 pre-existing unrelated lane entries remain. Required reports and validation evidence remain under `fundamental_reports/admin_runs/20261027T105748Z_refresh_fundamentals_f3c7e2a627f5_test/`, including normal result/source/replacement/canonical/downstream evidence and the three additional WFRD validation JSON files. The taxonomy lock was released normally. No manual candidate cleanup, backup deletion, publication cleanup, or rollback-backup acceptance occurred.

## Stop before Production

**Production authorization was measured and not exercised.** This task ends after Test. The next phase is a separate operator decision on Production using this exact Preview/Test pair, with the normal fresh source, market/taxonomy, approval, lock, journal, and candidate/publication preflight. The DHR P/B ownership continuation remains a separate OPEN review; this Test does not approve it.

No repository pytest or full suite ran because source was unchanged. Only this Test/validation report is committed. Candidate DBs, downloads, runtime reports/evidence, queue, manifests, journal, logs, caches, and unrelated work remain outside the commit. Nothing is pushed.
