# Phase 13G.3.1 - Sharadar Fundamentals Refresh Audit

Audit date: 2026-09-19  
Repository baseline: `23244f9662458d66420f49dad865d8c12e1e4993`  
Scope: read-only repository, production database, archive, report, and API inspection

## 1. Outcome

A clear architecture can be recommended. Use Sharadar `lastupdated` as a cheap
changed-ticker discovery hint, fetch complete ARQ and MRQ histories for every
changed known ticker, replace those histories in a provider candidate, and then
build fresh canonical and analysis databases. Publish the three validated
candidates as one guarded generation and advance refresh state only after
successful publication.

Two findings must be corrected before Production is enabled:

1. RawCandle's current `provider_record_key` is not the Sharadar source primary
   key. It substitutes `lastupdated` for `date`, although Sharadar declares
   `(ticker, dimension, date, reportperiod)` as its primary key.
2. The current Administration transaction mutates provider and canonical
   production databases in place and atomically replaces only analysis. Its
   exception rollback is useful, but a process or host crash between writes can
   leave the three-file set inconsistent.

The strategic hypothesis is otherwise sound. No production database was
modified during this audit.

## 2. Current Source Architecture

The relevant implementation is:

| Concern | Current code |
| --- | --- |
| Credentials and paths | `rawcandle/config/env.py` |
| Sharadar HTTP client, validation, redaction | `rawcandle/fundamentals/providers/sharadar.py` (`SharadarClient`) |
| Bulk download and provider ingestion | `rawcandle/fundamentals/schema/production_bootstrap.py` |
| Phase 12C backfill/archive build | `rawcandle/fundamentals/schema/phase12c_backfill.py`, `rawcandle/cli/run_phase12c_sharadar_backfill.py` |
| Archive source resolution | `rawcandle/fundamentals/phase13d1_real_source.py`, `rawcandle/fundamentals/admin/batch_add_tickers.py` |
| Canonical reconcile and TTM | `rawcandle/fundamentals/phase12d.py` |
| V2 analysis rebuild | `rawcandle/fundamentals/operating_income_v2/full_rebuild.py` |
| RV source and engine | `rawcandle/fundamentals/relative_valuation/source.py`, `engine.py` |
| Guarded Production transaction | `rawcandle/fundamentals/admin/production_transaction.py` |
| Operation adapters | `rawcandle/fundamentals/admin/production_operations.py` |
| Full workflow | `rawcandle/fundamentals/admin/full_workflow.py` |
| UI/service and reports | `rawcandle/fundamentals/admin/ui_service.py` and admin run writers |
| Scheduler exclusion lock | `rawcandle/scheduler/runner.py` |

The API base is `https://api.sharadar.com/v1.0`; Fundamentals uses
`/data/fundamentals` and the schema endpoint `/schema/fundamentals`. The client
retains a legacy `/data/SF1` alias. `SHARADAR_API_KEY` is loaded by the existing
environment configuration and sent in the `x-api-key` header. The audit printed
neither the key nor authenticated request URLs.

The verified archive is
`data/source_archives/sharadar/fundamentals/phase12c_20260910/sharadar_fundamentals_10y.zip`.
It contains one 802,067,611-byte CSV (`fundamentals-10Y.csv`) in a 225 MB zip,
with 1,036,805 rows, 9,299 tickers, 112 columns, and all six dimensions. Its
SHA-256 matches the hard-coded Phase 12C manifest value
`dc9d3f729830c1881873d10dec2dc2a3e7035d2a247e1737983bdb64cd0e0d36`.
Its maximum `lastupdated` is 2026-09-09. It is a verified acquisition snapshot,
not a continuously current authority: there is no active-version pointer,
refresh watermark, or currentness check.

## 3. Provider Schema

Production `data/fundamentals_provider.db` contains:

| Table | Purpose | Rows at audit |
| --- | --- | ---: |
| `provider_run` | Ingestion run metadata | 9 |
| `provider_observation` | Provider-neutral payload and content hash | 187,365 |
| `sharadar_fundamental_observation` | Parsed Sharadar Fundamentals values | 187,365 |
| `sharadar_ticker_metadata` | Stable identity/listing metadata | 74,078 |
| `sharadar_action_metadata` | Corporate-action metadata | 156 |
| `schema_version` | Provider schema version | n/a |

