# Approved frozen evidence and full resolver-context handoff

P1.6A extends the existing reviewed-publication-plan preparer and validator with an explicit, versioned approved-input mode. **No real publication plan was created or executed.** Exact approved-case dry validation: **85 inputs, 85 eligible, 0 held**. Production remained unchanged.

## Reproduced P1.6 failures

Before editing code, the exact 85-case P1.6 validation was repeated. `prepare_policy_plan` rejected the supplied original candidate versus active canonical `_evidence_rows` equality check with **PUBLICATION_POLICY_STORED_EVIDENCE_DRIFT**. All 85 Production candidate inventories were empty. No output was published.

The same repeated check reconstructed the preparer's legacy `SecFiling` from primary_excerpt for every case. All 85 reconstructed fingerprints differed from the approved resolver_context_sha256 because full parent/result-section/exhibit fields were lost. Those failures reproduced against the immutable receipt; approval was not recreated or reinterpreted.

Baseline HEAD: `904628f9f2347ab556b5a843d8b1ad6572ae465f`.

Active generation: `refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`.

Provider watermark: `2026-10-08`; latest successful normal Fundamentals Production run: `20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`; provider completion `2026-10-09T04:27:27Z`.

Journal: COMPLETED / COMPLETED; activation ACTIVATED_AND_VERIFIED; postflight PASSED; recovery NOT_REQUIRED. Authority census: VERIFIED 12,890; NOT_FOUND 1,882; UNRESOLVED 842; AMBIGUOUS 628. Review Queue: six RESOLVED refresh rows, 38 audit rows, zero ownership reviews.

The pre-existing modified journal, untracked active-generation data and unrelated PE research outputs remain excluded from this commit.

## Chosen extension point and backward compatibility

The existing `prepare_policy_plan` API now accepts explicit `approved_handoff_path` and `expected_approval_fingerprint`. Approved mode requires policy_evidence_path=None and a caller-pinned approval fingerprint obtained from the authorized operator workflow. Do not derive that expected pin from an untrusted input package. No default discovery, automatic missing-evidence fallback, UI framework or new publication system was added.

The existing `prepare_reviewed_plan` entry point forwards these inputs only with PUBLICATION_EVENT_POLICY_V1; mixed modes and missing pins reject. Without approved mode, schema version 2 preparation, strict Production stored-evidence equality, excerpt reconstruction, narrowed-context validation and existing application behavior remain unchanged.

New helper: `rawcandle/fundamentals/admin/approved_publication_evidence.py`. The helper validates explicit portable inputs and current read-only state. It creates no approval, acquires no source, installs no observation and writes no database.

## Explicit handoff schema — version 1

`schema_version=1`, `input_mode=APPROVED_FROZEN_REVIEW_EVIDENCE`. The canonical `handoff_fingerprint` covers every field except itself. Required content:

| Field | Bound content |
| --- | --- |
| proposal | Exact immutable P1.4 proposal, fingerprint reproduced using its existing contract. |
| approval | Exact immutable P1.5 receipt, including operator confirmation metadata, exact selection, approved bindings and all non-executing flags. |
| review_candidate | Original Stage 1 candidate ledger, reproducing the receipt's candidate/current-state/generation/baseline fingerprints. |
| approved_snapshots | One natural-key/snapshot entry per approved case; each snapshot exactly reproduces the receipt's per-case current_state_fingerprint. Contains complete canonical identity/authority/quarter rows, original evidence inventory, full company open-quarter scope and source/identity/capture hash provenance. |
| companies | One entry per approved company: company_id, exact capture_raw_json and additional_document_texts. The capture's byte SHA-256 must equal the approved snapshot's company_capture_sha256; complete must be true. Its full SecFiling payloads include all retained competing/negative context. Additional text is only for approved proof documents absent from the original exhibit list. |
| identity_input | Exact byte-preserving raw_json plus its original source_reference label, when the approval bound an identity capture. The hash must match both approved snapshot and proposal source-file binding. |
| semantic_input_references | Exact relevant reviewed-input and Policy V1 source hash manifest derived from the approved snapshots. |
| semantic_input_paths | Optional explicit relocation map from bound logical references to current immutable files with identical bytes. No implicit file search. |

The proposal and receipt are embedded as immutable trust proofs; neither is modified. Approvals are exact observations, not generic acceptance of supplied data. No proposal-only package, wrong receipt, HOLD/REJECT/omitted key, altered observation, substituted source or altered quarter can enter an approved plan.

Captures carry parsed filing-context data, not raw SEC HTML downloads. Full capture bytes preserve original metadata/completeness and prevent silently dropping a competing filing while leaving the selected parent unchanged. Filing context is represented once per company in the handoff; existing frozen_inputs retain the concrete filing list for validator/application compatibility. No large raw HTML blobs are duplicated or acquired.

