# Fundamentals single-FETCH acquisition foundation V1

Phase 1 implements an **acquisition-only** API with durable singleton checkpoints, immutable captured source evidence, explicit seven-day freshness and credential-scoped native HTTP coordination. It does not connect that API to Refresh, Full Workflow, the scheduler or financial publication. FETCH success always reports `publication_authorized=false`; it creates no executable Preview/Test/Production authorization.

Architecture baseline: `1926f78cb368d3374c302265dd27e61b131eafc5`. The operator overrides that document: **one ticker at a time, ARQ then MRQ as separate native requests; 168 hours instead of 24 hours; no batch, all-dimension, ZIP or batch-qualification implementation.** The accepted architecture document is preserved as historical evidence; this task's explicit overrides govern this implementation.

## Changed modules

| File | Change |
| --- | --- |
| `rawcandle/fundamentals/admin/acquisition_snapshot.py` | Explicit `start_fetch` / `resume_fetch`; native OLD pinning, fixed singleton request plan, durable original bodies/captures, coverage and checkpoint verification, sealing, read-only Phase 2 consumption |
| `rawcandle/fundamentals/providers/sharadar_limiter.py` | Private credential-scoped flock/state files, single in-flight request through body read, durable start pacing/cooldown, bounded waiting and both Retry-After formats |
| `rawcandle/fundamentals/providers/sharadar.py` | Preserve original response bytes/headers/request/time/attempt ID; scoped attempt observer and bounded acquisition reads; default native transport always coordinates; fail-fast 429; original native V1 capture boundary retained |
| `tests/test_fundamentals_acquisition_snapshot.py` | Singleton acquisition, native capture, durable interruption/resume, integrity, source coverage, exact age, read-only boundaries and large-child acceptance |
| `tests/test_fundamentals_sharadar_shared_limiter.py` | Retry-After, real separate-process serialization/cooldown, native retry ledger, non-coordinator default client and untrusted coordination state |
| `tests/test_fundamentals_v4_sharadar_provider.py` | Replace the old automatic 429 retry expectation with the deliberately selected immediate RATE_LIMITED result |
| This report | Contract, acceptance and operational limitations |

Source-capture policy/envelope, normalization, generations, journal, recovery, queue, provider schemas, watermarks and financial orchestration are not changed.

## Acquisition entry and exact request scope

`start_fetch(tickers, project_root=..., source_day=..., root=..., operation_id=..., client=..., now=...)` starts an explicit acquisition-only operation. `operation_id` is minted once as `fetch_<uuidhex>` unless an unused ID of that form is supplied. An exclusive directory creation prevents overwriting an existing operation. No CLI/scheduler hook or automatic publication hook is installed.

The caller supplies an ordered unique ticker scope; this phase does not perform financial discovery/classification or infer approval from that list. Planning reads native immutable-generation authority and provider source keys in SQLite read-only mode. It records the OLD generation ID, manifest SHA and all three role sizes/SHAs, verifying role hashes against the native manifest. Resume requires the same current OLD binding, original plan, schema, source/capture policy and request bytes. It does not run recovery or create a financial lock/journal transaction.

Schema is acquired once through `SharadarClient.schema('fundamentals')`, stored and pinned before histories. Every ticker is acquired sequentially, **ARQ then MRQ**; no next dimension starts until the current terminal receipt, index and control update are durable. An operation flock prevents concurrent resumes. Native per-credential coordination prevents concurrent HTTP calls from other processes using the default native transport as well.

History parameters are exactly:

```text
endpoint=/data/fundamentals
 ticker=<one exact planned ticker>
 dimension=ARQ or MRQ
 from=<explicit lower bound>
 to=<pinned source day>
 limit=10000
 format=json
 sort=date.asc
```

There is no `fields` projection, `lastupdated` discovery filter, offset, pagination, batch ticker or dimension combination in a history request.

### Supported horizon and its limits

