# Phase 13G.3.2 - Refresh Source Contract and Read-Only Preview

Date: 2026-09-19  
Baseline: `466a93bd1971b7b97010312a5e9472495f59fe76`  
Production database access: read-only

## 1. Outcome

Phase 13G.3.2 succeeded. RawCandle now has a corrected Sharadar source-row
identity contract, deterministic raw/effective fingerprints, refresh-state and
bootstrap semantics, fail-closed ARQ/MRQ acquisition, effective change
classification, publication-date bootstrap evidence, and a new read-only
`Refresh Fundamentals` Preview in Fundamentals Administration.

No provider, canonical, analysis, market, or taxonomy production database was
written. Test on copies, Production update, candidate replacement, canonical
rebuild, publication, and scheduling remain intentionally unimplemented.

## 2. Source Key

The implemented authoritative Sharadar source key is:

`(ticker, dimension, date, reportperiod)`

`source_key()` and `source_key_evidence()` in
`rawcandle/fundamentals/admin/refresh_fundamentals.py` normalize ticker and
dimension to uppercase and retain source dates verbatim after date validation.
The identity excludes `lastupdated`, row order, JSON order, SQLite IDs, and
content hashes.

## 3. Legacy Provider-Key Gap

Production was inspected but not migrated:

| Diagnostic | Count |
| --- | ---: |
| Provider observations | 187,365 |
| Legacy `provider_record_key` groups | 184,959 |
| Repeated legacy-key groups | 2,060 |
| Rows mapping cleanly to the true source key | 187,365 |
| True source-key groups | 186,530 |
| Repeated true source-key groups | 835 |
| Extra historical versions under true keys | 835 |

Preview collapses legacy versions deterministically to the greatest
`lastupdated`/observation order for comparison. Phase 13G.3.3 must replace these
histories in a candidate and establish true-key replacement storage. Existing
Add Tickers persistence remains unchanged in this phase.

## 4. Normalized Source Contract

`normalize_source_row()` separates:

- identity: `ticker`, `dimension`, `date`, `reportperiod`;
- source update metadata: `lastupdated`;
- fiscal metadata: `calendardate`, `fiscalperiod`;
- effective values: `revenue`, `gp`, `opinc`, `ebit`, `ebitda`, `netinc`,
  `ncfo`, `capex`, `fcf`, `cashneq`, `debt`, `debtc`, `debtnc`, `sharesbas`,
  `shareswa`, `shareswadil`, `netinccmn`, `receivables`, `inventory`,
  `payables`, `deferredrev`, and `assets`.

Dates and `YYYY-Qn` fiscal identities are structurally validated. Financial
values are normalized independent of API/SQLite numeric representation.

Two hashes are retained:

- raw source fingerprint includes `lastupdated`;
- effective content fingerprint excludes `lastupdated` but includes source
  identity, fiscal metadata, and all effective values.

Histories are sorted by true source key before ARQ, MRQ, and combined hashes are
calculated. Retrieval and JSON ordering therefore do not affect fingerprints.

## 5. Refresh State

The minimal singleton schema is defined as `REFRESH_STATE_SCHEMA_SQL` with:

- source dataset and table;
- published source watermark;
- provider semantic fingerprint;
- source schema fingerprint;
- successful run ID;
- completion UTC.

`ensure_refresh_state_schema()` is available for candidate/fixture databases.
It was not run against production.

Production has no state row, so current Preview uses `BOOTSTRAP_BASELINE`. The
derived provider maximum is `2026-09-09`; it is explicitly not represented as a
successfully published watermark. Established state will be read only from the
singleton row after a later successful Production publication.

## 6. Watermark

Established state computes:

`query_start_date = published_source_watermark - 3 calendar days`

and uses inclusive `lastupdated.gte`. Bootstrap applies the same overlap to the
derived provider maximum. Preview reports published/derived watermark, overlap,
query start, maximum observed source date, source row count, and ticker count.
It never persists or advances state.

The accepted live Preview used query start `2026-09-06` and observed source
maximum `2026-09-19`.

