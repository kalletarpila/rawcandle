# Phase 13G.3.80: Controlled Live Form 6-K Reviewed APPLY

Date: 2026-10-07 (Europe/Helsinki).
Starting HEAD: `3d2fa397737b147dfabf5fc0baa763aadae0323e`.
Old active generation: `publication_drain_20261006T150551Z_9cfd3ca0`.
New active generation: `publication_drain_20261007T093516Z_fd654a20`.
Scope: live operator phase, exactly nine reviewed authority keys; no source edits.

## Executive Summary

Executed the first confirmed live `FORM_6K_RESULT_PUBLICATION_AUTHORITY_V1`
reviewed APPLY using a **fresh live PREPARE**, immutable plan validation,
same-plan rehearsal and final live-state gate. All stages passed.

The 23-quarter / 30-candidate cohort reproduces **9 UNIQUE / 2 timestamp REVIEW /
6 multiple-event / 5 wrong-period / 1 temporal-identity REVIEW**. Exactly nine
NOT_FOUND rows became VERIFIED, explicitly sourced to `SEC_FORM_6K_RESULT`,
rank **2**, confidence **MEDIUM**, V1 rule version and exact reviewed parent
accessions/acceptance timestamps. Fourteen held rows remain NOT_FOUND unchanged.

Live result **SUCCESS**, journal **COMPLETED**, postflight **PASSED**, immutable
activation **ACTIVATED_AND_VERIFIED**, rollback **NOT_REQUIRED**. Network fetches
were zero. All existing evidence and outside-plan authority were preserved.
Financial content, identity/fiscal mappings, provider/analysis bytes, Review Queue,
scheduler config and source code remain unchanged. No Refresh or retry/drain ran.

## Bounded Review and Preflight

Reviewed only Phase [79](fundamentals_v4_phase13g3_79_form6k_live_apply_gate.md),
Phase [78](fundamentals_v4_phase13g3_78_form6k_reviewed_plan_integration.md), its
CSV, frozen fixture, current authority/generation, actual CLI and existing lock/
journal/publication contracts. No broad repository scan, new research or source
implementation work was needed. HEAD includes the approved Phase 79 gate;
tracked source/tests have no unexpected modifications.

Preflight validated provider/canonical/analysis `quick_check=ok` and zero foreign
key errors. Journal was COMPLETED with no recovery pending. Admin-production and
scheduler kernel locks were both available via read-only nonblocking probes.
The source bundle is 2,553,917,440 bytes; free space exceeded eight bundles plus
1 GiB for rehearsal, candidates, generations and retained rollback backups.
Both active source publication CHECK definitions still excluded the new source.

The Phase 77 fixture file SHA remains:
`689f3e25f3309a5414af84ff6c58f9563f0eb401be6421400373168e1a418387`.
Its semantic fixture fingerprint is:
`bc14070bae6a90c87c47119ef28e127b102a70a8b34f7187246da093d5fe215d`.

Full state, role inventories/hashes, schema definitions, manifest, cohort, source
file hashes, Review Queue, scheduler config, journal and recent-open scope were
captured before PREPARE. A temporary operator helper initially compared runtime
tuples with their serialized JSON lists and stopped before invoking PREPARE.
JSON normalization proved the complete live state identical; only that `/tmp`
helper comparison was corrected. RawCandle source was not changed and no real
state drift was found.

## Fresh Plan and Commands

Runtime/operator directory:
`fundamental_reports/publication_drains/form6k_13g380/`.
Plan ID: `publication_form6k_plan_9fd0ad37d32e4db390929f2d22f5ed2e`.
Plan fingerprint:
`7b7e09f3275cee515c41c20e290cd70a22abe5effbe0de4bb38dd6f8e3c72c12`.
Prepared-key fingerprint:
`81c9fc6ef7919eeb576f0ceff6dbfe81657a595ff47d95f1f8c449e67b397632`.
Aggregate decision fingerprint:
`8db13d88f825b267a418297d1ba5211883958774818c1ba8aa1649e7053006ae`.
Reviewed cohort fingerprint:
`43fcf3d9274adaec95c821682680b0d9d94460ffd6d8af09efde2c5cbe18f95b`.
Active source manifest fingerprint:
`29a0407bc3a18a3ecf68698e88a216c4698590158098052f8a0944eecebbc18d`.
Canonical authority/identity-state fingerprint, matching live PREPARE:
`a429b489fc1530dadc3da889b3e22f9f2f1a6871bd1b788da451b40e47365394`.

Actual subprocess invocations used the existing CLI, not direct SQL or writer
substitution. From the repository root, the commands were equivalent to:

```bash
venv/bin/python -m rawcandle.cli.result_publication_backlog_drain \
  --prepare-reviewed-plan \
  --publication-authority-mode FORM_6K_RESULT_PUBLICATION_AUTHORITY_V1 \
  --policy-evidence tests/fixtures/form6k_authority_v1.json \
  --exact-allowlist docs/fundamentals_v4/fundamentals_v4_phase13g3_78_form6k_reviewed_plan_results.csv \
  --output-plan fundamental_reports/publication_drains/form6k_13g380/reviewed_plan.json

venv/bin/python -m rawcandle.cli.result_publication_backlog_drain \
  --reviewed-apply-plan fundamental_reports/publication_drains/form6k_13g380/reviewed_plan.json \
  --publication-authority-mode FORM_6K_RESULT_PUBLICATION_AUTHORITY_V1 \
  --rehearsal --rehearsal-root /tmp/rawcandle_13g380_rehearsal

venv/bin/python -m rawcandle.cli.result_publication_backlog_drain \
  --reviewed-apply-plan fundamental_reports/publication_drains/form6k_13g380/reviewed_plan.json \
  --publication-authority-mode FORM_6K_RESULT_PUBLICATION_AUTHORITY_V1 \
  --apply --confirm-production
```

PREPARE was read-only for publication data; complete preflight matched afterward.
Schema 3, explicit mode/version/source/rank/confidence, complete state bindings,
all plan/fixture/cohort/key/aggregate/per-quarter fingerprints, all 23 quarters and
30 candidates were validated. Prepared keys came from PREPARE, not a hardcoded
ticker list. Decisions and selected accessions/timestamps were compared with the
Phase 78 reviewed CSV; the exact partition matched with no errors. All 14 held
decisions have no selected timestamp. Identity/ADR, provider conflicts, acceptance
and relation evidence remain frozen; no depositary-bank filer or chronology
shortcut qualifies, and no timestamp correction or issuer substitution was used.

## Same-Plan Rehearsal and Final Gate

The newly prepared live plan was rehearsed on `/tmp/rawcandle_13g380_rehearsal`.
Result PASS, prepared/selected/applied **9/9/9**, network **0**, unrelated changes
**0**, journal COMPLETED, postflight PASSED, rollback NOT_REQUIRED. Financial
digests, outside-prepared authority/evidence, provider/analysis, source hashes,
held state and exact selected results passed the normal rehearsal checks.
Immutable copy activation succeeded and the temporary candidate lane was removed.
CLI runtime: **46.536 seconds**. Plan fingerprint was unchanged afterward.

Final gate at `2026-10-07T09:29:12Z` passed with the same source generation,
manifest, full 23-case authority/identity/evidence state, all fingerprints and
COMPLETED journal. Both locks were available. No stronger VERIFIED authority,
scope or identity drift was present. A fresh immediate pre-APPLY capture matched
the preflight again; the writer then reloaded/revalidated under its normal admin
and scheduler locks. The plan was neither regenerated nor narrowed after rehearsal.

## Live APPLY and Selected Results

Writer run: `publication_drain_20261007T093516Z_fd654a20`.
Source remained the old immutable generation throughout candidate preparation.
The existing writer performed the inactive canonical candidate CHECK upgrade,
frozen replay, common `apply_resolution`, exact apply-set checks, verified backups,
journal and atomic immutable activation. No active DB migration, manual authority
edit, direct manifest change, ordinary scope substitution or fresh SEC fetch was
performed. Native writer runtime: **21.179 seconds**; CLI runtime **23.580 seconds**.
PREPARE CLI runtime: **3.129 seconds**.

| Ticker | Parent accession | Selected UTC | Transition |
| --- | --- | --- | --- |
| WDH | 0001104659-26-105667 | 2026-09-08T11:30:46Z | NOT_FOUND -> VERIFIED |
| CAN | 0001104659-26-105660 | 2026-09-08T11:20:24Z | NOT_FOUND -> VERIFIED |
| NEGG | 0001213900-26-094402 | 2026-08-27T20:30:01Z | NOT_FOUND -> VERIFIED |
| VNET | 0001104659-26-098054 | 2026-08-18T10:16:34Z | NOT_FOUND -> VERIFIED |
| PAAS | 0000771992-26-000063 | 2026-08-12T21:38:01Z | NOT_FOUND -> VERIFIED |
| BTDR | 0001213900-26-086938 | 2026-08-10T11:08:07Z | NOT_FOUND -> VERIFIED |
| CAMT | 0001178913-26-003975 | 2026-08-10T11:16:13Z | NOT_FOUND -> VERIFIED |
| WPM | 0001193125-26-338641 | 2026-08-06T22:47:58Z | NOT_FOUND -> VERIFIED |
| NVMI | 0001178913-26-003892 | 2026-08-06T11:30:57Z | NOT_FOUND -> VERIFIED |

