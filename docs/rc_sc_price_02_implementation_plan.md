# RC-SC-PRICE-02: revised temporary bridge plan

**Study COMPLETE. Implementation readiness CONDITIONAL, with a small RC-only design
and explicit ticker-local holds.** The previous whole-history-equality and concurrent-
acquisition requirements are not retained as global blockers. No implementation,
activation, Source change or scheduler change is authorized/performed in this phase.

Evidence: [root causes/materiality](rc_sc_price_02_mismatch_root_causes.md),
[adjusted append semantics](rc_sc_price_02_adjusted_price_and_append_semantics.md),
[split/scheduler safety](rc_sc_price_02_split_safety_and_scheduler.md),
[acceptance report](rc_sc_price_02_acceptance_evidence.md).

## Revised practical compatibility matrix

The existing scheduler selects 4,524 usa tickers and 98 omxh tickers. USA exact,
dated Source identity mapping remains 4,201 unique, 127 missing, 196 ineligible,
zero ambiguous. The new target retains **OMXH Yahoo**, rather than skipping it as
the PRICE-01 all-market-Source experiment would have done.

Apply current hard exclusions before the anchor tolerances. The mutually exclusive
prospective dispositions are:

| Disposition | Tickers |
| --- | ---: |
| Previously exact-compatible cohort, still a candidate | 3,202 |
| Previously mismatching, now acceptable candidate under anchor/materiality semantics | 879 |
| Material OHLC difference at current valid append anchor | 12 |
| Material volume difference at current valid append anchor | 2 |
| Invalid actual RC append anchor / new Source row gate | 5 |
| Split/date/ratio/action reconciliation hold | 26 |
| Missing/unqualified Source boundary coverage | 19 |
| Source operator exclusion | 9 |
| Source HELD | 8 |
| Currency evidence unresolved | 39 |
| USA ticker missing from Source | 127 |
| USA route ineligible/closed | 196 |
| Ambiguous USA mapping | 0 |
| OMXH continues existing Yahoo | 98 |
| Total | 4,622 |

Thus **4,081 USA candidates**, versus 3,236 PRICE-01 preliminary exact-overlap
candidates: net +845. Of the original 3,236, 18 now have reverse-action holds,
15 unresolved quote currency and one missing Source boundary. Of the 931 mismatches,
879 are candidates: **801 have an exact anchor and only historical differences;
78 need marginal anchor tolerance**. Other members of the 931: 12 material prices,
two material volumes, five invalid anchors, six action holds, three coverage holds
and 24 currency holds. This accounting sums to 931.

These are **not production-qualified tickers** or rows to insert. No matched ticker
currently has a qualified newer Source observation than RC. Qualification must be
rechecked against the actual pending new interval, current dependency/action state,
currency/unit support and app paths during implementation and every scheduled run.
One legacy usa candidate BTC-USD is already_current on November 1; market labels
must never replace its UTC 24/7 calendar or imply comparable equity volume units.

## Evidence-supported numerical contract

- Prices: relative error <=0.1% per OHLC field on the actual common-date anchor;
  separate 1e-12 relative allowance for floating-point roundoff, no absolute-price floor.
- Normal compatible counted volume: relative <=1%.
- Positive small counted volumes with max >100 and <=5,000: Source multiple-of-100
  observation may instead differ by <=50 units and <=10%; values are not rounded.
  Above 5,000 this absolute allowance is redundant with 1%; <=100 stays exact.
  Zero/nonzero volume never uses a denominator floor or absolute exception.
- Dividend reconstruction: accepted float OHL×(Adj Close/Close), Close=Adj Close,
  original accepted volume. Require current adjusted_usable/units/quality. Do not
  multiply by split ratios or derive a factor from dividend cash totals.
- Preserve the explicitly evidenced legacy dividend-vintage path in the append
  report: new RECORDED cash dividend, ordinary anchor matches RC, valid current
  factor and all independent gates pass. It explains the existing Yahoo append
  contract; it never overrides an unexplained factor or split/unit/currency hold.

Source session/identity/currency/action holds, invalid new prices, wrong adjusted
definition and unresolved units **always take precedence**. Older historical equality
is not an admission condition. Older RC defects remain visible without being
returned, rewritten or treated as newly qualified Source observations.

