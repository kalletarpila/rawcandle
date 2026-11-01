# RC-SC-PRICE-01: temporary integration plan

**Study COMPLETE. Implementation readiness BLOCKED for the complete requested
behavior under the current unchanged contracts.** A conservative scheduled-only
bridge is technically feasible for individually qualified tickers, conditional on
the bounded decisions/evidence below. Nothing in this document activates it.

Read [current contract](rc_sc_price_01_current_provider_contract.md),
[compatibility and coverage](rc_sc_price_01_stockcore_data_compatibility.md) and
[acceptance evidence](rc_sc_price_01_acceptance_evidence.md) together.

## Recommendation and realistic alternatives

Choose **A: explicit scheduled-only provider injection at runner._run_one_market's
call to RawCandleApp._run_stock_update_via_service**, selected explicitly by the
installed scheduler CLI main. Pass an optional adapter factory through the runner;
its default stays Yahoo, including the scheduler UI's Run now call. Keep the current
default builder and all other callers unchanged. Reuse its existing stock_factory contract;
do not introduce a generalized provider framework for a 2–3 month bridge.

| Option | Concrete files/functions | Estimated production footprint | Contract/rollback | Risk and focused tests |
| --- | --- | --- | --- | --- |
| A, recommended | New services/stockcore_price_provider.py; main.py:_run_stock_update_via_service optional explicit adapters; rawcandle/scheduler/runner.py:run_scheduler_config/_run_one_market optional scheduled factory/safety context and reason logs; rawcandle/cli/run_stock_update_scheduler.py:main explicit selection | About 300–500 adapter/qualification/RO-facade lines, 5–15 main lines, 20–50 runner lines, 5–10 CLI lines; excludes tests | Reuses history and splits-shaped object; drop CLI injection to restore scheduled Yahoo | Private Source validation/version coupling, basis/split safety, current cross-lock; test reader, injection, all no-data branches and manual callers |
| B | services/stock_update_service.py:fetch_history_for_date_ranges plus scheduled context propagation from CLI through runner/app/service callers | Roughly 20–50 wrapper lines **plus the same adapter and gates**, and plumbing | Same frame possible, but history switch is shared; must thread an explicit source context through many functions; rollback removes branching/plumbing | Larger caller/isolation regression surface; cannot solve splits/backfill simply by changing history |
| C | runner._run_one_market calls run_stock_data_update directly using app._build_stock_update_service_adapters with only local overrides, gated by explicit CLI selection | Same adapter plus about 35–60 duplicated orchestration-argument lines and CLI context plumbing; no main change | Existing DI hook, easy local reversal | Duplicates main's long argument binding and can drift when its callbacks change; not clearly simpler overall |

All estimates assume conservative skips for unsafe split/history cases. Supporting
automatic historical replacement or changing the existing cross-system exclusion
would exceed this small bridge and the current authorized phase.

## Minimal proposed interface and ownership

The new module would expose a small explicit per-market factory/context:

```python
factory = StockCorePriceFactory(source_path, rc_path, market, now, reason_sink)
stock = factory(ticker)          # existing Callable[[str], Any] seam
stock.history(start=..., end=...)  # end exclusive; materialized DataFrame
stock.splits                    # sourced, qualified, already RC-reconciled Series
```

This is a proposed interface, not implemented code. `reason_sink` records classified
counts/cutoffs/dependency tokens in the existing RC scheduler log/summary boundary.
It must not hold SQLite handles or create another integration store. Construction
must not fetch, migrate, initialize, allocate identity or start background work.
Use fixed columns Open/High/Low/Close/Volume (float64 prices, qualified int64 volume),
DatetimeIndex Date in the verified instrument session timezone, deterministic order,
no duplicate session dates. Additional action columns are unnecessary for RC OHLCV
conversion; .splits supplies the separate actual contract.

