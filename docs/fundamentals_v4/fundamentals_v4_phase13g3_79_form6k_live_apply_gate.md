# Phase 13G.3.79: Controlled Form 6-K Live APPLY Gate

Date: 2026-10-07 (Europe/Helsinki).
Starting HEAD: `f89445712f2db8119890cedb07f9ed115d79ea22`.
Real active generation: `publication_drain_20261006T150551Z_9cfd3ca0`.
Scope: bounded gate implementation and copy-only validation. No real live APPLY.

## Contract Review

Reviewed Phase [78](fundamentals_v4_phase13g3_78_form6k_reviewed_plan_integration.md)
and its result CSV, Phase [77](fundamentals_v4_phase13g3_77_form6k_authority_v1.md),
strict plan dispatch, writer root guard, confirmation, lock and recovery boundaries.
No broad repository scan or external research was needed.

The Phase 78 live-root prohibition was intentional rollout staging, not a missing
schema/ranking capability. All requested authorization checks already exist in
the reviewed-plan/writer composition. No additional bypass flag, writer, schema
redesign, authority contract, or acquisition path is necessary.

The sole production source change removes the unconditional rejection of a
Form 6-K reviewed plan when `project_root == ROOT`. It is replaced by an orienting
comment identifying the existing guards. No confirmation, state, journal, lock,
recovery, transaction or publication check is removed or weakened.

## Gate Before and After

Before: even a fully valid, confirmed schema-3 plan failed with
`PUBLICATION_FORM6K_COPY_ONLY_PRODUCTION_APPLY_FORBIDDEN` before the writer lock.
Isolated-root rehearsal was possible; confirmed actual-root APPLY was not.

After: the same strict reviewed-plan path is usable at the live root, but only
through the existing complete authorization chain:

1. `reviewed_apply_plan` must load through the strict schema-3 validator.
2. Mode/version must be `FORM_6K_RESULT_PUBLICATION_AUTHORITY_V1`; explicit
   source/rank/confidence must be `SEC_FORM_6K_RESULT` / 2 / MEDIUM.
3. The plan, fixture/cohort, prepared keys and aggregate/per-quarter decisions
   must fingerprint and reproduce exactly. Missing mode cannot become 6-K.
4. APPLY still requires `confirm_production=True`, equivalent to the existing
   `--apply --confirm-production`. Missing confirmation fails before locking.
5. The normal production and scheduler locks must be acquired successfully.
6. Journal recovery guard must allow a writer. Pending recovery restores OLD
   and stops with RETRY_REQUIRED; failed recovery blocks writes.
7. A recovered exact-plan fence must match every mode/source/version/scope hash.
8. The immutable artifact is reloaded under lock. Active generation/manifest,
   every cohort authority/quarter/company/CIK/security and original SQL evidence
   must still match before the candidate lane is created.
9. Only the already prepared exact keys reach the unchanged candidate adapter.
   Reproduction, exact apply-set and postflight checks must still pass.

The optional CLI mode assertion is not an authorization grant. There is no
`--allow-6k`, force switch, confirmation alternative or ordinary-drain opt-in.
Rehearsal continues to use its normal copy workflow without live confirmation.

Ordinary default/exact drains remain domestic operations, not prohibited as a
whole: supplying 6-K filing data there does not authorize a 6-K authority, create
the new source enum or produce a VERIFIED 6-K row. LEGACY/schema-1 and domestic
Policy V1/schema-2 behavior remains unchanged. Schema-1/2 artifacts pretending
to be Form 6-K schema-3 plans are rejected.

## Candidate Migration and Authority Safety

The Phase 78 adapter is unchanged. It rejects finalized-generation paths, opens
`BEGIN IMMEDIATE`, validates all bound cohort state/evidence and only then performs
the narrow CHECK migration inside a SAVEPOINT on the inactive candidate.
Frozen decisions are reproduced and passed to the existing `apply_resolution`.
The writer retains verified backups, immutable activation, journal/postflight and
cleanup. Active source tables are never migrated in place or repaired afterward.

