# Fundamentals V4 Phase 13G.2.1 Authoritative Downstream Hardening

Date: 2026-09-15

Outcome: **OUTCOME C — MATERIAL ARCHITECTURE OR SAFETY DEFECT; PRODUCTION UNCHANGED**

Phase 13G.2.1 was intended to replace the limited Phase 13D downstream adapter in Batch Add Tickers with the repository's full authoritative copy-only Fundamentals V4 downstream chain, then run the ARM and ten-ticker acceptance sequence.

The phase did **not** complete Outcome A. The correct result is Outcome C because the current authoritative downstream runner is not a generic Add Tickers pipeline.

## Repository State Verified

Required baseline commits were present:

- `470072e` — Phase 13G.1 administration foundation
- `00d08d2` — Sharadar user-config fallback
- `b1cbaae` — Phase 13G.2 Batch Add Tickers foundation

The worktree was clean before this phase.

## Root Cause

The current complete downstream ordering exists in `rawcandle.fundamentals.phase13f4_2_production._apply_pipeline_for_paths`.

That function correctly sequences:

1. transition identity repair;
2. provider staging;
3. provider identity links;
4. canonical rebuild;
5. TTM rebuild;
6. structural contract;
7. valuation classification update;
8. operational-universe/dependency schema;
9. active package refresh;
10. Relative Position refresh;
11. manual Relative Valuation refresh;
12. dependency attach;
13. Snapshot smoke.

However, its source and identity adapters are Phase 13F ticker-transition specific. They depend on the fixed `TRANSITIONS` set and helpers such as `_apply_transition_identities`, `stage_provider_rows(source["rows_by_ticker"])`, `_valuation_classification_update` target lists and the Phase 13F archive reconciliation shape.

They are not safe to call for arbitrary Batch Add Tickers inputs such as `ARM` or:

`AG ALOY ARM ASML ASX BABA BHP BIDU BTDR CAMT`

Using that runner blindly would either process the wrong ticker set or create misleading acceptance evidence.

## Code Change

Phase 13G.2 Batch Add Tickers apply results now expose a structured limitation:

`downstream.authoritative_downstream.status = NOT_AVAILABLE_FOR_GENERIC_BATCH_ADD_TICKERS`

The message states that a generic provider-source and identity adapter is required before package/RP/RV/Snapshot can be claimed for arbitrary Add Tickers batches.

This is deliberately explicit so future tests can distinguish "known not implemented" from a silent success.

## AREB Regression Resolution

Previously failing test:

`tests/test_phase13f_historical_delisted.py::test_downstream_summary_keeps_cross_sectional_layers_explicitly_blocked`

Old expectation:

`ACTIVE_UNIVERSE_FILTER` must appear in `relative_valuation_status`.

Current implementation returned:

`CURRENT_RELATIVE_VALUATION_EXCLUDES_AREB`

Investigation found the current result is semantically correct. `downstream_areb_summary` returns the old active-universe-filter warning only if active current Relative Valuation rows still exist for AREB. Current production has zero active AREB Relative Valuation rows, so the correct date-aware status is that current Relative Valuation excludes AREB.

The test was updated narrowly to assert:

- `current_relative_valuation_rows_for_areb == 0`
- `relative_valuation_status == CURRENT_RELATIVE_VALUATION_EXCLUDES_AREB`

No production code was changed for AREB. Obsolete AREB current participation was not restored.

## Acceptance Not Run

The ARM and ten-ticker acceptance sequences were not run because the required generic authoritative adapter does not exist yet. Running the large copy-only sequence through the transition-specific Phase 13F runner would produce invalid evidence.

No result is claimed for ARM or any of:

`AG ALOY ARM ASML ASX BABA BHP BIDU BTDR CAMT`

## Required Next Implementation

To reach Outcome A, implement a generic Add Tickers authoritative adapter that:

1. acquires or locates provider metadata and fundamentals per accepted ticker;
2. supports local provider rows, verified archives and bounded Sharadar requests behind `--allow-network`;
3. stages all accepted provider rows into the provider copy;
4. persists stable provider identity, company/security identity, aliases, CIK and listing evidence;
5. applies date-aware eligibility and structural-break boundaries;
6. reconciles canonical and TTM once after all accepted staging;
7. invokes the existing package refresh once;
8. invokes Relative Position once;
9. invokes manual Relative Valuation once;
10. attaches dependencies once;
11. generates Snapshot smoke reports for accepted tickers;
12. proves repeat `NO_CHANGE` and independent replay determinism.

Only after that adapter exists should the ARM and ten-ticker acceptance run be executed.

## Tests

Focused tests run:

- `python3 -m pytest tests/test_phase13f_historical_delisted.py::test_downstream_summary_keeps_cross_sectional_layers_explicitly_blocked`
- `python3 -m pytest tests/test_fundamentals_admin_batch_add_tickers.py`

Targeted broader regressions from Phase 13G.2 were not rerun in full after this small change because the only production-code change was an explicit metadata field in the Phase 13G.2 result contract and the AREB change was a narrow test expectation update. The previous Phase 13G.2 targeted run had 124 passed and the single AREB expectation failure described above.

## Production Isolation

This phase made no production database writes, no Scheduler changes, no UI changes, no production report changes and no provider network requests.

The full ARM/ten-ticker copy-only acceptance was intentionally not run.

## Disk Hygiene

No Phase 13G.2.1 database copy lanes were created. No phase-owned temp cleanup was required.
