# Canonical Report V2 Production Build Runbook

## 1. Purpose

This runbook documents the future safe procedure for:

- backing up production `analysis.db`
- applying canonical V2 migrations if needed
- running canonical V2 orchestrator
- running parity audit
- rendering canonical V2 outputs
- verifying results

Important boundaries:

- this is not a default report replacement
- this does not change legacy daily/rolling report paths
- this should be run manually and deliberately
- canonical outputs remain opt-in

## 2. Current Known Production State

Read-only findings from DB-V2-58:

- production DB: `/home/kalle/projects/rawcandle/data/analysis.db`
- source tables exist:
  - `dc_ticker_swing_signal_daily`
  - `dc_group_swing_signal_daily`
  - `dc_group_synthetic_ohlc_daily`
- known source counts for `2026-05-29 / DC_TAXONOMY_FULL_V1`:
  - ticker rows: `236`
  - group rows: `54`
  - synthetic rows: `53`
- canonical V2 schema exists:
  - `dc_report_run_v2`
  - `dc_report_context_group_v2`
  - `dc_report_context_daily_v2`
  - `dc_report_context_window_v2`
  - `dc_report_classification_v2`
- canonical V2 tables currently have zero rows
- current state: `V2_SCHEMA_PRESENT_NO_ROWS`

## 3. Critical Data Model Warning

Canonical V2 context/classification tables are not an archive of many parallel runs.

Key constraint:

- primary keys are defined by date/taxonomy/horizon/entity/classification-type grain
- `run_id` is metadata and traceability, not a duplicate-row version key
- before building production rows, check whether rows already exist for the target date/taxonomy
- if rows already exist, decide explicitly whether to replace that slice or stop
- do not create stale or mixed canonical slices for the same date/taxonomy

## 4. Preflight Checklist

- `[` `]` confirm DB path is `/home/kalle/projects/rawcandle/data/analysis.db`
- `[` `]` confirm DB file exists and size is greater than zero
- `[` `]` confirm required source tables exist
- `[` `]` confirm source counts for the selected date/taxonomy are non-zero
- `[` `]` confirm V2 tables exist or the migration plan is clear
- `[` `]` check whether V2 rows already exist for the selected date/taxonomy
- `[` `]` choose explicit production `run_id`
- `[` `]` prepare backup path
- `[` `]` prepare parity audit command
- `[` `]` prepare rollback plan
- `[` `]` confirm no scheduler/dashboard/default-report changes are involved

## 5. Step 1 — Backup Production DB

`DO NOT RUN WITHOUT USER CONFIRMATION`

Use SQLite `backup(...)`, not plain `cp`.

```bash
mkdir -p /home/kalle/projects/rawcandle/temp

PYTHONPATH=. python3 - <<'PY'
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

source = Path("/home/kalle/projects/rawcandle/data/analysis.db")
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
target = Path(f"/home/kalle/projects/rawcandle/temp/analysis.db.backup.{stamp}.sqlite")

src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
dst = sqlite3.connect(str(target))
try:
    src.backup(dst)
    dst.commit()
finally:
    dst.close()
    src.close()

print(target)
PY

test -s /home/kalle/projects/rawcandle/temp/analysis.db.backup.<TIMESTAMP>.sqlite
```

Backup verification requirement:

- backup file exists
- backup file size is greater than zero

## 6. Step 2 — Read-only Preflight Queries

Known example target:

- signal date: `2026-05-29`
- taxonomy version: `DC_TAXONOMY_FULL_V1`

