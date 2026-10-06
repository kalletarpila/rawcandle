# Phase 13G.3.73: Policy V1 Reviewed Apply Plans

Date: 2026-10-06 (Europe/Helsinki).
Starting HEAD: `15f412ca438d3cba8d51f0d2ea8168c4db6a3011`.
Source generation: `publication_drain_20261006T110330Z_2d836e37`.
Scope: explicit policy-aware reviewed plans and copy-only rehearsal. No live apply.

## Contract Review

Phase 69 schema-1 plans reproduce legacy resolver uniqueness. Their ordinary
exact-key selector excludes AMBIGUOUS and aged rows. All 26 Phase 72 reviewed
quarters are AMBIGUOUS, including six outside the ordinary recent window. Reusing
that selector unchanged for V1 would prepare zero keys, not the authorized 23.

V1 therefore has an **explicit reviewed event-cohort scope**, not a widened retry
selector. It accepts only supplied, reviewed exact identities and matching stored
candidate evidence, including reviewed historical ambiguity. VERIFIED, missing
identity and conflicting CIK states cannot become apply keys. The policy plan
binds all inspected state; APPLY cannot reselect or widen the cohort.

LEGACY plans, ordinary exact allowlists, normal drain, retry cap 100, uncapped
NEW_THIS_REFRESH and the default 60-day horizon remain unchanged. No generic
earliest/latest rule, source-rank change or acceptance-time replacement is added.
The old Phase 69 source-scope contract remains the default, not V1's reviewed
historical event scope. This distinction is explicit in the artifact and journal.

## Policy-Aware Plan

`policy_mode` is `LEGACY` when absent. Explicit `LEGACY` remains schema 1.
Explicit `PUBLICATION_EVENT_POLICY_V1` is schema 2 with evidence schema
`reviewed_event_observations_v1`. Missing/inconsistent mode or version cannot fall
back to legacy reproduction. Default PREPARE output remains unchanged.

V1 PREPARE requires both an exact allowlist and an explicit `--policy-evidence`
input. There is no implicit test-fixture path, network observation generator or
unreviewed extraction fallback. Phase 72's reviewed semantic observations remain
the facts supplied to the deterministic policy evaluator, not autonomous NLP.
This phase does not reinterpret or invent financial/event scope.

The plan persists:

- Explicit policy/evidence versions and reviewed-input fingerprint.
- All 26 inspected quarters' complete authority and company/CIK/security state.
- All 52 original stored candidate records, including excluded and holdout evidence.
- Frozen `SecFiling` primary/section/exhibit context and complete company request
  windows, content-addressed by the existing deterministic fingerprint.
- Source-bound observations, event classification, eligibility/reasons, review
  conditions, relations/proof/fingerprints, and exact precedence decisions.
- Stored acceptance, fresh submissions observations, reviewed index evidence,
  timezone interpretation and corroboration status.
- Per-quarter decision fingerprint covering policy version, frozen-input reference,
  original evidence, observations, relations, acceptance evidence and reproduced
  decision. An aggregate fingerprint binds every quarter decision.
- Only deterministic UNIQUE keys in `prepared_keys`/`per_case`. REVIEW/AMBIGUOUS/
  ERROR remain separate PREPARE classifications with no selected timestamp.
- Exact selected evidence, accession/time, prepared-key fingerprint, complete
  generation manifest binding, and overall plan fingerprint.

The loader reconstructs and validates legacy candidates before policy evaluation.
Original evidence IDs and every resolver-produced field must match the stored
baseline. Observation/context fingerprints and same-accession excerpt constraints
still apply. It reproduces the full V1 decision and exact selected evidence, then
also verifies reproduction under narrowed/chunked apply context. Removing a
preliminary/completion relation produces ambiguity, never an earliest fallback.

Outer/inner fingerprints reject stale or altered classes, excerpts, context,
candidates, relations, selected accession/time, acceptance observations and policy
versions. Acceptance corruption also fails the corroboration gate. As in Phase
69, fingerprints are tamper evidence, not signatures or an independent SEC
authenticity service: fully regenerated consistent artifacts require a new review.

## Candidate Apply and Evidence Retention

V1 dispatch is isolated in `admin/policy_reviewed_publication_plan.py`; ordinary
`run_candidate_publication`, `enrich_database`, exact allowlists and default
resolver behavior are unchanged. The plan adapter validates and reproduces all
policy decisions, checks every cohort state/evidence record against the inactive
candidate, then supplies **only reproduced selected evidence** to the existing
`apply_resolution` authority machinery. It does not issue direct VERIFIED SQL.

The existing backlog writer still owns the production lock, inactive candidate
copies, verified backups, journal, immutable generation activation, postflight,
rollback/recovery and cleanup. Publication against a finalized generation is
rejected. Source/state drift fails before the first apply call; a mid-apply failure
rolls back the candidate transaction and prevents activation.

All original evidence rows must already match the reviewed source and are checked
again after apply. Existing INSERT OR IGNORE semantics retain the original rows
without changing their contents or dispositions. Filtered != erased. Later
completion/revision evidence keeps its own availability timestamp; no later
financial value is backdated to preliminary publication. Structured policy
provenance is retained in the immutable plan and writer report; journal scope
binds the corresponding decision fingerprints. No authority/evidence schema
migration is introduced.