## 7. Discovery

Discovery makes lightweight ARQ and MRQ calls projected to `ticker`,
`dimension`, and `lastupdated`. If a call returns fewer than 10,000 rows, it is
complete under the exercised table contract. At exactly 10,000 rows, discovery
partitions every date in the window by exact `lastupdated` and dimension. An
exact-date/dimension partition that still reaches 10,000 returns
`DISCOVERY_INCOMPLETE` and cannot authorize future Test.

Authentication, HTTP/provider, malformed row, date, and incomplete-partition
failures are fail-closed and written as sanitized durable evidence.

## 8. ARQ/MRQ Complete Fetch

Each known changed ticker is fetched independently for full ARQ and full MRQ
history. Complete-history authority intentionally does not use a `fields=`
projection. Live diagnosis proved that Sharadar's projected response could
return `fiscalperiod` empty despite requesting it. The unprojected response
returned all 112 fields and valid `fiscalperiod` values.

This correction is narrow: it removes the lossy projection assumption; it does
not relax validation. Trust remains `INCOMPLETE` or `FAILED` for:

- empty history;
- wrong ticker or dimension;
- missing/invalid date or fiscal metadata;
- malformed financial values;
- duplicate true source keys;
- exactly-limit/truncated response;
- provider failure.

A one-row young-company history is accepted when structurally valid. Discovery
retains its safe lightweight projection.

## 9. Change Comparison

Current provider rows are normalized with the same contract. Legacy versions of
one true key are collapsed to current state before comparison. For ARQ and MRQ,
Preview calculates:

- physical and normalized current row counts;
- source row counts;
- added and removed source-key sets;
- common-key effective changes;
- common-key metadata-only changes;
- old/new raw and effective history fingerprints.

Comparison never relies on `lastupdated` alone. A removal is reported only when
the fetched history is `COMPLETE`; otherwise the ticker is `REVIEW_REQUIRED`.

## 10. Classifications

Rules are deterministic:

- `NEW_QUARTER`: latest ARQ fiscal identity advances without prior-history
  change.
- `HISTORICAL_REVISION`: effective prior history changes without an advance.
- `NEW_QUARTER_AND_REVISION`: the latest quarter advances and earlier source
  content also changes or disappears.
- `SOURCE_REMOVAL`: trusted complete source omits current keys without a latest
  quarter advance.
- `SOURCE_ONLY_METADATA_CHANGE`: only raw metadata such as `lastupdated`
  changes.
- `NO_EFFECTIVE_CHANGE`: raw/effective histories are already equivalent.
- `NOT_IN_CANONICAL_UNIVERSE`: no canonical identity exists; Add Tickers owns
  expansion.
- `REVIEW_REQUIRED`: identity or complete-history evidence is ambiguous or
  invalid.

Latest quarter is derived from explicit `fiscalperiod`, not calendar quarter.

## 11. Publish Date Contract

The repository has no column named `publish_date`. Existing canonical semantics
are:

- Sharadar winner `date` is written to `v4_quarter.source_availability_date`;
- `reconcile_canonical()` may move it when a winning row changes;
- `first_public_result_date` exists but was NULL for all 88,835 production
  quarters;
- TTM and downstream availability use `source_availability_date`;
- there was no explicit publish-date repair path.

The locked two-field contract is now explicit:

- `source_availability_date` may follow the current winning Sharadar source row;
- `first_public_result_date` stores the original quarterly publication date and
  is immutable during routine refresh after bootstrap;
- preserved dates bind to `(company_id, fiscal_year, fiscal_quarter)`, never a
  source row, hash, order, or SQLite surrogate ID;
- only a separately authorized explicit repair operation may change an
  established `first_public_result_date`.

The read-only bootstrap audit compared every canonical quarter's current
`source_availability_date` with the winner selected by the accepted existing
policy. All 88,835 quarters were `BOOTSTRAP_ELIGIBLE`; zero required repair.
Phase 13G.3.3 may populate `first_public_result_date` on copies only.

