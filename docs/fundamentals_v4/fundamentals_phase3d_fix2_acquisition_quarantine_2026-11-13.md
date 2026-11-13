# Fundamentals Phase 3D FIX2 — ticker-local acquisition quarantine

Implements whole-ticker source exclusion for isolated, evidenced Sharadar history
failures in `UPDATE_FETCH`, with continued safe-peer acquisition and the existing
VALIDATE/BUILD/publication kernels. This task performs no live acquisition,
UPDATE resume, SEC request, review action or production publication.

Starting HEAD: `e60eda8e2d2963a1d3103f44e1ee929470008d15` (accepted FIX1).
Governing contracts: [FIX1](fundamentals_phase3d_fix1_sharadar_capture_compatibility_2026-11-12.md),
[Phase 2](fundamentals_phase2_local_validation_publication_2026-11-12.md),
[Phase 3B](fundamentals_phase3b_snapshot_integration_2026-11-12.md), and the
operator's explicit FIX2 locality decision. Historical reports retain their
original rollout observations; the current route is `SNAPSHOT_V1`, on HOLD.

## Exact incident and existing boundary

Original UPDATE:
`20261112T194901Z_refresh_fundamentals_a45d1fafcc56_snapshot_update_c604bb4c`.
Original FETCH: `fetch_c604bb4c912f491da652efd5d55592db`.
Its native `phase3d_resume1_operator_report.md` and
`fetch/rejections/5312916a276e476ca97fccea056f03a0.json` were read at these
known operation paths. No repository-wide runtime search was used.

RESUME1 stopped at INM ARQ slot 3018 after 3,018 verified slots, split 1,509 ARQ
and 1,509 MRQ, out of 6,470 planned slots for 3,235 tickers. The INM response was
HTTP 200, `count=0`, zero rows, 21 bytes, SHA-256
`2d89d22ece49414976a5b77bbbe54af051d791fbe060dee51b82f9b8dca2868a`.
All four response binding/shape checks passed. The native failure was
`EMPTY_OR_LIMIT_COVERAGE_UNPROVEN`. Its OLD anchors contain 28 ARQ and 29 MRQ
keys. Existing INM baseline-integrity hold is not source completeness, a
financial approval, or permission to remove those keys.

Previously, an empty/identity/window/source-key response failure escaped the
FETCH loop and blocked all peers. Some nonempty source-profile failures became
diagnostic checkpoints, which remain financially ineligible. FIX2 adds a third
explicit acquisition outcome for positively isolated UPDATE source failures;
`ACQUISITION_ONLY` behavior remains unchanged. Valid nonempty histories missing
OLD keys continue through existing source-history comparison and financial
review. They are never interpreted as authorized removals.

## Positive source-locality contract

`acquisition_quarantine.py` is a bounded source-disposition helper for the
existing acquisition operation, not a review or publication subsystem.
Classification requires an exact native request, actual HTTP 200 completion,
original timestamp, response bytes/hash, transport ledger binding, and original
native capture envelopes where rows exist. Retained public rows must equal the
native client's dimension-filtered raw payload. Current OLD generation/manifest
and a unique native company/security/provider identity must bind the requested
ticker, without a planned sibling security sharing its company scope.

Only recognized source failures can be localized:

| Source evidence | Acquisition result |
| --- | --- |
| Exact successful empty or limit-sized bounded HTTP response | Local quarantine if isolation passes, never complete history |
| Duplicate/invalid source key, out-of-window history | Local quarantine when request/identity/capture isolation passes |
| Missing/unusable required source fields | Local quarantine with original raw/envelope evidence |
| Requested ticker rows mixed with a malformed non-object member in a known list/count-data frame | Local quarantine; unknown wrappers/count inconsistency still STOP |
| One unplanned foreign ticker or native ARQ/MRQ dimension-filter contradiction | Local only with exact binding and no planned-peer identity collision |
| Mixed identities or another planned ticker's history returned | Global STOP |
| Missing/corrupt capture or transport/body/request disagreement | Global STOP |
| Unknown schema, pagination, unbounded transport or oversized response | Global STOP |
| Foreign provider security ID in otherwise valid source | Existing global financial identity gate before candidate construction; an untrustworthy source with that contradiction cannot be localized at FETCH |
| Authentication/authorization failure or failed shared transport | Native global blocked outcome |
| Shared credential limit | Native PAUSE, keeping committed evidence |

