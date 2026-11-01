# RC-SC-PRICE-02: final acceptance report

**Investigation COMPLETE. Implementation readiness CONDITIONAL.** The temporary
scheduled-USA bridge has a credible RC-only design with broader compatibility than
PRICE-01, while unresolved tickers remain excluded. No implementation or activation
was performed. This report includes the user's materiality addendum.

Reports:

- [Mismatch root causes and tolerances](rc_sc_price_02_mismatch_root_causes.md)
- [Adjusted prices and append semantics](rc_sc_price_02_adjusted_price_and_append_semantics.md)
- [Split safety and scheduler behavior](rc_sc_price_02_split_safety_and_scheduler.md)
- [Implementation plan and complete matrix](rc_sc_price_02_implementation_plan.md)

## Repository identity and preservation

| Repository | Starting/inspected HEAD | Branch/worktree |
| --- | --- | --- |
| RawCandle | f6da66f106eaed99eb9dd707f4cb24c52df25375 | chore/ignore-backups; /home/kalle/projects/rawcandle only |
| StockCore, strictly read-only | 20d3cdcddf82fdfac29ae652219fd1725eea4b7b | main; /home/kalle/projects/stockcore only |

The user supplied PRICE-02 brief and materiality addendum govern this task. The
previously read StockCore AGENTS.md/accepted Source ownership rules remain applicable
at the unchanged HEAD; no applicable RC/root/docs/temp AGENTS.md was found. No
sub-agent delegation was requested or used. Inspection stayed on the price/accepted
Source/action/calendar/lock contracts, retained fixtures and two directly relevant
RC run logs; no unrelated repository content audit was performed.

RawCandle's existing modified Fundamentals publication journal and untracked
research/plot, generation data, repair documents/outputs/script and missing-day
reports were present before the study. Initial status and journal SHA-256 were
captured. Final validation checks identical unrelated status and journal content,
unchanged Source HEAD/clean status and exactly five task-owned staged documents.
PRICE-01 documents/evidence remain unchanged; corrections are explicit in PRICE-02.

## What changed in the conclusion

- The 931 are **690 volume-only, 74 OHLC-only and 167 combined** mismatches.
  Exclusive explanatory signatures are 690 volume-only, 81 recorded-dividend scaling,
  11 dividend plus other changes, 86 other raw-bar changes and 63 legacy-quality cases.
- Historical bitwise equality is not part of RC's insert-only append contract.
  Current anchor compatibility and independent unit/action gates are the relevant checks.
- Recommended thresholds: OHLC 0.1%, normal volume 1%, separate roundoff 1e-12
  relative and the explicitly bounded 50-unit/10% small-volume allowance. Very small
  and zero/nonzero volumes are protected separately. Sensitivity tables report counts;
  percentages were not chosen to admit every mismatch.
- **4,081 prospective USA candidates**: 3,202 retained from the prior 3,236 and 879
  newly acceptable from the mismatch cohort. Of the 879, 801 have exact anchors and
  78 need numerical tolerance. No candidate is claimed activated/production-qualified.
- Hard/ticker-local exclusions remain: 26 split/action, 39 unresolved currency, 19
  missing Source boundaries, nine operator, eight Source HELD, five invalid current
  anchors, 12 material current prices, two material volumes, 127 missing and 196
  ineligible mappings. Zero ambiguities currently; negative ambiguity cases are tested.
- Scheduled OMXH's **98 selected tickers retain Yahoo**. No USA Yahoo fallback;
  manual/UI/default runner calls, forecasts and Fundamentals keep their existing paths.
- Existing cross-system scheduler exclusion is retained under the user's revised
  staggered-time policy. Overlap prevents the **whole** RC workflow, including OMXH
  and subsequent poststeps; it does not silently defer just USA.
- Correction to PRICE-01: the coordinated RC UI updater's operation lock reuses the
  same scheduler flock, so it already protects that batch's preflight/write interval.

There is no remaining requirement for a new Source service, identity master,
integration database, daemon, Source modification or global fresh-run gate. Actual
new adapter/dispatch/reader-import qualification remains work for a later explicitly
authorized implementation phase; the current RC interpreter has no installed
StockCore package. The plan specifies the bounded trusted-checkout read-only import
and deployment checks rather than silently depending on it.

## Measured and tested evidence

