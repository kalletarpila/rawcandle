# P1.8A — Publication-drain support in existing run acceptance

The existing acceptance inspector now recognizes reviewed publication drains, verifies their terminal journal/generation/backup evidence, and supplies an in-memory view to the existing acceptance contract. The real P1.7 run is ELIGIBLE. No real cleanup was invoked and no real acceptance metadata was recorded.

## Reproduced P1.8 failure

Before changing source, `inspect_cleanup_eligibility(publication_drain_20261009T175136Z_e99387cf)` returned `NOT_ELIGIBLE / CLEANUP_RUN_DIRECTORY_INVALID` from `_run_dir`: the default Admin root does not contain this publication-drain report. With the explicit `fundamental_reports/publication_drains` root, it returned `NOT_ELIGIBLE / Run is not a Production update` because the old inspector required `mode=PRODUCTION_APPLY`. The original result instead has `operation=RESULT_PUBLICATION_BACKLOG_DRAIN`, `apply=true`, `status=SUCCESS`, `journal_state=COMPLETED`, source/published generations, backup/postflight records and reviewed scope. It has no Admin `outcome` or embedded journal. Both failures were reproduced against the exact selected run before the adapter was installed.

## Additive recognition and journal mapping

Only `rawcandle/fundamentals/admin/run_acceptance_cleanup.py` changed. Explicit run kinds are `ADMIN_PRODUCTION_APPLY` and `PUBLICATION_DRAIN`. Publication recognition uses the structured operation field, exact boolean apply, reviewed-plan scope and terminal evidence. Unknown operation kinds in the publication directory reject; ordinary Admin mode/outcome/publication/journal gates remain unchanged.

`_run_dir` checks the requested root and, only for an `admin_runs` root, its established sibling `publication_drains`. It never recursively discovers reports. Ambiguous duplicate run IDs, symlinked run directories/operation roots and unknown publication reports reject. Explicit publication-root inspection also works. Run History enumeration and UI code are unchanged: technical publication-drain operations are not added as default rows, and no duplicate entry or new UI workflow is introduced. The existing service’s explicit `cleanup_eligibility(run_id)` and `accept_run_and_cleanup_backups(run_id)` routes use this same resolver.

The canonical publication journal is read from the existing explicit `journal_path` argument (default `data/.fundamentals_admin_publication_journal.json`). It must identify the selected run and `RESULT_PUBLICATION_BACKLOG_DRAIN`, use GENERATION_POINTER, and prove COMPLETED/current step COMPLETED/postflight PASSED/activation ACTIVATED_AND_VERIFIED/rollback-recovery NOT_REQUIRED. An alternative embedded journal, if present, must agree exactly. The adapter re-reads the canonical journal and active manifest after its read-only verification; disagreement rejects.

The operation’s published generation, OLD generation, current active manifest and both on-disk generation manifests must agree with the journal. Exact provider/canonical/analysis role sets and role paths must agree. The reviewed plan and scope must agree across operation and journal; selected natural keys are unique and reproduce the membership fingerprint. Candidate SUCCESS, processed/VERIFIED/applied counts, complete applied-key list and zero unprocessed/error keys must agree with that scope. A SUCCESS string alone cannot establish eligibility.

**Historical limitation:** the publication subsystem currently retains one mutable canonical journal, not an immutable per-run journal archive. The adapter does not guess historical terminal/recovery state after another run replaces that evidence. A journal belonging to any other run, or an active manifest advanced beyond the selected journal/generation, rejects. Historical Admin acceptance remains unchanged. Supporting older publication runs after advancement would need separately designed durable lineage evidence; no permissive fallback was added here.

## Exact ownership, integrity and unchanged deletion boundary

Publication inspection requires exactly the selected `backup_root/run_id/{provider,canonical,analysis}.db` inventory with no extra files. Existing path/source ownership validation rejects symlinks and paths outside that selected set. The OLD generation sources must agree with operation backups and journal lineage; source verification, backup verification, journal old/verified fingerprints and old-manifest role verification must agree. Recorded sizes must agree with the files. Published role fingerprints must agree across operation, journal, new manifest and actual current role bytes. Backup and active-role SQLite quick checks and foreign-key checks must pass.

The adapter supplies a normalized in-memory result with run kind, terminal mode/outcome and the independently loaded journal. No historical result or journal JSON is rewritten. Existing `_generation_publication_sources` and `_validated_manifest` are reused. The existing `_accept_run_and_cleanup_backups_locked` remains the only deletion boundary, inside the existing Production/scheduler lock. It repeats inspection/normalization and its existing hash/integrity checks, then re-reads and compares terminal evidence immediately before its unchanged three-file unlink loop. Generation directories and audit artifacts never enter the backup allowlist. Existing `backup_cleanup.json` audit and repeat-cleanup behavior are reused.