```bash
PYTHONPATH=. python3 - <<'PY'
import sqlite3

db = "/home/kalle/projects/rawcandle/data/analysis.db"
conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
try:
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }

    required_source = {
        "dc_ticker_swing_signal_daily",
        "dc_group_swing_signal_daily",
        "dc_group_synthetic_ohlc_daily",
    }
    required_v2 = {
        "dc_report_run_v2",
        "dc_report_context_group_v2",
        "dc_report_context_daily_v2",
        "dc_report_context_window_v2",
        "dc_report_classification_v2",
    }

    print("SOURCE_TABLES_OK", required_source.issubset(tables))
    print("V2_TABLES_OK", required_v2.issubset(tables))

    print(
        "SOURCE_TICKER_ROWS",
        conn.execute(
            """
            SELECT COUNT(*) FROM dc_ticker_swing_signal_daily
            WHERE signal_date = '2026-05-29'
              AND taxonomy_version = 'DC_TAXONOMY_FULL_V1'
            """
        ).fetchone()[0],
    )
    print(
        "SOURCE_GROUP_ROWS",
        conn.execute(
            """
            SELECT COUNT(*) FROM dc_group_swing_signal_daily
            WHERE signal_date = '2026-05-29'
              AND taxonomy_version = 'DC_TAXONOMY_FULL_V1'
            """
        ).fetchone()[0],
    )
    print(
        "SOURCE_SYNTHETIC_ROWS",
        conn.execute(
            """
            SELECT COUNT(*) FROM dc_group_synthetic_ohlc_daily
            WHERE ohlc_date = '2026-05-29'
              AND taxonomy_version = 'DC_TAXONOMY_FULL_V1'
            """
        ).fetchone()[0],
    )

    for table in sorted(required_v2):
        print(table, conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    print(
        "RUN_ROWS_FOR_TARGET",
        conn.execute(
            """
            SELECT COUNT(*) FROM dc_report_run_v2
            WHERE signal_date = '2026-05-29'
              AND taxonomy_version = 'DC_TAXONOMY_FULL_V1'
            """
        ).fetchone()[0],
    )
    print(
        "GROUP_ROWS_FOR_TARGET",
        conn.execute(
            """
            SELECT COUNT(*) FROM dc_report_context_group_v2
            WHERE signal_date = '2026-05-29'
              AND taxonomy_version = 'DC_TAXONOMY_FULL_V1'
            """
        ).fetchone()[0],
    )
    print(
        "DAILY_ROWS_FOR_TARGET",
        conn.execute(
            """
            SELECT COUNT(*) FROM dc_report_context_daily_v2
            WHERE signal_date = '2026-05-29'
              AND taxonomy_version = 'DC_TAXONOMY_FULL_V1'
            """
        ).fetchone()[0],
    )
    print(
        "WINDOW_ROWS_FOR_TARGET",
        conn.execute(
            """
            SELECT COUNT(*) FROM dc_report_context_window_v2
            WHERE signal_date = '2026-05-29'
              AND taxonomy_version = 'DC_TAXONOMY_FULL_V1'
            """
        ).fetchone()[0],
    )
    print(
        "CLASSIFICATION_ROWS_FOR_TARGET",
        conn.execute(
            """
            SELECT COUNT(*) FROM dc_report_classification_v2
            WHERE signal_date = '2026-05-29'
              AND taxonomy_version = 'DC_TAXONOMY_FULL_V1'
            """
        ).fetchone()[0],
    )
finally:
    conn.close()
PY
```

## 7. Step 3 — Apply Canonical V2 Migrations

`DO NOT RUN WITHOUT BACKUP CONFIRMED`

Use:

- `rawcandle.report_canonical_v2_migration.apply_report_canonical_v2_migration(conn)`

The helper applies or repairs:

- `004`
- `005`
- `006`
- `007`
- `008`

Important notes:

- `008` partial schema repair is handled per-column
- migrations must run only after backup is confirmed
- this step performs schema writes if needed

```bash
PYTHONPATH=. python3 - <<'PY'
import sqlite3
from rawcandle.report_canonical_v2_migration import apply_report_canonical_v2_migration

db = "/home/kalle/projects/rawcandle/data/analysis.db"
conn = sqlite3.connect(db)
try:
    apply_report_canonical_v2_migration(conn)
    conn.commit()
finally:
    conn.close()
PY
```

## 8. Step 4 — Run Canonical V2 Orchestrator

`DO NOT RUN WITHOUT BACKUP AND PREFLIGHT`

Use:

- `analysis.datacenter_indices.report_canonical_v2_orchestrator.run_report_canonical_v2(...)`

Known first production-build candidate:

- DB: `/home/kalle/projects/rawcandle/data/analysis.db`
- signal date: `2026-05-29`
- taxonomy version: `DC_TAXONOMY_FULL_V1`
- run id: `REPORT_CANONICAL_V2_PROD_BUILD_2026_05_29`
- horizons: `daily`, `rolling2`, `rolling5`, `rolling30`
- created_at_utc: `2026-05-29T00:00:00Z`

```bash
PYTHONPATH=. python3 - <<'PY'
import sqlite3
from analysis.datacenter_indices.report_canonical_v2_orchestrator import run_report_canonical_v2

db = "/home/kalle/projects/rawcandle/data/analysis.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
try:
    summary = run_report_canonical_v2(
        conn,
        signal_date="2026-05-29",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="REPORT_CANONICAL_V2_PROD_BUILD_2026_05_29",
        horizons=("daily", "rolling2", "rolling5", "rolling30"),
        created_at_utc="2026-05-29T00:00:00Z",
        notes="Production canonical V2 build for controlled manual run",
    )
    conn.commit()
    print(summary)
finally:
    conn.close()
PY
```

