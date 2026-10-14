# Scheduler incident: 2026-10-14

## Finding and limits

The daily scheduler started, completed both market updates and the datacenter command, and entered EC historical backfill. Execution was interrupted during creation of the EC pre-write backup across a WSL boot boundary. EC never returned a terminal result; Fundamentals Full workflow and scheduler summary publication were never reached. The UI correctly selects the October 13 summary because it is the newest persisted summary.

The original process exit code, terminating signal, exact termination instant, and reason the WSL instance restarted are **not available in the retained Linux records**. They must not be represented as a successful exit or as a proven systemd timeout, OOM kill, Python exception, or application defect. The boot transition and interrupted backup establish the execution interruption; host-side evidence would be needed to identify its initiator. Acceptance criteria requiring an exact original exit status cannot be fully satisfied from these records.

Audit observations were collected on October 14, approximately 12:06–12:11 EEST, against repository HEAD `0608c67e84961a019720ddcb4209625096b805d0`. Times below are Europe/Helsinki EEST (UTC+03:00), with UTC explicitly identified where used. All operational inspection was read-only. No scheduler locks were acquired as probes, DBs opened for recovery, stages invoked, tests run, or runtime files changed by this audit.

## Invocation and systemd evidence

| Item | Evidence |
| --- | --- |
| Timer | `stock-update-scheduler.timer`, installed and active; `OnCalendar=*-*-* 04:30:00`, `Persistent=true` |
| Exact timer trigger | `LastTriggerUSec=Wed 2026-10-14 04:30:08 EEST` |
| Service | `stock-update-scheduler.service`, `Type=oneshot` |
| Service start request | Journal timestamp `2026-10-14T01:30:08.389923Z` / `04:30:08.389923 EEST`: “Starting RawCandle stock update scheduler (omxh + omxs)...” |
| Command | `/usr/bin/python3 /home/kalle/projects/rawcandle/rawcandle/cli/run_stock_update_scheduler.py --config /home/kalle/projects/rawcandle/scheduler_config.json` |
| Working directory | `/home/kalle/projects/rawcandle` |
| Original PID | `2015282`, corroborated by service journal and production-lock owner text |
| Invocation ID | `741332f6cee343c08d678c0f0c667b49` from journal `_SYSTEMD_INVOCATION_ID` |
| Original boot ID | `ae2d0793733d464883c4605704940fdf` |
| Scheduler run identity | `started_at_utc=2026-10-14T01:30:10Z`; expected summary basename `stock_update_scheduler_summary_20261014T013010Z.json` |
| Original terminal service result/exit | **Unavailable**, no retained completion, failure, timeout, signal, or exit-status record |
| Current service state | `inactive/dead`, `MainPID=0`, empty invocation ID; `ExecMainStartTimestamp=n/a`, `ExecMainExitTimestamp=n/a`, `Result=success`, `ExecMainCode=0`, `ExecMainStatus=0` |
| Interpretation of current result | Current boot's unexecuted/reset service state; **not** evidence of October 14 run success |
| Limits | `TimeoutStartUSec=infinity`, `RuntimeMaxUSec=infinity`, `TimeoutStopUSec=1min 30s`; no evidence that any limit terminated this run |
| Next trigger | `Thu 2026-10-15 04:30:00 EEST` |

The description still says “omxh + omxs”; the executed configuration and logs show `enabled_markets=[omxh, usa]`. This label did not control execution.

Bounded service journal inspection (`04:20–12:15 EEST`) returned 321 records, with one scheduler invocation ID and one original boot ID. The final service record is a Yahoo warning at `07:20:36.200885 EEST`; captured datacenter output is persisted separately. No second scheduler invocation or morning overlap was found. Historical process inventories do not exist, so this is an evidence-based absence of recorded overlap, not a retrospective inventory of every process.

`journalctl --list-boots` identifies the following transitions:

| Boot | Retained interval / relevant evidence |
| --- | --- |
| `ae2d0793733d464883c4605704940fdf` | Started October 3; last retained journal entry October 14 `07:20:36 EEST` |
| `2f10b6c4cfb74311bb5b16f7e7ac1f95` | New kernel boot at `07:23:35.540896 EEST`; first systemd boot records at `07:23:36`; later orderly shutdown records at `07:48:45` and `07:51:52` |
| `8ae919934c9e4d75bf46314904a191c4` | Current boot, first retained records at `08:03:54 EEST` |

