# Fundamentals V4 Phase 12C.1 Retention and Historical-Universe Audit

## Decision

Principal result: `OUTCOME_B_HISTORY_POLICY_CORRECTION_REQUIRED`.

Secondary blocker: `OUTCOME_C_HISTORICAL_RESEARCH_UNIVERSE_WORK_REQUIRED`.

Phase 12D is not authorized by this audit. Phase 12C production data was not
rolled back, no upstream request was made, and no production database, active
pointer or existing report was changed.

## Permanent history policy

The requested permanent ten-year minimum is not implemented. The ordinary
production bootstrap still calls `download_sharadar_5y_bulk()`, requests
`years=5`, records five-year entitlement text and has tests that require that
scope. The generic downloader and Phase 12C support `years=10`, but Phase 12C is
a separate operational command rather than the default ingestion policy.

Provider persistence is append-only through `INSERT OR IGNORE`. A later
snapshot does not replace the database, valid absent observations remain, and
no provider-history cleanup or rolling ten-year deletion path was found. Data
older than the requested window may therefore remain locally. Horizon metadata
and oldest-date reporting exist in Phase 12C but are not yet a single permanent
contract shared by every relevant ingestion path.

The smallest correction before Phase 12D is to define one versioned minimum
history constant of ten years, route the normal fundamentals bootstrap through
it, update run metadata/help/documentation, and replace five-year regression
expectations with tests that reject any smaller request. Append-only retention
must remain unchanged and ten years must not become a deletion cutoff.

## Oldest ARQ reconciliation

The complete staged source has 227,460 ARQ rows across 9,017 tickers and begins
at 2014-12-31. Exactly two rows precede the production minimum:

| Ticker | Fiscal period | Period end | Availability | Last updated | Reason |
|---|---|---|---|---|---|
| CHCR | 2014-Q4 | 2014-12-31 | 2018-05-18 | 2021-10-08 | Outside current target universe |
| HNGR | 2014-Q4 | 2014-12-31 | 2017-05-12 | 2022-08-08 | Outside current target universe |

Neither ticker belongs to the 2,470-ticker bootstrap universe or resolves to a
current canonical identity. After target selection the oldest ARQ date is
2015-06-30. Identity validation excludes no additional target row, so the
staging and production minimum is also 2015-06-30. The discrepancy is entirely
global-versus-current-target scope, not unintended data loss.

| Dimension | Global rows/tickers | Current snapshot target rows/tickers | Production rows/tickers | Append-only excess |
|---|---:|---:|---:|---:|
| ARQ | 227,460 / 9,017 | 88,979 / 2,449 | 89,432 / 2,451 | 453 |
| MRQ | 227,466 / 9,007 | 89,954 / 2,449 | 90,421 / 2,451 | 467 |

The production excess consists of observations retained from earlier snapshots.

## Historical universe

The operational universe is `temp/v3_active_tickers_99_27.csv`, a current
SEC/fiscal-calendar bootstrap of 2,470 ticker symbols. It is not a dated
historical membership universe. Of these, 2,449 occur in each current staged
ARQ/MRQ snapshot; production retains observations for 2,451 tickers.

ARQ retains 39.118526% of global provider rows and excludes 138,481 rows across
6,568 tickers. MRQ retains 39.546130% and excludes 137,512 rows across 6,558
tickers. Among excluded ARQ identities:

- 1,242 have an exact local OHLC ticker match;
- 507 of those have current Financial Services or Real Estate sector context;
- 735 have direct OHLC but another or blank current sector context;
- 5,326 have no direct local OHLC identity;
- zero resolve through the current canonical alias table;
- zero exact ticker identities are ambiguous.

All 2,449 staged target tickers have direct local OHLC matches. Full 30/60/120/
180-session labels were intentionally not calculated; this audit establishes
identity and OHLC feasibility only.

The retained Sharadar file has no permanent security/company identifier,
instrument type, listing status, acquisition, bankruptcy or delisting field.
Therefore funds, unsupported securities, acquired firms, bankruptcies and true
delistings cannot be classified authoritatively from this artifact. Current
sector/industry is descriptive context only and is not historical PIT taxonomy.

## Survivorship assessment

The current universe is appropriate for operational V4 and Snapshot reporting,
but it is unsuitable as the sole historical ML universe. Thousands of historical
fundamental identities are excluded, including 1,242 with direct local OHLC.
Selection from a current ticker universe creates a likely upward survivorship
bias, while acquisitions, specialized-accounting exclusions and unresolved
identities leave its exact magnitude uncertain.

Recommended architecture is Alternative B: leave operational production scope
unchanged and add a separate broad historical research universe with dated
identity resolution. Delisted/inactive identity and terminal-return semantics
need a distinct phase before return labels. Broadening all production canonical
and Snapshot readers (Alternative C) would couple operational reporting to an
ML-only requirement and introduce unnecessary migration risk.

## Phase 12B feasibility

Raw revised-history feasibility, not calculated Score readiness:

| Basis/year | Endpoints | 8Q chain | Raw Score feasible | Tickers | Signal months |
|---|---:|---:|---:|---:|---:|
| Fiscal 2021 | 9,157 | 7,518 | 7,379 | 1,909 | 27 availability months |
| Availability 2021 | 9,125 | 7,472 | 7,335 | 1,869 | 12 |
| Availability 2022 | 9,416 | 8,112 | 7,777 | 2,016 | 12 |
| Availability 2023 | 9,660 | 9,054 | 8,867 | 2,280 | 12 |

The original 9,157/7,379 fiscal-2021 result reconciles exactly. The
availability-year rows are the relevant estimate for the locked 2021-2023
development split. Raw warmup now makes the unchanged Phase 12B common-cohort
gate plausibly capable of passing, but this cannot be asserted until a separately
authorized canonical, TTM and downstream rebuild is complete. Development,
validation, confirmation, labels, purge, embargo, hypotheses and model gates
remain unchanged.

## Integrity and evidence

The final deterministic audit result fingerprint is
`91a63a678b7242171901be409b47cab7ac194f707f15810004e3e5ce94d413df`.
The source fingerprint is
`3a5cf6af14a0257ca00cab18469112eb2b51381b97e1271d28d2c6a9147e5f6c`
and the audit-contract fingerprint is
`bbca84258c0586dd5357284c32127de48d9b72524cdf5bdba5dcb064eed5c032`.
Two independent source analyses matched, and 19 serialized audit artifacts were
byte-identical between replay directories.

Production preflight and postflight aggregate fingerprint:
`43274d224adb48af0f1101c868dedb592b58dca918b499640dd353ce7933a32d`.
All protected database hashes, schemas, logical table row counts, active
pointers and report hashes matched. The taxonomy database's visible WAL was
explicitly included; it was empty, and read-only SQL observed its logical state.

Detailed evidence is under
`temp/fundamentals_v4_phase12c1/20260910T_PHASE12C1_FINAL/`.
The history remains currently revised history, not point-in-time history.

Focused audit, Phase 12C, provider/bootstrap/acceptance and production-isolation
regressions passed 100/100 tests. Compile checks and `git diff --check` passed.
The complete Fundamentals V4 suite was not rerun because this phase added an
isolated read-only research module and did not modify reusable Fundamentals
production code or an economic engine.
