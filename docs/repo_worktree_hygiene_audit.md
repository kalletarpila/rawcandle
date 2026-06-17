# repository worktree hygiene audit

## Executive summary

This audit documents RawCandle working-tree noise around local DB files, SQLite WAL/SHM files, backups, temp artifacts, exports, generated reports, local scheduler config, and other untracked artifacts.

Assessment: the recurring noise was mostly caused by safe-to-ignore local artifacts that were not covered by `.gitignore`. A minimal `.gitignore` update was added for DB/WAL/SHM files, SQLite backup files, `temp/`, `exports/`, generated report directories, `data/yf_cache/`, data backup directories, and the local root `scheduler_config.json`.

No DB, backup, WAL/SHM, temp, export, generated report, runtime, test, scheduler, or config file was deleted. No DB contents were inspected.

## Current Status Summary

Initial `git status --short` showed:

| Path | Status | Category | Recommended action |
|---|---|---|---|
| `.gitignore` | modified | MAYBE_TRACK | Safe to commit with this audit after review. |
| `analysis.db` | untracked | MUST_IGNORE | Ignore; do not stage. |
| `analysis.db.after_base_strength_change` | untracked | MUST_IGNORE | Ignore as local DB snapshot; do not stage. |
| `analysis.db.before_base_strength_change` | untracked | MUST_IGNORE | Ignore as local DB snapshot; do not stage. |
| `data/analysis.db-shm` | untracked | MUST_IGNORE | Ignore; do not stage or delete automatically. |
| `data/analysis.db-wal` | untracked | MUST_IGNORE | Ignore; do not stage or delete automatically. |
| `data/ecosystem_dashboard.db-shm` | untracked | MUST_IGNORE | Ignore; do not stage or delete automatically. |
| `data/ecosystem_dashboard.db-wal` | untracked | MUST_IGNORE | Ignore; do not stage or delete automatically. |
| `data/yf_cache/` | untracked | MUST_IGNORE | Ignore local cache. |
| `data_backup_2026-05-16/` | untracked | MUST_IGNORE | Ignore local backup directory; do not delete automatically. |
| `exports/` | untracked | MUST_IGNORE | Ignore generated exports. |
| `canonical_reports/` | untracked | MUST_IGNORE | Ignore generated reports. |
| `swing_reports/` | untracked | MUST_IGNORE | Ignore generated reports. |
| `temp/` | untracked | MUST_IGNORE | Ignore temp and backup artifacts; do not delete automatically. |
| `scheduler_config.json` | untracked | MUST_IGNORE | Ignore exact local scheduler config path. |
| `commit` | untracked | UNKNOWN | Leave unignored and untracked until user decides. |
| `scripts/recompute_divergence_all.py` | untracked | MAYBE_TRACK | Potential intentional script; leave unignored and untracked until user decides. |

After the `.gitignore` update, `git status --short` only reports the unrelated `.gitignore` change plus:

- `commit`
- `scripts/recompute_divergence_all.py`

Those two paths are intentionally not hidden by the new ignore rules.

## Existing `.gitignore` Assessment

Before this audit, `.gitignore` already ignored some artifact classes, including:

- `backups/`
- `venv/`
- Python caches
- `data/*.db`
- selected analysis outputs
- logs
- broad `*.csv`, with `!data/results.csv`
- broad artifact/report extensions such as `*.txt`, `*.xlsx`, and `*.html`

The previous unstaged `.gitignore` change added:

```gitignore
# Local API keys / environment overrides
.env.local
```

This is safe and useful, so it is preserved and included in this commit.

Gaps found:

- root-level local DB files such as `analysis.db` were not ignored.
- root-level DB snapshots such as `analysis.db.after_base_strength_change` were not ignored.
- SQLite WAL/SHM files were not ignored.
- SQLite backup files under non-`backups/` directories could remain visible.
- `temp/`, `exports/`, `canonical_reports/`, `swing_reports/`, `data/yf_cache/`, and `data_backup_*` were not ignored.
- exact local `scheduler_config.json` was not ignored.

## `.gitignore` Changes Made

Added safe local-artifact patterns:

```gitignore
*.db
*.db.*
*.db-*
*.sqlite
*.sqlite3
*.sqlite-wal
*.sqlite-shm
data/*.db-wal
data/*.db-shm
data/yf_cache/
temp/
exports/
canonical_reports/
swing_reports/
data_backup_*/
/scheduler_config.json
.env.local
```

Notes:

- No global `*.md` ignore was added, because documentation is a first-class tracked artifact in this repository.
- No new global `*.csv` ignore was added; one already exists, and tracked taxonomy CSV files remain tracked.
- `/scheduler_config.json` is exact-root only, so tracked smoke/sample scheduler config files are not hidden by this rule.
- Existing tracked files remain tracked even if a new ignore rule would match the same filename pattern.

## Representative Ignore Findings

Representative paths now ignored:

| Path | Matching rule |
|---|---|
| `analysis.db` | `*.db` |
| `analysis.db.after_base_strength_change` | `*.db.*` |
| `analysis.db.before_base_strength_change` | `*.db.*` |
| `data/analysis.db-wal` | `data/*.db-wal` |
| `data/analysis.db-shm` | `data/*.db-shm` |
| `data/ecosystem_dashboard.db-wal` | `data/*.db-wal` |
| `data/ecosystem_dashboard.db-shm` | `data/*.db-shm` |
| `data/yf_cache/` | `data/yf_cache/` |
| `data_backup_2026-05-16/` | `data_backup_*/` |
| `exports/` | `exports/` |
| `canonical_reports/` | `canonical_reports/` |
| `swing_reports/` | `swing_reports/` |
| `temp/` | `temp/` |
| `scheduler_config.json` | `/scheduler_config.json` |

Representative paths intentionally not ignored:

| Path | Reason |
|---|---|
| `scripts/recompute_divergence_all.py` | Could be an intentional script; requires user decision. |
| `commit` | Unknown local artifact; requires user decision. |

## Already Tracked But Risky

`git ls-files` found some already tracked paths that look potentially risky or artifact-like:

| Path/pattern | Current status | Category | Recommended action |
|---|---|---|---|
| `test.db` | tracked | ALREADY_TRACKED_BUT_RISKY | Do not remove in this step; review whether it is an intentional fixture. |
| `tmp_analysis.db` | tracked | ALREADY_TRACKED_BUT_RISKY | Do not remove in this step; review whether it is an intentional fixture. |
| `scheduler_config_smoke.json` | tracked | MAYBE_TRACK | Likely test/smoke fixture; keep unless separate review decides otherwise. |
| `data/datacenter_ecosystem_taxonomy_full_v1.csv` | tracked | MAYBE_TRACK | Intentional taxonomy source; keep. |
| `data/datacenter_ecosystem_taxonomy_v1.csv` | tracked | MAYBE_TRACK | Intentional taxonomy source; keep. |
| `docs/**/*.md`, root docs, archived docs | tracked | MAYBE_TRACK | Intentional documentation; keep. |
| `reports/test_summary.md` | tracked | MAYBE_TRACK | Could be a generated summary or intentional fixture; review separately if needed. |
| `venv/**/README.md` / license docs | tracked | ALREADY_TRACKED_BUT_RISKY | Virtualenv content is unusual in git; review separately, but do not remove here. |

## Safe Ignore Policy

- Ignore local DB files, DB snapshots, SQLite WAL/SHM files, SQLite backups, temp artifacts, exports, generated reports, logs, caches, and exact local machine config.
- Do not globally ignore Markdown files.
- Do not add broad source-file ignores.
- Avoid hiding possible intentional scripts.
- Keep fixtures explicit: if a test needs a DB fixture, place it intentionally and review whether a negation rule is needed.
- Existing tracked files should not be removed merely because a new ignore rule would match them.

## Do Not Delete Automatically

Never delete DBs, backups, WAL/SHM files, temp artifacts, exports, generated reports, or caches automatically in this repository. These files may be needed for rollback, audit, or local debugging.

## Recommended Later Cleanup Procedure

1. Verify noisy files are ignored with `git check-ignore -v <path>`.
2. Use `git status --short --ignored` only for visibility; do not use it as deletion approval.
3. Move or delete local artifacts only after explicit user approval.
4. Never use broad `git clean -fdx` in this repository.
5. If cleanup is ever needed, use targeted dry-run commands first, for example `git clean -n -- temp/ exports/`.
6. Only after reviewing the dry-run output should a targeted cleanup command be considered.

## Things Not Touched

- No DB files were deleted.
- No backup files were deleted.
- No WAL/SHM files were deleted.
- No export/temp/generated report files were deleted.
- No DB contents were inspected.
- No runtime code was changed.
- No tests were changed.
- No scheduler behavior or `scheduler_config.json` was changed.
- No current `dc_*`, `ec_*`, `ec_source_layer`, or legacy Datacenter behavior was changed.

## Recommended Next Step

Review the remaining untracked paths:

- `scripts/recompute_divergence_all.py`
- `commit`

If `scripts/recompute_divergence_all.py` is intentional, decide whether to add and test it in a separate code-focused change. If `commit` is accidental, remove it only after explicit user approval.

## Follow-up Resolution

Follow-up inspection resolved the two remaining untracked paths from the initial audit:

| Path | Decision | Reason | Action |
|---|---|---|---|
| `commit` | `ACCIDENTAL_REMOVE` | One-byte empty local artifact with no meaningful content. | Removed from working tree. |
| `scripts/recompute_divergence_all.py` | `NEEDS_REWORK_BEFORE_TRACK` | Potentially useful maintenance script, but it uses hard-coded `/home/kalle/projects/rawcandle/data/osakedata.db` and `/home/kalle/projects/rawcandle/data/analysis.db`, executes work at top level, lacks CLI guards/dry-run, and calls divergence recomputation with `only_missing=False`. | Left untracked; do not commit until rewritten with explicit CLI arguments, safe defaults, and dry-run/confirmation behavior. |

Safe check run:

- `python3 -m py_compile scripts/recompute_divergence_all.py`: passed.

Expected `git status --short` after this follow-up:

```text
?? scripts/recompute_divergence_all.py
```