The new kernel explicitly identifies `6.18.33.2-microsoft-standard-WSL2`, `WSL_ROOT_INIT=1`, and WSL version `2.7.11.0`. The original boot's journal does not contain an orderly shutdown or scheduler termination record in the bounded interruption window. Its last retained journal entry is **not** the process stop time: filesystem artifacts prove execution continued until at least `07:23:27.635964 EEST`.

Execution therefore lasted at least approximately 2 h 53 min 19 s from the service start request, and ceased before the new boot at approximately 2 h 53 min 27 s after that request. Exact duration is unavailable.

## Stage timeline

All artifact paths in this report are relative to `/home/kalle/projects/rawcandle` unless absolute.

| Stage | Started / completed | Start → end, EEST | Artifact / terminal evidence |
| --- | --- | --- | --- |
| OMXH market (task calls it OMHX) | YES / YES | `04:30:11 → 04:34:26` | `logs/stock_update_omxh_20261014T0130Z.txt`; `SUMMARY status=OK`, errors=0, warnings=0 |
| USA market | YES / YES | `04:34:26 → 07:21:17` | `logs/stock_update_usa_20261014T0134Z.txt`; `SUMMARY status=OK`, errors=0, warnings=0 |
| Standalone technical relevance | Execution lies between USA and datacenter under current control flow; independent terminal result not persisted | Within `07:21:17–07:21:51`; exact timestamps unavailable | No terminal scheduler summary. Datacenter's own technical relevance substage did complete, but does not prove the standalone post-step result |
| Datacenter pipeline | YES / YES | `07:21:51 → 07:23:18` | `logs/datacenter_pipeline_usa_20261014T0421Z.txt`; subprocess returncode=0; pipeline/audit status WARN; scheduler wrapper maps to OK |
| EC source layer | YES / NO | Backup initiated in second `07:23:18`; backup file last modified `07:23:27.635964`; termination before new boot `07:23:35.540896` | **STARTED_NO_TERMINAL_ARTIFACT**; incomplete backup and journal below; no EC text log |
| Fundamentals Full workflow | NO / NO | Not reached | **NOT_STARTED**; no October 14 parent, Preview, Test, Production, workflow report or generation |
| Scheduler summary finalization | NO / NO | Not reached | No October 14 terminal or partial summary found |

Market counts corroborate successful completion: OMXH checked 98 tickers, updated 96, skipped 2, failed 0; USA checked 4,524, updated 4,238, skipped 286, failed 0. Service-journal “possibly delisted; no price data” messages are provider diagnostics, not the first causal failure: both persisted market results report OK. Market status allowed downstream continuation.

Datacenter log headers contain actual start/end timestamps, executed command and return code, not merely filename timestamps. All 16 stage-result lines show `status=OK`, including report generation/copy. The audit has `daily_ready=NO`, `weekly_ready=YES`, `non_ok_group_count=1`, `synthetic_non_ok_count=1` and `validation_status=WARN`; final `pipeline_status=WARN`, empty stderr. Stage 2 completed the planned dates October 6, 7, 8, 9, 12 and 13, `stage2_retry_required=false`.

In `rawcandle/scheduler/runner.py`, `_run_datacenter_post_step` returns FAILED on a nonzero subprocess return code and returns OK on zero. WARN audit output does not change this wrapper result. The EC wrapper is called immediately after it. The configuration enables EC and allows the successful USA market path, so there was no contractual datacenter gate stopping continuation.

## EC evidence and first causal interruption

Two files establish that EC actually started, independently of its missing text log:

```
temp/analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261006_20261013__20261014T042318Z.sqlite
temp/analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261006_20261013__20261014T042318Z.sqlite-journal
```

The backup is **0 bytes**, mtime `2026-10-14T04:23:27.635964Z`. Its journal is **1,024 bytes**, mtime `2026-10-14T04:23:18.407602Z`. No SQLite connection was opened on these artifacts; they were inspected only as filesystem entries. This backup is incomplete and must not be treated as a restore source.

`rawcandle/cli/run_ec_source_layer_backfill.py:_backup_filename` creates exactly this name from the backup initiation time. `_create_backup` opens the source read-only, opens the destination and runs SQLite `source.backup(target)`. The backfill calls this before its EC loading/replacement loop. The date range also matches datacenter's downstream dirty interval. Thus EC reached **HISTORICAL_BACKFILL / pre-write backup creation** at `07:23:18`, with no evidence of reaching the later EC mutation loop. This establishes the stage more precisely than an absent log could.

