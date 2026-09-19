# Phase 13G.2.11 - Add Tickers Full Workflow and Retry Semantics

## Scope and outcome

Phase 13G.2.11 adds reporting semantics and orchestration around the existing Add Tickers Preview, Test on copies, and Production update implementations. It does not add an alternative calculation path. Production remains a full V2 + RP V2 + RV rebuild followed by the existing validation, backup, lock, atomic publication, fsync, postflight, and rollback contracts.

No real Production Add Tickers operation was used to develop or test this phase.

## Zero-ARQ semantics

The after-state reporter now resolves the candidate/final canonical company and queries the actual candidate/final analysis database first. A real Score, Lifecycle, or Valuation result always wins over source-readiness inference.

Only when all three result families are absent and the saved authoritative acquisition evidence says both:

- provider row count is greater than zero; and
- usable quarterly ARQ count is exactly zero;

the reporter emits:

`analysis_availability = NO_USABLE_QUARTERLY_HISTORY`

with `integrity_status = EXPECTED_NO_ANALYSIS`. This is an analytical limitation, not an operation failure or reporting-integrity error. The ticker may still have final action `Added`, while its report says that V2 analysis is unavailable because no usable quarterly history exists.

The compact summary uses `No usable quarterly history`. The detailed report uses `V2 analysis: Not available - no usable quarterly ARQ history`. Analysis Outcome counts these cases separately and does not also count their placeholder model states as contradictory readiness outcomes.

## Reporting-integrity boundary

`REPORTING_INTEGRITY_ERROR` remains strict for:

- missing or ambiguous after-state canonical identity;
- unreadable analysis database or internal query error;
- resolved candidate identity with no Score/Lifecycle/Valuation result and no positively known zero-ARQ explanation.

The Test report always places a genuine integrity error in Warnings or Blockers. It cannot report a nonzero integrity count and also claim that no warnings or blockers exist. Expected zero-ARQ cases appear under Analytical Limitations instead of prominent warnings.

Representative semantics:

| State | Report treatment | Automatic workflow |
| --- | --- | --- |
| Known zero usable ARQ, no model rows | Analytical limitation | Continue if ordinary guards allow |
| Score LIMITED/NOT_READY | Normal model outcome | Continue if ordinary guards allow |
| Valuation NOT_APPLICABLE | Normal model outcome | Continue if ordinary guards allow |
| RV not eligible / RP peer group small | Normal model outcome | Continue if ordinary guards allow |
| Genuine reporting-integrity error | Prominent warning | Stop after Test |
| Review Required | Existing item/stage authorization rules | No new business decision |

Manual Production availability after a successful Test continues to follow the backend transaction contract. The automatic workflow is deliberately more conservative and stops on genuine reporting-integrity errors.

## Git worktree behavior

The old `PHASE13G2_CLEAN_GIT_WORKTREE_REQUIRED` rejection is removed from the shared Administration production path. Production records, where Git is available:

- full and short HEAD;
- branch;
- dirty true/false;
- a bounded list of changed tracked paths.

A dirty worktree adds the informational warning `Git worktree contains uncommitted changes.` It does not require separate confirmation and does not block Production. Full workflow reports use `Warning: Production ran with uncommitted Git worktree changes.`

No database safety guard was demoted. Preview/Test binding, requested input, source fingerprints, active taxonomy, production and scheduler locks, storage gate, verified backups, full B1 validation, source rechecks, same-filesystem atomic replacement, fsync, postflight, and rollback remain hard requirements.

## Production retry authorization

A failed Production result now contains structured `retry_authorization`.

Direct retry is available only when:

- the write boundary was not crossed;
- Preview validation completed;
- matching Test evidence was validated;
- the exception did not establish stale or mismatched evidence.

Temporary lock contention and similar non-mutating preflight failures preserve Preview/Test. A direct retry reruns every Production preflight; it does not cache a passed preflight.

Authorization is invalidated when validation detects stale Preview, input/fingerprint mismatch, missing or corrupt Test evidence, source/taxonomy change, or another explicit binding failure. The UI then clears stale authorization and requires the appropriate earlier stage.

Preflight reports state in the main report that Production made no database changes, give a plain-language reason, and say whether direct retry remains available. The technical exception remains in the appendix.

## Full-workflow architecture

`rawcandle.fundamentals.admin.full_workflow` is a thin orchestration layer. Through `FundamentalsAdminUIService` it calls the same existing stage implementations used by the individual buttons:

1. Add Tickers Preview;
2. Add Tickers Test on copies;
3. Add Tickers Production update.

It does not duplicate source resolution, identity mutation, TTM construction, structural calculation, full V2 rebuild, RP V2, RV, candidate validation, publication, or rollback logic.

Each child stage keeps its own run ID, `result.json`, progress evidence, technical artifacts, and `operation_report.md`. The parent workflow writes:

- `workflow_result.json`;
- `workflow_report.md`;
- current `progress_status.json`;
- bounded stage transition/progress events and heartbeat;
- an artifact manifest.

The workflow result persists normalized requested inputs, current stage, child run IDs, status, start/completion times, final outcome, stop reason, retry availability, warnings, and report references. Run history shows the Full workflow entry without hiding child runs. Both normal child reports and the workflow report are downloadable through the guarded report route.

## Workflow stop and failure behavior

The orchestrator never loops automatically. It stops before the next stage when:

- a child backend stage fails;
- the child result does not authorize the next stage;
- Test reports a genuine reporting-integrity error;
- Production preflight or transaction fails;
- an existing backend guard rejects input, source state, binding, or concurrency.

Completed earlier child reports remain available. A Test failure preserves the successful Preview for a manual Test retry. A retryable pre-write Production failure preserves Preview and Test for direct manual Production retry. A stale failure does not.

## UI state machine

| UI state | Preview | Test on copies | Production update | Run full workflow |
| --- | --- | --- | --- | --- |
| Valid fresh input | Enabled | Disabled | Disabled | Enabled |
| Manual Preview running | Disabled | Disabled | Disabled | Disabled |
| Manual Preview complete | Enabled | Enabled | Disabled | Disabled |
| Manual Test complete | Enabled | Disabled/completed | Enabled | Disabled |
| Full workflow running | Disabled | Disabled | Disabled | Disabled |
| Retryable Production preflight failure | Enabled | Disabled/completed | Enabled | Disabled |
| Full workflow Test failure | Enabled | Enabled | Disabled | Disabled |
| Full workflow complete | Depends on new input | Disabled | Disabled | Depends on new input |

`Run full workflow` always starts a fresh chain for the visible ticker input. It is disabled once a manual chain has started, so it never guesses whether to resume or replace manual evidence. A successful Production/full workflow clears the completed ticker batch. Input mutation invalidates old authorization through the existing material preview signature and backend validation.

Workflow progress is shown as Preview, Test on copies, and Production update while child progress callbacks and child durable logs remain intact.

## Concurrency

All UI service stages and full workflow use the same nonblocking filesystem operation lock. A workflow holds it across all three child stages, so another UI service Preview, Test, Production, or workflow cannot overlap it. The existing production/scheduler kernel locks remain independently authoritative for real database writes.

## Test coverage

Focused fixtures cover:

- expected zero-ARQ absence and actual-result precedence;
- genuine missing-result integrity failure;
- separate Analysis Outcome counts and consistent warnings;
- dirty Git warning without Git-only failure;
- retryable pre-write failure followed by direct retry;
- stale evidence invalidation;
- full workflow happy path and distinct child reports;
- Test failure, integrity stop, zero-ARQ continuation, Production preflight stop, and dirty Git completion;
- workflow history/report downloads and shared-lock exclusion;
- exact UI button states, batch reset, manual Test retry, and direct Production retry.

All workflow tests use callbacks, temporary databases, isolated run roots, or transaction rehearsals. They do not write production databases, taxonomy, or `ticker_meta`.

Executed verification:

| Command | Passed | Skipped | Failed |
| --- | ---: | ---: | ---: |
| `pytest -q tests/test_fundamentals_admin_ticker_reporting.py tests/test_fundamentals_admin_production_transaction.py tests/test_fundamentals_admin_full_workflow.py tests/test_fundamentals_admin_ui.py` | 82 | 0 | 0 |
| `pytest -q tests/test_fundamentals_admin_*.py` | 194 | 0 | 0 |
| `pytest -q tests/test_fundamentals_v4_full_rebuild.py tests/test_fundamentals_v4_operating_income_v2.py tests/test_fundamentals_v4_operating_income_v2_current_sources.py tests/test_fundamentals_v4_operating_income_v2_persistence.py tests/test_fundamentals_v4_relative_valuation_engine.py tests/test_fundamentals_v4_relative_valuation_persistence.py tests/test_fundamentals_v4_relative_valuation_source.py tests/test_phase13f1_reconciliation.py tests/test_phase13f2_date_aware_policy.py tests/test_phase13f3_4_structural_integration.py` | 107 | 0 | 0 |
| `python3 -m py_compile` for every touched Python module and test | completed | 0 | 0 |

`git diff --check` also completed without findings.

## Production safety evidence

No production stage was invoked. Final file size and nanosecond-mtime checks for `fundamentals_provider.db`, `fundamentals_v4.db`, `fundamentals_analysis.db`, `osakedata.db`, and `analysis.db` exactly matched the values recorded before this phase. No taxonomy or `ticker_meta` write occurred. Tests created only temporary fixture databases outside production paths; no phase-owned rehearsal database remains under the repository `temp/` tree.