Shared nonempty contract contradictions are compared by deterministic evidence
signatures, including required-field omissions, reduced projections, observed filter/key-set shapes
and request-window filtering failure. Matching signatures across distinct
requested tickers STOP with `SHARED_ACQUISITION_SOURCE_CONTRACT_FAILURE`.
There is no failure-count or percentage cutoff. Identical empty bodies alone
do not establish a shared schema defect. As a conservative positive locality
control, sealing also requires a nonquarantined ticker with both ARQ and MRQ
verified. An all-quarantined acquisition cannot silently seal as successful;
it stops with `ACQUISITION_LOCALITY_WITHOUT_VALID_PEER_CONTROL`.

Unknown/non-isolatable failures remain global. This does not diagnose every
possible upstream outage from an HTTP 200 response: no arbitrary failure-rate
heuristic or retry policy is introduced. Native storage/recovery/schema/OLD
and financial approval gates remain mandatory.

## Durable receipts, slot accounting and immutable sealing

Contract: `FUNDAMENTALS_TICKER_ACQUISITION_QUARANTINE_V1`.
Disposition: `LOCAL_ACQUISITION_QUARANTINE`.
Each actual rejected slot gets an atomic receipt at
`fetch/quarantines/NNNNNN.json`, a compact `fetch/quarantine_index.jsonl` entry,
separately typed original `QUARANTINE_BODY` and `QUARANTINE_CAPTURES`, and the
hash-bound rejection diagnostic. Receipts retain operation/slot/ticker/dimension,
both affected slot IDs, native identity, exact request, OLD, transport attempt,
timestamp, parameters, response hash/size and original capture references.

`history_complete`, `incoming_financial_input_eligible`,
`absence_authorizes_deletion`, and `publication_authorized` are explicitly false.
No source rows, timestamps or attestations are regenerated. Receipt replay
verifies the retained original graph and recomputes locality. Atomic receipts
surviving interruption before their index append are safely adopted; missing
committed receipts or children fail closed. Valid partial capture remains in
the ordinary verified checkpoint graph and is distinguishable from rejection.
Each rejection also binds its genuine captured-row count. The ticker disposition
explicitly exposes `valid_partial_capture_obtained` and hash-bound
`verified_partial_captures`; these references do not grant financial eligibility.

Every slot must be accounted for individually by a real verified checkpoint or
a justified quarantine receipt. Both dimensions are still requested. A ticker
quarantine never fabricates its unattempted counterpart. Manifest accounting
distinguishes planned/verified/diagnostic slots, whole-ticker quarantines,
quarantined financial slots, actual rejected slots, nonquarantined verified
slots, accounted slots and genuinely pending slots. The optional manifest
quarantine contract/index preserves compatibility with existing snapshots.
Sealing and every subsequent opening verify this graph and the original age.

Example from the isolated fixture: 3 tickers / 6 slots, 5 verified source slots,
1 actual rejected slot, 1 quarantined ticker / 2 excluded financial slots,
4 nonquarantined verified slots, and 0 pending slots. The valid counterpart
checkpoint remains evidence, but neither dimension of that ticker is readable
as financial input. Quarantine bodies cannot be promoted to ordinary BODY
references. No HTTP fallback is available after sealing.

## Financial exclusion and OLD preservation

VALIDATE explicitly obtains the quarantined ticker set, verifies its native
identity, and creates an existing local-held disposition before loading either
incoming history. It binds that disposition through the native locality and
full-OLD authority. Source quarantine does not upsert, resolve, reopen or
approve financial queue rows. A pre-existing retained-history approval remains
bound and unconsumed even through disposable publication of safe peers.