| Check | Actual result | Practical limit |
| --- | --- | --- |
| Canonical Source requalification | 4,201 unique matches; 4,169 with recent usable rows; 24 unavailable; eight partly HELD; 8,403 metadata/reader snapshots, max 1.868s | Per-ticker snapshots, not one cross-system historical/PIT snapshot |
| Exact 931-cohort measurements | 5,582 common observations; 773 OHLC-changed, 2,394 volume-changed; full per-field/volume quantiles and date breakdown in root-cause report | 42 undefined RC-zero relative-price fields counted, not filled; original RC payloads unavailable |
| Accepted snapshot binding | All 4,169 measured usable tickers retained the canonical-reader dependency token; explicit price/volume-unit and RC-market checks found zero additional holds | Must recheck future new scopes; old accepted observations are not universally immutable |
| Bounded direct fetch scopes | 8,338 per-ticker Source/RC overlap reads; maximum 0.099s rounded up in this run | Observed timings, not a production latency guarantee |
| Library formula parity | yfinance 0.2.66 and 1.7.0 independently: 30 frames, 63,962 exact same-vintage OHLC rows each; volume unchanged | Does not prove independent response vintages equal |
| Currency support | 3,715 identity/approved operating-USD, 447 accepted cached price-currency references, 39 unresolved | No currency inferred from price equality or usa label; old per-row RC currencies are not stored |
| Actions | Two material ratio conflicts, plus reverse-ledger discrepancies; 26 exclusive active holds after prior Source holds | No conflict resolved by rounding, tolerance, date proximity or corrected flag |
| Historical holdout | October 29 anchor/October 30 new row: 684 compatible/evidenced append and within-bounds retained-new-row comparisons among 931; 50 dividend anchor explanations | Today's accepted vintage, not historical availability certification; no actual live new session exists beyond RC maximum |
| Actual RC writer on tiny fixtures | Positive ordinary/NFE, dividend/AAPL, ETF/SPY and specifically evidenced ARI-dividend append; original row untouched; duplicate ignored | Isolated RC SQLite only, not an implemented provider |
| Matching old split | Actual sync_splits_for_ticker inserts zero matching events, preserves corrected bit/prices, no double multiplication | New/revised action preflight remains a modeled design until adapter implementation |
| Independent hard gates | Tiny numerical differences cannot bypass identity/route, split/date, operator/Source, currency, unit, new-price/volume or dependency holds | Tests cover policy model and existing actual helpers; future adapter wiring still needs its own tests |
| Data age/no-new behavior | Actual service flow skips downstream on empty history; nonempty duplicates retain divergence behavior; date-planning tests pass | Final market-level Dow/poststeps remain existing behavior; none run operationally |
| Lock overlap | Actual RC exclusive and Source shared lock helpers reject overlap both ways against temporary files | Production lock never acquired/changed by this study |
| SQLite closure | Actual isolated DELETE journal: commit busy during reader, succeeds after close; injected exception closes reader; mode=ro rejects writes | No write attempt against either operational database |
| Default provider isolation | Existing default adapter/CLI regressions pass; proposed USA/OMXH/manual selection modeled separately | No claim of passing integration tests for code that has not been implemented |

**Final focused tests: 98 passed in 9.08s. Full suite: NO.** The final run includes
the ignored study tests plus existing date-planning, history-conversion, ticker-flow,
main-adapter, Yahoo price-basis research and scheduler-CLI modules. Generated SQLite
fixtures, pytest roots and logs remain ignored.

Validation caught an incorrect initial test assumption that QQQ's October 29
1.2719% volume change would pass a 1% gate. The gate was retained; QQQ/AMD became
explicit negative holdout cases, while SPY (0.6926%) and AAPL (0.4700%) remain
positive. Intermediate logs are retained, and the final tests pass after adding
unit, invalid-anchor and evidenced-dividend cases. No threshold was widened merely
to make that failing test pass.

## Reproduction and artifact boundary

All machine-generated evidence is under existing ignored **temp/rc_sc_price_02/**:

| Artifacts | Contents |
| --- | --- |
| baseline.json | Starting HEAD/status and unrelated journal hash |
| requalify.py, coverage.json, requalify.log | Canonical current Source/identity/session qualification |
| measure.py, measurements.json, measure.log | Exact cohort dimensions, quantiles, per-ticker signatures, currencies and action comparisons |
| overlap_differences.json | Bounded six-position differences/ratios and small selected numeric examples, not a historical database extract |
| assess.py, assessment.json, assessment.log | Explicit policy model, exclusive final matrix, threshold grids and holdout results |
| segment_signatures.json | Three-position multiplier signatures and affected tickers |
| fixture_formula.py, formula_0.2.66.json, formula_1.7.0.json | Same retained inputs tested independently in both installed interpreters |
| append_fixtures.json, test_study.py | Tiny retained-value/synthetic isolated append/action/lock/closure cases |
| pytest_signed_off.log, pytest_signed_off/ | Final passing 98-test acceptance run and disposable databases |
| Earlier pytest logs/roots | Intermediate development checks, including the retained failed-oracle check |
| manifest.json | Input/script/report hashes, final checks and local commit identity recorded at finalization |

Run scripts using `python -B`/PYTHONDONTWRITEBYTECODE=1. Measurement and requalification
connections use explicit URI mode=ro, query_only and closure; no StockCore Temp,
runtime, source file or bytecode writes are needed. Formula checks construct no provider
object. The final test command is:

```text
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B -m pytest -q -o addopts='' -p no:cacheprovider --basetemp=temp/rc_sc_price_02/pytest_signed_off temp/rc_sc_price_02/test_study.py tests/test_stock_update_service_date_planning.py tests/test_stock_update_service_history_conversion.py tests/test_stock_update_service_ticker_update_flow.py tests/test_stock_update_main_adapters.py tests/test_yahoo_price_basis_research.py tests/test_stock_update_scheduler_cli.py
```

No copied market-data database, whole-history price extract or provider dump is
committed. The maintained deliverables are these five authored reports with bounded
aggregate tables/examples. PRICE-01 evidence is read as prior evidence, not overwritten.

## Operational and commit flags

Operational database writes **0**. Real provider requests **0**. Scheduled jobs run
by this task **0**. Analysis recalculations **0**. Production schema changes **0**.
Scheduler/timer/enabled/lock-policy changes **0**. RawCandle unrelated modifications
by this task **0**. StockCore modifications **0**. New integration services/databases
**0**. Isolated test fixture writes **YES**, only under the ignored task directory.

The local documentation commit contains only the five requested rc_sc_price_02
Markdown files. Final checks cover links, whitespace, numerical/table totals,
cohort coverage, ignored evidence, staged paths and preserved worktree content.
The final RawCandle commit hash is reported in chat and manifest.json, avoiding a
self-referential document hash. StockCore stays at the inspected HEAD. **Push: NO.**
