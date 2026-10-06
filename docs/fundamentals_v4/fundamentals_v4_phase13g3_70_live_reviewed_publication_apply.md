# Phase 13G.3.70: Live Reviewed Publication Apply

Date: 2026-10-06. Outcome: **SUCCESS**. Production APPLY executed once.

Baseline HEAD: `a9a3209fa5878c9c98636800ffde32a362a2df24` (Phase 13G.3.69).
No source changes or tests were needed. The operation used the existing reviewed-plan CLI,
resolver, immutable-generation writer, backup, journal and postflight contracts.

## Reviewed Scope and Plan

Authoritative inputs: [original 60-case allowlist](fundamentals_v4_phase13g3_66_controlled_publication_application.csv)
and [reviewed apply-plan contract](fundamentals_v4_phase13g3_69_reviewed_apply_plan.md).
The approved natural key is `(company_id, fiscal_year, fiscal_quarter)`.

| Measure | Result |
| --- | --- |
| Original reviewed unique keys | 60 |
| Current eligible reviewed keys, measured at PREPARE | 43 |
| Fresh unique / prepared keys | 43 |
| No candidate / ambiguous / fetch error | 0 / 0 / 0 |
| Out of current 60-day scope | 17 |
| Identity/scope drift classification | 17, all `NOT_IN_CURRENT_SCOPE` |
| Other drift / no longer open | 0 / 0 |
| Rehearsal | PASSED |
| Rehearsal unrelated changes | 0 |
| Production applied / new VERIFIED | 43 / 43 |
| Historical 28 UNRESOLVED -> VERIFIED | 21 |
| Historical 32 NOT_FOUND -> VERIFIED | 22 |
| Existing AMBIGUOUS modified | 0 |
| Original reviewed keys remaining open, all ages | 17: 7 UNRESOLVED, 10 NOT_FOUND |

Plan ID: `publication_plan_6132f85cf00e476f81a0432a7b6d4d1c`.

| Binding | SHA-256 fingerprint |
| --- | --- |
| Original allowlist | `4b69d8500733c1d3e3d5219458bf070dc5c8fb6b99f4082e3241413c9a99ce4e` |
| Immutable plan | `428a920fc5aaef831618dd8eeaaee51bee319a70599c36f599914c5a5685ee16` |
| Prepared key set | `3d2f49ae09291ecd370e9e33265fb4cbd064fbf1c1a893ab6c3a4c8fd83a9c9b` |
| Source generation manifest | `2fc75401017b63e79d45ed9ac7afbaf7e01bdb19485d42913fd51b4449b4d210` |
| Canonical authority state | `fe10afc22c54e8b63d934038c333a90b9f9406adcc687035466eecff26d07255` |

Runtime artifact directory (not committed):
`fundamental_reports/publication_drains/publication_13g370_operator_20261006/`.
Plan: `reviewed_plan_13g370.json`, schema version 1, created `2026-10-06T10:59:43Z`,
immutable/read-only. Frozen evidence and raw SEC documents are not included in this documentation commit.

## Preflight and Review Gates

Preflight PASS: active generation resolved, all three role databases matched their
manifest hashes, `quick_check=ok`, zero FK errors, journal COMPLETED, no recovery
pending. Existing publication/scheduler kernel locks were available; probes were
read-only and did not change lock-owner files. No source/test modifications existed.
Source roles totalled 2,553,741,312 bytes. Both repository and temporary storage had
699,076,108,288 bytes available against a conservative 17,876,189,184-byte requirement.

The original CSV parsed into exactly 60 unique keys with the approved fingerprint.
All original reviewed keys were still open before PREPARE; 17 were outside the
current horizon. PREPARE did not modify production publication state.

Plan structural validation and the committed state revalidation passed. Every
prepared key was a currently eligible FRESH_UNIQUE result, previously UNRESOLVED or
NOT_FOUND, with one candidate and complete frozen parent/evidence/context bindings.
No VERIFIED, AMBIGUOUS or outside-reviewed key entered the prepared set.

Authority timestamp invariant: **PASS**. Every selected timestamp is the parent
eligible Item 2.02 8-K SEC acceptance timestamp, not a linked-exhibit timestamp.
Where exhibits supplied context, accession, URL, hash and fiscal-identity provenance
remained bound to that same parent. The frozen representation is the accepted
normalized filing/context representation, not separately stored raw SEC HTML.

Immediately before Production, the final gate at `2026-10-06T11:02:42Z` revalidated
the same plan, source generation/manifest, all authority/open-state bindings and
clean journal. No key was dropped or regenerated. The CLI then applied its existing
locked revalidation and production-write safety checks.

## Commands Executed

Executed from the repository root, in this order, using the unchanged CLI:

```bash
venv/bin/python -m rawcandle.cli.result_publication_backlog_drain \
  --prepare-reviewed-plan \
  --exact-allowlist docs/fundamentals_v4/fundamentals_v4_phase13g3_66_controlled_publication_application.csv \
  --output-plan fundamental_reports/publication_drains/publication_13g370_operator_20261006/reviewed_plan_13g370.json

venv/bin/python -m rawcandle.cli.result_publication_backlog_drain \
  --reviewed-apply-plan fundamental_reports/publication_drains/publication_13g370_operator_20261006/reviewed_plan_13g370.json \
  --rehearsal

venv/bin/python -m rawcandle.cli.result_publication_backlog_drain \
  --reviewed-apply-plan fundamental_reports/publication_drains/publication_13g370_operator_20261006/reviewed_plan_13g370.json \
  --apply --confirm-production
```

