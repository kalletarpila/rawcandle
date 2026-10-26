# G-OPS-06 acceptance evidence

**COMPLETE.** Starting HEAD `c0a962e16bdd1d6a1ad9234a1be5280bc976310a` →
local G-OPS-06 commit recorded in `temp/g_ops_06/commit_receipt.json`.
Branch `chore/ignore-backups`. Push: **NO**.

| Outcome | Verified result |
|---|---|
| Approved cleanup | 23 exact G-OPS-05 candidates deleted; **278,384,205,824 allocated bytes** |
| EC main images | **24 → 1**; **291,597,950,976 → 13,213,745,152 allocated bytes** |
| Retained point | October 24 general Analysis image; unchanged full identity/hash, integrity/schema PASS |
| Historical hold | **RELEASED**, retained as an evidence-bound state receipt |
| Future owner | **ACTIVE**, conditional on accepted EC scope, general recovery and closed publication/recovery obligations |
| Existing Windows cleanup | Entire EC family protected; enabled 21:00 schedule and unrelated behavior unchanged |
| Production preservation | 244 main-file witnesses and 29 EC/DC table fingerprints unchanged; publication/configuration unchanged |
| Current parity/watermarks | Original 19-date discrepancies unchanged; latest six pass; heads aligned through October 23 |
| StockCore / existing work | Unchanged; all 12 original RawCandle worktree entries preserved |
| Destructive exclusions | No sidecars, unknown files, unrelated backups or operational databases deleted |
| Runtime actions | Providers 0; live backfills/repairs 0; new permanent backups 0; compaction 0 |

## Focused checks

**198 tests passed** across `test_ec_backup_cleanup.py`,
`test_ec_backup_retention.py`, `test_stock_update_scheduler_runner.py`,
`test_run_ec_source_layer_backfill_cli.py` and
`test_run_ec_source_layer_refresh_cli.py`. Full suite: **NO**.

Tests cover exact 23-image reconciliation, required-image exclusion, changed or
unknown identities/associated files, sidecars, active owners, interruption after
unlink, restart/idempotence, unrelated-file preservation, checked hold release,
accepted COMPLETE and accepted overall PARTIAL, genuinely unfinished/FAILED/
CANCELLED states, unresolved publication, explicit reuse, general-point protection
and Windows script coexistence. No live job was needed.

An initial fixture run exposed the new current-image open-reference guard raising
instead of reporting a hold; the guard was corrected before deletion and the
complete focused set passed. One test invocation used incorrect CLI test filenames
and collected no tests; the corrected invocation is the recorded 198-test PASS.
`git diff --check`, Python compilation and runtime preservation assertions pass.
No full-size restoration was repeated.

## Space measurements

All figures are bytes; snapshots are recorded in `temp/g_ops_06/disk_space.json`.

| Measure | Before | After |
|---|---:|---:|
| Linux available | 407,881,822,208 | 686,249,050,112 |
| Windows D: free | 54,229,786,624 | 54,229,786,624 |
| WSL VHDX allocated | 923,382,317,056 | 923,382,317,056 |

Linux available space increased **278,367,227,904 bytes**, which is **16,977,920
bytes less** than the exact deleted image allocation. New parity/audit/test
evidence and other filesystem writes consume space during measurement; the
unlink ledger remains the authority for the deleted allocation. Windows D: free
space increased **0 bytes**. VHDX apparent and allocated size remain
**923,382,317,056 bytes**; no D: reclamation or compaction is claimed.

## Durable evidence and commit boundary

Ignored `temp/g_ops_06/` contains preflight/process/open-file/kernel-lock checks,
production/publication and StockCore witnesses, exact allowlist plus per-unlink
ledger, retained qualification, held ownership, release qualification/receipt,
repeated parity/head results, final preservation assertions, Windows/Linux disk
snapshots, task/timer snapshots and focused logs. The accepted G-OPS-04/05 evidence
remains intact and independently hash-bound.

Only the four requested reports, maintenance backlog and focused RawCandle owner/
cleanup implementation/tests belong to this commit. Original publication-journal
changes and unrelated untracked files are excluded. No database, large generated
extract or temporary restore is committed. See
[exact deletions](g_ops_06_ec_backup_cleanup.md),
[release/lifecycle](g_ops_06_retention_hold_release.md),
[recovery qualifications](g_ops_06_recovery_and_preservation.md) and
[maintenance backlog](operational_maintenance_backlog.md).
