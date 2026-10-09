# Historical publication plan handoff — stopped at contract boundary

**No publication plan was created.** All 85 operator-approved observations still match current source, identity, quarter and Policy V1 bindings, but none can enter the existing preparer without crossing the explicit P1.6 stop boundary. This phase is incomplete with respect to plan creation; the permitted revalidation and documentation are complete.

The existing preparer requires exact candidate-evidence rows in the active canonical database, where all 85 keys currently have zero such rows. It also reconstructs an excerpt-only legacy SecFiling context instead of the approved full parent/exhibit context. These are unsupported handoff inputs, not stale approvals. No gate was weakened and no alternate plan format, evidence insertion, copy-generation substitution or Production write was attempted.

## P1.5 documentation and receipt integrity

The P1.5 operator-review report initially still presented Stage 1. Its introduction now records completed Stage 2: explicit YES, 85 approved observations, immutable receipt and fingerprints, non-executing flags, commit lineage, unchanged Production and next phase. Historical Stage 1 evidence and gate descriptions remain preserved below the Stage 2 addendum.

Proposal fingerprint: `ea28d203681fa6c331ef3ef1741d80908f7520fd1c3924e9703284c313614657`.

Proposal byte SHA-256: `6ca99cbc6aeb05ec15fd0927a0c008c9f6add54229ed705b0654c81f89891786`.

Approval fingerprint: `0d82b233adec0e0d85a6e1ad568b72d061881103dd2442c0922b42b1786bf651`.

Approval byte SHA-256: `77571dfad2b9d5b6b3a0601df6718b68cf93b2d5f150c898f0141db4039a8387`.

Approval receipt: `docs/fundamentals_v4/review_approvals/historical_publication_review_approval_v1.0d82b233adec0e0d85a6e1ad568b72d061881103dd2442c0922b42b1786bf651.json`.

Stage 1 commit: `1c7fa3e1dcf64295db700092bb0e99f93a54c432`; Stage 2 commit: `b3ff5235e72b34684b62e882f1e8bedfc92e534b`.

The canonical JSON fingerprint contracts reproduce for the proposal, immutable receipt and exact selection. Membership equals exactly the 85 approved natural keys, with matching observation/evidence/context/source fingerprints and per-case current-state fingerprints. The selection fingerprint is `8bdf27a1a754b36973e7728a1abb582fb5fd4ff1613e3040b597ca1c74d01b14`; the approved candidate fingerprint is `5faea82e92b9887b00cea21e227a02860874964036a3caadaac31e1d50d691a6`.

The receipt records the interactive user's explicit YES at `2026-10-09T10:22:53Z`; no personal identity was invented. Its status is OPERATOR_APPROVED_REVIEW_EVIDENCE. All four flags remain false: runtime_use_permitted, publication_authorized, production_apply_authorized, authority_mutation_authorized. Approval was neither recreated, broadened, changed nor consumed.

## Current baseline

HEAD at revalidation: `b3ff5235e72b34684b62e882f1e8bedfc92e534b`.

Pre-existing worktree changes: modified publication journal; untracked active-generation pointer/directory and unrelated PE research script/plot. These remain excluded from the commit. The P1.5 documentation correction is this phase's scoped change.

Active generation: `refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`.

Provider watermark: `2026-10-08`; latest successful normal Fundamentals Production run: `20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`; provider completion `2026-10-09T04:27:27Z`.

Journal: state/step COMPLETED; activation ACTIVATED_AND_VERIFIED; postflight PASSED; recovery NOT_REQUIRED; updated `2026-10-09T04:37:11Z`.

Authority census: VERIFIED 12,890; NOT_FOUND 1,882; UNRESOLVED 842; AMBIGUOUS 628. Whole-authority fingerprint: `41e710eb4dca4418d48e403fde8c70777efa1c02be24cb48e7eb3a6a4ccce577`.

Review Queue: six RESOLVED refresh rows, 38 audit rows, zero ownership reviews. No queue mutation occurred.

Current authority, complete accepted canonical quarter, company/security/active CIK chain, structural identity context and evidence inventory were read in SQLite read-only/query-only mode. The current Production hashes remain equal to the prior baseline; no normal Production advancement occurred during this phase. Normal advancement would have been evaluated as current state rather than treated automatically as failure.

## Exact approved-population reconciliation