The format has no hard-coded temp-file dependency. All candidate, approval, quarter, capture, additional proof-text and identity evidence needed for pure validation travels in the input. Only explicitly listed semantic references are read during live preflight. For long-lived P1.6B plans, retain those files in a durable artifact store and set semantic_input_paths when relocation is needed; missing files or mismatched hashes fail closed. Historical absolute source_reference labels in embedded proofs are provenance identifiers, not files opened implicitly by validation.

The handoff separates source eligibility from current state. Frozen approval snapshots are immutable C2 proof. Current active generation, authority/quarter/company/security/CIK rows, fiscal scope, provider identity mappings, structural events and canonical evidence rows are C1 and are read again before preparation/revalidation. Frozen evidence cannot override contradictory current facts.

## Full resolver context and source proof

Approved mode decodes the existing complete SecFiling payloads directly. It preserves accession, form/items, acceptance UTC, primary document/reference, complete parent text, legacy_primary, result_sections and result_exhibits including URL, raw-source hash and extracted text. Existing fingerprint definitions are unchanged. All approved resolver_context_sha256 values reproduce exactly.

Approved observation/document hashes, extracted-text hashes, Unicode excerpt locators and literal excerpts are checked. Context text is reused for proof documents; additional retained proof text is supplied only when necessary. No source/observation rebinding, new semantic extraction or network request occurs.

A dry-run failure exposed an additional required part of context: **full company quarter scope**. Restricting quarters to approved writable keys can make a retained filing for a different quarter become unresolved, causing the unchanged Policy V1 competing-context gate to return REVIEW. Version 3 therefore freezes the exact approved company scope, derives its resolver quarter records, and checks that scope against current Production.

Context-only quarters are explicitly distinct from source_allowlist_keys/prepared_keys/policy_cases/per_case. They supply negative/period disambiguation context only, receive no reviewed observation or approval, and can never become writable membership merely by appearing in frozen_inputs or capture metadata. The 514 P1.4 holds remain excluded from approval and writable membership; none was newly researched or adjudicated.

Version 3 declares execution_context=APPROVED_FULL_COMPANY_RESOLVER_CONTEXT_V1. Its validator reproduces against that exact full context, which is also checked before candidate execution. This is not an unresolved-context bypass: the full approved scope and complete captured filings remain present, current and mandatory. The source resolver's unresolved-competing rule remains unchanged. A focused test proves a context-only Q3 is necessary to keep approved Q2 UNIQUE, while Q3 remains unapproved and NOT_FOUND after synthetic copy execution.

## Identity/perimeter evidence

Provider identities are keyed by provider/security_id rather than company_id. The approved byte-bound identity capture supplies the original rows for all security IDs attached to the company. Current provider_security_identity rows are compared through those security IDs. Structural events are compared by company_id. Company/CIK/security rows and the entire accepted quarter/authority state retain their existing exact equality guard. A changed mapping or perimeter row rejects.

The planner implementation hash is retained in immutable snapshot provenance but excluded from the live semantic-input manifest because this phase explicitly changes that implementation. Policy V1, ordinary resolver, timestamp comparator and known reviewed semantic-input hashes remain checked. Identity/population capture references are handled through embedded approved identity proof plus live identity/fiscal checks, rather than undocumented temp-file reads.

## Plan schema and provenance

Approved mode uses **Policy plan schema version 3**. All existing plan fields remain; versions 2/legacy and Form 6-K behavior retain their existing branches. Version 2 rejects approved-mode fields, preventing downgrade-based gate bypass.

Additional version 3 fields: candidate_evidence_provenance=APPROVED_FROZEN_REVIEW_EVIDENCE; execution_context; approved_evidence_handoff; approved_handoff_fingerprint; approval_fingerprint; proposal_fingerprint. Fixed preparation-state flags: publication_authorized=false, production_apply_authorized=false, executed=false.

Existing original_candidate_evidence is now explicitly frozen approved evidence in version 3; it is not represented as pre-existing Production evidence. The approved snapshot preserves the historical Production inventory, while current inventory is separately read and checked at every live preflight. For the 85 dry inputs, both approval-time and current inventories are empty.

The plan still binds current generation/manifest, complete current authority/identity state, exact allowlist/prepared keys, frozen request/quarters/filings, original candidate payload, observation/acceptance/relation bindings, policy decisions and all existing fingerprints. The whole-plan fingerprint contract is unchanged. Receipt/proposal/handoff fingerprints and exact evidence/context/source/observation bindings are additionally validated.

## Stored evidence and future application rules

