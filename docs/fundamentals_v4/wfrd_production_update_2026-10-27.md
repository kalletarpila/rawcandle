**Current result — Stage 2: Production COMPLETED; atomic generation activation and postflight PASS. Explicit operator YES was received after Stage 1. OLD and three verified rollback backups are retained. Earlier STOP and Stage 1 consent records are preserved below; the completed Stage 2 record follows them.**

# WFRD Production authorization — stopped before consent

Task: WFRD-PRODUCTION-AUTHORIZATION-1. Date: 2026-10-27. Starting HEAD: `fb90d46854fd94c77a338a41f616bd696fd885fd`.

**STOPPED_SOURCE_DEFECT. Production preflight cannot pass. No Production authorization question was presented, no Production operation was invoked, and no publication boundary was entered.**

The request explicitly requires stopping on a source defect and making it a separate implementation phase. The defect below was found during the required narrow review of the actual Production candidate path, before fresh network/source/bundle work or any runtime mutation. No source was modified and no pytest/full suite ran.

Governing evidence: [Test on copies](wfrd_test_on_copies_2026-10-27.md) and [approved WFRD review history](wfrd_combined_preservation_approval.md).

## Exact authority inspected

| Field | Stored/verified evidence |
| --- | --- |
| Preview | `20261027T101828Z_refresh_fundamentals_052a88da4fba` |
| Preview fingerprint | `777f76d7ba4750772307fdb39f1545bfd6ce760e2fe78cd952e2f7069ab715e9` |
| Test | `20261027T105748Z_refresh_fundamentals_f3c7e2a627f5_test` |
| Test outcome | COMPLETED |
| Stored authorized effective changes | 94 |
| Stored Production gate | AUTHORIZED / MATCHING_SUCCESSFUL_TEST_VALIDATED |
| WFRD resolution | `boundary_3446e01f1422ebb5f7b3ea9e4a7e0f194cb5c8503669e5ed06b515659d0d1f5d` |
| WFRD proposal | `0ddf1bdf2b398145521d990ed4a468e7a23a38e58ebfaf719f5f1484efc5ce34` |
| Registered V2 receipt | `b154760b9e948ce98e5515a661e1df8b87de91fddf2dffe92b934804bcdb07b3` |
| Approved decision | `be718f56947cc3774bcd4fa9567620d4bf94511a704b503d59ffc9e086b71865` |
| Current queue item | APPROVED / operator kalle / no stale or rejection reason |

The existing read-only `load_production_authorization()` accepts this exact saved Preview/Test pair and its durable Test evidence. Decision integrity verification passes. The stored AUTHORIZED gate is preserved; it is not relabeled or treated as operator permission. It also does not prove that the separate Production builder installs WFRD semantics correctly.

## Blocking Test-versus-Production candidate construction gap

The successfully tested copy path passes the applied decisions explicitly:

```python
# refresh_copy_runtime.py:1184, normal Test candidate construction
replace_provider_histories(
    provider_candidate, selected_histories, identities,
    applied_at=applied_at, merge_plans=selected_merge_plans,
    boundary_applications={
        item["ticker"]: item["accounting_boundary_resolution"]
        for item in changed
        if (item.get("accounting_boundary_resolution") or {}).get("applied")
    },
)
```

The actual Production path omits that argument:

```python
# refresh_production.py:952, normal Production candidate construction
replace_provider_histories(
    provider_candidate, histories, identities,
    applied_at=utc_now(), merge_plans=merge_plans,
)
```

In `refresh_copy_runtime.py:400`, `boundary_applications` defaults to None. The loop over that argument is the mechanism that verifies candidate inputs and calls `boundary.install_on_copy(provider_db, application["decision"])` before native histories are replaced. That installation creates the immutable historical MRQ evidence, current MRQ context, and reviewed ARQ interpretation/decision store on the inactive provider copy.

The current published provider has **zero installed reviewed decisions and zero historical MRQ archive rows**, as expected before publication. Production backs up that published provider to construct its fresh candidate; it does not inherit the deleted Test candidate. No alternate accounting-boundary installation call exists in `refresh_production.py`. Consequently the Production call shown above cannot install the required approved WFRD resolution/archive/context through this path, even though source revalidation can recognize the approved decision in memory.