`runner.py:_run_ec_source_layer_refresh_post_step` chooses an EC log path on entry but writes the actual file in its terminal `_write_log` helper, after a skip, exception result, or backfill/refresh return. An interruption inside backup creation therefore leaves no `ec_source_layer_usa_20261014...txt` file. The expected basename would begin `ec_source_layer_usa_20261014T0423Z` (collision suffix if needed). A normal skip would also write a log; this is not evidence of SKIPPED_BY_CONTRACT.

The first established causal interruption is loss of the original execution environment across the WSL boot boundary while the backup was unfinished. Missing Fundamentals and summary artifacts are downstream consequences. The retained evidence does not identify whether Windows/WSL was explicitly restarted, shut down, crashed or terminated for another host-side reason. There is no persisted Python traceback, summary-writer exception, OOM record, systemd timeout or overlapping-lock rejection explaining this original invocation. No code defect is established by this audit.

## Fundamentals evidence

Configured admin roots are defined in `rawcandle/fundamentals/admin/artifacts.py`: `fundamental_reports/admin_runs` and `temp/fundamentals_admin_phase13g1`. Inspection found no October 14 run directories or matching nested dated artifacts. `data/fundamentals_generations` also has no October 14 generation and no `.preparing` entry. The scheduler calls Fundamentals only after the EC wrapper returns, which did not occur here.

The latest known Full workflow remains:

```
fundamental_reports/admin_runs/20261013T041843Z_refresh_fundamentals_d00eb7239fed_full_workflow_0538b308/workflow_result.json
fundamental_reports/admin_runs/20261013T041843Z_refresh_fundamentals_d00eb7239fed_full_workflow_0538b308/workflow_report.md
```

Its persisted outcome is COMPLETED, started `2026-10-13T04:18:43Z`, completed `2026-10-13T04:35:56Z`. The UI normalizes the report name to `fundamentals_full_workflow_20261013T043556Z.md`; this is a display name for the referenced workflow artifact.

`data/.fundamentals_admin_publication_journal.json` is terminal: `state=COMPLETED`, `current_publication_step=COMPLETED`, `generation_activation_state=ACTIVATED_AND_VERIFIED`, `postflight_state=PASSED`, `rollback_recovery_state=NOT_REQUIRED`, updated `2026-10-13T04:35:55Z`. Its production ID is `20261013T042603Z_refresh_fundamentals_3d9f10e1f3f2_production_25d220d5`. The active-generation manifest references that same generation. There is no observed nonterminal Fundamentals publication or incident-specific candidate lane.

## Summary publication and UI

Targeted recursive searches found **zero** `stock_update_scheduler_summary_20261014*.json` files under `logs`, `fundamental_reports`, `swing_reports` and configured EC backup root `temp`. A further `logs/*summary*20261014*` recursive search found no differently suffixed or partial summary. No summary was created by this audit. This proves absence in the inspected configured roots at audit time; it cannot prove a file was never externally removed.

The newest existing summary is `logs/stock_update_scheduler_summary_20261013T013010Z.json`, with `overall_status=OK`, `finished_at_utc=2026-10-13T04:35:56Z`, EC BACKFILL_COMPLETED and Fundamentals COMPLETED.

In `runner.py:run_scheduler_config`, summary publication follows market updates, technical relevance, datacenter, EC and Fundamentals, then result construction. `_write_summary_json` writes the start-time-named JSON using `Path.write_text`; terminal scheduler status is written afterward. Returned failure results can also reach summary publication: it is **not success-only**. However, an uncaught exception before finalization goes through an outer `except BaseException` that writes FAILED scheduler status and re-raises **without writing a summary**. Process/environment destruction bypasses even that handler. There is no durable in-progress scheduler summary or boot-reconciliation path in this function. The observed partial logs, stale RUNNING status and absent summary are consistent with its interruption behavior.

In `dev_tools/stock_update_scheduler_ui.py:load_latest_scheduler_summary`, candidates are sorted descending by filename and the first JSON-decodable file is selected. The artifact browser discovers market, datacenter and EC logs independently; `scheduler_log_artifacts` adds the Fundamentals report referenced by the selected summary. Therefore October 14 text logs and an October 13 Latest summary/report can legitimately coexist.