Sharadar's API schema declares the source primary key as:

`(ticker, dimension, date, reportperiod)`

RawCandle currently enforces uniqueness only on
`provider_observation(provider, native_table, provider_record_key, content_hash)`.
`insert_production_sharadar_observation()` constructs `provider_record_key` from
`(permaticker-or-empty, ticker, dimension, reportperiod, fiscalperiod,
lastupdated-or-date)`. This is not the source key and can assign one record key
to separate filings. The content hash prevents physical loss today, but source
identity and replacement semantics are ambiguous. Production has 184,959
distinct record keys for 187,365 rows, including 2,060 repeated-key groups.

Persisted parsed fields are:

`ticker`, `permaticker`, `dimension`, `calendardate`, `reportperiod`,
`fiscalperiod`, `date`, `lastupdated`, `revenue`, `gp`, `opinc`, `ebit`,
`ebitda`, `netinc`, `ncfo`, `capex`, `fcf`, `cashneq`, `debt`, `debtc`,
`debtnc`, `sharesbas`, `shareswa`, `shareswadil`, `netinccmn`, `receivables`,
`inventory`, `payables`, `deferredrev`, and `assets`. The full source payload is
also retained in `provider_observation.payload_json`.

There are no separate stored fiscal-year or fiscal-quarter columns. They are
derived from `fiscalperiod` and reporting dates when canonical rows are built.
`date` is the filing/reference date; `lastupdated` is the source change date.
The archive has no `permaticker`, explaining most null values in ARQ/MRQ rows.

Current dimensions and row counts are ARQ 91,262, MRQ 91,996, ART 1,672, ARY
615, MRT 1,420, and MRY 400. Current Add Tickers staging can store all six, and
the historical bulk archive has all six. Production bootstrap policy admits
ARQ/MRQ. Canonical winner selection uses ARQ only. TTM, Score, Lifecycle, and
Valuation derive from canonical ARQ quarters; Add Tickers eligibility also
requires ARQ. MRQ should be retained as the companion reported-quarter source.
Annual and trailing dimensions are not required by the active calculation
pipeline.

The existing `FUNDAMENTALS_REQUIRED_FIELDS` is insufficient for refresh: it
does not require `lastupdated` or the newer working-capital fields
`receivables`, `inventory`, `payables`, `deferredrev`, and `assets`.

## 4. Current Refresh Capability

The repository has useful pieces, but no routine current-state refresh:

- `SharadarClient.fundamentals()` supports ticker, dimension, fields,
  `date`/date ranges, and arbitrary table filters.
- Phase 12C can bulk-download and ingest a 10-year archive.
- Add Tickers resolves local provider rows, then the verified archive, then the
  network, and stages generic provider rows.
- `phase12d.reconcile_canonical()` selects revised ARQ winners and updates or
  inserts affected canonical rows.
- The B1 full rebuild path creates complete V2, RP V2, and RV analysis state.
- Administration already supplies run evidence, stage binding, backups,
  shared locks, copy testing, and postflight checks.

However, provider writes are append-only, no source watermark exists, there is
no complete per-ticker replacement operation, and canonical reconcile does not
delete rows absent from provider state. `canonicalize_arq_production()` is also
`INSERT OR IGNORE`, so it is not revision-safe. No scheduler job refreshes
Fundamentals. The former external Fundamentals scheduler post-step is absent.

Relevant existing tests include
`tests/test_fundamentals_v4_sharadar_provider.py`,
`tests/test_phase12c_sharadar_backfill.py`,
`tests/test_phase12d_operational_rebuild.py`,
`tests/test_fundamentals_admin_batch_add_tickers.py`,
`tests/test_fundamentals_admin_production_transaction.py`, and
`tests/test_fundamentals_admin_full_workflow.py`.

## 5. Sharadar Change Semantics

Read-only API evidence from 2026-09-19 established:

- `/schema/fundamentals` succeeds and reports 112 fields.
- `lastupdated` exists and has source DATE granularity.
- equality, `.gte`, and `.gt` filters on `lastupdated` work.
- `lastupdated.gt=2026-09-09` returned 1,839 rows for 213 tickers, dated through
  2026-09-19; the local provider/archive maximum was still 2026-09-09.
- A complete NVDA request returned 180 rows: 40 each ARQ/ART/MRQ/MRT and 10 each
  ARY/MRY, with no duplicate declared primary keys.
- A representative changed ticker, ABAT, demonstrated additions, historical
  changes, and a source-key removal against local state.

This proves that historical data changes and that current local state is stale.
It also shows that row disappearance must be supported. The API returned a JSON
list without pagination metadata in the exercised endpoint. Nasdaq Data Link's
table documentation describes filter operators and a 10,000-row per-call
limit: <https://docs.data.nasdaq.com/docs/python-tables> and
<https://docs.data.nasdaq.com/v1.0/docs/parameters-1>.

It remains unproven whether Sharadar can publish a delayed correction carrying
an old `lastupdated` date. A watermark alone therefore cannot be the sole
recovery authority.

## 6. Change Detection Options

| Option | Correctness and cost | Decision |
| --- | --- | --- |
| `lastupdated` delta | Cheap; directly verified; boundary and delayed-old-date risk | Primary discovery mechanism with overlap |
| Per-ticker history fingerprints | Authoritative for queried tickers; about two calls per 2,500 known tickers if split by dimension | Validation and periodic reconciliation, not daily discovery |
| Full 10-year snapshot | Simplest complete comparison; roughly 800 MB uncompressed and auditable, but expensive for every check | Recovery and periodic control |
| Existing repository mechanism | Archive and Add Tickers resolution are reusable building blocks, but neither tracks current source state | Extend rather than duplicate |

## 7. Recommended Detection Strategy

1. Query `/data/fundamentals` with `lastupdated.gte` from the prior published
   watermark minus a three-calendar-day overlap.
2. Reject or partition a result that reaches the 10,000-row limit. Partition by
   exact `lastupdated` date and dimension; if a partition still reaches the
   limit, fail closed and use the bulk-snapshot recovery path.
3. Deduplicate to changed ticker strings.
4. Resolve each ticker against existing canonical security/company identity and
   Sharadar ticker metadata.
5. Fetch complete ARQ and MRQ histories separately for every changed known
   ticker.
6. Compare normalized natural-key sets and semantic row hashes with current
   provider state. Only effective differences enter the replacement set.

The delta is discovery, not authoritative content. The complete ticker fetch is
the replacement authority. A periodic verified 10-year snapshot comparison is
the fallback for uncertain watermarks, truncation, or delayed old timestamps.

## 8. Watermark

Persist the highest `lastupdated` DATE observed in a successfully published
refresh, not local wall-clock time. The source exposes no timezone or time of
day, so UTC conversion is inapplicable to the watermark itself.

The next query is inclusive:

`lastupdated >= published_watermark - 3 calendar days`

Multiple rows sharing a date are normal. Deduplicate by the declared source key
and semantic hash. Advance state only after all three databases pass postflight
and the publication is durable. A Preview-only `NO_CHANGE` does not write or
advance state; re-reading a small overlap is intentional. Before Production,
refetch/revalidate the selected complete histories so a stale Preview cannot be
published.

The overlap protects date boundaries and retries, but cannot prove detection of
a newly published row bearing an older date. Periodic full-snapshot
reconciliation closes that gap.

## 9. Changed Ticker Classification

Compare complete normalized ARQ/MRQ natural-key sets and semantic hashes. The
reliable categories are:

- `NEW_QUARTER`: latest ARQ fiscal period advances and no prior row changes.
- `HISTORICAL_REVISION`: existing historical keys/values change, with no latest
  period advance.
- `NEW_QUARTER_AND_REVISION`: both conditions occur.
- `SOURCE_ONLY_METADATA_CHANGE`: source rows differ only in fields outside the
  persisted/canonical effective contract.
- `NO_EFFECTIVE_CHANGE`: normalized effective histories are identical.
- `NOT_IN_CANONICAL_UNIVERSE`: changed source ticker cannot resolve to an
  existing canonical identity.
