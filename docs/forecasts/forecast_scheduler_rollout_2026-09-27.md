# Forecast Scheduler Rollout (2026-09-27)

## 1. Restore rehearsal result

The latest valid production backup,
`backups/forecasts/forecast_20260927T185204266430Z.db`, was restored only to
`/tmp/rawcandle_forecasts_restore_rehearsal_phase7.db`. Manifest SHA-256, schema
`forecasts_v2_fiscal_links`, `PRAGMA quick_check`, every core-table count,
first/latest observation timestamps, and a representative PIT row and canonical
payload hash matched the backup boundary.

Result: `RESTORE_REHEARSAL_PASS`. Production was not replaced or modified by
the rehearsal.

## 2. Scheduler integration point

Forecasts use the independent systemd user units:

- `~/.config/systemd/user/rawcandle-forecast-daily.service`
- `~/.config/systemd/user/rawcandle-forecast-daily.timer`

Registration is rendered and installed by `rawcandle.forecasts.scheduler` via
`python3 -m rawcandle.cli.forecasts scheduler-install --apply`. The timer is
enabled and active. It neither imports nor orders itself against the stock
update service, OHLCV success, Fundamentals publication/recovery, or DC jobs.

## 3. Daily command

The service invokes the existing orchestration boundary exactly once:

```bash
/usr/bin/python3 -m rawcandle.cli.forecasts daily --max-symbols 100
```

Scheduler code does not duplicate preflight, backup, universe selection,
acquisition, identity resolution, linking, reconciliation, or reporting.

## 4. Schedule time

The timer runs daily at `07:30 Europe/Helsinki`. The existing stock/OHLCV timer
starts at 04:30, and its latest observed production run finished around 05:22.
The selected slot provides about two hours of practical separation, runs after
the completed US trading day, and avoids coupling either job's status.

## 5. Initial bound

The approved rollout is exactly `max_symbols=100`. Selection takes the first
100 eligible symbols in deterministic company order from the active
`fundamentals_operational_universe_active_version/member` authority. There is
no forecast watchlist or manual symbol cherry-picking. `--max-symbols` remains
mandatory and there is no full-universe default.

## 6. Expected requests

The rollout performs 100 symbols times three forecast families, or 300 family
requests per invocation. The pacing floor is 150 seconds at 0.5 seconds, before
network latency, bounded request retries, persistence, linking, and reporting.

## 7. Timeout

The systemd service has `TimeoutStartSec=1800` (30 minutes). Normal operation is
expected to finish well inside this window; the network-enabled controlled run
took about 2.5 minutes. On timeout systemd
terminates the one invocation. SQLite transactions protect individual writes,
persisted attempts remain available, and no full-run retry is configured.

## 8. Failure policy

DB integrity/schema failure maps to `DB_PREFLIGHT_FAILED`; backup failure maps
to `BACKUP_FAILED`; fatal universe resolution fails before Yahoo acquisition.
After acquisition starts, individual provider, identity, linking,
reconciliation, and reporting failures preserve completed work and produce a
daily `PARTIAL` result. A clean bounded run is `SUCCESS`.

CLI exit codes are 0 for `SUCCESS`, 2 for `PARTIAL`, and 1 for pre-acquisition
or unhandled `FAILED`. Compact output includes detectable acquisition counts,
`RATE_LIMITED`, `UNKNOWN_SCHEMA_DRIFT`, `IDENTITY_UNRESOLVED`, and
`FISCAL_AMBIGUOUS` signals when present.

## 9. Retry ownership

Only the transport owns bounded request-level retries. The timer invokes the
daily command once and the service has no `Restart=` policy. `PARTIAL` is not
automatically rerun. An operator reviews the run and may use the existing
explicit resume contract where attempts are genuinely missing; completed
failed attempts are not silently replayed.

## 10. Overlap prevention

Every daily workflow takes a nonblocking forecast-specific `flock` beside the
forecast DB for its whole invocation. A second scheduled or manually invoked
daily writer fails with `OVERLAP_ACTIVE`. Read-only health, report, and universe
preview commands do not take this lock.

## 11. Backup before acquisition

The daily workflow verifies production and creates one SQLite-safe, manifested,
immutable backup before universe resolution or acquisition. Backup failure is
fail-closed. The controlled run created
`backups/forecasts/forecast_20260927T185204266430Z.db` with `quick_check=ok` and
size 598,016 bytes.

Raw cleanup and backup retention remain separate manual operations. A later
review may schedule weekly raw cleanup and weekly retention, always retaining
their dry-run/report contract; neither is part of the daily service.

