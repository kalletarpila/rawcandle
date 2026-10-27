# WFRD combined preservation approval history

Latest status: the Stage 1 restart below registered the exact V2-bound review **OPEN** at `2026-10-27T10:10:31Z`. Explicit operator approval remains pending. Earlier STOP entries are preserved as historical evidence.

Date: 2026-10-27. Task: WFRD-REVIEW-APPROVAL-1.

## Result

**STOPPED_SOURCE_DEFECT. The explicit approval gate was not reached.** No proposal was registered, no operator approval was requested or applied, and no new Preview, Test, or Production ran.

The existing combined-review backend cannot preserve the exact rehearsal receipt fingerprint when registering an OPEN proposal. Section F of the request requires that binding at registration. The request also states: “If a source defect is discovered, STOP and make it a separate implementation phase.” This report follows that stop condition; it does not treat incomplete revalidation as a passing result.

Implementation inspected at HEAD `f23af13e7086296b1c917dcc5d2c25ca7accb3f6`. Governing documents remain the [ARQ evidence review](wfrd_fiscal_identity_review_2026-10-25.md), [MRQ disposition policy](wfrd_mrq_disposition_policy.md), and [combined implementation report](wfrd_combined_preservation_implementation.md). No source files or governing policies were changed.

## Latest overnight scheduler result

The scheduler result was inspected before loading the proposal. The latest scheduled FULL_WORKFLOW parent is:

`20261027T052613Z_refresh_fundamentals_d00eb7239fed_full_workflow_08a70a67`

Its exact Preview child is:

`20261027T052613Z_refresh_fundamentals_c274483eb886`

Evidence: the parent's `request.json`, `result.json`, and the child's `result.json` under `fundamental_reports/admin_runs/`. The parent completed at `2026-10-27T05:28:40Z` with outcome `STOPPED`. Its sole stage was Preview, completed with outcome `REVIEW_REQUIRED`.

| Measurement | Overnight result |
| --- | --- |
| WFRD classification | `REVIEW_REQUIRED` |
| WFRD scope | `GLOBAL_BLOCKING_REVIEW` |
| WFRD reasons | `REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION`, `SAME_FISCAL_SOURCE_KEY_REPLACEMENT` |
| Safe effective changes | 93 |
| Total global blockers | 1, WFRD |
| Review required | 1 |
| Held/local items | 0 |
| Test authorized | NO: `GLOBAL_BLOCKER_PRESENT` |
| Production authorized | NO: `GLOBAL_BLOCKER_PRESENT` |
| Test ran | NO; no Test stage |
| Production ran | NO; `production_entered=false`, `production_completed=false`, database writes 0 |

The overnight evidence still records the exact ARQ label revision and complete-response MRQ absence proof. It did not resolve WFRD. These historical observations are not a substitute for the fresh provider fetch required before registration and approval. The scheduler artifacts were not modified or relabeled.

## Blocking registration contract gap

The relevant existing implementation is narrowly localized:

- `rawcandle/fundamentals/admin/ui_service.py:949`: `register_accounting_boundary_proposal(self, proposal)` accepts only a proposal and calls `save_item(queue_path, proposal)`.
- `rawcandle/fundamentals/admin/accounting_boundary_review.py:383`: `save_item` accepts `proposal`, optional `decision`, and stale/rejection reasons. An OPEN item contains `proposal`, `decision=None`, `status=OPEN`, and the two reason fields. The audit receives the same item. Neither has a rehearsal receipt or receipt-fingerprint binding.
- `rawcandle/fundamentals/admin/ui_service.py:955`: the receipt is first supplied to `approve_accounting_boundary_review(..., rehearsal=...)`. It is verified and stored within the resulting approved decision, rather than bound to the previously registered OPEN item.

The exact existing proposal also has no receipt or receipt-fingerprint field. Its top-level fields are `created_at`, `evidence`, `evidence_fingerprint`, `operator`, `production_authorized`, `proposal_fingerprint`, `resolution_id`, `schema_version`, `stale`, and `status`. Consequently, registering that proposal unchanged cannot satisfy the requested OPEN-item receipt binding.

Adding a receipt field to the proposal would change its exact fingerprint and break the existing receipt's proposal binding. Supplying an approved decision to registration would cross the explicit operator gate. Manually editing the queue or inventing an unsupported envelope would bypass the required backend. None of these workarounds was attempted.