- `SOURCE_REMOVAL`: a current natural key is absent from a proven complete new
  history.
- `REVIEW_REQUIRED`: identity ambiguity, invalid structure, or an untrusted
  destructive difference.

For each ticker report old/new latest fiscal period, old/new ARQ count, and
added/changed/removed natural-key counts. A new latest period plus other
historical differences is explicitly the combined category.

## 10. Acquisition Strategy

For each changed known identity, fetch complete histories for only ARQ and MRQ,
using all identity, date, financial, and working-capital fields required by the
provider and canonical contracts. Request each dimension separately and below
the 10,000-row ceiling. A result exactly at the ceiling is not accepted as
complete.

Ticker is necessarily the API selector because the Fundamentals schema and
archive do not contain `permaticker`. It must not be the sole authorization:
bind the requested ticker to current `sharadar_ticker_metadata` and canonical
security/company identity before replacement.

## 11. Provider Replacement

Start with a copy of the production provider DB. For every validated changed
ticker, delete its SHARADAR `fundamentals` ARQ/MRQ observations and parsed child
rows in the candidate, then insert the complete fetched ARQ/MRQ histories using
the true source key `(ticker, dimension, date, reportperiod)`. Preserve all
unrelated tickers and all unrelated native tables/dimensions.

The implementation must migrate or otherwise correct current identity handling
before replacement. The normalized semantic fingerprint should cover all
persisted source fields and be independent of SQLite row IDs, ingestion order,
JSON formatting, and file bytes.

A disappeared row is removed only after a structurally complete fetch. For a
destructive removal, require the Production source recheck to return the same
history fingerprint; otherwise classify it `REVIEW_REQUIRED`. Empty, malformed,
truncated, wrong-ticker, or partial responses can never authorize deletion.

Minimum validation includes exact requested ticker, only ARQ/MRQ, unique true
source keys, parseable and plausible dates, valid fiscal metadata, successful
schema parsing, no truncation, and usable ARQ structure. No arbitrary minimum
row count is imposed on young companies. Preview may continue after one ticker
failure to collect diagnostics, but any unresolved known ticker blocks Test and
Production for the entire refresh set.

## 12. Canonical Rebuild

Build a fresh complete canonical candidate from the updated provider candidate.
Current `_provider_winners()` correctly considers ARQ and selects a latest
filing per company/fiscal quarter using reporting/update dates, but
`reconcile_canonical()` is mixed incremental logic: it updates/inserts and
reports stale rows without removing them. It is insufficient for source
deletions.

The refresh implementation should preserve canonical identity/control tables,
then deterministically reconstruct derived quarter rows, financial rows,
provenance, TTM, and structural state from provider current state. An explicit
prune plus reconcile is acceptable only if tests prove equivalence to a fresh
reconstruction and no stale derived rows remain.

## 13. V2/RP/RV Rebuild

Use the existing B1 full V2 analysis rebuild from the fresh canonical candidate,
including Score, Lifecycle, Diagnostics, Valuation, RP V2, and RV. Read current
Sector/Industry from `data/osakedata.db.ticker_meta` and active taxonomy from
`data/analysis.db` domain `dc_ecosystem`, both read-only.

Do not add changed-ticker analysis, partial RP, incremental RV, or dependency
propagation. Current full rebuild runtimes are minutes, so the simpler complete
rebuild remains the correctness and recovery path.

## 14. No-Change Path

If discovery returns no relevant rows, or all fetched known histories normalize
to their current fingerprints, Preview returns:

`No relevant Sharadar fundamentals changes since the previous successful refresh.`

Status is `NO_CHANGE`, not failure. Test, Production, and a full workflow stop
after Preview. No candidate rebuild, database write, backup, or watermark
advance occurs.

## 15. Unknown Tickers

Use option C. Report source tickers that cannot be bound to the canonical
universe as `NOT_IN_CANONICAL_UNIVERSE`; do not ingest or publish them. Add
Tickers remains the sole deliberate universe-expansion workflow. Unknown ticker
activity remains visible and may be downloaded as structured evidence.