For an existing affected quarter, Preview records the existing availability and
first-public values, proposed bootstrap baseline, source `date`/`lastupdated`,
drift diagnostic, and policy result. For a genuinely new quarter, initial date
selection is deferred to existing canonical policy. Source removals retain
quarter-level preservation evidence even when the removed source row has no new
winner counterpart.

Focused tests cover historical financial revision, metadata-only update,
winner/source-key change, new quarter, bootstrap, immutable established date,
and explicit-repair separation.

## 12. Unknown Tickers

Discovery tickers without exactly one trustworthy canonical security/company
identity are not ingested. Missing identities are
`NOT_IN_CANONICAL_UNIVERSE`; ambiguous canonical/provider/permaticker bindings
are `REVIEW_REQUIRED`. Current Sharadar ticker metadata is checked when
available. Add Tickers remains the only universe-expansion workflow.

## 13. NO_CHANGE

Preview returns `NO_CHANGE` when no trusted known ticker needs effective
replacement, including a discovery window containing only repeated overlap,
metadata-only differences, or unknown source tickers. It does not build
candidates, make backups, run downstream analysis, or write refresh state.

## 14. Preview UX

Fundamentals Administration now offers `Refresh Fundamentals` as a fourth
operation. It has no ticker input and exposes Preview only. `Test on copies`,
`Production update`, and `Run full workflow` are not presented as available for
this operation.

The executive summary shows discovery rows/tickers, effective known changes,
classification counts, unknowns, and review-required count. The compact table
shows ticker, old/new latest quarter, classification, ARQ before/after, row
deltas, and publication-date handling. Details remain downloadable.

## 15. Real Read-Only Preview

Accepted run:

`20260919T190406Z_refresh_fundamentals_0fb542ea4f44`

Runtime was 41 seconds. Results:

| Metric | Count |
| --- | ---: |
| Discovery ARQ/MRQ rows | 539 |
| Discovered source tickers | 266 |
| Known canonical tickers | 77 |
| Effective changed known tickers | 70 |
| New quarter | 8 |
| Historical revision only | 3 |
| New quarter and revision | 48 |
| Source removal | 11 |
| No effective change | 7 |
| Unknown source tickers | 189 |
| Review required | 0 |

The refresh-set fingerprint is
`601755ff823d8e70da33b5b684cd0757e031b5cc62c85c9e68d42b299fdd7d39`.

The preceding diagnostic run used a projected complete-history request and
produced 77/77 `COMPLETE_HISTORY_NOT_TRUSTED` cases and 5,458 row-level
`INVALID_FISCAL_PERIOD` errors. The accepted rerun retained the same 539 rows,
266 discovered tickers, 77 known tickers, and 189 unknown tickers, but had zero
review cases. This proves one shared API projection contract mismatch rather
than broad malformed data or identity failure.

Five end-to-end controls were independently refetched after the correction:

| Ticker | ARQ/MRQ trust | Result | Added | Changed | Removed |
| --- | --- | --- | ---: | ---: | ---: |
| ABAT | COMPLETE / COMPLETE | New quarter and revision | 2 | 9 | 1 |
| AI | COMPLETE / COMPLETE | New quarter | 2 | 0 | 0 |
| ABM | COMPLETE / COMPLETE | Source removal | 0 | 0 | 2 |
| GOSS | COMPLETE / COMPLETE | Historical revision | 0 | 68 | 0 |
| AVGO | COMPLETE / COMPLETE | New quarter and revision | 2 | 0 | 2 |

Every full response had 112 fields; every row had `fiscalperiod`; normalized
row count equaled raw response count; no trust errors remained. No target
success percentage was used.

## 16. Structured Artifacts

Each Preview writes:

- `request.json`;
- `refresh_preview.json`;
- `refresh_ticker_changes.json`;
- `refresh_unknown_tickers.json`;
- `refresh_review_required.json`;
- `publish_date_bootstrap_exceptions.json`;
- `operation_report.md`;
- normal result, status, progress, heartbeat, exit-code, and manifest artifacts.

Raw API payloads and secrets are not written. Evidence contains normalized
keys, counts, fingerprints, classifications, trust status, and bounded details.