This is a real missing candidate-installation step, distinct from an approval or presentation problem. Without the installed decision, the incoming native ARQ 2020-Q4 label has no reviewed effective 2019-Q4 projection in that candidate, and the removed MRQ has no required historical-only archive/context installation. The required Production semantics cannot be certified. No claim is made that incorrect data was actually published or that later candidate checks would necessarily permit publication: the Production path was not run.

The omission must be fixed and validated in a separate bounded implementation phase. The natural parity fix is to pass the validated applied accounting-boundary applications into the Production provider builder, as Test does, and verify the expected decision/archive/context explicitly in candidate and postflight checks. Regression evidence should cover raw/effective ARQ identity, both genuine Q4s/dates, historical/current MRQ separation, calculation exclusions, and ARQ P/B/share provenance through the real Production candidate path on disposable copies. No manual installation into active provider/canonical storage is an acceptable substitute.

## Read-only closeout and untouched state

Fresh local hashing matches the completed Test's closeout for provider, canonical, analysis, active/generation manifests, journal, and queue. Scheduler config was hashed separately for closeout. The active generation remains `refresh_20261022T043408Z_refresh_fundamentals_bb23ca223d59_production_eb6f648d`; watermark remains `2026-10-21`. Journal state/step remain COMPLETED, activation ACTIVATED_AND_VERIFIED, postflight PASSED, recovery NOT_REQUIRED.

The live WFRD decision remains APPROVED and unchanged. DHR's exact P/B review remains OPEN and unchanged; the entire live queue hash remains `d92e21f51d002fe6d9093f1db0da0b02d062fe466217b7285d19ddbbb680c17d`. No review mutation, source fetch, candidate build, Preview, Test, Production, journal preparation, generation activation, backup creation/deletion, recovery action, or publication-authority workflow was performed in this attempt.

| Stage 1 gate | Result |
| --- | --- |
| Exact saved Preview/Test authorization reader | PASS |
| Stored WFRD decision integrity/status | PASS; external current-source freshness not revalidated after stop |
| Fresh full source revalidation | NOT RUN after source-defect stop |
| Fresh market semantic/bundle comparison | NOT RUN after source-defect stop |
| Fresh taxonomy binding comparison | NOT RUN after source-defect stop |
| Full operational lock/storage/publication preflight | Not completed after source-defect stop |
| Production preflight | FAIL_SOURCE_DEFECT |
| Production consent question / explicit Production YES | Not presented / not received |
| Production run / publication boundary | None / not entered |
| Active generation / watermark / financial state changed | NO / NO / NO |

The stopped attempt does not assert fresh WFRD source validity from a stored non-stale flag. The recorded market/taxonomy/source PASS results remain historical Test evidence and are not reused as new Production preflight results. DHR's OPEN case is not the cause of this stop; no new global blocker interpretation was invented for it.

## Next phase and commit scope

Implement and validate the bounded Production candidate parity fix separately, then restart this Production task from Stage 1. Freshly revalidate the exact saved Preview/Test pair and current source/market/taxonomy/baseline under the existing contract; stop if stale. Only after every Stage 1 gate passes should the one exact Production YES/NO question be presented. This report supplies no Production consent and authorizes no replacement Preview/Test.

Only this stopped-authorization report is committed. No DB, manifest, journal, queue, download, runtime evidence, backup, cache, or unrelated work is included. Nothing is pushed. The proposed successful-publication commit title is not used because no publication occurred.

## Stage 1 restart after Production candidate parity fix

Task: WFRD-PRODUCTION-AUTHORIZATION-1-STAGE1-RESTART. Date: 2026-10-27. Validated source HEAD and parity commit: `310429b622ac31efb66cf94ad9414c7c3430f5e4`. The historical source-defect STOP above is preserved. That defect was separately fixed by `310429b622ac31efb66cf94ad9414c7c3430f5e4`; this section records a fresh Stage 1 run after that fix.

**Stage 1 PASS; awaiting new explicit Production YES/NO. Production has not executed, no publication boundary was entered, and live authorities are unchanged.** All Stage 1 gates passed before presenting the question below. This task did not run repository pytest or the full suite and did not change source.

### Exact saved authority and current approval

