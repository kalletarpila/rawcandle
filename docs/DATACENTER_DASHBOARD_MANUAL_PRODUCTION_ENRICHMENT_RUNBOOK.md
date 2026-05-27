# Datacenter Dashboard Manual Production Enrichment Runbook

## 1. Purpose

This runbook defines the manual, operator-approved procedure for:

- backing up production `data/analysis.db`
- applying Datacenter dashboard enrichment schema/migrations manually
- running the first manual non-dry enrichment write
- auditing enrichment readiness
- exporting enrichment JSON
- building a dashboard from enrichment into controlled temporary outputs
- comparing against reports-mode reference outputs
- deciding whether later scheduler source-mode switch planning can proceed

This runbook does not:

- switch scheduler behavior
- remove reports mode
- remove `.md` reports
- authorize automatic production DB writes by scheduler


## 2. Scope and Non-Goals

This runbook is limited to a manual operator procedure outside scheduler.

Explicit non-goals:

- no automatic scheduler migration
- no scheduler source-mode switch
- no deletion of reports-mode outputs
- no deletion of existing dashboard snapshots
- no automatic production HTML replacement unless explicitly approved later


## 3. Required Preconditions

Before starting, confirm all of the following:

- git tracked worktree is clean
- latest relevant tests passed
- backup location is decided in advance
- production `analysis.db` path confirmed:
  - `/home/kalle/projects/rawcandle/data/analysis.db`
- price DB path confirmed:
  - `/home/kalle/projects/rawcandle/data/osakedata.db`
- dashboard DB path confirmed:
  - `/home/kalle/projects/rawcandle/data/ecosystem_dashboard.db`
- reports directory confirmed:
  - `/home/kalle/projects/rawcandle/swing_reports`
- watchlist file confirmed:
  - `/home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt`
- taxonomy version confirmed:
  - `DC_TAXONOMY_FULL_V1`
- target signal/report date selected
- reports-mode dashboard path still works


## 4. Safety Rule

Never run scheduler source-mode switch before all of the following are true:

- manual production enrichment write succeeds
- enrichment audit returns `READY`
- enrichment dashboard build succeeds
- acceptance report returns `blockers=0`
- reports fallback mode is verified


## 5. Backup Procedure

Backup must be created before any production migration or enrichment write.

Rules:

- backup directory must be outside `temp/`
- backup directory must not be committed to git
- do not rely on WAL/SHM files as the canonical backup
- if the DB may be open or using WAL mode, ensure no write is running before backup
- advanced checkpointing should only be used if it is already established project practice

Example:

```bash
cd /home/kalle/projects/rawcandle

TS="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="/home/kalle/projects/rawcandle/backups/manual_enrichment_${TS}"

mkdir -p "${BACKUP_DIR}"

cp /home/kalle/projects/rawcandle/data/analysis.db \
  "${BACKUP_DIR}/analysis.db.before_enrichment"

cp /home/kalle/projects/rawcandle/data/ecosystem_dashboard.db \
  "${BACKUP_DIR}/ecosystem_dashboard.db.before_enrichment"

ls -lh "${BACKUP_DIR}"
```


## 6. Migration Procedure

This step is manual, operator-approved, and modifies production `data/analysis.db`.

Scheduler must not run migrations automatically.

Verified migration mechanism:

- the project does not expose a separate standalone Datacenter enrichment migration CLI in the inspected code path
- tests and runtime both use `analysis.database_manager.DatabaseManager`
- `DatabaseManager.__init__(...)` calls `_init_database()`
- `_init_database()` calls `apply_datacenter_dashboard_enrichment_migration(conn)`
- `apply_datacenter_dashboard_enrichment_migration(conn)` applies:
  - `rawcandle/sqlite/migrations/002_create_datacenter_dashboard_enrichment.sql`
  - `rawcandle/sqlite/migrations/003_add_high_exit_risk_days_count_to_ticker_enrichment.sql` when the column is missing

Verified manual command:

```bash
PYTHONPATH=. python3 -c 'from analysis.database_manager import DatabaseManager; DatabaseManager("/home/kalle/projects/rawcandle/data/analysis.db").close()'
```

Operator interpretation:

- this uses the existing project migration/init code path
- this writes to production `data/analysis.db` if run
- this applies more than only the Datacenter enrichment migration:
  - it runs the broader `DatabaseManager` initialization/ensure logic for `analysis.db`
  - it also invokes other existing schema/migration helpers wired there
- the Datacenter enrichment migration helper itself is idempotent in tests
- the command must be treated as a write operation
- no other process should be writing to `analysis.db` while this runs

