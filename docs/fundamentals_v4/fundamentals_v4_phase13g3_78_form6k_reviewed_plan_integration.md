# Phase 13G.3.78: Form 6-K Reviewed Apply Plan Integration

Date: 2026-10-07 (Europe/Helsinki).
Starting HEAD: `3d1bc2f6de5193967224a1cc2c007b9e23c66ad9`.
Source generation: `publication_drain_20261006T150551Z_9cfd3ca0`.
Scope: explicit offline PREPARE and real writer on isolated copies only.

## Executive Summary

Integrated `FORM_6K_RESULT_PUBLICATION_AUTHORITY_V1` into reviewed plans and
the existing inactive-generation writer. The frozen 23-quarter / 30-candidate
cohort reproduces **9 UNIQUE / 2 timestamp REVIEW / 6 multiple-event /
5 wrong-period / 1 temporal-identity REVIEW**. Exactly nine keys were prepared
and became VERIFIED in the production-shaped copy rehearsal.

`SEC_FORM_6K_RESULT` is stored explicitly, with rank **2**, confidence **MEDIUM**
and the V1 authority version. This requires a narrowly scoped, transactional
publication CHECK migration on the inactive candidate. Production was not
migrated or applied. The copy journal completed, postflight passed, rollback was
not required, all unrelated data stayed identical, and network fetches were zero.

The result is ready for a separately approved controlled-live phase, not automatic
6-K acquisition or default refresh enablement. A writer gate currently rejects
this mode's APPLY against the real repository root even with confirmation flags.

## Contract Review

Reviewed only Phase [77](fundamentals_v4_phase13g3_77_form6k_authority_v1.md),
the frozen fixture and results, Phase [73](fundamentals_v4_phase13g3_73_policy_v1_reviewed_plan_integration.md),
reviewed-plan dispatch, publication SQL, the ordinary apply function, and existing
immutable-generation/journal/recovery machinery. No broad repository scan or
network research was needed. No conflicting refresh/locking contract was found.

The schema's source CHECK constraints were the concrete storage conflict. The
other necessary compatibility change is reading an already stored 6-K rank
when comparing a subsequent domestic/issuer candidate. This is separate from
authorizing new 6-K candidates and does not add 6-K to the global `SOURCE_RANK`.

Pre-existing dirty journal, active-generation files, and unrelated research
artifacts were preserved and excluded from the commit.

## Storage / Source Contract

`upgrade_form6k_candidate_schema` extends only the two publication tables'
source enums. It preserves their original CREATE definitions, constraints,
columns, values, explicit indexes and triggers. Both publication tables are
physically rebuilt because SQLite cannot alter a CHECK in place; existing rows
are copied without changing their contents or dispositions. No financial or
identity table is migrated. Views keep their original names and targets.

The adapter opens `BEGIN IMMEDIATE`, binds all cohort state/evidence, then performs
the migration within a SAVEPOINT. Evidence is recreated before authority, with
foreign keys enabled and checked. Triggers are restored after copying rows, so
copying historical evidence does not invoke insert side effects. Unexpected
incoming foreign keys or a partially upgraded/unrecognized schema fail closed.
An already upgraded pair is a no-op. Rollback restores the old CHECK definitions
and rows. The default schema initializer remains unchanged.

Selected evidence stores the explicit source, parent accession/document, exact
timestamp and V1 `rule_version`. Its versioned `matching_method` JSON stores rank
2, MEDIUM confidence, decision fingerprint and complete frozen event/acceptance/
identity/relation proof. Authority stores source, MEDIUM confidence and the V1
rule version. No alias to 8-K, fallback or issuer source is used.

Hierarchy remains issuer 4, Item 2.02 8-K 3, ordinary fallback 2, manual 1.
Explicit 6-K is rank 2. The common writer preserves stronger VERIFIED authority
exactly; a same-rank conflicting timestamp fails closed under the existing
AMBIGUOUS rule. Default candidate authorization still excludes 6-K. The read-only
rank compatibility permits a later rank-3/4 candidate to supersede stored 6-K
without a KeyError or changed hierarchy.

## Reviewed Plan Contract

Existing naming is retained: missing `policy_mode` means LEGACY/schema 1;
`PUBLICATION_EVENT_POLICY_V1` means schema 2; explicit
`FORM_6K_RESULT_PUBLICATION_AUTHORITY_V1` means schema 3. Source values cannot
implicitly activate this mode. Missing/inconsistent mode or authority version
fails; legacy and domestic policy plans retain their previous validation paths.

PREPARE requires explicit authority mode, exact natural-key CSV and frozen
evidence JSON. There is no implicit fixture, acquisition fallback or network
client. The schema-3 plan binds:

- Plan ID/fingerprint, schema, mode/version, explicit source/rank/confidence.
- Entire reviewed fixture/version/fingerprint, all 23 keys and 30 candidates.
- Active generation ID/manifest hash and full per-quarter canonical, authority,
  company, CIK, security and existing SQL evidence state.
- Current status/timestamp, current 60-day membership, complete decisions,
  per-quarter fingerprints and their aggregate fingerprint.