| Field | Freshly checked evidence |
| --- | --- |
| Preview | `20261027T101828Z_refresh_fundamentals_052a88da4fba` |
| Preview fingerprint | `777f76d7ba4750772307fdb39f1545bfd6ce760e2fe78cd952e2f7069ab715e9` |
| Test | `20261027T105748Z_refresh_fundamentals_f3c7e2a627f5_test`; COMPLETED / MANUAL / COPY_ONLY_APPLY |
| Preview result | COMPLETED / MANUAL / PREVIEW_ONLY; SAFE_CHANGES_TEST_AUTHORIZED |
| Exact authorized set | 94 effective changed tickers; exact ticker list and binding match saved Test, not just count |
| Review partition | 0 held/local; 0 global blockers; 0 refresh REVIEW_REQUIRED |
| Production authorization loader | PASS on exact saved pair; no prior linked Production execution found |
| Production gate | AUTHORIZED / MATCHING_SUCCESSFUL_TEST_VALIDATED |
| WFRD resolution | `boundary_3446e01f1422ebb5f7b3ea9e4a7e0f194cb5c8503669e5ed06b515659d0d1f5d` |
| Proposal | `0ddf1bdf2b398145521d990ed4a468e7a23a38e58ebfaf719f5f1484efc5ce34` |
| Registered V2 receipt | `b154760b9e948ce98e5515a661e1df8b87de91fddf2dffe92b934804bcdb07b3` |
| Decision | `be718f56947cc3774bcd4fa9567620d4bf94511a704b503d59ffc9e086b71865`; APPROVED / operator kalle; no stale or rejection reason |

Ordered actions remain `PRESERVE_ACCEPTED_FISCAL_IDENTITY`, `RETAIN_REMOVED_ACCEPTED_MRQ_AS_HISTORICAL_SOURCE`. Current decision/receipt verification passed. Full normal source revalidation fetched COMPLETE current histories and ran the existing current-state accounting-boundary verifier: applied=true, stale=false, exact approved decision. Identity/company/security/permaticker, exact ARQ acquisition, MRQ absence/current evidence, established canonical Q4/date and P/B binding all remain valid.

### Operational guards, baseline, and full source revalidation

Scheduler status was idle. The normal Fundamentals operation lock and Production/scheduler exclusion locks were acquired without contention and held throughout preflight. The taxonomy lock was available through its normal probe, then held through binding and candidate consumption. Journal state/step were COMPLETED / COMPLETED; activation ACTIVATED_AND_VERIFIED; postflight PASSED; rollback/recovery NOT_REQUIRED. The normal recovery guard returned terminal COMPLETED without recovery. Active OLD resolved as `refresh_20261022T043408Z_refresh_fundamentals_bb23ca223d59_production_eb6f648d`, with watermark `2026-10-21`. No preparing generation or blocking Refresh lane existed; all 25 pre-existing unrelated lane entries were preserved.

Before candidate work, the baseline captured HEAD, the complete worktree state, role/manifests/journal/queue hashes, watermark, WFRD approval, all P/B cases including DHR, Q4 identities/dates, and P/B/share provenance. The pre-existing dirty journal and unrelated untracked work were recorded and left untouched. No cleanup or workaround was applied to them.

The unchanged `load_production_authorization()` accepted the exact artifacts. Production's existing `revalidate_bound_source()` then checked current published state, source schema, discovery, every known evaluated ticker's complete ARQ/MRQ histories, ordinary approvals, reviewed WFRD evidence, merge plans, partition, and exact refresh-set fingerprint. The fresh fingerprint equals the saved Preview/Test fingerprint. The current 94-member replacement list equals the saved Test list exactly; 94 was checked, not forced. A second complete source revalidation after candidate analysis passed the same binding and exact selected boundary applications. No WFRD-only shortcut or replacement Preview/Test was used.

### Active parity path and complete disposable candidates

Git ancestry and byte equality of all three parity source files against the parity commit passed. Current Production derives applications from freshly revalidated `ticker_changes` filtered to replacement classes, using the shared pure extraction helper; it selects exactly WFRD, excludes non-applied entries, and forwards that embedded application through `build_provider_candidate()` into `replace_provider_histories()`. No independent queue approval selection or manual post-replacement installation was introduced.

