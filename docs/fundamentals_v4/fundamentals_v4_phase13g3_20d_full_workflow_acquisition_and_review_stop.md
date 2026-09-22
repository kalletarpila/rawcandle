# Phase 13G.3.20D - Add Tickers acquisition authority and workflow review stop

## Baseline and scope

- Source baseline: `e4e2442 feat: remove admin runs from UI history`.
- Branch: `chore/ignore-backups`.
- The history visibility policy from `e4e2442` remains in force. This phase changes the ordering of eligible rows only.
- No live Preview, Test, Production, Full Workflow, Refresh, taxonomy, or scheduler job was run.

## Retained acquisition evidence

The successful and failed Preview requests are byte-identical. Both request files have SHA-256
`31688945e02b3df448e55d0f9b4bba8a9748e69718bfccd63937cc85c1ba5f62` and request exactly
`KRSA PSQL QVCG`, market `usa`, with network access enabled.

| Ticker | Successful Preview | Failed Full Workflow Preview | Proven cause |
| --- | --- | --- | --- |
| KRSA | HTTP 200, `SUCCESS`, 160 rows, 34 ARQ | final HTTP 500, `TRANSIENT_FAILURE`, 0 parsed rows | Bounded provider retry ended in a transient server failure |
| PSQL | HTTP 200, `SUCCESS`, 16 rows, 3 ARQ | HTTP 200, `SUCCESS`, 16 rows, 3 ARQ | Acquisition remained successful and unchanged |
| QVCG | HTTP 200, `SUCCESS`, 180 rows, 40 ARQ | final HTTP 500, `TRANSIENT_FAILURE`, 0 parsed rows | Bounded provider retry ended in a transient server failure |

The failed Preview recorded five requests: one successful PSQL request and two attempts each for KRSA and QVCG. The existing `SharadarClient` bounded retry was therefore active. There was no evidence that Sharadar authoritatively returned an empty quarterly history for KRSA or QVCG.

The first semantic collapse was `_network_rows()`: every non-success result was converted to an empty tuple. Planning then interpreted that tuple as `NO_USABLE_QUARTERLY_HISTORY`. A network acquisition failure must not be represented as authoritative zero quarterly history.

## Corrected acquisition contract

Add Tickers contract V7 records a structured per-ticker acquisition result:

- `SUCCESS_WITH_USABLE_DATA`
- `SUCCESS_NO_USABLE_QUARTERLY_HISTORY`
- `NETWORK_TRANSIENT_FAILURE`
- `NETWORK_PERMANENT_FAILURE`
- `RESPONSE_SCHEMA_INVALID`
- `INCOMPLETE_FISCAL_IDENTITY`

Only successful, structurally valid acquisition is authoritative for row and ARQ coverage. Failed or untrusted acquisition reports coverage as `Not established`, carries provider/HTTP status and a redacted error summary, and blocks application. Clearly transient outcomes remain marked retryable and reuse the provider client's bounded retry; permanent and schema failures are not blindly retried.

Successful empty responses retain `NO_USABLE_QUARTERLY_HISTORY`. Full complete-history acquisition remains unprojected and fiscal identity remains mandatory, preserving the V6 correction. The material acquisition/applyability change bumps the contract from V6 to `PHASE13G2_BATCH_ADD_TICKERS_COPY_ONLY_V7_ACQUISITION_AUTHORITY`, invalidating old authorization.

## Workflow and reporting

Preview now publishes a structured `applyability` object. A Full Workflow must not enter Test on copies when its bound Preview contains unresolved review-required items that make the plan non-applicable. Such a run stops at Preview; Test and Production invocation counts remain zero.

The earlier orchestration checked only the child's technical `COMPLETED` state, payload path, and fingerprint. Add Tickers Preview used `COMPLETED` for a technically completed calculation even when item decisions required review, so the old gate incorrectly entered Test.

Terminal reporting now separates:

- the technical failure/stop stage; and
- the authoritative item-evidence stage.

The latest materially completed child stage remains authoritative operator evidence even when a later stage fails technically. Requested, eligible, review, rejected, affected ticker, and per-item reason facts are promoted from that stage without Markdown parsing. The UI consumes the same terminal structure.

`ADMIN_ADD_TICKERS_STALE_PLAN_CONTENT_CHANGED` remains fail closed. A focused regression deliberately changes the bound plan fingerprint and verifies the exact guard.

## Run history ordering addendum

The old `history_entries(include_technical=True)` implementation grouped Administration rows before technical/legacy rows after cursor projection. That grouping overrode chronology. Cursor candidates were also sorted by raw path name, which could place untimestamped legacy evidence before timestamped runs.

Timestamp and ordering authority is:

1. the timestamp encoded in the durable run ID, which is available before projection and preserves lazy paging;
2. structured completion/start/status timestamps for display, with the run-ID timestamp as display fallback;
3. no timestamp when no parseable durable run identity exists.

Equal timestamps use run ID descending as a deterministic tie-breaker. Rows without a reliable timestamp follow all timestamped rows and use source/run directory identity descending as their deterministic order.

Run history is globally ordered by authoritative run timestamp descending; category, stage, and visibility classification do not override chronological ordering.

Rows without a reliable timestamp are placed after all timestamped runs and ordered deterministically.

The technical/legacy toggle changes inclusion only. It does not create category groups. Full Workflow, Preview, Test, Production, acceptance, maintenance, and legacy rows participate in the same ordering when eligible. The cursor still loads incrementally: 8, then 16, then 24. Each projected `result.json` is cached and read at most once. The initial page now avoids reading untimestamped technical directories that sort after valid run IDs. The `e4e2442` exclusion policy remains unchanged.

## Verification

Focused tests cover:

- usable success, successful empty history, transient failure, rate limit, permanent failure, invalid response/schema, malformed fiscal identity, and unprojected complete history;
- a technically completed Preview with one eligible and two review-required tickers stopping before Test and Production;
- a later technical Test failure retaining Preview item evidence;
- exact stale-plan content-change rejection;
- global mixed-category ordering, toggle behavior, equal-time tie-breaking, unavailable-time placement, 8/16/24 paging, and one-read projection caching;
- preservation of the `e4e2442` normal-history visibility policy.

Historical run directories were not rewritten or deleted. The identity resolution registry remained unchanged: KRSA, PSQL, and QVCG retain their approved fingerprints and DRK remains unapproved. Production database fingerprints/size/mtime are checked before and after the phase. Scheduler state was observed as timer enabled but inactive and service static/inactive; no scheduler command changed state.

The separate comprehensive fixture-sized Production-parity workflow suite remains deferred.
