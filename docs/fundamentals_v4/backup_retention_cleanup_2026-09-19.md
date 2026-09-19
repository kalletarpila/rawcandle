# RawCandle Fundamentals Backup Retention Cleanup - 2026-09-19

## Audit baseline

The cleanup used commit `e57e664d4b08a5e1c9f87e94ba4c26967901b6a9` and only the exact paths in `backup_retention_proposed_deletions_2026-09-19.csv`.

| Measure | Audit baseline |
| --- | ---: |
| Backup files | 98 |
| Total size | 97,763,926,592 bytes (97.763927 GB / 91.049752 GiB) |
| Planned deletion candidates | 66 |
| Planned reclaimable size | 58,326,718,745 bytes (58.326719 GB / 54.320990 GiB) |
| Planned retained files | 32 |
| Planned retained size | 39,437,207,847 bytes (39.437208 GB / 36.728762 GiB) |

Preflight checks established that:

- All 66 deletion rows were unique and marked only `DELETE_CANDIDATE`.
- No deletion row used `CURRENT_ROLLBACK`, `MILESTONE_BACKUP`, or `AMBIGUOUS` classification.
- All paths resolved to regular files under the repository `backups/` tree, with no symlink paths or active `data/` paths.
- The deletion and keep path sets did not overlap.
- Every deletion candidate existed and matched its audited size and timestamp.
- All 32 retained files existed and matched the keep inventory.
- The complete current backup inventory was the audited 98-file union; there were no new files.

## Execution

Deletion was performed as 66 individual exact-path `unlink` operations after repeating the preflight checks. No wildcard, recursive directory deletion, age rule, or inferred path was used. Empty directories were left in place.

| Outcome | Files | Bytes |
| --- | ---: | ---: |
| `DELETED` | 66 | 58,326,718,745 |
| `ALREADY_ABSENT` | 0 | 0 |
| `SKIPPED_CHANGED` | 0 | 0 |
| `FAILED` | 0 | 0 |

## Result

The complete post-cleanup inventory contains **32 files totaling 39,437,207,847 bytes (39.437208 GB / 36.728762 GiB)**.

Actual reclaimed storage is **58,326,718,745 bytes (58.326719 GB / 54.320990 GiB)**. This exactly equals the approved allowlist total. Every candidate path is absent, and no additional deletion was used to force the expected result.

## Retention verification

All keep-inventory paths remain present and retain their audited file sizes and timestamps:

| Classification | Files present | Missing | Changed |
| --- | ---: | ---: | ---: |
| `CURRENT_ROLLBACK` | 3 | 0 | 0 |
| `MILESTONE_BACKUP` | 16 | 0 | 0 |
| `AMBIGUOUS` | 8 | 0 | 0 |
| `EVIDENCE_OR_METADATA` | 5 | 0 | 0 |
| **Total** | **32** | **0** | **0** |

All eight ambiguous files across the four audited ambiguous families remain untouched.

## New files since audit

None. The post-cleanup tree contains exactly the 32 paths listed in `backup_retention_keep_inventory_2026-09-19.csv`.

## Production safety

The cleanup executor recorded existence, size, and nanosecond mtime for all five protected production databases before and after deletion. Those attributes remained identical, including after the required lightweight checks.

| Active database | Exists | `PRAGMA quick_check` |
| --- | --- | --- |
| `data/fundamentals_provider.db` | yes | `ok` |
| `data/fundamentals_v4.db` | yes | `ok` |
| `data/fundamentals_analysis.db` | yes | `ok` |

`data/osakedata.db` and `data/analysis.db` also remain present with unchanged size and mtime; no SQLite operation was run against them. No migration, rebuild, restore, or schema modification was performed.

Git validation before creating this report showed a clean worktree at the audit commit. `git diff --check` passed. Final validation after report creation also passed, with this report as the only repository documentation change; backup deletions remain ignored as designed.

## Exceptions

None. There were no changed candidates, already-absent candidates, deletion failures, missing or changed retained files, newly created backups, path substitutions, or deletions outside the approved CSV.

## Final state

**Yes. Only the approved `DELETE_CANDIDATE` set was removed, with all retained and ambiguous backups preserved.**