## 16. Transaction Architecture

Generalize the existing `ProductionOperation` and `run_transaction()` machinery
for a new `AdminOperationType.REFRESH_FUNDAMENTALS`. Reuse Preview/Test binding,
source fingerprints, storage preflight, verified backups, Administration lock,
scheduler lock, reporting, and postflight validation.

Do not reuse the current Add Tickers mutation sequence unchanged. It mutates
provider and canonical production files before constructing and replacing the
analysis candidate. Instead:

1. Build and validate provider, canonical, and analysis candidates before the
   publication boundary.
2. Acquire the shared Administration and scheduler/production locks and recheck
   Preview, Test, production source fingerprints, and Sharadar refresh-set
   fingerprints.
3. Back up all three production files and fsync backups/directories.
4. Write a durable publication journal/recovery marker naming old and candidate
   fingerprints.
5. Replace the three files in a documented order, fsync each file and parent,
   run production-path postflight, then mark the journal complete.
6. On an ordinary exception, restore the whole set and verify it.
7. On startup, refuse new operations while an incomplete journal exists and
   deterministically finish or restore it.

Three independent `os.replace()` calls cannot be transactionally atomic as a
set. Locks prevent cooperating writers, not process/host failure or unlocked
readers observing an intermediate generation. A future generation directory
plus atomically switched active pointer would provide strict reader atomicity,
but that broader path/configuration migration is not required for the first
refresh implementation. Candidate-first publication plus a durable recovery
journal is the minimum safe correction.

## 17. Preview UX

Representative summary:

```text
37 known tickers have relevant Sharadar changes since 2026-09-09.
New quarter: 31
Historical revision only: 5
New quarter and revision: 1
Source removals: 2
Not in canonical universe: 3
Review required: 0
```

The table contains ticker, current latest quarter, source latest quarter,
classification, ARQ count before/after, and added/changed/removed rows. Display
the query boundary, source table/schema fingerprint, effective watermark, and
whether the result was complete. Keep raw row evidence downloadable rather than
placing every cell difference in the normal view.

## 18. Test UX

`Test on copies` applies exactly the bound refresh set to copies, performs the
fresh canonical and full analysis rebuild, and reports:

- provider tickers and row counts replaced;
- canonical quarters added, changed, and removed;
- Score/Lifecycle/Valuation status changes;
- RP/RV availability changes;
- zero-ARQ or no-analysis cases;
- validation and reporting-integrity failures;
- candidate database semantic fingerprints.

Normal output is concise; component-level numeric deltas remain in structured
evidence. Any unresolved ticker or invariant failure blocks Production.

## 19. Production UX

The receipt records old/new source watermark, discovery window, schema and
refresh-set fingerprints, changed ticker/category counts, provider replacement,
canonical and analysis rebuild outcomes, backup paths/hashes, publication
journal state, fsync/postflight results, rollback status, and a concise
per-ticker summary. It never includes API credentials or authenticated URLs.

## 20. Full Workflow

Reuse the stage-callable orchestration concept:

`Preview -> Test on copies -> Production update`

`full_workflow.py` is currently Add-Tickers-specific in operation type, ticker
input parsing, labels, and outcome handling. Extract a small operation adapter
contract for stage invocation, reports, and `NO_CHANGE`; keep the existing run
writer/progress/history model. Each stage retains its own report and the
workflow emits one lightweight summary. Do not clone the engine.

## 21. Scheduler

Technical capability: a daily discovery call can be cheap and must use the same
Administration/scheduler locks and durable run reporting. There is no existing
scheduled Fundamentals refresh to preserve.

Recommended initial policy: run Production manually. A scheduler may perform
discovery and notify/report `NO_CHANGE` or pending changes. Enable unattended
Production only after candidate-first multi-DB recovery, idempotent reruns,
alerting, and failure recovery have been exercised operationally. Scheduler,
Add Tickers, Refresh Fundamentals, Sector/Industry sync, and Taxonomy sync must
all share one exclusive production lock contract.

## 22. Runtime and Scale

Read-only production measurements:

| State | Size / rows |
| --- | ---: |
| Provider DB | 915 MB / 187,365 observations / 2,499 ARQ tickers |
| Canonical DB | 624 MB / 88,835 quarters and financial rows / 2,505 companies |
| Analysis DB | 861 MB / 88,835 score and valuation rows; 13,995 RP rows; 2,444 RV company rows |
| Combined write set | about 2.4 GB |
| Free filesystem capacity | about 823 GB at audit |

Existing successful copy-only Add Tickers runs took 454-690 seconds (median
472). Successful Production runs took 580-2,333 seconds (median 586; recent
normal runs about 580-593). One full workflow took 1,126 seconds. The Phase 12D
rehearsal records 211.96 seconds for a full no-change replay and 279.26 seconds
for an independent clean-copy apply, and recommends a 20-minute maintenance
window.

Existing evidence does not separate backup copy time reliably. No expensive
benchmark was run. A daily cheap check is practical; a rebuild on actual filing
days remains operationally acceptable in minutes, with a conservative
20-minute window and the observed long-tail run acknowledged.

## 23. Failure Modes

| Failure | Required behavior |
| --- | --- |
| Authentication, timeout, rate limit, provider unavailable | `FAILED`; durable sanitized evidence; no candidates published |
| Discovery reaches API limit | Partition deterministically or fail to snapshot recovery |
| Malformed/wrong-ticker/unexpected-dimension response | `REVIEW_REQUIRED`; block Test/Production |
| Partial or exactly-limit history | Never authorize replacement or deletion |
| Duplicate source key | Fail ticker validation |
| One ticker fetch fails | Continue Preview diagnostics if useful; block whole apply |
| Unknown identity | Report only; no universe expansion |
| Rename, merger, ADR, delisting, ambiguous identity | `REVIEW_REQUIRED`; do not auto-merge identities |
| Source changes after Preview/Test | Production recheck fails stale binding |
| Candidate rebuild/invariant failure | Preserve production; report failure |
| Exception during publication | Restore and verify all backed-up roles |
| Process/host crash during publication | Recover from durable journal before any new run |
| Delayed row with old `lastupdated` | Detect through periodic full snapshot reconciliation |

## 24. Recovery

The immediate recovery primitive is the verified three-database backup set plus
the publication journal. Restore all roles together, run SQLite integrity and
semantic postflight, and retain failure evidence.

The long-term recovery primitive is rebuild, not delta replay: acquire a fresh
verified 10-year Sharadar snapshot using the existing archive mechanism,
validate manifest/hash/schema/completeness, reconstruct provider current state,
then rebuild canonical and full analysis. Keep operational run reports for
history, but do not make recovery depend on a long chain of refresh deltas.

## 25. Alternatives Rejected

- Append only the latest quarter: misses amendments, restatements, corrections,
  and removals.
- Patch changed cells/rows: amplifies source-key ambiguity and partial-response
  risk.
- Changed-ticker-only downstream analysis: reintroduces dependency propagation
  and can leave RP/RV package state inconsistent.
- Download the full 10-year snapshot on every check: authoritative but
  needlessly expensive when verified delta discovery is available.
- Persist a long delta/version graph: adds recovery complexity without improving
  the current-state rebuild model.
- Use ticker alone as identity: unsafe around renames, mergers, delistings, and
  duplicate/ambiguous mappings.

## 26. Recommended Implementation Phases

### 13G.3.2 - Source contract and Preview

Correct provider source-key semantics; add minimal refresh state; implement
sanitized `lastupdated` discovery, complete ARQ/MRQ fetch/validation,
fingerprints, classifications, `NO_CHANGE`, and Preview reports. Read-only with
respect to production.

### 13G.3.3 - Copy-only replacement and rebuild

Implement candidate provider per-ticker replacement, deletion-safe fresh
canonical construction, full V2/RP V2/RV rebuild, validation, and Test reports.

### 13G.3.4 - Guarded three-database publication

Generalize the transaction adapter, build all candidates before publication,
add durable multi-file publication/recovery journal, source recheck, whole-set
backup/rollback, postflight, and Production receipt.

### 13G.3.5 - Workflow and operational automation

