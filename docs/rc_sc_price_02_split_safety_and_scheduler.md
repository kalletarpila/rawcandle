# RC-SC-PRICE-02: split safety, isolation and existing scheduling

Investigation only. Related [root causes](rc_sc_price_02_mismatch_root_causes.md),
[append semantics](rc_sc_price_02_adjusted_price_and_append_semantics.md),
[implementation plan](rc_sc_price_02_implementation_plan.md) and
[acceptance evidence](rc_sc_price_02_acceptance_evidence.md).

## Actual split workflow and its hazardous branch

The scheduled service receives a ticker-shaped object from stock_factory.
After nonempty converted history reaches the downstream section:

1. `main._build_stock_update_service_adapters.sync_splits` calls
   `stock/splits.py:sync_splits_for_ticker`, passing that same object.
2. `fetch_splits_for_ticker` reads **object.splits**; default yf.Ticker access can
   load max history. Exceptions are swallowed into a warning and empty list, so
   raising from a property is not a reliable split safety gate.
3. `upsert_splits` uses INSERT OR IGNORE keyed by ticker/date. New dates receive
   is_price_data_corrected=0. An existing date with a different ratio is ignored,
   not reconciled. The corrected bit is RC processing state, not proof of Source parity.
4. `main._maybe_backfill_splits_for_ticker` checks any uncorrected event. If present,
   it invokes `delete_prices_from_2018`, which **commits deletion before fetching**,
   then `refetch_prices_from_yahoo`, which constructs a new yf.Ticker independent
   of the injected factory. Success cleans analyses, recomputes divergence and
   marks splits corrected; failure does not safely restore the committed deletion.

All this is actual current code, not exercised on operational data. The service
does not wait for a positive number of inserts before split callbacks; a nonempty
duplicate history also reaches them. An empty converted history bypasses them.

Therefore the guard belongs **before any USA history is returned for RC insertion**.
Replacing only the main OHLCV call or returning an empty .splits property is insufficient.

## Current bidirectional action reconciliation

The Source owner stores Yahoo NEW_PER_OLD ratios and accepts/refetches already
split-adjusted six-field history without multiplying prices again. The bridge must
copy neither Source split ratios nor RC corrected flags into a price multiplier.

PRICE-01 found these two genuine ratio conflicts:

| Ticker / date | RC corrected ratio | Source PROCESSED ratio | Meaning |
| --- | ---: | ---: | --- |
| PLRZ / 2025-11-28 | 0.125 | 0.16666666666666666 | 1:8 versus 1:6, not floating-point noise |
| SCLX / 2026-06-16 | 1.006 | 1.606 | Materially different action values |

The deeper reverse comparison also finds **38 RC-only split events on 29 matched
tickers inside Source's accepted observation interval**. Four more RC-only events
are at/after the missing Source tail rather than inside that interval; those tickers
already have availability holds. Five of the 29 tickers are already withheld by
Source/operator/availability gates. The remaining 24 plus the two ratio conflicts
produce **26 exclusive split-reconciliation holds** in the final matrix:

```text
ALIT ARTL BRCC CPOP FTFT HAO JBDI LEXX LGHL LILA LILAK MNDR MOD NAMI
OMH PLRZ RETO RUSHA SCCO SCLX SLXN SMX SVC TRIB TSLS YYAI
```

Examples include TRIB's RC dates August 26 and 27, 2025, LILA/LILAK's 1.1 event,
and other accepted-interval events missing from Source's current split dictionary.
Do not collapse nearby dates, round ratios, infer event continuity or assume the
RC-only event is correct merely because it is marked corrected. This study does
not decide which history is wrong or alter either ledger; the discrepancy is an
unresolved action-evidence hold.

Another **4,180 RC-only events precede Source's accepted available interval**, often
pre-2018 or before a later qualified available start. Source makes no claim to
complete earlier history. Corrected old RC records remain untouched; lack of a
Source assertion outside its scope is not itself an invented conflicting event.
Any uncorrected RC event, actual shared-date ratio conflict, new/revised Source
event or current unit/identity hold still withholds the ticker. No new permanent
cross-system action master is needed.

## Minimal scheduled-USA guard

Before supplying any of a ticker's pending rows:

- Read the accepted Source snapshot, current head/reader quality, dated route,
  qualified action scope and applicable actions. Inspect RC split records read-only.
- Reject missing/HELD action evidence, new Source actions absent from RC, differing
  ratios or dates, relevant RC-only actions in Source's asserted scope, and **any
  uncorrected RC split**. Check both directions; retain exact evidence/reasons.
- Do not fetch Yahoo, insert a split to signal correction, change a corrected bit,
  delete history, or invoke the destructive backfill callback for a rejected ticker.
  Return an empty typed history plus a named skip reason, so the existing service
  bypasses ticker downstream work and continues independent tickers.
- For matching PROCESSED Source actions already corrected in RC, supply the real
  sourced .splits Series. Existing INSERT OR IGNORE then does zero new work, and
  the existing maybe-backfill callback returns False. An isolated test verifies
  this with a 4:1 event and unchanged stored prices/corrected state.

