# Phase 13G.2.8 - Add Tickers per-ticker reporting

## Outcome

Phase 13G.2.8 succeeded. Add Tickers now carries one structured per-ticker
reporting payload from Preview through Test on copies and Production update.
The downloaded report contains a compact summary and detailed ticker sections.

## Reporting contract

Each ticker records identity, market/exchange, before-state, acquisition source,
network request/use, provider and ARQ coverage, Sector/Industry, active
`dc_ecosystem` memberships and roles, eligibility, stage-specific canonical and
V2 after-state, RP V2 and RV outcomes, and the final plain-language action.

The payload is included in the saved Preview plan and therefore covered by the
existing Preview fingerprint. Test and Production enrich that saved evidence
with the state read from the validated candidate or published databases.

## Source-of-truth rules

- Provider and canonical before-state come from Add Tickers Preview evidence.
- Coverage comes from the resolved provider rows. Explicit `fiscalperiod` is
  preferred when formatting quarters; calendar/report dates are only fallback.
- Sector/Industry comes from the `ticker_meta` classification resolved by Add
  Tickers. The report labels `ticker_meta` as its authority.
- Taxonomy membership is read directly and read-only from the active
  `analysis.db` `dc_ecosystem` taxonomy. All active roles and memberships are
  retained; no CSV is accepted.
- Score, Lifecycle, Valuation, RP V2, and RV after-state comes from the validated
  Test candidate or final Production analysis database.

## Before-state and acquisition

Before-state is classified as `New`, `Provider data already present`,
`Canonical identity already present`, `Already fully present`, or `Existing but
incomplete`. Provider, canonical, and pre-existing V2 facts remain separate in
the structured payload.

Acquisition is reported as existing local provider data, verified local archive,
network, or no usable fundamentals. Network requested and network result used
are separate booleans, so archive/local resolution is not confused with a
network fetch.

## Coverage and analysis

Coverage reports total provider rows, ARQ row count, and first/latest fiscal
quarters. Preview labels final V2 and RP state as `Not calculated during
Preview`. Test and Production report current Score, Lifecycle, Valuation,
total/ecosystem RP V2 rows with zero-result reasons, and RV status/eligibility.

## Report and UI summary

The report begins with a nine-column Ticker Summary and follows it with an
Identity, Before, Data acquisition, Classification, Taxonomy, V2 analysis, and
Final result section for each ticker. The Executive Summary adds ticker count,
new count, network count, and active taxonomy count. Duplicate `Completed in`
duration wording was removed; the report keeps one `Duration` row plus exact UTC
timestamps in the Technical Appendix.

## Acceptance evidence

The isolated end-to-end fixture exercises Preview, Test on copies, and guarded
Production simulation, and asserts stage-appropriate report content. Additional
fixtures cover new, provider-only, canonical-only, complete, archive, network,
not-found, taxonomy member/non-member/multiple-role, ready, limited, not-ready,
RP zero-result, and RV eligibility states.

A read-only real Preview was also run for `STM`, `TECK`, and `TEM` as
`20260919T100439Z_add_tickers_c8719229e2aa`. It reported all three as already
fully present, no network use, and active taxonomy membership for STM and TECK.
The operation made no database writes. No real Test or Production operation was
run for this reporting phase.

## Verification

- `pytest -q tests/test_fundamentals_admin_ticker_reporting.py tests/test_fundamentals_admin_batch_add_tickers.py tests/test_fundamentals_admin_ui.py`: 67 passed.
- `pytest -q tests/test_fundamentals_admin_ticker_reporting.py`: 5 passed.
- `pytest -q tests/test_fundamentals_admin_*.py`: 175 passed.
- Failed: 0. Skipped: 0.

## Safety and cleanup

Reporting uses read-only queries and existing operation evidence. Calculation
semantics, transaction ordering, locks, backups, rebuild, atomic replacement,
rollback, taxonomy, and `ticker_meta` are unchanged. Copy lanes are cleaned by
the existing workflow; only lightweight reports and test evidence are retained.
Production rollback backups were not touched.

## Remaining issues

No material reporting gap remains in the Phase 13G.2.8 scope. Historical reports
are intentionally not rewritten; enrichment applies to future runs.
