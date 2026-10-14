# Scheduler recovery 2026-10-14

## Current outcome

Recovery resumed after the operator confirmed completion of the UI stock-database update. **R1 PASS; R2 PASS; R3 PASS. Final readiness: READY_WITH_NONBLOCKING_INCIDENT_RESIDUE.** EC catch-up and the normal manual Fundamentals Full workflow completed successfully. All execution locks are free, the publication journal is terminal and the timer remains active for October 15 at 04:30 EEST. The old scheduler UI status and interrupted backup evidence remain explicitly non-authoritative residue, not a repaired historical scheduler run.

Incident: [scheduler_incident_2026-10-14.md](scheduler_incident_2026-10-14.md), commit `bc3a28ba5a35fd85dbc2b2f4a15a710f8f751641`. The first recovery attempt stopped safely at R1 because application PID 52552 held the scheduler lock; that stop was committed as `44d98c59f89b7a5a16697a7e8bd6b250e78f978a`. The operator subsequently confirmed the live operation was a stock-database update, allowed it to finish, and authorized resuming the original recovery through a fresh R1.

The operator identified the original WSL restart as manual recovery from a Codex/WSL problem. No further host-cause investigation or scheduler rerun was performed. Times are UTC where suffixed Z; Helsinki EEST is UTC+03:00. Paths are relative to `/home/kalle/projects/rawcandle` unless absolute.

## R1 — renewed preflight, PASS

Preflight was repeated around **12:41–12:44 EEST**. Host process/kernel-lock inspection confirmed:

- Scheduler service inactive, MainPID=0; no competing scheduler, EC or Fundamentals CLI operation found.
- The UI `main.py --port 8888` process remained alive, but had released scheduler FLOCK.
- Its remaining analysis DB POSIX locks were READ locks: main DB byte range 1073741826–1073742335 and SHM byte 128.
- No Production or Admin UI operation kernel-lock holder was shown.
- Authoritative taxonomy lock file `temp/datacenter_taxonomy_changes/taxonomy_operation.lock` was absent. This lock is file-based, not a kernel-flock contract.

The existing `production_transaction.production_lock()` successfully acquired both Production and scheduler execution locks and released them normally. While holding these locks, a SQLite connection to the existing analysis DB reported WAL journal mode, successfully executed **BEGIN IMMEDIATE**, then rolled back without any data statements. This confirmed the current UI readers did not block the write reservation EC needs. Subsequent real EC completion independently confirms this point. No UI process was stopped or signalled.

The current publication journal passed the required checks: COMPLETED, current step COMPLETED, ACTIVATED_AND_VERIFIED, postflight PASSED, rollback/recovery NOT_REQUIRED. `safety_status()` did not block writes. `resolve_active_generation(require_generation=True)` resolved the October 13 generation and all three role files. Read-only `PRAGMA quick_check` returned `ok` for provider, canonical and analysis. No `.preparing` generation or new October 14 candidate lane existed before recovery execution; no publication recovery was pending.

### Stale scheduler status handling

The old `logs/stock_update_scheduler_status.json` still says RUNNING with start `2026-10-14T01:30:10Z`, current_market=usa and no finish/summary. It was **not manually edited or rewritten**.

The current `runtime_state.read_scheduler_status` only reads JSON. `runner.acquire_scheduler_lock` uses nonblocking kernel flock and does not consult this status. `production_transaction.production_lock` uses its kernel lock plus that scheduler lock. The standalone EC and manual Full workflow paths do not require a successful historical scheduler status. No dedicated supported stale-status reconciliation/reset was identified in these inspected paths. The latest operator instruction explicitly permits proving this state non-authoritative/non-blocking instead of resetting it.

Handling: **NOT_REQUIRED for execution — proven non-authoritative/non-blocking; persisted UI residue remains.** This is not a claim that the historical run completed. The next actual scheduler invocation normally writes its own status after acquiring locks. Until then, the UI may still report the old run as running; assess current execution using service/process/kernel-lock evidence.

Stale Production-lock owner text is informational under the existing persistent-lock contract. Normal recovery lock acquisitions may replace that owner text; no persistent lock file was deleted merely to remove metadata.

### Interrupted backup gate

The original pair remains preserved:

```
temp/analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261006_20261013__20261014T042318Z.sqlite
temp/analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261006_20261013__20261014T042318Z.sqlite-journal
```

