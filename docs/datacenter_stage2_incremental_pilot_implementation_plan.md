# Datacenter Stage 2 Incremental Pilot Implementation Plan

This is an implementation-planning document only. It does not modify runtime
code, tests, schemas, migrations, scheduler configuration, watermark behavior,
or EC loaders.

Evidence sources:

- `docs/current_datacenter_pipeline_dependency_map.md`
- `docs/datacenter_incremental_execution_and_ec_sync_contract.md`

## 1. Objective

Replace the daily full-range Stage 2 execution with a watermark-driven,
trading-day-based incremental execution using separate input warmup and output
materialization ranges, while conservatively rerunning required downstream
stages and keeping the transitional EC source layer visibly synchronized.

## 2. Scope

Included:

- Stage 2 planner integration.
- Current 220-valid-row input-history behavior.
- Explicit output-overlap policy.
- Actual materialized-date reporting.
- Conservative downstream chain:
  `Stage 3 -> Stage 7 -> Stage 8 -> Stage 9`.
- Multi-date transitional EC backfill bridge.
- Parity/coverage validation.
- Scheduler summary/status propagation.
- Tests and read-only production verification.

Excluded:

- Stage 1 incremental execution.
- Stage 4-6 incremental changes.
- Minimal downstream ranges.
- Full pipeline planner conversion.
- Changed-row hashes.
- Sparse affected-date sets.
- Permanent EC sync-debt schema.
- Future raw-data EC materialization architecture.

## 3. Current Code Touchpoints

`analysis/datacenter_indices/swing_pipeline_orchestrator.py`

- Likely responsibility: consume Stage 2 planner output, pass narrowed Stage 2
  dates to the Stage 2 CLI, and propagate the resulting materialized range to
  downstream Datacenter stages.
- Likely responsibility: keep Stage 6 outside the Stage 2 dirty chain.
- Likely responsibility: include structured materialization and EC bridge fields
  in the pipeline summary.

`analysis/datacenter_indices/pipeline_plan.py`

- Likely responsibility: define or host the Stage 2 planning model for
  `FULL | INCREMENTAL | SKIP`.
- Likely responsibility: use `dc_pipeline_watermark` as one input, not as a
  naive execution gate.
- Likely responsibility: calculate trading-day output overlap and input warmup
  ranges.

`analysis/datacenter_indices/swing_ticker_persistence.py`

- Confirmed responsibility: Stage 2 range execution and per-date
  `replace-date` writes.
- Confirmed behavior: 220-valid-price-row input history limit.
- Confirmed behavior: per-date commits in range execution.
- Likely responsibility: expose or preserve enough per-date summary information
  for attempted and successfully completed date reporting.

`analysis/datacenter_indices/swing_group_persistence.py`

- Confirmed responsibility: Stage 3 group swing base metrics.
- Confirmed responsibility: Stage 7 timing field updates.
- Confirmed responsibility: Stage 8 overheat field updates.
- Confirmed behavior: Stage 3 uses per-date commits in range execution.
- Confirmed behavior: Stage 7 and Stage 8 use one range transaction per stage.

`analysis/datacenter_indices/swing_ticker_persistence.py`

- Confirmed responsibility: Stage 9 ticker scanner field updates.
- Confirmed behavior: Stage 9 reads ticker rows in the requested range and
  same-date group timing state.
- Confirmed behavior: Stage 9 uses one range transaction for scanner updates.

`rawcandle/scheduler/runner.py`

- Likely responsibility: select the correct transitional EC bridge mode based
  on actual Datacenter materialized range.
- Confirmed behavior: current single-date EC refresh failure changes an
  otherwise successful scheduler result from `OK` to `OK_WITH_WARNINGS`.
- Likely responsibility: record multi-date bridge status and prevent silent
  clean `OK` after bridge failure.

Current EC refresh/backfill CLI entry points:

- `rawcandle/cli/run_ec_source_layer_refresh.py`
  - Confirmed responsibility: current single-date latest refresh path.
  - Confirmed behavior: returns non-zero when parity/coverage is unacceptable.
- `rawcandle/cli/run_ec_source_layer_backfill.py`
  - Confirmed responsibility: date-based historical backfill path.
  - Confirmed behavior: returns non-zero when parity/coverage is unacceptable.
  - Confirmed behavior: historical backfill intentionally skips
    `ec_pipeline_watermark` refresh.

Related tests:

- `REQUIRES_VERIFICATION`: exact existing test files to extend should be selected
  during implementation. Candidate areas include planner tests, Stage 2
  persistence tests, group persistence tests, scheduler runner tests, and EC
  source-layer refresh/backfill CLI tests.
- Tests must use fixtures, mocks, or temporary databases. They must not read the
  large real USA OHLCV dataset.

## 4. Proposed Phased Implementation

### Phase 1 - Planner Result Model

- Define Stage 2 plan inputs and structured outputs.
- Keep execution unchanged.
- Add unit tests for `FULL`, `INCREMENTAL`, `SKIP`, incompatible versions, forced
  full, and forced range.

Expected result: planner behavior can be tested without changing pipeline writes.

### Phase 2 - Trading-Day Range Resolution

- Resolve output dates from valid market dates.
- Resolve the current Stage 2 input history using the existing 220-valid-row
  preload behavior.
- Keep output overlap explicit and configurable through stage policy.
- Add weekend, holiday, and missing-ticker-history tests.

Expected result: planner emits separate input and output ranges using valid
trading/signal dates.

### Phase 3 - Stage 2 Execution Wiring

- Use planner output to narrow Stage 2 selected output dates.
- Preserve `replace-date`.
- Capture attempted and successfully completed per-date summaries.
- Do not advance watermark on partial or failed stage completion.
- Add regression tests proving the fixed `2025-08-01` start is no longer used
  when an incremental plan is valid.

Expected result: Stage 2 incremental execution works behind an opt-in path while
current full-range behavior can remain available.

### Phase 4 - Conservative Downstream Wiring

- Run Stage 3, Stage 7, Stage 8, and Stage 9 for the Stage 2 materialized range.
- Preserve each stage's current write and transaction semantics.
- Keep Stage 6 outside the pilot.
- Add dependency/range propagation tests.

Expected result: Stage 2 changes are propagated through the confirmed pilot
dirty chain without claiming minimal downstream ranges.

### Phase 5 - Structured Materialization Summary

- Add structured pipeline-run output containing:
  - planned input range
  - planned output range
  - attempted dates
  - successfully completed dates
  - actual materialized start/end when valid
  - partial/failed status
  - reason code
- Prefer a run/log/JSON artifact rather than a new database schema in the pilot.

Expected result: operators can see what was planned, attempted, committed, and
validated.

### Phase 6 - Transitional EC Bridge

- Single-date materialization: retain current EC latest refresh.
- Multi-date materialization: invoke existing EC historical backfill/date-based
  replace for the conservative affected range.
- Run existing coverage/parity checks.
- Record bridge mode, required range, load status, parity status,
  retry-required flag, and error.

Expected result: current EC source layer cannot become silently stale after a
multi-date Datacenter rewrite.

### Phase 7 - Scheduler Status Integration

- Ensure EC bridge failure cannot produce clean `OK`.
- Document the selected pilot policy:
  - preserve current `OK_WITH_WARNINGS`, or
  - elevate bridge failure to `FAILED`.
- Do not silently ignore multi-date backfill failure.

Expected result: scheduler summaries and status files expose EC bridge failure.

### Phase 8 - End-to-End Verification

- Unit and integration tests.
- Dry-run or test-database execution.
- Read-only real-DB planning verification.
- Controlled production run only after explicit approval.
- Validate DC/EC parity for affected dates.
- Confirm no unexpected Stage 1 or Stage 4-6 rebuild.

Expected result: the pilot can be activated with bounded blast radius and a clear
rollback path.

## 5. Planner Policy Decision Still Required

`DECISION-STAGE2-OVERLAP-001`

The Stage 2 output-overlap policy must be selected before Phase 3 write-range
wiring.

Options:

- Output only new valid dates.
- Small fixed overlap.
- Overlap tied to the longest unstable recent metric/state horizon.
- Overlap triggered only by explicit dirty/invalidation events.

The 220-row input warmup does not determine the output overlap. It defines the
current input-history baseline for calculation correctness. Output overlap is
about which already-materialized dates are rewritten.

Proposed conservative pilot default:

- Use a small fixed trading-day output overlap for normal new-date incremental
  runs.
- Use explicit dirty/invalidation start when known, if earlier than the fixed
  overlap start.
- Treat this as a proposal, not as confirmed current code behavior.

Decision points:

- Exact overlap trading-day count.
- Whether policy differs between normal new-date runs and explicit historical
  invalidation.