Generalize full-workflow orchestration and UI controls/history. Add scheduler
discovery/notification only. Evaluate unattended apply separately after
recovery behavior is proven.

### Periodic recovery control

Add a later bounded task that refreshes the existing verified bulk archive and
compares full provider semantics. This is the control for uncertain/delayed
timestamps, not a second archive architecture.

## 27. Open Questions

Only two material source/operational questions remain, and neither blocks the
copy-only design:

1. Does Sharadar contractually guarantee that every newly published correction
   receives a new `lastupdated` date? The observed API cannot prove this.
2. What full-snapshot reconciliation cadence and unattended Production policy
   does the operator want after the manual workflow and recovery journal have
   demonstrated reliability?

Direct answers required by the audit:

1. **Table/dataset:** Nasdaq Data Link Sharadar Fundamentals,
   `/data/fundamentals` (legacy alias `/data/SF1`).
2. **Dimensions:** Provider storage currently contains all six dimensions;
   active canonical/downstream use ARQ, with MRQ retained/eligible. Refresh
   should authoritatively replace ARQ and MRQ only.
3. **Natural key:** `(ticker, dimension, date, reportperiod)` per live schema.
4. **`lastupdated`:** Yes, a DATE field.
5. **Filterable:** Yes; equality, `.gte`, and `.gt` were verified.
6. **Efficient changed-ticker discovery:** Yes, by overlapped `lastupdated`
   delta, subject to the 10,000-row guard.
7. **Complete ticker history:** Yes for representative requests, split by
   ARQ/MRQ and guarded against limit/truncation; the API provides no explicit
   pagination completeness marker.
8. **Historical changes:** Yes, proven by current API-versus-local comparison.
9. **Rows disappear:** Yes in observed current-state comparison; replacement
   must support removal but only from a proven complete response.
10. **Archive value:** Yes, as verified fallback/recovery and periodic full
    comparison; it is not current authority.
11. **Existing support:** Client filters, archive/bulk ingestion, Add Tickers
    source resolution/staging, canonical reconcile, full analysis rebuild, and
    Administration guards/reports are reusable; refresh/replacement/state are
    missing.
12. **Rows replaced:** Complete SHARADAR Fundamentals ARQ/MRQ history for each
    validated changed known ticker, in a candidate provider DB.
13. **Canonical scope:** Fresh complete rebuild is recommended because current
    reconcile retains source-deleted stale rows.
14. **Analysis scope:** Full V2, RP V2, and RV rebuild.
15. **Runtime:** Normally about 8-20 minutes from existing real evidence, with
    an observed long-tail Production run of about 39 minutes.
16. **Minimum metadata:** Dataset/table, published source watermark, provider
    semantic fingerprint, source schema fingerprint/version, successful run ID,
    and completion UTC. One current-state row is sufficient.
17. **No change:** Preview returns `NO_CHANGE`; skip Test, Production, backups,
    rebuild, and watermark write.
18. **Unknown/new tickers:** Report `NOT_IN_CANONICAL_UNIVERSE`; Add Tickers owns
    expansion.
19. **Locks:** Shared Administration operation lock and scheduler/production
    lock across every production-writing Fundamentals operation, plus durable
    publication recovery state.
20. **Workflow reuse:** Yes, after extracting the currently Add-Tickers-specific
    stage adapter/input/label logic.
21. **Main failures:** API/auth/rate/truncation, malformed or incomplete ticker
    histories, identity ambiguity, stale stage binding, candidate validation,
    multi-file crash window, and delayed old-timestamp updates.
22. **Sequence:** Preview/source contract, copy-only replacement/full rebuild,
    guarded three-file publication, then workflow/UI and optional scheduler
    discovery.

## 28. Git

Only this documentation file is intended to change. No runtime code or
production data is changed. The documentation commit message is:

`docs: audit Sharadar fundamentals refresh architecture`

The commit containing this file is identified by
`git log -1 --format=%H -- docs/fundamentals_v4/fundamentals_v4_phase13g3_1_sharadar_refresh_audit.md`.
Its exact hash and final clean `git status` are reported in the Phase closeout;
a Git commit cannot embed its own final object hash without changing that hash.