Every row has source `SEC_FORM_6K_RESULT`, rank 2 in versioned evidence provenance,
MEDIUM confidence and `FORM_6K_RESULT_PUBLICATION_AUTHORITY_V1` rule version.
Selected evidence IDs, payload fields, exact parent/time and complete frozen
candidate proof match the fresh plan. All nine new evidence rows are ACCEPTED.

Held unchanged: BABA/BIDU timestamp conflicts; TSEM/TSM/POET/GDS/NBIS/CLLS competing
events; MKDW/MLGO/HOLO/SCNI/BHP wrong periods; IQMX temporal identity and separate
issuer-source handoff. Their complete state and evidence compare exactly with
preflight, not merely their NOT_FOUND status.

## Storage and Postflight Proof

All new active role DBs report `quick_check=ok`, zero FK errors. Journal is
COMPLETED, postflight PASSED, generation activation ACTIVATED_AND_VERIFIED,
rollback NOT_REQUIRED. Every journal plan/mode/version/source/scope/decision
binding matches the immutable live plan.

Full authority comparison finds **exactly nine changed natural keys**, no added
or deleted authority keys. All original evidence rows remain byte-for-field
identical; exactly nine new selected evidence IDs exist. All **16,221** authority
rows outside prepared scope, including previously VERIFIED rows, are unchanged.
All **14,164** outside-scope evidence rows retain the same semantic digest.
All **26** non-publication canonical table digests match, including monetary
financials, provenance, quarter identities and fiscal/identity mappings.

Provider/analysis hashes and sizes match preflight. All three OLD source role
hashes/integrity results still match, and the old manifest/schema are unchanged.
The new canonical schema changes exactly **two** objects: the evidence and
authority source CHECK definitions, each equal to the old definition with only
the explicit new allowed source added. No other table/index/view/trigger SQL
changed. Unsupported arbitrary-source CHECK rejection was validated using these
new CREATE definitions and selected rows **in memory only**, never by writing
to the immutable active DB.

The candidate lane was removed. Verified OLD provider/canonical/analysis backups
remain under:
`backups/fundamentals_admin_production/publication_drain_20261007T093516Z_fd654a20/`.
Each retained backup's hash, size, quick_check and FK result match the old source.
Old generation and rollback backups were not deleted.

## Recounts

Current recent-open scope is measured with the unchanged selector as of
2026-10-07 and 60 calendar days, using `max(first_public_result_date,
source_availability_date)` as scope context, not publication authority.

| Recent-Open | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Total | 159 | 152 | -7 |
| UNRESOLVED | 18 | 18 | 0 |
| NOT_FOUND | 139 | 132 | -7 |
| AMBIGUOUS | 2 | 2 | 0 |

Prepared inside scope: **7**. Outside: **2**, WPM and NVMI. The current cutoff is
2026-08-08; WPM's context date is 2026-08-07 and NVMI's 2026-08-06. Therefore the
measured reduction is seven, not the earlier conditional estimate of eight when
only NVMI was outside. No historical reviewed key was forced into retry metrics.

Reviewed cohort: **23 total / 9 VERIFIED / 14 NOT_FOUND / 0 other statuses**.
Decision partition remains **9 applied / 2 timestamp holds / 6 multiple-event /
5 wrong-period / 1 temporal-identity hold**. No retry or drain followed recount.

## Default-Path and Production Safety

Source file hashes and fixture are identical to preflight; no RawCandle source
or test edits were made. Source hierarchy remains issuer 4, 8-K Item 2.02 3,
explicit reviewed 6-K/fallback 2, manual 1. Structural CHECK support does not add
6-K to global `SOURCE_RANK` or ordinary candidate authorization. Normal discovery,
Refresh, retry, exact/default drain and scheduler do not acquire 6-K automatically.
Timestamp/identity rules, retry logic and 60-day horizon were not changed.

Review Queue and scheduler configuration hashes remain unchanged. No live Refresh,
automatic retry, ordinary backlog drain or scheduler workflow ran. Publication
state and the active generation changed only through this approved exact-nine
operation. Financial content and unrelated pre-existing research artifacts were
preserved. No test suite was run; validation was operational PREPARE/replay/
rehearsal/final gate/postflight plus `git diff --check`.

## Artifacts and Commit Scope

The runtime directory retains preflight/schema/inventory and source hashes,
fresh PREPARE, immutable plan/validation, exact commands/stdout/stderr/execution
times, rehearsal, final gate, production output, semantic before/after,
postflight, schema comparison, summary/recounts and local `live_results.csv`.
The writer's own output is also retained in its run directory. Rehearsal DBs,
generations, backups and journal remain in `/tmp/rawcandle_13g380_rehearsal`.

Only this report and the [23-row live result CSV](fundamentals_v4_phase13g3_80_live_form6k_reviewed_apply.csv)
are committed. Runtime plan/payloads, Production DBs, active pointer, backups,
journal, lock files, logs and unrelated dirty worktree files are excluded. No push.