The DB is 0 bytes; its journal is 1,024 bytes. Host `fuser -v` found no process using either exact file. Current publication journal/active manifest/scheduler status do not reference the pair. The inspected standalone EC backfill has no automatic restore consumer or persisted mutation/recovery journal selecting this file: the SQLite journal belongs to its incomplete backup destination. It is not authoritative, is unusable for restoration, and does not block creation of a uniquely named new backup. Neither file was opened as a DB, restored, consumed or deleted.

**R1 gate: PASS.** No legitimate competing operation, lock conflict or pending publication recovery remained. SQLite write availability was proven; stale scheduler text was proven non-blocking.

## R2 — standalone EC catch-up, PASS

### Interval and planner

Current `_resolve_ec_bridge_catchup_state` found DC fact and watermark heads at **2026-10-13**, EC fact and watermark heads at **2026-10-12**. Head-only catch-up therefore identifies October 13. The existing `_build_ec_bridge_decision` also accounts for actual datacenter materialization: the successful morning datacenter log records EXECUTED materialization from **October 6 through October 13**. Its normal MULTI_DATE_MATERIALIZATION rule selects HISTORICAL_BACKFILL over that complete dirty interval, including replacing previously loaded dates.

The existing standalone no-write planner was run with:

```
venv/bin/python -m rawcandle.cli.plan_ec_source_layer_backfill
  --db /home/kalle/projects/rawcandle/data/analysis.db
  --ecosystem DATACENTER
  --taxonomy-version DC_TAXONOMY_FULL_V2_1
  --date-from 2026-10-06 --date-to 2026-10-13
  --taxonomy-csv data/datacenter_taxonomy_full_v2_1.csv
  --watchlist watchlists/datacenter_watchlist.txt
  --allow-replace-existing
```

It returned READY_BACKFILL_PLAN. All six trading dates had aligned sources: 257 ticker, 54 group-signal, 53 synthetic-OHLC and 54 group-index rows each. Taxonomy hash matched, watchlist MATCH, no blocking dates or missing primary memberships. October 10–11 were excluded because no aligned trading-day source existed. This validated the dirty interval against current sources rather than blindly forcing the incident interval.

### Existing backup and standalone operation

The operation used the existing `rawcandle.cli.run_ec_source_layer_backfill` API and its own `_create_backup` helper under the normal Production/scheduler lock guard. Backup creation and validation were separated from loader execution to meet the requirement to validate before EC writes; the existing API's `create_backup=False, existing_backup_path=<new validated backup>` option supplied that same backup to the loader. No backup algorithm, loader, gate or source code was changed.

New backup:

```
temp/analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261006_20261013__20261014T094436Z.sqlite
```

Creation began `2026-10-14T09:44:36.886218Z`. Size **12,450,451,456 bytes**, read-only quick_check=ok; validated at **09:44:56.270962Z before EC loading**. The interrupted 04:23 artifact was explicitly excluded and never overwritten or reused.

`run_ec_source_layer_backfill` used the planner's DB/ecosystem/taxonomy/date/CSV/watchlist parameters, `ohlc_calc_version=DC_SWING_OHLC_V2`, exact confirm_db/confirm_ecosystem/confirm_taxonomy_version, allow_replace_existing=True, normal watchlist reconciliation, and normal final watermark advancement. No taxonomy rebuild or policy modification was requested. Production and scheduler locks remained held across backup validation and EC execution and were released afterward.

Normal rendered report and persisted operation evidence:

- `logs/ec_recovery_20261014T094436Z.txt` — existing `render_backfill_text` output.
- `logs/ec_recovery_20261014T094436Z.json` — standalone operation result, persisted `09:44:56.935591Z`.
- `logs/ec_recovery_20261014T094436Z.plan.json` — current plan under the execution guard.
- `logs/ec_recovery_20261014T094436Z.backup_validation.json` — validity evidence timestamped before writes.

### Terminal validation

Result **BACKFILL_COMPLETED**, all selected dates completed: October 6, 7, 8, 9, 12 and 13. failed_date/failed_step/error are null; errors empty; total_mismatch_count=0. Every date has coverage and parity **OK_WITH_WARNINGS**, both execution statuses COMPLETED. Warnings describe accepted unmapped diagnostic fields and the established EC/watchlist universe difference; no required source rows or blocking semantic/lineage mismatches were missing. Per-date watermark parity is skipped by normal policy; four canonical watermark heads were advanced once after all date validations, watermark_advance_status=OK.

