# Report Canonical V2 Real-Data Parity Smoke

## 1. Purpose

This workflow validates factual/content parity between:

- current in-memory daily/rolling report-builder outputs
- canonical Report V2 context/classification outputs

The workflow uses a real analysis database copied to a temporary database, then runs:

1. Report Canonical V2 migrations on the temp DB
2. Report Canonical V2 orchestrator on the temp DB
3. Report Canonical V2 parity audit CLI on the temp DB

The parity target is classification and report-content semantics, not formatting, row order, section order, Markdown layout, or CSV layout.

## 2. Safety Rules

- Never write to `/home/kalle/projects/rawcandle/data/analysis.db`.
- Always use a temp DB under `/home/kalle/projects/rawcandle/temp/`.
- Use SQLite `backup(...)`, not plain `cp`.
- Do not run dashboard logic.
- Do not run scheduler logic.
- Do not run stock-update logic.
- Do not render reports.
- Do not parse report files.
- Treat mismatches as factual differences until proven otherwise.

## 3. Required Inputs

Known successful example:

- Source DB:
  `/home/kalle/projects/rawcandle/data/analysis.db`
- Temp DB:
  `/home/kalle/projects/rawcandle/temp/analysis_report_canonical_v2_smoke_2026-05-29.db`
- Signal date:
  `2026-05-29`
- Taxonomy version:
  `DC_TAXONOMY_FULL_V1`
- Horizons:
  `daily,rolling2,rolling5,rolling30`

## 4. Source Preflight Commands

Verify required source rows exist before creating the temp copy.

```bash
sqlite3 /home/kalle/projects/rawcandle/data/analysis.db "
SELECT COUNT(*) FROM dc_ticker_swing_signal_daily
WHERE signal_date = '2026-05-29'
  AND taxonomy_version = 'DC_TAXONOMY_FULL_V1';
"

sqlite3 /home/kalle/projects/rawcandle/data/analysis.db "
SELECT COUNT(*) FROM dc_group_swing_signal_daily
WHERE signal_date = '2026-05-29'
  AND taxonomy_version = 'DC_TAXONOMY_FULL_V1';
"

sqlite3 /home/kalle/projects/rawcandle/data/analysis.db "
SELECT COUNT(*) FROM dc_group_synthetic_ohlc_daily
WHERE ohlc_date = '2026-05-29'
  AND taxonomy_version = 'DC_TAXONOMY_FULL_V1';
"
```

Expected successful example counts:

- ticker: `236`
- group: `54`
- synthetic: `53`

Stop if any required source count is unexpectedly zero.

## 5. SQLite Backup Copy Command

Do not use `cp`. Use SQLite `backup(...)` so the temp copy is consistent in this environment.

```bash
mkdir -p /home/kalle/projects/rawcandle/temp

PYTHONPATH=. python3 - <<'PY'
import sqlite3

src = "/home/kalle/projects/rawcandle/data/analysis.db"
dst = "/home/kalle/projects/rawcandle/temp/analysis_report_canonical_v2_smoke_2026-05-29.db"

source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
target = sqlite3.connect(dst)
try:
    source.backup(target)
    target.commit()
finally:
    target.close()
    source.close()
PY
```

Optional read-only verification after backup:

```bash
sqlite3 /home/kalle/projects/rawcandle/temp/analysis_report_canonical_v2_smoke_2026-05-29.db "
SELECT name
FROM sqlite_master
WHERE type='table'
  AND name IN ('dc_group_swing_signal_daily', 'dc_group_synthetic_ohlc_daily', 'dc_ticker_swing_signal_daily')
ORDER BY name;
"
```

## 6. Apply V2 Migrations to Temp DB

Use the existing migration helper:

- `rawcandle.report_canonical_v2_migration.apply_report_canonical_v2_migration`