This finding concerns the additional pre-approval registration requirement. It does not claim that the existing approval function omits receipt validation: the approval path does validate and store a supplied receipt. The missing behavior is binding the reviewed receipt while the item is still OPEN, and enforcing that binding when approval is later applied.

## Partial baseline and invariance evidence

Active generation:

`refresh_20261022T043408Z_refresh_fundamentals_bb23ca223d59_production_eb6f648d`

The published watermark is `2026-10-21`; the successful run remains `20261022T043408Z_refresh_fundamentals_bb23ca223d59_production_eb6f648d`.

The publication journal reports `state=COMPLETED`, `current_publication_step=COMPLETED`, `generation_activation_state=ACTIVATED_AND_VERIFIED`, `postflight_state=PASSED`, and `rollback_recovery_state=NOT_REQUIRED`. No service constructor, recovery path, or publication operation was invoked.

Read-only file hashing reproduced the implementation baseline for all three active financial databases, the active manifest, and the Review Queue:

| File | SHA-256 |
| --- | --- |
| Provider | `cadd3a90f40e0320558b7a6e4de14deb06c77373b9cf3ed81fbb22d26d69dac8` |
| Canonical | `02a13632b45008734ff6078e4e8ba717778bc261471febae504908f951c66b6b` |
| Analysis | `e984fe99df5a3683e76ad9fe9a3dd5c6f55f87d530ef7ca0a30ac5cbb9436adf` |
| Active manifest | `f07a6022eb747f10dc4211b996ffd4fa52bcc5a3393fcc57f32c4cc931a47401` |
| Review Queue | `5864471eb66848b015e537308f2f6ba245c1ff9fa910bdca35744c1519fd6652` |
| Publication journal | `855a3619dc5bc109abc6f74d7705d6237a1ee0c779da4b5fe9f7824a0979b9f2` |

The queue has 6 legacy review rows, 42 legacy audit rows, and 4 P/B ownership reviews. Neither `accounting_boundary_review_item` nor its audit table exists. No combined WFRD review item is registered. Queue reads used SQLite read-only mode with `query_only=ON`; no initializer or registration method was called.

Published WFRD Q4 identity/date reads:

| Fiscal identity | Quarter ID | Period end | Availability / first-public date |
| --- | --- | --- | --- |
| 2019 Q4 | 84335 | 2019-12-31 | 2020-03-16 / 2020-03-16 |
| 2020 Q4 | 84339 | 2020-12-31 | 2021-02-19 / 2021-02-19 |

Both belong to company 2368. The identical published DB hashes establish that stored financial values, identity mappings, provenance, parent-equity/P/B bindings, and publication dates have not changed from the implementation baseline. They do not establish freshness of external provider evidence. A new independent source/P/B/rehearsal validation was not completed after the source-defect stop.

The pre-existing modified publication journal, untracked active manifest/generation data, and unrelated OHLCV/research files were left untouched. Only this report is committed.

## Proposal, receipt, and intended semantics

Both work artifacts still exist. The values below were read from them, not certified as current approval material:

- Proposal: `/tmp/wfrd_implementation2/proposal_0ddf1bdf2b398145521d990ed4a468e7a23a38e58ebfaf719f5f1484efc5ce34.json`.
- Stored proposal fingerprint: `0ddf1bdf2b398145521d990ed4a468e7a23a38e58ebfaf719f5f1484efc5ce34`.
- Receipt: `/tmp/wfrd_implementation2/receipt_1275e85ca75f46eadd44a24bd28b7ed32ab0b87344aafd837b837965a776b380.json`.
- Stored receipt fingerprint: `1275e85ca75f46eadd44a24bd28b7ed32ab0b87344aafd837b837965a776b380`.
- The proposal stores `status=OPEN`, `operator=null`, `stale=false`, and `production_authorized=false`. The receipt stores `mode=COPY_ONLY`, `passed=true`, and the matching proposal fingerprint. These stored flags are not fresh validation results.

The intended resolution remains:

| Observation | Exact source key | Intended interpretation |
| --- | --- | --- |
| ARQ | `(WFRD, ARQ, 2020-03-16, 2019-12-31)` | Preserve accepted/effective 2019 Q4, retaining raw provider 2020 Q4 |
| Removed MRQ | `(WFRD, MRQ, 2019-12-31, 2019-12-31)` | Historical `SUCCESSOR_YEAR_END_STOCKS`; calculation eligible false |
| Current MRQ | `(WFRD, MRQ, 2019-12-13, 2019-12-13)` | Current `PREDECESSOR` / `PARTIAL_PERIOD_FLOW`; calculation eligible false |

The two linked actions remain `PRESERVE_ACCEPTED_FISCAL_IDENTITY` and `RETAIN_REMOVED_ACCEPTED_MRQ_AS_HISTORICAL_SOURCE`. No runtime interpretation was applied, no MRQ archive was installed, and the records were not merged.

## Incomplete gates and next phase

| Gate | Result |
| --- | --- |
| Latest scheduler inspection | Completed |
| Fresh provider fetch / complete-history fingerprint recomputation | Not performed after source-defect stop |
| Current proposal verifier / `validate_pending` | Not completed |
| Proposal stale | UNKNOWN; stored false is not current proof |
| Current receipt/candidate hash and semantic revalidation | Not completed |
| Proposal registered | NO |
| Live combined review status | NOT_REGISTERED |
| Explicit operator YES/NO | Not requested; prerequisites unmet |
| Combined approval / audit | NOT_APPROVED; no new audit |
| New manual Preview / classification / Test gate | Not run or recomputed |
| WFRD blocker | Still present in latest overnight Preview; not cleared by this task |
| Test executed / Production executed | NO / NO |
| Production financial state / active generation / watermark changed | NO / NO / NO |

No pytest was run because source was unchanged. Verification was limited to scheduler/runtime artifact inspection, backend contract inspection, read-only SQLite checks, and file hashing.

Recommended next phase: a separate bounded implementation task to persist the exact validated rehearsal receipt/fingerprint alongside the OPEN proposal and its audit, and require that same receipt binding at approval. Preserve proposal immutability, both linked actions, existing copy-only rejection, and the financial publication lifecycle. Then restart Stage 1 with a fresh live provider fetch and complete proposal/receipt/baseline revalidation. Only after successful OPEN registration should the exact fingerprint-bound YES/NO question be presented. This report grants no approval and no Test/Production authorization.

## Fresh Stage 1 attempt after OPEN receipt binding V2

Task: WFRD-REVIEW-APPROVAL-1-STAGE1. Date: 2026-10-27. HEAD at inspection: `c937d67e6bf03f2ebad95cc6ceaafb802084f14c`.

**STOPPED_CONFIRMATION_CONTRACT_GAP, before real registration.** The previous receipt-registration defect above was resolved by [OPEN receipt binding V2](wfrd_open_receipt_binding.md). This attempt found a different mismatch between the requested confirmation output and the implemented read-only confirmation method. No source was changed, and the previous STOP history is preserved.

### Latest scheduler inspected first

The newest scheduler FULL_WORKFLOW parent remains `20261027T052613Z_refresh_fundamentals_d00eb7239fed_full_workflow_08a70a67`, with exact Preview child `20261027T052613Z_refresh_fundamentals_c274483eb886`. Freshly reading the parent's request/result and child's result confirmed:

| Field | Result |
| --- | --- |
| Workflow outcome | STOPPED |
| Preview outcome | REVIEW_REQUIRED |
| WFRD classification | REVIEW_REQUIRED |
| WFRD scope | GLOBAL_BLOCKING_REVIEW |
| WFRD reasons | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION; SAME_FISCAL_SOURCE_KEY_REPLACEMENT |
| Safe effective changes | 93 |
| Global blockers | 1, WFRD |
| Held/local items | 0 |
| Review required | 1 |
| Test authorized | NO, GLOBAL_BLOCKER_PRESENT |
| Test ran | NO; only Preview appears in stages |
| Production ran | NO; entered/completed false, database writes 0 |

These are measurements of the latest stored scheduler Preview, not a new Preview or newly granted authorization. No scheduler artifact was modified.

### Exact confirmation mismatch

Section H requires `accounting_boundary_approval_confirmation(resolution_id)` to return the existing confirmation fields plus “both actions / resolution identity.” In `rawcandle/fundamentals/admin/ui_service.py`, the method currently returns only:

```text
status
proposal_fingerprint
receipt_fingerprint
receipt_passed
baseline_generation
candidate_sha256
```

