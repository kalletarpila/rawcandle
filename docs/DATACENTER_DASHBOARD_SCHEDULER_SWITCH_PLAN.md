# Datacenter Dashboard Scheduler Source-Mode Switch Plan

## 1. Purpose

This document defines the controlled operator plan for eventually switching the Datacenter dashboard scheduler post-step from reports-mode to enrichment-mode.

This is a docs/runbook planning step only.

It does not:

- switch scheduler source mode
- change scheduler behavior
- edit `scheduler_config.json`
- authorize a production scheduler run
- remove reports fallback
- remove `.md` report generation
- authorize production DB writes without explicit operator approval


## 2. Current Readiness Status

Latest validated Datacenter parity state:

- `pullback_validity_differences=0`
- `entry_readiness_differences=0`
- `candidate_priority_label_differences=0`
- `final_field_parity_not_safe_for_switch=0`
- `canonical_decision_input_missing=0`

Latest validated acceptance status after `3a977da`:

- `status=OK`
- `blockers=0`
- `recommendation=READY_FOR_SCHEDULER_SWITCH_PLANNING`

Important interpretation:

- enrichment source-mode is now factually aligned for:
  - `pullback_validity`
  - `entry_readiness`
  - `candidate_priority_label`
- raw snapshot `action` residuals remain visible
- those residuals are non-blocking only under the updated factual candidate parity contract


## 3. Explicit Non-Goals

This plan does not perform the switch by itself.

Required operational boundaries:

- reports-mode remains the default until config is intentionally changed
- reports fallback must remain enabled for the initial switch attempt
- Datacenter `.md` reports must still be generated before the dashboard post-step
- no production `ecosystem_dashboard.db` switch should happen without backup and post-run validation
- no scheduler migration step should be enabled implicitly


## 4. Required Preconditions

Before any operator changes scheduler config, all of the following must be true:

- tracked git worktree is clean
- production `analysis.db` contains the Datacenter enrichment tables
- production `analysis.db` contains the latest enrichment rows for the target signal date
- latest enrichment audit is `READY`
- latest acceptance report has:
  - `status=OK`
  - `blockers=0`
  - `recommendation=READY_FOR_SCHEDULER_SWITCH_PLANNING`
- watchlist file exists:
  - `/home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt`
- Datacenter taxonomy CSV / pipeline prerequisites are OK through scheduler inspect
- scheduler inspect-only output confirms:
  - `datacenter_dashboard_source_mode` can be set to `enrichment`
  - `datacenter_enrichment_enabled` can be set to `true`
  - `datacenter_dashboard_fallback_to_reports` remains enabled
  - `datacenter_enrichment_apply_migrations` remains `false`

Important current code reality:

- current inspect-only code reports `enrichment_effective_status=CONFIGURED_NOT_WIRED` when enrichment is enabled
- current enrichment plan also emits warning `ENRICHMENT_EXECUTION_NOT_WIRED`
- therefore DB-20a prepares the switch plan and inspect-only validation path
- DB-20a does not authorize an actual production source-mode flip yet


## 5. Exact Scheduler Config Fields

Use the exact current scheduler config field names from [config.py](/home/kalle/projects/rawcandle/rawcandle/scheduler/config.py):

- `datacenter_dashboard_enabled`
- `datacenter_dashboard_db`
- `datacenter_dashboard_html_output_dir`
- `datacenter_dashboard_source_mode`
- `datacenter_enrichment_enabled`
- `datacenter_enrichment_apply_migrations`
- `datacenter_enrichment_taxonomy_version`
- `datacenter_enrichment_watchlist_file`
- `datacenter_enrichment_write_mode`
- `datacenter_dashboard_fallback_to_reports`
- `datacenter_dashboard_run_acceptance_report`
- `analysis_db_path`
- `osakedata_db_path`

Safe intended values for the eventual controlled switch:

- `datacenter_dashboard_enabled=true`
- `datacenter_dashboard_source_mode="enrichment"`
- `datacenter_enrichment_enabled=true`
- `datacenter_enrichment_apply_migrations=false`
- `datacenter_enrichment_taxonomy_version="DC_TAXONOMY_FULL_V1"`
- `datacenter_enrichment_watchlist_file="/home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt"`
- `datacenter_enrichment_write_mode="replace-date"`
- `datacenter_dashboard_fallback_to_reports=true`
- `datacenter_dashboard_run_acceptance_report=true`
- `analysis_db_path="/home/kalle/projects/rawcandle/data/analysis.db"`
- `osakedata_db_path="/home/kalle/projects/rawcandle/data/osakedata.db"`


## 6. Inspect-Only Commands

Inspect current scheduler dashboard config:

```bash
PYTHONPATH=. python3 rawcandle/cli/run_stock_update_scheduler.py \
  --config /home/kalle/projects/rawcandle/scheduler_config.json \
  --inspect-dashboard-config \
  --show-enrichment-plan
```

Relevant inspect summary fields from the current CLI:

- `scheduler_dashboard_config.dashboard_source_mode`
- `scheduler_dashboard_config.enrichment_enabled`
- `scheduler_dashboard_config.enrichment_apply_migrations`
- `scheduler_dashboard_config.enrichment_watchlist_file_status`
- `scheduler_dashboard_config.dashboard_fallback_to_reports`
- `scheduler_dashboard_config.dashboard_run_acceptance_report`
- `scheduler_dashboard_config.enrichment_effective_status`
- `scheduler_enrichment_plan.source_mode`
- `scheduler_enrichment_plan.enrichment_enabled`
- `scheduler_enrichment_plan.effective_status`
- `scheduler_enrichment_plan.analysis_db_status`
- `scheduler_enrichment_plan.watchlist_file_status`
- `scheduler_enrichment_plan.fallback_to_reports`
- `scheduler_enrichment_plan.run_acceptance_report`
- `scheduler_enrichment_plan.stage.md_reports_generation`
- `scheduler_enrichment_plan.stage.enrichment_write`
- `scheduler_enrichment_plan.stage.enrichment_audit`
- `scheduler_enrichment_plan.stage.enrichment_export_json`
- `scheduler_enrichment_plan.stage.structured_dashboard_build`
- `scheduler_enrichment_plan.stage.acceptance_report`
- `scheduler_enrichment_plan.stage.fallback_reports_build`


## 7. Controlled Switch Sequence

### A. Backup

Before any config change or scheduler run:

- back up production `analysis.db`
- back up production `ecosystem_dashboard.db`
- use a timestamped directory under:
  - `/home/kalle/projects/rawcandle/backups/`

Example operator naming:

- `/home/kalle/projects/rawcandle/backups/scheduler_switch_<UTC_TIMESTAMP>/analysis.db.before_switch`
- `/home/kalle/projects/rawcandle/backups/scheduler_switch_<UTC_TIMESTAMP>/ecosystem_dashboard.db.before_switch`

### B. Inspect Current Config

Run:

```bash
PYTHONPATH=. python3 rawcandle/cli/run_stock_update_scheduler.py \
  --config /home/kalle/projects/rawcandle/scheduler_config.json \
  --inspect-dashboard-config \
  --show-enrichment-plan
```

Expected pre-switch state today:

- `scheduler_dashboard_config.dashboard_source_mode=reports`
- `scheduler_dashboard_config.enrichment_enabled=0` or operator-chosen current local value
- `scheduler_dashboard_config.dashboard_fallback_to_reports=1`
- `scheduler_dashboard_config.enrichment_apply_migrations=0`

### C. Update Config Intentionally

Do not perform this inside DB-20a.

When later authorized, update only the intended scheduler config fields:

- `datacenter_dashboard_source_mode`
- `datacenter_enrichment_enabled`
- `datacenter_dashboard_fallback_to_reports`
- `datacenter_dashboard_run_acceptance_report`

Review the config diff before any run:

- if config is tracked: inspect `git diff`
- if config is local/untracked: inspect the file diff locally before execution

### D. Inspect Switched Plan

Run the same inspect-only command again after the intentional config edit.

Minimum expected values for the planned switch:

- `scheduler_dashboard_config.dashboard_source_mode=enrichment`
- `scheduler_dashboard_config.enrichment_enabled=1`
- `scheduler_dashboard_config.enrichment_apply_migrations=0`
- `scheduler_dashboard_config.enrichment_watchlist_file_status=OK`
- `scheduler_dashboard_config.dashboard_fallback_to_reports=1`
- `scheduler_dashboard_config.dashboard_run_acceptance_report=1`
- `scheduler_enrichment_plan.source_mode=enrichment`
- `scheduler_enrichment_plan.enrichment_enabled=1`
- `scheduler_enrichment_plan.analysis_db_status=OK`
- `scheduler_enrichment_plan.watchlist_file_status=OK`
- `scheduler_enrichment_plan.fallback_to_reports=1`
- `scheduler_enrichment_plan.stage.md_reports_generation=1:DATACENTER_PIPELINE_ENABLED`
- `scheduler_enrichment_plan.stage.fallback_reports_build=1:FALLBACK_ENABLED`

Current important limitation:

- current code is expected to show:
  - `scheduler_dashboard_config.enrichment_effective_status=CONFIGURED_NOT_WIRED`
  - `scheduler_enrichment_plan.effective_status=CONFIGURED_NOT_WIRED`
  - warning `ENRICHMENT_EXECUTION_NOT_WIRED`
- if those values remain present, stop after inspect-only review
- do not perform a production scheduler source-mode switch yet

### E. Controlled Manual Scheduler Execution

Do not do this in DB-20a.

Only after inspect-only output, code wiring, and explicit operator approval are complete:

```bash
PYTHONPATH=. python3 rawcandle/cli/run_stock_update_scheduler.py \
  --config /home/kalle/projects/rawcandle/scheduler_config.json
```

Operational rule:

- do not resume normal recurring scheduler operation first
- use one controlled manual scheduler execution first

### F. Post-Run Validation

After the future manual scheduler run:

- run enrichment audit
- verify structured dashboard build status
- run acceptance report
- confirm production `ecosystem_dashboard.db` was updated only by the intended scheduler path
- confirm reports fallback was not used unless explicitly noted and accepted


## 8. Rollback Plan

If the future switched run is not acceptable:

1. Set config back to:
   - `datacenter_dashboard_source_mode="reports"`
   - `datacenter_enrichment_enabled=false`
2. Keep:
   - `datacenter_dashboard_fallback_to_reports=true`
3. Re-run inspect-only command and confirm:
   - `scheduler_dashboard_config.dashboard_source_mode=reports`
   - fallback still enabled
4. Restore `ecosystem_dashboard.db` from backup if the published dashboard needs rollback
5. Restore `analysis.db` only if enrichment write corruption or unintended production write damage occurred
6. If needed, rerun the reports-mode dashboard path after rollback


## 9. Success Criteria

A future source-mode switch is successful only if all of the following are true:

- scheduler run status is `OK` or approved `OK_WITH_WARNINGS`
- Datacenter dashboard post-step status is `OK`
- source mode enrichment is confirmed by scheduler summary output
- acceptance report returns:
  - `blockers=0`
  - ready recommendation
- reports fallback was not used unless explicitly documented and accepted
- production dashboard DB and HTML exist at the intended output paths
- output row counts are sane
- no unexpected tracked source changes are created locally


## 10. Stop Conditions

Stop immediately if any of the following occurs:

- tracked worktree is dirty before switch
- backup was not created
- enrichment audit is not `READY`
- acceptance report has `blockers > 0`
- inspect-only output does not show fallback enabled
- inspect-only output still shows `CONFIGURED_NOT_WIRED`
- scheduler reports enrichment failure while fallback is disabled
- production DB write errors occur
- any unexpected schema or migration attempt is detected


## 11. Open Residuals / Accepted Differences

The following remain visible and must stay visible in acceptance reporting:

- raw action residuals remain visible
- those residuals are non-blocking only when factual candidate parity is clean
- `review_later` items may remain, including production migration review items if still emitted

These are not to be hidden by the switch plan. They must remain operator-visible.


## 12. Next Step After DB-20a

The next task after DB-20a should be:

- an operator prompt for inspect-only scheduler config validation
- not an immediate scheduler source-mode switch

If inspect-only still reports `CONFIGURED_NOT_WIRED`, the next engineering task is to close that scheduler wiring gap before any production switch attempt.