Tests intercept the migration connection and prove its path is in the temporary
candidate lane, the transaction is active and the immutable old schema still
excludes the new source. An injected failure after schema upgrade aborts apply,
does not create a publication journal or activate a generation, and removes the
candidate lane. Phase 78's idempotency, original-row/index/view/trigger/FK retention
and transactional schema rollback regressions remain in the final group.

Source hierarchy remains issuer 4, Item 2.02 8-K 3, explicit 6-K/fallback 2,
manual 1. A newly stronger VERIFIED authority or same-rank conflict introduced
after PREPARE fails the full state gate before candidate creation. The underlying
common-apply stronger-source preservation and same-rank conflict rules are
unchanged and regression-tested.

The 23-case cohort still has exactly 9 prepared keys. BABA/BIDU timestamp holds,
six multiple-event holds, five wrong-period holds and IQMX's temporal-identity /
separate issuer handoff cannot become executable by enabling the root gate.
Widening prepared keys, deleting decisions or forging hold outcomes fails replay.
ADR/underlying-company witnesses, provider conflicts, typed relations, parent
acceptance/submissions/index/header agreement and timezone interpretation are
unchanged. There is no chronology shortcut, mapping repair, provider-label trust,
issuer timestamp substitution or network lookup during APPLY.

## Journal and Recovery

The existing journal binds the exact immutable plan ID/hash, authority mode/
version/source/rank/confidence, prepared key count/hash, cohort/fixture hash,
aggregate decision hash and all 23 per-quarter decision hashes.

Production-mode tests on isolated roots exercise `AFTER_PREPARED`,
`AFTER_NEW_GENERATION_READY` and `AFTER_GENERATION_ACTIVATION`. First recovery
restores the exact OLD role hashes, raises `PublicationRecoveredRetryRequired`
and does not continue mutation. Subsequent default, ordinary exact, LEGACY,
domestic Policy V1 and another valid 6-K plan are all rejected. Only the identical
frozen plan completes. Existing missing-binding fencing tests are retained.
`RECOVERY_FAILED` blocks a new writer. No recovery implementation was changed.

## Validation Method

Live-root unit tests change the writer's `ROOT` and the production lock module's
configuration root to disposable roots, with a local scheduler config and local
scheduler/admin lock files. This exercises the former ROOT-equality branch and
the actual production lock implementation without using real scheduler locks.

The production-shaped experiment first copies the real immutable source read-only
to `/tmp/rawcandle_13g379/source_copy`, prepares a new frozen 23-case plan there,
and runs the normal same-plan rehearsal in a separate `rehearsal` root. A second
copy, `production_mode_copy`, starts from the identical OLD generation and executes
confirmed Production-mode APPLY with the same plan. All SecClient network entry
points are failing sentinels. Both roots use the real writer and generation
publication machinery, not a stubbed gate or direct SQL simulation.

Comparisons cover all non-publication canonical tables, outside-prepared authority
and evidence, the 14 held rows, provider/analysis bytes, old source bytes, exact
selected publication fields, journal bindings and cleanup. Per-run audit clocks
(`verified_at_utc`/`updated_at_utc`) may differ between two operations; the exact
financial event timestamp, source, confidence, version, accession and selected
evidence identity may not differ.

Runtime plans, cloned DBs, backups, generations, journals and detailed JSON are
uncommitted under `/tmp/rawcandle_13g379/`. No duplicate result CSV is created;
this report and runtime JSON supply the two-run evidence, while Phase 78's CSV
already records the unchanged 23-case decisions.

## Real Production Read-Only Readiness

Only read-only production checks are performed: active generation, journal,
publication CREATE definitions, all cohort state/identity/evidence and comparison
against the Phase 78 binding. The old copy plan is read solely for this drift
check, not reused as a future Production plan. No live plan is created here.