- Exact prepared keys/count/hash, selected evidence/accession/time and all holds.

Quarter contents, reporting CIK and security/company identity must agree with
the frozen witness. Revalidation checks every cohort row and stored evidence,
not just prepared rows, against the current active generation under the existing
writer lock. Full replay verifies every decision and selected payload before
apply. Immutable plan publication uses the existing exclusive/fsynced path.

The reviewed-key identity gate is reused, not the normal retry selector. NVMI is
explicitly reviewed despite being outside the normal 60-day window. The normal
60-day horizon, default retry scope and exact-allowlist semantics are unchanged.
Zero prepared keys return SKIPPED before cloning, migration, journal or default
drain; there is no scope widening.

The smallest new CLI surface is `--publication-authority-mode` for PREPARE or
an explicit mode assertion when loading a plan. It is mutually exclusive with
`--publication-event-policy`. For an operator-supplied isolated copy root:

```bash
venv/bin/python -m rawcandle.cli.result_publication_backlog_drain \
  --prepare-reviewed-plan \
  --rehearsal-root /tmp/isolated_source_copy \
  --publication-authority-mode FORM_6K_RESULT_PUBLICATION_AUTHORITY_V1 \
  --policy-evidence tests/fixtures/form6k_authority_v1.json \
  --exact-allowlist /tmp/reviewed_23_keys.csv \
  --output-plan /tmp/reviewed_form6k_plan.json
```

The existing `--reviewed-apply-plan <path> --rehearsal` interface uses the actual
active source read-only and creates an isolated target; it performs no live
activation. The production-shaped exercise here used the same rehearsal API with
an already isolated source copy as an extra safety boundary.

Fingerprints are tamper evidence, not signatures or an independent verifier of
financial meaning. A fully regenerated, internally consistent artifact is a new
plan and requires a new operator review and approval of its exact hash.

## Frozen Evidence and Apply

The new adapter retains parent/result URLs and hashes, excerpts, primary/exhibit
roles, original acceptance observations, fiscal/entity/financial facts, official
ADR/underlying-issuer chain, temporal witnesses and provider type conflicts.
Submissions/index agreement and available headers reproduce parent acceptance.
No timezone correction, fresh fetch or alternate accession is substituted.

All five Phase 77 typed relation types remain supported by the same evaluator.
CLLS's XBRL-only supplement is retained and excluded as a new first event;
its two competing result events remain held. NBIS's candidate acceptance conflicts
remain inside its multiple-event decision. All 11 ADR cases and ten provider
security-type conflicts remain bound without changing identity mappings.

Only UNIQUE cases enter `per_case`. The adapter reruns the Phase 77 evaluator,
checks the exact decision, then supplies the reproduced selected payload to
**the existing `apply_resolution`**, using a narrow explicit reviewed-case
argument. That function independently replays the eligibility proof and checks
exact payload/quarter equality before enabling a local rank-2 entry. There is
no second VERIFIED writer. The existing UPSERT, evidence retention, source
hierarchy, transaction, generation publication and recovery still own mutation.

All existing SQL evidence is checked before and after apply and remains unchanged.
The nine selected events' full proof is stored in their new evidence records.
All 30 reviewed candidates, including held/nonselected/wrong-period/relation
evidence and IQMX's independent issuer-source handoff, remain in the immutable
plan. Held quarters receive **no new SQL rows or authority mutations**; retaining
their external evidence in the plan does not authorize writes outside nine keys.
Finalized-generation paths are rejected by the adapter.

## Exact Cohort Result

| Prepared | Parent accession | Reproduced timestamp UTC |
| --- | --- | --- |
| NEGG | 0001213900-26-094402 | 2026-08-27T20:30:01Z |
| BTDR | 0001213900-26-086938 | 2026-08-10T11:08:07Z |
| CAMT | 0001178913-26-003975 | 2026-08-10T11:16:13Z |
| VNET | 0001104659-26-098054 | 2026-08-18T10:16:34Z |
| WPM | 0001193125-26-338641 | 2026-08-06T22:47:58Z |
| NVMI | 0001178913-26-003892 | 2026-08-06T11:30:57Z |
| PAAS | 0000771992-26-000063 | 2026-08-12T21:38:01Z |
| WDH | 0001104659-26-105667 | 2026-09-08T11:30:46Z |
| CAN | 0001104659-26-105660 | 2026-09-08T11:20:24Z |

These names are test/result expectations, not production policy logic.
BABA/BIDU remain timestamp holds with no selected timestamp. TSEM/TSM/POET/GDS/
NBIS/CLLS remain multiple-event holds. MKDW/MLGO/HOLO/SCNI/BHP remain wrong-period.
IQMX remains `IDENTITY_TEMPORAL_REVIEW`, retaining acceptance conflict and separate
issuer-source handoff. No generic earliest/latest decision was introduced.
Errors: zero. The [result CSV](fundamentals_v4_phase13g3_78_form6k_reviewed_plan_results.csv)
contains all 23 rows and decision/plan hashes.

