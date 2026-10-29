# Historical financial freeze policy — 2026-10-29

Task: `FUNDAMENTALS-HISTORICAL-FREEZE-POLICY-1`.
Base commit: `cc54d46c45da5c6371cc57f6722c2372234c2648`.

## Contract and implementation

`FUNDAMENTALS_HISTORICAL_FREEZE_V1` freezes an already accepted canonical financial identity when its authoritative **period_end <= 2024-12-31**. The cutoff is fixed. Fiscal labels, source/publication dates, today's date and the separate rolling provider-history horizon do not determine membership. Accepted periods ending 2025-01-01 or later retain existing Refresh behavior. New identities without an accepted financial row are outside this preservation contract.

`admin/historical_freeze.py` contains the pure decision helper and read-only accepted-source binding. It distinguishes `NOT_FROZEN`, `FROZEN_NO_CONFLICT`, `FROZEN_PROVIDER_CONFLICT_HELD`, and `FROZEN_REVIEWED_REPAIR_ALLOWED`. The binding uses company, accepted quarter identity, authoritative period_end, source key, exact accepted observation ID/hash, canonical financial values and provenance. Missing, contradictory or ambiguous accepted bindings fail closed. Normalized decimal strings are compared using SQLite's numerical storage representation. Parent-equity projection retains its native accepted-shares requirement and finite-number handling.

Preview applies the policy around existing review matching; Test and Production repeat it against current source/state. The policy descriptor and exact conflict evidence enter the bound Refresh fingerprint. Native publication winner precedence and publication-date validity rules are reused. A final candidate check rejects an unreviewed alteration or deletion of any previously accepted frozen financial identity before the immutable generation can be published.

Ordinary changes to financial payload, economic share factor, source identity/key, accepted winner, or an unretained source disappearance are held. Existing coherent source-window retention continues carrying the old source row. Mere lastupdated changes with no financial or identity effect do not create a frozen-conflict review.

## Evidence, review and operator experience

There is no schema migration, new review state, parallel review family, override button or history-version graph. The existing ticker-keyed provider-history review represents a frozen conflict. Existing removal/fiscal reviews retain their classification and eligibility rules and receive additional frozen evidence when appropriate. A new ordinary frozen-conflict shape uses the same local queue, Wait/Retry actions and publication partition.

Evidence contains accepted financial/publication values, accepted raw acquisition evidence, exact old observation ID/hash/key, incoming normalized/full acquisition payload, alternative candidates, fiscal identity, period_end, changed reasons and evidence fingerprint. It is retained in Preview and queue context. On a material change, `HISTORICAL_PROVIDER_CONFLICT_OBSERVED` appends the full diagnostic evidence to the **existing queue audit table**, so updating the current ticker item does not discard an earlier observed conflict. Identical reevaluations do not append duplicate evidence events.

The shared presentation shows **Historical value preserved**, **Frozen historical provider conflict**, **No immediate action required**, and **Review only if you intend to repair this historical period**. Accepted-history/provider-evidence outcomes are stated separately. Structured evidence is summarized before the existing raw-evidence view. Rendering does not write review state or authorize repair. Ordinary frozen conflicts stay in lightweight Review; existing authoritative accounting-boundary exceptions retain their separate Deep Review route. Resolved rows retain existing history treatment.

Publication remains ticker-local: a held ticker is excluded from replacement, while independently safe peers use native Test/Production. This retains the current ticker-level execution granularity; it does not partially publish a held ticker. A reviewed repair plus another unreviewed frozen change in the same ticker remains a local hold, not a new global blocker. Existing true global blockers remain authoritative.

Provider, canonical and analysis roles remain distinct. Held incoming observations remain diagnostic evidence; the accepted provider history in the active generation remains rebuildable. Canonical retains accepted frozen values and established publication metadata. Full V2/RP/RV analysis rebuilds from that preserved canonical candidate and shared inputs. The analysis database is not globally frozen: a safe peer or changed market input can legitimately change derived output.

## Exact reviewed exceptions

The implementation consumes existing exact source-removal/replacement approvals after the native queue matcher revalidates their complete source and published-state binding. Only the accepted source keys named by that proof receive the exception. Other frozen identities remain protected. The candidate check binds the exact old accepted state and proposed new state; stale source, tampered fingerprints and unrelated revisions cannot reuse that authority. A later ordinary reverse-provider refresh is held against the newly accepted repaired state.