Disposable lane: `/tmp/wfrd_production_stage1_restart/candidate`. The actual fixed Production provider helper, actual fresh canonical rebuild, compact source-binding helper, and full Production V2/RP/RV helper ran against the entire freshly revalidated authorized set. Canonical ownership maintenance used a copied queue; live source revalidation only read live queue evidence. The provider candidate retained unrelated source state unchanged and installed the exact reviewed decision, archive, and context. Candidate refresh state proposed watermark `2026-10-26` only in the disposable DB; live watermark stayed unchanged.

| WFRD candidate invariant | Result |
| --- | --- |
| Preserved ARQ source | `(WFRD, ARQ, 2020-03-16, 2019-12-31)`; raw 2020-Q4, effective 2019-Q4 |
| Genuine 2020 Q4 | Separate `(WFRD, ARQ, 2021-02-19, 2020-12-31)`; effective 2020-Q4; no borrowed preservation resolution |
| Historical MRQ | Exact original Dec 31 record archived; HISTORICAL_ONLY / SUCCESSOR_YEAR_END_STOCKS / calculation=false; absent from native/current history |
| Current MRQ | Exact Dec 13 observation; PREDECESSOR / PARTIAL_PERIOD_FLOW; calculation/full-quarter/canonical/TTM/P/B/share/stock-fallback=false |
| Acquisition integrity | Exact normalized/acquisition evidence; no hybrid or null filling; 32 current MRQ rows |
| Canonical 2019 Q4 | Period end 2019-12-31; availability/first-public 2020-03-16 |
| Canonical 2020 Q4 | Period end 2020-12-31; availability/first-public 2021-02-19 |
| Existing WFRD quarters | All 27 preserved; no unexpected existing financial/identity/date change or loss |
| Current-source addition | WFRD 2026 Q3 added normally, first-public 2026-10-21; distinct from preservation effect |
| Parent-equity/share/P/B | 327 financial provenance rows are ARQ; zero MRQ authority; exact separate Q4 share/P/B observation IDs match saved Test |
| P/B reviewed binding | Raw 2020-Q4 / effective 2019-Q4 / exact resolution; genuine 2020 Q4 remains independent |
| Saved Test parity | WFRD quarter/date/P/B/share projections match, ignoring internal quarter IDs |

Full canonical impact matches saved Test: 89,792 unchanged existing quarters, 178 changed existing, 86 added, 0 removed, and zero unexplained unaffected changes. All 89,970 established first-public dates were preserved; 86 new dates follow normal policy. There are 21 independently authorized source-availability changes, no historical bootstrap/repair, and zero duplicate quarter keys. WFRD established Q4 dates do not drift. Company/security mappings match before/after.

### Fresh market, taxonomy, and downstream package

The normal semantic comparator returns **MATCH**, no differing contract sections, for this full 94-ticker candidate versus the exact authorizing Test. This supersedes the parity phase's deliberately WFRD-only diagnostic bundle comparison; no binding rule was weakened.

| Binding | Current measured value |
| --- | --- |
| Market mode / contract | `STABLE_SOURCE_BUNDLE` / `FUNDAMENTALS_READ_ONLY_SOURCE_V1` |
| Market semantic fingerprint | `70ac1b42b6258e69a9e2ab8da86db0112172dc4e68f94cc0769adf9d7788796c` |
| Market schema fingerprint | `e2119e82a1fddbada8d486b4faaa0b0f22f3ad50823034171a561fa8ff68826f` |
| Canonical valuation requirements | 89,586; exact Test-compatible canonical binding |
| Taxonomy mode / domain / version | `DIRECT_LOCKED_READ` / `dc_ecosystem` / `DC_TAXONOMY_FULL_V2_1` |
| Taxonomy semantic fingerprint | `801698f6b352c445cc8e6f5fd51a1cac2779d11f6ce72a1c10bf71bb8aae4559`; 350 memberships |

