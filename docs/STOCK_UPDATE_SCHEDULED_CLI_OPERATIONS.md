# STOCK_UPDATE_SCHEDULED_CLI_OPERATIONS

This document defines how to run and later schedule the manually runnable stock update CLI.

This step does not install cron.
This step does not install systemd units.
This step does not change runtime code.

## Current validated state

- service path has passed direct service smoke
- service path has passed UI opt-in smoke
- service path has passed manually runnable CLI smoke
- stale3 copied DB test restored `294` OHLCV rows
- Dow summary reported `dow_structures_updated=621`
- no duplicates were created
- default UI behavior is still legacy
- update button `on_click` was not changed

## Manual production command

Intended manual production command:

```bash
PYTHONPATH=. python3 rawcandle/cli/run_scheduled_stock_update.py \
  --osakedata-db /home/kalle/projects/rawcandle/data/osakedata.db \
  --analysis-db /home/kalle/projects/rawcandle/data/analysis.db \
  --market omxh
```

Other market examples:

```bash
PYTHONPATH=. python3 rawcandle/cli/run_scheduled_stock_update.py \
  --osakedata-db /home/kalle/projects/rawcandle/data/osakedata.db \
  --analysis-db /home/kalle/projects/rawcandle/data/analysis.db \
  --market omxs
```

```bash
PYTHONPATH=. python3 rawcandle/cli/run_scheduled_stock_update.py \
  --osakedata-db /home/kalle/projects/rawcandle/data/osakedata.db \
  --analysis-db /home/kalle/projects/rawcandle/data/analysis.db \
  --market usa
```

## Scheduler fundamentals post-step

The production scheduler entrypoint is `rawcandle/cli/run_stock_update_scheduler.py --config scheduler_config.json`. The configured scheduler run is serialized by the existing scheduler lock and runs these stages in order:

1. configured RawCandle market OHLCV updates
2. technical relevance post-step, when enabled
3. Datacenter and EC source-layer post-steps for USA, when the USA market phase is eligible
4. SwingMaster USA fundamentals post-step

The SwingMaster stage stays on the process boundary. RawCandle invokes the existing SwingMaster CLIs from the configured `swingmaster_repo_path` and does not copy fundamentals logic into RawCandle. By default the scheduler uses `/home/kalle/projects/swingmaster/.venv/bin/python`, `/home/kalle/projects/swingmaster/fundamentals_usa.db`, and the scheduler `osakedata_db_path`.

Daily behavior:

- every non-skipped scheduler run executes SwingMaster USA `check_fundamental_new_results.py` after the RawCandle pipeline finishes
- the check uses the scheduler's explicit decision date and explicitly passes all material SwingMaster result-check policy values: `swingmaster_ohlcv_stale_days=14`, `swingmaster_event_watch_days_after=5`, `swingmaster_calendar_confirmation_days_before=7`, `swingmaster_calendar_maintenance_limit=100`, `swingmaster_calendar_stale_days=45`, and `swingmaster_calendar_failure_retry_days=3` by default
- stdout, stderr, command, cwd, and exit code are captured in `swingmaster_usa_result_check_<timestamp>.txt`

Sunday behavior:

- Sunday uses the same single fresh check result from that run
- if the fresh plan has executable candidates, RawCandle invokes SwingMaster `run_fundamental_quarter_update.py --quarter-refresh-plan-json <fresh-plan>`
- old plan artifacts are never reused by the scheduler
- no weekly update is attempted when the check fails, when the check has zero candidates, or Monday-Saturday

Failure behavior:

- check failures are reported as `swingmaster_result_check_status=FAILED` and make the scheduler result failed
- Sunday update failures are reported as `swingmaster_weekly_update_status=FAILED`; candidate success/failure counts are preserved when the SwingMaster CLI emitted them
- the scheduler does not retry either SwingMaster subprocess inside the same run

The scheduler summary JSON and CLI output include a dedicated `swingmaster_*` / `swingmaster_fundamentals.*` field family, including active ticker count, 7-day watch-window count, due result checks, confirmation calls, failure retries, maintenance selected, unique provider-check tickers, maintenance backlog remaining, result-check log path, result-check plan path, and weekly update counts. The scheduler UI loads these fields from the latest summary JSON and lists SwingMaster text logs alongside market, Datacenter, and EC logs.

## Pre-run checklist

- ensure no UI stock update is running
- ensure no other CLI update is running
- make database backups before first production run
- confirm `osakedata.db` and `analysis.db` paths
- confirm both DBs are in the same data directory
- confirm enough disk space
- run first production CLI manually before adding scheduler
- check `SUMMARY status` after run