After migration, verify schema and enrichment table availability with audit:

```bash
PYTHONPATH=. python3 dev_tools/run_datacenter_dashboard_enrichment_audit.py \
  --analysis-db /home/kalle/projects/rawcandle/data/analysis.db \
  --signal-date <YYYY-MM-DD> \
  --taxonomy-version DC_TAXONOMY_FULL_V1
```

Expected immediately after migration but before enrichment write:

- expected enrichment tables exist
- row counts may be `0`
- readiness is likely `EMPTY`
- status is `OK`

If the audit reports `MISSING_TABLES`, stop.


## 7. Manual Non-Dry Enrichment Write

Run the enrichment write only after backup and migration verification.

Command:

```bash
PYTHONPATH=. python3 dev_tools/run_datacenter_dashboard_enrichment_write.py \
  --analysis-db /home/kalle/projects/rawcandle/data/analysis.db \
  --signal-date <YYYY-MM-DD> \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --mode replace-date \
  --watchlist-file /home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt
```

Important notes:

- this writes enrichment rows into production `data/analysis.db`
- this does not write `ecosystem_dashboard.db`
- this does not render HTML
- this does not run scheduler
- `replace-date` rebuilds one `signal_date + taxonomy_version` deterministically


## 8. Post-Write Audit

Audit immediately after the enrichment write:

```bash
PYTHONPATH=. python3 dev_tools/run_datacenter_dashboard_enrichment_audit.py \
  --analysis-db /home/kalle/projects/rawcandle/data/analysis.db \
  --signal-date <YYYY-MM-DD> \
  --taxonomy-version DC_TAXONOMY_FULL_V1
```

Expected after a successful write:

- `ticker_enrichment READY`
- `group_enrichment READY`
- `action_summary READY`
- `decision_trace READY`
- `enrichment_run READY`
- `overall READY`
- `status OK`

If readiness is `PARTIAL`, `EMPTY`, or `MISSING_TABLES`, stop and diagnose before export/build.


## 9. Export Enrichment JSON

Export the enrichment dashboard input JSON:

```bash
PYTHONPATH=. python3 dev_tools/run_datacenter_dashboard_analysis_db_export.py \
  --analysis-db /home/kalle/projects/rawcandle/data/analysis.db \
  --price-db /home/kalle/projects/rawcandle/data/osakedata.db \
  --ecosystem-code DATACENTER \
  --report-date <YYYY-MM-DD> \
  --source-mode enrichment \
  --output-json /home/kalle/projects/rawcandle/temp/datacenter_dashboard_enrichment_export_<YYYY-MM-DD>.json
```

Notes:

- this reads production `analysis.db`
- this writes only JSON to `temp/`
- this does not write `ecosystem_dashboard.db`
- this does not render HTML
- the output file is temporary and must not be committed


## 10. Build Controlled Enrichment Dashboard DB and HTML

Build to controlled temporary outputs first. Do not overwrite production dashboard DB in this step.

```bash
PYTHONPATH=. python3 dev_tools/run_datacenter_dashboard_build.py \
  --dashboard-db /home/kalle/projects/rawcandle/temp/manual_enrichment_dashboard_<YYYY-MM-DD>.db \
  --report-date <YYYY-MM-DD> \
  --input-mode structured \
  --structured-input-json /home/kalle/projects/rawcandle/temp/datacenter_dashboard_enrichment_export_<YYYY-MM-DD>.json \
  --mode replace-date \
  --render-html \
  --html-output /home/kalle/projects/rawcandle/temp/manual_enrichment_dashboard_<YYYY-MM-DD>.html
```

Important:

- this is a controlled temporary build
- this is not production `ecosystem_dashboard.db`
- this is not scheduler output
- production dashboard DB should only be written after explicit approval


## 11. Build Reports Reference Dashboard

Build a reports-mode reference snapshot into separate temporary outputs:

```bash
PYTHONPATH=. python3 dev_tools/run_datacenter_dashboard_build.py \
  --dashboard-db /home/kalle/projects/rawcandle/temp/manual_reports_dashboard_<YYYY-MM-DD>.db \
  --report-date <YYYY-MM-DD> \
  --input-mode reports \
  --reports-dir /home/kalle/projects/rawcandle/swing_reports \
  --mode replace-date \
  --render-html \
  --html-output /home/kalle/projects/rawcandle/temp/manual_reports_dashboard_<YYYY-MM-DD>.html
```

Notes:

- this uses the reports-mode reference path
- this writes only temporary DB/HTML
- this does not modify production `ecosystem_dashboard.db`


