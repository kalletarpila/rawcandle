# SIMPLIFY-04: resumable SEC acquisition

Date: 2026-11-14. Verdict: PASS for source implementation and offline qualification.
Starting HEAD: `ee3003c20a2fb389333dd6c4baf1b9b586d4d743`.
No live acquisition, production workflow execution, financial writes or push.

## Root cause and scope

The previous capture restored `budget_started_at_utc` from `pending.json` and
subtracted its entire elapsed lifetime from the 300-second network budget.
Resumes therefore inherited an exhausted deadline. Budget errors were cached as
request failures and sealed into the final manifest, preventing useful resumes.

Read-only inspection of the historical Phase 3D manifest confirmed 1,654 scopes,
941 successful responses and 1,220 budget outcomes among 2,161 request entries.
Those are historical request/error counters, not the current universe or 1,220
distinct company scopes. The old manifest was 972,805 bytes and remains untouched.

The governing SIMPLIFY-01 and SIMPLIFY-03 reports and native discovery, capture,
publication resolution and UPDATE integration were inspected. No broad repository
audit or overall workflow redesign was performed.

One task wording correction is necessary: the existing 60-day / 100 policy limits
retry **quarters**, not HTTP attempts. Native SEC HTTP retries allow three attempts
with 0.5/1-second backoff and 0.12-second pacing. Both existing policies remain.

## Execution and durable resume

Each invocation now receives a fresh monotonic 300-second budget. The original
capture timestamp remains provenance and freshness authority; the 168-hour limit
is not reset. A 2,500-start ceiling also bounds work per invocation. The boundary
stops starting new requests; finishing an in-flight request and checkpointing can
extend elapsed time. Native request timeouts remain bounded by the remaining
budget and 30 seconds.

The existing operation-owned `pending.json` holds scope outcomes, durable request
attempt counters, retry eligibility, source references and slice progress. There
is no new queue, database, worker, service or scheduler. A nonblocking operation
lease prevents simultaneous capture of the same UPDATE without holding a
production writer lock over network activity.

Request starts are checkpointed before transport. Successful bytes are synced,
content-addressed and checkpointed with their hashes and original timestamps.
Completed scopes are skipped; partial scopes reuse verified successful responses.
Native retry counts and backoff survive invocation boundaries, including pacing
from the last request completion. A new slice does not grant three new attempts.
Exactly-once reuse applies to durably recorded successful capture: a response lost
before its durable checkpoint can require another request after a crash.

The existing outcomes distinguish COMPLETED, PENDING, RETRY_WAIT,
SOURCE_UNRESOLVED and TERMINAL_FAILURE. Missing filings/mapping and local source
failures allow safe peers to continue. Shared authorization, unsafe response or
durable integrity failures stop execution and remain failed on automatic resume.
Budget exhaustion leaves pending work and does not become a source rejection.

Every slice reports total/resolved/pending/retry-wait/local-unresolved/terminal
counts, newly completed scopes, elapsed time, request count, remaining eligibility
and whether VALIDATE can begin. Final sealing checks all durable scope outcomes
and successful body references across slices, not only the last invocation.

## VALIDATE, source authority and compatibility

The same UPDATE, snapshot and plan resume through the existing FETCH entry point.
Pending SEC work produces FETCH_PAUSED without sealing `update_sources.json` or
starting VALIDATE. Sharadar's existing sealed capture is reused. Once all scopes
are accounted for, VALIDATE receives completed and actual unresolved evidence.

Capture completion is not approval of a publication date. Native SEC parsing,
filing identity, provenance, PIT/publication-date resolution, financial retry
selection, quarantine, review/HOLD and BUILD/publication gates remain unchanged.
Missing authoritative dates remain unresolved under those gates.

Legacy UPDATE records and sealed SEC bundles remain readable. Valid legacy
mutable checkpoints can resume with a fresh budget while retaining verified
evidence and original capture time. Historical budget observations are retained;
unknown old attempt counts are explicitly marked rather than reconstructed.
Legacy nonbudget failed requests remain conservatively terminal. Already sealed
legacy manifests are never reopened or rewritten: their budget errors remain
unresolved. This change does not retroactively repair those immutable old seals.

## Offline qualification and measured progress

The final targeted selection passed **56 tests in 50.76 seconds**, with no failures,
errors or skips. It covered fresh slices, immutable reuse, interruption/crash,
partial responses, durable retries/backoff, concurrency exclusion, shared/local
failures, corrupt checkpoints/bodies, freshness, legacy input, native publication
authority, retry-quarter policy, same-UPDATE VALIDATE integration and unchanged
financial acceptance/publication behavior. The socket guard recorded zero network
attempts. The full test suite was not run.

A separate five-scope acceptance fixture used one operation and five invocations:

| Slice | Resolved | Pending | Local unresolved | Requests | Virtual seconds | Pending bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 4 | 0 | 2 | 300.12 | 3,309 |
| 2 | 2 | 3 | 0 | 2 | 300.24 | 4,057 |
| 3 | 3 | 2 | 0 | 2 | 300.24 | 4,798 |
| 4 | 3 | 1 | 1 | 2 | 300.24 | 5,885 |
| 5 | 4 | 0 | 1 | 1 | 150.12 | sealed |

Retry-wait and terminal counts were zero in this exercise; dedicated tests cover
both states. The final genuine local 404 remains unresolved and is passed to
native validation. Nine fixture request starts produced eight successful response
records, zero completed-URL re-fetches and zero real requests. Verified records,
hashes and the original timestamp stayed unchanged. A repeated sealed invocation
performed no requests or writes.

Actual fixture wall time was 0.7633 seconds; simulated elapsed time was 1,350.96
seconds. The final manifest was 6,359 bytes; two unique fixture bodies occupied
285 bytes. The deliberately small/shared synthetic bodies and virtual request
durations do not predict live SEC throughput or production checkpoint size.
Runtime measurements and logs remain in ignored task-owned paths, outside Git.

## Production preservation, limitations and next action

Before/after checks passed: all twelve tracked selections and hashes for active
financial roles, controls/configuration, publication journal and review queue were
unchanged. Active generation remains
`20261114T151806Z_refresh_fundamentals_cce2b9c73301_universe_reconciliation_b80ba048`;
universe remains `2113bb9da2e5d620a8aa4de67c53f208`; watermark remains `2026-10-28`.
Fundamentals automatic refresh remains HOLD. The existing nightly configuration
was left unchanged (its inspected time is 04:30 Helsinki, despite the task's 04:45
description). No market/taxonomy database or old immutable SEC evidence changed.

No new implementation blocker remains. Live performance is unmeasured, shared
terminal failures require operator correction, and immutable legacy budget seals
need a separately authorized recovery policy rather than destructive rewriting.
The next action is review of this commit, followed by a separately authorized
bounded live continuation using an eligible mutable/new UPDATE. This task grants
no production acquisition, publication or scheduler authorization.
