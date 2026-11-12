# Fundamentals Phase 3D FIX1 — counted Sharadar responses and rejection diagnostics

The Phase 3D failure is **PROVEN**: the snapshot adapter rejected Sharadar's
`{"count": 42, "data": [...]}` envelope because its shape check allowed only
single-key objects. The native client had parsed and captured all 42 AA/ARQ rows
correctly. The correction supports exactly that counted-data envelope, with a
strict integer count equal to the returned row count, and retains all other
capture, identity, window, completeness and financial-authority gates.

Starting HEAD: `76ba0618c7597c9eafc77baac4d1d367ea016499`. Governing implementation:
[Phase 3B](fundamentals_phase3b_snapshot_integration_2026-11-12.md).

## Original incident and independently recovered evidence

Original UPDATE:
`20261112T194901Z_refresh_fundamentals_a45d1fafcc56_snapshot_update_c604bb4c`.
Original FETCH: `fetch_c604bb4c912f491da652efd5d55592db`.

The original immutable request, OLD bindings, discovery, schema response and
receipt, acquisition plan, all anchors, transport ledger, control/result files
and operator report were inspected. Discovery completed with 3,084 changed
tickers, 580 queue/boundary tickers and a union of 3,235 tickers / 6,470 slots.
The original history request used:

```json
{"ticker":"AA","dimension":"ARQ","limit":"10000","from":"2016-07-01","to":"2026-11-12","format":"json","sort":"date.asc"}
```

The original HTTP 200 response was 92,427 bytes, SHA-256
`0440b2370a987ecba25b137e09ab27d42731a5458cb000ef575a0f145aa37353`.
It was rejected before its body or any capture checkpoint was persisted.
Consequently the original artifacts alone could not identify the failed
subpredicate. Initial synthetic reproductions were explicitly hypotheses, not
historical response fixtures.

During FIX1 the operator then explicitly authorized **one Sharadar diagnostic
request**. This superseded the task's initial no-network rule for that request
only. The native client used the exact original parameters, native credential
coordination, `max_retries=0` and the existing response-size guard. Its attempt
ledger records exactly one actual HTTP 200 request. No schema request,
discovery, UPDATE creation or original-operation resume accompanied this probe.

The diagnostic response acquired at `2026-11-12T20:05:06.240628+00:00` has exactly
the original size and SHA-256. It therefore independently recovers the original
body bytes; it does **not** recreate the original transport headers or an
original acquisition envelope. The fresh response's Content-Type was
`application/json; charset=utf-8`.

The recovered body contains precisely two top-level keys: integer `count=42`
and a `data` list of 42 AA/ARQ objects. Native checks before the correction:

| Original predicate | Fresh identical-body result |
| --- | --- |
| Response body present | true |
| Exact request parameters match | true |
| Payload shape valid | **false** |
| Raw payload equals captured records | true |

The old `_payload_shape` rejected the two-key object through `len(payload)==1`.
This establishes a concrete provider/adapter compatibility defect and the
original rejecting subcondition. It does not establish that the later financial
classification or production publication would succeed.

The probe body and its separate authorization/attempt metadata remain under
`temp/fundamentals_phase3d_fix1_20261112/authorized_single_probe/`. They were not
inserted into the failed FETCH, any accepted live slot or a publication receipt,
and are excluded from Git.

## Minimal correction and unchanged boundaries

`acquisition_snapshot._payload_shape` now additionally accepts an object only
when its key set is exactly `{"count", "data"}`, `data` is an object-row list,
`type(count) is int` and `count == len(data)`. Booleans, strings, floats,
inconsistent counts, other counted containers, pagination and extra metadata
remain rejected. Existing list and single-key data/rows/results representations
retain their behavior. Capture replay uses the same predicate.

No provider request construction or dimension filtering changed. The four
original response checks remain, and `_coverage` still validates original
envelopes, body/request/timestamp bindings, exact ticker/dimension, unique source
keys, date scope, row limits and native history/profile semantics before any
checkpoint commits. Financial acceptance, OLD retention, quarantine, approvals,
first-public dates, SEC policy, normalization/capture versions and the 168-hour
age limit are unchanged. HTTP 200 alone never establishes acceptance.

