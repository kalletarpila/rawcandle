# Phase 13G.2.9 - Add Tickers reporting semantics

## Outcome

Phase 13G.2.9 refines the Phase 13G.2.8 reporting contract without changing
Add Tickers business logic or database behavior. Internal statuses remain
machine-readable while all user-facing surfaces use stage-appropriate terms.

## Summary and review semantics

Preview summaries reconcile requested tickers into ingestion statuses:

- `Eligible to add`
- `Already present`
- `Review required`
- `Rejected`

New versus already-present before-state is shown separately, so overlapping
concepts are explicit. Test summaries report tested outcomes, and Production
summaries report added, updated/rebuilt, and unchanged outcomes.

`REVIEW_REQUIRED` appears in the Executive Summary, Ticker Summary, Changes
Found, Warnings or Blockers, and a dedicated Items Requiring Review section.
Known reason codes are translated into plain language while the original codes
remain in structured run evidence. Item review is not presented as an
operation-level failure or blocker.

## State and action vocabulary

The before-state vocabulary remains `New`, `Provider data already present`,
`Canonical identity already present`, `Already fully present`, and `Existing
but incomplete`.

Preview actions distinguish `Eligible to add`, `Already present - complete`,
`Already present - V2 analysis incomplete`, `Review required`, and `Rejected`.
Test distinguishes new and existing ticker outcomes. Production distinguishes
`Added`, `Updated`, `Existing ticker - analysis rebuilt`, and `Already present -
no source change`, while retaining review/rejection states for excluded items.

## Coverage and identity

Known zero quarterly coverage is shown as `0 ARQ`, not `Not available`. When
provider rows exist but ARQ is zero, the detail explicitly explains that data
exists but no usable quarterly ARQ history was identified.

Preview canonical wording is state-aware: existing identities are `Present`,
eligible new identities `will be created if applied`, and unresolved identities
are `pending review`. Test labels newly created copy identities, and Production
distinguishes created from pre-existing identities.

## V2, taxonomy, and classification

Preview shows `Existing V2 analysis` for a complete existing ticker, `No
existing V2 analysis` for an incomplete existing ticker, and `Not calculated
during Preview` for a new ticker. No calculations were added to Preview.

The compact taxonomy column uses role names directly (`CORE`, `EXTENDED`,
`WATCH_ONLY`, or `No`). Missing Sector/Industry is shown as `Classification
unavailable`; detailed output retains separate Sector and Industry values.
Source-of-truth rules remain unchanged: classification comes from `ticker_meta`
and taxonomy from the active `analysis.db` `dc_ecosystem` domain.

## Acceptance evidence

The report fixture covers new eligible, zero-ARQ, review-required, fully
present, existing incomplete, taxonomy member, non-member, and multiple-role
states. It verifies Preview wording plus Test and Production identity/action
wording. Existing end-to-end fixtures continue to exercise Preview, Test on
copies, and guarded Production simulation. No real Production operation was
run for this reporting refinement.

## Safety

Ticker eligibility, provider/archive/network resolution, the 25-ticker limit,
identity creation, V2/RP/RV calculations, transaction ordering, locks, backups,
rollback, taxonomy, market data, and `ticker_meta` are unchanged. This phase
only changes structured reporting evidence and presentation derived from it.

## Verification

- `pytest -q tests/test_fundamentals_admin_ticker_reporting.py`: 7 passed.
- `pytest -q tests/test_fundamentals_admin_ticker_reporting.py tests/test_fundamentals_admin_batch_add_tickers.py tests/test_fundamentals_admin_production_transaction.py tests/test_fundamentals_admin_ui.py`: 93 passed.
- `pytest -q tests/test_fundamentals_admin_*.py`: 177 passed.
- Failed: 0. Skipped: 0.

## Remaining issues

No material reporting gap remains in the Phase 13G.2.9 scope. Historical
reports are intentionally left immutable.
