# WFRD Production candidate parity

Task: WFRD-PRODUCTION-CANDIDATE-PARITY-1. Date: 2026-10-27. Starting HEAD: `f8ed243be58c6712206ed6b1baea404e55a0cfa1`.

## Defect reproduced before changes

AST inspection confirmed that Test supplied `boundary_applications` while Production omitted it. On a disposable copy of the WFRD fixture, the pre-fix Production-style replacement produced native raw 2020-Q4 with effective 2020-Q4, zero installed decisions, zero historical archive rows, and zero reviewed contexts. Live provider reads confirmed no installed decision/archive/context to inherit from OLD. This reproduces the [Production stop report](wfrd_production_update_2026-10-27.md); no real Production was invoked.

## Authority and bounded fix

The governing authority remains Preview `20261027T101828Z_refresh_fundamentals_052a88da4fba`, fingerprint `777f76d7ba4750772307fdb39f1545bfd6ce760e2fe78cd952e2f7069ab715e9`, and successful Test `20261027T105748Z_refresh_fundamentals_f3c7e2a627f5_test`. The installed candidate decision is the exact live APPROVED decision `be718f56947cc3774bcd4fa9567620d4bf94511a704b503d59ffc9e086b71865`, operator `kalle`, for resolution `boundary_3446e01f1422ebb5f7b3ea9e4a7e0f194cb5c8503669e5ed06b515659d0d1f5d`. Its proposal fingerprint is `0ddf1bdf2b398145521d990ed4a468e7a23a38e58ebfaf719f5f1484efc5ce34`; its registered V2 receipt fingerprint is `b154760b9e948ce98e5515a661e1df8b87de91fddf2dffe92b934804bcdb07b3`. Ordered actions remain `PRESERVE_ACCEPTED_FISCAL_IDENTITY`, `RETAIN_REMOVED_ACCEPTED_MRQ_AS_HISTORICAL_SOURCE`.

Production's authoritative application source is `revalidated['ticker_changes']`, filtered into `changed` by existing replacement classifications **after normal current-source revalidation**. Both Test and Production now call the same pure `applied_applications(changed)` helper. It selects embedded objects using the existing truthy `applied` rule, preserves the selected objects, excludes absent/false applications, and rejects ambiguous duplicate ticker entries and synthetic copy-only runtime authority. Production never performs an additional queue approval lookup to choose candidate applications.

`refresh_production.build_provider_candidate()` checks that its destination is inactive, then calls the existing replacement routine with that map. The real Production workflow uses this helper immediately after backing up OLD. There is no WFRD ticker/key branch in Production, no post-replacement manual installation, and no reuse of a Test candidate DB. No-application behavior and the underlying native replacement contract remain intact.

The shared installer now validates every selected application before installing any: applied/non-stale phase, exact decision/proposal integrity, ticker alignment, required source keys, exact acquisition evidence, full pending source binding, and absence of new unreviewed related events. Existing decision verification remains authoritative. The current reviewed policy supports the bounded WFRD event only; this work does not invent approvals for other tickers. A dispatch regression proves multiple ticker objects are forwarded generically, while actual installation remains subject to that policy. Multiple independently valid ticker resolutions cannot currently be manufactured under the existing verifier.

## Expected-state validation and postflight

The existing store validator validates records it finds and could accept a store with no decisions. `validate_expected_store()` adds explicit absence detection against the expected embedded applications. It requires exact installed decision equality, including proposal/receipt/approval lineage, and native acquisition payload equality; it reuses existing archive, current context, effective identity, normalized observation ID, membership, and eligibility checks.

With a canonical candidate it additionally requires established Q4 identity/date equality, ARQ parent-equity authority, effective fiscal identity, and exact resolution binding for the preserved source. The genuine next Q4 cannot borrow the preservation resolution. Production checks this state during candidate validation, again after bounded result-publication enrichment, and in published-generation postflight. A regression builds the old defective candidate and proves actual `_postflight()` rejects its missing expected decision. Other regressions reject changed lineage, native payload, established dates, and P/B resolution linkage.

The Production authorization reader's function AST is unchanged, and a read-only call still accepts the exact saved Preview/Test pair. `MATCHING_SUCCESSFUL_TEST_VALIDATED` has not been weakened. The generation, journal, backup, activation, rollback/recovery, publication policy, resolver, ownership policy, and P/B formulas are unchanged.

## Disposable real-data rehearsal

Evidence directory: `/tmp/wfrd_production_parity1/`; inactive candidate directory: `/tmp/wfrd_production_parity1/real/`. These runtime files and DBs are excluded from Git. The rehearsal used current active provider/canonical stores, freshly fetched COMPLETE WFRD ARQ/MRQ responses, the current identity resolver, and read-only combined-review revalidation. The application was applied=true, stale=false, with the exact approved decision.

The actual fixed Production provider helper built an inactive candidate from OLD with the revalidated WFRD change and ordinary merge plan. A second disposable provider used the Test installer from the same OLD input and the same object. Full semantic projections matched for current/native WFRD rows, historical archive, contexts, installed decision, source keys, effective identities, resolution linkage, and calculation eligibility. Applied timestamps can differ; semantic equality is required rather than SQLite byte equality.