Classification: **UI CORRECT, scheduler run incomplete**. Refresh cannot find an absent October 14 summary. The view has lazy view/log caches and explicit force-refresh invalidation, but no cache defect is needed to explain this state. The artifact list exposes newer dated filenames; the Latest summary exposes its path. There is no explicit comparison warning that artifact dates exceed summary date in the inspected rendering path. Running-state text trusts the persisted scheduler status, so it can show “running” after a reboot even though this original process is gone. That is a stale runtime record, not evidence of a hidden newer summary.

## Residue and next-run safety

| Check | Read-only observation |
| --- | --- |
| Scheduler status | **Stale/nonterminal YES**: `logs/stock_update_scheduler_status.json` still has `is_running=true`, `last_status=RUNNING`, `current_market=usa`, start `2026-10-14T01:30:10Z`, null finish/error/summary. This market field is not a stage heartbeat |
| Original production owner text | `temp/.fundamentals_admin_production.lock` still names PID 2015282 and `2026-10-14T01:30:11Z`; **stale metadata YES** |
| Original kernel lock / orphan | **NO** original surviving process or held lock found; reboot releases kernel locks. Lock files are intentionally persistent; their existence does not imply an active lock |
| Current scheduler lock | `lslocks` shows FLOCK on `logs/stock_update_scheduler.lock` held by PID **52552**, `/home/kalle/projects/rawcandle/venv/bin/python main.py --port 8888`, started **11:59:49 EEST** on the current boot. It also holds analysis DB POSIX locks and open analysis DB/WAL/SHM descriptors. This is a live application process, not the original scheduler orphan |
| Current admin production lock | No holder shown by `lslocks`; stale owner text has no locking authority (`production_transaction.py:production_lock`) |
| Other lock files | `logs/.stock_update_scheduler.lock` and older Fundamentals phase lock files exist; no corresponding held locks shown. No files removed |
| EC residue | Incomplete backup plus destination journal described above, retained intact; no October 14 terminal EC artifact |
| Datacenter residue | Terminal datacenter log; Stage 2 explicitly says retry_required=false. No incident-specific datacenter temporary artifact identified among configured `temp` entries |
| Fundamentals residue | Terminal October 13 journal; no October 14 candidate/generation/preparing lane observed |
| Partial summary | None found |
| Production analysis DB | File exists; observed WAL size=0 and SHM size=32,768 bytes. Currently open by the live application. These sizes are not an integrity check; no recovery, checkpoint or integrity scan performed |

**Dangerous operational residue: NO demonstrated incident-caused production recovery blocker.** The incomplete EC backup is unusable, but the source code places it before EC writes. It must not be selected for restoration. This audit did not establish whole-DB integrity or diagnose the work currently holding the live application lock. Existing unrelated worktree artifacts were not attributed to this incident.

**Next scheduled run safety: UNKNOWN / NEEDS_MORE_EVIDENCE.** There is no demonstrated requirement to clear a stale kernel lock or roll back Fundamentals. Nevertheless, the application currently holds the scheduler execution lock; a scheduler attempt while it remains held will be rejected before the run body and summary creation. The observed lock holder's operation and expected release time are unknown. Host/WSL interruption cause and future uptime are also unverified. It would be unsound to assert unconditional safety or inevitable recurrence. Stale RUNNING JSON and stale owner text alone do not block acquisition: the current contract uses kernel flock, not those records, as execution authority.

## Evidence scope and recommended separate phase

Read-only sources: exact user unit files, scheduler config, bounded service/invocation and interruption-window journals, boot list, current service/timer properties, host process/descriptor/kernel-lock snapshots, named logs, scoped dated artifact searches, selected prior Fundamentals JSON, and the narrow scheduler/backfill/UI/artifact/locking functions referenced above. No broad repository or unrelated journal scan was used. Audit snapshots are time-specific; the live application can change its locks after observation.

Recommended next phase: a separate **host/WSL interruption and current lock-owner investigation**, obtaining host-side records for approximately `07:23 EEST` and identifying the live application's update operation before choosing any recovery or rerun. Inspect production/EC consistency in a separately authorized, bounded read-only validation if needed. Do not restore the zero-byte backup. A separate implementation proposal may address durable stage-start/termination evidence and stale status reconciliation after reboot; this audit does not establish a source defect or authorize implementing it.

Only this report is to be committed. Existing tracked runtime-journal changes and untracked research, repair, generation, reports and output files remain outside the commit. No source/config/unit edits, runtime mutation, cleanup, scheduler/stage rerun, tests/full suite or push were performed.