BUILD receives only safe financial source maps/plans. Existing provider merge,
canonical carry-forward and analysis construction retain OLD for excluded
tickers; rejected ARQ/MRQ never reaches V2/package/RP/RV calculations. Native
held-preservation verification applies before and after publication. Degraded
OLD retains its baseline-integrity hold and lack of new accepted evidence.
The degraded fixture compares all retained canonical content, provenance and
publication-date values; generated `provenance_id` surrogate numbers may move
in the rebuilt canonical database and are not financial authority.

SEC incoming planning skips quarantined histories. Existing OLD retry scope
and missing-input semantics remain unchanged. Progress, UPDATE summary rows,
workflow reports, validation reports and existing run-history/report access
distinguish source quarantine from a global failure. No Admin UI redesign or
second publication engine is introduced. Code binding explicitly includes the
new helper even before Git tracks it.

The integrated disposable test executes native FETCH → seal → VALIDATE → one
inactive BUILD → explicitly confirmed fixture publication/VERIFY. Safe AAA and
YYAI proceed, quarantined BBB remains exact OLD, and the native journal reaches
COMPLETED/PASSED. A separately degraded OLD fixture retains its existing
restrictions. Deleting an accounted counterpart checkpoint blocks publication
before activation. Historical sealed evidence still opens after the fixture's
active generation changes, without depending on current live OLD resolution;
financial stage preflight separately binds current OLD and identity.

## Original UPDATE same-ID resume assessment

Same-ID continuation is contractually possible, conditional on a fresh native
operational preflight and separate operational authorization. All 3,018
checkpoints remain reusable, with unchanged request/discovery/anchors/schema,
transport, captures, prior diagnostics and reports. Capture/normalization/source
policy constants are unchanged. No validation/candidate/code receipt exists yet;
the corrected committed implementation may bind the first future VALIDATE.
An existing financial receipt must never be rebound to changed code.

The original INM diagnostic has `raw_body_retained=false`. It cannot be upgraded
to a new authoritative quarantine receipt or successful slot. A future native
request for INM ARQ must retain real bytes and, if still empty and locally
isolatable, create a new rejected-slot receipt. INM MRQ must also be attempted
and accounted for. Verified peers are not reacquired. No diagnostic cache
import, original timestamp reset, replacement UPDATE or historical rewrite is
needed or performed.

The original deadline remains **2026-11-19T19:49:02.002339+00:00**. Recheck current
OLD roles, configuration, source/schema/checkpoints, installed code, age, locks,
sidecars, permissions and actual free storage before any later continuation.
Both immutable intents remain false. A later FETCH/VALIDATE/inactive BUILD
authorization would still grant no review approval, publication, activation,
watermark move, scheduler enablement, ownership publication or optimization.

## Validation and protected-state evidence

Evidence is retained only under
`temp/fundamentals_phase3d_fix2_20261113/`; raw runtime evidence is excluded from
Git. Targeted modules cover native acquisition, FIX1 rejections, FIX2 quarantine,
Phase 2 financial kernels and Phase 3B integration. The full suite is not run.
Fake native transport and isolated SQLite fixtures are used throughout; an
outgoing-socket guard records attempted connections and fails the run on any
attempt, including exceptions caught by application code.

**201 distinct targeted cases have a passing latest result**, without skips or
remaining failures. This is coverage across bounded runs, not a claim that one
201-case command was executed:

| Module | Distinct passing cases |
| --- | ---: |
| Native acquisition snapshot | 56 |
| FIX1 rejection/capture compatibility | 32 |
| FIX2 acquisition quarantine | 44 |
| Phase 2 financial workflow | 35 |
| Phase 3B integration | 34 |

Evidence sequence: `regression.xml` ran 196 cases (194 passed, 2 failed);
`final.xml` reran the affected native/capture paths and selected financial
integration (134 cases, 133 passed, one incorrect phase assertion);
`accepted.xml` passes all 44 FIX2 cases in 138.85 seconds; `partial.xml` passes
11 focused receipt/partial-evidence/integrated-publication checks in 50.04
seconds after making partial-capture status explicit. Latest-case aggregation
is recorded in `targeted_test_summary.json`. The two existing regression
failures were a positional seal-hook compatibility issue and a default-route
test reading the operator's selected production route; both pass in `final.xml`.
The remaining phase assertion was corrected to exercise the existing global
provider-ID gate at VALIDATE, with a separate FETCH case proving that the same
identity contradiction cannot be hidden in a local source quarantine.