The public native contract documents **`from` and `to`**, with a one-year default lower bound if none is provided; the Fundamentals parameter table describes filing-date bounds. This implementation uses those actual parameter names, rather than relying on the existing client's unrelated `start_date` / `end_date` argument names or an omitted default. It also makes the format explicit. [Native Fundamentals documentation](https://sharadar.com/docs/fundamentals), [native query documentation](https://sharadar.com/docs/getting-started).

The lower bound is the first day of the quarter containing the ten-year lookback date, minus one additional quarter. For source day **2026-11-11**, requests explicitly cover **2016-07-01 through 2026-11-11**. This is a bounded requested window, **not proof that every company has ten years of observations**, not lifetime history, and not a fixed minimum row count. Young issuers may legitimately have short histories.

Coverage requires a complete successful native body, exact scope identity, no hidden row filtering, fewer than 10,000 rows, unique source keys, valid source-key dates inside the explicit window, and all OLD source keys already present inside that window. A default-one-year or silently shortened result that omits those OLD anchors fails closed as `OLD_WINDOW_COVERAGE_MISSING`. Response wrapper pagination/metadata beyond the sole row collection is not silently ignored; exact-limit, incomplete transport and uncertain coverage cannot become a checkpoint.

Receipts bind the precise requested horizon, observed minimum/maximum dates, request fingerprint, row count/source-key digest, OLD anchor count, native query contract and `server_horizon_live_verified=false`. Thus an explicit request window and observed span remain distinct facts. An account/server silently omitting rows never previously observed locally cannot be disproved by offline tests or row-count heuristics. No live behavior, entitlement, ten-year server conformance or universal completeness oracle is claimed; a separately authorized acquisition-only conformance run may establish those facts later. No financial production cutover is authorized here.

OLD observations outside the window are neither queried as deletion candidates nor rewritten. Every receipt says `old_outside_window_action=PRESERVE_OLD`; Phase 2 must retain that authority. Missing OLD keys inside the requested window block coverage rather than imply deletion. No grandfathered row is assigned a new V1 envelope.

## Durable artifact contract

Artifacts live in the existing native admin run root, or an explicit disposable root in tests:

```text
<admin_run_root>/<operation_id>/
  request.json
  result.json                         # bounded current status, counts and references
  operation_report.md                 # acquisition-only status
  acquisition_snapshot_reference.json # only after sealing; bounded typed reference
  artifact_manifest.json              # existing native top-level hash manifest
  fetch/
    control.json                      # request/plan/schema refs, declared slot prefix
    operation.lock
    acquisition_plan.jsonl            # slot ordinal, exact ticker/dimension, OLD-key ref
    anchors/<slot>.jsonl              # OLD keys inside requested window only
    attempts.jsonl                    # actual transport lifecycle; no secrets/bodies
    schema_receipt.json               # schema body/hash, fingerprint, original attempt
    responses/<uuid>.body             # exact received native bytes
    captures/<uuid>.jsonl             # original raw row + original native V1 envelope
    checkpoints/<slot>.json           # atomic terminal receipt
    checkpoint_index.jsonl            # compact slot -> typed receipt reference
    snapshot_manifest.json            # bounded immutable source root
    seal.json                         # operation + source-root SHA reference
```

All JSONL lines are bounded to 64 KiB. Control/root JSON is bounded to 64 KiB; parent progress/results contain no histories. Large bodies and captures are referenced by operation, artifact type, relative path, exact size and native streaming SHA-256. The native top-level artifact manifest binds the bounded snapshot-reference file; that reference binds the source root and its children. Native run-ID/path checks and `sha256_file` are reused, with narrow nested-artifact type/path checks for source children.

Traversal, unexpected artifact type, another operation's reference, symlinked root/ancestor/child, missing declared file and wrong size/hash fail verification. This is the native local hash/reference trust model, not a remote signature system; Phase 2 should retain the returned expected root reference in its own receipt and require it when opening/preflighting.