## Journal and Recovery

Scope evidence retains `scope_mode=REVIEWED_APPLY_PLAN`, plan ID/fingerprint,
prepared-key fingerprint/count and original allowlist binding. V1 additionally
records policy/evidence versions, aggregate policy-decision fingerprint and all
individual quarter decision fingerprints.

Existing first-recovery behavior restores the old generation and raises
RETRY_REQUIRED. Retry requires the exact same immutable plan and all policy scope
bindings. Missing policy binding, different plan/version, legacy/default or
ordinary allowlist fallback is rejected. Three crash boundaries and missing-policy
journal fencing were exercised on disposable roots. No recovery machinery was
redesigned.

## Exact Cohort Results

| Stage | Unique | Ambiguous | REVIEW |
| --- | ---: | ---: | ---: |
| V1 eligibility, including proven supplemental-repeat exclusion | 19 | 4 | 3 |
| Typed precedence / prepared keys | 23 | 0 | 3 |

Exactly 52 original events are bound. The four preliminary/completion cases are
GME, TE, RDVT and RXT; both events qualify and the proven typed relation selects
the qualifying preliminary stage. All 10 reviewed acceptance discrepancies for
GME, MOVE, ANRO, KLXE and PDYN are bound and corroborated. Stored timestamps are
preserved; fresh submissions observations are not selected instead.

Exact prepared cases:
GME, SMCI, MOVE, GOSS, REKR, ANRO, KSCP, TE, CDXS, KLXE, ASTS, BKD, CRC, PLUG,
RDVT, RXT, ARKO, APA, CF, DMLP, PDYN, RGLD, SM.

ABAT: REVIEW, annual/Q4 scope unproven.
OPTT: REVIEW, annual-only initial/revised results do not establish Q4.
AMR: REVIEW, segment sales do not prove consolidated revenue perimeter.
All three remain outside `prepared_keys` with NULL proposed selection; their
authority and candidate evidence remain untouched in rehearsal.

## Production-Shaped Copy Rehearsal

Runtime root: `/tmp/rawcandle_policy_plan_13g373_20261006`.
The source's 2.4 GiB immutable generation was cloned to `source_copy`; PREPARE ran
against that copy. The same protected plan was then consumed in the separate
`rehearsal` root through the real generation writer. No production workflow ran.

Plan ID: `publication_policy_plan_12d859a36d394cfb92305360db011346`.
Plan fingerprint:
`fed4727c8793fc4112b1821fd4ae8cca7c5f79594e5b3441adcd8b51aa1ebf99`.
Prepared-key fingerprint:
`fddd07b14716d3a54c628afa20efe792c42107a97f635317fac379bcb6f058eb`.
Aggregate policy-decision fingerprint:
`2716cabb2c61e71a6037a68434d6f3194a5df5f6ff68fe8f4d021688e8ec0aae`.

- Rehearsal: PASSED; exactly 23 VERIFIED authorities, exact prepared/apply set.
- Holdouts, outside-cohort authority and existing VERIFIED history: unchanged.
- Original 52 candidate records, including all filtered/completion evidence: retained.
- Unrelated publication changes: 0; network fetches: 0.
- Canonical non-publication semantic table fingerprints: unchanged.
- Provider and analysis file hashes: unchanged.
- Journal: COMPLETED; postflight: PASSED; immutable copy activation succeeded.
- Production provider/canonical/analysis, pointer, journal, queue and scheduler
  hashes: all seven unchanged before/after the operation.

The compact committed CSV has one row per original quarter with preparation,
selection/review outcome, relation count, exact plan/decision fingerprints and
rehearsal result. Runtime plans, frozen payload, cloned DBs, backups, generations
and journals are deliberately not committed.

## Operator Interface

Example PREPARE against an existing reviewed copy root:

```sh
venv/bin/python -m rawcandle.cli.result_publication_backlog_drain \
  --rehearsal-root /tmp/reviewed_source_copy \
  --prepare-reviewed-plan \
  --publication-event-policy PUBLICATION_EVENT_POLICY_V1 \
  --policy-evidence /tmp/reviewed_event_evidence.json \
  --exact-allowlist /tmp/reviewed_cohort.csv \
  --output-plan /tmp/reviewed_policy_plan.json
```

`--reviewed-apply-plan <path> --rehearsal` dispatches from the explicit bound plan
mode. An optional `--publication-event-policy` assertion must match that plan.
Without rehearsal/apply, it only validates state. Policy flags are rejected for
ordinary allowlist/drain modes. Live apply support is structural only and retains
existing `--apply --confirm-production` confirmation; it was not executed.

## Validation and Safety

Focused validation: **227 tests**, covering policy-plan schema/reproduction,
revision/repeat/no-backdating, all legacy plan tests, exact/default writer
regressions, V1 cohort/ambiguity tests, source/timestamp authority, no-network
rehearsal, recovery fencing, zero plans, holdout drift and existing VERIFIED safety.
No full suite was run. Compile/import and `git diff --check` passed.

Production publication state changed: NO. Default Production policy changed: NO.
Financial DBs, active generation, Review Queue and scheduler changed: NO.
Live workflows executed: NO. No live apply, Refresh, drain, SEC fetch, recovery,
timer enablement or backup deletion occurred. Pre-existing worktree changes remain.
No push.
