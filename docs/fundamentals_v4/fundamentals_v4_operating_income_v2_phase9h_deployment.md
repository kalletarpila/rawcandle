# Operating-Income V2 Phase 9H Production Deployment

## Outcome

Phase 9H deployed and activated the corrected Diagnostic Flags V2 package on
2026-09-07. The only written production database was
`/home/kalle/projects/rawcandle/data/fundamentals_analysis.db`. Canonical,
provider, market and taxonomy databases were read-only and content-identical;
no provider update or canonical/TTM rebuild ran. Existing files under
`fundamental_reports/` remained byte-identical.

The code gates were committed as `a2dd4ab92176fc340d4249ad6154f3fa1af5d022`
and the idempotent activation update as
`092ca4a`. Archived-package validation was corrected in `0059b14`. The
deployment-record commit is the commit containing this document.

## Identity

| Identity | Before | Active after |
|---|---|---|
| Package | `cf4ce8134c362399ea94667e4659e27a32b1e8b9de199eaaba32c91b450a51bc` | `a36d6903c3d640da5e9bd7034faee700b7b064e74ea871880c1bfa2348f4964d` |
| Diagnostic model | `d5434e139b68ee8af44dffce34cb9225538f0badb61d5d1074fb976a4de3185d` | `7f6291bf04e69cf22944ea3f81e07b284ccffd8edbd0edea4190ddc79050b031` |
| Snapshot economic | `7bfa88aa64f3897ea610894a1b7a3613abfc7881d9b9ea8e26912ef0426e7ee8` | `1b4963c3b968008dd753d86c9a95c5f21737956113ea5c70f481b2ee96757f64` |
| Snapshot presentation | `bc4b4a3b355063697f1fe3182a105342d804a59bb41a86ec40ef6fe4364abee2` | unchanged |

Corrected Diagnostic source/result/physical/layout fingerprints are
`ac370371...`, `f51858c0...`, `124ca6c1...`, and `75b83b2c...`. The coherent
full-package economic and physical fingerprints are `8bdbd6a2...` and
`1271b8ed...`. Score, Lifecycle, Valuation, Delta and Relative Position model
fingerprints did not change.

Both coherent manifests are retained in
`operating_income_v2_package_manifest_history`. A rollback rehearsal on the
post-deployment backup successfully activated `cf4ce813...`, resolved Diagnostic
model `d5434e...`, and read all seven old NVDA evaluations.

## Cohorts

The calculation as-of date is 2026-09-06 and freshness is controlled by
`ttm_source_available_date`, which must be non-future and at most 180 calendar
days old. Complete history contains 2,451 companies. Of these, 2,448 have a
latest endpoint knowable by the as-of date and 2,431 are current-fresh. The
earlier 2,451 “current-fresh” label was a reporting error; economic history was
correct and was not filtered or changed to reproduce that label.

Current-fresh prevalence:

| Flag | Flagged | Clear | Not ready | Not applicable |
|---|---:|---:|---:|---:|
| Abrupt Fundamental Shift | 245 | 1,853 | 9 | 324 |
| Earnings-Cash Divergence | 239 | 1,859 | 9 | 324 |
| Capex Intensity Shift | 74 | 2,024 | 9 | 324 |
| Net Debt Shift | 169 | 1,929 | 9 | 324 |
| Valuation Yield Outlier | 28 | 2,218 | 46 | 139 |
| Recent Margin Deceleration | 12 | 2,051 | 229 | 139 |
| Working Capital Shift | 50 | 2,241 | 1 | 139 |

There are 430 current-fresh companies with at least one active flag. The full
history Working Capital distribution is 1,265 flagged, 43,861 clear, 2,556 not
ready and 2,903 not applicable.

## Backup and storage

The verified pre-write online backup is
`/home/kalle/projects/rawcandle/backups/fundamentals_analysis.phase9e.20260907T102623Z.db`:

- size 952,270,848 bytes
- SHA-256 `10d714b70ecccf4ac938947e53274838bacf40c8f7e338dc8edfded7f8509f71`
- `quick_check=ok`, zero foreign-key violations
- 101,170 Diagnostic endpoints and 708,190 evaluations across V1 and pre-9G V2
- independently openable with no WAL dependency

The post-deployment/no-op boundary backup is
`backups/fundamentals_analysis.phase9e.20260907T103432Z.db`, size 1,043,939,328
bytes, SHA-256 `b93112be06e2a415b8eaf27ad2b6e4092c31b88f04d24738e7011dccf0ec5e2a`.

Production grew by 91,668,480 bytes, from 232,488 to 254,868 pages. Final
freelist is zero and no analysis WAL/SHM remains. Schema hash changed from
`47c4951a...` to `add400f5...` solely for the additive manifest-history table.
The independent second command caused zero byte, mtime, page, freelist, pointer
or fingerprint change; final database SHA-256 is `ea61ea95...`.

## Apply and reconciliation

The exact-copy rehearsal at
`temp/fundamentals_v4_diagnostic_phase9g/20260907T102013Z/` passed deterministic
pure replay, transaction rollback, first apply, second no-op and source/report
immutability. Production artifacts are under
`temp/fundamentals_v4_operating_income_v2_phase9h/`.

The first production apply was `APPLIED` with 1,348,543 logical package rows.
Its internal second apply was `NO_CHANGE`. The independent second production
command returned `NO_CHANGE` for both apply calls and for the provider-disabled
pipeline smoke, with unchanged activation time `20260907T102623Z`.

The corrected package has 50,585 Diagnostic endpoints and 354,095 evaluations,
exactly seven per endpoint, zero duplicates and zero orphans. Pure engine,
persistence and reader reconcile at tolerance `1e-12`. Working Capital agrees
with V1/source on all 50,585 endpoints. The other six flags agree on all 303,510
evaluations. Score, Lifecycle, Valuation, Delta, Relative Position, V1
Diagnostic Flags, canonical and TTM values are unchanged. SQLite quick check is
`ok` and foreign-key check is empty.

Temporary reports for CRMD, APD, NVDA, AGEN, AAT and BNC resolve the active
package and unchanged presentation. Working Capital renders CRMD 1.9700% clear,
APD 1.8119% clear, NVDA 9.0264% clear, AGEN 11.4504% active and AAT not
applicable. BNC is not ready for six TTM/valuation-derived flags, while its
canonical Working Capital inputs are available and produce 0.8855% clear; this
explains the apparent BNC expectation mismatch without changing the model.
Current, filing-date and Q-1 valuation sections remain present. UI generation,
partial batch handling, secure download, traversal rejection and route tests
passed.

Verification included 80 initial focused persistence, Phase 9G, Snapshot and UI
tests; 69 post-activation focused tests; 55 selected Snapshot/Scheduler UI
tests; 782 complete Fundamentals V4, Snapshot and Scheduler UI tests; and the
complete repository suite: 2,613 passed with 8 warnings in 384.22 seconds.
`compileall` and `git diff --check` passed. No test was omitted.

## Commands and rollback

The exact commands are retained in each artifact directory's
`commands_run.txt`. The production command was the Phase 9E protected module
with the five exact production paths, package `a36d6903...`, all seven exact
model fingerprints, `--full-universe --apply --confirm-production`, and an
isolated Phase 9H output directory. The second command used identical economic,
path and authorization arguments; only its fresh artifact directory differed.

For activation-only rollback, acquire the maintenance lock and atomically set
the active row to archived package `cf4ce813...` with its archived model
manifest, then run `assert_v2_active` before commit. For database restore, stop
all writers, retain the failed database, verify the pre-write backup SHA-256,
restore it into a new file with `sqlite3.Connection.backup()`, reopen read-only,
require `quick_check=ok`, zero foreign-key violations and the original active
manifest, then atomically replace the production file. No rollback was needed.

Remaining risks are current-revised rather than PIT history, current taxonomy,
the fixed 2026-09-06 package as-of until the next source refresh, and the normal
operational cost of a full-package recalculation. Nothing was pushed.
