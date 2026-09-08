# Fundamentals V4 Phase 10C.1 Test-Isolation Audit

## Result

Status: `LOGICALLY_VERIFIED_CURRENT_BASELINE`

Phase 10C.1 established repository-wide pytest protection for the seven
configured production SQLite databases, corrected two tests that could open a
production default as writable, logically verified the current
`data/analysis.db`, and created one independently openable online backup.
No economic model, production row, active package, taxonomy content, report, or
pipeline result was changed by this phase.

This is a forward-looking baseline. It does not prove that the byte layout from
before the Phase 10C incident was restored.

## Incident and root cause

The Phase 10C deployment report records the original incident in
`fundamentals_v4_non_operating_gap_phase10c_deployment.md`. The old
`test_generate_random_findings_returns_tuple` supplied a temporary market
database but used the writable literal `data/analysis.db` for
`DatabaseManager`. `DatabaseManager.get_connection()` called
`sqlite3.connect()` in the main pytest process. Existing production deployment
gates protected deployment entrypoints, not arbitrary repository tests, so the
write was not rejected.

The exact random `analysis_findings` row was removed and its sequence restored
during Phase 10C. Insert/delete activity nevertheless changed SQLite pages.
Restoring rows and sequences does not recreate the prior page allocation, free
space, transaction metadata, or byte ordering. No `VACUUM`, dump/reload, or
page-level rewrite was used.

The hardened full-suite run found a second latent route:
`test_backfill_dry_run_writes_report` passed a temporary market database to
`backfill_uncorrected()`, while that function opened its current-working-
directory default `data/analysis.db` even in dry-run mode. The guard rejected
the connection before it opened. The test now changes into `tmp_path`, where
the same relative path resolves to a disposable test database. Behavioral
coverage remains unchanged.

## Production database registry

The authoritative test registry was derived from scheduler configuration,
Fundamentals manifests/runbooks, and production tool defaults. Zero-byte
placeholders `fundamentals_analysis_2.db`, `results.db`, and `stock_data.db`
are not configured production databases and are not included.

| Role | Resolved file | Size (bytes) | Main SHA-256 | Journal |
| --- | --- | ---: | --- | --- |
| Analysis/classification and taxonomy source | `data/analysis.db` | 10,406,772,736 | `d967eabfabe115ffb2ef21f5a04c2daed530811fa95eb3300747c5c9a58b1f3c` | WAL |
| Market data | `data/osakedata.db` | 1,965,875,200 | `fcf4e374e1ca2d7208940e8ce9c8b737c310843c04923a8f779caa8cd115e48f` | WAL |
| Fundamentals provider | `data/fundamentals_provider.db` | 551,792,640 | `1905d09cf93901622ae178e7b472e571bc872ba2b243ff3b02a5957f9b6e2c14` | DELETE |
| Fundamentals canonical | `data/fundamentals_v4.db` | 372,228,096 | `f553639e7f25ce75fed51af0c2127121a96573cd88728c2eafa84b9dfdc087da` | DELETE |
| Fundamentals analysis | `data/fundamentals_analysis.db` | 1,146,810,368 | `8193f11efa8494c060e8fdb7772c3e89de1565baaedf1a25e8e48ad3f5417d87` | DELETE |
| Combo Edge workbench | `data/combo_edge_workbench.db` | 2,330,624 | `2c0cc3d4ffea48f33a909a60c8c689a00c3fae329c04b3d474e71b72c7b559ba` | DELETE |
| Ecosystem dashboard | `data/ecosystem_dashboard.db` | 14,454,784 | `6b847fb44d43e04af4aaff1be36abc5e768307595fc3d96e46d791837adc2960` | WAL |

The timestamped JSON artifact records configured and resolved paths, file type,
symlink state, permissions, mtimes, schema hashes, page metrics, freelists,
sidecars, every table row count, sequences, integrity checks, and selected
ordered logical fingerprints.

## Repository write-path audit

