# Scheduler recovery 2026-10-14 — stopped at R1

## Outcome

**R1: STOP. No EC or Fundamentals recovery operation was started.**

The current live application process holds the scheduler execution kernel lock. The recovery request explicitly requires stopping when that lock cannot safely be obtained. No process was killed, no lock acquired or cleared, and no runtime state changed. The recovery objective remains incomplete; this report records the required safe stop.

Incident reference: [scheduler_incident_2026-10-14.md](scheduler_incident_2026-10-14.md), commit `bc3a28ba5a35fd85dbc2b2f4a15a710f8f751641`. The operator has now identified the WSL restart as manual recovery from a Codex/WSL problem; its cause is not investigated again here. The interrupted scheduler invocation remains historically incomplete.

Read-only observations were collected October 14 around **12:26–12:27 EEST (UTC+03:00)**. Paths below are relative to `/home/kalle/projects/rawcandle` unless absolute.

## R1 preflight and stop evidence

| Check | Observation |
| --- | --- |
| Scheduler service active | NO: `stock-update-scheduler.service`, `ActiveState=inactive`, `SubState=dead`, `MainPID=0` |
| Scheduler CLI process active | NO matching process found in host process snapshot |
| EC CLI process active | NO matching process found; in-process application activity cannot be excluded |
| Fundamentals CLI process active | NO matching process found; in-process application activity cannot be excluded |
| Application process | PID **52552**, started **2026-10-14 11:59:49 EEST**, `/home/kalle/projects/rawcandle/venv/bin/python main.py --port 8888` |
| Scheduler execution lock available | **NO**: host `lslocks` shows PID 52552 holding FLOCK on `logs/stock_update_scheduler.lock` at initial and final snapshots |
| Other application locks | PID 52552 also holds POSIX locks on `data/analysis.db` and `data/analysis.db-shm` |
| Fundamentals Production lock | No current kernel holder shown for `temp/.fundamentals_admin_production.lock`; not acquired/probed after the mandatory stop |
| Taxonomy lock | `temp/datacenter_taxonomy_changes/taxonomy_operation.lock` absent. This is the authoritative file-based lock under the current taxonomy contract; no acquisition attempted |
| Exact application operation | Not established from these observations. A live application process with database and scheduler locks cannot be treated as a stale lock owner or safely bypassed |
| R1 result | **STOP — scheduler execution lock unavailable** |

Host process inspection was elevated only to read the real host process/lock state, outside the sandbox PID namespace. No debugger, thread interruption, process signal, lock deletion or application control was used. No further dependent preflight or execution was attempted after the lock stop condition was established. The additional reads below document current state without claiming all remaining R1 checks passed.

## Stale scheduler state

`logs/stock_update_scheduler_status.json` remains unchanged from the incident:

```
is_running=true
last_status=RUNNING
current_market=usa
started_at_utc=2026-10-14T01:30:10Z
finished_at_utc=null
summary_json_path=null
error=null
```

Scheduler stale status reconciled: **NO**. The original scheduler service is absent, but the current live application's execution lock prevents proceeding with recovery. No JSON was manually edited. The narrowly inspected scheduler runner/CLI/UI paths do not expose a verified dedicated safe stale-status reset; ordinary status-writing functions alone do not establish an operator recovery contract. Whether a supported reconciliation mechanism exists elsewhere remains unresolved and must be established before a future attempt requiring persisted status correction. The current execution contract uses kernel flock for exclusion; stale status text alone is not locking authority. This observation does not override the present live-lock stop.

`temp/.fundamentals_admin_production.lock` retains informational owner text for original PID `2015282`, started `2026-10-14T01:30:11Z`. The current Production lock contract tolerates stale owner text and keeps persistent lock files. No current kernel holder was shown. The file was left intact.

## Publication state snapshot

The current Fundamentals journal reports:

