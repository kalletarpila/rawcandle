# Phase 13G.2.3.1 Disk Usage Reconciliation and Cleanup

Date: 2026-09-15

Outcome: `OUTCOME A — DISK USAGE RECONCILED, SAFE PHASE-OWNED CLEANUP COMPLETED, AND PRODUCTION UNCHANGED`

No production Add Tickers run, economic rebuild, application-code change, Scheduler change or UI change was performed.

## Baseline

- Repository root: `/home/kalle/projects/rawcandle`
- Branch: `chore/ignore-backups`
- Starting HEAD: `3170b3ed591c10c67bfd01246448fe46f11c8066`
- Worktree before cleanup: clean
- Initial filesystem availability: `492.39 GiB`
- Final filesystem availability after cleanup and `sync`: `598.20 GiB`
- Confirmed reclaimed availability: `105.81 GiB`

## Root Cause

The reported drop from roughly `599G` free to roughly `493G` free was real.

It was caused by Phase 13G.2.3 pytest temporary directories under `/tmp/pytest-of-kalle`, not by compact retained evidence under `fundamental_reports/admin_runs/`.

Deleted candidates:

| Path | Classification | Allocated | Apparent | Reason |
| --- | --- | ---: | ---: | --- |
| `/tmp/pytest-of-kalle/pytest-145` | `CURRENT_PHASE_OWNED_TRANSIENT` | `31,967,817,728` bytes | `31,966,686,581` bytes | Phase 13G.2.3 targeted Snapshot/RP/RV pytest fixtures |
| `/tmp/pytest-of-kalle/pytest-146` | `CURRENT_PHASE_OWNED_TRANSIENT` | `40,801,288,192` bytes | `40,789,333,470` bytes | interrupted Phase 13G.2.3 full-suite attempt |
| `/tmp/pytest-of-kalle/pytest-147` | `CURRENT_PHASE_OWNED_TRANSIENT` | `40,842,854,400` bytes | `40,827,875,230` bytes | successful Phase 13G.2.3 full-suite rerun |

Total confirmed deleted allocated size: `113,611,960,320` bytes (`105.81 GiB`).

The largest contents were ordinary SQLite fixture/copy files, including repeated production-shaped `analysis.db`, `osakedata.db`, `fundamentals_analysis.db`, `fundamentals_v4.db` and provider DB copies. They were not sparse files or durable evidence.

## Preserved

The following material paths were preserved:

- `/tmp/pytest-of-kalle/pytest-104` - `36G`, older Sep 14 pytest tree, ownership not proven for this phase.
- `/tmp/pytest-of-kalle/pytest-105` - `8.0G`, older Sep 14 pytest tree, ownership not proven for this phase.
- `/tmp/pytest-of-kalle/pytest-107` - `38G`, older Sep 14 pytest tree, ownership not proven for this phase.
- `/tmp/phase13g22_accept` - `1.6M`, earlier Phase 13G.2.2 acceptance evidence.
- `/home/kalle/projects/rawcandle/temp` - `110G`, dominated by earlier Phase 13D/13F artifacts and outside the authorized Phase 13G.2.3.1 cleanup scope.
- `/home/kalle/projects/rawcandle/backups` - `79G`, treated as verified/preserved backup material.
- `/home/kalle/projects/rawcandle/fundamental_reports` - compact durable reports/evidence.

No uncertain-ownership path was deleted.

## Process and Open-File Checks

`lsof +L1` reported no deleted-but-open files. It emitted only unavailable filesystem warnings for `hugetlbfs` and `mqueue`.

No active pytest, Phase 13G admin, SQLite writer, backup or rebuild process was found beyond the inspection command itself before cleanup.

## Production Safety

Production checks were read-only.

Protected database paths remained present:

- `data/fundamentals_provider.db`
- `data/fundamentals_v4.db`
- `data/fundamentals_analysis.db`
- `data/osakedata.db`
- `data/analysis.db`

Pre/post checks:

- `PRAGMA quick_check`: `ok` for all protected DBs
- `PRAGMA foreign_key_check`: no rows for all protected DBs
- active package unchanged: `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- active RV model fingerprint unchanged: `76c2974108b2c5085b7dfa102acd4bb04eea36a5267bbdb1930a2bc7dc8cb35e`
- active RV snapshot ID unchanged: `1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b`
- active RV result fingerprint unchanged: `9c642e80b06fdbb8c6e703a46a6bda2c7031bc270fbd195b0a3acd7cdeba30f3`

## Evidence

Retained under:

`fundamental_reports/admin_runs/phase13g2_3_1_disk_cleanup/`

Key files:

- `disk_usage_before.json`
- `cleanup_candidates.json`
- `cleanup_actions.json`
- `disk_usage_after.json`
- `storage_reconciliation.json`
- `production_readonly_pre.json`
- `production_readonly_post.json`
- `production_readonly_comparison.json`
- `manifest.json`
- `status.json`
- `exit_code.txt`

## Handoff

The 106G discrepancy is reconciled and was safely reclaimed from confirmed current-phase pytest temp fixtures. Production is unchanged. Phase 13G.2.4 production deployment preparation can proceed, with the existing clean-tree guard and production apply authorization still required.