The AST-backed audit examined Python sources after excluding generated
`temp/`, `backups/`, virtual environments, and Git internals. It classified
1,210 SQLite/helper/subprocess call sites:

| Classification | Count |
| --- | ---: |
| `SAFE_READ_ONLY` | 80 |
| `SAFE_TEMP_COPY` | 515 |
| `PRODUCTION_GUARDED` | 605 |
| `NOT_SQLITE` | 10 |
| `UNSAFE_REAL_PATH` | 0 |
| `AMBIGUOUS` | 0 |

No imported `sqlite3.connect` alias, active SQLAlchemy SQLite adapter, or
actual test invocation of the external `sqlite3` executable was found.
Python subprocess tests inherit the guard through `sitecustomize.py`.
The complete call-site evidence is in
`repository_write_path_audit.csv`.

## Layered protection

`rawcandle.testing.database_isolation` provides one canonical resolved-path
registry and these controls:

1. `sqlite3.connect` and `sqlite3.dbapi2.connect` reject writable opens of
   protected targets before connection establishment.
2. Plain paths, relative paths, `..`, symlink aliases, percent-decoded SQLite
   URIs, and `file:` URIs resolve to canonical paths before comparison.
3. A protected database is permitted only with an explicit SQLite
   `mode=ro` URI. `immutable=1` is not used, so committed WAL content is not
   hidden.
4. Guarded connection/cursor methods reject protected `ATTACH DATABASE` and
   `VACUUM INTO` targets, including bound parameters. SQLite's authorizer is a
   second check for `ATTACH`.
5. Custom connection factories are rejected during pytest because they could
   bypass guarded cursor behavior.
6. `require_test_database_path` rejects missing writable test paths instead
   of permitting a production fallback.
7. `tests/conftest.py` snapshots the main, WAL, and SHM bytes of all protected
   databases before collection and after the session. Any main/WAL/content
   change fails the session. Only an SHM mtime change with identical size and
   SHA-256 is tolerated.
8. `RAWCANDLE_TEST_DATABASE_GUARD=1` and repository `PYTHONPATH` are
   propagated through `PYTHONPATH`, protecting Python child processes.

## Current taxonomy baseline

Baseline capture: `20260908T055459Z` UTC.

The morning scheduled production update completed before this phase's baseline.
It legitimately advanced broad analysis/market state from the prior night's
Phase 10C evidence. Phase 10C.1 therefore compares all of its tests against the
verified state present at its own preflight; it does not describe morning
production changes as test mutations.

For `data/analysis.db`:

| Check | Result |
| --- | --- |
| Size | 10,406,772,736 bytes |
| SHA-256 | `d967eabfabe115ffb2ef21f5a04c2daed530811fa95eb3300747c5c9a58b1f3c` |
| Schema hash | `d1e8d48588891e85c0080ff6b844e36ca919f4d998acf8ca9f4eaf2b5cffee6c` |
| Page size / pages / freelist | 4,096 / 2,540,716 / 1 |
| Journal / WAL | WAL / zero-byte WAL |
| `quick_check` | `ok` |
| Foreign-key violations | 0 |
| Prohibited duplicate identities | 0 |
| Explicit taxonomy orphan relationships | 0 |
| Incident row present | no |
| `analysis_findings` count / max id / sequence | 1,556,609 / 4,711,870 / 4,711,870 |
| Ecosystem / versions / entities / aliases / memberships | 1 / 3 / 335 / 1 / 1,188 |

Ordered `analysis_findings` fingerprint:
`fe613ad7ed78a4b22947208c134065f83d20af716ac9f06fa87617fbaf1aa71d`.
All five EC table fingerprints are in the JSON inventory. NVDA, AMZN, and VRT
resolved through direct current ticker identities; sector/industry and
ecosystem reads succeeded. The current Relative Position source loaded 4,899
observations with classification fingerprint
`f7d2a73c4742df1107888314e49e25ac4b1970a72c31f5edbe747e0b68b084b3`
and taxonomy fingerprint
`1ed7618a3d9e1d3e8cf39fbef917c0038b734745298665709f876e67af6e7e60`.

