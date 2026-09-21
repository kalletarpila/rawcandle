# Phase 13G.3.20A - Add Tickers reviewed identity Preview

## Scope and finding

The historical Add Tickers Preview `20260921T161310Z_add_tickers_da1bdaccf33d`
correctly classified KRSA, PSQL, and QVCG as eligible, but its operator report
used generic new-identity wording. The historical artifact is retained unchanged
as evidence of that gap.

The defect was reporting-only. The runtime trace is:

`Add Tickers request -> resolve_ticker_identity -> approved registry validation -> GenericBatchItemPlan.identity_resolution -> mutation -> _apply_identities`

`build_generic_batch_plan()` already retained the complete `APPROVED_VALID`
resolution and `_apply_identities()` already consumed its authorized mutation
plan. The loss occurred in `build_preview_reporting()`, which did not carry
`identity_resolution` into the structured operator result. Markdown and the UI
summary therefore had no reviewed-plan evidence to render.

## Structured result and presentation

For an `APPROVED_REVIEW` resolution, Add Tickers Preview now carries the actual
producer result, including authority, review status, readiness, approval
fingerprint, current-state validation, continuity decisions, exchange authority,
reason codes, automatic-mutation permission, the complete mutation plan, and
its exact canonical consequences. Markdown derives its reviewed-identity
section from this structured result; it does not query a database or reparse the
review registry. The existing UI summary receives a concise readiness, action,
state-validation, and fingerprint-prefix line through the shared operation
summary mechanism.

Ordinary deterministic Add Tickers cases retain their existing generic report
wording.

## Candidate semantics proved

Fixture-sized production-shaped coverage passes the real committed approved
records through `build_generic_batch_plan()` and `_apply_identities()`:

- KRSA reuses company 627, leaves security 628 and CYCN unchanged, creates a
  distinct successor security, and attaches only KRSA to that security.
- PSQL creates a new company and security with CIK 0002119292. BBCQ company,
  security, and aliases are not reused or copied.
- QVCG creates a successor company and a new security with CIK 0001254699.
  QVCAQ and QVCBQ remain attached only to their prior historical security.

The runtime contains no ticker-specific mutation branch. The generic approved
plan operations drive all three outcomes. Existing approval-binding tests remain
fail closed for mismatched fingerprints, stale provider or canonical state,
conflicting provider identity, proposed/rejected records, and any readiness
other than `APPROVED_VALID`.

## Preview binding

The Add Tickers Preview contract is now
`PHASE13G2_BATCH_ADD_TICKERS_COPY_ONLY_V5_REVIEWED_IDENTITY_REPORTING`.
Consequently, the old V4 live Preview cannot authorize Test on copies. A fresh
Preview is required after this change.

## Safety and acceptance

No live Preview, Test on copies, Production update, Full Workflow, scheduler
job, or production database mutation was performed in this phase. Verification
used fixture databases only. The committed KRSA, PSQL, and QVCG interpretations,
approval statuses, and fingerprints were not changed; DRK remains out of scope.

Add Tickers Preview must expose the exact approved identity mutation plan that
Test on copies will execute.

Eligibility based on financial/source data does not substitute for reviewed
identity authority.
