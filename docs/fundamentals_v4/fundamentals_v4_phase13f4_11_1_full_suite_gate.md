# Phase 13F.4.11.1 Full-Suite Completion Diagnosis

Status: `OUTCOME A - FULL ACTIVE SUITE COMPLETED CONCLUSIVELY; PRE-WRITE TEST GATE CLOSED`.

Phase 13F.4.11.1 remained strictly pre-write. It did not create production backups, did not activate a package or Relative Valuation snapshot and did not write production databases.

## Root Cause

The failing boundary was not an economic assertion failure, SQLite corruption, OOM kill or production-data mutation. The root cause was a combination of:

- `tests/test_phase13f_historical_delisted.py::test_copy_only_pilot_smoke_without_heavy_rebuild` still used full logical production inventories through `production_preflight()` even with `run_heavy=False`;
- the earlier suite command had no heartbeat/atomic exit-code wrapper, so the long quiet section near 66% could leave the Codex PTY without a conclusive pytest exit-code artifact.

Isolated evidence:

- before correction, the suspicious test eventually passed but took `723.26s (0:12:03)`;
- after correction, the same test passed in `149.24s (0:02:29)`;
- the full `tests/test_phase13f_historical_delisted.py` file passed: `9 passed in 296.97s (0:04:56)`;
- the collection-boundary slice passed: `60 passed in 300.57s (0:05:00)`.

No OOM kill was visible in cgroup memory events, and no core files were found. System evidence access was available enough to check `dmesg` and cgroup memory event counters.

## Corrections

Implemented corrections:

- added `rawcandle.testing.durable_pytest_runner`, a pytest wrapper that records metadata, log, heartbeat and atomic exit code;
- added a light read-only inventory mode for the Phase 13F historical-delisted smoke path when `run_heavy=False`;
- preserved the heavy default path for actual copy-only pilot evidence.

The smoke path still verifies production immutability using hashes, schema, row counts, quick checks, foreign-key checks and active identities, but it avoids full table-content fingerprints for the large production databases.

## Full Active Suite

Durable command:

`python3 -m rawcandle.testing.durable_pytest_runner --artifact-dir temp/fundamentals_v4_phase13f4_11_1_full_suite_gate/full_active_suite_after_fix --heartbeat-seconds 60 --timeout-seconds 14400 -- -q`

Result:

- exit code: `0`
- summary: `2961 passed, 14 deselected, 8 warnings in 795.83s (0:13:15)`
- active collected tests: `2961`
- retired Fundamentals V3 deselected tests: `14`
- reached `100%`: yes
- timed out: no
- remaining pytest/durable-runner process: none observed

Evidence:

- full log: `temp/fundamentals_v4_phase13f4_11_1_full_suite_gate/full_active_suite_after_fix/pytest.log`
- heartbeat: `temp/fundamentals_v4_phase13f4_11_1_full_suite_gate/full_active_suite_after_fix/heartbeat.jsonl`
- exit code: `temp/fundamentals_v4_phase13f4_11_1_full_suite_gate/full_active_suite_after_fix/exit_code`
- compact evidence: `temp/fundamentals_v4_phase13f4_11_1_full_suite_gate/phase13f4_11_1_evidence.json`

## Production Isolation

Production remained unchanged.

Post-run writable hashes:

- provider: `7957c44632ff98eda87b12014152eb26b9fd3d445c5d8d2510b7b0f9eca03e11`
- canonical: `554aaa3c8fc359b08ed0c9171f62e08e2cd59c3be2bfed1fa6ff09713275e736`
- analysis: `a46ab948a9b6b3d12078b7f09158ccde603d28ab649e6bd9015273aa3e54e8d2`

Read-only source hashes:

- market: `0079fe29cc55765fe387d980fc52f20f8c87c33b084fd9c86e4e08c656795dd4`
- taxonomy: `b88bdd6d885b5bf59781a3f048a521c771a7117eaba546c6b5ed7fd3af4958d0`

Active identities remained:

- package: `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- Relative Valuation snapshot: `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`

`PRAGMA quick_check` returned `ok` for provider, canonical, analysis, market and taxonomy.

## Cleanup

The Phase 13F.4.11.1 artifact root contains compact logs and JSON evidence. No phase-owned `.db`, `-wal`, `-shm` or `-journal` files remained under the artifact root. Final artifact root size was about `504K`; workspace free space was about `568G`.

## Next Step

The pre-write full-suite test gate is closed. This outcome authorizes preparation of a separately authorized Phase 13F.4.12 production activation only; it does not authorize production writes in Phase 13F.4.11.1.