| Classification | Count |
| --- | ---: |
| READY_FOR_PLAN | 0 |
| ALREADY_VERIFIED | 0 |
| STALE_APPROVAL_SOURCE_CHANGED | 0 |
| STALE_APPROVAL_QUARTER_CHANGED | 0 |
| STALE_APPROVAL_COMPETING_CONTEXT | 0 |
| STALE_APPROVAL_IDENTITY_OR_PERIMETER | 0 |
| STALE_APPROVAL_POLICY_INPUT_CHANGED | 0 |
| OTHER_HOLD | 85 |
| Reconciled approved total | 85 |
| Exact planned total | 0 |

OTHER_HOLD means `EXISTING_PREPARER_REQUIRES_DURABLE_PRODUCTION_EVIDENCE_AND_CANNOT_RECONSTRUCT_APPROVED_FULL_CONTEXT`. It does not mean the source evidence or operator approval became stale. A source-valid proposal is not READY_FOR_PLAN when the existing plan contract cannot represent it safely.

The 514 original P1.4 holds remain completely outside this revalidation/plan population. No research, acquisition, new interpretation or plan membership was performed for them. [Exact revalidation CSV](fundamentals_v4_historical_publication_plan_revalidation.csv) contains one row per approved key; membership CSV: NOT_CREATED because no plan exists.

For all 85 cases across 32 companies, current accepted quarter IDs, period ends, authority rows, company/security/active CIK identities, selected accession, source type/form, primary document, reference, timestamp, full evidence payload/hash and approved observation fingerprint match exactly. All authority rows remain open; durable candidate evidence remains empty. No fiscal or perimeter drift was found.

Full current company open-quarter scopes were replayed with the retained complete official filing captures to detect competing contexts. There is no new competing event or unresolved competing context. Policy/resolver code and the known reviewed-input/exclusion/precedence sources match their proposal-bound hashes. Policy V1 and resolver behavior remain unchanged.

All 595 approved source excerpts reproduce from retained raw HTML, including source hash, extracted filing-text hash, Unicode offsets, literal excerpt and excerpt hash. Copy-only Policy V1 preview: 85 UNIQUE with the exact approved observations; control without observations: 85 REVIEW. No observations were installed into an authoritative runtime location. The retained captures are dated 2026-10-09; no new network crawl or acquisition was performed. Missing or changed retained inputs would have blocked this proof.

The existing approved caution remains: active security valid_from is absent; exact registrant/linked-release issuer proofs remain unchanged. Six proposals use additional retained official exhibit text outside the original resolver exhibit list, with independent approved document hashes. No fresh perimeter judgment was substituted.

## Existing preparer, validator and application boundary

Only `rawcandle/fundamentals/admin/policy_reviewed_publication_plan.py` and the relevant legacy reviewed-plan helpers were inspected. No alternative runtime or generic approval mechanism was introduced.

`prepare_policy_plan` accepts explicit root, exact allowlist CSV, explicit Policy V1 evidence JSON, output path, as-of date and retry_days. Evidence JSON requires policy_version plus cases with quarter, events and relations; each event includes complete evidence, primary_excerpt, reviewed observation and optional acceptance-index review. Approval metadata is not an automatic authorization input.

The preparer resolves the active generation and clean journal, reads the active canonical DB in read-only mode, and selects exact open identities. For each selected key it compares supplied original candidates with `_evidence_rows` from that active database. At the exact equality gate it raises `PUBLICATION_POLICY_STORED_EVIDENCE_DRIFT` if the rows differ. There is no supported frozen-evidence override or separate staging-input parameter.

The prepared schema would be version 2, Policy V1 / reviewed_event_observations_v1, with source allowlist, current generation/manifest fingerprint, complete per-case authority/identity state, original candidate evidence, observations, acceptance observations, relations, frozen request/quarters/filings, reproduced decisions and fingerprints. `validate_policy_plan` reproduces evidence and semantic decisions, checks exact scope/order and narrowed apply context. The plan fingerprint covers the complete serialized plan except its own fingerprint field.

`legacy.revalidate_plan_state` checks generation/manifest, current open scope, complete authority/identity rows and exact durable evidence again against the active canonical database. `run_policy_candidate` repeats current-state/evidence checks before its authority writer boundary. Neither apply routine, candidate runner, rehearsal, drain nor worker was invoked.

`legacy.publish_plan` exclusively publishes the validated plan to an explicit caller-provided output path, rejects existing output, and uses a temporary file plus hard link/read-only permissions. The preparer excludes data/backups destinations. There is no fixed plan directory imposed by this API, and no real output path or alternative format was selected in this stopped phase. The preparer also generates a random plan ID and current creation time, so future deterministic replay must freeze those metadata inputs rather than claim two unrestricted calls yield identical bytes.

## Durable evidence and full-context gaps — required STOP