The actual Production canonical rebuild used a **copied Review Queue**, so ownership observation maintenance could not touch the live queue. All 89,970 existing canonical quarters and financial projections remained unchanged; zero removed, zero source-availability changes, zero bootstrap repairs, zero unexplained unaffected changes. All 89,970 established first-public dates were preserved. Exactly one ordinary current-source addition was WFRD 2026 Q3, period end 2026-09-30, first-public/source-availability 2026-10-21. Its initial date follows existing policy; it is not a preservation side effect. Company/security mapping fingerprints were identical before and after; candidate duplicate quarters were zero.

| Candidate check | Result |
| --- | --- |
| Exact preserved ARQ key | `(WFRD, ARQ, 2020-03-16, 2019-12-31)` |
| Native raw / reviewed effective ARQ label | `2020-Q4` / `2019-Q4` |
| Genuine 2020 Q4 | Independent `(WFRD, ARQ, 2021-02-19, 2020-12-31)`; effective `2020-Q4`; no borrowed resolution |
| Historical MRQ | One exact original archive record, `HISTORICAL_ONLY`, `SUCCESSOR_YEAR_END_STOCKS`, calculation=false; absent from native/current history |
| Current MRQ | `(WFRD, MRQ, 2019-12-13, 2019-12-13)`, PREDECESSOR / PARTIAL_PERIOD_FLOW; calculation/full-quarter/canonical/TTM/P/B/share/stock-fallback=false |
| MRQ acquisition | Exact approved normalized/acquisition evidence; no hybrid or null filling; 32 current MRQ rows |
| 2019 Q4 | End 2019-12-31; availability and first-public 2020-03-16 |
| 2020 Q4 | End 2020-12-31; availability and first-public 2021-02-19 |
| WFRD canonical provenance | 327 ARQ financial provenance rows; zero MRQ authority |
| Share/P/B bindings | Separate ARQ observations; shares 69,999,966 and 70,017,356; exact saved Test observation IDs |
| Saved Test comparison | Same WFRD quarter/date projections and P/B bindings, ignoring internal quarter IDs; same decision/context/archive checks |

This is a bounded WFRD parity rehearsal, not a new authorization of the full 94-ticker set. Other tickers retain active OLD data; therefore the complete derived package is not asserted byte-identical to the prior 94-ticker Test. A future Production Stage 1 must revalidate the entire authorized set.

For clarity, the normal Test-versus-Production source-binding comparator was also measured on this bounded candidate: it returns `STALE`, section `market`. The WFRD-only canonical bundle has 89,501 valuation requirements versus the full Test's 89,586 (85 omitted peer-quarter additions); its canonical-dependent market semantic binding consequently differs. The bundle schema and input row counts match (157,901 price rows, 6,447 split rows, 5,068 ticker metadata rows), and taxonomy matches exactly: `801698f6b352c445cc8e6f5fd51a1cac2779d11f6ce72a1c10bf71bb8aae4559`, 350 memberships. This measurement is not a successful full-pair Production preflight and was not bypassed in a Production operation. Full authorization must compare a fresh candidate for all currently revalidated authorized changes in the restart phase.

The initial disposable harness completed provider/canonical construction, then stopped on an incorrect diagnostic join to a nonexistent canonical observation table. The read-only provenance query was corrected to join the candidate provider, and the already-built copies were revalidated before continuing. No live mutation or publication was involved.

## Focused regressions

314 distinct focused tests pass on the final source. No full suite was run. All invocations used `PYTHONDONTWRITEBYTECODE=1`, `-x -q --tb=short -p no:cacheprovider -o addopts=''`.

| Group | Result |
| --- | --- |
| `tests/test_wfrd_production_candidate_parity.py` | 19 passed; includes actual Production forwarding, equivalent provider/canonical candidates, exact archive/context/identity/date/P/B projections, generic selection/dispatch, absent/false applications, malformed/missing/stale decisions, missing key, ticker mismatch, new conflict, changed proposal, synthetic authority, and postflight absence detection |
| `tests/test_fundamentals_admin_refresh_production.py` | 67 passed; existing authorization, ordinary Production, full downstream/postflight and rollback/crash regressions |
| `tests/test_wfrd_accounting_boundary_review.py`, `tests/test_fundamentals_admin_refresh_copy_test.py`, `tests/test_phase12d_operational_rebuild.py`, `tests/test_publication_date_authority.py`, `tests/test_fundamentals_pb_reporting.py` | 228 passed; includes all 143 WFRD regressions and directly related Test/canonical/date/parent-equity/P/B checks |

Logs: `/tmp/wfrd_production_parity1/tests_parity_production.log` (84 passed before two additional malformed-decision cases), `tests_final_parity.log` (final 19), `tests_related.log` (228). A separate initial WFRD run also passed 143; repeat runs are not double-counted above. Bounded source whitespace checks pass.

## Live invariance and package closeout

