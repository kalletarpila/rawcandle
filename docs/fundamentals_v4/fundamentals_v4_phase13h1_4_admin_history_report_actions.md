# Phase 13H.1.4 Administration History, Report And Actions

Outcome: `OUTCOME A - ADMIN HISTORY, REPORT AND COPY ACTION LABEL CLOSED`

## Observed Problem

Run history sorted directory names before applying its 12-row limit. Phase evidence directories beginning with `phase` sorted ahead of timestamped runs. The classification rule also treated any result with an admin operation type as an administration run, including synthetic phase evidence. With technical history visible, evidence rows consumed the limit before the latest completed Taxonomy preview could appear. Its `UNCHANGED` count was not mapped to a membership count, and the raw backend `COMPLETED` outcome obscured the business result.

## History Contract

The reader recognizes timestamped operation runs with supported operation modes as administration runs. Phase closures, acceptance evidence, cleanup evidence and malformed or symlinked results remain technical or invalid. It sorts each class by the structured completion timestamp before limiting. The normal view contains administration runs only; the technical view includes a separate bounded technical group without displacing administration runs.

The retained `20260918T085757Z_check_update_taxonomy_dcb015ad6e99_dc_ecosystem_preview` appears first in the normal view with completion time `2026-09-18T09:01:52Z`, operation `Taxonomy`, business result `No changes`, count `350 memberships`, and report availability. The page refreshes history after each completed operation and selects the current run. Selecting a run reads its summary and progress through the safe history artifact API. Invalid artifacts fail closed while the current-session result remains visible.

## Downloadable Report

New reports have Executive Summary, What Was Checked, Changes Found, Actions Performed, Downstream Impact, Warnings or Blockers, Final Result, and Technical Appendix sections. The main body uses structured run fields and omits empty values, raw JSON, absolute paths, fingerprints, and stage telemetry. The appendix retains bounded run identifiers, fingerprints, counts and artifact filenames. Report rendering is deterministic; report write, manifest hashing, redaction and exact download routing remain in place.

The latest retained Taxonomy run's `operation_report.md` was regenerated from its unchanged structured result, and its artifact manifest was rehashed. The previous report and manifest are retained under `fundamental_reports/admin_runs/phase13h1_4_admin_history_report_actions/`. Older retained reports were not rewritten. New runs use the revised format. The Taxonomy audit itself was not rerun.

## Action Label And Safety

The copy-only button now reads `Test on copies`. Preview, copy testing and the protected Production update action have distinct descriptions. Phase 13H.1.3 freshness, business outcome, domain and backend authorization gates remain active; no-change Taxonomy previews show only Preview.

## Verification

Focused admin UI/history, taxonomy, progress, scheduler UI, Snapshot, safe report download and production isolation tests passed. `compileall` and `git diff --check` passed. An initial overbroad selection reached the long Taxonomy acceptance module and was interrupted; the intended 151-test focused suite then passed. The full repository suite was not run because this phase changes only presentation, history reading and report wording. No production write, taxonomy update, package/RP/RV refresh, provider request or Scheduler lifecycle change was made.