A checkpoint contains its format/operation/slot identity, terminal state, exact parameters, acquisition timestamp, actual native attempt ID, content type, body/capture references and coverage evidence. It binds to a successful original transport FINISHED event with identical endpoint, parameters, response size/SHA and acquisition time. Replay reconstructs the existing V1 wire representation using the original raw object and original envelope; it never calls the acquisition attestation constructor again. ABSENT, EXPLICIT_NULL and VALUE remain distinct.

Binary bodies use the native temporary-file/fsync/atomic-replace pattern extended to unchanged bytes; directories are fsynced as well. Captures stream one row/envelope at a time into an atomic child file. The terminal receipt is the checkpoint commit point. Its compact index entry is then fsynced, and control remembers the declared completed prefix before another request starts.

### Completion and diagnostic-only source defects

`COMPLETE_VERIFIED` requires both transport/coverage proof and native financial source/profile/history validation. BASE and FREEZE profiles are checked with the existing source-capture implementation, retaining applicable explicit-null semantics. Full incoming financial acceptance and any later P/B-specific acceptance remain Phase 2/native consumers' responsibility.

A structurally identified, coverage-proven native response with projected/missing/unusable financial fields may be recorded only as `DOCUMENTED_LOCAL_SOURCE_DEFECT`. It retains the original diagnostic body/envelopes, explicit reasons and **no eligible incoming financial rows**. `read_slot` exposes its eligibility flag. That state does not grant a local hold approval: Phase 2 must prove isolation and OLD preservation before any safe-peer publication.

Empty histories, wrong ticker/dimension, invalid/duplicate source keys, transport truncation, missing original capture, tampered envelope, missing OLD coverage, exact limit and shared schema/identity uncertainty do not become COMPLETE_VERIFIED or benign cache misses. They block FETCH. Shared HTTP failures pause/block promptly while useful previous checkpoints remain.

## Resume and corruption

`resume_fetch` reopens the original operation, pins/verifies OLD and every committed checkpoint's bytes, original captures, request and transport/coverage bindings before any new HTTP request. It fetches only missing/uncommitted slots in the original order. A completed ARQ survives an interrupted/429 MRQ, and completed earlier tickers survive later failure.

Atomic receipts surviving a crash before their index/control update are verified and adopted locally. An incomplete trailing unsealed index append is not accepted as authority; the verified receipt set rebuilds that compact view. A missing receipt declared by the committed index/control prefix is an integrity failure. Missing/tampered COMPLETE children are never overwritten by a replacement download. An incomplete attempt-ledger line fails closed; it is not guessed into a valid transport event.

Original acquisition times and request bounds are retained across resume. Another operation cannot silently consume these checkpoints; it must acquire its own scope. Once sealed, normal resume performs only local verification/age checking and returns the same source root, without HTTP or source mutation. Audit opening remains read-only and available after expiry.

## Seven-day policy and Phase 2 reader

`MAX_AGE_SECONDS=604800` implements the operator's **168-hour** policy. Age is measured from the oldest original terminal history acquisition checkpoint; diagnostic timestamps are conservatively included. The newest checkpoint must not be in the future. Exactly 168 hours is eligible; any greater age is expired. There is no 24-hour or same-UTC-day restriction.

Age is checked before resuming/fetching additional slots, after each new acquisition and at seal. An expired unsealed operation cannot refresh its timestamp. An expired sealed snapshot remains readable for audit but is ineligible at preflight.

Stable read-only consumption interfaces are:

- `open_snapshot(operation_id, root=..., expected_reference=...)`: verify the sealed graph without network or writes; intentionally permits old audit evidence.
- `snapshot.iter_slots()`: stream the compact plan.
- `snapshot.read_slot(number)`: verify/read one native captured response and receipt, with explicit incoming eligibility.
- `snapshot.validate_preflight(old_authority=..., now=..., expected_reference=...)`: recheck source graph, exact OLD and age, returning source age and acquisition eligibility. It **always returns publication_authorized=false**; Phase 2 still owns financial validation, intent, safe/held partition, native publication and recovery.
- `pin_old_authority(project_root)`: read-only native immutable-generation binding for the above check.

