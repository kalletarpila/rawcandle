# Phase 13G.2.5E: Fundamentals V1 Schema Retirement

## 1. Outcome

Phase 13G.2.5E succeeded. Fresh analysis bootstrap is V2-only, the explicit
copy-only cleanup migration is proven, and a fresh full V2 + RP V2 + RV rebuild
finished `READY`. Live `data/fundamentals_analysis.db` was not changed.

## 2. Starting V1 schema footprint

Read-only production inventory found:

- `lifecycle_result`: 0 rows, one empty 4 KiB table page;
- `valuation_result`: 0 rows, one empty 4 KiB table page;
- their two empty indexes: one 4 KiB page each;
- `operating_income_v2_package_manifest_history`: one 4 KiB page and one row,
  duplicating the current manifest;
- no trigger referencing either legacy result table;
- no non-current model fingerprint in Score, revised Lifecycle, revised
  Valuation, Delta, Diagnostics, RP snapshot, or the RP active pointer;
- one current Score V2 `analysis_model_run`, one current active family, one
  current package manifest, and one current RP V2 pointer.

The starting analysis file was 892,256,256 bytes with 217,836 pages and no
free-list pages. Its SHA-256 was
`7ed45dd8e8ae902d66022d3dcdbfc1b9140c2a7710391f2f5046738c817782b7`.

## 3. Final schema

`ANALYSIS_SCHEMA_SQL` now creates Score V2 storage, revised Lifecycle and
Valuation storage, Delta, eight-flag Diagnostics, RP V2, RV, and current-state
metadata directly. Full rebuild no longer depends on a legacy bootstrap plus
later compatibility expansion.

## 4. Removed structures

- Removed `lifecycle_result` and `valuation_result` plus their indexes. They
  were empty V1-only outputs and no current reader or writer used them.
- Removed `operating_income_v2_package_manifest_history`. It duplicated the
  current manifest and existed only for archived-package selection.
- Removed pre-Phase-9G and ten-year package aliases, the old diagnostic
  fingerprint allow-list entry, archived-manifest lookup, and the dormant
  seven-flag package writer.
- Removed executable Phase 12E and Phase 13C production entrypoints tied to
  retired package identities. Their runbooks remain as historical evidence.
- Updated the current report reader to the eight-flag Diagnostic and Snapshot
  identities.

## 5. Shared structures retained

`analysis_model_run`, `fundamentals_active_model_family`, the current package
manifest, revised result tables, model version/fingerprint fields, RP V2
snapshot/pointer tables, RP taxonomy dependency, RV tables, Delta relationship
fingerprints, and current EBIT diagnostic fields remain. Each participates in
current validation, reader selection, source lineage, or current model math.
RV's version suffix `V1` is current RV and is unrelated to retired Fundamentals
or Relative Position V1. Historical migration runbooks and Phase 12D evidence
code remain for provenance.

## 6. Cleanup migration

`cleanup_legacy_v1_schema(path)` rejects relative paths, symlinks, and the live
production analysis path. Under `BEGIN IMMEDIATE` it validates the complete
active Phase 10B package and rejects non-current shared-table state or nonempty
legacy result tables. It then drops only the five classified objects, runs
foreign-key and quick checks, and commits. Failure rolls back; an already-clean
current DB returns `NO_CHANGE`.

## 7. Production-copy rehearsal

SQLite online backup produced a production-shaped copy and a byte-identical
pre-cleanup backup, both SHA-256
`b3ec035c4fb4c0ca179ba518e7477d45c54a3e5dbb936a0478f836155b04ada7`.
Cleanup returned `APPLIED`; its second invocation returned `NO_CHANGE`.
Quick check and foreign-key check passed. Economic fingerprint remained
`f377ebd50789b2f9ed6d7932528fb8c2faeb7f779a35ab03dea9cad27026980c`
and physical package fingerprint remained
`40787b540b7763a3a5cceb2f5c797b998a0a918c9c900e260ff6ec60ddf28a66`.

## 8. Fresh final-schema rebuild

At explicit as-of `2026-09-18`, the independent rebuild finished `READY` with
87,860 Score, Lifecycle, Valuation, Delta, and Diagnostic endpoints; 702,880
Diagnostic evaluations; 13,799 RP results; and 2,444 RV companies. The package
economic and physical fingerprints exactly matched the cleaned copy. Taxonomy
was `dc_ecosystem` / `DC_TAXONOMY_FULL_V2_1` /
`801698f6b352c445cc8e6f5fd51a1cac2779d11f6ce72a1c10bf71bb8aae4559`.
RP result fingerprint was
`8933e92bfa6e1c6993992935fea84e0d2647990f74f55a35327a83fac26e33bf`.
Current-source RV input/source/result fingerprints were respectively
`7631d5d3a1eae2137d444d89bc325a5d12c482b285f43d3d0ae572a9001bfad9`,
`ff36b9874c33ed5a9e40b32cfffe905aed798d48723bb055a00d8ae5f6a48188`,
and `c4caee88e63ec378ecba3341f621ced844baa5daa6daa3440014ff57c085c8a9`.