## Exact selection and minimal files

Keep the existing injection route:

```text
installed run_stock_update_scheduler.py:main
  explicit scheduled adapter-factory argument
  -> runner.run_scheduler_config
  -> runner._run_one_market, market == 'usa' only
  -> RawCandleApp._run_stock_update_via_service, optional per-call adapters
  -> existing run_stock_data_update stock_factory/history contract
```

| File/function | Proposed change |
| --- | --- |
| New services/stockcore_price_provider.py | Small read-only Source facade, ticker-shaped adapter, mapping/quality/action/anchor preflight and reason counters |
| main.py:_run_stock_update_via_service | Optional explicit adapter dictionary; default existing builder remains unchanged |
| rawcandle/scheduler/runner.py:run_scheduler_config/_run_one_market | Pass optional factory; substitute only for explicit scheduled USA, retain OMXH/default runner behavior and existing logs |
| rawcandle/cli/run_stock_update_scheduler.py:main | Explicitly supply the scheduled-USA factory; no timer arguments/configuration edits |

Estimate roughly **350–550 production lines across these four RC files**, including
read-only validation/diagnostics and action/factor safety, plus focused tests. This
does not include unrelated counter repairs, an identity service, a new schema or
automatic historical replacement. A generic source-selection wrapper in the shared
history function adds unnecessary propagation and affects manual callers. Calling
run_stock_data_update directly from the runner would duplicate main's long binding;
the small optional app injection is easier to review and reverse.

The installed RC interpreter currently does **not** have StockCore installed.
The study successfully imports its canonical pure readers from the trusted checked-out
reference using Python 3.10. A future adapter must explicitly qualify that import
boundary (for example, a validated local checkout path added after existing module
search paths when constructing the scheduled USA adapter). Do not change systemd
Environment, install a different Yahoo into RC, alter global Yahoo bindings, or use
StockCore constructors that initialize/migrate/acquire. Missing/incompatible reader
code fails closed with a visible Source-contract error, never Yahoo fallback.

## Adapter output and read ownership

The provider remains a small ticker-shaped object:

```python
stock = scheduled_usa_factory(ticker)
history = stock.history(start=..., end=...)  # inclusive start, exclusive end
splits = stock.splits                       # real qualified reconciled Series
```

History is a materialized single-ticker DataFrame with columns in order
Open, High, Low, Close, Volume; float64 prices, representable integral volume,
Date DatetimeIndex in the qualified instrument session timezone, ordered unique
dates and a correctly shaped empty result for no new data/expected holds. The
consumer accesses columns by name; it does not need Adj Close or dividend columns.
Use the verified calendar, including index/crypto conventions, rather than a
generic UTC-date shift or weekday approximation. Convert inclusive Source range
ends from RC's exclusive end and clip to completed, accepted sessions.

Source path is `/home/kalle/projects/stockcore/runtime/osakedata_ng.db`, current
projection Store schema 5/application_id 0x53434f52. Read via physical-path-checked
URI **mode=ro**, query_only/trusted-schema guards, short timeout and bounded rows.
Canonical Store.read's ordinary writable open is insufficient by itself. Reuse
PriceReader qualification on a pinned read-only facade and retrieve its same-snapshot
accepted six fields/actions/head, not staging/source_received prices or unaccepted
payloads. Source's ordinary reader plus accepted adjusted_usable is sufficient;
there is no need to pretend production is StockCore research.

Materialize one ticker's pending bounded scope, pin dependencies and close before
frame conversion, sleeps, RC writes or analysis. The snapshot facade can yield the
same outer connection to canonical reader calls; it must not combine mapping/actions
from one revision with values from another. Schema/API drift, busy errors and unexpected
failures are visible warning/failure outcomes; expected missing/held tickers are named
skips. No long job-wide read, immutable=1, Source writer lock, journal-mode change,
large database copy or synchronization store is proposed.

## One coherent later implementation phase

1. Recheck HEADs/installed dependencies, exact Source schema/reader behavior and
   representative runtime facts; preserve unrelated worktrees. Use the already
   approved existing staggered-time/whole-lock-overlap policy without changing it.
