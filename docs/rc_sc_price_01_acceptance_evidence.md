# RC-SC-PRICE-01: acceptance evidence

**Study result COMPLETE; implementation readiness BLOCKED under all current stated
constraints.** This is a completed feasibility investigation, not operational
acceptance of a provider. See [current contract](rc_sc_price_01_current_provider_contract.md),
[compatibility](rc_sc_price_01_stockcore_data_compatibility.md) and
[implementation plan](rc_sc_price_01_implementation_plan.md).

## Inspected baselines and bounded scope

| Repository | Starting/inspected HEAD | Branch/worktree |
| --- | --- | --- |
| RawCandle | 4d06c793cb6d1feb6120473955f7da2c9d4b500b | chore/ignore-backups; /home/kalle/projects/rawcandle only |
| StockCore, read-only | 20d3cdcddf82fdfac29ae652219fd1725eea4b7b | main; /home/kalle/projects/stockcore only |

RawCandle had one tracked modification (`data/.fundamentals_admin_publication_journal.json`)
and existing untracked research scripts/plot, Fundamentals generation data, OHLCV
repair documents/outputs/script and missing-day reports. StockCore's bounded Git
status was clean. The initial status lists are retained in ignored evidence. No
preexisting path was staged, reset, restored, cleaned or intentionally modified.

Inspection followed the installed RC unit → runner → app adapters → service fetch,
conversion/write/downstream and direct split helper chain. StockCore inspection was
limited to AGENTS, relevant architecture/P02 contracts and supersessions, accepted
identity/Source/calendar/reader/storage/transport/daily-owner contracts and their
current runtime facts. No broad repository content scan, operational import,
unrelated implementation audit or external web/provider query was needed.

## Reproducible evidence location

All generated evidence and disposable scripts are in the existing ignored directory
**`temp/rc_sc_price_01/`** (`git check-ignore` verified). It contains:

| Artifact | Purpose |
| --- | --- |
| probe.py / probe.log / coverage.json | Exact RC scheduler candidate aggregation; dated mapping, canonical short Source reader scopes and cutoff counts |
| safety.py / safety.log / coverage_safety.json | Nine Source operator holds, strict recent OHLCV overlap and split inventory reconciliation; preliminary dispositions |
| compare.py / compare.log / comparison.json | Installed library signature, retained same-vintage/independent fixtures, 16 accepted Source sample windows, frame conversion, research guard and isolated SQLite contention |
| contract_probe.py / contract_probe.log | Synthetic missing/unique/ambiguous/unaccepted routes, ID ambiguity, DST dates, types, date planning and mode=ro write refusal against disposable SQLite |
| pytest.log / pytest/ | Focused existing regression result and isolated test data |
| contention.sqlite | Tiny synthetic two-connection fixture; no copied market database |
| rawcandle_status_before.txt / stockcore_status_before.txt | Initial unrelated-worktree inventory |
| manifest.json | Script/retained-input hashes and final status evidence, generated during final validation |

These are disposable generated evidence, not committed provider dumps. The maintained
deliverables are the four authored documents only. Their numbers are observations
at the study's recorded source snapshots, not targets to force future runs to match.

Executed with bytecode disabled and no application startup/acquisition:

```text
/usr/bin/python3 -B temp/rc_sc_price_01/probe.py
/usr/bin/python3 -B temp/rc_sc_price_01/safety.py
/usr/bin/python3 -B temp/rc_sc_price_01/compare.py
/usr/bin/python3 -B temp/rc_sc_price_01/contract_probe.py
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B -m pytest -q -o addopts='' -p no:cacheprovider --basetemp=temp/rc_sc_price_01/pytest tests/test_stock_update_service_date_planning.py tests/test_stock_update_service_history_fetch.py tests/test_stock_update_service_history_conversion.py tests/test_stock_update_service_ohlcv_write.py tests/test_stock_update_service_ticker_update_flow.py tests/test_stock_update_main_adapters.py tests/test_yahoo_price_basis_research.py
```

The scripts directly open both production databases with `mode=ro`, `query_only`,
short read scopes and explicit closure. The probe Store subclass overrides the
connection open only and retains canonical validation and PriceReader semantics;
it is not installed or used by RC. The safety script fetches only six-session
overlap and small metadata. The comparison script reads bounded representative
windows. It never invokes a production writer/downstream callback. Only synthetic
SQLite fixtures receive writes. No large database copies, backups or extracts exist.

## Executed results