First, every approved key has zero durable Production candidate rows, while every approved case supplies one exact resolver candidate. The existing preparer rejects this mismatch. A direct read-only preparation attempt with the exact 85-key allowlist and explicit temporary approved evidence input returned **`PUBLICATION_POLICY_STORED_EVIDENCE_DRIFT`**, before any output plan was published. Repeated against the same frozen baseline, it returned the same error and still created no output.

Inserting these rows into Production to satisfy the gate is forbidden by P1.6 G/O. Inserting rows into a substituted generation or copied database would not produce a current-Production-valid plan: the unchanged Production evidence check would reject it during revalidation/application. Neither workaround was attempted.

Second, the existing preparer constructs SecFiling from primary_excerpt with default legacy fields. This loses the full reviewed parent/result-section/exhibit context. For all 85 cases, its reconstructed context fingerprint differs from the approved observation's resolver_context_sha256. The revalidation CSV records both fingerprints. Changing the observation hash, stripping exhibit context or relaxing reproduction would silently rebind approval or weaken Policy V1; none was done.

P1.6 G requires stopping if existing architecture requires Production evidence writes for preparation. P1.6 O additionally requires stopping when the existing preparer cannot represent these observations without weakening the contract. These conditions apply. The immutable plan deliverable, plan fingerprint, plan validation and deterministic plan replay are therefore **NOT_CREATED / NOT_RUN**, not successful results.

## Validation and invariance

No source code was changed. No full suite or unrelated regression group was run. Deterministic assertions and the existing preparer/validator boundaries were used, as required for a no-source-change phase.

Passed: receipt/proposal/selection fingerprints and byte hashes; exact 85-case membership and complete bindings; accepted identity and open authority state; 595 source locators; Policy V1 reviewed/control replay; zero unapproved/held keys; 85 explicit durable-evidence gaps and context mismatches; existing preparer fail-closed rejection; existing plan validator rejects the receipt as a plan. The entire current-state/source revalidation and blocked-preparation checks were repeated twice, producing identical revalidation CSV bytes and summary bytes.

Revalidation CSV SHA-256: `597692ff6066bbec9e29c97f9cfb04225f5f410fd5eebc8956a7c8f8a104c53e`.

Plan validation: NOT_RUN_NO_PLAN. Deterministic plan replay: NOT_RUN_NO_PLAN. These are blocked acceptance criteria, not passes. No fake, empty or authorization-bearing plan was fabricated.

Protected provider/canonical/analysis DBs, active pointer, authority statuses/timestamps, Review Queue and pre-existing sidecars, publication journal, schedulers, provider watermark, immutable proposal/approval and prior P1.1–P1.4 reports remain unchanged before/after. No new SQLite sidecars were introduced. The corrected P1.5 report was protected after its authorized documentation update.

| Protected role | SHA-256 |
| --- | --- |
| provider | `fda234de30f448fe342fd5fc842ff430575fd6b361146409cf1f8131e17f2981` |
| canonical | `996deb198513b94e22888dbbb11b8139698b68cf98201a5df4d9bb8cd30a1845` |
| analysis | `9da7016ef65571d47b8ae9d2db79f4f42589dc866c1967042fbde8e770db9e8c` |
| pointer | `30c08f22b5b9b2a3cbb07f5183d2946e3ed8b980634d0e54255936b9310b5de3` |
| queue | `84c18a698ef541a355950c91805ba0e949c9dd4d1a1d4d7d991a7bebc5d3e15b` |
| queue-wal | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| queue-shm | `fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb` |
| journal | `6f7e625fe10c0ab98c31902bb34d4e7a0c24ea2c94b840497b0459a07817aa67` |
| scheduler | `3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894` |
| forecast_scheduler | `67e55b992b6144306b8b96a23157d4879490256c3af1d267f3852da5f1587e79` |

Authoritative observations installed: NO. Approval changed/consumed: NO. Publication authority or financial DBs changed: NO. Generation activated: NO. Queue/journal/scheduler/retry horizon/cap changed: NO. Policy V1/resolver changed: NO. Production publication authorized: NO. Production apply executed: NO. Push: NO.

## Next phase and exact authorization boundary

The next phase must explicitly design and test a copy-only durable-evidence/full-filing-context handoff extension to the existing reviewed-plan contract, preserving current-Production preconditions and approved bindings. This report does not authorize implementing a workaround or inserting evidence into Production. Re-run P1.6 revalidation and plan preparation after that boundary is resolved.

P1.7 apply is premature: there is no prepared plan to authorize. Any future Production execution must separately authorize the exact validated plan fingerprint, membership and current generation, after a fresh stale-plan check. Reviewed-evidence approval remains immutable and non-executing in the meantime.