Use Source's current accepted schema and **PriceReader** eligibility semantics, not
raw SQL price selection alone. A small RC-owned read-only Store facade must open
`file:<absolute Source>?mode=ro`, validate physical path, application ID, schema 5,
projection mode and required reader columns, set query_only/trusted_schema guards,
and close on success/error. StockCore's existing Store.read alone opens writable
and therefore does not satisfy this boundary. Its current validation method is
private: pin compatibility to the inspected Source contract and fail closed after
unqualified schema/reader changes. Do not modify StockCore to evade its path guards.

One ticker snapshot must pin route, security eligibility, calendar/binding,
Source dependency/head, accepted six-field rows and their quality/action/coverage
evidence. The public reader can run against the same pinned read-only facade;
metadata and raw fields must not be fetched in another unbound snapshot and then
combined. Return plain in-memory values; close before float reconstruction,
DataFrame work, Yahoo pacing sleeps, RC writes or downstream callbacks. Bounded
metadata acquisition may be separate, but revalidate each ticker's actual inputs.

Use a short busy timeout and a progress/deadline guard; read only the necessary
bounded rows (a full security history is under the transport's 10,000-row bound).
On busy/error/changed binding, close immediately and record SOURCE_BUSY or a typed
failure. Do not spin, block either writer with a long read, copy the database,
use immutable=1, change journal mode or take the Source acceptance lock.

## Qualification before returning any new row

1. Resolve RC market/ticker deterministically to one current accepted instrument.
   Only verified usa→USA is available. Missing/ambiguous/ineligible/unsupported
   tickers produce an empty frame with a specific skip reason. No Yahoo fallback.
2. Respect Source operator exclusions independently of historical reader availability.
   Validate action/unit/dependency/volume/adjusted factors for the requested scope.
   Keep GAP, UNKNOWN_PREFIX and accepted no-observation positions in evidence; never
   invent a bar. A HELD segment is not silently bridged by a compressed series.
3. Translate [start,end) to inclusive Source dates clipped to completed instrument
   sessions. If none, or if no qualified accepted observation is newer than RC,
   return the correctly shaped empty frame. Do not query/fabricate a new global
   session from the latest run timestamp.
4. For a ticker with prospective new data, compare enough accepted shared history
   to establish RC compatibility, including action-sensitive boundaries. The recent
   six-session screen is insufficient proof of the full stored history. A bounded
   per-security full history read (no export/copy) is a possible initial qualification
   strategy; perform arithmetic/comparison after closing Source. Any unsupported
   vintage/units, changed overlapping row, missing proof or ratio conflict is
   **UNSAFE_TO_IMPORT**, with no RC history rewrite and no tolerance invented to
   make it pass. Recheck when Source revisions/actions change.
5. Reconstruct only the qualified accepted same-vintage fields with the installed
   RC float formula: OHL × (Adj Close/Close), Close=Adj Close, unchanged volume.
   Prove finite positive prices/factor and representable integral volume. Do not
   apply split ratios or derive dividend factors from actions. Preserve normalization
   provenance; approved Source substitutions do not prove original Yahoo parity.
6. Reconcile all applicable processed Source splits with RC dates/ratios/corrected
   state before supplying history or .splits. Any new/revised/missing/uncorrected
   action holds the ticker **before the existing RC insert path**. New split handling
   must not call the default delete/refetch/reanalysis path. Establish existing RC
   mutation exclusion across this check and its batch; scheduler flock alone does
   not prove every manual writer is excluded. If that cannot be proved within a
   small scheduled-only guard, leave those cases blocked.
7. Return only requested, qualified, increasing session rows. Reuse the existing
   insert-only writer and analysis callbacks unchanged for supported cases. The
   adapter's .splits is the real qualified Source Series after reconciliation,
   never an empty placeholder used to conceal a new split. No calls to yf.Ticker,
   .info, .actions, max-history or refetch_prices_from_yahoo from this adapter.

The current reader restricts adjusted mode to research=True and uses Decimal
arithmetic, not exact yfinance float substitution. Prefer an explicitly reviewed
**RC-local compatibility conversion** after canonical Ordinary qualification and
adjusted_usable checks on the same accepted payload. Do not set research=True in
an operational adapter just to bypass that restriction. If StockCore ownership
requires a different public reader contract, that needs a separately authorized
owner change; it cannot be implemented in this read-only reference task.

## No-new-data cases and unchanged processing

| Case | Proposed scheduled provider outcome | Existing RC consequence |
| --- | --- | --- |
| A: newer qualified compatible row | Return in requested [start,end) | Existing missing-date insert, split callbacks safely reconciled, divergence/candles/Dow behavior |
| B: Source only already-known dates | Empty after date filter | no_history_data skip; no per-ticker downstream; existing final market Dow/poststeps still run |
| C: ticker missing/ambiguous | Empty + MISSING_TICKER/AMBIGUOUS_TICKER | Count skipped with diagnostic reason; no fallback |
| D: HELD, unsafe basis/action/overlap | Empty + specific SOURCE_HELD/UNSAFE_TO_IMPORT | No ticker insertion, split backfill or per-ticker analysis |
| E: Source acquisition incomplete | Only committed qualified observations; if none newer, empty | No wall-clock/global freshness barrier; other qualified tickers can advance |
| Old rows returned despite half-open request | Disallowed adapter behavior | Would cause zero inserts yet run divergence/splits, changing B |
| Read contention, unavailable file or schema drift | Close/fail closed; SOURCE_BUSY/contract failure, surfaced in scheduled logs | No Yahoo fallback, no silent successful freshness claim |

Missing/no-new/held are expected ticker skips, not provider transport failures.
Unexpected corruption/schema failure must be surfaced as a warning/failure; never
turn every error into a successful empty run. Keep existing totals, append bridge
reason counts and pinned source/cutoff/RC-tail evidence without repairing unrelated
legacy counter placeholders. Defaults for all nonscheduled callers remain Yahoo.

## Existing concurrency blocker

`stockcore/daily_source.py:rawcandle_idle` opens
`/home/kalle/projects/rawcandle/logs/stock_update_scheduler.lock` read-only and takes
a **shared nonblocking flock**, held by DailySource.run across planning/acquisition.
RawCandle's runner takes an **exclusive nonblocking flock on that inode**, including
the current FULL_WORKFLOW production_lock path. If Source is acquiring, RC is rejected
as already running before `_run_one_market` or any adapter executes. The reciprocal
Source start also skips when RC owns the lock. This is existing explicit coordination;
a two-hour schedule gap cannot prove it will never apply.

Therefore an adapter alone cannot fulfill “if StockCore is still running, RawCandle
uses previous accepted rows” while preserving both current scheduler/exclusion
contracts. Do not bypass, rename or stop honoring that lock. Options requiring a
later explicit decision are: accept existing fail/skip-on-overlap behavior for this
temporary bridge, or authorize an owner-reviewed exclusion change that separates
scheduled read-only price use from still-live Yahoo/manual/Fundamentals acquisition.
The latter is outside this phase and affects scope beyond a pure provider adapter.
No new scheduler dependency, watcher or daemon is recommended. Trigger times and
enabled states remain for the user to configure manually through existing UIs.

At the SQLite level, a brief snapshot can read the previous complete accepted state
during a Source write and release promptly; isolated DELETE-journal contention was
tested. This storage property does not remove the earlier application flock blocker.

## One later coherent implementation phase

After explicit implementation authorization and resolution of the relevant holds:

1. Recheck both HEADs, installed library versions, Source schema/reader and bounded
   runtime coverage. Do not require a new global latest Source run.
2. Add the small RC-only facade/factory and qualification reasons; no Source changes,
   schema, integration database, network code or framework.
3. Add explicit optional per-call adapters in main's service method, substituting them
   at runner._run_one_market only when the installed scheduler CLI has supplied its
   optional adapter factory through run_scheduler_config. No timer/config edits or
   origin detection are needed. Preserve default runner, scheduler UI Run now and
   other UI/CLI callers. Implement only resolved safety/exclusion behavior.
4. Add focused isolated Source-schema fixtures, history conversion/action safety,
   scheduled injection and manual-caller regression tests. Retained sanitized/synthetic
   fixtures only in Git; generated evidence remains ignored.
5. Validate read-only behavior and connection closure with actual isolated SQLite
   commits, exception/deadline tests, and spies that fail if the scheduled price
   bridge touches Yahoo (including .splits/backfill). Never run a real scheduled
   update as an accidental test.
6. Report per-ticker acceptance disposition, review source diff and create an RC
   implementation commit. Operational activation/provider replacement is a separate
   explicit user action; timer changes are not bundled.

Estimated source scope: the four RC files above, about 330–575 lines total before
tests and roughly 150–300 focused test lines if existing fixtures can be reused.
Uncertainty is concentrated in owner reader policy and existing exclusion, not HTTP
plumbing. This estimate excludes supporting unsafe historical rewrites, repairing
RC's preexisting counter semantics or redesigning the Source owner.

## Focused acceptance required before activation

- Exact frame column order/types, float formula/direct adjusted Close, unchanged
  int64 volume, empty frames, DST/session normalization, end-exclusive clipping,
  weekends, long-range chunks and short histories.
- Unique/missing/ambiguous ticker and ID resolution, wrong market, inactive/closed
  routes, competing pending routes and no alias inference.
- Ordinary/dividend payer/ETF, old/recent/reverse splits, nonpositive/missing factor,
  accepted volume/Adj Close substitutions, original provenance UNKNOWN, qualified
  absent sessions, UNKNOWN_PREFIX, HELD/operator holds and stale dependencies.
- RC historical overlap mismatch, new/revised/uncorrected split and differing ratio:
  no RC insert/backfill, no split-ratio price multiplication, no history overwrite.
- A/B/C/D/E above; stale Source for one ticker does not block another; rejected
  Source candidate cannot replace good accepted data; no provider fallback.
- Concurrent isolated Source commit, old/new atomic snapshot visibility, close on
  all exceptions, bounded busy behavior, and source URI refusing writes. Exercise
  the existing application lock result separately; do not label it SQLite success.
- All default manual UI/service/scheduler-UI-Run-now/missing-day/Yahoo/forecast/Fundamentals routes keep
  their providers; monkeypatch tests must verify default and scheduled calls together.
- Existing insert-only duplicate semantics and per-ticker/final market analysis
  triggers remain as documented. Summary counters distinguish skipped/held/error.

## Holds and reversal

Implementation is not READY:

1. **Concurrency requirement conflict:** a pure adapter cannot run inside the
   existing Source/RC mutual exclusion. Accept that limitation explicitly or
   separately authorize a qualified owner change; no unilateral lock bypass.
2. **Price/history qualification:** exact formula is established, exact stored
   history equality is not. 931 overlap mismatches, two split conflicts and earlier
   dividend-history differences must remain UNSAFE_TO_IMPORT. The 3,236 preliminary
   candidates require broader history qualification before they become imports.
3. **Adjusted production reader policy:** approve the explicit RC-local compatibility
   contract or separately qualify an owner interface. Ordinary StockCore prices
   cannot directly replace RC adjusted OHLC.
4. **Split evolution:** a new split cannot safely use RC's unchanged delete/refetch
   callback under this bridge. Qualified ticker-local skips are the bounded option;
   replacing/recomputing history needs a different authorized scope.

No missing user detail prevents completing the study itself. These are concrete
implementation/activation decisions, not permission requests for this documentation.

Reversal of the proposed implementation is removal of the explicit scheduler CLI
adapter-factory argument (or reversion of its isolated implementation commit). This restores the
unchanged default Yahoo factory and callbacks without editing manual UI calls or
schedules. No integration store/schema needs removal. Stop beginning new RC work
while an already-running batch completes; do not switch sources mid-ticker. Provider
reversal is **not a rollback of already inserted market data**: any future imports
would need retained RC-side run/session/dependency evidence and the existing qualified
backup/recovery process for a separately authorized data rollback. This study wrote
no operational data, so its documentation commit needs no data recovery.
