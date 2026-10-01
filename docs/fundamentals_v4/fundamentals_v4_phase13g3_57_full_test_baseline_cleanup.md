# Phase 13G.3.57: Full Test Baseline Cleanup

Date: 2026-10-01

## Scope And Safety

This phase audited only the failures from the fresh repository-wide baseline and their directly relevant contracts. No production code was changed. No production financial database, operational Review Queue, live workflow, scheduler state, watermark, backup, or runtime artifact was modified. The pre-existing `data/.fundamentals_admin_publication_journal.json` worktree change was left untouched.

## Starting Baseline

Fresh `pytest -q` result:

- 3250 passed
- 13 failed
- 7 setup errors
- 8 warnings
- Duration: 1096.18 seconds

All red groups reproduced independently.

## Failure Inventory

| Group | Initial red tests | Root cause | Fix type | Final result |
|---|---:|---|---|---|
| Add Tickers production parity | 1 failure | QVCG's fixture prices do not satisfy either filing or current-price fallback age, while the old assertion expected full RV | Test expectation | Passed |
| Remove Tickers production parity | 8 failures | Test forced `2026-09-23` for Test while Preview correctly bound sources to its actual run date; stale protection stopped the workflow and caused dependent assertions to cascade | Fixture | Passed |
| Ticker reporting | 4 failures | The helper predated acquisition-authority gating, so valid fixture rows were intentionally hidden as unestablished; one acquisition label also predated the current failure wording | Fixture and test expectation | Passed |
| Legacy company snapshot | 7 setup errors | LEG and BNC no longer have accepted TTM rows after fiscal-identity quarantine, so the shared legacy presentation fixture could not assemble those reports | Fixture | Passed |

### Exact Red Tests

Add Tickers, failure, individually reproducible YES:

- `tests/test_add_tickers_full_workflow_production_parity.py::test_real_full_workflow_publishes_three_reviewed_identity_patterns`

Remove Tickers, failures, individually reproducible YES:

- `test_remove_tickers_real_full_workflow_success_and_source_contract[AAA-False-None]`
- `test_remove_tickers_real_full_workflow_success_and_source_contract[BBB-True-21]`
- `test_remove_tickers_full_workflow_stale_test_or_source_blocks_publication[canonical]`
- `test_remove_tickers_full_workflow_stale_test_or_source_blocks_publication[market]`
- `test_remove_tickers_full_workflow_stale_test_or_source_blocks_publication[taxonomy]`
- `test_remove_tickers_full_workflow_preboundary_failure_cleans_everything`
- `test_remove_tickers_full_workflow_publication_failure_rolls_back_complete_old_generation`
- `test_remove_tickers_full_workflow_partial_crash_recovers_through_real_entrypoint`

Ticker reporting, failures, individually reproducible YES:

- `test_preview_contract_preserves_before_source_coverage_classification_and_taxonomy`
- `test_before_state_and_acquisition_categories_cover_new_local_canonical_and_complete`
- `test_preview_semantics_reconcile_mixed_states_and_explain_review`
- `test_zero_arq_expected_absence_is_not_reporting_integrity_error`

Legacy company snapshot, setup errors, module-reproducible YES:

- `test_phase11f_active_capex_report_uses_percentage_points`
- `test_phase9j_2_zero_flag_wording_preserves_readiness_scope`
- `test_phase9j_2_active_flags_remain_candidates_with_limited_scope`
- `test_phase9i_edge_reports_preserve_na_nm_stale_and_not_applicable`
- `test_phase9j_1_mixed_unit_table_labels_only_score_difference_as_points`
- `test_phase9j_main_report_does_not_render_diagnostic_reason_codes`
- `test_phase9j_explanations_keep_diagnostic_statuses_distinct`

## Repairs And Contract Basis

### Add Tickers

Previous expectation: QVCG RV was `VALUATION_FULL`.

Current contract and fixture result: the workflow publishes successfully and Score is full, but filing valuation is `VALUATION_NOT_READY / PRICE_FALLBACK_TOO_OLD` and current RV is `VALUATION_NOT_READY / CURRENT_PRICE_FALLBACK_TOO_OLD`. The test now asserts both exact states and reasons. This is stronger than asserting only one status and preserves the distinction between successful analysis and insufficiently recent prices.

### Remove Tickers

Previous fixture behavior: Test was given a hard-coded as-of date that diverged from Preview after the calendar advanced.

Current contract: Test defaults to the accepted Preview date and must reject genuinely changed source bindings. Removing the override restores same-boundary parity while all explicit canonical, market, and taxonomy drift tests continue to exercise stale rejection.

### Ticker Reporting

Previous fixture behavior: rows were supplied without acquisition authority and were nevertheless expected to produce coverage.

Current contract: coverage is reportable only after authoritative acquisition. The helper now supplies authority for successful local/archive/network sources and withholds it for required/unavailable acquisition. The network-unavailable label expectation now matches the authoritative `Provider acquisition failed` wording. Exact coverage and zero-ARQ assertions remain intact.

### Legacy Snapshot

Previous fixture behavior: LEG and BNC were assumed to have accepted TTM endpoints.

Current contract: quarantined fiscal identities have no accepted TTM rows and snapshot assembly correctly rejects them. HLX now exercises the exact stale-price presentation after deterministic removal of recent prices from the copied test-only market database. AIOT exercises the same one-not-ready/seven-clear diagnostic shape and `REQUIRED_INPUT_MISSING` explanation previously covered by BNC. No production database was changed.

No tests were removed.

## Focused Validation

- Add Tickers primary parity case: 1 passed
- Remove Tickers production-parity module: 9 passed
- Ticker reporting module: 13 passed
- Legacy company snapshot module: 33 passed

## Final Validation

Final repository-wide `pytest -q`:

- 3270 passed
- 0 failed
- 0 errors
- 8 warnings
- Duration: 1088.70 seconds

Compile/import validation: passed for all changed Python test modules.

`git diff --check`: passed.

Phase-owned large files remaining: none.
