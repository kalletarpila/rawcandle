# Phase 13F.4.10 Identity And Dependency Fixed-Point Repair

Status: `OUTCOME A - IDENTITY AND DEPENDENCY FIXED POINT VERIFIED; READY FOR SEPARATELY AUTHORIZED PHASE 13F.4.11 PRODUCTION DEPLOYMENT`.

Phase 13F.4.10 stayed copy-only. It did not write production databases, did not activate a production package and did not make network requests. The run repaired the protected logical-content drift exposed by Phase 13F.4.9 and proved the full copy-only chain reaches a fixed point under the Phase 13F.4.9 logical-content guard.

## Root Causes And Corrections

The Phase 13F.4.9 failure was a real idempotency defect, not stale expectations or SQLite physical variation.

- Relative Position `NO_CHANGE` inserted a new `relative_position_refresh_audit` row and advanced `validated_through_date`. The corrected path now returns `audit_rows_inserted=0` and leaves the protected audit table unchanged when active content is identical.
- Ticker-transition identity replay reported apply semantics without proving rows changed. The transition identity apply path now counts changed rows and returns `NO_CHANGE` when replay has no logical write.
- Successor provider identity linking read production provider metadata even in copy lanes. The copy lane now supplies the provider copy path, so identity reconciliation is isolated to the rehearsal copy set.
- Dependency persistence used `INSERT OR REPLACE` for existing natural keys. SQLite deleted and reinserted those rows, rotating `dependency_id` while preserving natural economic content. The dependency writer now uses `ON CONFLICT DO UPDATE`, preserving protected row identity.

## Copy Rehearsals

First instrumented run:

`temp/fundamentals_v4_phase13f4_10_fixed_point/20260914T_PHASE13F4_10_FIXED_POINT`

Result: `OUTCOME B - ROOT CAUSE IDENTIFIED BUT FIXED POINT NOT YET ACHIEVED; PRODUCTION NOT AUTHORIZED`.

The only remaining protected drift was `analysis.fundamentals_result_dependency`: row count stayed `10`, but six rows were deleted and six inserted because the `dependency_id` primary keys rotated. That field-level finding justified the dependency persistence correction.

Fixed run:

`temp/fundamentals_v4_phase13f4_10_fixed_point/20260914T_PHASE13F4_10_FIXED_POINT_R2`

Result: `OUTCOME A - IDENTITY AND DEPENDENCY FIXED POINT VERIFIED; READY FOR SEPARATELY AUTHORIZED PHASE 13F.4.11 PRODUCTION DEPLOYMENT`.

Fixed-point gates:

- `primary_cycle_b_no_change`: `true`
- `primary_cycle_c_no_change`: `true`
- `primary_b_c_end_state_identical`: `true`
- `replay_cycle_b_no_change`: `true`
- `primary_cycle_c_protected_diffs`: `[]`
- production immutability: `true`

Protected diff evidence:

- `primary/cycle_b_protected_table_diffs.csv`: header only
- `primary/cycle_c_protected_table_diffs.csv`: header only
- `replay/cycle_b_protected_table_diffs.csv`: header only

The final copy-chain still reports the expected first-cycle writes: provider staging changes `401`, provider identity writes `9`, package logical changes `2396550`, Relative Valuation first refresh `ACTIVATED`, and package/RV second applies `NO_CHANGE`. In primary cycles B/C and replay cycle B, transition identities, provider identities, provider staging, package, Relative Position and Relative Valuation all report no logical changes. `dependencies_outcome` remains `APPLIED` because the dependency reconciler records an accepted apply step, but protected table diffs are empty and the end-state comparison is logically identical.

## Production Immutability

Production was unchanged. Post-run hashes remained at the Phase 13F.4.9 restored baseline:

- `data/fundamentals_provider.db`: `7957c44632ff98eda87b12014152eb26b9fd3d445c5d8d2510b7b0f9eca03e11`
- `data/fundamentals_v4.db`: `554aaa3c8fc359b08ed0c9171f62e08e2cd59c3be2bfed1fa6ff09713275e736`
- `data/fundamentals_analysis.db`: `a46ab948a9b6b3d12078b7f09158ccde603d28ab649e6bd9015273aa3e54e8d2`

`quick_check` returned `ok` for provider, canonical and analysis production databases. The only production inventory metadata drift reported by the guard was a content-identical taxonomy `-shm` timestamp change, which is nonblocking under the Phase 13F.4.9 logical-content comparator.

Copy cleanup removed rehearsal `.db`, `-wal`, `-shm` and `-journal` files from both run roots. The retained evidence is JSON/CSV telemetry only; each run root is about `611M`. Free workspace disk after the fixed run was about `703G`.

## Snapshot Smoke

Snapshot report smoke checks over the fixed run found no UI-facing leakage of `company_id`, `security_id`, `provider_identity` or `internal` identity fields in the generated snapshot report artifacts.

## Verification

Commands run:

- `python3 -m compileall rawcandle/fundamentals/phase13f4_10_fixed_point.py rawcandle/fundamentals/relative_position/persistence.py rawcandle/fundamentals/phase13f3_ticker_transition.py rawcandle/fundamentals/phase13f3_2_successor_recovery.py tests/test_fundamentals_v4_relative_position_persistence.py tests/test_phase13f3_ticker_transition.py`
- `pytest -q tests/test_fundamentals_v4_relative_position_persistence.py tests/test_phase13f3_ticker_transition.py tests/test_phase12d_operational_rebuild.py`
- `python3 -m compileall rawcandle/fundamentals/phase13b_foundation.py rawcandle/fundamentals/phase13f4_10_fixed_point.py tests/test_phase13b_foundation.py`
- `pytest -q tests/test_phase13b_foundation.py tests/test_fundamentals_v4_relative_position_persistence.py tests/test_phase13f3_ticker_transition.py tests/test_phase12d_operational_rebuild.py`
- `git diff --check`
- `pytest -q` was started and remained green through the visible Phase 13F.4/13F historical section at `66%`, but the tool PTY stopped returning a final pytest report after the pytest process was no longer visible in process listings. It is not counted as a completed passing full-suite run.
- `pytest -q tests/test_phase13f_historical_delisted.py` was then started separately and reached the visible eighth passing test in a nine-test file before the same PTY/session non-return occurred after the pytest process was no longer visible. It is not counted as a completed passing file run.

The full active suite must still pass before any later production activation phase is authorized.

## Next Authorization Boundary

This phase does not authorize production activation. It only establishes that the corrected copy-only identity and dependency chain has reached a protected logical fixed point. Production deployment remains a separate, explicitly authorized Phase 13F.4.11 action with fresh backups, preflight inventory, the Phase 13F.4.9 logical-content guard and the Phase 13F.4 runbook gates.