## 12. Acceptance Report

Run acceptance using the temporary dashboard DBs:

```bash
PYTHONPATH=. python3 dev_tools/run_datacenter_dashboard_enrichment_acceptance_report.py \
  --ecosystem-code DATACENTER \
  --report-date <YYYY-MM-DD> \
  --reports-dashboard-db /home/kalle/projects/rawcandle/temp/manual_reports_dashboard_<YYYY-MM-DD>.db \
  --reports-run-id <reports_run_id> \
  --enrichment-dashboard-db /home/kalle/projects/rawcandle/temp/manual_enrichment_dashboard_<YYYY-MM-DD>.db \
  --enrichment-run-id <enrichment_run_id> \
  --analysis-db-copy /home/kalle/projects/rawcandle/data/analysis.db \
  --max-examples 50
```

Clarifications:

- run IDs must come from the build `SUMMARY` lines
- using production `analysis.db` as `--analysis-db-copy` is acceptable here because the acceptance report is read-only
- the argument name is historical from temp-copy smoke tooling
- the acceptance report must not mutate DBs


## 13. Optional Parity Diagnostics

If the acceptance report needs explanation, optional read-only diagnostics can be run:

```bash
PYTHONPATH=. python3 dev_tools/run_datacenter_dashboard_enrichment_parity_diagnosis.py \
  --ecosystem-code DATACENTER \
  --report-date <YYYY-MM-DD> \
  --reports-dashboard-db /home/kalle/projects/rawcandle/temp/manual_reports_dashboard_<YYYY-MM-DD>.db \
  --reports-run-id <reports_run_id> \
  --enrichment-dashboard-db /home/kalle/projects/rawcandle/temp/manual_enrichment_dashboard_<YYYY-MM-DD>.db \
  --enrichment-run-id <enrichment_run_id> \
  --analysis-db-copy /home/kalle/projects/rawcandle/data/analysis.db \
  --max-examples 100
```

These diagnostics are optional and read-only.


## 14. Acceptance Criteria

Minimum criteria before later scheduler source-mode decisions:

- backup exists
- migration/audit confirms enrichment tables exist
- enrichment write status is `OK`
- enrichment audit overall status is `READY`
- enrichment export status is `OK`
- temporary enrichment dashboard build status is `OK`
- temporary reports reference dashboard build status is `OK`
- acceptance report status is `OK`
- acceptance report `blockers=0`
- visual HTML review is acceptable
- reports fallback build still succeeds
- expected known differences are understood:
  - `CRGY` outside ecosystem, if still applicable
  - extra `market_map` groups, if still present
  - verbose enrichment trace V0
  - small action residuals, if still present


## 15. Rollback Procedure

Normal rollback posture:

- scheduler remains in reports mode, so scheduler rollback should not be required
- leave enrichment tables and rows in `analysis.db` for audit unless there is a specific reason to remove them
- do not delete `ecosystem_dashboard.db` snapshots
- regenerate reports-mode temporary or production HTML through the existing reports-mode path if needed

If production `analysis.db` must be restored:

```bash
# Stop any process that may write to analysis.db before doing this.

cp "${BACKUP_DIR}/analysis.db.before_enrichment" \
  /home/kalle/projects/rawcandle/data/analysis.db
```

If production `ecosystem_dashboard.db` must be restored:

```bash
cp "${BACKUP_DIR}/ecosystem_dashboard.db.before_enrichment" \
  /home/kalle/projects/rawcandle/data/ecosystem_dashboard.db
```

Cautions:

- restore only after explicit approval
- make sure no scheduler/update process is writing
- do not restore over a live write


## 16. Next Stage After Successful Manual Procedure

Planned follow-ups after successful manual execution:

- `DB-17h`
  - scheduler config update proposal for enrichment source mode, still disabled by default
- `DB-17i`
  - scheduler enrichment source-mode local fake/dry run using temporary DBs
- `DB-17j`
  - explicit approval before production source-mode switch
- `DB-17k`
  - first production scheduler enrichment run with fallback enabled, if approved


## 17. Explicit Operator Checklist

- git tracked worktree clean
- backup created
- migration command verified
- migration applied to production `analysis.db`
- enrichment audit after migration checked
- enrichment write run
- enrichment audit `READY`
- enrichment JSON exported
- temporary enrichment dashboard DB/HTML built
- temporary reports reference DB/HTML built
- acceptance report `blockers=0`
- visual HTML review completed
- reports fallback path verified
- decision made whether to proceed to scheduler source-mode planning