Phase 2 must use its own operation's stored expected root reference and current native OLD binding. No acquisition success can be converted into a legacy Preview/Test receipt or a Production authorization.

## Shared native HTTP pacing and 429

The default real native `SharadarClient` transport always uses a credential-scoped coordinator, including schema, projected discovery, history and retries. Passing the legacy process pacing limiter does not remove that coordination. Injected fake openers remain fixture boundaries and may explicitly use a disposable credential coordinator; they do not create production limiter files during offline acceptance.

Coordination is a small private `temp/sharadar_transport/` directory with a SHA-256 credential identifier in filenames, one flock and a bounded JSON pacing/cooldown file. No key, authorization header, signed URL, request history or financial state is stored there. The directory must belong to the OS user and have no group/other permissions; symlinked or corrupt state fails closed. These are local-machine processes, not distributed-host coordination.

The flock covers opening, full response read/close and durable cooldown recording. Starts are spaced by at least 0.5 seconds; conservatively another 0.5-second eligibility bound is recorded after completion, so slow local receipt fsyncs cannot shorten actual transport spacing. This may be slower than the old start-only clock. It is not a claimed Sharadar quota.

On HTTP 429 the client records credential-wide cooldown before releasing the lock and immediately returns RATE_LIMITED, regardless of its configured normal retry count. Acquisition returns `FETCH_PAUSED`, verified counts, actual-attempt counters and resume eligibility. It does not run the remaining ticker loop. Other default native clients see the same cooldown. Long waits exceeding the client's wait budget return before another transport attempt; server guidance is not clipped to 60 seconds.

Retry-After accepts finite nonnegative numeric values (including zero), HTTP dates, and case-insensitive headers. Past dates mean zero; absent/malformed/negative/nonfinite guidance uses a conservative five-second cooldown. Zero still respects pacing. Existing bounded non-429 transient retries remain native and each actual attempt is recorded separately. Current callers still receive the existing RATE_LIMITED status; their financial routing is not replaced in this phase.

Each operation ledger records STARTED and FINISHED/FAILED/INTERRUPTED attempt events using unique attempt IDs and safe request parameters. It records response size/SHA, never bodies or headers containing credentials. The result separates known actual attempts from dispatch intents and unmatched/indeterminate attempts after SIGKILL; it does not claim an unmatched intent is a definitely executed call. Invalid UTF-8, body-length mismatch or a credential echoed into a successful body cannot produce an accepted capture; safe header values are redacted.

## Focused offline/disposable acceptance

Acceptance uses fake HTTP through the real native `SharadarClient` and V1 capture boundary, disposable native OLD generation layouts/SQLite files and disposable run roots. No provider endpoint, sample API endpoint or authenticated schema endpoint was called. Only the two public documentation pages linked above were read.

The final focused release check covers **227 test cases** across:

```text
tests/test_fundamentals_acquisition_snapshot.py
tests/test_fundamentals_sharadar_shared_limiter.py
tests/test_fundamentals_v4_sharadar_provider.py
tests/test_provider_capture_contract.py
tests/test_provider_capture_storage.py
tests/test_provider_capture_acceptance.py
tests/test_fundamentals_v4_sharadar_acceptance.py
tests/test_fundamentals_generations.py
tests/test_fundamentals_workflow_evidence.py
```

The new cases cover exact singleton/ARQ/MRQ order; no repeated verified acquisition; interruption after ARQ and after earlier tickers; receipt/index/control/root sealing crash boundaries; rehashed semantic tamper; missing/corrupt/path/type/symlink/operation/OLD faults; schema failures; projected/empty/wrong/duplicate/truncated/limit/pagination responses; OLD-window omission; field states; under/equal/over 168 hours and six/seven/eight-day resumes; seal-time expiry; credential echo/invalid encoding/bounded reads; fail-fast 429 with retained ARQ; numeric/date/long/zero/malformed/absent guidance; separate-process in-flight/pacing/cooldown; default non-coordinator clients; native retries; read-only OLD hashes; native root artifact bindings and truthful interrupted-attempt counters.