Before implementation and during the real rehearsal, physical hashes matched for active provider/canonical/analysis, active and generation manifests, publication journal, and the entire live Review Queue. Semantic comparisons also matched every queue table/schema, watermark, WFRD published quarters/dates, P/B bindings/provenance, and scheduler config. The live provider remains without installed reviewed decision/archive/context; only the disposable provider contains them. DHR's OPEN ownership review is untouched.

**Final rehearsal result: PASS.** The actual Production downstream helper ran once on the disposable provider/canonical and compact market/protected taxonomy sources, as-of 2026-10-27. Full V2 status is READY; package, RP, and RV each ran once. RP snapshot `fd0cf3fd14223c082fdbc090960a053476effd19daec1832867ca92ccf952c89` validates. RV outcome is ACTIVATED **inside the disposable analysis DB**, snapshot `adca9658f14658cf7e374d982d542f8c9220f9d6ea24464e4e549e4153d470f6`, with 2,443 company rows. Normal Production analysis-generation validation also passed against the candidate roles and taxonomy dependency. Provider, canonical, and analysis each passed quick_check with zero FK errors; expected accounting-boundary validation passed again after downstream work.

Final `invariance.json` passes all baseline comparisons. The scheduler/Fundamentals/Production/taxonomy read guards used for the rehearsal have exited. Active generation, journal terminal state, watermark `2026-10-21`, live approval, all live queue schema/tables, and published WFRD Q4/date/P/B/provenance records remain unchanged. The DHR OPEN review remains unapproved. No real Preview/Test/Production, live approval mutation, publication journal preparation, generation creation/activation, watermark advance, or backup cleanup occurred.

| Live authority | Before = after SHA-256 |
| --- | --- |
| Provider | `cadd3a90f40e0320558b7a6e4de14deb06c77373b9cf3ed81fbb22d26d69dac8` |
| Canonical | `02a13632b45008734ff6078e4e8ba717778bc261471febae504908f951c66b6b` |
| Analysis | `e984fe99df5a3683e76ad9fe9a3dd5c6f55f87d530ef7ca0a30ac5cbb9436adf` |
| Active / generation manifest (each) | `f07a6022eb747f10dc4211b996ffd4fa52bcc5a3393fcc57f32c4cc931a47401` |
| Publication journal | `855a3619dc5bc109abc6f74d7705d6237a1ee0c779da4b5fe9f7824a0979b9f2` |
| Entire live Review Queue | `d92e21f51d002fe6d9093f1db0da0b02d062fe466217b7285d19ddbbb680c17d` |
| Scheduler config | `3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894` |

Runtime evidence includes `gap.json`, `before.json`, `real_source.json`, `provider_semantics.json`, `provider_replacement.json`, `canonical_rebuild.json`, `semantic_parity.json`, `authorization_and_pb.json`, `read_only_source_binding.json`, `saved_test_binding_comparison.json`, `analysis_result.json`, `candidate_validation.json`, `after.json`, `invariance.json`, and terminal `phase.json`. All are under the evidence directory above and excluded from the commit. The commit contains only three bounded source files, the focused parity test file, and this report; unrelated pre-existing worktree/runtime changes are preserved. Nothing is pushed.

## Exact restart instructions

Restart `WFRD-PRODUCTION-AUTHORIZATION-1` from **Stage 1** using only the exact Preview, fingerprint, Test, and WFRD resolution above. This implementation supplies no Production consent.

1. Establish scheduler/Fundamentals idle state, scheduler/Production/taxonomy lock availability, terminal clean journal, healthy active OLD generation, no preparing/blocking lane, no recovery, and normal storage/backup availability. OLD remains `refresh_20261022T043408Z_refresh_fundamentals_bb23ca223d59_production_eb6f648d`, watermark `2026-10-21`.
2. Read the exact saved Preview/Test through the unchanged authorization reader; verify the current review partition, bindings, candidate results, AUTHORIZED gate and `MATCHING_SUCCESSFUL_TEST_VALIDATED`. The stored count 94 is a comparison, not a target. Verify WFRD's exact current approved proposal/receipt/decision/actions and both Q4/date/P/B bindings.
3. Use normal full source revalidation for every authorized ticker; rebuild/compare the compact market binding and protected direct taxonomy binding against saved Test semantics. Measure current `STABLE_SOURCE_BUNDLE` / `FUNDAMENTALS_READ_ONLY_SOURCE_V1` and `DIRECT_LOCKED_READ` / `dc_ecosystem` / `DC_TAXONOMY_FULL_V2_1` contracts. Prove provider/canonical/analysis candidate feasibility through the fixed path and normal publication preflight without entering the publication boundary.
4. Stop on stale Preview/Test/source/market/taxonomy/WFRD/baseline or another legitimate blocker. Do not create a replacement Preview/Test, approve DHR, change policy/resolver, or clean rollback backups. Only after every Stage 1 gate passes, present the prescribed exact-pair Production YES/NO question and stop for a **new explicit Production answer**. Earlier approval/Test YES does not authorize Production.
5. Only in the separately authorized Stage 2, repeat critical freshness checks and use the normal Production lifecycle, including the new expected-state candidate/postflight checks and retained rollback backups. Nothing in this copy rehearsal replaces those gates.
