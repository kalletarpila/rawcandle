# Fundamentals V4 Phase 13G.2 Batch Add Tickers CLI

Date: 2026-09-15

Outcome: **OUTCOME B — BATCH ADD TICKERS COPY-ONLY FOUNDATION READY; AUTHORITATIVE FULL DOWNSTREAM GAP REMAINS**

Phase 13G.2 adds a reusable Batch Add Tickers service and CLI over the Phase 13G.1 durable administration foundation. It remains copy-only and does not authorize production writes.

## Implemented

- Batch ticker parsing, normalization, deduplication and deterministic ordering.
- Durable preview runs under `fundamental_reports/admin_runs/`.
- Copy-lane creation under `temp/fundamentals_admin_phase13g1/` by SQLite online backup.
- Phase 13D preview reuse for per-ticker local provider, market, canonical and taxonomy evidence.
- Immutable Phase 13G.2 preview fingerprints and saved Phase 13D payloads.
- Copy-only apply from an immutable preview payload with stale-preview rejection.
- Confirmed apply gate with `--apply`, `--confirm-apply`, `--preview-payload` and `--preview-fingerprint`.
- Durable JSON, Markdown, CSV, heartbeat, status, exit code and manifest artifacts.
- Copy-lane rollback after injected post-boundary failure.
- Read-only CLI:

`python3 -m rawcandle.cli.run_fundamentals_admin_add_tickers`

## Deliberate Gap

The service currently adapts the existing Phase 13D copy-only backend. That backend proves identity/canonical copy mutation, operational-universe dependency attachment and idempotent second apply, but it does **not** yet run the complete generic authoritative downstream chain required by the Phase 13G.2 master prompt:

- Operating-Income V2 package refresh;
- full-universe Relative Position refresh;
- manual full-universe Relative Valuation refresh;
- Snapshot smoke for all accepted batch members.

For that reason Outcome A is not claimed. The implementation records this explicitly in apply results as:

- `package = GAP_NOT_AUTHORITATIVELY_REFRESHED_BY_PHASE13D_ADAPTER`
- `relative_position = GAP_NOT_AUTHORITATIVELY_REFRESHED_BY_PHASE13D_ADAPTER`

## CLI Shape

Preview is the default:

```bash
python3 -m rawcandle.cli.run_fundamentals_admin_add_tickers ARM
```

Copy-only apply requires a saved preview payload:

```bash
python3 -m rawcandle.cli.run_fundamentals_admin_add_tickers \
  --apply \
  --confirm-apply \
  --preview-payload fundamental_reports/admin_runs/<run>/phase13d_preview_payload.json \
  --preview-fingerprint <fingerprint>
```

The CLI also supports:

- space/comma/newline ticker inputs;
- `--input-file`;
- explicit database paths for isolated fixtures;
- `--allow-network` as recorded metadata only in this phase;
- `--run-root` and `--temp-root` for tests and rehearsals;
- `--keep-copies` for debugging copy-only failure evidence.

No provider network request is implemented or performed in this phase.

## Focused Test Evidence

`python3 -m pytest tests/test_fundamentals_admin_batch_add_tickers.py`

Result: **9 passed**

Coverage includes:

- parsing and normalization;
- duplicate handling;
- mixed accepted/rejected/already-present preview;
- preview fingerprint stability;
- durable artifacts and run-history reading;
- idempotent copy-only apply;
- stale-preview rejection before write boundary;
- post-boundary failure rollback;
- network flag metadata;
- production path refusal;
- CLI preview smoke.

## Targeted Regressions

Command:

`python3 -m pytest tests/test_fundamentals_admin_foundation.py tests/test_phase13d_backend.py tests/test_phase13f_historical_delisted.py tests/test_structural_break_contract.py tests/test_fundamentals_v4_operating_income_v2_phase10c.py tests/test_fundamentals_v4_relative_position_production.py tests/test_fundamentals_v4_relative_valuation_production.py tests/test_fundamentals_snapshot_ui.py tests/test_production_database_isolation.py tests/test_config_env.py`

Result: **124 passed, 1 failed**

The failure was:

`tests/test_phase13f_historical_delisted.py::test_downstream_summary_keeps_cross_sectional_layers_explicitly_blocked`

Observed assertion:

`ACTIVE_UNIVERSE_FILTER` was expected inside `relative_valuation_status`, but the current value was `CURRENT_RELATIVE_VALUATION_EXCLUDES_AREB`.

Phase 13G.2 did not modify `phase13f_historical_delisted` or the underlying Relative Valuation exclusion status logic. This is recorded as a pre-existing or adjacent expectation drift to resolve before claiming production readiness.

Compile check:

`python3 -m compileall rawcandle/fundamentals/admin rawcandle/cli/run_fundamentals_admin_add_tickers.py`

Result: passed.

## Production Isolation

Read-only production checks were run before and after.

All five production databases reported:

- `quick_check=ok`
- zero foreign-key errors
- unchanged size and mtime

Active package pointer remained:

`f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`

Active Relative Valuation snapshot remained:

`76c2974108b2c5085b7dfa102acd4bb04eea36a5267bbdb1930a2bc7dc8cb35e`

No production database, Scheduler state, UI code, active report or provider source was modified.

## Disk Hygiene

Free space before: 599G.

Regression tests temporarily consumed about 8.1G under `/tmp/pytest-of-kalle/pytest-133`. That directory was removed after verification. Final free space returned to 599G.

No Phase 13G.2 copy lane remains under repository `temp/`.

Older large pytest directories under `/tmp/pytest-of-kalle/pytest-104`, `pytest-105` and `pytest-107` were not removed because they predate this phase and are not Phase 13G.2-owned artifacts.

## Ten-Ticker Acceptance Status

The prompt-requested real copy-only acceptance sequence for:

`AG ALOY ARM ASML ASX BABA BHP BIDU BTDR CAMT`

was **not run to completion** in this phase.

Reason: the currently available reusable adapter does not yet execute the complete authoritative package/RP/RV/Snapshot chain for a generic accepted batch. Running the large production-shaped acceptance would therefore create misleading evidence. The exact ticker sequence remains the required acceptance set for the next hardening pass.

No result is claimed for ARM or the ten-ticker batch in this commit.

## Phase 13G.3 / Next-Hardening Handoff

Before Phase 13G.2 can be promoted from Outcome B to Outcome A, add an operation-specific downstream adapter that runs, on copies:

1. provider staging for every accepted ticker;
2. canonical and TTM rebuild across the whole accepted batch;
3. Operating-Income V2 package refresh exactly once;
4. Relative Position exactly once;
5. manual full-universe Relative Valuation exactly once;
6. dependency attachment and compatibility verification;
7. Snapshot smoke for accepted tickers;
8. independent replay lane comparison;
9. exact ten-ticker acceptance sequence.

Also resolve or explicitly rebaseline the current `test_phase13f_historical_delisted` expectation drift before using Phase 13G.2 as a production readiness gate.