An offline test replayed the recovered genuine bytes through the real native
capture client and snapshot writer, using a tiny isolated project populated
with the original AA/ARQ anchor keys. It produced one `COMPLETE_VERIFIED`
**fixture** checkpoint, then deliberately interrupted before MRQ; it did not
seal a snapshot or create financial authority. The 43 OLD anchor keys versus
42 returned rows include two missing OLD keys. The resulting coverage still
requires source-history comparison and records `absence_authorizes_deletion=false`.
The fix does not discard or automatically approve those differences.

The first offline harness mislabeled the retained SQL schema body as JSON and
was correctly blocked. Correcting only that fixture Content-Type allowed the
genuine-body replay to pass. No further real request or application workaround
was used. Compact replay evidence is retained as `genuine_body_offline_replay.json`
under the FIX1 evidence directory.

## Rejected-response diagnostics

The combined guard now identifies `RESPONSE_BODY_PRESENT`,
`REQUEST_PARAMETERS_MATCH`, `PAYLOAD_SHAPE_VALID` or `PAYLOAD_CAPTURE_EQUAL`.
Subsequent native coverage failures preserve their existing exact identifiers.
The terminal FETCH reason and a diagnostic path expose the failure rather than
only the exception class. Non-rate-limit client rejection also records its
client status; rate-limit pause behavior remains unchanged.

Each rejection writes an atomic compact JSON record under
`fetch/rejections/<uuid>.json`, bounded by the existing 64 KiB control-record
limit. It records operation/slot identity, expected and observed allowlisted
parameters, Content-Type, body type/size/SHA-256, transport-ledger observations,
payload structure/count, raw/captured row counts and bounded identity samples,
capture request/body fingerprints and the exact failed predicate. Key names and
text samples are bounded; known credentials are redacted. Arbitrary parameter
values and sensitive HTTP headers are not copied.

No automatic raw-response archive was added. Normal diagnostics contain no
raw body or financial rows. They explicitly record `accepted_snapshot_slot=false`
and `publication_authorized=false`. Rejection files are not accepted artifact
kinds and cannot serve as BODY/CAPTURE references. Snapshot manifests and
checkpoint indexes do not promote them. A later valid retry preserves previous
diagnostic files and committed valid checkpoints.

## Targeted verification

**122 distinct targeted tests PASS, zero failures/errors/skips.**

| Selection | Cases |
| --- | ---: |
| New rejection/count-envelope tests | 32 |
| Existing Phase 1 acquisition snapshot tests | 56 |
| Native Sharadar provider tests | 28 |
| Directly relevant Phase 3B integration cases | 6 |

The primary run passed 121 cases in 55.20 seconds. One additional counted-empty
case passed in 6.89 seconds; it confirms that a valid empty counted envelope
still fails the existing nonempty history requirement. The full repository
suite and the earlier 354-case Phase 3B selection were not run.

Coverage includes supported JSON/container/UTF-8/CSV representations; strict
counts and pagination rejection; wrong ticker/dimension and unfiltered rows;
request/capture parameter and body binding mismatches; malformed/empty payloads;
exact rejection identifiers; bounded credential-free diagnostics; zero committed
rejected slots; inability to seal rejected evidence; valid-checkpoint preservation
on resume; and diagnostic non-authority. An integrated synthetic UPDATE test
proves same-ID resume before validation code binding and rejection of later
code drift after a validation receipt exists.

The six existing Phase 3B cases cover capture pause/checkpoint reuse, local
actions refusing unsealed FETCH, acquisition-only rejection, scheduler HOLD,
exact candidate controls and the integrated copy-only build/native publication
fixture. No such fixture touched production. A task-owned outgoing-socket guard
recorded zero test network attempts; the genuine-body offline replay also
recorded zero outgoing attempts.