2. Implement only the RC-owned reader/factory and bounded per-ticker preflight:
   identity → Source eligibility/coverage/units/currency → bidirectional split state
   → valid current anchor/new rows → compatible boundary or explained dividend
   vintage → adjusted frame. Withhold any new/revised/uncorrected split before
   returning the first history chunk. No empty .splits deception.
3. Wire the explicit CLI-origin factory only to scheduled USA. Leave scheduled
   OMXH, scheduler UI Run now defaults, manual searches/UI updates/service CLI,
   forecasts/Fundamentals and downstream mathematical callbacks unchanged.
4. Add isolated tests against the actual new implementation: positive equity/dividend/
   ETF appends, matched old split, new/revised/missing action, factor/FX/unit errors
   despite tiny differences, low/zero volume, no-new/missing/HELD/ambiguity, duplicate
   triggers, Source commit/closure/deadline and CLI/market/manual isolation. Tests
   fail if the USA bridge touches Yahoo, including .splits or destructive backfill.
5. Validate actual integrated call signatures, reason counters and existing default
   adapter regressions; create a scoped RC implementation commit. Do not run a real
   provider job or activate a cutover implicitly as a test.

Keep existing RC writes/analysis. A rejected ticker has no OHLCV insert or split
write and does not enter per-ticker analysis; independent tickers continue. Existing
market-level Dow/relevance/report/Fundamentals poststep triggers are preserved.
Do not attempt to repair legacy zero aggregate counters as part of this bridge.

## Remaining true holds and resolved restrictions

Resolved as global design objections:

- Bitwise historical equality is unnecessary for RC's insert-only contract.
- Different versions share the required adjustment formula, verified on retained data.
- Ordinary Source is convertible locally to RC's existing adjusted definition without
  changing StockCore's technical default or introducing a second investment model.
- New/revised splits can be withheld ticker-locally before insertion; matched old
  splits need no second adjustment. Historical rewriting is not required for others.
- The user now accepts the existing whole-workflow lock result on overlapping schedules.

Still held per ticker: 26 action discrepancies, 39 currencies without sufficient
Source quote support, 19 missing Source boundaries, nine operator exclusions, eight
HELD scopes, five invalid anchors, 12 material price anchors, two material volumes,
missing/ineligible mappings and any future inconsistent Source/action/unit state.
The 39 do not become USD merely because their RC market is usa: 3,715 matches have
qualified identity/operating-USD support, 447 have accepted cached **price-currency**
metadata evidence (not an inferred dividend-cash currency), and 39 remain unresolved.
No actual conflicting accepted currency was observed. RC's original per-row currency
is not persisted; same qualified Yahoo route and unchanged conversion semantics are
part of the compatibility contract, not a numerical FX inference.

The owner publication code explicitly rejects SOURCE_PRICE_CURRENCY_CONFLICT when
returned frame currency contradicts a qualified operating currency. Successful
compacted price rows do not retain a per-row currency field. The 447 cached
price-currency references are dated accepted evidence, not a certificate for every
future capture: runtime must establish that the reference still applies to the
current route/pending scope and withhold if missing, contradicted or no longer
qualified. Do not assert fresh per-capture FX verification from numerical equality
or turn this limitation into an unapproved Source-schema/provider change.

The concrete remaining implementation prerequisites are qualifying deployment of
the read-only reader and testing the actual adapter/dispatch/guards. The 4,081
candidates still require new-interval qualification at runtime. None of the local
holds requires a global stop or a new Source modification; none may be waived to
maximize coverage. Trigger times and enabled states remain under the user's existing UIs.

## Reversal

Remove the optional factory argument from the installed scheduler CLI, or revert
the isolated future implementation commit. Default USA Yahoo and all existing
callbacks are then restored; OMXH/manual paths never changed. No integration schema,
service, mapping database, Source write or scheduler-state restoration is needed.
Do not switch a running ticker mid-batch. Reversing provider selection does not
undo future imported rows; any requested data rollback would use the existing
qualified RC backup/recovery process plus logged imported session/dependency evidence.
This study changes only documentation and ignored evidence, so its local commit
has no operational data to reverse.