It does not explicitly return `resolution_id` or the linked actions. Those values are already present in the durable item/binding, and the function validates that binding internally. Therefore this is a confirmation-output contract gap; it is not a loss of stored receipt evidence or a claim that the implemented fingerprint checks are invalid.

Reading the two fields separately from the item would prove their identity, but would not make the specified method return the output Section H explicitly requires. No substituted confirmation output was represented as a passing method result. No real item was registered with a known subsequent gate mismatch.

The current request says, “If a source defect appears: STOP.” It also excludes source changes from this runtime-only phase. Adding the missing confirmation fields and adjusting the focused presentation test therefore belongs to a separate bounded implementation phase. No source fix or pytest run was made here.

### Read-only closeout baseline

The active generation remains `refresh_20261022T043408Z_refresh_fundamentals_bb23ca223d59_production_eb6f648d`; provider watermark remains `2026-10-21`. The journal remains COMPLETED / ACTIVATED_AND_VERIFIED / PASSED / NOT_REQUIRED. Fresh hashes reproduce the values in the previous baseline table: provider, canonical, analysis, active manifest, Review Queue, and publication journal are unchanged.

The queue still has 6 legacy review rows, 42 legacy audit rows, and 4 P/B ownership reviews. No combined item or combined audit table exists. No queue constructor/initializer, registration method, approval method, recovery operation, or financial write was invoked. Existing unrelated worktree changes were left untouched.

### Gates not reached

| Gate | Result |
| --- | --- |
| Fresh provider fetch | Not performed after confirmation-contract stop |
| Current proposal freshness | NOT_REVALIDATED in this attempt |
| Current V2 receipt freshness / physical candidate checks | NOT_REVALIDATED in this attempt |
| Registration preflight | Not run |
| Real OPEN registration | NO |
| Registered decision / receipt binding / audit | No item registered; no event appended |
| Explicit approval question | Not presented; prerequisites unmet |
| Approval / new Preview / Test / Production | None performed |
| WFRD blocker cleared | NO |
| Financial DBs / active generation / watermark changed | NO |
| Live Review Queue changed | NO |

The request's known proposal fingerprint remains `0ddf1bdf2b398145521d990ed4a468e7a23a38e58ebfaf719f5f1484efc5ce34`; its known V2 receipt fingerprint is `b154760b9e948ce98e5515a661e1df8b87de91fddf2dffe92b934804bcdb07b3`. Neither is certified fresh by this stopped attempt. The earlier implementation's successful checks are historical evidence, not reused authorization.

Recommended next phase: add explicit resolution identity and both linked actions to the read-only confirmation response, preserving all existing fingerprint checks and non-authoritative semantics, and cover that response with the directly relevant service test. Then restart Stage 1 from the latest scheduler inspection and fresh live provider/proposal/V2 receipt validation. No approval consent, Test authorization, or Production authorization is granted by this report. Only this documentation update is committed; nothing is pushed.

## Stage 1 restart: exact OPEN registration and explicit approval gate

Task: WFRD-REVIEW-APPROVAL-1-STAGE1-RESTART. Date: 2026-10-27. Implementation HEAD at validation: `557bdf08b42d47884d9f88f60485c87fd0be240e`.

**Stage 1 validation and registration PASS. Status OPEN; operator YES/NO pending. No approval, new Preview, Test, or Production was performed.** The earlier registration and confirmation gaps were resolved by the documented implementation commits before this restart. No source changed and no pytest ran in this runtime phase.

### Latest scheduler state inspected before proposal access

Fresh inspection of the newest scheduler FULL_WORKFLOW parent and exact Preview child confirmed the same unresolved WFRD blocker:

| Field | Measured latest stored result |
| --- | --- |
| Parent | `20261027T052613Z_refresh_fundamentals_d00eb7239fed_full_workflow_08a70a67` |
| Preview child | `20261027T052613Z_refresh_fundamentals_c274483eb886` |
| Workflow / Preview outcomes | STOPPED / REVIEW_REQUIRED |
| WFRD classification / scope | REVIEW_REQUIRED / GLOBAL_BLOCKING_REVIEW |
| WFRD reasons | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION; SAME_FISCAL_SOURCE_KEY_REPLACEMENT |
| Safe effective changes | 93 |
| Global blockers | 1, WFRD |
| Held/local / review required | 0 / 1 |
| Test authorized | NO, GLOBAL_BLOCKER_PRESENT |
| Production authorized | NO, GLOBAL_BLOCKER_PRESENT |
| Test / Production ran | NO / NO; only Preview stage, Production entered/completed false, writes 0 |

