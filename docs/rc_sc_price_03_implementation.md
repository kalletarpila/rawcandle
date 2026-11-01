# RC-SC-PRICE-03 implementation and cutover acceptance

Implementation is installed in source only; neither bridge nor handoff is activated.
Starting RC HEAD: `bba25b60c86f987d4aa3ac7dda1ae042eea820d2`.
Starting StockCore HEAD: `20d3cdcddf82fdfac29ae652219fd1725eea4b7b`.
Each repository has a separate local implementation commit; final hashes are in
the task completion report. PRICE-03 supersedes PRICE-02's earlier no-fallback
design only for proven missing/ineligible USA instruments.

## Provider contract

The existing scheduled CLI accepts explicit `--stockcore-prices`, passing an
adapter factory through runner → app → existing service adapters. Its default,
the installed service command, UI Run now, manual searches, missing-day recovery
and other callers retain Yahoo. No global Yahoo replacement occurs.

| Selected scheduled path | Provider / result |
| --- | --- |
| USA unique eligible accepted route | Qualified StockCore Source |
| USA ticker absent, proven closed/future route, dated eligibility absence, inactive/non-USA supported-route absence | Existing Yahoo factory |
| Known but ambiguous, unqualified, excluded, unsafe or insufficient Source | Ticker withheld; reason recorded; no Yahoo |
| Healthy Source has no newer price observations | Existing empty-history behavior; no Yahoo |
| OMXH | Existing Yahoo; no Source connection/import needed |

Reader/contract failures fail the ticker and increment `reader_failures`; they
never authorize fallback. One ticker's full pending scope is preflighted and
cached before history is returned, preventing partial provider switching.

Source authority remains `PriceReader` and `source_accepted`. A pinned store
facade gives the canonical reader the same physically guarded SQLite `mode=ro`,
`query_only` snapshot as identity, route, calendar, dependency, actions and quality
checks. Application/schema/mode and accepted identity metadata are validated.
The read has a two-second SQL progress deadline, bounded results and explicit
closure on every path. Pandas processing occurs after the snapshot closes.
No Source initialization, migration, repair or write occurs operationally.

Same-vintage accepted ordinary OHLC plus Adj Close reconstructs RC output:
`factor=Adj Close/Close`; multiply Open/High/Low by factor, assign Close directly
from Adj Close, preserve Volume. Validate positive finite ordered bars, adjusted
usability, qualified split-adjusted price and reported-volume units, representable
integer volume, USD evidence, per-session identity/eligibility and bound calendar.
Qualified explicit no-price/action-only sessions retain their canonical absence;
unexplained missing or held sessions block the entire ticker.

The actual latest stored RC date is the anchor, never a substituted earlier date.
Apply PRICE-02 OHLC relative tolerance 0.1% plus 1e-12 roundoff, normal volume 1%.
Zero/nonzero never matches; both volumes ≤100 must match exactly. Counted volume
may additionally differ by ≤50 when max volume is 101–5000, Source is a multiple
of 100 and relative difference ≤10%. Crypto/index has no counted-unit exception.
These thresholds come from PRICE-02 evidence, not a new coverage optimization.
Up to two preceding bars diagnose persistent unexplained scaling. Material new
factor steps exceeding the price tolerance require independently recorded
positive dividends and the correct factor direction. Ordinary overnight returns
are not limited by an arbitrary maximum price move.

The dividend-vintage exception requires recorded positive dividends after the
actual anchor through the imported scope, ordinary Source OHLC matching stored
RC OHLC, and a positive accepted factor below one. No factor is inferred from
cash amounts. Historical revisions remain unchanged. No numerical tolerance
overrides identity, currency, unit, held/operator, coverage or split checks.

All Source splits must be processed, exact dated NEW_PER_OLD matches to corrected
RC splits. RC-only events inside Source history and any uncorrected RC event hold.
New/revised/conflicting splits are withheld before insertion. Source sync/backfill
callbacks recheck RC split state and never enter destructive Yahoo history repair;
the real reconciled `.splits` series is retained. Yahoo's existing split behavior
is unchanged. History also rechecks the RC anchor against concurrent changes.

Existing market logs and JSON summary lines include bounded bridge counters,
reason counts and up to 20 examples. Existing service counters and downstream
calculation, insert-only writer, reporting and error continuation remain intact.

## Handoff and timer ownership

StockCore's normal scheduled owner is `tools.daily_yahoo run` → `DailyPipeline.run`.
The new hook executes after `DailySource.run` returns through finalization, after
Source acquisition and P03/P04 callbacks, outside the scheduler/operation/Source
acquisition locks and shared RawCandle flock. Manual, dry-run and resume paths do
not dispatch. See StockCore `docs/rc_sc_price_03_handoff.md` for eligibility and
durable at-most-one request semantics.

The existing `stock-update-scheduler.timer` supplies the independent timed trigger.
The separate `stock-update-scheduler.service` is a static oneshot with the scheduler
CLI as ExecStart. It has no timer Requires/BindsTo/PartOf dependency. Disabling
the timer does not mask, disable or stop the service. The new UI helper commands
only the timer; isolated command/UI tests verify the service and schedule settings
remain untouched. This verifies configuration-level on-demand startability, not
a successful live scheduler execution.