Full V2 status is `READY`. Full rebuild/package/RP/RV each ran once. RP snapshot `c9152b1f63cd2efb4bddee0de67149df7d635283f0ae69e968045fc45d0d41ba` validates; RV outcome `ACTIVATED` is confined to the disposable candidate, snapshot `99e8d0da082ad9bc6d5b614aaa8d149d99091232c606d2ce79906cbc9916f69d`. All three candidates passed quick_check and FK checks, canonical identity checks, publication-date checks, and normal analysis-generation/cross-role/taxonomy validation. `validate_expected_store()` passed against provider and canonical after downstream work, establishing the expected boundary-state postflight precondition, including missing-state detection. No live post-publication postflight is claimed.

All seven V2 calculation fingerprints (delta, diagnostic, lifecycle, relative, score, structural, valuation) also match the saved authorizing Test exactly; the fresh comparison has no differing sections.

### Publication preconditions, DHR, and invariance

Normal `_storage_preflight()` passed: 21,185,335,296 bytes required versus 691,119,702,016 available at measurement. Candidate, generation, and backup roots are writable on the same filesystem. Normal generation ID/role/file/integrity/target feasibility was checked without creating NEW or a journal. OLD and terminal journal were rechecked at closeout. Rollback destination is available; no rollback backup was created or deleted.

Normal read-only `select_candidate_scope()` selected 86 new quarters plus 45 existing recent retries with unchanged 60-day / 100-quarter policy. This is a scope/precondition measurement only: no SEC publication enrichment, historical backlog drain, journal PREPARING, immutable generation preparation, activation, or Production operation occurred. Those normal lifecycle steps remain behind explicit Production authorization.

DHR case `02d04d87dd80c0a3dab8dd153bc1f32afe8191e9eda8c1b016bab3a713f948d3` remains OPEN, approval=null, no operator approval. It is separate from WFRD and is not a global blocker under the measured Refresh partition. No approval, live observation metadata, policy, resolver, scheduler configuration, or ownership formula was changed.

Fresh baseline, midpoint, and final comparisons prove live provider/canonical/analysis, active/generation manifests, publication journal, complete queue schemas/tables and decisions, watermark, WFRD published Q4/date/P/B/share provenance, and scheduler configuration unchanged.

After candidate cleanup, a final normal operation/Production/scheduler/taxonomy guard probe passed again, with scheduler idle and journal clear. Market file metadata remained unchanged from the guarded candidate checks; taxonomy main-file size/mtime still matched the fresh semantic binding, with no pending WAL frames. Existing taxonomy shared-memory reader metadata is normal and is not treated as a source change. All guards were released before asking for consent. Evidence: `final_guard_verification.json` and `source_files_after_candidate_validation.json`.

| Live authority | Before = after SHA-256 |
| --- | --- |
| analysis | `e984fe99df5a3683e76ad9fe9a3dd5c6f55f87d530ef7ca0a30ac5cbb9436adf` |
| canonical | `02a13632b45008734ff6078e4e8ba717778bc261471febae504908f951c66b6b` |
| provider | `cadd3a90f40e0320558b7a6e4de14deb06c77373b9cf3ed81fbb22d26d69dac8` |
| active_manifest | `f07a6022eb747f10dc4211b996ffd4fa52bcc5a3393fcc57f32c4cc931a47401` |
| generation_manifest | `f07a6022eb747f10dc4211b996ffd4fa52bcc5a3393fcc57f32c4cc931a47401` |
| journal | `855a3619dc5bc109abc6f74d7705d6237a1ee0c779da4b5fe9f7824a0979b9f2` |
| queue | `d92e21f51d002fe6d9093f1db0da0b02d062fe466217b7285d19ddbbb680c17d` |
| scheduler_config | `3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894` |

Only this Stage 1 attempt's disposable lane was removed after checks; all existing lanes and Production backups were preserved. Runtime evidence remains at `/tmp/wfrd_production_stage1_restart` (operational/authority/source and final-source JSON, exact set comparison, candidate/source bindings and validation, publication feasibility/scope, before/midpoint/after invariance, cleanup and phase records). It is excluded from Git. Only this appended documentation is committed, with no push.

### Explicit Production authorization gate

All Stage 1 gates passed. No Production answer has been inferred or consumed. Section N of the restart request requires stopping here for a new explicit answer.

