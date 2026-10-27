# WFRD combined preservation approval: stopped before registration

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
