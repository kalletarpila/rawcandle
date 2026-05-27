# Datacenter Dashboard Scheduler Switch Plan

## 1. Purpose

This document defines the planned staged transition from the current Datacenter dashboard scheduler flow, where dashboard snapshots are built from `.md` reports, to a future flow where dashboard snapshots are built from the enriched `analysis.db` path.

This is a planning/spec document only.

It does not:

- switch scheduler behavior
- change scheduler code
- remove reports mode
- remove `.md` report generation
- authorize production DB writes
- authorize production schema changes

Current acceptance status for planning input:

- enrichment acceptance report recommendation: `READY_FOR_SCHEDULER_SWITCH_PLANNING`
- blockers: `0`
- accepted differences: known and classified


## 2. Current Production-Safe Flow

Current scheduler post-step flow remains:

`stock update`
-> `datacenter .md report generation`
-> `reports-mode dashboard build`
-> `ecosystem_dashboard.db`
-> `DB-backed HTML`

Operationally important points:

- `.md` reports are still the current machine input source for the production-safe dashboard path.
- reports mode remains the fallback and reference implementation
- current scheduler summaries already expose Datacenter pipeline and dashboard status at a high level


## 3. Target Future Flow

Target future scheduler post-step flow:

`stock update`
-> `datacenter .md report generation for audit/human review`
-> `enrichment write into analysis.db`
-> `enrichment audit`
-> `analysis-db enrichment export JSON`
-> `structured dashboard build into ecosystem_dashboard.db`
-> `DB-backed HTML`
-> `optional parity/acceptance report`

Important boundary:

- `.md` reports are still generated and retained
- after switch completion they are no longer the machine input source for dashboard publishing
- reports mode remains available as fallback/reference


## 4. Required Production Preconditions Before Scheduler Switch

Before any scheduler source-mode switch is allowed, all of the following should be true:

- production `data/analysis.db` has the required enrichment schema applied
- enrichment writer path can run non-dry against production `analysis.db`
- temp-copy e2e smoke remains `OK`
- enrichment acceptance report has `blockers=0`
- reports-mode fallback still works end-to-end
- dashboard HTML generated from the enrichment path has been reviewed visually
- scheduler config paths are explicit and inspected
- a backup and rollback plan exists before changing the scheduler source mode

These are preconditions for switch planning and later rollout, not proof that production switch should happen immediately.


## 5. Proposed Scheduler Config Additions

The following config fields are proposed for a future implementation. Exact names are proposal only unless already implemented in scheduler code.

- `datacenter_dashboard_source_mode = reports|enrichment`
- `datacenter_enrichment_enabled = true|false`
- `datacenter_enrichment_apply_migrations = false` by default
- `datacenter_enrichment_taxonomy_version = DC_TAXONOMY_FULL_V1`
- `datacenter_enrichment_watchlist_file = <path>`
- `datacenter_enrichment_write_mode = replace-date`
- `datacenter_dashboard_fallback_to_reports = true|false`
- `datacenter_dashboard_run_acceptance_report = true|false`

Intent of these proposals:

- source mode should be explicit
- enrichment enablement should be independently controllable
- production schema mutation should never happen implicitly
- fallback behavior should be explicit and auditable


## 6. Proposed Scheduler Execution Order

Future staged execution order:

1. Existing market stock update
2. Existing Datacenter `.md` report generation
3. Enrichment write
4. Enrichment audit
5. Enrichment export JSON
6. Structured dashboard build
7. HTML render
8. Optional parity/acceptance report
9. If enrichment path fails and fallback is enabled: reports-mode dashboard build

Notes:

- step 2 remains in place even after the enrichment path becomes primary
- the reports build is retained as fallback until explicit later approval removes that dependency


## 7. Failure and Fallback Rules

Planned failure handling rules:

### A. Enrichment write failure

- do not write an enrichment dashboard snapshot as the canonical output
- if fallback is enabled, run reports-mode dashboard build
- scheduler summary should mark:
  - enrichment failed
  - fallback used

### B. Enrichment export failure

- do not continue as if structured dashboard build succeeded
- if fallback is enabled, run reports-mode dashboard build

### C. Structured build failure

- do not mark enrichment output as canonical
- if fallback is enabled, run reports-mode dashboard build

### D. Acceptance report blockers

- if acceptance report returns blockers, reports-mode output remains canonical
- do not mark the enrichment dashboard as production-ready solely because it was buildable


## 8. Summary Lines Contract Proposal

The scheduler should eventually emit explicit summary lines for the Datacenter dashboard source path. These are proposal-only for now:

```text
SUMMARY datacenter_dashboard_source_mode=<reports|enrichment>
SUMMARY datacenter_enrichment.attempted=<0|1>
SUMMARY datacenter_enrichment.status=<OK|FAILED|SKIPPED>
SUMMARY datacenter_enrichment.readiness=<READY|PARTIAL|FAILED>
SUMMARY datacenter_enrichment.run_id=<...>
SUMMARY datacenter_dashboard.enrichment_export_status=<OK|FAILED|SKIPPED>
SUMMARY datacenter_dashboard.structured_build_status=<OK|FAILED|SKIPPED>
SUMMARY datacenter_dashboard.fallback_used=<0|1>
SUMMARY datacenter_dashboard.final_source_mode=<reports|enrichment>
```

Operational goals of the summary contract:

- make fallback visible
- distinguish attempted vs skipped
- distinguish enrichment readiness from final published source mode


## 9. Rollback Plan

Rollback should be simple and explicit:

- set source mode back to `reports`
- leave enrichment tables in `analysis.db` in place for audit and diagnosis
- do not delete `ecosystem_dashboard.db` snapshots
- keep reports-mode build available
- regenerate HTML from reports mode if needed

Rollback should not require deleting enrichment data. It should only require switching the publishing source back to reports mode.


## 10. First Implementation Steps After This Spec

Planned staged follow-ups:

### DB-17c

- add scheduler config fields
- add inspect-only visibility for those fields

### DB-17d

- add scheduler dry-run / plan output for the enrichment path

### DB-17e

- wire enrichment path behind a disabled config flag

### DB-17f

- enable fallback to reports mode

### DB-17g

- define local manual production DB migration and non-dry enrichment write procedure

### DB-17h

- final scheduler source-mode switch after explicit approval


## 11. Explicit Non-Goals

This planning step does not include:

- immediate scheduler switch
- removal of reports mode
- automatic migration of production `analysis.db` by scheduler without explicit approval
- deletion of `.md` reports
- production DB writes during planning


## 12. Decision Boundary

Current interpretation of readiness:

- the enrichment path is ready for scheduler switch planning
- it is not yet approved for automatic production scheduler switch
- reports mode remains the operational fallback and reference path until later staged work is completed and approved
