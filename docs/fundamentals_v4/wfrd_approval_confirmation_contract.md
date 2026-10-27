# WFRD approval confirmation contract

Task: WFRD-APPROVAL-CONFIRMATION-1. Date: 2026-10-27.

## Gap reproduced before changes

At HEAD `18dd70b1fab95b1d55f3a290310667459909a4e8`, a valid synthetic proposal and V2 receipt were registered OPEN through the service on a disposable queue. Calling `accounting_boundary_approval_confirmation(resolution_id)` returned exactly:

```text
status
proposal_fingerprint
receipt_fingerprint
receipt_passed
baseline_generation
candidate_sha256
```

The response omitted `resolution_id` and `linked_actions`, reproducing the latest [approval STOP report](wfrd_combined_preservation_approval.md). No live WFRD queue was used. Live financial DB, manifest, journal, and queue hashes were captured before implementation.

The governing contracts are the [combined preservation implementation](wfrd_combined_preservation_implementation.md) and [OPEN receipt binding V2](wfrd_open_receipt_binding.md). This task changes read-only confirmation presentation and validation only.

## Authoritative resolution and action identity

The confirmation method now selects the exact combined queue row by the SQL primary key `resolution_id` using SQLite read-only mode and `query_only=ON`. It no longer selects an item solely by an ID embedded in its JSON proposal. The requested ID, selected row ID, registered proposal ID, and receipt-binding ID must all agree. Any explicit item-level JSON ID must also agree with the row. The returned ID comes from that validated registered proposal, not an unchecked echo of the caller's argument.

The method uses the existing proposal verifier and receipt-binding verifier. These validate proposal/binding fingerprints, resolution scope, exact source keys, authoritative evidence, and the action agreement. The registered receipt binding's `linked_actions` must equal the proposal's ordered ARQ action followed by MRQ action. Under the existing WFRD contract these are `PRESERVE_ACCEPTED_FISCAL_IDENTITY`, then `RETAIN_REMOVED_ACCEPTED_MRQ_AS_HISTORICAL_SOURCE`. Missing, empty, duplicated, reordered, unknown, or contradictory action lists reject. The UI/service does not hard-code an action list, sort action labels, or fill missing actions from a separate proposal supplied by the caller. It returns a copied list from the validated persisted binding.

## Final response contract

| Field | Authoritative value |
| --- | --- |
| `resolution_id` | Registered proposal ID, checked against input, SQL row, and binding |
| `linked_actions` | Registered binding's exact ordered action list, verified against proposal |
| `status` | OPEN |
| `proposal_fingerprint` | Verified registered proposal fingerprint |
| `receipt_fingerprint` | Exact registered V2 receipt identity |
| `receipt_passed` | Validated true |
| `baseline_generation` | Registered binding's nonempty generation string |
| `candidate_sha256` | Registered provider and canonical SHA-256 values |

The existing `baseline_generation` name is retained as the equivalent of `baseline_generation_id`. The existing nested `candidate_sha256.provider` and `.canonical` values are retained rather than renamed to flat fields. Only `resolution_id` and `linked_actions` are added. The existing confirmation consumer can display both new fields alongside all previous values without consulting another proposal object. Returned lists/dictionaries do not expose mutable queue state.

## Fail-closed validation and compatibility

Before returning any payload, the method requires supported combined item schema `WFRD_ACCOUNTING_BOUNDARY_REVIEW_ITEM_V2`, status OPEN, an explicitly present `decision=None`, and no contradictory stale/rejection reason. Proposal and receipt-binding integrity checks remain mandatory. The receipt must be PASS, match the proposal and resolution, and carry valid baseline and candidate-hash evidence. The method adds the required nonempty baseline-generation type check.

Unknown/missing requested IDs, mismatched SQL/proposal/binding IDs, unsupported or missing schema, missing proposal/fingerprints/binding, failed receipt, inconsistent actions, missing candidate/baseline evidence, non-OPEN status, and an unexpected decision reject through `BoundaryReviewError`. Malformed JSON and structurally malformed records are converted to the same review-domain error type. No partial response is returned. Legacy OPEN items without a valid binding remain non-approvable, with no upgrade or schema write on read.

Confirmation performs no provider request, physical candidate check, current canonical query, or fresh proposal/source staleness validation. Those remain Stage 1 and approval responsibilities. The existing bound proposal/authority integrity verification remains in use. Confirmation does not initialize/migrate a queue, append audit, create a decision, clear a blocker, or grant workflow authorization.

`approve_accounting_boundary_review(...)` is unchanged. It still checks publication safety, requires a named operator and the exact proposal/registered receipt fingerprints, fetches current source evidence, and delegates current source/baseline verification and atomic approval to the existing backend. The extra confirmation fields do not relax any approval checks. No unrelated queue actions, queue schemas, shared fixtures, Policy V1, or resolver logic changed.

## Focused tests

Commands:

```text
PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m pytest -x -q --tb=short -p no:cacheprovider -o addopts='' tests/test_wfrd_accounting_boundary_review.py -k 'confirmation or service or approval or old_open or queue_registration or unrelated_queue'
PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m pytest -x -q --tb=short -p no:cacheprovider -o addopts='' tests/test_fundamentals_admin_refresh_review_queue.py
```