No trustworthy full pre-incident logical backup exists. Prior deployment
artifacts prove selected historical hashes and stable EC counts, but they are
not a complete ordered pre-incident content inventory. Exact historical
restoration is therefore not claimed.

## Backup

Free space before backup was 467,704,635,392 bytes. The conservative gate
required 26,182,254,592 bytes: twice the source size plus a 5 GiB reserve.

The online SQLite backup is:

`backups/analysis.phase10c1.20260908T055459Z.db`

It is a new 10,406,772,736-byte regular non-symlink file. Its SHA-256 is
`8c64ea6226818ed46451bfe3abb3ad54e4d5a47564e0c1b856730f640cdf6a01`.
It opens independently, has no WAL/SHM dependency, returns
`quick_check=ok`, and has zero foreign-key violations. Schema, pages,
freelist, all table counts, sequences, and selected ordered logical
fingerprints match the source baseline. Its physical SHA differs, as expected
for SQLite online backup output with an independently materialized layout.

## Verification

Focused guard and original corrected-test run: 15 passed in 13.09 seconds.
After the second unsafe default was exposed, the final expanded focused command
passed 18 tests in 15.24 seconds.

Final complete repository run:

`2678 passed, 8 warnings in 408.69s (0:06:48)`.

The complete suite includes Scheduler, taxonomy, Relative Position, Snapshot,
Fundamentals V4, and the formerly offending tests. Compile checks passed.
`ruff` was not installed and was not added. `git diff --check` is part of
the final commit gate.

Preflight and postflight main and WAL inventories are identical for all seven
databases. All logical fingerprints and taxonomy checks are identical. The
`analysis.db-shm` and `ecosystem_dashboard.db-shm` mtimes changed during
read locking, but both remained 32,768 bytes with identical SHA-256
`fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb`.
No database content changed.

Production invariants after the suite:

* active package remains
  `0e269e52a63500342df8a08ee2f91552fdc8fb216fa68cfe469bafb6aa8e3c30`
* rollback package
  `a36d6903c3d640da5e9bd7034faee700b7b064e74ea871880c1bfa2348f4964d`
  remains `COMPLETE`
* active diagnostics contain 50,585 endpoints and 404,680 evaluations
* every endpoint has exactly eight evaluations
* score, lifecycle, delta, relative-position, valuation, diagnostic, and
  snapshot fingerprints remain those in the active manifest
* provider, canonical, fundamentals-analysis, and report state did not change
  during the controlled test window.

## Artifacts

Preflight:
`temp/fundamentals_v4_test_isolation_phase10c1/20260908T055312Z_preflight/`

Verified baseline and backup evidence:
`temp/fundamentals_v4_test_isolation_phase10c1/20260908T060000Z_baseline_backup/`

Final postflight:
`temp/fundamentals_v4_test_isolation_phase10c1/20260908T064000Z_postflight_final/`

Final invariant-gated audit:
`temp/fundamentals_v4_test_isolation_phase10c1/20260908T063500Z_final_verified/`

These generated artifacts and the database backup are intentionally untracked.

## Residual limits

The preventive Python guard covers the repository's discovered SQLite paths,
standard connection APIs, guarded SQL execution, and Python subprocesses. Code
can still bypass a Python monkeypatch with a native extension, an external
non-Python SQLite process, direct OS file writes, deliberate monkeypatch
replacement, or replacement of SQLite's authorizer. Session byte inventories
contain these routes if they affect protected files.

An unrelated external production writer during pytest also causes a deliberate
session failure; run the full suite outside scheduled update windows. New
production database roles must be added to
`PROTECTED_DATABASE_ROLES` when production configuration changes. Tests that
need writes must always use `tmp_path` or an explicit disposable fixture.