Preflight the **whole pending ticker scope** before returning the first chunk;
otherwise an earlier returned frame could survive a hold discovered in a later
history chunk. RC collects history chunks before writing, but an empty later chunk
does not automatically invalidate previously returned rows. A bounded in-memory
accepted snapshot/decision for the ticker avoids that trap. No read transaction
continues into RC insertion, analysis or provider pacing sleeps.

No new/revised split is automatically repaired through this bridge. Withholding
only that ticker is the smallest safe behavior under the no-history-rewrite rule.
Supporting automatic split replacement would require a different, explicitly
authorized historical-write and recovery design.

## Existing exclusion is sufficient for coordinated RC UI work

Correction to PRICE-01: `services/missing_day_recovery.py:stock_update_operation_lock`
**reuses acquire_scheduler_lock**. For the configured production database, it resolves
the same scheduler_config.log_dir and lock file. It is not a separate independent
mutation lock. `main.update_stock_data` is decorated with `_coordinate_stock_update_ui`,
including its service opt-in path; missing-day recovery also uses that exclusion.
Thus the scheduler's existing exclusive lock already excludes those coordinated
UI price mutations during the preflight/write batch. No additional nested acquisition
of the same nonreentrant flock should be added.

This does not assert exclusion of arbitrary standalone scripts, external SQLite
writers or uncoordinated manual CLI invocations. They remain outside the existing
job contract. The bridge neither starts them nor adds a new concurrency framework.

## Exactly what schedule overlap does

Installed RC service:
`rawcandle/cli/run_stock_update_scheduler.py --config .../scheduler_config.json`,
using /usr/bin/python3. Config enables **omxh then usa**, with current timer/JSON
04:30. Source's stored yahoo-daily schedule is currently 23:45 Helsinki, disabled;
these observed settings were not changed or used as a global Source-read gate.
The loaded/enabled systemd state was not queried. The user controls future times.

StockCore `daily_source.rawcandle_idle` takes a shared nonblocking flock on
`/home/kalle/projects/rawcandle/logs/stock_update_scheduler.lock` throughout daily
Source planning/acquisition. RC `run_scheduler_config` takes an exclusive nonblocking
flock on that inode **before any market stage**. Current FULL_WORKFLOW also acquires
that scheduler lock through Fundamentals production_lock.

| Overlap order | Existing outcome, retained |
| --- | --- |
| Source daily acquisition already holds shared flock | RC lock acquisition raises SchedulerAlreadyRunningError; CLI emits FAILED, scheduler_skipped=0 and exits 1 |
| Consequence for RC stages | **Neither OMXH Yahoo nor USA Source work starts; subsequent RC Dow/relevance/DC/EC/Fundamentals poststeps do not run** |
| RC already holds exclusive flock | Source daily start detects RAWCANDLE_ACQUISITION_RUNNING and returns its existing SKIPPED/NOT_STARTED result/diagnostics |
| Next opportunity | Existing timer/manual initiation; no new queue, automatic defer/retry service or per-market retry is added |

The user now accepts staggered times and this existing fail/skip-on-overlap policy.
Accordingly it is an operational limitation, **not the unresolved architectural
blocker asserted for PRICE-01's different concurrent-run requirement**. Do not claim
that only USA skips: current exclusion covers the whole RC workflow, including OMXH.

## SQLite reads and acceptance

Actual Source and RC databases use DELETE journaling. Source publishes accepted
observations/actions/head/coverage locally and atomically; failed/staged responses
are never adapter prices. Short `mode=ro` snapshots see an accepted state and close
before RC writes. Ordinary Store.read's writable open followed by query_only is
not sufficient for the explicit no-runtime-write-access requirement; use an RC-owned
read-only facade with the canonical reader/validation semantics.

An isolated DELETE-journal test confirms writer COMMIT may be busy while a reader
remains open, succeeds after closure, and the reader also closes on an injected
exception. Source/RC flock tests exercise the actual existing lock functions against
temporary files in both directions, never the production lock. No journal-mode,
busy-timeout, timer, lock path or enabled-state change is made operationally.

## Provider isolation

Select the optional factory explicitly from the installed scheduler CLI and pass
it through `run_scheduler_config` → `_run_one_market` → app service adapters:

| Caller/market | Future provider |
| --- | --- |
| Installed scheduled CLI, usa | StockCore accepted Source, no Yahoo fallback |
| Installed scheduled CLI, omxh | Existing Yahoo factory and split/backfill behavior |
| Manual/UI Yahoo searches, update UI/service opt-in, missing-day recovery | Existing Yahoo |
| Scheduler UI Run now | Existing default runner/Yahoo; it must not inherit an unconditional runner switch |
| Other manual service CLI, forecasts and Fundamentals | Existing behavior |

A person invoking the installed scheduler CLI directly invokes that same selected
workflow; no unreliable process-origin guessing is proposed. Keep the generic
history helper and shared default builder unchanged; do not monkey-patch main.yf
or yfinance globally. No actual selection code is changed in this study.