The historical scheduler result remains unmodified. Registration does not retroactively alter its classification, counts, or authorization.

### Fresh live baseline

Active generation remains `refresh_20261022T043408Z_refresh_fundamentals_bb23ca223d59_production_eb6f648d`, watermark `2026-10-21`, successful run `20261022T043408Z_refresh_fundamentals_bb23ca223d59_production_eb6f648d`. Journal state/step remain COMPLETED, activation ACTIVATED_AND_VERIFIED, postflight PASSED, recovery NOT_REQUIRED.

Before registration, the queue had 6 legacy review rows, 42 legacy audit rows, 4 P/B ownership rows, and no combined tables/item. All existing worktree changes were recorded and left untouched. Baseline identity is company/security 2368/2379, `SEC_CIK:0001603923`, WFRD, Sharadar permaticker 635310. The 27 accepted WFRD parent-equity source bindings are all ARQ; full source/provenance records were captured and compared after registration.

| Accepted quarter | Quarter ID | Period end | Source availability / first-public date |
| --- | --- | --- | --- |
| 2019 Q4 | 84335 | 2019-12-31 | 2020-03-16 / 2020-03-16 |
| 2020 Q4 | 84339 | 2020-12-31 | 2021-02-19 / 2021-02-19 |

### Fresh provider evidence and proposal validation

The normal Sharadar client fetched fresh COMPLETE histories without validation errors. The service independently fetched and revalidated both dimensions again during actual registration.

| Dimension | Rows | Raw comparison fingerprint | Effective fingerprint |
| --- | --- | --- | --- |
| ARQ | 28 | `fba6bf8b3bf554f9a1d501362facb3db82ce78df4fc0d62d373489d0a173838c` | `94a9e4940bcaf351f0a28b6628da5a3edf6d7ee250ed1a77ee9ebc255780b695` |
| MRQ | 32 | `d8fd585f22669710e25f160ae326e322312d9bbe97a56b79a426ed1d015d9cef` | `f64e0a571711993723d7bbba91c4a80f7ff01c0ae0bed842d304d7cb03372edb` |

The exact ARQ `(WFRD, ARQ, 2020-03-16, 2019-12-31)` remains provider-native `2020-Q4`, lastupdated `2026-10-22`. Normalized fingerprint is `6bf770f0d7b055d5240996d5064a615b5f78cd55e6c95d1cc1cb896f21936855`; its 22-field financial fingerprint is `479d8937aea886c6d1cee338a47c4e6d0590d46bf89e48dd6c30e6fdb8f2e05a`, unchanged from accepted evidence. Genuine `(WFRD, ARQ, 2021-02-19, 2020-12-31)` is present as 2020 Q4.

Old MRQ `(WFRD, MRQ, 2019-12-31, 2019-12-31)` is absent from the complete current response. Current `(WFRD, MRQ, 2019-12-13, 2019-12-13)` is present with normalized fingerprint `a133a4f4a8d732975f5fd76be7a5257989926f737d49c48294735c497dcf3c67` and financial fingerprint `b84a41068c7acd0d6854c0a253c898b18f80a893798797bf2d4c10be2190df3f`. Its only non-null comparison financial fields remain OCF -68m, capex -73m, FCF -141m, and weighted shares 1,004m. Complete-response absence evidence matches the proposal. There is no new conflicting boundary observation.

`verify()` and `validate_pending()` passed against the current published stores, fresh histories, and identity. Exact fingerprint, OPEN/operator-null/non-stale/non-Production-authorized proposal semantics, both actions, three source keys, established Q4 identities/dates, accepted identity mappings, and authoritative review/policy hashes match. No proposal or receipt was regenerated.

### V2 receipt, physical candidates, and preflight

Proposal fingerprint: `0ddf1bdf2b398145521d990ed4a468e7a23a38e58ebfaf719f5f1484efc5ce34`.

V2 receipt fingerprint: `b154760b9e948ce98e5515a661e1df8b87de91fddf2dffe92b934804bcdb07b3`.

