# WFRD OPEN rehearsal receipt binding

Task: WFRD-OPEN-RECEIPT-BINDING-2. Date: 2026-10-27.

## Defect reproduced before source changes

At HEAD `1d3a1560e112f701d6b9e2ab501b5525d53510f7`, the existing WFRD fixture independently passed `verify(proposal)` and `validate_rehearsal_receipt(proposal, receipt)`. On a disposable synthetic queue, `FundamentalsAdminUIService.register_accounting_boundary_proposal(proposal)` accepted only the proposal and returned exactly `proposal`, `decision`, `status`, `stale_reason`, and `rejected_reason`. The OPEN audit stored that same object. Neither recorded receipt identity. Approval accepted a separately supplied rehearsal and could not prove it was the rehearsal reviewed at registration.

The live queue was not used for reproduction. Its file hash and the published provider/canonical/analysis, active manifest, and publication journal hashes were captured before implementation.

Governing references: [implementation](wfrd_combined_preservation_implementation.md) and [approval stop report](wfrd_combined_preservation_approval.md). The source-key meanings and policies remain unchanged.

## Registration and approval contracts

The combined-review service now exposes:

```python
register_accounting_boundary_proposal(proposal, *, rehearsal=receipt)
accounting_boundary_approval_confirmation(resolution_id)
approve_accounting_boundary_review(
    resolution_id, *, operator, proposal_fingerprint, receipt_fingerprint
)
```

Registration requires the actual receipt data. `validate_registration()` is a read-only preflight: it verifies the proposal, receipt integrity and scope, actual inactive candidate files and hashes, fresh complete provider histories, identity, baseline, established Q4s, and accepted financial/P/B provenance. The service fetches ARQ/MRQ again through the normal client when registering and when approving; tests inject a synthetic client and paths. The shared source resolver and unrelated review APIs are unchanged.

`receipt_binding()` checks the versioned receipt before queue writes. It requires exact proposal/resolution identity, baseline generation/manifest/state, both linked actions, the three source keys, COPY_ONLY/PASS, all seven rehearsal assertions, both candidate SHA-256 values, creation time, complete-history evidence, accepted-state fingerprint, result fingerprint, and the receipt's own recomputed fingerprint. The existing physical verifier also checks the actual candidate hashes, SQLite quick/FK integrity, installed synthetic copy-only decision's exact proposal, historical/current MRQ store invariants, both Q4 identities/dates, and ARQ parent-equity bindings. A fingerprint string alone cannot register evidence.

The receipt assertions remain `both_q4s`, `established_dates`, `no_existing_financial_change`, `unrelated_tickers`, `historical_only_archive`, `mrq_nonfinancial`, and `pb_arq_binding`. The receipt producer runs the real inactive-copy reconciliation and verifies these before issuing PASS. Assertions are not inferred from the requested outcome.

Approval loads the OPEN item and checks the displayed proposal/receipt fingerprints before fetching evidence. The backend rereads the item under a SQLite write transaction, verifies the immutable binding, and revalidates current complete histories, identity, generation, refresh state, canonical Q4s, dates, and accepted financial/provenance/P/B state. It approves both linked actions together with a named operator and the same bound receipt identity. A different passing receipt is rejected. The previous unregistered `approve(proposal, operator=..., rehearsal=...)` entry point now fails closed; callers use `approve_registered()` through the service. Direct decision injection into `save_item()` is also rejected.

The read-only confirmation method returns status, exact proposal fingerprint, exact registered receipt fingerprint, receipt PASS, baseline generation, and both candidate hashes. It does not approve or mutate the stored binding.

## Durable authority and schema

The preferred compact queue model is implemented. No durable file hierarchy was added.

- Proposal contract stays `WFRD_ACCOUNTING_BOUNDARY_REVIEW_V1`. The supplied proposal and its fingerprint are unchanged.
- New receipt format is `WFRD_ACCOUNTING_BOUNDARY_REHEARSAL_V2`.
- Combined item JSON is `WFRD_ACCOUNTING_BOUNDARY_REVIEW_ITEM_V2`.
- Its `rehearsal_receipt_binding` has schema `WFRD_ACCOUNTING_BOUNDARY_RECEIPT_BINDING_V1`.