PREPARE alone used live SEC access: 43 metadata requests, 72 document requests,
115 total network requests; 46 candidate filings inspected, 1,903 outside-scope
filings skipped and 26 context exhibits fetched. Rehearsal and Production each
read 43 frozen inputs and made **zero network fetches**. Both existing resolver/apply
executions reproduced all 43 unique results; the plan itself did not grant authority.

Rehearsal root: `/tmp/rawcandle_publication_plan_fao9kvn8`.
Its copied generation was `publication_drain_20261006T110051Z_551bbdea`, not Production.
Writer runtime: 22.554 seconds in rehearsal and 23.443 seconds in Production;
Production acquisition/replay and enrichment took 1.593 seconds within the writer.

## Production Publication and Postflight

Source generation: `publication_drain_20261005T064921Z_43a1e040`.
Activated generation: `publication_drain_20261006T110330Z_2d836e37`.

Production result SUCCESS; journal **COMPLETED**; postflight **PASSED**;
activation **ACTIVATED_AND_VERIFIED**; rollback **NOT_REQUIRED**.
Journal scope is `REVIEWED_APPLY_PLAN`, with the exact plan ID, plan fingerprint
and prepared-key fingerprint recorded. Selected, enriched and applied key sets
each equal the same 43 prepared keys, without duplicates or widening.

Independent read-only postflight repeated all active-role quick checks and FK
checks, verified manifest hashes, and checked every selected authority/evidence
payload against its frozen plan payload. All timestamps, selected evidence IDs,
matching methods, parent accessions and linked-exhibit provenance matched.
The same immutable plan and frozen evidence were used in rehearsal and Production.

| Active role | Bytes | SHA-256 | quick_check / FK errors |
| --- | --- | --- | --- |
| Provider | 968331264 | `2b3a57add8b51413d98f220d4cdd313994d1a4079f987a94796bf6a2b6db5fbb` | ok / 0 |
| Canonical | 675065856 | `ce7a57a33e6fe40e7741c1bddc97b4580d2e374f3fc2b9c95164a189436ae48d` | ok / 0 |
| Analysis | 910483456 | `a8dcc37e1a0e2442dd44023b63d8c6ba91ee5fdce3ab05e2fa5407413a0355ce` | ok / 0 |

All canonical non-publication tables were compared using the existing semantic
digest helper against the rehearsal's verified source baseline. Row counts and
digests matched exactly, including financial values, identity/fiscal mappings,
quarter identities, provenance and TTM content. All publication authority and
evidence rows outside the prepared keys also matched exactly: 16,187 authority
rows and 14,121 evidence rows. Thus existing AMBIGUOUS, already VERIFIED and C8
unrelated rows were untouched; Production unrelated changes = **0**.

Provider and analysis remained byte-identical. All original-generation role files
and retained backups matched their preflight hashes. Canonical source/backup hash:
`6fb73fe67e9d28407012ebb76e9b57951e409898b817a4eca94e58d934d4b5c2`.
Rehearsal and Production candidate lanes were cleaned up by the existing writer.
Backups are retained under
`backups/fundamentals_admin_production/publication_drain_20261006T110330Z_2d836e37/`.
No rollback, manual repair, repeated Production APPLY or backup deletion occurred.

## Cohort Impact

Read-only measurement uses the existing 60-calendar-day selector as of 2026-10-06,
with no mutation, retries or backlog drain. These are whole-cohort counts, not the
writer's deliberately bounded 43-key counters.

| Current recent-open population | Before | After |
| --- | --- | --- |
| UNRESOLVED | 41 | 20 |
| NOT_FOUND | 170 | 148 |
| AMBIGUOUS | 20 | 20 |
| Total | 231 | 188 |

The original 60 now contain 43 VERIFIED, 7 UNRESOLVED and 10 NOT_FOUND.
The 17 still-open reviewed identities are outside the current 60-day scope, were
not prepared/applied, and retained their complete prior authority rows unchanged.
They were not brought back into scope. The [60-row outcome CSV](fundamentals_v4_phase13g3_70_live_reviewed_publication_apply.csv)
preserves every original identity; `current_scope_state` means scope at PREPARE,
while `post_status` is the post-Production state.

## Safety and Evidence

Publication state changed: YES, plan keys only. Active generation changed: YES,
through normal immutable publication. Canonical/provider financial content changed:
NO. Existing AMBIGUOUS/C8/VERIFIED outside-plan content changed: NO.
Resolver code, authority policy, retry logic/cap/horizon, Review Queue, scheduler
configuration and systemd changed: NO. Live Refresh or scheduler execution: NO.
Review Queue and scheduler configuration SHA-256 stayed identical to preflight.
No full suite or automatic rerun of the 111 prior tests was performed.

Runtime evidence (retained locally, not committed): `preflight.json`,
`plan_validation.json`, `rehearsal_cli.json`, `final_gate.json`,
`production_cli.json`, and `postflight.json` in the operator artifact directory.
Normal Production writer report:
`fundamental_reports/publication_drains/publication_drain_20261006T110330Z_2d836e37/result.json`.
The existing journal records the immutable activation and retained role backups.
This commit contains only this Markdown report and its 60-row CSV. No push.
