# G-OPS-04 cleanup execution

**PARTIAL task. Destructive cleanup: BLOCKED; no full EC backup image deleted.**
The user STOP condition was triggered by unresolved historical EC semantic and
required-lineage parity. No production repair/backfill was authorized or run.

| Measure | Before | After |
|---|---:|---:|
| Full EC pre-write images | 24 | 24 |
| Full-image allocated bytes | 291,597,950,976 | 291,597,950,976 |
| RETAIN_REQUIRED | 1 | 1 |
| RETAIN_TEMPORARILY | 0 | 0 |
| RETIRE_APPROVED | 0 | 0 |
| BLOCKED_UNCERTAIN | 23 | 23 |
| Images / allocated bytes deleted | — | **0 / 0** |
| Linux available bytes | 407,955,087,360 | 407,933,816,832 |
| Windows D: available bytes | 54,233,366,528 | 54,233,366,528 |
| WSL VHDX apparent / Windows allocated bytes | 923,382,317,056 | 923,382,317,056 |

Linux free-space change: **-21,270,528 bytes**.
No backup reclamation is credited; filesystem movement includes evidence,
metadata and concurrent host activity that was not individually attributed.
Windows allocation was measured using GetCompressedFileSizeW, attributes Archive.
No VHD compaction, trim, relocation or Windows configuration change occurred.
Linux and Windows numbers are independent measurements.

The exact deletion allowlist is **empty**, expected reclaimed bytes **0**, in
ignored `temp/g_ops_04/deletion_allowlist.json`; `cleanup_execution.json` records
the stop. The unexecuted retirement proposal was disabled. Every original image's
path/device/inode/link/owner/type/size/mtime/ctime remains unchanged after all
read-only checks. Original full-image SHA-256 values are in the inventory.

All **21 historical proposal images**, totaling **252,230,393,856 allocated
bytes**, are individually BLOCKED_UNCERTAIN. Two former keep-three candidates are
also blocked; the latest October 24 image is RETAIN_REQUIRED for current EC
rollback/six-date replay. **Zero new full EC images** were discovered since G-OPS-01.
No keep-three approval or original-operation closure was inferred from age.
Per-image originating intervals, receipts and exact unresolved historical dates
are in [inventory](g_ops_04_ec_backup_inventory.md) and its machine-readable record.

The blocker is precise: **19 historical trading dates September 21–October 15**
have **15,269 semantic + 2,033 required-lineage mismatches** under the existing
explicit-V2 parity contract, with zero operational-metadata drift. Coverage and
latest heads pass; only the latest six dates pass parity. Historical accepted
source/EC vintages and their rollback/investigation obligations cannot yet be
closed. No SQLite corruption was found: all 24 images passed quick_check and
exact live-schema comparison. That physical validity does not override the
application-level hold.

## Lifecycle and preserved owners

The implemented terminal retention function is installed in both backup creators
and the existing scheduler's final reporting path. A durable same-scope hold at
`temp/.ec-backup-retention-hold.json` prevents release while historical acceptance
is unresolved, including future otherwise successful rolling runs. It records the
blocking evidence/hash and release condition. It was installed under existing
Production/scheduler and EC retention locks; no operation was run to exercise it
against production. Normal accepted-run bounding is implemented/tested but remains
**held for this scope** until separately qualified resolution.

Existing `/home/kalle/scripts/rawcandle_temp_cleanup.sh` matches the maintained
tracked script. Its unsafe EC refresh age/count ownership is removed; all EC
backfill/refresh destinations, including interrupted empty copies and sidecars,
are protected from its other rules. Other cleanup rules and the 21:00 task are
unchanged; no generic cleanup was invoked against production directories.

Host process, kernel-lock and open-file inspection found no active EC backfill,
source/Fundamentals/forecast operation using these images. The idle scheduler UI
was preserved. The audit's own image readers were identified separately and
finished before final checks. No process was stopped. The latest bounded restore
used only an isolated **138,723,328-byte EC-only copy**; that exact audit-owned
scratch was removed after its integrity/semantic receipts were retained. This is
not counted as retirement of an original backup.

Original manifests, compact recovery evidence and EC/scheduler logs remain, with
copied per-operation receipts in ignored `temp/g_ops_04/receipts/`. Existing empty
WAL/SHM and two orphan interrupted-copy journals remain; the audit also caused
SQLite read-only reader sidecars on the retained image. No existing image/sidecar
was manually removed or checkpointed. No live database was restored, published,
recalculated, vacuumed or checkpointed during this task.

Final preservation checks passed for the captured protected main files under
RawCandle data/Fundamentals/forecast backup groups. Read-only SQLite inspection may
update transient SHM reader-lock metadata; protected main databases, committed
WAL state and the pre-existing tracked publication journal were not changed.
Seven StockCore protected-file witnesses and its clean Git status remain unchanged;
no StockCore writes occurred. Source/forecast configuration SHA-256 values and
systemd timer definitions match the baseline. Source **04:30**, forecast **14:00**,
Windows cleanup **21:00**, enabled states unchanged. Normal source service starts
a fresh interpreter from this checkout; the idle UI was not restarted.

The original **12 unrelated worktree entries** are preserved and excluded from
the task commit. Final HEAD is the local commit containing these reports, recorded
in `temp/g_ops_04/commit_receipt.json`. **Push: NO.**

## Largest remaining relevant RawCandle groups

These are disjoint; data below means direct files, excluding generation children.
No unrelated subsystem cleanup was undertaken.

| Group | Allocated bytes |
|---|---:|
| Full EC backup family | 291,597,950,976 |
| `data/fundamentals_generations` | 59,923,107,840 |
| `backups/forecasts` | 31,264,391,168 |
| `backups/fundamentals_admin_production` | 25,413,484,544 |
| `backups/datacenter-weighting-v2` | 22,714,478,592 |
| Direct `data/` files | 20,183,445,504 |
| `temp/datacenter_weighting_v2_migration_rehearsal` | 11,387,379,712 |

Outstanding: qualify the 19-date historical parity/vintage issue and the absent
August pre-taxonomy full-reversal image reference before any affected retention
release. The independent October 25 Fundamentals FULL_WORKFLOW blocker is reported
separately and was not repaired. See [acceptance](g_ops_04_acceptance_evidence.md),
[policy](g_ops_04_retention_policy.md) and [maintenance backlog](operational_maintenance_backlog.md).
