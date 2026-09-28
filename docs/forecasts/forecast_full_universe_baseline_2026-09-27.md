# Forecast Full Bounded-Universe Baseline (2026-09-27)

## 1. Preflight

The reviewed branch was `chore/ignore-backups` at mismatch-refinement commit
`41663d80c4a2e58e682c9834af14b4013f8fc904`, with only the reviewed full-mode
source and test changes present in the worktree. The production path was
`/home/kalle/projects/rawcandle/data/forecasts.db`, schema version was
`forecasts_v2_fiscal_links`, and `PRAGMA quick_check` returned `ok`.

The timer was `disabled` and `inactive` before the run. The installed unit still
contained the temporary `daily --max-symbols 100` command and 1,800 second
timeout, so no scheduler invocation could overlap the manual baseline.

Pre-run database state was 8,167,424 bytes, 3 runs, 618 fetches, 303 snapshots,
9,016 estimates, 520 price-target rows, 400 earnings-history rows, 308 raw
evidence rows totaling 715,373 bytes, 206 identity rows, and 800 fiscal-link
rows. Observation bounds were `2026-09-27T16:27:26.679445Z` through
`2026-09-27T19:16:49.211778Z`.

## 2. Pre-Run Backup

The daily fail-closed workflow created exactly one pre-run backup before
universe resolution or Yahoo acquisition:

- database: `backups/forecasts/forecast_20260927T193934723866Z.db`
- manifest: `backups/forecasts/forecast_20260927T193934723866Z.manifest.json`
- size: 8,167,424 bytes
- SHA-256: `ec258b15446faa82d9756cd3e4c23edb762d8d3560906e2622a97e47ef355ec2`
- schema: `forecasts_v2_fiscal_links`
- quick check: `ok`

The manifest's nine core-table counts equal the recorded pre-run state.

## 3. Universe And Command

Authority was
`fundamentals_v4.fundamentals_operational_universe_active_version/member` plus
canonical active security identity. Universe version was
`3b8121b74c852f08575fa1e2b70004e6`: 2,468 candidates, 2,441 eligible symbols,
11 `ACTIVE_MULTI_SECURITY` exclusions, and 16
`HISTORICAL_RETAINED_NO_ACTIVE_SECURITY` exclusions. Duplicate routes were
removed by the accepted deterministic selection.

The exact one-time production command was:

```bash
/usr/bin/python3 -m rawcandle.cli.forecasts daily --full-bounded-universe
```

Run `e31ffae704a843ffab97dc9b25d8bf27` attempted exactly 2,441 symbols and all
7,323 expected symbol/family requests. Omission of both scope flags remains an
error, and `--max-symbols` and `--full-bounded-universe` are mutually exclusive.
The run scope persistently records the authority, version, 2,441 eligible and
selected symbols, and `FULL_BOUNDED_UNIVERSE` selection mode.

## 4. Runtime

The workflow ran from `2026-09-27T19:39:34.712217Z` to
`2026-09-27T20:41:30.366498Z`. Total elapsed time was 3,715.654 seconds; phases
were 0.057 seconds preflight/backup/universe, 3,666.087 acquisition, 27.169
AS_KNOWN linking, 21.779 reconciliation, and 0.562 reporting/health. The run
used 41.3% of the selected 9,000 second service timeout.

## 5. Acquisition Coverage

Coverage means a fetch with a usable semantic snapshot, not HTTP success.

| Family | Changed | Unchanged | No data | Unavailable | Transient | Rate limited | Malformed | Usable | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FISCAL_ESTIMATE | 2,192 | 98 | 140 | 0 | 0 | 0 | 11 | 2,290 | 93.81% |
| PRICE_TARGET | 2,338 | 103 | 0 | 0 | 0 | 0 | 0 | 2,441 | 100.00% |
| EARNINGS_HISTORY_REFERENCE | 2,277 | 101 | 63 | 0 | 0 | 0 | 0 | 2,378 | 97.42% |