Do you authorize the Production update for exact Preview 20261027T101828Z_refresh_fundamentals_052a88da4fba, fingerprint 777f76d7ba4750772307fdb39f1545bfd6ce760e2fe78cd952e2f7069ab715e9, and exact Test 20261027T105748Z_refresh_fundamentals_f3c7e2a627f5_test, using the freshly revalidated authorized change set of 94 safe effective changes and the approved WFRD accounting-boundary resolution boundary_3446e01f1422ebb5f7b3ea9e4a7e0f194cb5c8503669e5ed06b515659d0d1f5d, through the existing Fundamentals Production publication path? YES/NO

YES authorizes only this exact Preview/Test pair, the freshly revalidated safe set, and the already approved WFRD application through the normal Fundamentals Production path. It does not authorize DHR/other review approval, rollback-backup cleanup, historical publication backlog drain, Policy V1 changes, or resolver changes. Before any later publication, critical gates must be freshly revalidated; material source/market/taxonomy/WFRD/baseline authorization drift makes consent stale and requires STOP. This Stage 1 prompt executes no Production.


## Stage 2 — explicit YES and normal Production publication

Task: WFRD-PRODUCTION-AUTHORIZATION-1, Stage 2 after the explicit conversation reply **YES** to the exact Stage 1 question. Starting HEAD: `6e7b65f593eb542cb97cae582c34e8e6d1f67000`. Source/parity commit remains `310429b622ac31efb66cf94ad9414c7c3430f5e4`; no source or policy/resolver change was made. Consent recorded at `2026-10-27T18:43:11Z` after documentation commit `6e7b65f593eb542cb97cae582c34e8e6d1f67000`. Consent and its exact scope were persisted in the Production run's `wfrd_operator_authorization.json`.

**Production outcome: COMPLETED / SUCCESS_WITH_PUBLICATION_PARTIAL. Publication boundary entered: YES. Published generation and independent WFRD validation PASS.** Repository pytest and the full suite were not run.

### Exact authority, post-YES freshness, and execution

| Field | Evidence |
| --- | --- |
| Preview | `20261027T101828Z_refresh_fundamentals_052a88da4fba` |
| Preview fingerprint | `777f76d7ba4750772307fdb39f1545bfd6ce760e2fe78cd952e2f7069ab715e9` |
| Test | `20261027T105748Z_refresh_fundamentals_f3c7e2a627f5_test`; COMPLETED |
| WFRD resolution | `boundary_3446e01f1422ebb5f7b3ea9e4a7e0f194cb5c8503669e5ed06b515659d0d1f5d` |
| Production authorization | Explicit YES; backend AUTHORIZED / MATCHING_SUCCESSFUL_TEST_VALIDATED |
| Production run | `20261027T184515Z_refresh_fundamentals_f3c7e2a627f5_production_72bba2f3` |
| Trigger / mode | MANUAL / PRODUCTION_APPLY |
| Start / completion | `2026-10-27T18:45:15Z` / `2026-10-27T19:06:59Z` |
| Post-YES preflight | PASS; exact Stage 1 baseline and complete source binding remained current |
| Effective changed tickers | 94; exact authorized set, no holds or global blockers |
| OLD | `refresh_20261022T043408Z_refresh_fundamentals_bb23ca223d59_production_eb6f648d` |
| NEW active | `refresh_20261027T184515Z_refresh_fundamentals_f3c7e2a627f5_production_72bba2f3` |
| Published watermark | `2026-10-21` → `2026-10-26` |

After YES, the scheduler was idle; normal Fundamentals, scheduler, Production, and taxonomy guard availability passed. The exact saved Preview/Test loader, WFRD approval/proposal/receipt/decision, complete live queue decisions, active OLD generation, terminal journal, watermark, source code/parity files, scheduler config, and market/taxonomy source files matched the Stage 1 consent baseline. The existing `revalidate_bound_source()` fetched and validated the entire authorized set again, returning the exact fingerprint and exact 94-member ticker list; WFRD remained applied=true/stale=false, with its exact approved decision. No replacement Preview/Test or approval mutation was performed.

The normal `refresh_production.run_production_apply()` backend ran with explicit confirmation and Production intent, normal paths/run/temp/journal/backup roots, MANUAL trigger, and the normal exclusion guards. Reentrant lock handling retained the already-held scheduler/Production guard during the backend call; no lock was bypassed. It independently repeated full source revalidation, built fresh provider/canonical/analysis candidates from OLD, derived WFRD applications from the current validated change set, and performed its final complete source recheck before backups/publication. The Stage 1 candidate was not reused.