| Check | Actual evidence | Result / limitation |
| --- | --- | --- |
| Installed scheduled entrypoint | User service file points to run_stock_update_scheduler.py, /usr/bin/python3, actual JSON omxh+usa | Verified statically; loaded timer runtime state not claimed |
| Effective RC Yahoo defaults | /usr/bin/python3 and venv: yfinance 0.2.66, pandas 2.3.3; local PriceHistory/history/utils source read | auto_adjust=True established, not inferred from loose requirements |
| Effective StockCore environment | .venv: yfinance 1.7.0, pandas 2.3.3; transport explicit arguments read | Ordinary six-field output contract established |
| Ticker coverage | 4,622 scheduled = 4,201 unique + 127 missing + 196 ineligible + 98 unsupported; zero ambiguous | Snapshot mapping, not safe-import count |
| Canonical recent Source qualification | 4,169 qualified recent; 24 unavailable; 8 partially HELD | Nine explicit operator holds overlap unavailable group |
| Preliminary safety screen | 3,236 candidates; 931 overlap mismatches; 2 split conflicts; other skips as compatibility table | 1,386 withheld now; candidates still need broader history proof |
| Newer sessions | No uniquely mapped ticker has a qualified recent session newer than RC latest | No operational update executed to demonstrate a positive live append |
| Same-vintage float transform | 30 retained ordinary frames, 63,962 rows vs installed utils.auto_adjust | Exact OHLC equality; unchanged volumes |
| Independent retained True frames | 11 windows, 183 common rows, 54 bitwise-exact OHLC rows; zero rows beyond 1ppm diagnostic | Different captures are not exact parity; tolerance is not authorization |
| Representative accepted Source | 16 windows, including dividends, split/reverse split, ETFs, short/unknown prefix, inactive, HELD and stale | Exact frame reconstruction on each stored sample; actual RC historical/value differences retained, not repaired |
| Date/types/duplicates/no-data | Existing conversion/date/write/flow regressions plus DST synthetic probe | Requested end-exclusive and existing downstream triggers established |
| Missing/ambiguous mapping | Actual zero ambiguities; synthetic missing/unique/competing ticker + by-ID/unaccepted route | Reject ambiguity verified without operational identity mutation |
| Research restriction | Production adjusted read without research flag raises ADJUSTED_BASIS_REQUIRES_EXPLICIT_RESEARCH | Production compatibility policy remains a hold |
| Source closure / contention | Tiny DELETE-journal fixture: writer commit busy while reader open, succeeds after close; isolated mode=ro rejects UPDATE | Storage behavior verified; production contention timing not stress tested |
| Snapshot timing | 8,403 canonical/metadata read scopes, max 2.033s; 8,338 short overlap fetches, max 0.000512s | Bounded study observations; operational deadline/closure regression still required |
| Application-level concurrent jobs | StockCore shared scheduler flock versus RC exclusive flock, traced through FULL_WORKFLOW | Existing lock rejects concurrent RC start before adapter; no production lock manipulation tested |
| Manual Yahoo isolation | Existing default adapter factory tests pass; task diff only docs; scheduler UI Run now also calls the runner | Future explicit CLI-origin factory injection must preserve default runner/UI behavior |
| Focused existing tests | **55 passed in 9.36s** | Seven named modules above; full suite **NO** |

One-ppm comparisons are diagnostics inherited from the prior retained experiment,
not an approved way to merge different observations. Exact-historical parity and
action continuity must not be inferred from numerical closeness or a qualified
Ordinary row alone. Neither provider offers historical point-in-time certification.

## Safety boundaries and outstanding acceptance

Real Yahoo/provider requests **NO**. Scheduled update/source job **NO**. Source/RC
operational database writes **NO**. Analysis recalculation **NO**. Provider/UI code
changes **NO**. Scheduler/timer/enabled changes **NO**. StockCore repository writes
**NO**. New schemas/services/daemons **NO**. Production lock changes **NO**.
Only documentation, ignored analysis outputs and tiny isolated test SQLite writes
were produced. No runtime database was copied or staged.

The following were established by inspection/probes rather than implementation:
safe scheduled injection, canonical reader mapping, deterministic adjusted formula,
skip/no-new behavior and minimal rollback. The following remain unqualified:
whole-history parity for every prospective ticker, operating while Source holds the
existing scheduler flock, permitted production adjusted-reader binding, and safe
new/revised split handling without reaching RC's destructive refetch path. These
are explicitly recorded blockers/conditional scope choices in the plan; the study
does not weaken any of them to claim readiness.

## Final change and commit boundary

Only these requested files belong to the local documentation commit:

- docs/rc_sc_price_01_current_provider_contract.md
- docs/rc_sc_price_01_stockcore_data_compatibility.md
- docs/rc_sc_price_01_implementation_plan.md
- docs/rc_sc_price_01_acceptance_evidence.md

Final validation checks relative document links, coverage/disposition sums, ignored
evidence, whitespace, selected diff/staged paths and both repositories' status/HEAD.
The documentation commit's hash is reported in the final response and ignored
manifest (a document cannot contain its own final commit hash without changing it).
StockCore remains at its inspected HEAD; unrelated RC status entries are preserved.
**Push: NO.**
