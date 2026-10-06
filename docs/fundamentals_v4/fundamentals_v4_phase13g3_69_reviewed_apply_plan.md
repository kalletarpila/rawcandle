# Phase 13G.3.69: Reviewed Publication Apply Plans

Date: 2026-10-06 (Europe/Helsinki)
Starting HEAD: `53b9c55617b9f3dd18f57111ac3ab2a233e6b3d2`.

## Contract

The Reviewed Apply Plan is an operator-gating and evidence-handoff artifact. It does not change publication authority, resolver semantics, ambiguity policy, or retry policy.

Production apply using a Reviewed Apply Plan must use the same frozen SEC evidence reviewed during PREPARE and must not refetch network evidence.

Phase 13G.3.68 stopped because an ordinary exact allowlist permits all successfully
resolved outcomes through normal apply semantics, not just a separately reviewed
fresh-unique subset. Its CLI also had no cross-invocation frozen-input handoff.
The new mode supplies that operator gate above the existing resolver/writer.
It does not change ordinary exact-allowlist eligibility or outcome behavior.

## Lifecycle

PREPARE parses the original reviewed CSV and classifies its current state using
indexed exact-key queries and the existing 60-day horizon. VERIFIED, AMBIGUOUS,
missing identity, non-open and out-of-scope cases never reach fetching. Only
eligible original allowlist keys are fetched and resolved. No global recent-open
cohort is fetched or used as a substitute for that scope.

The existing `resolve_sec_filings_detailed` supplies candidate eligibility,
matching and candidate counts. Exactly one candidate produces FRESH_UNIQUE;
zero/multiple candidates produce NO_CANDIDATE/AMBIGUOUS. Fetch failures are
FETCH_ERROR. Noneligible keys are separately NO_LONGER_OPEN or
IDENTITY_OR_SCOPE_DRIFT. These labels are artifact classifications, not new
production statuses. Only FRESH_UNIQUE keys enter `prepared_keys`.

All database inspection during PREPARE uses SQLite `mode=ro`. No candidate,
backup, journal write, recovery, activation or production lock mutation is made.
The only output is a runtime plan file. Existing files cannot be overwritten;
complete JSON is fsynced, published through an exclusive hard link, made read-only
(0444), and the containing directory is fsynced. Writes into production data or
backup directories are rejected. Source generation/state and terminal journal
are rechecked before publishing the artifact.

APPLY loads and validates the entire artifact, requires normal explicit production
confirmation, and uses the existing writer lock. Inside the lock, journal/recovery
guard, artifact fingerprint, active generation and every prepared key's state
are checked. Any drift rejects the whole plan before candidate creation; keys
are not dynamically dropped, added or resolved against fresh network inputs.

An empty plan is a valid artifact. APPLY returns SKIPPED with
`NO_PREPARED_PLAN_KEYS`, after safety checks, without candidate generation,
backups, journal preparation or authority mutation. It never falls back to the
ordinary backlog.

## Schema and Integrity

Schema version 1 records:

- Plan ID, UTC creation time, as-of date and retry horizon.
- Original allowlist path, normalized keys, count and original fingerprint.
- Active generation ID and canonical JSON fingerprint of its complete manifest.
- Sorted prepared keys, count and prepared-key fingerprint.
- Per-case complete quarter/authority and company/CIK/security row bindings,
  prior status, scope state, unique outcome, candidate count and parent CIK.
- Parent accession, form, acceptance timestamp, matching method and linked
  exhibit provenance/context.
- Existing resolver evidence payload, per-case evidence fingerprint and frozen
  input reference.
- Immutable filing inputs, original CIK/year/date-window request and quarter
  context, classifications and PREPARE request counters.
- Full plan fingerprint excluding only the fingerprint field itself.

Fingerprints use deterministic sorted-field compact JSON and SHA-256. The
prepared keys must have canonical order and shape, be unique and be a subset
of the original reviewed allowlist. JSON with duplicate field names, unsupported
versions, altered payloads, missing frozen inputs or inconsistent inner hashes
is rejected. The same immutable artifact content gives the same fingerprint;
separate preparations have distinct IDs/timestamps and may have different hashes.

Fingerprinting is tamper evidence, not a cryptographic signature or an independent
SEC authenticity service. Operators must review and retain the printed plan
fingerprint alongside the protected artifact; regeneration is a new review.

Complete relevant authority and identity rows bind more than just prior status:
same-status metadata edits, quarter ID/period/date changes, CIK mapping changes,
security edits and generation/manifest changes all fail closed. The recorded
horizon is evaluated at APPLY's current as-of date; aging out is drift, not an
automatic extension of the recent window.

## Frozen Inputs and Resolver Authority

Frozen inputs are the existing `SecFiling` fields: normalized primary text,
legacy-primary eligibility flag, normalized sections, bounded exhibit text,
original HTML-content exhibit SHA-256, source URLs, accession and acceptance time.
No raw SEC HTML is added to the model. Text required by the current resolver is
retained without lossy summarization. Negative/ranking filing context is retained,
not only the selected candidate. Shared company context is content-addressed once.

The loader reconstructs `SecFiling`/`SecResultExhibit`, validates parent URL against
CIK/accession/document, same-accession exhibit URLs, timestamp normalization,
Item 2.02 parent eligibility and field shapes. Existing resolver reproduction
must produce the exact recorded single evidence payload and exhibit context.
Narrowing from original inspection keys to prepared keys, including 200-key
chunk boundaries, must reproduce that payload as well; otherwise the artifact
is rejected rather than manufacturing uniqueness by removing context.