Post-operation catch-up resolution is **ALIGNED**, DC=EC=2026-10-13 across all four fact and watermark heads, with no catch-up interval remaining. Watchlist reconciliation NO_CHANGE, membership MATCH. Publication safety remained clear and no execution/Admin lock holder remained before Fundamentals began. No EC recovery or retry is required. The new backup remains retained; the interrupted pair remains incident evidence.

## R3 — normal manual Fundamentals Full workflow

Started through `FundamentalsAdminUIService.full_workflow(operation_type="REFRESH_FUNDAMENTALS", raw_inputs="", trigger_source="MANUAL")`. No scheduler wrapper or direct Production-only call was used. The parent request persists mode FULL_WORKFLOW and trigger_source MANUAL.

| Stage | Run ID | Current result |
| --- | --- | --- |
| Parent | `20261014T094617Z_refresh_fundamentals_d00eb7239fed_full_workflow_3262544c` | COMPLETED, 09:46:17–10:04:14Z |
| Preview | `20261014T094617Z_refresh_fundamentals_c9fd48c1852d` | COMPLETED, 09:46:17–09:46:46Z |
| Test on copies | `20261014T094646Z_refresh_fundamentals_43db1c8371f6_test` | COMPLETED, 09:46:46–09:54:01Z |
| Production | `20261014T095401Z_refresh_fundamentals_43db1c8371f6_production_6917d617` | COMPLETED, 09:54:01–10:04:14Z |

Preview: 3 effective changed known tickers, 3 safe changes, 0 held items, review_required=0 and global_blockers=0. Two classifications NEW_QUARTER_AND_REVISION and one SOURCE_HISTORY_CHANGE; 41 discovered tickers outside the canonical universe were handled by the normal contract. Test gate authorized with SAFE_CHANGES_TEST_AUTHORIZED. Decision: “Safe peer changes are available and may continue.”

Test source revalidation matched Preview. Provider and canonical integrity checks passed; full V2/RP V2/RV candidate reached READY; candidate databases were removed by normal Test cleanup. Market binding used a stable compact source bundle; taxonomy used protected DIRECT_LOCKED_READ, active DC_TAXONOMY_FULL_V2_1 and source contract FUNDAMENTALS_READ_ONLY_SOURCE_V1. Test operational decision records Production AUTHORIZED / MATCHING_SUCCESSFUL_TEST_VALIDATED. The requested Full workflow supplies Production authorization through the existing normal gates.

Production authorization/recovery preflight passed and complete Sharadar source state still matched Test, including the final pre-publication recheck. Published effective changes were **DAL, DPZ and WS**. The provider/canonical/analysis candidates passed validation; the normal workflow created and verified three durable rollback backups, prepared the journal, created the immutable generation and atomically activated it. Postflight passed, the journal committed and normal terminal cleanup completed.

Active generation after publication:

```
refresh_20261014T095401Z_refresh_fundamentals_43db1c8371f6_production_6917d617
```

The active manifest resolves all three nonzero role files in that generation. Production-path postflight records quick_check=ok for provider, canonical and analysis; canonical duplicate/foreign-key/missing-first-public counts are zero. Cross-role lineage matches the validated candidate, canonical identities, provider refresh state and active taxonomy fingerprint. Fundamentals source watermark advanced from **2026-10-12 to 2026-10-13**; two canonical quarters were added, 89,938 existing first-public dates preserved and two new first-public dates established. No publication recovery is required.

### Normal publication-authority result

The candidate's bounded publication-authority subworkflow returned **PARTIAL**, independently of the successful whole-generation publication. Its normal scope processed 58 quarter keys: 2 VERIFIED, 3 AMBIGUOUS, 40 NOT_FOUND and 13 UNRESOLVED. There were no technical errors and no unprocessed selected keys. It used the unchanged normal 60-day retry window and 100-quarter cap; 56 eligible recent retries were selected. `retry_backlog_remaining=0` describes selection overflow, **not** an absence of unresolved publication cases. No manual drain, expanded historical scope, policy change or resolver override was performed.

The Full workflow's authoritative operational decision is PUBLICATION_COMPLETED, Production AUTHORIZED, safe_effective_changes=3, held_item_count=0 and global_blocker_count=0; recommended action is NO_ACTION_REQUIRED. Its review_required=0 concerns the Refresh partition, not a claim that all publication-authority observations are verified. The existing gates accepted these normal unresolved authority outcomes and postflight passed. They do not require EC or generation rollback in this task.

### Durable results and retained rollback backups

Normal workflow report:

```
fundamental_reports/admin_runs/20261014T094617Z_refresh_fundamentals_d00eb7239fed_full_workflow_3262544c/workflow_report.md
```