## Copy Rehearsal

Runtime artifacts are uncommitted under `/tmp/rawcandle_13g378/`:
`source_copy`, `reviewed_form6k_plan.json`, `rehearsal`, PREPARE/rehearsal/summary
and preflight/postflight JSON. The production active generation was read-only
copied first; PREPARE and the real writer's existing rehearsal ran against copies.
All SecClient network entry points were replaced with a failing sentinel.

Plan ID: `publication_form6k_plan_768af51be92245519f8c684fd12ac3e4`.
Plan hash: `913a9723a709c8ddb88941721491f3d4df49d3a18a5745eeb34cc0c1aada02ea`.
Aggregate decision hash: `8db13d88f825b267a418297d1ba5211883958774818c1ba8aa1649e7053006ae`.
Activated COPY: `publication_drain_20261007T064725Z_1b154ba6`.
Total copy/prepare/rehearsal/postflight runtime: **48.731 seconds**.

Result: **PASS**, prepared/selected/applied **9/9/9**, new VERIFIED **9**,
network **0**, unrelated mutations **0**. All selected accessions/timestamps,
source/rank/confidence/version match. Fourteen held cohort rows stayed identical.
All **16,221** authority rows outside the prepared set and **14,164** outside
evidence rows retained their semantic digests. All 26 non-publication canonical
tables matched before/after, including 89,914 quarters, 89,914 financial rows,
all fiscal/identity mappings and provenance tables. Provider and analysis bytes
matched the source. Production role hashes also stayed unchanged:

- Provider: `2b3a57add8b51413d98f220d4cdd313994d1a4079f987a94796bf6a2b6db5fbb`.
- Canonical: `ed5f37239dcde7b012e9ba4aaaa9e00c0ad5ba91e98d23a5c1fd32525170a65d`.
- Analysis: `a8dcc37e1a0e2442dd44023b63d8c6ba91ee5fdce3ab05e2fa5407413a0355ce`.

Journal **COMPLETED**, postflight **PASSED**, rollback **NOT_REQUIRED**,
immutable copy activation succeeded and temporary candidate lane was removed.
Verified backups and immutable copy generations remain only in the rehearsal root.

## Journal / Recovery

`scope_mode=REVIEWED_APPLY_PLAN` binds plan ID/hash, mode/version, source/rank/
confidence, prepared-key count/hash, cohort/fixture version/hash, aggregate hash
and **all 23** per-quarter decision hashes. A recovered fence requires every
binding to match the identical immutable plan. Missing fields, different source
or version, default drain, ordinary exact scope or LEGACY/domestic substitution
cannot continue. A source/mode binding cannot fall back to another integration.

Disposable-root tests exercise `AFTER_PREPARED`, `AFTER_NEW_GENERATION_READY` and
`AFTER_GENERATION_ACTIVATION`. First recovery restores the exact OLD generation
and hashes, raises `PublicationRecoveredRetryRequired`, and does not continue
mutation. A scope-less retry is rejected; only the same frozen plan completes.
Removed mode/version/source/prepared/aggregate/per-quarter/cohort journal bindings
are rejected. No journal/recovery architecture was redesigned.

## Validation

Initial focused integration run: **39 passed**. The final targeted integration
and relevant grouped regression run covers Form 6-K evaluator/plans/storage,
legacy and domestic Policy V1 reviewed plans, ordinary exact allowlists, backlog
writer, candidate publication, source authority and domestic event policy.
Final result is recorded after execution below. **No full suite was run.**
Final grouped result: **385 passed in 70.24 seconds**, including **46** focused
integration tests and the unchanged Phase 77 evaluator's **112** tests.

Coverage includes schema idempotency and transaction rollback; preserved old rows,
indexes/views/triggers/FKs; arbitrary-source rejection; explicit mode; 23/30/9
bindings; resealed outer-plan tampering; acceptance, ADR, relation, selected
payload and version corruption; stronger-source preservation and rank-2 conflict;
default 6-K rejection; read compatibility for later issuer/8-K evidence; no-network
real rehearsal; outside/held invariance; finalized-generation rejection; zero-key
SKIPPED; CLI compatibility; crash/recovery and exact-plan fences.

## Production Safety and Next Phase

Production publication rows, timestamps/statuses, financial role DBs, active
pointer/generation, Review Queue, scheduler config and journal matched preflight.
The domestic policy implementation and source ranks stayed unchanged. No live
APPLY, refresh, retry, backlog drain or scheduler was run. The Phase 77 fixture is
unchanged. Default acquisition, resolver candidate eligibility, retry logic and
60-day horizon remain unchanged. No Production identity mapping was edited.

Recommended next phase: **13G.3.79 - Controlled Live Form 6-K Authority V1 Reviewed
Apply**, requiring explicit approval, fresh active-state review and exact immutable
plan/hash review, verified old-generation backup, and a separately reviewed change
to the current live-APPLY gate. The current copy plan cannot be reused after
generation/authority/identity drift. Do not enable automatic acquisition or retry
widening as part of a nine-key live rollout. No push was performed.