## Focused tests

`python3 -m pytest -q tests/test_publication_drain_run_acceptance.py tests/test_fundamentals_admin_run_acceptance_cleanup.py` → **79 passed** (46 publication-drain cases, 33 existing Admin acceptance/UI cases; 15.97 seconds). Two additional focused contradiction cases also passed after tightening rejection of optional conflicting mode/outcome fields: **81 total**, including 48 publication-drain cases. The directly relevant existing group includes Run History/UI action routing, idempotency and the no-backup-hashing rule for ordinary Admin history inspection. No unrelated groups or full suite were run.

The small synthetic P1.7-shaped fixture includes source/published SQLite roles, generation manifests, the canonical journal and the original operation report shape. Coverage includes apply false/wrong type, failed/nonterminal operations, each terminal journal gate, mismatched run/generation/scope, missing file and metadata for every role, unexpected files, hash/size/source/path changes, backup and operation-root symlinks, corrupt backup/live SQLite, conflicting evidence and optional mode/outcome fields, missing manifests, journal replacement during verification, later-run journal/active-generation rejection, duplicate run-root IDs, and exact cleanup ownership. Cleanup tests run only in pytest temporary directories and prove selected backups alone are deleted while both generations, other-run backups and report/audit evidence remain intact. Normal Admin tests passed unchanged.

## Real P1.7 read-only validation

Selected run: `publication_drain_20261009T175136Z_e99387cf`. Checked with the updated default-root inspector at `2026-10-09T20:12:56+00:00`.

- Recognized kind: **PUBLICATION_DRAIN**.
- Eligibility: **ELIGIBLE**; canonical journal: **COMPLETED**; terminal/activation/postflight/recovery binding: **PASS**.
- Exact backup ownership, current generation/manifest and actual role/hash/size/SQLite checks: **PASS**.
- Selected inventory: **3 files / 2,627,518,464 bytes**.
- Real cleanup invoked: **NO**. Real acceptance state recorded: **NO**.
- Remaining selected inventory: **3 files / 2,627,518,464 bytes**. No `backup_cleanup.json` exists for this run.

| Selected backup | Bytes | Verified SHA-256 |
|---|---:|---|
| `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/publication_drain_20261009T175136Z_e99387cf/provider.db` | 968331264 | `fda234de30f448fe342fd5fc842ff430575fd6b361146409cf1f8131e17f2981` |
| `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/publication_drain_20261009T175136Z_e99387cf/canonical.db` | 749371392 | `996deb198513b94e22888dbbb11b8139698b68cf98201a5df4d9bb8cd30a1845` |
| `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/publication_drain_20261009T175136Z_e99387cf/analysis.db` | 909815808 | `9da7016ef65571d47b8ae9d2db79f4f42589dc866c1967042fbde8e770db9e8c` |

Active generation before/after: `publication_drain_20261009T175136Z_e99387cf`. Manifest fingerprint: `ff44c14a9d2a3834bd1bc0b6e2e4da86870b58839279ced82eced69447c13d1a`.

Before/after file hashes and sizes are identical for active provider/canonical/analysis DBs, active pointer, publication journal, Review Queue and existing WAL/SHM, scheduler configurations, operation report, proposal, approval, handoff/semantic support, plan, execution authorization and P1.7 report/result CSV. All protected hashes also match the P1.8 baseline. Canonical byte identity proves unchanged authority and financial state. The current provider watermark and normal refresh identity remain inside the unchanged provider DB. Policy V1 and ordinary resolver source files were not modified.

Publication authority changed: NO. Financial DBs changed: NO. Active generation changed: NO. Review Queue changed: NO. Journal changed: NO. Scheduler changed: NO. Watermark changed: NO. Policy V1 changed: NO. Resolver changed: NO. Selected backups deleted: NO.

## Exact P1.8B next step

Retry runtime acceptance for exactly `publication_drain_20261009T175136Z_e99387cf` using the existing `accept_run_and_cleanup_backups` action. Re-establish current state, run the updated default inspector, reconcile the exact three-file/2,627,518,464-byte backup inventory and gates, then invoke the existing locked action only if eligibility remains valid. Verify its `backup_cleanup.json`, zero remaining selected backup bytes, untouched generations/active data/audit evidence and unchanged other backups. If the canonical journal or generation advanced, STOP rather than reuse this read-only PASS. P1.8A performs no part of that runtime deletion.

Commit scope: this acceptance adapter, focused tests and this report only. No runtime reports, journals, generations, databases, logs or backups are committed. Nothing was pushed.
