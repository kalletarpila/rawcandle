# G-OPS-06 exact EC backup cleanup

**COMPLETE.** Explicit G-OPS-06 authorization executed the final G-OPS-05 proposal:
**23 images deleted / 278,384,205,824 allocated bytes**. EC whole images fell from
**24 / 291,597,950,976 bytes** to **1 / 13,213,745,152 bytes**. No other database,
backup family or SQLite sidecar was deleted.

Starting HEAD `c0a962e16bdd1d6a1ad9234a1be5280bc976310a`, branch
`chore/ignore-backups`. Actual HEAD and the 12 original worktree entries matched
expectations. No applicable RawCandle or ancestor AGENTS.md was present.
StockCore is outside this task and unchanged.

## Authority and ownership

The accepted [G-OPS-05 matrix](g_ops_05_backup_recovery_decisions.md) and its exact
machine proposal SHA-256
`a96540c2acf9ac77f6de94bf78ad677d9eeeef78d6ed75719029f6a23215bc27`
are the allowlist authority, combined with the user's explicit G-OPS-06 deletion
instruction. The G-OPS-05 proposal itself remains unmodified and non-executable.
No discovered/new filename acquired authority through age, pattern or ordering.

Every main matched its original device/inode, regular-file mode, uid, single link,
size/allocation, mtime and ctime. The original G-OPS-04 full SHA-256 witnesses were
reused only under these unchanged identities. All originating operation receipts
and compact-bundle artifacts retained their hashes. The required image received
a fresh full hash, quick_check and exact live-schema comparison.

The execution acquired the existing Production/admin and scheduler locks,
forecast lock, Windows temporary-cleanup flock and narrow EC retention flock.
Host process, lsof, service, taxonomy-operation, publication and kernel-lock checks
found no affected active owner. Operational main-file witnesses and publication
state were checked throughout deletion. Production jobs were neither stopped nor
disabled. All ownership was released normally after reconciliation.

`rawcandle/ec_backup_cleanup.py` checks the entire allowlist before unlinking,
persists the plan and each unlink intent durably, rechecks each identity, syncs
the directory, and records completion. Restart reconciles an absent file only
with its existing durable unlink intent; a changed or reappearing file is held.
Unknown associated files, symlinks, hard links, mounts, nonempty WAL/journals,
open references or changed sidecars stop the pass. Small existing sidecars were
bound to the plan and deliberately preserved; orphan journals were also preserved.

## Exact images deleted

All following filenames resolve directly under
`/home/kalle/projects/rawcandle/temp/`. Each completed with ledger state `DELETED`.

| ID | Exact filename | Allocated bytes deleted |
|---|---|---:|
| 1 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260911_20260918__20260920T034202Z.sqlite` | 11,078,078,464 |
| 2 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260914_20260923__20260924T042100Z.sqlite` | 11,172,302,848 |
| 3 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260917_20260924__20260925T041337Z.sqlite` | 11,264,593,920 |
| 4 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260918_20260925__20260926T111845Z.sqlite` | 11,356,659,712 |
| 5 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260921_20260928__20260929T041800Z.sqlite` | 11,469,307,904 |
| 6 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260922_20260929__20260930T041342Z.sqlite` | 11,555,975,168 |
| 7 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260923_20260930__20261001T041542Z.sqlite` | 11,644,329,984 |
| 8 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260924_20261001__20261002T041851Z.sqlite` | 11,736,100,864 |
| 9 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260924_20261002__20261003T135514Z.sqlite` | 11,827,843,072 |
| 10 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260928_20261005__20261006T041910Z.sqlite` | 11,915,485,184 |
| 11 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260929_20261006__20261007T042129Z.sqlite` | 12,002,193,408 |
| 12 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260930_20261007__20261008T041913Z.sqlite` | 12,091,564,032 |
| 13 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261001_20261008__20261009T041929Z.sqlite` | 12,183,887,872 |
| 14 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261002_20261009__20261010T042304Z.sqlite` | 12,276,498,432 |
| 15 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261005_20261012__20261013T041830Z.sqlite` | 12,362,510,336 |
| 16 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261006_20261013__20261014T094436Z.sqlite` | 12,450,455,552 |
| 17 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261007_20261014__20261015T042325Z.sqlite` | 12,584,992,768 |
| 18 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261008_20261015__20261016T041944Z.sqlite` | 12,682,313,728 |
| 19 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261009_20261016__20261017T042428Z.sqlite` | 12,773,339,136 |
| 20 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261012_20261019__20261020T042221Z.sqlite` | 12,858,425,344 |
| 21 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261013_20261020__20261021T042349Z.sqlite` | 12,943,536,128 |
| 22 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261014_20261021__20261022T042600Z.sqlite` | 13,032,247,296 |
| 23 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261015_20261022__20261023T042325Z.sqlite` | 13,121,564,672 |

The sole retained main is
`analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261016_20261023__20261024T042011Z.sqlite`.
It retains its original path, inode and content. It was not renamed, copied or
restored over an operational database.

Durable exact evidence is in ignored `temp/g_ops_06/`: `deletion_plan.json`,
`deletion_plan.json.execution.json`, `images_before.json`, `ownership_held.json`,
`locks_held.json`, `operational_open_check.json`, `temp_tree_before.json` and
`execution.log`. No original pre-existing temporary file disappeared outside the
23-image allowlist. See [hold release](g_ops_06_retention_hold_release.md),
[recovery](g_ops_06_recovery_and_preservation.md) and
[acceptance/space](g_ops_06_acceptance_evidence.md).