The later operator phase must always perform fresh live PREPARE with a new
immutable plan, review current prepared/hold partition, rehearse that exact plan,
recheck live state under the normal guards, and supply explicit confirmation.
Any generation, authority, identity or evidence drift requires new review; a
past copy result never authorizes a changed live state.

Read-only result: **READY**. The real journal is **COMPLETED**, both active
publication table CHECK definitions still exclude `SEC_FORM_6K_RESULT`, and all
Phase 78 generation/state/identity/evidence bindings still match. Technical
blockers: none observed. Operational prerequisites remain fresh live PREPARE,
new exact plan review, exact-plan rehearsal, final state gate and confirmation;
no live plan or live APPLY was created in this phase.

## Recorded Results

New COPY plan: `publication_form6k_plan_fa9af5d47a4b46099bb8d65a1102fc82`.
Fingerprint: `0fccc10b142d6f2fe0545ea4f626052586655a6233ed67d6e8e815328a49e42a`.
Exact partition: **9 UNIQUE / 2 acceptance holds / 6 multiple-event /
5 wrong-period / 1 temporal-identity hold**, errors zero.

| Check | Same-Plan Rehearsal | Confirmed Production-Mode Copy |
| --- | --- | --- |
| Result | PASS | PASS |
| Prepared / selected / applied | 9 / 9 / 9 | 9 / 9 / 9 |
| Source / rank / confidence | SEC_FORM_6K_RESULT / 2 / MEDIUM | SEC_FORM_6K_RESULT / 2 / MEDIUM |
| Network fetches | 0 | 0 |
| Unrelated changes | 0 | 0 |
| Held rows unchanged | 14 | 14 |
| Journal / postflight | COMPLETED / PASSED | COMPLETED / PASSED |
| Rollback | NOT_REQUIRED | NOT_REQUIRED |
| Immutable activation | PASS | PASS |
| Candidate cleanup | PASS | PASS |

Rehearsal COPY activation: `publication_drain_20261007T090608Z_d937d053`.
Production-mode COPY activation: `publication_drain_20261007T090652Z_2b3c012d`.
Total copy preparation, both workflows and read-only postflight: **92.451 seconds**.
The nine authority results match apart from per-operation audit clocks. Financial
table digests, outside-scope authority/evidence digests, provider/analysis bytes
and original source role hashes match. All real-production preflight/postflight
capture fields, including DB/pointer/journal/queue/scheduler hashes, match exactly.

Initial focused live-gate tests: **32 passed in 17.17 seconds**. A first test
attempt exposed a test-only list/tuple mismatch when calling the semantic digest
helper; it was corrected without changing production code. Two additional
live-root LEGACY/domestic compatibility tests bring gate coverage to **34**.
Final focused-plus-relevant regression group: **419 passed in 76.81 seconds**.
It includes all gate tests, Phase 78 integration/storage/recovery, Phase 77
evaluator, legacy/domestic plans, exact/default writer, candidate publication,
source authority and domestic event policy. **Full suite not run.**

Result CSV: **NOT_CREATED**; it would duplicate the unchanged Phase 78 cohort CSV
and the two-run result table above. Detailed runtime evidence is in `prepare.json`,
`rehearsal.json`, `production_mode.json`, `summary.json`, `preflight.json` and
`postflight.json` under `/tmp/rawcandle_13g379/`, never in the commit.

## Production Safety and Next Phase

The source authority evaluator, schema migration, default resolver/acquisition,
normal refresh/retry/exact scope, 60-day horizon, CLI, scheduler, journal and
recovery implementations are unchanged. The existing dirty journal and unrelated
research/data artifacts are preserved and excluded from the commit. No live
publication/financial/identity data, active generation, Review Queue, scheduler
config or journal is changed by this phase.

After both copy gates and regressions pass, recommend **13G.3.80 - Controlled Live
Form 6-K Authority V1 Reviewed Apply** as a separate operator phase. Enabling the
bounded writer capability is not execution of that live operation and does not
enable automatic Form 6-K discovery, retries, refresh or scheduler use. No push.