## Post-run checks

### A. Row count by market

```sql
SELECT market, COUNT(*) AS rows
FROM osakedata
GROUP BY market
ORDER BY market;
```

### B. Duplicate check

```sql
SELECT osake, pvm, COUNT(*) AS cnt
FROM osakedata
GROUP BY osake, pvm
HAVING COUNT(*) > 1
ORDER BY osake, pvm;
```

### C. Latest date per market

```sql
SELECT market, MAX(pvm) AS latest_pvm
FROM osakedata
GROUP BY market
ORDER BY market;
```

### D. Latest ticker sample for one market

```sql
SELECT osake, MAX(pvm) AS latest_pvm, COUNT(*) AS rows
FROM osakedata
WHERE market = '<MARKET>'
GROUP BY osake
ORDER BY osake
LIMIT 20;
```

## SUMMARY interpretation

- `SUMMARY status=OK` means the command completed without reported warnings or errors
- `SUMMARY status=OK_WITH_WARNINGS` means the command completed but some tickers or downstream steps reported warnings or errors
- `SUMMARY status=FAILED` means the CLI failed before or during service execution
- `tickers_updated` follows legacy-compatible semantics:
  - non-empty Yahoo history path counts as updated even if no new OHLCV rows were inserted
- `ohlcv_rows_inserted` is the actual count of new OHLCV rows inserted
- `dow_structures_updated` maps Dow `rows_inserted` when available
- warning/error counts are summary counts; details may appear in the UI summary or logs

## Logging recommendation

Safe example:

```bash
mkdir -p /home/kalle/projects/rawcandle/logs

PYTHONPATH=. python3 rawcandle/cli/run_scheduled_stock_update.py \
  --osakedata-db /home/kalle/projects/rawcandle/data/osakedata.db \
  --analysis-db /home/kalle/projects/rawcandle/data/analysis.db \
  --market omxh \
  >> /home/kalle/projects/rawcandle/logs/stock_update_omxh.log 2>&1
```

## Cron example

This example is documentation only. It is not installed by this step.

```cron
30 5 * * * cd /home/kalle/projects/rawcandle && PYTHONPATH=. /usr/bin/python3 rawcandle/cli/run_scheduled_stock_update.py --osakedata-db /home/kalle/projects/rawcandle/data/osakedata.db --analysis-db /home/kalle/projects/rawcandle/data/analysis.db --market omxh >> /home/kalle/projects/rawcandle/logs/stock_update_omxh.log 2>&1
```

Notes:

- choose a time after market data is expected to be available
- separate markets may need separate schedules
- do not overlap market jobs unless locking is implemented later

## systemd timer example

These examples are documentation only. They are not installed by this step.

Example user-level service:

```ini
# ~/.config/systemd/user/stock-update-omxh.service
[Unit]
Description=RawCandle stock update OMXH

[Service]
Type=oneshot
WorkingDirectory=/home/kalle/projects/rawcandle
ExecStart=/usr/bin/python3 /home/kalle/projects/rawcandle/rawcandle/cli/run_scheduled_stock_update.py --osakedata-db /home/kalle/projects/rawcandle/data/osakedata.db --analysis-db /home/kalle/projects/rawcandle/data/analysis.db --market omxh
Environment=PYTHONPATH=/home/kalle/projects/rawcandle
```

Example user-level timer:

```ini
# ~/.config/systemd/user/stock-update-omxh.timer
[Unit]
Description=Run RawCandle stock update OMXH daily

[Timer]
OnCalendar=*-*-* 05:30:00
Persistent=true

[Install]
WantedBy=timers.target
```

Notes:

- this document does not install these units
- paths may need adjustment
- timer should not overlap with other update jobs
- locking is not implemented yet, so avoid overlapping schedules

## Rollback / disable

- because UI still defaults to legacy, UI rollback is simply leaving `_use_stock_update_service` unset or `False`
- for CLI rollout, rollback means stop using the CLI command
- for cron, remove or comment the crontab line
- for systemd, disable the timer:

```bash
systemctl --user disable --now stock-update-omxh.timer
```

- restore DB backup if needed

## Known limitations

- no cross-process locking yet
- no dry-run mode
- no ticker filter
- no automatic scheduler installed
- CLI expects `osakedata.db` and `analysis.db` in the same directory
- service path is not yet the UI default

## Recommended next step

- run the CLI manually once against production DBs
- inspect `SUMMARY` and SQL checks
- only then install cron or systemd timer
- consider adding locking before enabling overlapping multi-market schedules
