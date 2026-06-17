# Datacenter Dashboard Manual Production Enrichment Runbook

## 1. Purpose

This runbook documents the manual Datacenter dashboard enrichment production-write path using `dev_tools` only.

It is intentionally not the full scheduler path.

This procedure:

- does not run scheduler
- does not run `rawcandle/cli/run_stock_update_scheduler.py`
- does not run Yahoo/OHLCV/stock update work
- writes production `data/analysis.db`
- writes production `data/ecosystem_dashboard.db`
- writes production dashboard HTML under `swing_reports/`

Scheduler switch remains a separate operator decision. See [DATACENTER_DASHBOARD_SCHEDULER_SWITCH_PLAN.md](/home/kalle/projects/rawcandle/docs/DATACENTER_DASHBOARD_SCHEDULER_SWITCH_PLAN.md).


## 2. When To Use This Runbook

Use this runbook when:

- Datacenter reports already exist for the target report date
- `analysis.db` source tables are already available
- the operator wants to update dashboard output from enrichment without running stock update
- scheduler execution would be too slow or would trigger Yahoo/OHLCV work

Do not use this runbook when:

- Datacenter source reports are missing
- enrichment audit tables are missing
- the operator wants to update OHLCV data
- full scheduler behavior is being tested


## 3. Preconditions

Before starting, confirm all of the following:

- tracked git worktree is clean
- required files and directories exist:
  - `/home/kalle/projects/rawcandle/data/analysis.db`
  - `/home/kalle/projects/rawcandle/data/osakedata.db`
  - `/home/kalle/projects/rawcandle/data/ecosystem_dashboard.db`
  - `/home/kalle/projects/rawcandle/swing_reports`
  - `/home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt`
- target report date Datacenter reports exist:
  - daily
  - rolling `2d`
  - rolling `5d`
  - rolling `30d`
  - weekly if relevant
- `datacenter_enrichment_apply_migrations=false`
- scheduler is not part of this procedure


## 4. Backup Procedure

Create backups before any production write:

```bash
cd /home/kalle/projects/rawcandle

BACKUP_DIR="/home/kalle/projects/rawcandle/backups/dashboard_prod_write_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"

cp /home/kalle/projects/rawcandle/data/analysis.db "$BACKUP_DIR/analysis.db.before_manual_dashboard_write"
cp /home/kalle/projects/rawcandle/data/ecosystem_dashboard.db "$BACKUP_DIR/ecosystem_dashboard.db.before_manual_dashboard_write"

stat -c '%n|%s|%Y' \
  /home/kalle/projects/rawcandle/data/analysis.db \
  /home/kalle/projects/rawcandle/data/ecosystem_dashboard.db
```

Operational notes:

- do not delete backups
- do not commit backups
- if backup or `stat` fails, stop before any write


## 5. Manual Dev-Tool Production Write Sequence

Use these variables:

```bash
REPORT_DATE=YYYY-MM-DD
TAXONOMY_VERSION=DC_TAXONOMY_FULL_V1
```

### A. Pre-Write Audit

```bash
PYTHONPATH=. python3 dev_tools/run_datacenter_dashboard_enrichment_audit.py \
  --analysis-db /home/kalle/projects/rawcandle/data/analysis.db \
  --signal-date "${REPORT_DATE}" \
  --taxonomy-version "${TAXONOMY_VERSION}"
```

Capture:

- `status`
- `readiness`
- `missing_tables`
- existing row counts if printed

Stop if `missing_tables > 0`.

### B. Enrichment Write

```bash
PYTHONPATH=. python3 dev_tools/run_datacenter_dashboard_enrichment_write.py \
  --analysis-db /home/kalle/projects/rawcandle/data/analysis.db \
  --signal-date "${REPORT_DATE}" \
  --taxonomy-version "${TAXONOMY_VERSION}" \
  --mode replace-date \
  --watchlist-file /home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt \
  --use-upstream-rolling5-pullback \
  --pullback-lookback-rows 5
```

Capture:

- `status`
- `readiness`
- `ticker_rows`
- `group_rows`
- `action_summary_rows`
- `decision_trace_rows`
- `ticker_decision_updated_rows`
- `rolling5_classifier_source`
- `rolling5_classifier_rows`
- `ma_break_helper_rows`
- `ma_break_payload_rows`
- `freshness_helper_rows`
- `freshness_payload_rows`
- `rolling2_helper_rows`
- `rolling2_payload_rows`
- `rolling30_helper_rows`
- `rolling30_payload_rows`
- `run_id`