| Current Production candidate evidence | Approved mode behavior |
| --- | --- |
| Absent | Allowed only with complete explicit approval/capture/current-state proof. |
| Exact matching source facts | Allowed; no pre-insertion is required. |
| Different source facts or extra candidate | Reject as stale/conflicting before any candidate authority writer. |
| Authority already VERIFIED | Current open-scope/application guards exclude or reject repeat application. |
| Changed quarter, generation, identity, fiscal scope, semantic input or full context | Reject; no silent rebind. |

SQL-only nullable columns normalize to None when absent from the frozen payload; disposition/created_at_utc are bookkeeping fields only when not present in the approved payload. Every source/event field, identifier and approved full-payload fingerprint remains exact. Additional non-null source facts and extra evidence IDs reject. Version 2 row comparison remains strict and unchanged.

`legacy.revalidate_plan_state` retains generation/manifest, exact open-key scope and complete state checks. For version 3 it additionally checks the approved handoff, full fiscal/provider/perimeter context and missing-or-exact evidence compatibility. It does not incorrectly require preinstallation. `run_policy_candidate` validates all approved/current case guards before its first writer, then uses the plan's exact reviewed candidate. Existing apply_resolution remains the authority writer. It may install the exact frozen candidate only inside a later separately authorized candidate execution; no such real execution occurred here.

The prepared false authorization flags describe immutable preparation state. Successful validation does not grant consent. Existing external exact-plan authorization and candidate/generation publication boundaries remain required for future execution; no runtime consumer or worker discovery was added. The receipt stays immutable and unconsumed; no one-shot finalization was introduced.

## Tests and exact approved-case dry proof

Focused tests: **34 passed**, `tests/test_approved_publication_evidence.py`. Directly relevant existing reviewed-plan regression group: **25 passed**, `tests/test_policy_reviewed_publication_plan.py`. Final combined run: **59 passed**. Full suite: **not run**.

Coverage includes required/pinned approval integrity, schema/version/mode separation, exact membership, HOLD/REJECT/omission rejection, frozen candidate/context/source/observation/excerpt binding, absent/matching/conflicting/extra stored evidence, current quarter/generation/authority/identity/provider/perimeter/fiscal/policy drift, unchanged legacy missing-evidence rejection, fail-closed validation, deterministic preparation with frozen ID/time metadata, and the explicit reviewed-plan entry point.

The production-shaped smoke uses two public SEC filing contexts and synthetic temporary approvals/generations. Preparation with empty candidate tables does not invoke the writer or change source DB bytes. A separate candidate-copy execution verifies the future frozen-evidence path, preserves the financial sentinel, and leaves its source generation unchanged. Context-only keys remain unmodified.

After focused tests passed, the exact immutable P1.5 85-case receipt/proposal/current snapshots were represented by the new contract. Complete capture fingerprints, full parent/exhibit contexts, provider identities, 595 excerpt locators and all current-state preconditions reproduced. Input **85**; eligible **85**; held **0**; companies **32**; Production evidence insertions **0**. All 514 backlog holds remain excluded.

Dry handoff fingerprint: `cc638f2861a0ea6f65f5e7f6271bf75191425c774f0be4d343d69e81bd10f532`.

Approval fingerprint: `0d82b233adec0e0d85a6e1ad568b72d061881103dd2442c0922b42b1786bf651`.

Proposal fingerprint: `ea28d203681fa6c331ef3ef1741d80908f7520fd1c3924e9703284c313614657`.

The only 85-case serialization was temporary validation material under `/tmp/publication_handoff_p16a/`; it is not a published Production plan or committed artifact. No production candidate runner, rehearsal, worker or drain was called for those 85. Reproduction with frozen creation timestamp/ID produces byte-identical temporary plan objects; current-state revalidation passes. P1.6B must independently re-establish current state and prepare the durable immutable plan later.

## Production invariance

Before/after protected hashes match for provider/canonical/analysis DBs, active pointer, Review Queue and pre-existing sidecars, publication journal, schedulers, immutable proposal/approval and prior reports. No new database sidecars were introduced. Ordinary resolver, timestamp comparator and Policy V1 source remain byte-identical to baseline.

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

Publication authority changed: NO. Authoritative reviewed observations installed: NO. Approval changed: NO. Financial DBs changed: NO. Active generation changed: NO. Queue/journal/schedulers/watermark/retry behavior changed: NO. Policy V1 eligibility or ordinary resolver changed: NO. Real publication plan created: NO. Production publication authorized or apply executed: NO. Push: NO.

## Next phase

P1.6B: re-establish current Production state, materialize/verify explicit immutable handoff references, reconcile the exact approved membership, and prepare/validate one durable immutable version 3 plan. Do not reuse this dry object's fingerprint as execution authorization. P1.7 must separately authorize execution of the exact then-current prepared plan fingerprint; no publication is authorized by P1.6A.