The 140 fiscal no-data observations include recognized exact Yahoo empty
templates and have fetch history without semantic snapshots or fiscal links.
The 11 malformed fiscal symbols were ATLX, BHP, BIVI, BTCT, CBL, JBGS, NFE,
NUWE, SIDU, SIGA, and VEEE. Each had four rows with usable estimate values, but
one to three rows lacked required period/endDate metadata. They correctly remain
visible as unsupported usable-sparse contract cases and were not generalized to
`VALID_NO_DATA`.

## 6. Analyst And Family Detail

Both quarter and annual estimate data were available for all 2,290 usable
fiscal symbols. Analyst counts are reported as provider horizon rows, separately
for EPS and revenue because the values can differ.

| Metric | Zero | 1-2 | 3-5 | 6-10 | 11-20 | >20 | Available rows | Median | P90 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| EPS analyst count | 0 | 2,122 | 2,237 | 2,016 | 1,951 | 793 | 9,119 | 6 | 19 |
| Revenue analyst count | 48 | 1,246 | 2,359 | 2,543 | 2,221 | 743 | 9,160 | 7 | 19 |

Price targets had current-price values for all 2,441 symbols and low, high,
mean, and median values for 2,289 symbols. Currency was present for 2,440
symbols. There was no unexpected price-target contract drift, and no price
target acquired a fiscal link.

Earnings history had usable provider-reference rows for 2,378 symbols and
`VALID_NO_DATA` for 63. The usable row-count distribution was 21 symbols with
one row, 25 with two, 38 with three, 2,287 with four, and 7 with five. These
remain Yahoo references rather than canonical Fundamentals actuals.

## 7. Identity And Fiscal Links

All 2,441 successful fiscal routes resolved identity: 2,440 by
`TICKER_ALIAS_AS_OF` and one by `CURRENT_SECURITY_TICKER_AS_OF` (the
`CURRENT_TICKER` reporting category). Provider identity, ambiguous, and
unresolved identity counts were zero, for 100.00% identity resolution.

AS_KNOWN produced 9,152 `LINKED`, zero `AMBIGUOUS`, and 8 `UNRESOLVED` rows:
99.91%, 0.00%, and 0.09% of 9,160 attempted links. The unresolved rows were all
four horizons for BATRK and BELFB with `INSUFFICIENT_FISCAL_CONTEXT`; there was
no target conflict. Linked targets split evenly into 4,576 quarter and 4,576
annual rows.

CURRENT_RECONCILED produced 9,152 linked rows: 4,576 annual targets and 4,576
quarter targets. No future quarter canonical ID was yet available, so canonical
quarter attached was zero and not-yet-available was 4,576. Reconciliation did
not guess links for the eight unresolved AS_KNOWN rows.

## 8. Provider And End-Date Quality

The run had zero retries (0.00%), rate limits, transient failures, or provider
unavailable results. Its semantic snapshots contained 52,603 occurrences of
the 23 known ignored provider paths, zero unknown drift occurrences, and no
distinct unknown paths.

Across 9,152 linked fiscal rows, 9,054 were within 45 days and 98 were outside.
Median absolute difference was 2 days, P90 3 days, P95 4 days, and maximum
1,428 days. The largest concise outliers were AEHR 0q (1,428 days), AZO +1y
(390), COST +1y (389), AZO 0y (388), COST 0y (387), NB +1y (367), CPRT 0y
(366), NB 0y (365), and IBEX/LPTH 0y (364). With 98.93% within tolerance and a
4-day P95, the broad evidence supports retaining the 45-day rule while keeping
the provider outliers visible.

## 9. Database Growth And Integrity

The database grew from 8,167,424 to a final 183,111,680 bytes, an increase of
174,944,256 bytes. The workflow result immediately after acquisition was
183,095,296 bytes; persisting the reviewed universe metadata in the run scope
allocated a further 16,384 bytes. The run added one run, 7,323 fetches, 6,807 snapshots,
201,664 estimate rows, 11,690 price-target rows, 8,968 earnings-history rows,
6,877 raw-evidence rows and 15,943,054 raw bytes, 2,441 identity rows, and
18,312 fiscal-link rows. Growth was roughly 74,731 bytes per 2,341 newly
expanded symbols. This baseline is not a steady-state forecast: unchanged
daily observations reuse semantic snapshots.