Fresh Production market/taxonomy semantic comparison returned **MATCH**, no differing sections: market `STABLE_SOURCE_BUNDLE` / `FUNDAMENTALS_READ_ONLY_SOURCE_V1`, semantic `70ac1b42b6258e69a9e2ab8da86db0112172dc4e68f94cc0769adf9d7788796c`; taxonomy `DIRECT_LOCKED_READ` / `dc_ecosystem` / `DC_TAXONOMY_FULL_V2_1`, semantic `801698f6b352c445cc8e6f5fd51a1cac2779d11f6ce72a1c10bf71bb8aae4559`. Normal storage/recovery/prepublication checks passed. The backend created verified rollback backups, durably prepared the journal, assembled a complete immutable NEW generation, atomically activated its manifest, verified published roles/cross-role lineage, and committed the journal. No manual role copy, manual WFRD installation, policy override, or alternate publication path was used.

### Published WFRD result

| Invariant | Published result |
| --- | --- |
| Preserved ARQ | `(WFRD, ARQ, 2020-03-16, 2019-12-31)`; native raw `2020-Q4`, reviewed effective `2019-Q4` |
| Genuine 2020 Q4 | Separate `(WFRD, ARQ, 2021-02-19, 2020-12-31)`, effective `2020-Q4`; no borrowed preservation resolution |
| Reviewed decision | Exact approved decision installed and auditable; proposal/receipt/approval lineage preserved |
| Historical MRQ | Exact original Dec 31 source evidence archived, HISTORICAL_ONLY / SUCCESSOR_YEAR_END_STOCKS / calculation=false; absent from native/current history |
| Current MRQ | Exact Dec 13 native observation, PREDECESSOR / PARTIAL_PERIOD_FLOW; calculation/full-quarter/canonical/TTM/P/B/share/stock-fallback=false |
| MRQ row integrity | Exact bound incoming acquisition/normalized evidence, no hybrid or null filling; 32 current MRQ rows |
| Canonical 2019 Q4 | Company 2368, period end 2019-12-31, first-public/availability 2020-03-16 |
| Canonical 2020 Q4 | Independent period end 2020-12-31, first-public/availability 2021-02-19 |
| Existing WFRD quarters | All 27 existing identity/value/date projections preserved; none lost or unexpectedly changed |
| Legitimate new quarter | WFRD 2026 Q3 published through ordinary source/initial-date policy, first-public 2026-10-21; separate from preservation effects |
| Share/P/B binding | ARQ source authority, exact preserved resolution binding, genuine 2020 Q4 independent; shares 69,999,966 and 70,017,356 from distinct exact ARQ observations |
| Canonical provenance | 327 WFRD financial provenance rows are ARQ; zero MRQ financial/share/P/B authority |
| Saved Test parity | Published WFRD quarter/date/share/P/B projections match the validated Test, ignoring internal quarter IDs |

The new published generation passed normal expected-boundary-state postflight, followed by independent read-only validation of the published decision/archive/context, source keys, raw/effective identities, both Q4s/dates, all existing WFRD financial projections, and ARQ share/P/B provenance against OLD and saved Test evidence. The live WFRD queue decision remains APPROVED and exactly unchanged; installation is on NEW rather than an edit to that approval.

### Complete financial package and publication authority

Canonical impact: **86 added / 178 changed / 0 removed**, with 89,792 unchanged existing quarters and zero unexplained unaffected changes. All 89,970 established first-public dates were preserved; 86 new dates followed normal policy. Historical bootstrap/repair count is 0. The 21 source-availability changes belong to the separately authorized source revisions; established WFRD Q4 dates did not drift. Company/security identity mappings are unchanged; duplicate quarter keys are zero.

V2 is `READY`, RP snapshot `c9152b1f63cd2efb4bddee0de67149df7d635283f0ae69e968045fc45d0d41ba` validates, and RV outcome is `ACTIVATED`, snapshot `99e8d0da082ad9bc6d5b614aaa8d149d99091232c606d2ce79906cbc9916f69d`. Normal package physical integrity, source lineage, taxonomy dependency, active readers, and cross-role checks passed. All seven calculation fingerprints match the authorizing Test: **YES**.