| Field | Value |
| --- | --- |
| state | COMPLETED |
| current_publication_step | COMPLETED |
| generation_activation_state | ACTIVATED_AND_VERIFIED |
| postflight_state | PASSED |
| rollback_recovery_state | NOT_REQUIRED |
| production_run_id | `20261013T042603Z_refresh_fundamentals_3d9f10e1f3f2_production_25d220d5` |

The active manifest names generation `refresh_20261013T042603Z_refresh_fundamentals_3d9f10e1f3f2_production_25d220d5`, matching the journal. These are **pre-existing October 13 results**, not outcomes of this recovery task. Full manifest-role health, candidate lanes, backup inventory and the remainder of R1 publication validation were not revalidated after the stop. Consequently, full R1 publication cleanliness is **not certified** here despite the clean journal fields.

## Interrupted EC artifacts

Read-only filesystem inspection confirms the preserved pair:

```
temp/analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261006_20261013__20261014T042318Z.sqlite
temp/analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261006_20261013__20261014T042318Z.sqlite-journal
```

The backup remains **0 bytes** and unusable; its journal is **1,024 bytes**. Neither was opened as a database, restored, consumed or deleted. Interrupted EC backup used: **NO**. Its authoritative-reference/open-handle checks were not completed after the R1 stop; R1.5 is not certified PASS. No new backup was created.

## R2 / R3 results

R2: **NOT_RUN — R1 STOP**. No standalone EC command was invoked. The intended interval `2026-10-06 ... 2026-10-13` remains incident context only; the effective required interval has **not** been recomputed. EC terminal result, parity/coverage and recovery requirement remain **UNKNOWN for recovery**, with no new terminal operation evidence.

R3: **NOT_RUN — R1 STOP**. No Full workflow parent, Preview, Test or Production operation was created. Changed ticker count, review_required, global blockers, Production authorization and new workflow postflight/recovery results are **NOT_EVALUATED**. No publication or rollback-backup cleanup occurred. Existing rollback backups were neither removed nor inventoried in this stopped attempt. The previous October 13 workflow report remains the latest known report from the incident audit.

## R4 readiness and historical integrity

Final readiness classification: **NOT_READY_MANUAL_RECOVERY_REQUIRED**. This means the requested recovery cannot proceed while the verified live execution-lock conflict exists; it does not establish a need to restore production or delete any lock. The owner must be identified and its operation allowed to finish through normal application controls before a fresh R1 preflight. Do not blindly terminate it or assume its lock is stale.

| Readiness item | Final observation |
| --- | --- |
| Scheduler lock before / after | HELD / HELD by PID 52552 |
| Production lock before / after | No kernel holder observed / no kernel holder observed; no acquisition attempted |
| Taxonomy lock before / after | Authoritative file absent / absent; no acquisition attempted |
| Timer | `stock-update-scheduler.timer`, active and enabled |
| Next normal trigger | **2026-10-15 04:30:00 EEST** |
| Schedule | Existing `*-*-* 04:30:00`, unchanged |
| October 14 scheduler summary | Still absent in configured `logs`; no fabricated or backdated summary |
| Source changes | NO |
| Runtime mutations / scheduler or stage reruns | NO |
| Tests / full suite | NO |
| Push | NO |

The incident report, original market/datacenter logs and incomplete EC artifacts were preserved. This documentation does not relabel a recovery operation as a scheduler run.

## Follow-up required

Identify the application's active database-update operation from its normal UI/status evidence and allow its legitimate work to terminate. Then restart the defined R1 preflight, verifying all three lock contracts, stale status handling, publication health and interrupted-artifact references before EC. Do not infer permission to bypass R1 from this report. If no supported stale-status reconciliation path can be established where required, stop for a separate implementation phase, as the recovery request specifies.

Only this recovery report is committed. Existing runtime journal changes, manifests/generations, research, repair scripts, outputs and other unrelated worktree files are excluded. This commit records a blocked recovery, not successful completion.