## 12. First controlled 100-symbol run

Run `ed343155a53c4e6c8dc37014c65d3c0b` used the exact service command and
selected 100 of 2,441 eligible symbols from universe version
`3b8121b74c852f08575fa1e2b70004e6`. It attempted all 300 family requests.

The reviewed daily result is `PARTIAL`: 285 `SUCCESS_CHANGED`, 6
`SUCCESS_UNCHANGED`, 3 `VALID_NO_DATA`, and 6
`MALFORMED_OR_SCHEMA_MISMATCH`, with zero unavailable, transient-failure, or
rate-limited outcomes. The six mismatches were fiscal-estimate rows without
required period/endDate strings for ABVC, AEI, AIFF, AIMD, AIV, and VAI.

An earlier sandboxed attempt, `4248b87dec5146198a00eb5a173092f5`, persisted
300 DNS transient failures. After explicit operator approval, the
network-enabled run above was a separate invocation with a new backup and run
ID. Historical health totals include both runs; rollout conclusions use only
the network-enabled run's scope.

## 13. Runtime and provider quality

The run started at `2026-09-27T19:14:19.442230Z`, finished at
`2026-09-27T19:16:51.236523Z`, and elapsed 151.794 seconds. Acquisition occupied
149.736 seconds; preflight/backup/universe and post-acquisition
link/reconcile/report work used about 2.06 seconds combined. It recorded zero
request retries, zero rate limits, 23 distinct known-ignored drift paths, and zero
unknown drift paths. Identity resolution produced 100
`TICKER_ALIAS_AS_OF`, zero ambiguous, and zero unresolved identities. With no
identity ambiguity, fiscal linking produced 376 AS_KNOWN `LINKED` rows and 376
CURRENT_RECONCILED `LINKED` rows, with zero ambiguous or unresolved links.

Family results were: earnings-history 95 changed, 2 unchanged, 3 valid-no-data;
fiscal estimates 92 changed, 2 unchanged, 6 malformed; and price targets 98
changed, 2 unchanged. Linear serial throughput projects roughly 3,705 seconds,
or 61.8 minutes, for 2,441 symbols under similar provider conditions. A
practical full-universe window should reserve at least 75-90 minutes. This is a
single observation, so concurrency or request-combining changes are not yet
justified.

## 14. Database growth

Production remained `quick_check=ok`. Across the network-enabled run, file size
increased from 917,504 to 8,167,424 bytes. It added 300 fetches, 100 identity
rows, 285 snapshots, 752 fiscal-link rows across both knowledge modes, and
671,822 raw-evidence bytes. The pre-run backup was 917,504 bytes.

After both Phase 7 attempts, production totals are 3 runs, 618 fetches, 303
snapshots, 206 identity rows, 800 fiscal-link rows, and 715,373 raw-evidence
bytes. The observed successful-run growth should be monitored over several
days because unchanged semantics will normally reuse snapshots and produce a
different growth profile.

## 15. Rollout ladder

The operator-reviewed ladder is:

```text
100 -> 250 -> 500 -> 1000 -> FULL_BOUNDED_UNIVERSE
```

The bound is never promoted automatically and the mandatory guard remains
until a later reviewed phase explicitly approves the full bounded universe.

## 16. Promotion criteria

Before each promotion, require at least five consecutive scheduled `SUCCESS`
runs at the current bound, `quick_check=ok`, verified pre-run backups, no
unknown schema drift, no recurring rate limits, and no unresolved provider
incident. Review provider failure rate, identity unresolved rate, fiscal
ambiguous/unresolved rate, elapsed runtime against timeout, database and raw
evidence growth, and backup duration/size. Run count alone is insufficient.

## 17. Rollback procedure

Stop new invocations without touching history:

```bash
systemctl --user disable --now rawcandle-forecast-daily.timer
```

If a service is active, inspect it before stopping; persisted attempts remain
valid. Investigate with `health` and the run report. Do not delete runs or
snapshots. Restore production only for demonstrated database corruption, using
the reviewed restore command with `--apply-production`, which first attempts a
safety backup. Re-enable only after tests and a bounded manual command pass.

## 18. Remaining work before 250

Keep the bound at 100. Review and either accept as explicit no-data or adapt the
existing fiscal parser contract for the six observed missing period/endDate
responses without weakening unknown-schema visibility. Then collect at least
five consecutive scheduled `SUCCESS` runs and review the promotion criteria
above. Rehearse timer disable/enable and inspect journal output once. Do not
increase to 250 while the current production-quality run remains `PARTIAL`.