Results: **65 passed, 78 deselected** in the focused WFRD selection; **52 passed** in the directly relevant Review Queue group. Total: **117 passed**. Full suite: **NOT RUN**. No P/B group was needed because shared queue/service fixtures were not changed; new confirmation fixtures are local to the WFRD test module.

Tests cover exact ID/action output and ordering, actual SQL key selection, input/item/proposal/receipt mismatches, supported schema, missing proposal and fingerprints, missing/empty/duplicate/unknown/reversed actions, missing binding, failed PASS, malformed records/JSON, missing candidate hashes and baseline, OPEN-only/decision invariants, old items, and semantically empty baseline with recomputed valid hashes. Corrupt binding fixtures recompute binding fingerprints where applicable so semantic validation is exercised beyond checksum failure.

The valid synthetic OPEN confirmation test verifies byte hashes of queue/provider/canonical files, unchanged item/audit, no provider fetch, no approval, and unchanged GLOBAL_BLOCKING_REVIEW semantics. Returned-list/hash mutations cannot change persisted evidence. Existing selected service tests still reject wrong receipt fingerprints and successfully approve the same registered receipt with fresh synthetic source reads. Unrelated queue-row invariance and existing local fiscal, retained-history, true-removal, wait/retry, and review gating regressions pass. No real runtime approval is used by these tests.

## Read-only live invariance

The latest stored scheduler FULL_WORKFLOW parent remains `20261027T052613Z_refresh_fundamentals_d00eb7239fed_full_workflow_08a70a67`, with Preview child `20261027T052613Z_refresh_fundamentals_c274483eb886`. Its result remains STOPPED / REVIEW_REQUIRED: WFRD is the sole GLOBAL_BLOCKING_REVIEW, 93 safe effective changes, Test unauthorized (`GLOBAL_BLOCKER_PRESENT`), and no Production entry or database writes. These historical Preview results were read, not rerun or modified.

No real WFRD combined item exists. Before/after file hashes confirm the live queue and Production authorities are unchanged:

| Authority | SHA-256 |
| --- | --- |
| Provider | `cadd3a90f40e0320558b7a6e4de14deb06c77373b9cf3ed81fbb22d26d69dac8` |
| Canonical | `02a13632b45008734ff6078e4e8ba717778bc261471febae504908f951c66b6b` |
| Analysis | `e984fe99df5a3683e76ad9fe9a3dd5c6f55f87d530ef7ca0a30ac5cbb9436adf` |
| Active manifest | `f07a6022eb747f10dc4211b996ffd4fa52bcc5a3393fcc57f32c4cc931a47401` |
| Live Review Queue | `5864471eb66848b015e537308f2f6ba245c1ff9fa910bdca35744c1519fd6652` |
| Publication journal | `855a3619dc5bc109abc6f74d7705d6237a1ee0c779da4b5fe9f7824a0979b9f2` |

Active generation remains `refresh_20261022T043408Z_refresh_fundamentals_bb23ca223d59_production_eb6f648d`; watermark remains `2026-10-21`. No real registration, approval, Preview, Test, Production, active archive installation, ARQ overlay installation, or blocker clearing occurred. Full real proposal/receipt freshness was deliberately not repeated in this phase. Existing unrelated worktree changes were preserved. Only confirmation source, focused WFRD tests, and this report are committed; no runtime artifacts are committed and nothing is pushed.

## Restart Stage 1

1. Restart WFRD-REVIEW-APPROVAL-1 Stage 1 with the then-latest scheduler parent/Preview inspection. Capture a fresh live baseline/queue and fetch COMPLETE WFRD ARQ/MRQ histories.
2. Load the exact proposal and V2 receipt identified in the OPEN receipt binding report: proposal `0ddf1bdf2b398145521d990ed4a468e7a23a38e58ebfaf719f5f1484efc5ce34` and receipt `b154760b9e948ce98e5515a661e1df8b87de91fddf2dffe92b934804bcdb07b3`. Treat their `/tmp` paths and this phase's prior validation as non-authoritative work evidence. Run current `verify()`, `validate_pending()`, physical receipt/candidate verification, and `validate_registration()` against the fresh live baseline. Stop on drift; do not reuse old freshness or consent.
3. Only after all Stage 1 gates pass, perform the separately authorized exact OPEN registration with `register_accounting_boundary_proposal(proposal, rehearsal=receipt)`. Read back the item/audit and call `accounting_boundary_approval_confirmation(resolution_id)`. Verify the returned ID/actions, both fingerprints, PASS, baseline, hashes, OPEN/decision invariants, unchanged unrelated queue rows and Production state, and the remaining blocker.
4. Update the approval history and present the one explicit YES/NO question bound to those exact registered identities and both actions. STOP. This implementation phase supplies no registration or approval consent. Only a later explicit YES can start post-YES revalidation and the original Stage 2 manual Preview-only workflow; it authorizes no Test or Production.