Stop if write `status` is not `OK`.

### C. Post-Write Audit

```bash
PYTHONPATH=. python3 dev_tools/run_datacenter_dashboard_enrichment_audit.py \
  --analysis-db /home/kalle/projects/rawcandle/data/analysis.db \
  --signal-date "${REPORT_DATE}" \
  --taxonomy-version "${TAXONOMY_VERSION}"
```

Expected:

- `status=OK`
- `readiness=READY`

Stop if post-write readiness is not `READY`.

### D. Export Enrichment JSON To `temp/`

```bash
PYTHONPATH=. python3 dev_tools/run_datacenter_dashboard_analysis_db_export.py \
  --analysis-db /home/kalle/projects/rawcandle/data/analysis.db \
  --price-db /home/kalle/projects/rawcandle/data/osakedata.db \
  --ecosystem-code DATACENTER \
  --report-date "${REPORT_DATE}" \
  --source-mode enrichment \
  --output-json /home/kalle/projects/rawcandle/temp/datacenter_dashboard_enrichment_export_${REPORT_DATE}_production_dashboard_write.json
```

Capture:

- `status`
- `source_mode`
- `readiness`
- `source_reports`
- `action_summary`
- `market_map`
- `watchlist`
- `tickers`
- `decision_trace`

### E. Build Production Enrichment Dashboard DB And HTML

This is the intentional production dashboard write:

```bash
PYTHONPATH=. python3 dev_tools/run_datacenter_dashboard_build.py \
  --dashboard-db /home/kalle/projects/rawcandle/data/ecosystem_dashboard.db \
  --report-date "${REPORT_DATE}" \
  --input-mode structured \
  --structured-input-json /home/kalle/projects/rawcandle/temp/datacenter_dashboard_enrichment_export_${REPORT_DATE}_production_dashboard_write.json \
  --mode replace-date \
  --render-html \
  --html-output /home/kalle/projects/rawcandle/swing_reports/datacenter_dashboard_${REPORT_DATE}.html
```

Capture:

- `run_id`
- `status`
- `readiness`
- counts
- HTML render status if printed

Stop if build `status` is not `OK`.

### F. Build Temp Reports Reference Dashboard

This build exists only for acceptance comparison:

```bash
PYTHONPATH=. python3 dev_tools/run_datacenter_dashboard_build.py \
  --dashboard-db /home/kalle/projects/rawcandle/temp/manual_reports_dashboard_${REPORT_DATE}_production_dashboard_write_reference.db \
  --report-date "${REPORT_DATE}" \
  --input-mode reports \
  --reports-dir /home/kalle/projects/rawcandle/swing_reports \
  --mode replace-date \
  --render-html \
  --html-output /home/kalle/projects/rawcandle/temp/manual_reports_dashboard_${REPORT_DATE}_production_dashboard_write_reference.html
```

Capture:

- `run_id`
- `status`
- `readiness`
- counts
- HTML render status if printed

Stop if reports build fails.

### G. Run Acceptance Report

Acceptance compares:

- temp reports reference dashboard DB
- production enrichment dashboard DB

```bash
PYTHONPATH=. python3 dev_tools/run_datacenter_dashboard_enrichment_acceptance_report.py \
  --ecosystem-code DATACENTER \
  --report-date "${REPORT_DATE}" \
  --reports-dashboard-db /home/kalle/projects/rawcandle/temp/manual_reports_dashboard_${REPORT_DATE}_production_dashboard_write_reference.db \
  --reports-run-id <reports_run_id_from_step_F> \
  --enrichment-dashboard-db /home/kalle/projects/rawcandle/data/ecosystem_dashboard.db \
  --enrichment-run-id <enrichment_run_id_from_step_E> \
  --analysis-db-copy /home/kalle/projects/rawcandle/data/analysis.db \
  --max-examples 50
```

Capture:

- `status`
- `blockers`
- `accepted_differences`
- `review_later`
- `recommendation`
- factual parity fields if printed
- action residuals if printed

### H. Optional Ticker Spot Checks

If acceptance output does not print the target tickers directly, inspect production dashboard rows read-only:

```bash
sqlite3 -header -column /home/kalle/projects/rawcandle/data/ecosystem_dashboard.db \
  "SELECT ticker, action, entry_readiness, candidate_priority_label
   FROM ecosystem_dashboard_ticker_status
   WHERE report_date='${REPORT_DATE}'
     AND ecosystem_code='DATACENTER'
     AND ticker IN ('CRUS','MYRG','HPQ')
   ORDER BY ticker;"
```

Expected:

- `CRUS = TIGHTEN_STOP / NEEDS_STOP_STABILIZATION / P2_STOP_STABILIZATION`
- `MYRG = TIGHTEN_STOP / NEEDS_STOP_STABILIZATION / P2_STOP_STABILIZATION`
- `HPQ = REDUCE / NEEDS_RISK_CLEARANCE / P3_RISK_CLEARANCE`

### I. Final Status Checks

Capture production DB metadata:

```bash
stat -c '%n|%s|%Y' \
  /home/kalle/projects/rawcandle/data/analysis.db \
  /home/kalle/projects/rawcandle/data/ecosystem_dashboard.db
```

Then verify final git state:

```bash
git status --short
git diff --stat
```


## 6. Success Criteria

Success requires all of the following:

- enrichment write `status=OK`
- post-write audit `readiness=READY`
- export `status=OK`
- production dashboard build `status=OK`
- production dashboard build `readiness=READY`
- reports reference build `status=OK`
- reports reference build `readiness=READY`
- acceptance:
  - `status=OK`
  - `blockers=0`
  - `recommendation=READY_FOR_SCHEDULER_SWITCH_PLANNING`
- factual parity:
  - `pullback_validity_differences=0`
  - `entry_readiness_differences=0`
  - `candidate_priority_label_differences=0`
- production `ecosystem_dashboard.db` intentionally modified
- scheduler not run
- Yahoo/OHLCV not run


## 7. Stop Conditions

Stop immediately if any of the following occurs:

- dirty tracked worktree
- missing reports for the target date
- missing DB input files
- `missing_tables > 0`
- enrichment write `status` not `OK`
- post-write audit not `READY`
- export failure
- production dashboard build failure
- reports reference build failure
- acceptance `blockers > 0`
- unexpected scheduler or stock update invocation
- production DB write error


## 8. Rollback

If dashboard output must be rolled back:

- restore `ecosystem_dashboard.db` from backup
- restore `analysis.db` from backup only if the enrichment write caused bad rows or corruption
- do not delete backups
- rerun reports-mode dashboard build if needed

Example restore commands:

```bash
cp "${BACKUP_DIR}/ecosystem_dashboard.db.before_manual_dashboard_write" \
  /home/kalle/projects/rawcandle/data/ecosystem_dashboard.db
```

```bash
cp "${BACKUP_DIR}/analysis.db.before_manual_dashboard_write" \
  /home/kalle/projects/rawcandle/data/analysis.db
```

Operational cautions:

- stop any process that may be writing before restore
- restore only with explicit operator approval
- do not restore over a live write


## 9. Known Accepted Residuals

Accepted residuals may remain visible after a successful run:

- raw action residuals may remain visible
- accepted differences may include known watchlist/outside-ecosystem differences
- accepted differences may include extra group / market-map / report-shape differences
- accepted differences may include verbose enrichment trace shape differences

These are non-blocking only when:

- factual candidate parity is clean
- acceptance `blockers=0`


## 10. Latest Accepted Example

Latest accepted production-write example:

- report date: `2026-05-28`
- backup dir:
  - `/home/kalle/projects/rawcandle/backups/dashboard_prod_write_20260529T134917Z`
- enrichment run id:
  - `DC_DASH_ENRICH_2026-05-28_2026-05-29T13:49:56Z`
- dashboard run id:
  - `ECO_DASHBOARD_DATACENTER_2026-05-28_20260529T135021Z`
- acceptance:
  - `status=OK`
  - `blockers=0`
  - `recommendation=READY_FOR_SCHEDULER_SWITCH_PLANNING`
- factual parity:
  - `pullback_validity_differences=0`
  - `entry_readiness_differences=0`
  - `candidate_priority_label_differences=0`
- ticker spot checks:
  - `CRUS = TIGHTEN_STOP / NEEDS_STOP_STABILIZATION / P2_STOP_STABILIZATION`
  - `MYRG = TIGHTEN_STOP / NEEDS_STOP_STABILIZATION / P2_STOP_STABILIZATION`
  - `HPQ = REDUCE / NEEDS_RISK_CLEARANCE / P3_RISK_CLEARANCE`