Expected row counts for the known `2026-05-29` smoke target:

- run rows: `1`
- group context rows: `216`
- daily context rows: `236`
- window context rows: `708`
- classification rows: `1180`

These are expected for the known accepted smoke target, not universal constants.

## 9. Step 5 — Run Parity Audit

Use:

- `dev_tools/run_report_canonical_v2_parity_audit.py`

```bash
PYTHONPATH=. python3 dev_tools/run_report_canonical_v2_parity_audit.py \
  --db /home/kalle/projects/rawcandle/data/analysis.db \
  --signal-date 2026-05-29 \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --horizons daily,rolling2,rolling5,rolling30 \
  --format text
```

Expected for the known target:

- `SUMMARY status=OK`
- `SUMMARY mismatch_count=0`

If parity is not OK:

- stop
- do not treat outputs as trusted
- do not attempt broad repair
- open a narrow follow-up diagnosis task first

## 10. Step 6 — Render Canonical Output

Use:

- `dev_tools/run_report_canonical_v2_output.py`

Example rolling30 CSV render:

```bash
PYTHONPATH=. python3 dev_tools/run_report_canonical_v2_output.py \
  --db /home/kalle/projects/rawcandle/data/analysis.db \
  --signal-date 2026-05-29 \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --run-id REPORT_CANONICAL_V2_PROD_BUILD_2026_05_29 \
  --horizon rolling30 \
  --format csv \
  --require-parity-ok \
  --output /home/kalle/projects/rawcandle/temp/datacenter_rolling30_canonical_v2_prod_2026-05-29.csv \
  --summary-output /home/kalle/projects/rawcandle/temp/datacenter_rolling30_canonical_v2_prod_2026-05-29.summary.txt
```

Clarifications:

- this output CLI is read-only
- it does not run migrations
- it does not run orchestrator
- it does not replace legacy outputs

## 11. Step 7 — Post-build All-output Verification

Safer verification path:

- run `dev_tools/run_report_canonical_v2_all_outputs_smoke.py`
- source DB is production DB opened read-only
- the tool creates a fresh temp DB via SQLite `backup(...)`
- the tool applies migrations/orchestrator to temp only
- the tool emits all 8 outputs to a temp output dir

Why this is safer:

- it keeps verification writes out of production
- it reuses the accepted release-gate path
- it reduces the chance of mixing production canonical slices with verification-only work

## 12. Rollback Plan

Rollback options:

- if only V2 rows were written and source tables are untouched:
  - restore the entire DB from backup, or
  - use a separately approved, narrowly scoped cleanup task later if row-level cleanup is preferred
- if schema migration caused the issue:
  - restore from backup is safest

Rules:

- never manually edit source tables as part of rollback
- do not improvise destructive cleanup during the first production build

## 13. Risks and Mitigations

- migration error  
  mitigation: confirm backup first, keep the helper invocation isolated, verify post-migration schema before building rows

- partial schema state  
  mitigation: run read-only schema checks first and rely on the migration helper’s guarded `004` through `008` behavior, including `008` per-column repair

- duplicate or stale `run_id`  
  mitigation: choose a unique production `run_id` and check for an existing run row before building

- existing V2 rows for target date/taxonomy  
  mitigation: check row presence for the target slice before writing and explicitly decide whether to stop or rebuild that authoritative slice

- parity mismatch  
  mitigation: require parity audit immediately after build and stop on non-OK

- accidental source-table write  
  mitigation: limit write steps strictly to migration helper and orchestrator; do not run unrelated code paths

- confusion between canonical output and default report replacement  
  mitigation: keep canonical outputs under separate `canonical_v2` filenames and continue documenting canonical output as opt-in only

## 14. Current Non-goals

- no default report path replacement
- no legacy layout parity guarantee
- no byte-for-byte CSV parity guarantee
- no dashboard integration
- no scheduler integration
- no automatic production build
- no automatic cleanup of old V2 rows

## 15. Recommended First Production Build Candidate

Recommended first controlled manual build candidate:

- date: `2026-05-29`
- taxonomy version: `DC_TAXONOMY_FULL_V1`
- run id: `REPORT_CANONICAL_V2_PROD_BUILD_2026_05_29`

Why this candidate:

- it was already used in all accepted temp-copy smokes
- source counts for that date/taxonomy are known
- parity for that target is already known to be green in temp DB
