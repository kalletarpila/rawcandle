# Phase 13G.3.14: Refresh Production Copy Sources

## Outcome

Refresh Production candidate construction now uses the same isolated full-V2
read-only source contract as Test on copies. No live Refresh Preview, Test,
Production update, or full workflow was run in this phase. The scheduler service
and timer remained `inactive/dead`.

ARQ/MRQ downstream overlay remains intentionally deferred.

## Root Cause

`run_full_v2_downstream()` requires copied `provider`, `canonical`, `market`, and
`taxonomy` inputs and rejects any source path that resolves to a Production path.
Test on copies supplied:

- a provider candidate;
- a canonical candidate;
- a SQLite online backup of `data/osakedata.db` for the `market` role;
- a SQLite online backup of `data/analysis.db` for the `taxonomy` role.

Production supplied provider and canonical candidates, but passed the live
market and taxonomy paths. The omission surfaced only at `ANALYSIS_CANDIDATE`
because provider replacement and canonical reconstruction do not invoke the
full-V2 source-isolation guard. The guard inspected `market` before `taxonomy`
and correctly raised `ADMIN_FULL_V2_COPY_SOURCE_REQUIRED:market`.

The full-V2 rebuild needs both read-only authorities: market data and
`ticker_meta` from `osakedata.db`, and the active `dc_ecosystem` taxonomy from
`analysis.db`. Production had copied neither. It now reuses the same shared
`prepare_full_v2_read_only_copies()` helper as Test on copies. The safety guard
was not changed or bypassed.

## Implementation

Changed files:

- `rawcandle/fundamentals/admin/refresh_copy_runtime.py`
- `rawcandle/fundamentals/admin/refresh_production.py`
- `rawcandle/fundamentals/admin/publication_journal.py`
- `tests/test_fundamentals_admin_refresh_copy_test.py`
- `tests/test_fundamentals_admin_refresh_production.py`
- this report

The shared helper creates run-scoped immutable SQLite snapshots only for the two
missing read-only roles, records lightweight path/size/mtime/quick-check evidence,
and marks them for cleanup. Provider and canonical continue to use their existing
candidates; no redundant copies were added. Storage preflight now accounts for
the large market and taxonomy snapshots on the actual temp and backup filesystems.

Terminal success and terminal pre-publication failure remove the complete
run-owned lane. A nonterminal journal retains its lane for recovery. Terminal
recovery removes the three candidate paths and any remaining run-owned read-only
source copies.

## Reporting

Pre-publication failures now report the publication boundary, zero Production
writes, unchanged Production generation, unchanged published state/watermark,
and a separately labelled proposed watermark. Provider and canonical effects are
labelled as candidate effects, published replacement counts remain zero, and
ticker actions state that a candidate was prepared but not published. A ticker
that did not reach that stage is labelled accordingly. Successful reports retain
explicit published semantics.

The historical failed run report is preserved as audit evidence and was not
rewritten. New reports use the corrected state-aware renderer.

## Live Verification

The repository started at `38d463ed7901b36e1f50c9d81feae92603a1bff8` with
only the pre-existing untracked terminal BNC journal. Direct verification after
implementation showed:

| Role | SHA-256 | Size |
| --- | --- | ---: |
| provider | `1547699f4eb337ff1e75466d980c6e47adee77772d36c9f25f9596e24c9e696e` | 958,828,544 |
| canonical | `5bfdddb0720f66fefc6c2582f8e281ad88e2003aaab8986603330e51f6c13d38` | 656,252,928 |
| analysis | `e53fe32f793b44338236de2255d0961fd7849ac60f1314e32a9e57aa3d6220e4` | 904,691,712 |

These match the pre-change stop-gate hashes. The provider still has no
`sharadar_refresh_state` table, so the published state remains
`BOOTSTRAP_BASELINE` with no published watermark. The journal is the terminal
`COMPLETED` BNC-removal journal, not a nonterminal Refresh journal. No partial
70-ticker Refresh exists.

## Failed-Run Cleanup

Audited run:
`20260920T152851Z_refresh_fundamentals_0e0c9a7e2477_production_c7a26568`.

| Path | Size at audit | Reason | Removed now |
| --- | ---: | --- | --- |
| `temp/fundamentals_admin_phase13g1/<run-id>` | absent | obsolete pre-publication candidate/source lane | no; already cleaned by the failed invocation |
| `backups/fundamentals_admin_production/<run-id>` | absent | failure occurred before backup creation | no; never created |

No run-owned DB, WAL, SHM, temp, or backup file remained. Bytes freed during this
audit: `0`; remaining phase-owned large files: `0`. Lightweight JSON and Markdown
run evidence remains under `fundamental_reports/admin_runs/`.

## Validation

- Focused source-binding, copy-Test, Production, reporting, cleanup, publication,
  rollback, and recovery suite: `76 passed`.
- Broader Refresh Preview/Test/Production/full-workflow/full-V2/Admin UI suite:
  `159 passed`.
- `py_compile` passed for changed Python modules and tests.

Fixture-sized databases were used. Full V2/RP/RV analytical logic, ARQ-based
canonical semantics, taxonomy semantics, publication order, rollback, and
recovery authority are unchanged.

## Remaining Limitations

This phase does not provide reader-atomic multi-file activation and does not add
ARQ/MRQ overlay behavior. The next operational chain must begin with a fresh
Preview because runtime code changed; the previous Preview/Test binding must not
be reused.