The existing accounting-boundary contract is reused without editing its rules. Its installed decision, acquisition and canonical proofs allow only its already-supported exact provider-label interpretation while keeping financial values, economic quarter identity and dates unchanged. This also preserves its existing copy-only rehearsal. No broad financial exception is inferred from a boundary decision.

There is no new generic restatement/SEC/corporate-action approval mechanism. A payload-only historical conflict with no applicable existing exact repair contract remains held; Wait/Retry does not approve it. Existing separately controlled payload-completeness repair remains unchanged. All supported repairs continue through native immutable generations, journal/postflight, rollback/recovery and cleanup. Established first_public_result_date never moves; the already-audited bootstrap of a previously unestablished date remains available unchanged.

## Fresh current-state inventory

Inventory and repeated read-only validation used the active generation:

`pb_ownership_719201a6f6f4497bb6a3e1ada35b81b6`

Published watermark: **2026-10-28**. Publication journal: **COMPLETED / PASSED / NOT_REQUIRED**. These observations describe current stored runtime state and retained source-comparison evidence, not a newly acquired complete external-provider universe.

| Observation | Count / result |
| --- | --- |
| Accepted canonical financial quarters | 90,141 |
| Accepted financial rows with period_end <= 2024-12-31 | **74,637** |
| Companies in the frozen financial population | **2,534** |
| Frozen accepted row vs current provider-winner financial/identity conflicts | **0** |
| Missing frozen provider winners | **0** |
| Frozen rows without one deterministic core accepted observation ID | **0** |
| Currently known frozen source-key review cases | **1: RRC** |
| Such cases already behind existing review protection | **1** |
| Known coherent frozen source-window absence events | **6**, covering four accepted fiscal quarters |
| Known changes that would currently mutate accepted frozen canonical without this policy | **0** |

All 74,637 accepted bindings were freshly checked, including native parent-equity acceptance. Three raw empty-string equity payloads project to null, and two source equity numbers have no accepted shares provenance and correctly remain null in canonical. These are native acceptance outcomes, not accepted-value conflicts. No structural inconsistency remained.

The latest retained complete-source comparison examined was `20261029T164949Z_refresh_fundamentals_5fc2aa1a7e10`. Both FDX and RRC remain existing provider-history reviews. FDX's actual removal exception concerns a nonfrozen 2025 period. RRC's `SAME_FISCAL_SOURCE_KEY_REPLACEMENT` concerns 2016 Q3: the removed old ARQ key is dated 2016-10-25, while the **already accepted** canonical source is dated 2016-11-16 for period_end 2016-09-30. Thus that known source-key conflict does not currently replace the accepted canonical winner. The six aged events are already handled by retained-history protection. The new policy does not reinterpret any of these past acceptances or rewrite them.

The latest stored response cannot be reconstructed exactly merely by subtracting absent keys from today's accepted provider history: retained raw-response fingerprints differ for both tickers. This was recorded explicitly rather than claiming a fresh exact-response replay. The full current accepted-binding/value audit succeeded independently; existing review evidence was inspected read-only and retained intact. No live Preview, provider refresh, approval, reconciliation or publication was invoked for this task.

## Disposable-copy rehearsal and regression coverage

Representative tests use disposable SQLite/provider/canonical copies. Two complete native fixture workflows publish immutable generations: one quarantines an ordinary frozen conflict while publishing a current peer, and one publishes an exact reviewed frozen replacement plus a current peer. Both run native Preview, Test and Production, native full derived rebuild, postflight lineage checks and terminal cleanup. Their accepted source data and generations are fixture-only.

| Required scenario | Evidence / outcome |
| --- | --- |
| Frozen source unchanged | No invented conflict; accepted values preserved |
| Changed frozen financial payload / equity / factor | Local hold, exact full evidence retained |
| Changed source key | Ordinary replacement held |
| Source disappeared | Existing removal review enriched, accepted row protected |
| Same-fiscal replacement | Existing review reused; exact reviewed exception tested separately |
| Exact reviewed frozen repair | Bound row publishes through native generation/journal/postflight |
| Stale or tampered repair | Native source binding / evidence checks reject |
| Unrelated frozen row during repair | Still held; safe peer partition stays local |
| Current changed row | Existing ordinary behavior and safe publication preserved |
| Mixed frozen conflict + current peer | Peer publishes; held financial history stays accepted |
| 2024-12-31 / 2025-01-01 | Exact inclusive/exclusive boundary verified, independent of fiscal label |
| Aged-out source window | Native retained rows rebuild without financial loss |
| Changed reappearance | Source merge retains evidence; ordinary canonical mutation held |
| Later reverse-source refresh after repair | Cannot silently undo accepted repair |
| Publication metadata | Established dates preserved; native bootstrap retained |
| Analysis | Native full canonical-derived rebuild and cross-role lineage pass |
| Evidence changes repeatedly | One current item, prior exact conflicts retained in existing audit |
| UI | No immediate action; native action eligibility retained; no rendering writes |
| Existing lifecycle / WFRD / source repair / publication authority / P/B | Direct focused regressions; no lifecycle/policy replacement |