- Whether operator-forced range bypasses default overlap.

## 6. Partial Failure Strategy

Current transaction asymmetry:

- Stage 2: per-date commits in range execution.
- Stage 3: per-date commits in range execution.
- Stage 7: one transaction per stage range.
- Stage 8: one transaction per stage range.
- Stage 9: one transaction per stage range.

Implementation requirements:

- Stage watermark advances only after complete success.
- Structured summaries must identify partial completion where possible.
- Retries must safely use current replace semantics.
- Abrupt termination may require reprocessing the entire planned output range
  unless durable per-date completion metadata is introduced.

Pilot preference:

- Prefer safe reprocessing over a new durable database schema.
- On partial or uncertain completion, rerun the conservative planned output
  range with existing replace semantics.
- Do not infer a continuous completed range after abrupt termination unless a
  durable mechanism exists.

## 7. Test Matrix

- Missing Stage 2 watermark -> full.
- Compatible watermark with one new trading date -> incremental.
- Weekend between watermark end and target date.
- Holiday/non-signal date.
- Incompatible signal/taxonomy version.
- Forced full.
- Forced range.
- Stage 2 failure on first date.
- Stage 2 failure after one or more committed dates.
- Stage 3 failure after Stage 2 success.
- Stage 7 transactional failure.
- Stage 8 transactional failure.
- Stage 9 transactional failure.
- Single-date EC refresh success.
- Multi-date EC backfill success.
- EC backfill parity failure.
- Scheduler overall status not clean `OK` after EC bridge failure.
- Unchanged current behavior when incremental feature is disabled, if an opt-in
  rollout flag is proposed.

Test constraints:

- Do not read the large real USA OHLCV dataset in scheduler tests.
- Use fixtures, mocks, or temporary SQLite databases.
- Keep planner tests deterministic and independent of wall-clock time where
  possible.

## 8. Rollout and Rollback

Conservative rollout:

- Add opt-in Stage 2 incremental mode initially.
- Add planning-only/log-only mode before write execution.
- Compare planned incremental range against current full-range behavior.
- Keep temporary fallback to current full Stage 2 execution.
- Require no schema migration for the pilot.
- Provide an explicit rollback switch/configuration.
- Activate in production only after parity and range verification.

Rollback:

- Disable Stage 2 incremental mode.
- Return to current fixed-start Stage 2 execution.
- Use existing EC latest refresh/backfill tools for any affected-date repair.
- Preserve generated logs/summaries for audit.

This task does not modify scheduler configuration.

## 9. Acceptance Mapping

| Requirement | Phase | Expected Tests | Verification Evidence |
| --- | --- | --- | --- |
| `REQ-DC-PLAN-001` | Phase 1, Phase 3 | planner incremental tests, regression that fixed `2025-08-01` is not used when valid watermark exists | planner output and Stage 2 CLI args |
| `REQ-DC-RANGE-001` | Phase 1, Phase 2 | planner range model tests | separate input/output fields in structured plan |
| `REQ-DC-CALENDAR-001` | Phase 2 | weekend, holiday, non-signal-date tests | valid trading/signal date selection |
| `REQ-DC-MATERIALIZE-001` | Phase 3, Phase 5 | partial success/failure tests | attempted/completed dates and actual materialized range in summary |
| `REQ-DC-WATERMARK-001` | Phase 3 | failed Stage 2 and partial Stage 2 tests | watermark unchanged after failed stage |
| `REQ-DC-DOWNSTREAM-001` | Phase 4 | dependency/range propagation tests | Stage 3, 7, 8, 9 receive materialized output range |
| `REQ-EC-BRIDGE-001` | Phase 6 | multi-date EC backfill success test | backfill invoked for affected range |
| `REQ-EC-BRIDGE-002` | Phase 6 | coverage/parity success and failure tests | bridge status records load and audit outcome |
| `REQ-STATUS-001` | Phase 7 | scheduler EC bridge failure test | overall status is not clean `OK` |
| `REQ-ARCH-001` | Phase 6, documentation review | no schema/loader future-architecture coupling test or review check | bridge remains transitional and no DC-specific debt schema is added |

## 10. Explicit Stop Points

Codex or an implementer must stop for review:

- After planner-only phases.
- Before Stage 2 write-range wiring.
- Before scheduler invokes multi-date EC backfill.
- Before production activation.

No production run should be performed without explicit approval.