Development XML is retained, including adversarial failures that led to stricter
original-envelope verification and shared reduced-projection detection. No
production configuration was changed to make a test pass. The final network
ledger records **0 outgoing attempts**. No full repository suite was invoked.

Read-only production baseline: `2026-11-13T07:20:07.861481+00:00`.
Final comparison: `2026-11-13T08:05:02.408647+00:00`.
All **15,549 original UPDATE/FETCH files** retain exact SHA-256, size, inode and
mtime, with identical membership. A separate native replay verifies all 3,018
COMPLETE_VERIFIED receipts, source children, schema, request/configuration,
original age and capture/normalization/policy bindings. No original checkpoint,
transport entry, progress view, diagnostic or operator report was rewritten.

The three active financial role hashes still match the exact original OLD
authority. Their byte sizes remain provider **968,331,264**, canonical
**749,371,392**, analysis **912,351,232**. Active generation remains
`current_rebuild_2a684ef130c6a540de4adc560ab171ad`, watermark **2026-10-28**.
The active manifest, publication journal and scheduler configuration retain
their hashes and metadata. Financial role files and the live review queue retain
size/inode/mtime/sidecar observations. Journal remains COMPLETED / PASSED /
NOT_REQUIRED; scheduler HOLD and both false UPDATE intents remain effective.
These observations are in `production_before.json`, `production_after.json`,
`protected_state_assessment.json` and `final_protected_state.json`.

The interval is **not** described as nine globally unchanged files: the existing
independent normal stock/datacenter scheduler was already running. Its native
summary `logs/stock_update_scheduler_summary_20261113T044840Z.json` records
04:48:40–07:28:36 UTC, Fundamentals DISABLED, preview attempts 0 and production
invoked false. Its stock log names the exact market/taxonomy paths; its
datacenter log covers 07:26:42–07:28:12 UTC. During this overlap market size grew
2,039,996,416 → 2,040,012,800 bytes and taxonomy grew
14,289,985,536 → 14,378,782,720 bytes, with taxonomy sidecars closing. This aligns
with those independent scheduled writes. FIX2 did not issue those writes or
restore the older dependency state. Both dependencies were stable in the final
comparison; future VALIDATE/BUILD must bind their then-current authority.

Actual task Sharadar/SEC HTTP calls: **0/0**. Live UPDATE resumed/new UPDATE
created: **NO/NO**. Task production financial, market, taxonomy, review queue,
scheduler, journal, manifest and watermark writes: **NO**. Normal independent
scheduled dependency activity above is disclosed separately. No full suite,
live recovery, production lock acquisition or storage optimization is performed.

Task-owned implementation paths:

- `rawcandle/fundamentals/admin/acquisition_snapshot.py`
- `rawcandle/fundamentals/admin/acquisition_quarantine.py` (new bounded helper)
- `rawcandle/fundamentals/admin/refresh_update.py`
- `rawcandle/fundamentals/admin/snapshot_workflow.py`
- `tests/test_fundamentals_acquisition_quarantine.py`
- `tests/test_fundamentals_snapshot_integration.py` (isolate default-route test
  from authorized production configuration)
- This report and the linked Phase 2 / Phase 3B contract follow-ups.

Unrelated journal/runtime generation state, the pre-existing baseline rollout
report, OHLCV reports/outputs and repair script are left unstaged. No production
database copies, compaction, VACUUM, history reduction, evidence deletion or
storage optimization is performed. Test writes are isolated fixture writes.

## Remaining operational boundary

FIX2 does not finish the original live UPDATE. Its remaining source fetches,
SEC evidence, financial decisions and candidate eligibility are not inferred
from fixture success. The next operator action is to authorize a same-ID
FETCH/VALIDATE/inactive BUILD continuation after reviewing this correction and
rechecking the original age and current native preflight. Stop at any global
gate. Publication and scheduler enablement require their own authority.
Only task-owned source/tests/documentation are committed; no push.