```bash
PYTHONPATH=. python3 - <<'PY'
import sqlite3
from rawcandle.report_canonical_v2_migration import apply_report_canonical_v2_migration

db = "/home/kalle/projects/rawcandle/temp/analysis_report_canonical_v2_smoke_2026-05-29.db"
conn = sqlite3.connect(db)
try:
    apply_report_canonical_v2_migration(conn)
    conn.commit()
finally:
    conn.close()
PY
```

Optional verification:

```bash
sqlite3 /home/kalle/projects/rawcandle/temp/analysis_report_canonical_v2_smoke_2026-05-29.db "
SELECT name
FROM sqlite_master
WHERE type='table'
  AND name IN (
    'dc_report_run_v2',
    'dc_report_context_group_v2',
    'dc_report_context_daily_v2',
    'dc_report_context_window_v2',
    'dc_report_classification_v2'
  )
ORDER BY name;
"
```

## 7. Run V2 Orchestrator on Temp DB

Use:

- `analysis.datacenter_indices.report_canonical_v2_orchestrator.run_report_canonical_v2`

```bash
PYTHONPATH=. python3 - <<'PY'
import sqlite3
from analysis.datacenter_indices.report_canonical_v2_orchestrator import run_report_canonical_v2

db = "/home/kalle/projects/rawcandle/temp/analysis_report_canonical_v2_smoke_2026-05-29.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
try:
    summary = run_report_canonical_v2(
        conn,
        signal_date="2026-05-29",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="REPORT_CANONICAL_V2_SMOKE_2026_05_29",
        horizons=("daily", "rolling2", "rolling5", "rolling30"),
        created_at_utc="2026-05-29T00:00:00Z",
        notes="Temp-copy real-data canonical V2 smoke run",
    )
    conn.commit()
    print(summary)
finally:
    conn.close()
PY
```

Successful example V2 output row counts:

- run: `1`
- group context: `216`
- daily context: `236`
- window context: `708`
- classification: `1180`

## 8. Run Parity Audit CLI on Temp DB

```bash
PYTHONPATH=. python3 dev_tools/run_report_canonical_v2_parity_audit.py \
  --db /home/kalle/projects/rawcandle/temp/analysis_report_canonical_v2_smoke_2026-05-29.db \
  --signal-date 2026-05-29 \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --horizons daily,rolling2,rolling5,rolling30 \
  --format text
```

Expected success condition:

```text
SUMMARY status=OK
SUMMARY mismatch_count=0
```

## 9. If Mismatches Appear

Do not fix immediately.

Procedure:

1. Take the first mismatch line exactly as printed.
2. Run a DB-V2-14-style read-only root-cause inspection for that mismatch family.
3. Classify the root cause before any code changes.

Typical root-cause categories:

- `CURRENT_EXTRACTION_BUG`
- `V2_CONTEXT_BUILDER_BUG`
- `V2_CLASSIFICATION_WRITER_BUG`
- `MISSING_CANONICAL_INPUT`
- `PARITY_AUDIT_MAPPING_BUG`
- `REAL_PARITY_BUG_UNCLASSIFIED`

## 10. Last Known Successful Smoke

- Signal date:
  `2026-05-29`
- Taxonomy version:
  `DC_TAXONOMY_FULL_V1`
- Source row counts:
  - ticker: `236`
  - group: `54`
  - synthetic: `53`
- V2 output row counts:
  - run: `1`
  - group context: `216`
  - daily context: `236`
  - window context: `708`
  - classification: `1180`
- Final parity:
  - `SUMMARY status=OK`
  - `SUMMARY mismatch_count=0`
- Commit containing the parity fix that resolved the daily BUY_WATCH near-pullback mismatch:
  `66972d69e38eb668cab72e502b71aa9597826169`

## Notes

- The original failing real-data smoke exposed daily BUY_WATCH mismatches caused by a missing canonical input:
  `distance_to_ema10_pct`
- That issue was fixed before the successful smoke above.
- The workflow should continue to use SQLite `backup(...)` for temp-copy creation in this environment.