Post-run schema remained `forecasts_v2_fiscal_links` and `PRAGMA quick_check`
returned `ok`. All 303 pre-existing snapshots remained. The earlier 300-row
DNS failure run and the six earlier malformed rows remained auditable. No
duplicate `(provider, family, identity, content_hash)` semantic key exists, and
no old canonical snapshot was rewritten.

## 10. PIT Verification

PIT checks passed:

- AAPL returned the original pilot fetch at the pilot timestamp, the later
  first-100 fetch before this baseline, and the new unchanged fetch afterward.
- ALG returned its first-100 fetch before the baseline and its new unchanged
  fetch afterward.
- CNDT, a symbol beyond the former first 100, returned no pre-baseline value and
  returned its new snapshot and AS_KNOWN/CURRENT_RECONCILED annual link after.
- ABVC returned no pre-baseline successful fiscal knowledge and returned the
  new `VALID_NO_DATA` fetch afterward with no snapshot and zero records.

All returned fetch timestamps were at or before the query timestamp. Price
targets remained non-fiscal.

## 11. Milestone Backup

After the integrity and PIT checks and persistent universe-scope completion,
the final post-baseline milestone backup was created:

- database: `backups/forecasts/forecast_20260927T204846170498Z.db`
- manifest: `backups/forecasts/forecast_20260927T204846170498Z.manifest.json`
- size: 183,111,680 bytes
- SHA-256: `c1b3dbb3bfdcbaa4695e695b331bdc55a605cade3c2e50d50d20ed78eabb1249`
- quick check: `ok`

An earlier post-run safety backup at `forecast_20260927T204445452888Z.db`
precedes only the universe-scope metadata completion. It and the pre-run backup
were retained, and backup retention was not applied.

## 12. Decision And Scheduler

Decision: `GO_FULL_DAILY`.

The reasons are intact DB/PIT history, complete attempted scope, no rate limits,
retries, transient failures, or unknown drift, 100% identity resolution, 99.91%
AS_KNOWN linkage, a small and correctly visible 0.45% sparse-malformed set, and
runtime well below the conservative timeout. Expected no-data and isolated
fiscal-context gaps are not STOP conditions.

The installed independent user service now runs:

```text
/usr/bin/python3 -m rawcandle.cli.forecasts daily --full-bounded-universe
```

`TimeoutStartSec=9000`; schedule remains `07:30 Europe/Helsinki`; the timer is
enabled and active. The next invocation is `2026-09-28 07:30:00 EEST`. The
service remained inactive after installation, proving that no second baseline
was triggered. There is no `Restart=` policy or OHLCV/Fundamentals publication
dependency.

## 13. Open Items And Maintenance

The 11 usable sparse responses need a separate versioned persistence-contract
review; do not weaken current metadata requirements or reclassify them as
no-data. Review the BATRK/BELFB Fundamentals fiscal context and the concise
end-date outliers without rewriting forecast history or changing the 45-day
tolerance automatically. Monitor several daily runs for steady-state storage,
runtime, rate limiting, and provider drift before considering concurrency.

Keep raw cleanup and backup retention outside the daily service. A reasonable
initial operator cadence is weekly dry-run review followed by separately
approved apply, with the milestone and pre-run backups protected under the
existing retention contract.

## 14. Production Schedule Change (2026-09-28)

By explicit operator decision, daily Yahoo forecast acquisition moved from
`07:30 Europe/Helsinki` to `14:00 Europe/Helsinki`. It continues to cover the
full bounded operational universe with this exact independent command:

```text
/usr/bin/python3 -m rawcandle.cli.forecasts daily --full-bounded-universe
```

The timeout remains 9,000 seconds. The user timer was installed through the
repository scheduler installer and verified `enabled` and `active`. Its next
invocation is `2026-09-28 14:00:00 EEST`.

The previous 07:30 timer invocation was already running when this schedule was
changed. It retained its original PID and start timestamp throughout the
installation, completed at 08:32 local time, and left the oneshot service
`failed` only because the reviewed `PARTIAL` daily result maps to exit code 2.
Enabling the updated timer did not start a service or another acquisition. The
installed unit has no `Restart=` policy and no stock/OHLCV or Fundamentals
publication dependency.