The same directory contains terminal `workflow_result.json` and `result.json`; each child directory named above contains its normal result and operation report. `logs/fundamentals_recovery_20261014T094616Z.json` persists the successful manual service response. Parent duration was 1,077 seconds (17 min 57 s).

The canonical publication journal now records the October 14 Production ID above, updated **10:04:14Z**, with COMPLETED / COMPLETED / ACTIVATED_AND_VERIFIED / PASSED / NOT_REQUIRED. Its generation matches the active manifest. Production terminal cleanup reports candidate_lane_absent=true, remaining_phase_owned_files=0 and status PASSED. Test removed its own candidates. Final inspection found no October 14 candidate lanes or `.preparing` generations.

Rollback backups are intentionally retained under:

```
backups/fundamentals_admin_production/20261014T095401Z_refresh_fundamentals_43db1c8371f6_production_6917d617/
```

| Role | File | Size, bytes |
| --- | --- | --- |
| analysis | `analysis.db` | 910,295,040 |
| canonical | `canonical.db` | 749,371,392 |
| provider | `provider.db` | 968,331,264 |

All three files were verified present after completion; total **2,627,997,696 bytes** (2.448 GiB). No rollback backup was deleted or accepted for deletion. Operator acceptance remains separate, as required by the normal cleanup result.

**R3 gate: PASS.** Preview, Test, Production and Full workflow are terminal COMPLETED; no gate was bypassed. Normal postflight and cleanup passed; recovery NOT_REQUIRED.

## R4 — final readiness

Final checks completed around **13:04–13:05 EEST** after the manual workflow terminated.

| Check | Final evidence |
| --- | --- |
| Scheduler service | Inactive, MainPID=0 |
| Competing scheduler/EC/Fundamentals operation | None found in host process snapshot |
| Scheduler lock before resumed recovery / after | FREE / FREE; acquired and released through the existing guard at both R1 and R4 |
| Production lock before / after | FREE / FREE; successful existing guard acquisition/release |
| Taxonomy lock before / after | Authoritative file absent / absent; normal Test and Production source guards acquired and released it during their lifetimes |
| Admin UI operation lock | No kernel holder shown after completion |
| Publication journal | COMPLETED, activation ACTIVATED_AND_VERIFIED, postflight PASSED, recovery NOT_REQUIRED |
| Active manifest | Resolves the new generation and all three healthy role files; matches terminal journal |
| Candidate/preparing residue | No current-run candidate lane, no `.preparing` generation; normal cleanup PASSED |
| EC | ALIGNED at 2026-10-13 for all four fact and watermark heads; no catch-up/retry interval or recovery required |
| New EC backup | Retained valid 12,450,451,456-byte backup; no rollback journal. SQLite sidecars are WAL=0 bytes and SHM=32,768 bytes; host fuser found no live user. They carry no pending WAL writes and were left intact under the no-manual-cleanup requirement |
| Interrupted EC evidence | Original 0-byte DB and 1,024-byte destination journal preserved and never consumed |
| Scheduler status JSON | Old non-authoritative RUNNING text remains; no manual reset or fabricated completion |
| October 14 scheduler summary | Absent; no summary created by this recovery |
| Timer | Installed, enabled and active; schedule unchanged `*-*-* 04:30:00` |
| Next normal trigger | **2026-10-15 04:30:00 EEST** |

Classification: **READY_WITH_NONBLOCKING_INCIDENT_RESIDUE**. All operational lock, publication, source-alignment and recovery gates are clean. This uses the operator's explicit allowance to prove stale scheduler status non-authoritative instead of manually changing it. It does **not** certify that persisted UI text was corrected: the scheduler page can still show the old RUNNING indication and October 13 Latest summary. A supported UI/status reconciliation improvement, if desired, is a separate implementation task; it is not necessary for the next scheduler execution's kernel-lock acquisition.

The manual Full workflow report is available in Admin run history. The interrupted October 14 scheduler invocation remains incomplete and auditable; its original market/datacenter logs, incident report and interrupted EC pair were preserved. Neither manual operation was backdated or relabelled as Scheduler execution.

## Scope

No OMXH, USA or datacenter rerun; no restore of the unusable backup; no fabricated scheduler summary; no source/config/systemd changes; no pytest/full suite. Normal Test on copies is an operational workflow stage, not a repository test-suite run. No rollback backups are accepted or deleted. Runtime EC/Fundamentals artifacts are excluded from Git; only this recovery document is to be committed. Nothing is pushed.