## 17. Progress/Heartbeat

The operation declares nine stages:

`REFRESH_STATE`, `SOURCE_SCHEMA`, `CHANGE_DISCOVERY`, `IDENTITY_RESOLUTION`,
`COMPLETE_HISTORY_FETCH`, `SOURCE_COMPARISON`, `CLASSIFICATION`, `REPORT`, and
`COMPLETED`.

Ticker-level progress updates counts and heartbeats without source-row event
spam. Existing Admin progress, history, operation lock, reports, and downloads
are reused.

## 18. API Failure Semantics

Authentication, timeout, rate limit, unavailable provider, malformed response,
and incomplete discovery fail Preview with sanitized durable evidence. One
known ticker's invalid complete history is retained as `REVIEW_REQUIRED` while
other tickers may be inspected, but the Preview sets future Test authorization
false. Wrong ticker/dimension, duplicate key, empty history, invalid dates,
missing fiscal identity, and exact-limit history remain fail-closed.

No API key, authorization header, or authenticated URL is included in artifacts
or reports.

## 19. Add Tickers Regression

The existing `_provider_observation()` and Add Tickers provider key were not
changed. Refresh source identity is isolated in the new module until candidate
migration. Existing Add Tickers Preview, copy apply, Production transaction,
full workflow, UI, progress, and Sharadar provider tests were included in the
targeted regression set.

One expected UI test was updated from three to four visible Administration
operations. No Add Tickers behavior changed.

## 20. Production Safety

All SQLite access in Refresh Preview uses `mode=ro` and `PRAGMA query_only=ON`.
The operation snapshots size and nanosecond mtime for provider, canonical,
analysis, market, and taxonomy files before and after every run and fails if any
differs. Both diagnostic and accepted live runs reported
`production_file_state_unchanged: true`.

No refresh state, schema migration, provider rows, canonical dates, analysis
rows, `ticker_meta`, or taxonomy data were written. The only durable writes are
Administration run artifacts.

## 21. Tests

Focused suite after the projection correction:

```text
pytest -q tests/test_fundamentals_admin_refresh_preview.py
16 passed
```

The suite covers true key identity, raw/effective/history fingerprints,
watermark/bootstrap, 10,000-row partition/fail-closed behavior, complete
ARQ/MRQ validation, the exact lossy-projection regression, comparisons,
classifications, publish-date semantics, Preview artifacts/read-only safety,
and Preview-only UI capability.

Final targeted regression:

```text
pytest -q tests/test_fundamentals_admin_refresh_preview.py \
  tests/test_fundamentals_v4_sharadar_provider.py \
  tests/test_fundamentals_admin_ui.py \
  tests/test_fundamentals_admin_progress.py \
  tests/test_fundamentals_admin_foundation.py \
  tests/test_fundamentals_admin_batch_add_tickers.py \
  tests/test_fundamentals_admin_production_transaction.py \
  tests/test_fundamentals_admin_full_workflow.py
157 passed in 141.86s
```

An additional focused UI assertion added after that run also passed:

```text
pytest -q tests/test_fundamentals_admin_ui.py::test_refresh_fundamentals_is_input_free_preview_only
1 passed in 7.46s
```

## 22. Next Phase

Phase 13G.3.3 should:

1. copy the production provider/canonical/analysis set;
2. bootstrap `first_public_result_date` for all eligible existing canonical
   quarters in copies and fail on any repair-required exception;
3. replace complete ARQ/MRQ histories for the bound changed ticker set using
   the true source key and deletion-safe semantics;
4. preserve bootstrapped/established first-public dates by stable quarter
   identity while allowing source availability to follow the new winner;
5. build a fresh deletion-safe canonical candidate;
6. rebuild full V2, RP V2, and RV;
7. validate and report Test on copies only.

It must not publish to production.

## 23. Git

The intended commit message is:

`feat: add read-only Sharadar fundamentals refresh preview`

The final commit hash and clean/dirty Git status are reported in the Phase
closeout. No push is performed.