| Published role | quick_check / FK errors | SHA-256 matching active manifest and journal |
| --- | --- | --- |
| provider | ok / 0 | `5986536f13891e506c7a009269d731fdc7f97d7da87a6544b2390b4ae49e794f` |
| canonical | ok / 0 | `5ec357a3a137b9cf3018c0603e17db191ec30033167fdf5c0f1c199805cc8a0e` |
| analysis | ok / 0 | `2bb68fb3029a6821c098c57b8f314e2af9693e566c030e75d2ee1e02b1d384e7` |

The normal bounded result-publication subworkflow ended **PARTIAL**, separately from core Refresh: 86 new quarters, 45 recent retries selected under unchanged 60-day / 100-quarter policy; 131 processed. Status counts: `{"AMBIGUOUS": 4, "NOT_FOUND": 30, "UNRESOLVED": 16, "VERIFIED": 81}`. Network statistics: `{"candidate_filings_inspected": 107, "candidate_filings_outside_scope_skipped": 4660, "document_requests": 135, "documents_fetched": 135, "metadata_requests": 129, "network_requests": 264, "result_context_exhibits_fetched": 28}`. No scope expansion, manual historical drain, retry-cap change, or resolver/Policy V1 change occurred. A PARTIAL authority outcome is retained as such under the existing core-success contract.

### Journal, backups, cleanup, and invariants

Journal terminal state/step: **COMPLETED / COMPLETED**; generation activation **ACTIVATED_AND_VERIFIED**; postflight **PASSED**; rollback/recovery **NOT_REQUIRED**. Active manifest and the NEW generation manifest identify the same complete generation, and published role hashes match their recorded verification and journal candidate fingerprints. The original OLD generation's provider/canonical/analysis files remain byte-identical to the preflight baseline.

**Three verified rollback backups are retained**, 2,628,214,784 bytes total. Each still exists with the backend's verified SHA-256. No deletion or acceptance was performed.

| Role | Bytes | Retained backup |
| --- | --- | --- |
| provider | 968,331,264 | `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/20261027T184515Z_refresh_fundamentals_f3c7e2a627f5_production_72bba2f3/provider.db` |
| canonical | 749,371,392 | `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/20261027T184515Z_refresh_fundamentals_f3c7e2a627f5_production_72bba2f3/canonical.db` |
| analysis | 910,512,128 | `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/20261027T184515Z_refresh_fundamentals_f3c7e2a627f5_production_72bba2f3/analysis.db` |

The backend's normal terminal cleanup removed its candidate DB/source-bundle/runtime lane. All 25 pre-existing unrelated lanes were preserved. The normal terminal cleanup record and retained backups remain available for a separate explicit acceptance decision.

DHR's P/B review remains **OPEN**, unapproved, with no operator approval. All typed P/B review decision states and approvals remain unchanged. In this run the entire live Review Queue also remained byte-identical: before/after SHA-256 `d92e21f51d002fe6d9093f1db0da0b02d062fe466217b7285d19ddbbb680c17d`, with every queue table/schema fingerprint unchanged. Normal ownership synchronization observed five cases and created zero; no existing legacy approval was finalized. WFRD's approved combined decision is unchanged. Scheduler configuration hash remains `3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894`. No unrelated approval, taxonomy edit, Policy V1 change, resolver change, manual backlog drain, or backup cleanup occurred. The financial generation/manifest/journal/watermark and bounded publication-authority mutations are the authorized Production result.

Runtime evidence: `fundamental_reports/admin_runs/20261027T184515Z_refresh_fundamentals_f3c7e2a627f5_production_72bba2f3/` (normal source/binding/candidate/postflight/result/journal-related reports and explicit consent) and `/tmp/wfrd_production_stage2` (post-YES source/baseline/terminal checks, independent published WFRD and role validation, retained backup verification, manifest/Test semantic comparison). Runtime DBs, manifests, journals, queue, backups, downloads, reports, logs, caches, and unrelated worktree changes are excluded from Git. This documentation is the only commit change; nothing is pushed.

**Next phase:** review the published result and perform a separate explicit rollback-backup acceptance/cleanup decision. The three backups and OLD generation remain retained; this task does not authorize deletion.