Resolution ID: `boundary_3446e01f1422ebb5f7b3ea9e4a7e0f194cb5c8503669e5ed06b515659d0d1f5d`.

The exact known `/tmp` artifacts were read and validated, rather than trusted from earlier reports. Receipt schema is WFRD_ACCOUNTING_BOUNDARY_REHEARSAL_V2, mode COPY_ONLY, passed true; its recomputed fingerprint, proposal/resolution relation, baseline, scope, assertions, and result evidence all pass. Candidate files are regular files, not symlinks; exact SHA-256, SQLite quick checks, and FK checks pass:

| Candidate | SHA-256 |
| --- | --- |
| Provider | `327316b27bfd58fe74102f69a0d583182caca52752acfd37660e15e05bc82394` |
| Canonical | `02c63de55e72b9914556626a1bfbfb9ed68eec7a8999f2852ac4a6c8bf9917f5` |

All seven assertions are PASS: both_q4s, established_dates, no_existing_financial_change, unrelated_tickers, historical_only_archive, mrq_nonfinancial, and pb_arq_binding. Independent read-only SQL comparison against the current canonical DB found all 89,970 existing quarter identity/value/date projections unchanged, with zero changed/missing existing quarters and zero unrelated company additions/changes. The sole added quarter is the previously documented independent WFRD 2026 Q3.

The candidate has the exact immutable historical-only old MRQ evidence and 32 current MRQ observations, including December 13 and excluding old December 31. Current predecessor partial-flow context matches every bound field, with all financial calculation eligibility flags false. Candidate ARQ remains raw 2020 Q4 and effective 2019 Q4. Both accepted Q4s/dates and ARQ P/B bindings pass physical verification. No candidate was installed into an active store.

`validate_registration()` passed. The compact binding covers exact fingerprints/resolution, receipt PASS, generation, manifest/state, accepted-state evidence, hashes, both ordered actions, all three keys, complete response evidence, all assertions, and result integrity. Bound generation-manifest semantic fingerprint: `04d3e06088b06e5c57c4f2105e87b72250174c91e4a2d2f54b14bc29ed798a56`; baseline state fingerprint: `57a90cd4b6990478044036c0ff03c80b04dc37c27a6cc90b41dca65dcecb6ed6`; accepted-state fingerprint: `52a21f789a5d471a7969d714ef3c70ee7585075c5b253554dc9d23f5a6a446cc`.

### Exact OPEN registration, audit, and confirmation

The one authorized mutation used `FundamentalsAdminUIService.register_accounting_boundary_proposal(proposal, rehearsal=receipt)` on the normal live queue. Startup recovery was explicitly disabled; no recovery/publication path or manual queue edit was used. The service performed its own current-source and physical receipt preflight before registration.

Readback confirms exactly one combined item, schema WFRD_ACCOUNTING_BOUNDARY_REVIEW_ITEM_V2, status OPEN, decision None, unchanged proposal, operator null, stale false, no stale/rejection reason, production_authorized false. The receipt binding is schema WFRD_ACCOUNTING_BOUNDARY_RECEIPT_BINDING_V1, validated and protected by the existing immutable-binding trigger. Persisted binding fingerprint: `a80ab6d8172059a17507b76b829d8f0bc4e62f3c4397b4aea58d83ba224f05f6`. The registration-time metadata is new; all proposal, receipt, scope, baseline, and candidate evidence fields match preflight exactly.

Exactly one new audit row exists: ID 1, event REGISTERED_OPEN, timestamp `2026-10-27T10:10:31Z`, status OPEN, exact proposal/receipt/resolution, baseline generation, both candidate hashes, receipt PASS, and the exact registered item. There is no APPROVED event or operator decision. Append-only audit triggers are present. All pre-existing queue table contents, counts, fingerprints, and schemas are unchanged, including the legacy audit and P/B reviews. Only the two additive combined tables and their normal constraints/triggers were added.

The read-only confirmation method returns exactly:

```json
{
  "resolution_id": "boundary_3446e01f1422ebb5f7b3ea9e4a7e0f194cb5c8503669e5ed06b515659d0d1f5d",
  "linked_actions": [
    "PRESERVE_ACCEPTED_FISCAL_IDENTITY",
    "RETAIN_REMOVED_ACCEPTED_MRQ_AS_HISTORICAL_SOURCE"
  ],
  "status": "OPEN",
  "proposal_fingerprint": "0ddf1bdf2b398145521d990ed4a468e7a23a38e58ebfaf719f5f1484efc5ce34",
  "receipt_fingerprint": "b154760b9e948ce98e5515a661e1df8b87de91fddf2dffe92b934804bcdb07b3",
  "receipt_passed": true,
  "baseline_generation": "refresh_20261022T043408Z_refresh_fundamentals_bb23ca223d59_production_eb6f648d",
  "candidate_sha256": {
    "provider": "327316b27bfd58fe74102f69a0d583182caca52752acfd37660e15e05bc82394",
    "canonical": "02c63de55e72b9914556626a1bfbfb9ed68eec7a8999f2852ac4a6c8bf9917f5"
  }
}
```

Requested ID, SQL row key, proposal ID, and receipt-binding ID agree; actions agree in the exact ARQ-then-MRQ order. A read-only runtime evaluation reports `pending=true`, `applied=false`, `stale=false`. There is no queued decision. WFRD remains globally unresolved; registration grants no Preview/Test/Production authorization.

### Production invariance after registration

Provider/canonical/analysis DBs, active and generation manifests, journal, generation, watermark, both WFRD Q4s/first-public dates, company/security/permaticker identity, and complete WFRD field/P/B source/provenance bindings are unchanged. Active provider has neither an installed reviewed decision nor the historical MRQ archive.

| Authority | Before / after SHA-256 |
| --- | --- |
| Provider | `cadd3a90f40e0320558b7a6e4de14deb06c77373b9cf3ed81fbb22d26d69dac8` / same |
| Canonical | `02a13632b45008734ff6078e4e8ba717778bc261471febae504908f951c66b6b` / same |
| Analysis | `e984fe99df5a3683e76ad9fe9a3dd5c6f55f87d530ef7ca0a30ac5cbb9436adf` / same |
| Active / generation manifest | `f07a6022eb747f10dc4211b996ffd4fa52bcc5a3393fcc57f32c4cc931a47401` / same |
| Publication journal | `855a3619dc5bc109abc6f74d7705d6237a1ee0c779da4b5fe9f7824a0979b9f2` / same |
| Review Queue | `5864471eb66848b015e537308f2f6ba245c1ff9fa910bdca35744c1519fd6652` / `18006f50998084a7e0674d353f46814b76b69892100eea8186e24bdc62d53fef` |

The queue difference is the authorized OPEN item, its one registration event, and additive combined schema. No unrelated queue data changed. Only this documentation update is committed. No runtime queue/artifact/DB/download/manifest/journal or unrelated work is committed; nothing is pushed.

### Explicit operator gate: awaiting YES/NO

The final response asks the following exact-scope question. No answer is assumed or recorded by this report:

> Do you approve this exact WFRD combined accounting-boundary resolution, resolution ID `boundary_3446e01f1422ebb5f7b3ea9e4a7e0f194cb5c8503669e5ed06b515659d0d1f5d`, bound to proposal fingerprint `0ddf1bdf2b398145521d990ed4a468e7a23a38e58ebfaf719f5f1484efc5ce34` and registered V2 rehearsal receipt fingerprint `b154760b9e948ce98e5515a661e1df8b87de91fddf2dffe92b934804bcdb07b3`, consisting of BOTH linked actions: (1) PRESERVE_ACCEPTED_FISCAL_IDENTITY for exact source key (WFRD, ARQ, 2020-03-16, 2019-12-31), preserving effective canonical 2019 Q4 while retaining raw provider 2020 Q4; and (2) RETAIN_REMOVED_ACCEPTED_MRQ_AS_HISTORICAL_SOURCE for exact removed key (WFRD, MRQ, 2019-12-31, 2019-12-31), while keeping current (WFRD, MRQ, 2019-12-13, 2019-12-13) as predecessor partial-period evidence and calculation-ineligible? YES/NO

YES approves both linked actions together. It authorizes no Test, no Production, and no unrelated review item. Any source/baseline/evidence drift before approval application invalidates consent. Stop here and await the explicit answer. Only a later YES permits post-YES fresh revalidation, exact named-operator combined approval, and the original Stage 2's one new MANUAL/PREVIEW_ONLY run. Neither approval nor that Preview is performed by this Stage 1 task.