The compact object retains receipt version/fingerprint/creation time, registration time, proposal fingerprint, resolution ID, mode/PASS, baseline generation/manifest/state, accepted-state fingerprint, candidate hashes, both actions, exact source keys, complete ARQ/MRQ response evidence, all seven assertions, and a result fingerprint. A separate binding fingerprint protects the persisted compact representation. The measured real binding is 2,384 JSON bytes. It contains no candidate paths, receipt path, full provider receipt payload, or candidate databases.

The accepted-state fingerprint covers both accepted Q4 rows, financial values, field provenance, parent-equity source, and parent-equity provenance. The result fingerprint binds the receipt's provider validation, canonical impact, and independent new quarters. Manifest-less synthetic baselines explicitly carry a null manifest fingerprint and still require the proposal's baseline-state fingerprint; real generation evidence carries its actual manifest fingerprint. Missing baseline keys are rejected.

After registration the item and append-only audit are the durable registration evidence. Approval requires neither the original receipt file nor its candidate paths to survive. Tests delete the candidate files after registration and successfully approve using the registered fingerprints plus freshly revalidated source/baseline evidence. Before initial registration, the actual receipt and candidate files are still required and must pass physical validation.

The two existing combined tables keep their SQL columns. Receipt binding and versioning are additive JSON fields. On an existing queue, only combined tables/triggers are initialized; unrelated schemas are not migrated. A brand-new queue receives the normal shared queue initialization before the additive combined tables. Existing databases with no combined tables remain readable without initializing them on read.

Legacy combined items remain readable. An old OPEN item without receipt binding is non-approvable and cannot be silently upgraded by re-registration. Historical decision verification remains readable for the existing copy/published evidence lifecycle; it is not a new registration or approval route.

## Immutability, audit, and staleness

Exact duplicate registration returns the existing item without an additional audit event or reopening a terminal item. Same proposal/different receipt and same resolution/different proposal reject without replacing the original item. The binding is never refreshed to a newer receipt. A SQLite trigger prevents in-place proposal/binding changes. Separate UPDATE/DELETE triggers make the combined audit append-only.

Registration appends `REGISTERED_OPEN` with timestamp, OPEN status, proposal and receipt fingerprints, resolution ID, generation, candidate hashes, PASS, and the registered item. There is no operator approval or Production authorization. Approval appends `APPROVED`, preserving the binding and recording the named operator in the decision. STALE/REJECTED transitions preserve the binding and its original registration audit.

Receipt binding does not waive staleness. Approval rejects source payload/label/key drift, complete-response drift, old-MRQ reappearance, new conflicting boundary observations, generation/manifest/refresh-state changes, canonical identity/date/value changes, identity/permaticker changes, and P/B provenance changes. Failed approval does not rewrite the registered evidence. Pending approved decisions also revalidate full source response fingerprints and accepted-state evidence when Preview evaluates them. Published decisions retain the pre-existing publication lifecycle, including ordinary subsequent source additions.

Registration remains OPEN with `decision=None`, proposal operator null and `production_authorized=false`. OPEN evidence stays globally blocking. Approval does not update an earlier Preview's authorization: a new Preview is required. Archive/interpretation installation remains confined to inactive candidates. No Policy V1 or resolver change was made.

## Focused verification

The targeted commands use `PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m pytest -x -q --tb=short -p no:cacheprovider -o addopts=''` and the existing production-database isolation guard.

The final groups are:

| Group | Result |
| --- | --- |
| `tests/test_wfrd_accounting_boundary_review.py` | 99 unique cases covered: 96 passed in the complete focused run; final receipt subset passed 21, including 2 added malformed-path cases; manifested-generation case passed separately |
| `tests/test_fundamentals_admin_refresh_review_queue.py` | Passed in the 142-case regression run |
| `tests/test_fundamentals_admin_refresh_full_workflow.py` | Passed in the 142-case regression run |
| `tests/test_fundamentals_admin_refresh_preview.py` | Passed in the 142-case regression run |
| `tests/test_fundamentals_pb_new_quarter_review.py` | Passed in the 142-case regression run |