Focused test results and final runtime verification are recorded below after completion. No full suite was run.

The directly relevant legacy test fixtures were aligned with the established contracts: retained-approval fixtures explicitly select the pre-horizon review behavior they intend to test; the scheduler Preview wrapper forwards its existing ownership flag; the fingerprint-only unit test stubs the newly introduced independent projection; and the old retention test now expects unreviewed 2016 overwrites/reappearances to be rejected on disposable candidates. The retained-approval fixture mismatch was independently reproduced with the freeze hook disabled before adjusting that fixture. Production scheduler and source-history semantics were not changed to accommodate tests.

## Rollout and exclusions

The source integration protects future normal Refresh, scheduler and manual Full Workflow through the shared native path. It has no separate runtime configuration switch and does not execute work on enablement. Acceptance is limited to the audited V2 accepted-source contract and the exact existing exceptions above. No service restart or live financial workflow is part of rollout.

No runtime database, review queue, journal, generation manifest, scheduler configuration, market/taxonomy data, backup or OHLCV/research artifact belongs to the source commit. The pre-existing journal/worktree changes are preserved and excluded. No bulk historical rewrite, live historical repair, backfill or backup deletion was performed. No push is authorized or performed.

## Final verification and decision

**PASS — integrate V1 into future normal Refresh operations.** No live reconciliation, publication or historical data mutation was triggered by integration.

Successful focused groups (overlapping tests, not additive totals):

- **358 passed**: freeze/native workflow publication parity, WFRD accounting-boundary and production-candidate parity, controlled provider payload repair/completeness, result-publication authority, and review queue regressions.
- **234 passed**: current freeze scenarios, actual Flet rendering, action-first/staged guidance, hobby-mode routing, final-polish, P/B presentation, review queue and admin UI regressions.
- **229 passed**: Refresh Preview/copy/Production/Full Workflow, historical source-window horizon, publication-date authority, future P/B and safe-no-change contracts.
- **149 passed** after the final no-op projection adjustment: freeze cases, Preview, action-first and actual admin UI. Tickers that native Refresh does not replace are not assigned a speculative regenerated observation-ID winner.

The complete freeze fixture module contains **19 cases**, including two native immutable-generation publication scenarios. Copy rehearsal **PASS**. `git diff --check` **PASS**. Full suite **NOT RUN**.

Repeated full accepted-binding validation covered **74,637 / 74,637** frozen rows across **2,534** companies. Final comparison against the initial runtime snapshot confirmed unchanged active generation, all provider/canonical/analysis hashes, watermark, complete queue content, journal, market/research inputs and scheduler configuration. Journal remains **COMPLETED / PASSED / NOT_REQUIRED**; all **50** backup files remain present. Earlier full replay also compared backup metadata before/after with no changes.

Financial role hashes:

| Role | SHA-256 |
| --- | --- |
| provider | `0f23acbd064d1859fa1d9f71996d1eb4979a9cdbac2db1d805a774d4215770f1` |
| canonical | `84987b23f13e8d42801b9a0304fe35adb9e4c198a2c78adc7bcaafefbbd8208e` |
| analysis | `b1fef5fd8eb651e0337c9f6128b1e068df2999873da158c653b45fff42223327` |

Development evidence remains excluded under `temp/fundamentals_historical_freeze_20261029/`: inventory, binding replay, current known-review evidence, native acceptance-guard audit, focused logs and `final_verification.json`. Native fixture databases and generation rehearsals remain disposable test artifacts. The source commit includes only the policy integration, shared presentation, directly relevant tests/fixture corrections and this report. WFRD, source-repair, first-public, publication-authority, P/B policy, locking, recovery and cleanup semantics remain unchanged.
