# RC-SC-PRICE-04 — read-only cutover diagnostics

Observed 2026-11-01; final verification 20:27 Europe/Helsinki (EET, UTC+02).
RC inspected HEAD: `32999950edf9a2cf7e357aded362283faefcefb2`.
StockCore inspected/unchanged HEAD: `e85995a14ff3b6665b2bd5438d57dca09839e08c`.
Both match PRICE-03. StockCore worktree is clean; RC's unrelated modifications
were preserved. This commit adds this report only. No cutover was performed.

## Decision

| Item | Classification | Observed basis |
| --- | --- | --- |
| RC automatic timer | **READY** | Loaded, disabled, inactive/dead; user has disabled the independent trigger |
| RC service state | **FAILED** | Loaded/static, failed/failed, Result=exit-code, process exited 1 |
| Previous failure root cause | **CONFIRMED** | Fundamentals Preview global review blockers propagated FAILED after both market stages succeeded |
| RC StockCore provider deployment | **NOT CONFIGURED** | Code/import boundary available; effective service ExecStart lacks `--stockcore-prices` |
| StockCore handoff activation | **DISABLED** | Explicit activation file absent; absence is disabled by implementation |
| Overall cutover | **BLOCKED** | Bridge selection, automatic Source owner, skip state and controlled acceptance remain outstanding |

The previous failure is an intentional application safety stop on recorded
Fundamentals evidence, not evidence of a scheduler launch/locking defect. Whether
those financial review items have since been resolved was not re-evaluated here.
There is no demonstrated clean later service execution or live bridge acceptance.

## Actual systemd state and invocation

`systemctl --user show` returned:

```text
stock-update-scheduler.timer
LoadState=loaded  UnitFileState=disabled
ActiveState=inactive  SubState=dead  Result=success
DropInPaths=  NeedDaemonReload=no

stock-update-scheduler.service
LoadState=loaded  UnitFileState=static
ActiveState=failed  SubState=failed  Result=exit-code
ExecMainCode=1  ExecMainStatus=1
ExecMainStartTimestamp=Sun 2026-11-01 04:30:56 EET
ExecMainExitTimestamp=Sun 2026-11-01 05:34:43 EET
InvocationID=37366110e15540aa947a676020b6ba43
DropInPaths=  NeedDaemonReload=no
CanStart=yes  RefuseManualStart=no
ConditionResult=yes  AssertResult=yes  Restart=no
```

ExecMainCode 1 is CLD_EXITED; the process exited with status 1 rather than being
killed by a signal. The terminal journal explicitly records
`code=exited, status=1/FAILURE` at 05:34:43.626998 EET.

The effective service is the single fragment
`/home/kalle/.config/systemd/user/stock-update-scheduler.service`, Type=oneshot,
with no drop-ins:

```text
WorkingDirectory=/home/kalle/projects/rawcandle
Environment=PYTHONPATH=/home/kalle/projects/rawcandle
ExecStart=/usr/bin/python3 /home/kalle/projects/rawcandle/rawcandle/cli/run_stock_update_scheduler.py --config /home/kalle/projects/rawcandle/scheduler_config.json
```

The bridge flag is absent, so this invocation selects the existing Yahoo adapters
for both configured markets, OMXH then USA. The unit description still mentions
OMXS; actual market selection comes from the JSON and run receipts.

The executable, working directory, CLI script, PYTHONPATH directory and config
all exist and are readable/searchable as appropriate. With that PYTHONPATH and
`/usr/bin/python3` (3.10.12), an import-only, network-denied `python3 -B` probe
successfully loaded `services.stockcore_price_provider.source_contract` and the
canonical `stockcore.prices.PriceReader` plus required contract symbols from
`/home/kalle/projects/stockcore/stockcore`. No factory/history/Store instance or
CLI main was invoked. This proves the current import boundary, not per-ticker
qualification or successful runtime execution.

The service has Requires=basic.target/app.slice and no timer Requires/BindsTo/
PartOf relationship. Its loaded unit is unmasked and CanStart=yes; the disabled
timer does not disable this static service. A failed state alone is not a mask.
On-demand startability is supported statically; a successful start was **not**
tested, and no reset-failed was issued.

## Exact failure chain

The last 200 service journal entries, the identified invocation's short opening
window and its exact application receipts agree:

1. systemd started the process at **04:30:56.617345 EET**. Scheduler status/summary
   record **04:30:58–05:34:43 EET**, proving the scheduler CLI ran.
2. OMXH, **04:30:59–04:32:17**: OK, exit 0, 98 checked, zero ticker failures.
3. USA, **04:32:17–05:20:36**: OK, exit 0, 4524 checked, zero ticker failures,
   seven OHLCV rows inserted in that historical invocation. These are prior-run
   facts; this diagnostic task performed no writes.
4. Technical relevance: SKIPPED_EXISTING_RUN/RUN_ID_ALREADY_EXISTS, no error.
   Datacenter: OK (audit WARN). EC: SKIPPED/NO_EC_CATCHUP_NEEDED, no error.
