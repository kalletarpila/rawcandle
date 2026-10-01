# Phase 13G.3.56: Fiscal-Revision Acceptance

Date: 2026-10-01

Design authorities: `fundamentals_v4_phase13g3_54_trug_fiscal_identity_locality_audit.md` and `fundamentals_v4_phase13g3_55_local_fiscal_revision_quarantine.md`

## Outcome

The Review Queue now exposes the dedicated `ACCEPT_FISCAL_IDENTITY_REVISION` action for complete, tamper-free `REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION` items whose ticker-locality was proven by Phase 13G.3.55. The action is separate from `ACCEPT_RETAINED_HISTORY` and uses the existing `RETRY_REEVALUATION` lifecycle.

Accepting a fiscal-identity revision does not publish data immediately. It authorizes exactly matching evidence for automatic re-evaluation in the next Refresh, after which normal Preview/Test/Production controls still apply.

## Eligibility And Binding

The action is eligible only for an unresolved ticker-local MRQ fiscal-revision item with complete ARQ/MRQ evidence, stable source keys, agreeing ARQ companion evidence, complete company/security/provider identity, a queue item ID, a valid queue-evidence fingerprint, and a published-state binding.

The approval binds the ticker, queue item ID, review type and reasons, exact source keys, event count and dimensions, old/current fiscal identities, old/current source fingerprints, financial-payload-change evidence, full ARQ companion proof and its source fingerprints, identity binding, locality proof, queue-evidence fingerprint, and published-state binding. The approval timestamp, originating review run, operator action, and optional operator evidence are retained in the audit trail.

Global blockers, source-window items, incomplete evidence, legacy rows without an authenticated queue fingerprint, and tampered evidence are ineligible. `CONFIRM_TRUE_SOURCE_REMOVAL` remains unimplemented and unchanged.

## Lifecycle And Revalidation

Acceptance changes only the queue row from `OPEN` to `RETRY_REEVALUATION`. It does not mutate provider, canonical, or analysis databases.

On the next Preview, Refresh re-fetches ARQ/MRQ history, reruns fiscal comparison and locality classification, reconstructs the complete approval binding, and requires an exact match. A match removes only that approved fiscal revision from review-blocking classification, includes the revised history in the normal safe change set, consumes the approval, and resolves the queue item. Test independently reconstructs and verifies the approval from the Preview artifact before candidate construction.

Any drift in source keys, event count, dimension, fiscal identity, source fingerprint, ARQ companion proof, identity, review classification, locality, queue evidence, or published state prevents consumption. A still-local item is upserted as `OPEN` with current evidence and an approval-invalidation audit event. If locality is no longer proven, the existing global fail-closed behavior applies.

## Publication Contract

After exact revalidation, provider MRQ history may change through the ordinary candidate and publication path. Canonical construction remains ARQ-authoritative; fiscal approval does not allow MRQ data to overwrite canonical financial history. Publication-date preservation, Preview/Test/Production binding, and full V2/package/relative-position/relative-valuation processing are unchanged.

For the TRUG-shaped fixture, exact approval was consumed in the next Preview, TRUG entered Test and Production candidates, provider history changed, canonical financial content remained unchanged, the analysis candidate reached `READY`, and the queue item became `RESOLVED`.

## UI

Eligible rows show an `Accept fiscal revision` action. Its confirmation summarizes ticker, event count, dimension, report period/source key, old and new fiscal identities, financial-payload change, ARQ companion result, and review reason. It explicitly states that Production is not modified immediately, the next Refresh re-fetches and revalidates evidence, normal Preview to Test to Production controls remain mandatory, and drift invalidates approval. Accepted rows display the existing pending re-evaluation state.

## Tests And Safety

Focused tests cover eligibility, exact/idempotent persistence, no financial writes at acceptance, audit preservation, tamper handling, exact-match consumption, material drift and queue reopening, UI evidence and confirmation, retained-history regression, and a TRUG-shaped isolated full workflow. The relevant Refresh review, quarantine, UI, copy, and production tests run against fixture/temp databases only.

The focused Refresh regression group passed: `264 passed in 75.26s`. The repository-wide `pytest -q` run completed with `3250 passed`, `13 failed`, and `7 errors`; the failures are outside this phase in existing add/remove-ticker production-parity, ticker-reporting, and legacy company-snapshot fixtures. Compile/import validation and `git diff --check` passed.

- Production financial databases changed: NO.
- Operational Review Queue changed: NO.
- Live workflows executed: NO.
- Scheduler/systemd state changed: NO.
- Watermark changed: NO.
- Backups deleted: NO.