`PlanSecClient` permits only the request windows derived from the reviewed keys
and returns the frozen filing objects. All its network entry points reject;
unexpected CIK/window requests raise a database error so the existing fallback
cannot turn an input mismatch into an authority write.

The existing `run_candidate_publication`, `enrich_database` and `apply_resolution`
remain authoritative. The plan does not force VERIFIED. Candidate state must
still match, apply must return exactly the plan set with normal unique results,
and selected evidence ID/source/parent acceptance must match the reviewed input.
Any failure blocks activation and discards the inactive candidate via the
existing writer failure path. Ordinary exact/default behavior is unchanged.

## Rehearsal and Publication

Rehearsal clones the bound immutable source generation and its manifest into a
new isolated root, not production. It consumes the exact same plan through the
existing writer, including backups, journal, immutable activation and postflight.
No network is fetched. Source and financial-role hashes are checked; deterministic
before/after canonical table fingerprints prove financial/identity content and
all publication rows outside plan keys unchanged. This protects AMBIGUOUS,
already VERIFIED and C8/unrelated rows independently of status.

The structured rehearsal JSON records plan ID/fingerprint, before/after digests,
unrelated change count and writer evidence. It is retained in the rehearsal
root's `fundamental_reports/publication_plan_rehearsal.json`. No new optional
rehearsal-approval fingerprint requirement is introduced in this phase.

Publication uses the current candidate copy, SQLite verification, verified
backups, journal preparation, immutable pointer activation, postflight,
rollback/recovery and candidate cleanup. No second publication mechanism or
direct active-generation authority writes were introduced.

## Recovery

Journal scope evidence adds `scope_mode=REVIEWED_APPLY_PLAN`, plan ID, plan
fingerprint, prepared-key fingerprint/count and original allowlist provenance,
alongside selected/enriched/applied key evidence.

The existing first recovery invocation restores the source generation and raises
RETRY_REQUIRED. After recovery, only the identical plan fingerprint can retry.
Missing/different plans and ordinary/default/exact-allowlist attempts fail before
selection. Scope evidence survives crashes and rollback. Completed plan journals
do not restrict subsequent ordinary workflows. Plan state bindings are still
rechecked on retry. No recovery machinery or backup retention rules were changed.

## Operator CLI

Commands below document later authorized operation; none were run against
production in this phase. Plan files belong in runtime/operator storage, not docs.

```bash
venv/bin/python -m rawcandle.cli.result_publication_backlog_drain \
  --prepare-reviewed-plan \
  --exact-allowlist docs/fundamentals_v4/fundamentals_v4_phase13g3_66_controlled_publication_application.csv \
  --output-plan fundamental_reports/publication_drains/reviewed_plan.json

venv/bin/python -m rawcandle.cli.result_publication_backlog_drain \
  --reviewed-apply-plan fundamental_reports/publication_drains/reviewed_plan.json \
  --rehearsal

venv/bin/python -m rawcandle.cli.result_publication_backlog_drain \
  --reviewed-apply-plan fundamental_reports/publication_drains/reviewed_plan.json \
  --apply --confirm-production
```

`--rehearsal-root` optionally selects a new empty copy root with `--rehearsal`;
omitting it creates an isolated `/tmp` root. Without rehearsal, that existing
option still targets an already prepared non-production project root.
Reviewed-plan invocation without `--apply` is read-only scope validation, not
rehearsal and not network PREPARE. Plan binding/count/fingerprints are printed to
stderr; stdout remains structured result JSON. Plan and exact-allowlist modes
cannot be combined; PREPARE cannot be combined with APPLY/production flags.

## Validation and Safety

Focused command:

```bash
venv/bin/python -m pytest -q tests/test_reviewed_publication_plan.py tests/test_publication_exact_allowlist.py tests/test_publication_backlog_drain.py tests/test_candidate_publication.py tests/test_result_publication_authority.py
```

111 tests passed: 39 new plan/handoff tests plus 72 existing exact-writer,
default writer, journal/rollback, candidate and authority regressions. Coverage
includes protected statuses, stale/unknown identities, fetch errors, zero plans,
tampering, malformed inputs, frozen exhibits, no-network calls, in-lock checks,
source/authority/identity drift, apply reproduction, scope expansion, three crash
boundaries, first recovery abort, missing/different-plan fences, rollback, CLI
and multiple quarters sharing the same frozen company/date-window context.
The original 60-row CSV remains a valid PREPARE input without hardcoded live counts.

A separate production-shaped fixture rehearsal passed at
`/tmp/rawcandle_13g369_fixture_604qrh_i`. Its reviewed set had unique, current
VERIFIED/AMBIGUOUS, aged, no-candidate, fetch-error and new-conflict cases, with an
unrelated open row outside review. Only one unique key entered the plan and was
applied through the existing writer. Rehearsal unrelated changes were zero,
journal COMPLETED, postflight PASSED, candidate cleanup complete, and network
statistics contained only one frozen-input read. The same plan also succeeded
against the separate source fixture root; neither root was production.
Plan fingerprint:
`5c879b032a97d17d0d173e1caa6ec6b916d64c792ce86cf4c3a893686daecf2f`.

Compile/import checks and `git diff --check` passed. The full suite was not run.
No live SEC fetch, production PREPARE/APPLY, blanket drain, Refresh, scheduler,
recovery or backup deletion was executed. Production publication/financial DBs,
active generation, Review Queue, scheduler and runtime journal were unchanged.
Read-only SHA-256 comparison against the Phase 13G.3.66 STOP evidence confirmed
all three production role DBs, pointer, journal, Review Queue and scheduler
configuration unchanged; active generation ID also matched.
Only source/tests/this report are committed; runtime plans, frozen evidence,
fixture generations/backups and existing dirty research/runtime work are excluded.
No push.