Read-only host inspection during this task found the timer loaded/enabled/active
at 04:30 with Persistent=true, and the service loaded/static/failed from an earlier
run, without the bridge flag. No start/reset/stop or timer mutation was performed.
The pre-existing service failure needs operational diagnosis before cutover.

## Exact future cutover procedure — not executed

1. Obtain separate production cutover approval; ensure the existing StockCore
   Source/P03/P04 workflow is qualified and terminal. Wait for existing work to
   finish. Keep StockCore handoff disabled throughout preparation.
2. Open the existing RawCandle scheduler UI at
   `http://127.0.0.1:8555/scheduler`, select **Scheduler**, and click
   **Disable automatic schedule** below Timer status. Require the success message
   and inactive timer status. This runs `disable --now` on the timer only and
   verifies loaded/disabled/inactive. **Skip next run** is not persistent disable.
   Do not change market selections or run time. The user performs this action.
3. Verify read-only:
   `systemctl --user show stock-update-scheduler.timer --property=LoadState,UnitFileState,ActiveState`.
   Require loaded, disabled, inactive. Inspect the separate service's status and
   resolve its existing failure; do not infer health from static enablement.
4. Select the scheduled bridge in a service-only drop-in using
   `systemctl --user edit stock-update-scheduler.service`, preserving the existing
   working directory, environment and arguments:

   ```ini
   [Service]
   ExecStart=
   ExecStart=/usr/bin/python3 /home/kalle/projects/rawcandle/rawcandle/cli/run_stock_update_scheduler.py --config /home/kalle/projects/rawcandle/scheduler_config.json --stockcore-prices
   ```

   Reload user units if the editor did not do so. This is a future activation
   operation; no installed unit or drop-in was changed by this implementation.
5. In `/home/kalle/projects/stockcore`, explicitly enable the handoff:

   ```bash
   .venv/bin/python -B -c "from stockcore.config import Config; from stockcore.rawcandle_handoff import configure; configure(Config(mode='projection'), enabled=True)"
   ```

   Activation and every request independently require the RC timer to be disabled
   and inactive, and the loaded unmasked service to be idle with the bridge flag.
   Unknown/busy states fail closed. No helper disables the timer for the operator.
6. Inspect StockCore's linked handoff diagnostics and RC's existing logs on the
   separately approved run. REQUESTED means systemd accepted a nonblocking start;
   it does not establish RC completion. Confirm actual completion independently.

## Exact future restoration / rollback — not executed

1. Disable handoff using the same StockCore command with `enabled=False`. Wait
   for any already requested service run to finish. Disabling does not cancel it.
2. For full Yahoo rollback, remove only the bridge service drop-in/flag and reload
   user units. No historical RC rewrite is part of rollback.
3. In the same RC **Scheduler** tab click **Restore automatic schedule**. Require
   the restored message and active timer status. The UI refuses restoration while
   the handoff marker is enabled or unqualified; resolve that configuration first.
   The existing time and market settings remain authoritative. Persistent=true
   can cause a missed occurrence to run when the timer is restored.

The UI is the timer-management authority. Neither implementation activates the
handoff or disables the independent timer. A future concurrent operator changing
systemd behind the UI remains outside the check/start atomicity guarantee; the
existing exclusive RC workflow lock remains in place.

## Validation and operational limits

Focused RC adapter/service/runner/CLI tests pass, including actual isolated SQLite,
read-only refusal/closure, concurrent Source commits, no network, adjusted output,
tolerances, dividends/factor steps, split guards, fallback/holds and downstream
success/failure continuation. The final six-file RC group passed 187 tests; three
additional bounded-context revision/scaling cases passed after that run (190
distinct cases). Seven timer command/button cases are included in that group;
nine existing UI timer/Run now cases also passed (56 unrelated UI cases deselected).
An earlier expanded UI run was interrupted and is not claimed as completed.
StockCore's focused workflow/report group passed 73 tests, including 17 new
handoff cases. One separate existing HTTP label assertion failed identically with
the original HEAD modules; details are in the StockCore report. Initial test
fixture errors were corrected; sandbox loopback errors were resolved with the
required test permission. Full suites: NO.

No implementation command wrote production databases, scheduler settings,
timer/service files or Source rules. The local ignored scheduler_config.json
changed after the initial hash snapshot (mtime 2026-11-01 19:49:51 Helsinki,
before the first test log was created). The user confirmed this was their UI
change; its current contents were preserved without overwriting it.
The run time remains 04:30 and installed timer/service bytes match the initial
hashes. The unrelated tracked journal also matches its initial task hash.
No real Yahoo request, scheduler/systemd start, live calculation,
historical rewrite or push occurred. Isolated development acceptance is not live
operational acceptance. Import compatibility and ticker-local evidence must be
requalified if StockCore's canonical reader/schema changes during this temporary
bridge; no automatic fallback masks such failures.