Acceptance XML, exact counts and network ledgers are retained under
`temp/fundamentals_phase3d_fix1_20261112/`. The sole real network call in this task
was the separately authorized diagnostic Sharadar request; SEC calls were zero.

## Original UPDATE resume eligibility

**Same-ID resume is contractually permissible, conditional on fresh native
checks and separate authorization for live continuation. It was not executed.**

The failed parent has no financial validation attempt, candidate or publication
grant. Its immutable UPDATE request and FETCH binding contain effective relevant
configuration, OLD, policy and capture/normalization versions, but no stored
code fingerprint. `refresh_update._code_binding` first becomes financial
authority in VALIDATE's receipt, and `_assert_inputs` rejects later code drift.
Thus committing this correction does not require rewriting or rebinding an
existing financial receipt. No stored fingerprint or historical artifact was
changed. The synthetic integration test verifies both sides of this boundary.

`SnapshotWorkflow.advance` permits a failed, uncommitted UPDATE to return to its
missing FETCH phase. Native `resume_fetch` verifies the existing request,
OLD, plan, anchors, schema and checkpoints. It does not require replacing the
operation merely because its prior terminal result was FETCH_BLOCKED. The
original has zero committed history slots and a reusable verified schema;
resumption must fetch missing slots through the native boundary, never import
the diagnostic body as an accepted cache hit.

Required before any later continuation:

1. Inspect current native journal/recovery, locks, sidecars, storage and all OLD
   role hashes/manifest; the original OLD must still match exactly.
2. Preserve route `SNAPSHOT_V1`, FULL_WORKFLOW and the original relevant config;
   preserve scheduler HOLD and both immutable false intents.
3. Reverify original request, discovery, schema, plan and anchors. Keep original
   capture timestamps and policy versions. Do not change stored fingerprints.
4. Stay within the original UPDATE's 168-hour bound. Its current upper deadline
   is `2026-11-19T19:49:02.002339+00:00`; source/checkpoint freshness gates also apply.
5. Obtain authorization for same-ID live continuation, then use the native
   operator lock and `advance(original_update_id, stop_after="fetch")` with no
   publication confirmation. Later VALIDATE establishes current code/source/
   queue/dependency authority; further drift invalidates that authority.

Incompatible OLD/configuration or expired original evidence must not be repaired
by editing the old operation. A separately authorized new UPDATE would then be
required, preserving the failed UPDATE/FETCH and diagnostic evidence. No claim
is made that the remaining 6,470 slots, SEC acquisition, financial review gates,
production-scale BUILD or publication have passed.

## Production preservation and changed files

Before/after bounded checks cover nine protected files, including all three
financial roles, market, taxonomy, review queue, active manifest, journal and
scheduler configuration. Sizes, nanosecond mtimes, inodes and sidecars match;
manifest, journal and configuration SHA-256 values match. The normal targeted
test guard independently verified protected database byte identities.
A fresh read-only `pin_old_authority` also rehashed all three active financial
roles and matched the original UPDATE's exact OLD authority. Native read-only
request/plan/anchor/checkpoint and schema/transport checks passed; the existing
configuration still matches the immutable UPDATE request. These checks and the
original age deadline are recorded in `resume_assessment.json` in the FIX1
evidence directory. None of these checks executes resume or recovery.

All **6,492 original UPDATE/FETCH files** retain their exact content hashes,
sizes, mtimes, inodes and membership. No historical evidence was regenerated.
The active generation remains
`current_rebuild_2a684ef130c6a540de4adc560ab171ad`, watermark `2026-10-28`, journal
COMPLETED/PASSED/NOT_REQUIRED, route SNAPSHOT_V1 and scheduler HOLD effective.
No live UPDATE, recovery, validation, build, review write, activation, financial
publication or ownership publication occurred during FIX1.

Only these source/test/documentation files belong to this change:

- `rawcandle/fundamentals/admin/acquisition_snapshot.py`
- `tests/test_fundamentals_acquisition_rejections.py`
- This report.

Unrelated worktree changes are preserved. Runtime evidence, credentials,
diagnostic bodies, databases and test outputs are excluded from the commit.
No push is performed.
