# Operating-Income V2 Phase 9H Production Runbook

Status: `AUTHORIZED FOR PHASE 9H EXECUTION`

Phase 9H deploys only the Phase 9G Diagnostic Flags V2 correction and activates
the coherent package that contains it. It does not fetch provider data, rebuild
canonical or TTM data, change formulas, or regenerate `fundamental_reports/`.

## Locked identities

| Identity | Fingerprint |
|---|---|
| Diagnostic model | `7f6291bf04e69cf22944ea3f81e07b284ccffd8edbd0edea4190ddc79050b031` |
| Package | `a36d6903c3d640da5e9bd7034faee700b7b064e74ea871880c1bfa2348f4964d` |
| Diagnostic source | `ac3703717563f884555ed3a3e442f05cbb7d58bff52787342249f3812f21dc3d` |
| Diagnostic result | `f51858c047c3070fda072ffe3fdd683b0537cfc790cd6e2a81ffb0d19c6bbf80` |
| Diagnostic physical | `124ca6c140b9a466a34133fd5d468e2d5e04c0119dddd3addd50aef484f02c27` |
| Diagnostic layout | `75b83b2c228fc2ce87c218d00c946ef65c5c408aca2a7ad12db92ee1a485a955` |
| Snapshot economic | `1b4963c3b968008dd753d86c9a95c5f21737956113ea5c70f481b2ee96757f64` |
| Snapshot presentation | `bc4b4a3b355063697f1fe3182a105342d804a59bb41a86ec40ef6fe4364abee2` |

The existing Phase 9E CLI remains the protected production entry point. Its
runtime package and model constants must equal this table. Writes require exact
non-symlink production paths, `--full-universe`, `--apply`,
`--confirm-production`, every locked fingerprint, a clean worktree, an
available maintenance lock, and sufficient disk capacity.

## Versioned manifest preservation

`operating_income_v2_package_manifest` remains the current-package record.
Before replacement and after each successful package apply, its complete row is
also stored in `operating_income_v2_package_manifest_history`, keyed by the
persistence fingerprint. Active-family validation resolves the manifest named
by the activation pointer from this history. This preserves both the pre-9G and
corrected coherent manifests and permits an atomic pointer rollback without
rewriting economic rows.

## Procedure

1. Record git, process, holder, path, SQLite, sidecar, schema, row-count and disk
   evidence. Stop on any failed gate.
2. Resolve both latest-per-company and current-fresh cohorts. Current-fresh uses
   `ttm_source_available_date <= 2026-09-06` and age at most 180 calendar days.
   The verified pre-deployment counts are 2,451 latest endpoints and 2,431
   current-fresh endpoints; the earlier Phase 9G 2,451 label was inaccurate.
3. Run focused tests and an exact-copy Phase 9G rehearsal from the current
   production analysis database. Require all reconciliation, no-op and rollback
   checks.
4. Run the Phase 9E protected CLI with the Phase 9H fingerprints. It creates and
   verifies an online SQLite backup before the first write, applies the complete
   coherent package, requires a second `NO_CHANGE`, activates one manifest row,
   and runs provider-disabled pipeline, Snapshot and UI service smoke checks.
5. Independently verify the corrected and old manifests, all diagnostic counts,
   Working Capital V1/V2 equality, the six unaffected flags, source database
   immutability, report immutability, active reader resolution, SQLite integrity,
   and temporary reports for CRMD, APD, NVDA, AGEN, AAT and BNC.

## Rollback

Keep the verified pre-write backup. On an activation-only defect, hold the
maintenance lock and atomically restore the pre-9G activation row; validation
must resolve its archived manifest before commit. On integrity or unrelated-data
failure, stop writers, retain the failed database and restore into a new file
with `sqlite3.Connection.backup()` from the retained backup. Independently run
`quick_check`, `foreign_key_check`, original active-manifest checks and critical
row counts before an atomic file replacement. Do not delete either V2 history.