The WFRD group includes the combined service/confirmation/approval tests. Coverage includes missing/malformed/failed receipts, recomputed but wrong proposal/resolution/baseline/action/key bindings, missing hashes, each failed assertion, compact persistence, unchanged proposal, idempotence/conflicts, immutable audit, actual source refetch at both service actions, exact fingerprint approval, a different valid receipt, approval without temporary files, source/identity/baseline/date/P/B drift, old-key reappearance, full ARQ response drift, preserved stale history, old OPEN items, unrelated table/row invariance, unchanged financial DBs, and the requirement for a new synthetic Preview. Existing global/local action regressions and the P/B ownership fixture run unchanged.

The final receipt subset used `-k 'invalid_receipt or registration_requires_real or approval_uses_durable'` after normalizing malformed candidate-path errors into a fail-closed review error. The extra `-k manifested_generation` case proves non-null manifest/state persistence and rejects manifest drift. The four regression files passed **142 tests** together. Across the focused runs, **241 unique cases passed**. Changed Python files parse successfully and whitespace checks pass.

Early targeted failures exposed fixture assumptions: a synthetic generation manifest activated the inactive-copy guard, a new queue required normal initialization, and an attempted MRQ P/B mutation was correctly rejected by the existing ARQ-only CHECK constraint. The fixtures were corrected without changing those safety guards. Full suite: **NOT RUN**.

## Current real WFRD evidence: read-only validation

Fresh read-only normal Sharadar client requests returned COMPLETE:

| Dimension | Rows | Raw comparison fingerprint | Effective fingerprint |
| --- | --- | --- | --- |
| ARQ | 28 | `fba6bf8b3bf554f9a1d501362facb3db82ce78df4fc0d62d373489d0a173838c` | `94a9e4940bcaf351f0a28b6628da5a3edf6d7ee250ed1a77ee9ebc255780b695` |
| MRQ | 32 | `d8fd585f22669710e25f160ae326e322312d9bbe97a56b79a426ed1d015d9cef` | `f64e0a571711993723d7bbba91c4a80f7ff01c0ae0bed842d304d7cb03372edb` |

Both match the old proposal's evidence. `verify()` and `validate_pending()` pass on the real current provider/canonical stores. Company/security remain 2368/2379, company key `SEC_CIK:0001603923`, permaticker `635310`. Both established Q4s and first-public dates remain unchanged; accepted parent-equity/P/B evidence remains ARQ.

The old proposal remains current and was not regenerated:

`0ddf1bdf2b398145521d990ed4a468e7a23a38e58ebfaf719f5f1484efc5ce34`

Path: `/tmp/wfrd_implementation2/proposal_0ddf1bdf2b398145521d990ed4a468e7a23a38e58ebfaf719f5f1484efc5ce34.json`.

The old receipt `1275e85ca75f46eadd44a24bd28b7ed32ab0b87344aafd837b837965a776b380` retains valid physical/semantic evidence, but lacks the new versioned registration metadata and is rejected by the new registration contract. It was not edited or rehashed into a replacement. A fresh full copy-only rehearsal issued a new V2 receipt against the unchanged proposal:

`b154760b9e948ce98e5515a661e1df8b87de91fddf2dffe92b934804bcdb07b3`

Path: `/tmp/wfrd_open_receipt_binding2/receipt_b154760b9e948ce98e5515a661e1df8b87de91fddf2dffe92b934804bcdb07b3.json`.

Candidates are `/tmp/wfrd_open_receipt_binding2/receipt_v2_candidates/{provider.db,canonical.db}`:

| Candidate | SHA-256 |
| --- | --- |
| Provider | `327316b27bfd58fe74102f69a0d583182caca52752acfd37660e15e05bc82394` |
| Canonical | `02c63de55e72b9914556626a1bfbfb9ed68eec7a8999f2852ac4a6c8bf9917f5` |