A sparse **2 GiB child** is hashed by the real chunked helper with less than 8 MiB peak traced Python allocation for that hash. Control/reference artifacts remain bounded. Attempting singleton financial replay of that oversized child fails before an eager body read. This verifies large-child/reference behavior; it is not a claim that a 2 GiB singleton response is supported or that total process RSS stays below 8 MiB.

The existing regression cases exercise source-capture/profile/storage consumers, native safe-peer publication on disposable generations, legacy Sharadar callers, verified compact workflow evidence and native immutable-generation safety. No full repository suite or live financial Full Workflow is run.

**Final result: 227 PASS, zero failures/errors/skips**, in 63.87 seconds. The read-only runtime comparison at `2026-11-11T21:30:25.381123+00:00` verifies the same active generation `current_rebuild_2a684ef130c6a540de4adc560ab171ad` and identical sizes/SHA-256 hashes for all nine protected files: the three active financial roles, manifest, journal, market, taxonomy, review queue and scheduler configuration. Generated XML and hash evidence remain local under `temp/fundamentals_single_fetch_phase1_20261111/` and are excluded from the commit.

## Performance, space and operational limits

For an explicitly selected 1,810-ticker scope, normal acquisition is **3,620 history requests plus one schema request**, before actual failed attempts/retries. Discovery is a caller-selected scope prerequisite outside this Phase 1 API; existing native discovery requests still share transport coordination. No batching, ZIP, page splitting or parallelism exists. Actual duration depends on response/network/storage time plus conservative pacing; no server quota or measured production throughput is asserted.

Storage is original response bytes plus original raw-row/envelope sidecars, compact OLD key anchors, receipt/index/ledger metadata and native root references. No new provider DB, source-version graph, cache service, active generation or OLD financial copy is created. Captures intentionally retain raw rows as well as original body bytes so row evidence can be independently verified. No automatic evidence/backup cleanup is installed.

Scope is limited to 10,000 distinct tickers; singleton replies must contain fewer than 10,000 rows and at most 64 MiB of body bytes. Control/root JSON and JSONL lines are limited to 64 KiB. Oversized bodies/rows stop safely rather than allocate unbounded acquisition-set memory or truncate finance. Body bytes and native row objects are resident for one singleton response; captures stream on write, and the response is released before the next request. Full acquisition bodies are never aggregated into parent results or a multi-ticker in-memory history map.

Verification hashes large files in chunks and decodes one bounded singleton at a time. Compact plan/receipt/event metadata grows with scope. Resume/open/preflight intentionally recheck committed evidence; this costs local I/O proportional to captured bytes, not new remote calls. Index appends are constant-size per checkpoint, followed by an atomic rebuild on verified resume/seal; there is no per-ticker rehash of all earlier response bodies during ordinary acquisition. OLD generation hash pinning also costs local read I/O.

This is intended for a local Linux personal research installation with flock and trustworthy fsync/atomic-rename semantics, not a multi-host acquisition cluster. Actual upstream date-bound behavior/account entitlement and representative full-run RSS/wire sizes remain unmeasured without the separately authorized acquisition-only conformance run. Those unknowns do not grant a financial publication exception.

## Financial production and runtime boundary

The current Preview/Test/Production, Full Workflow and scheduler still use their existing financial path; no caller is rerouted to this acquisition API. Add/Remove/repair/PB callers retain their existing methods, result statuses and source-capture contract. The shared transport's process-independent pacing and immediate 429 result are intentional common changes, covered by targeted regressions.

No current provider, canonical, analysis, queue, journal, watermark, active manifest, scheduler configuration or recovery state is modified by the implementation/acceptance work. No archived patch is installed. No database is reset, historical row deleted or backup cleaned. Generated evidence and fixture bodies remain outside the source/test/documentation commit. No push is performed.