## 9. Semantic equivalence

The raw cleaned copy preserved its pre-cleanup RV exactly. During initial tests,
the pre-existing stock scheduler updated market/taxonomy source files; therefore
the old production RV correctly failed validation against the newer market
source. After stopping the scheduler and refreshing RV on a separate comparison
clone, cleaned-copy and fresh-rebuild current state matched for every V2 layer,
RP, taxonomy dependency, and RV. NVDA, AMZN, SNDK, and IA Snapshots matched
exactly after normalizing rebuild timestamps.

## 10. Administration validation

The Administration and full-rebuild suite passed 158/158 tests. It covers Add
Tickers, Sector/Industry synchronization, Taxonomy synchronization, the shared
full V2 rebuild, and B3 candidate/postflight and rollback behavior.

## 11. V1 absence proof

Fresh schema and both rehearsals contain none of the removed tables, indexes,
manifest history, old active package aliases, RP V1 pointers, old package
reader/writer paths, or Phase 12E/13C executable routes. Current V2 readers do
not query the removed structures. Runtime V1 modules and Admin/CLI routes were
already removed in Phase D.

## 12. RV safety

Current RV was retained and rebuilt successfully. It remains sourced from the
active V2 package and current authoritative sources. No RV table or current RV
identity was classified as legacy V1.

## 13. Database size

The migrated copy remained 892,256,256 bytes because SQLite does not shrink on
`DROP`; free-list count rose from 0 to 6 pages. The five measured removed
objects occupied 20 KiB. Natural fresh-final DB size was 892,231,680 bytes,
exactly 24,576 bytes smaller. `VACUUM` was intentionally not run.

## 14. Tests

- Focused schema/persistence/bootstrap: 81 passed, 0 skipped, 0 failed.
- Administration and full rebuild: 158 passed, 0 skipped, 0 failed.
- Broad relevant regression: 565 passed, 14 deselected, 0 failed.
- Post-hardening cleanup/reader/Snapshot rerun: 41 passed, 0 skipped, 0 failed.
- `compileall` and `git diff --check`: passed.

## 15. Documentation

This report is the current schema-retirement contract. Phase D, Phase 12E, and
Phase 13C runbooks are retained as historical audit records and marked as such;
their deleted commands are not current operating instructions.

## 16. Cleanup

Large Phase E migration, backup, comparison, and fresh-rebuild DB files were
deleted after final evidence capture. Lightweight rebuild events/result and
this report remain. The verified Phase C rollback backup is untouched. The
daily scheduler timer was restored to `active (waiting)` for the next 05:30
run; its service is healthy and `inactive` between runs.

## 17. Production safety

No Phase E command wrote the live production analysis, provider, canonical,
market, or taxonomy DB, and no production replacement or push occurred. A
pre-existing systemd scheduler did write `osakedata.db` and `analysis.db` during
the first tests; it was identified, stopped normally with its timer, and no
writer remained before either rehearsal baseline was captured.
Final stable SHA-256 values were analysis
`7ed45dd8e8ae902d66022d3dcdbfc1b9140c2a7710391f2f5046738c817782b7`,
canonical `31613bde3be6cf22a218ea36f2c98424a6e4c3bf99b08b6858ceb31fc5c5b974`,
provider `b79948a094cff6362488e1ce6f90406b125606d4c3f2d66ddd3c010ab3d58e01`,
market `2eccf0909c2859c545d8f85703bd688bafedfc3f1d06ff03b3898d342d2ff60f`,
and taxonomy `c7625e289a649ee153d8734722af7c11e087efe97ad50d7647eb7d6b05d47e87`.

## 18. Recommended final production cleanup

Phase F should build a new final-schema V2 DB from stable authoritative sources,
require `READY`, create and verify a backup of current production analysis,
atomically replace only `fundamentals_analysis.db`, and run production-path
postflight. The in-place cleanup exists for proof and recovery tooling, but is
not the preferred publication mechanism.

## 19. Remaining issues

No schema or code blocker remains. Phase F must coordinate scheduler downtime
and use a fresh preview/baseline because source state changed on 2026-09-19.

## 20. Recommended next phase

**Phase 13G.2.5F - Publish Final V2-Only Analysis Schema to Production and Close
V1 Retirement.** It is not executed here.

## 21. Git

The final commit hash, message, status, and broad-test count are appended at
closure after all intended changes are committed. No push is performed.