All seven assertions passed. Actual reconciliation preserved 89,970 existing quarters and their first-public dates, changed/removed zero existing quarters, changed zero unrelated quarters, and preserved source availability. It independently added the legitimate WFRD 2026 Q3 from current source history. Provider verification found no duplicate true keys, FK errors, or orphan children; quick check was `ok`. Current MRQ has 32 rows and excludes the old December 31 key; historical evidence retains that exact observation separately. The predecessor partial-flow context remains calculation-ineligible. Both Q4s and the ARQ parent-equity bindings pass the strengthened physical verifier.

The final read-only `validate_registration()` passes against the unchanged live baseline and the new receipt. Accepted-state fingerprint: `52a21f789a5d471a7969d714ef3c70ee7585075c5b253554dc9d23f5a6a446cc`. This answers that the pair would pass registration preflight; **no real registration was performed**. Work artifacts under `/tmp` are non-authoritative until a later authorized registration validates them and persists the compact binding.

## Production invariance

Active generation remains `refresh_20261022T043408Z_refresh_fundamentals_bb23ca223d59_production_eb6f648d`; watermark remains `2026-10-21`.

| Published authority | Unchanged SHA-256 |
| --- | --- |
| Provider | `cadd3a90f40e0320558b7a6e4de14deb06c77373b9cf3ed81fbb22d26d69dac8` |
| Canonical | `02a13632b45008734ff6078e4e8ba717778bc261471febae504908f951c66b6b` |
| Analysis | `e984fe99df5a3683e76ad9fe9a3dd5c6f55f87d530ef7ca0a30ac5cbb9436adf` |
| Active manifest | `f07a6022eb747f10dc4211b996ffd4fa52bcc5a3393fcc57f32c4cc931a47401` |
| Live Review Queue | `5864471eb66848b015e537308f2f6ba245c1ff9fa910bdca35744c1519fd6652` |
| Publication journal | `855a3619dc5bc109abc6f74d7705d6237a1ee0c779da4b5fe9f7824a0979b9f2` |

No real combined WFRD item or audit table was created. No real approval, Preview, Test, or Production ran. The global blocker was not cleared. No historical archive or ARQ interpretation was installed in active stores. The existing unrelated worktree changes, active generation data, manifest, and modified journal remain untouched. No DB, provider download, runtime receipt, candidate, manifest, journal, or unrelated file is committed. Nothing is pushed.

## Restart WFRD-REVIEW-APPROVAL-1 Stage 1

1. Inspect the then-latest scheduled FULL_WORKFLOW parent and exact Preview child first. The previously inspected October 27 parent stopped at Preview with WFRD as sole global blocker, 93 safe changes, and no Test authorization. Do not reuse its authorization or counts as current measurements.
2. Capture the then-current baseline/queue and fetch COMPLETE WFRD ARQ/MRQ anew. Load the unchanged proposal and the V2 receipt at the paths above. Run `verify()`, `validate_pending()`, and `validate_registration()` with the current stores, histories, and identity. Verify both candidate files still exist and match their receipt hashes, both Q4s/dates, and accepted P/B evidence. Do not assume this report's freshness persists.
3. If all current checks pass, register exactly that proposal with `register_accounting_boundary_proposal(proposal, rehearsal=receipt)`. Verify OPEN, `decision=None`, both actions, exact proposal fingerprint and V2 receipt fingerprint, audit binding, no unrelated queue changes, unchanged financial state/generation/watermark, and unchanged blocker. Any evidence drift requires stopping or a separately revalidated new proposal/rehearsal lineage; never replace an existing receipt binding.
4. Present `accounting_boundary_approval_confirmation(resolution_id)` and ask the one explicit YES/NO question bound to **both** exact fingerprints and linked actions. STOP. This implementation task supplies no operator YES.
5. Only a later explicit YES permits post-YES revalidation and `approve_accounting_boundary_review(resolution_id, operator=..., proposal_fingerprint=..., receipt_fingerprint=...)`, followed by one new MANUAL/PREVIEW_ONLY run under the original approval task. Approval uses the durable registered binding, not `/tmp` files. Do not run Test or Production in that approval phase.