## 15. Scheduler UI Forecast Tab (2026-09-28)

The existing RawCandle scheduler UI has a separate `Forecast` tab at
`/forecast`. It follows the Stock Scheduler layout: configuration, scheduler
controls, status, latest summary, actual timer/service state, and logs. Stock
Scheduler behavior and configuration remain independent and unchanged.

The editable forecast configuration is stored in
`forecast_scheduler_config.json` and contains `forecasts_db_path`,
`fundamentals_db_path`, `log_dir`, `timezone`, and `run_time`. Time uses strict
24-hour `HH:MM` validation and timezone uses the IANA timezone database. Scope
is read-only `Full bounded operational universe`; the UI cannot edit a command,
symbol count, or watchlist.

`Save config` atomically writes the forecast config, renders the existing
`rawcandle-forecast-daily.service/.timer` units, reloads user systemd, preserves
the timer's enabled state, and never starts the service directly. `Reload
config` discards unsaved field edits. The installed command remains:

```text
/usr/bin/python3 -m rawcandle.cli.forecasts daily --full-bounded-universe
```

`Run now` launches exactly that fixed CLI workflow in the background. Existing
preflight, backup, acquisition, identity, fiscal-link, reconciliation, health,
and forecast writer-lock contracts remain authoritative. An active writer is
reported as `OVERLAP_ACTIVE`; the UI does not reproduce workflow logic.

`Skip next run` persists a forecast-only one-shot flag. The service
`ExecCondition` atomically consumes it at the next invocation, skips that one
occurrence, and returns future daily invocations to normal. `Cancel skip`
clears a pending flag without starting a run. Neither action affects Stock or
other schedulers.

The latest summary reads forecast run/report/health data. Application workflow
states `SUCCESS`, `PARTIAL`, and `FAILED` remain distinct. Systemd timer/service
state is displayed separately, because a reviewed `PARTIAL` maps to CLI exit 2
and can leave a oneshot service looking `failed` without making the workflow
`FAILED`.

Forecast logs are limited to `forecast_scheduler.log` and timestamped
`forecast_run_<UTC>.log` files under the configured forecast log directory.
The UI supports refresh, read-only Open, and Download through a filename- and
directory-constrained route. It never exposes raw Yahoo payloads or arbitrary
paths.

The tab intentionally does not expose migration, restore, cleanup apply,
backup-retention apply, log deletion/editing, Fundamentals mutation, pacing,
retry, concurrency, timeout, or scheduler-command controls.

## 16. Daily Operator Presentation (2026-09-28)

The Forecast tab begins its operational area with a compact summary of the
forecast workflow state, timer enablement, next invocation or pending skip,
last-run timing, fixed universe, and separate systemd service state. Workflow
`SUCCESS`, `PARTIAL`, `FAILED`, and `RUNNING` values continue to come only from
forecast run data. A failed oneshot is not translated into a failed workflow.
The UI explains `PARTIAL` plus systemd `failed` only when the recorded service
exit status is 2.

Latest summary is grouped into Run, Acquisition, Identity, Fiscal linking,
Provider quality, and Database sections. Active runs retain the cheap persisted
fetch count versus expected fetch count. Provider quality applies
`yahoo_known_ignored_fields_v1` and reports known-ignored and unknown drift as
separate occurrence and distinct-path counts. The 23 accepted `financialData`
paths are never presented as unknown merely because they occur in snapshot
diagnostics.

Scheduled stdout and stderr append to
`logs/forecasts/forecast_scheduler.log`; manual UI runs use timestamped
`forecast_run_<UTC>.log` files in the same configured directory. Scheduler
installation creates the scheduler log file before the first invocation so it
is discoverable immediately. The UI lists only these names, newest first, and
its read-only Open and Download route rejects directory traversal.

`forecasts_db_path`, `fundamentals_db_path`, and `log_dir` remain editable
because they are established scheduler config inputs and match the Stock
Scheduler configuration convention. `timezone` and `run_time` also remain
editable. Universe, command, timeout, and maintenance operations stay
read-only or unavailable. The production command, 9,000-second timeout,
forecast writer lock, timer isolation, and no-run-on-save behavior are
unchanged.
