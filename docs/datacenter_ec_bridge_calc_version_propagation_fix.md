# Datacenter EC bridge calc-version propagation fix

## Root cause

The scheduler resolved `datacenter_ohlc_calc_version`, but both normal EC bridge
modes dropped it before calling the EC source-layer service. With V1 and V2 in
the same DC synthetic OHLC scope, the loader correctly refused to guess.

## Fixed paths

- Historical backfill and its catch-up/retry use pass the scheduler-selected
  value as `ohlc_calc_version`.
- Latest/refresh passes the same value.
- Both services and their CLIs pass it unchanged to the synthetic OHLC loader.
- Synthetic coverage and parity are scoped to the same value.
- Empty explicit values are rejected. Omitted values retain the loader's
  existing fail-closed behavior when multiple versions are present.

V1 remains an explicit supported selection; no latest-version fallback or
version inference was added.

## Verification

- Targeted EC bridge, backfill, refresh, loader, coverage, parity, and scheduler
  runner tests: `180 passed`.
- Scheduler config/version tests: `37 passed`.
- Changed Python files passed `py_compile`; `git diff --check` passed.
- Production config remained `DC_SWING_OHLC_V2` with taxonomy
  `DC_TAXONOMY_FULL_V2_1`.
- Current-scope refresh was invoked with explicit V2, watchlist reconciliation
  disabled, and replacement disabled. The planner refused the existing date as
  `BLOCKED_EXISTING_DATE_WITHOUT_REPLACE`; no backup or production write was
  made.
- DC V2 and EC V2 synthetic OHLC are current through `2026-10-02`, with 15,635
  rows across 295 dates each.
- Version-scoped synthetic parity for `2026-10-02`: 53 source rows, 53 target
  rows, zero mismatches, zero blocking mismatches.
- DC V1 and EC V1 fingerprints were unchanged after runtime verification.
- EC V2 duplicate keys: 0. Unexpected DC/EC calc versions: 0.
- `PRAGMA quick_check`: `ok`.

## Remaining limitation

The safe current-date refresh mode stops at its existing-date planner gate, so
the production loader was not re-run merely to prove propagation. Tests exercise
the complete scheduler-to-loader and audit call chain. Non-synthetic EC facts
(ticker, group signal, and group index) remain at `2026-09-25`; therefore a full
all-fact parity audit for `2026-10-02` is out of scope and expected to fail,
while the version-scoped synthetic OHLC parity relevant to this fix is clean.