5. Fundamentals FULL_WORKFLOW began **05:21:28**, stopped at Preview after
   approximately 773 seconds: STOPPED/GLOBAL_BLOCKER, four global blockers,
   Test and Production not authorized/invoked, Production database writes 0.
   Its own recorded process exit code is **3**. P/B auto-continuation was skipped
   as UNSAFE_FINANCIAL_RESULT/GLOBAL_BLOCKER_PRESENT.
6. The scheduler summary reports fundamentals status FAILED and overall FAILED.
   `runner.run_scheduler_config` propagates a FAILED Fundamentals summary to
   overall FAILED; the CLI returns 1 whenever overall status is not OK.
   systemd accurately retained that exit-code failure at **05:34:43 EET**.

The four global-review items recorded by the workflow report are:

| Ticker | Recorded issue codes |
| --- | --- |
| BBAI | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION |
| MIR | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION; BOUNDARY_CHRONOLOGY_INCONSISTENT; INTERIOR_SOURCE_KEY_REMOVAL; SAME_FISCAL_SOURCE_KEY_REPLACEMENT |
| OSK | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION; BOUNDARY_FISCAL_WINDOW_TOO_SHORT; OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW |
| SNDK | SOURCE_PAYLOAD_KEY_REGRESSION |

These are the report's global blockers, distinct from its 79 local held items.
No lock collision caused this failed invocation: both market stages ran and the
downstream receipt completed with a safety decision. There is no evidence here
of a Python traceback, malformed config, systemd executable failure, timeout or
operator interruption causing the terminal status. Historical Yahoo no-data
warnings occur in the journal but did not make either market stage fail.

Evidence paths were followed from the application, not selected by guessed dates:

- Current status: `logs/stock_update_scheduler_status.json` — is_running=false,
  last_status=FAILED, error=null; points to the exact summary below.
- Summary: `logs/stock_update_scheduler_summary_20261101T023058Z.json`.
- Summary-referenced market logs: `logs/stock_update_omxh_20261101T0230Z.txt` and
  `logs/stock_update_usa_20261101T0232Z.txt`.
- Summary-referenced financial report:
  `fundamental_reports/admin_runs/20261101T032128Z_refresh_fundamentals_d00eb7239fed_full_workflow_3680ea88/workflow_report.md`.
  That same run's artifact manifest, workflow result and exit_code corroborate
  the STOPPED result. Its authoritative Preview child is
  `20261101T032128Z_refresh_fundamentals_42af299507b0`.

## StockCore readiness and competing triggers

The explicit handoff file
`/home/kalle/projects/stockcore/runtime/evidence/daily_yahoo/rawcandle-handoff-config.json`
is absent: **DISABLED**, not malformed or implicitly enabled. Existing code checks
the disabled/inactive RC timer at enablement and again before dispatch. The timer
gate now passes, but the installed service command would fail
RC_SERVICE_BRIDGE_NOT_SELECTED. No activation or dispatch helper was called.

Source schedule was inspected in a short closed SQLite URI `mode=ro` transaction
with query_only: yahoo-daily enabled=0, time **23:45 Europe/Helsinki**, nine explicit
operator exclusions; updated 2026-10-31 16:39:39.949358 EET. The existing named
Windows owner was inspected using its **Inspect** action only:

- One `StockCore Daily Yahoo` task at `\`, Enabled=false, State=Disabled,
  timezone FLE Standard Time, daily trigger 23:45.
- Action: `C:\Windows\System32\wsl.exe` with arguments
  `--distribution Ubuntu-22.04 --user kalle --cd /home/kalle/projects/stockcore --exec /home/kalle/projects/stockcore/.venv/bin/python -B -m tools.daily_yahoo run`.
- Last host run 2026-10-30 16:45:01 EET, LastResult=0. A displayed NextRun of
  2026-11-01 23:45 does not make this disabled task active.

P03 and P04 integration markers are enabled and root/format-qualified. P04's
marker records VERIFIED recovery/restore_pass=true; backups were not requalified
by this diagnostic. Active marker is IDLE. Latest dated workflow is
`runtime/evidence/daily_yahoo/2026-10-31/workflow.json`, manual initiation at
22:25:26 EET, finished 22:29:31 EET, overall PARTIAL. Embedded Source has complete
metrics, qualified population 4257, accepted 4250, held 72, failed/unattempted 0;
P03 calculated 4248/current 1, held 228, failed/not_started 0;
P04 SKIPPED_CURRENT/current 4249, held 228, failed/not_started 0.
These are stage-specific counts, not additive population accounting. Usable
historical work exists; it is not proof of the next scheduled occurrence's
eligibility. Manual work is explicitly ineligible for the RC handoff.

The normal hook remains after Source/P03/P04 finalization and conflicting lock
release, requesting a nonblocking service start only for durable reconciled
scheduled work with both derived stages usable. Hold-only partial work is allowed;
failed/unfinished/unknown/manual work is rejected. Requesting is not completion.

Scoped duplicate-trigger checks found:

- RC user timer disabled; direct reverse dependencies list only the service itself.
- Only `rawcandle-forecast-daily.timer` remains in the user timer list. Its service
  runs the forecast CLI, not this stock scheduler.
- Direct-reference searches of user/local system systemd configuration found only
  the specified stock-update service; no additional reference in /etc/crontab or
  /etc/cron.d. User crontab: none.
- Windows tasks named `*RawCandle*` returned only `RawCandle Temp Cleanup`, whose
  action calls `/home/kalle/scripts/rawcandle_temp_cleanup.sh --apply`. That script
  contains none of the stock scheduler/systemctl/daily_yahoo entrypoint references
  searched. It is not a discovered stock-update trigger.

No duplicate automatic RC trigger was discovered in this bounded scope. Arbitrarily
named external tasks and future operator changes were not exhaustively audited.
Manual/UI invocations remain possible; the existing exclusive scheduler flock
continues to reject overlap. Restoring RC's timer while handoff is active must
remain prohibited. Do not alter the separate forecast/cleanup triggers.

## Remaining actions and minimal later cutover checklist — not executed

| Issue / consequence | Minimum necessary action | Code change? | Service-only config? | Controlled start needed? |
| --- | --- | --- | --- | --- |
| Recorded Fundamentals guard stopped the complete workflow | Review/requalify the four global items through their owning workflow; establish a clean accepted result without bypassing safety policy | Not indicated by this evidence; underlying review may require separate work | No; a service override cannot resolve financial evidence | Yes, to establish end-to-end acceptance after review |
| Bridge flag absent; a current start would use Yahoo for USA | Add the PRICE-03 service-only ExecStart drop-in with `--stockcore-prices`, preserving all existing arguments/environment; reload only under later approval | No | **Yes** | **Yes**; import success is insufficient |
| RC config currently skip_next_run=true; first start would skip and consume the flag | At the approved test window, use RC UI **Cancel skip**; keep automatic timer disabled | No | No; existing UI/config action | **Yes**, verify actual market execution rather than skipped success |
| Source automatic owner disabled in both DB and Windows; no normal scheduled completion can trigger RC | Enable the existing StockCore schedule through its UI during approved cutover; preserve chosen 23:45 unless the user changes it; verify host/store agreement | No | No; StockCore schedule control | Observe an approved scheduled invocation through Source/P03/P04 and handoff |
| Handoff switch absent | Explicitly enable only after timer and service guards pass | No | No; existing handoff switch | Observe one request and independently confirm RC completion |
| Static startability only; service retains failed result | Validate a controlled start and inspect exact new logs; reset-failed alone would not repair or prove anything | No proven need | No additional change beyond bridge selection | **Yes**, separately authorized |

Ordered procedure:

1. Obtain separate controlled-run/cutover approval, including the necessary provider
   calls, operational writes and downstream work; this report authorizes none.
   Requalify the recorded financial blockers and current Source/P03/P04 evidence.
2. Recheck no active work and RC timer still loaded/disabled/inactive. Do not repeat
   the user's disable action. Clear **Skip next run** with **Cancel skip** only
   when ready for the approved test; preserve all unrelated settings.
3. Apply the service-only bridge drop-in documented in PRICE-03 and reload units
   under that later approval. Verify effective ExecStart, dependencies and timer
   state. No new production source implementation is presently indicated.
4. Perform the separately authorized controlled service run; verify actual USA
   bridge counters/holds and OMXH behavior, absence of skipped success, downstream
   acceptance and service outcome. Static CanStart/imports do not replace this.
5. Recheck guards; enable the explicit StockCore handoff switch, then enable its
   existing normal daily schedule through StockCore's UI, checking stored/host
   agreement and preserving its selected time. Keep RC's independent timer off.
6. Observe a qualified scheduled Source → P03 → P04 completion, one REQUESTED
   receipt after lock release, and independent RC completion evidence. A receipt
   alone does not certify success. If restoring RC scheduling later, disable handoff
   first, wait for requested work, and use RC's **Restore automatic schedule** UI.

## Checks and isolation

Read-only checks: verified both HEADs/worktrees and PRICE-03 reports/instructions;
systemctl show/cat/dependencies/timer/unit-file queries; bounded journal windows;
exact status/summary/referenced run artifacts; guarded import-only deployment
probe; one closed read-only schedule query; activation markers/latest workflow;
named Windows task Inspect and RawCandle-name search; direct config/cron searches.
Initial sandbox bus/Windows/crontab reads required read-only escalation.
No live scheduler or `tools.daily_yahoo`
command, unit mutation/reset/start, provider request, calculation or repair ran.

Only this maintained report and ignored RC diagnostic staging were written.
Operational config, installed unit files and the pre-existing tracked journal
matched this task's starting SHA-256 values at verification. StockCore was not
modified. No automated test suite was run for this diagnostic-only report.
**Production changes: NONE. Push: NO.**
