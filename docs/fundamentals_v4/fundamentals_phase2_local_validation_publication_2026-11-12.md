# Fundamentals Phase 2 — local validation and disposable publication

Implemented a snapshot-consuming backend with real native provider/canonical/analysis builds, explicit disposable publication, native postflight and OLD recovery. **Production remains disabled and unchanged.** This is the bounded disposable implementation requested by FUND-V4-PHASE-2, not acceptance of every production integration item in the architecture's larger Phase 2.

Starting HEAD: `29fec9e34b02866a14a74456050d0fb090dd3ad7`. Governing contracts are the [accepted architecture](fundamentals_simplification_v1_architecture_2026-11-11.md), [Phase 1 foundation](fundamentals_single_fetch_acquisition_foundation_v1_2026-11-11.md) and [scheduler/history/queue correction](fundamentals_scheduler_hold_history_queue_correction_2026-11-12.md). No live update, scheduler reactivation, financial policy change or historical authority-backlog cleanup is authorized by this implementation.

## Implemented scope and authority

`admin/refresh_update.py` exposes these local entry points:

1. `create_disposable_environment(root)` creates an exclusively owned directory under `/tmp` or repository `temp`, with an exact ownership marker. It does not copy production data. Populate the environment with synthetic/native fixture databases and a Phase 1 snapshot, as the integration tests do.
2. `validate_snapshot(env, snapshot_operation_id, as_of_date=...)` opens the immutable Phase 1 capture, validates original acquisition evidence and OLD binding, evaluates native financial rules and approval matches, and writes a sealed validation receipt plus hash-bound decisions.
3. `build_candidate(env, validation_id, expected_validation_fingerprint=...)` builds only the validated safe partition into one inactive generation. It requires the exact current receipt fingerprint. It never activates that generation.
4. `publish_disposable(env, validation_id, expected_validation_fingerprint=..., confirmation="PUBLISH_DISPOSABLE_FUNDAMENTALS_ONLY")` rechecks source freshness, OLD, code, dependencies, queue and exact candidate bytes; uses native backups, generation activation and postflight; commits or restores OLD. Use the updated fingerprint returned by BUILD, rather than the superseded VALIDATE fingerprint.
5. `recover_disposable(env)` invokes native interrupted-publication recovery without requiring the source snapshot. A restored incomplete publication produces native `PublicationRecoveredRetryRequired`; it is not a successful publication or automatic retry.
6. `finalize_disposable_reviews(env, validation_id)` retries native, idempotent approval bookkeeping after a healthy financial commit. It does not reacquire source or rebuild/publish finance.

The environment uses its own native writer/scheduler locks, journal, review queue, run directory, market/taxonomy sources and generation project. Production paths are rejected. Symlink ancestors, file hardlinks, path traversal and unowned directories are rejected. Before native recovery, journal manifest, role, backup, candidate and generation paths are checked against the owned environment; a copied live journal cannot redirect recovery into production.

Snapshot validity, operator review and successful tests each remain separate from publication permission. Every validation receipt records `production_authorized=false`. Journal authorization uses the actual snapshot reference and validation fingerprint with a disposable-only discriminator. Preview/Test identifiers are `None`; no old receipts are fabricated. Existing Preview/Test callers and their authorization contract remain intact.

## Validation and partitioning

Original Phase 1 identity, checkpoint/capture hashes, ARQ/MRQ completeness, source scope, original timestamps and the 168-hour freshness limit remain authoritative. Validation, BUILD and publication use the same captured source. No timestamps are refreshed and missing inputs are never reacquired. Wrong provider identity, corrupt source and incompatible OLD fail before activation.

Native comparison, retained-history/fiscal-revision/true-removal approval matching, historical freeze and accounting-boundary rules are reused. An approval must match the actual incoming evidence and established OLD publication binding. Approval is consumed only after verified publication, through the native finalizer. Review rows alone do not determine blocking status, and mere queue presence grants no permission.

Verified provider rolling expiry preserves the OLD source rows, economic values, provenance and publication dates. Interior/current-window absence remains review evidence; it does not automatically delete rows. The existing three-year historical-review shortcut is disabled when proving source-window retention, as in the corrective contract.

Whole-ticker locality requires positive company/security/provider identity and accepted OLD provider/canonical authority. Shared/foreign evidence and identity collisions prevent isolation; there is no ticker/reason allowlist or count threshold. Ordinary native local holds, generic positive-locality holds and accepted degraded-baseline holds are distinguished from global blockers. The full canonical OLD domain is inspected, including tickers absent from FETCH and the review queue. An unisolatable canonical identity is a global failure.

For a degraded baseline, incoming rows are excluded, the complete accepted canonical state is carried forward in the inactive candidate, and the original missing/broken provenance remains missing/broken. Carry-forward does not repair or attest OLD. Provider/economic/provenance authority is compared before and after BUILD and after publication. The 100-held-ticker test proves that count and acquisition-scope absence do not stop a safe peer.

No safe effective changes produces `NO_CHANGE`, without a candidate build or activation. Global decisions produce `BLOCKED`, and build/publication refuse that partition. Invalid source/authority gates raise their exact errors rather than creating a nominal successful receipt.

## Native candidate and publication

The candidate uses native provider replacement/merge, fresh canonical reconstruction and exactly one normal full V2 package/RP/RV pipeline. Held canonical state is restored immediately after reconciliation, before dates/TTM/analysis. Native freeze and first-public preservation remain active. Scoring, valuation, schemas and production V2-only policy are unchanged.

Publication roles remain exactly provider, canonical and analysis. Market/taxonomy are source dependencies. Each reader resolves one native generation for its operation. BUILD prepares immutable NEW role files without switching the active pointer. PUBLISH checks the exact bytes and native expected-OLD condition before atomic manifest activation; postflight reopens the actual active roles and checks lineage, source history, dates, watermark and held preservation.

Native immutable OLD backups and generation/backup binding checks are reused, including the `9ed344e3` correction. The journal retains the original pre-move candidate-lane paths required by native recovery ownership rules. No alternative transaction engine or recovery database is introduced.

Successful verification reaches `COMPLETED / PASSED / NOT_REQUIRED`. Ordinary failures at preparation, activation and postflight restore exact OLD role bytes, manifest and watermark and report `ROLLED_BACK / RESTORED_AND_VERIFIED`. Crashes at those three workflow boundaries leave an incomplete native journal; recovery restores OLD and requires an explicit fresh retry, including when the source directory has been removed. A healthy completed journal is not replayed. Post-commit queue bookkeeping failure reports `PUBLISHED_WITH_REVIEW_SYNC_PENDING` and never rolls back healthy committed finance.

Per-validation `summary.json` and `operation_report.md` show source identity/root/age, OLD watermark, actual safe/held/global decisions, candidate quarter impact and invocation counts, held preservation and publication/recovery outcome. Hash-bound `decisions.json` contains history events, missing-source evidence and approval bindings; `build.json`, commit/failure receipts and the native journal provide stage details. Source payloads remain in the original Phase 1 capture, rather than being duplicated into control receipts.

## Bounded deviations and unimplemented integration

The current task permits a safely separable disposable scope. The larger architecture is **not fully implemented**:

- Existing UI/service/scheduler routes are not switched or rewritten. The new API is not called from production. Full production operation state-machine/cutover integration and architecture-wide module extraction remain future work. Disposable attempts use existing-style UUID run identifiers with exact snapshot references; architecture-wide monotonic attempt naming and operation-derived generation naming are not implemented here.
- Small owned fixture market/taxonomy sources use the existing `FULL_SQLITE_BACKUP` source mode, bounded to 64 MiB per dependency. This avoids production copies and global taxonomy locks. Production compact/direct source integration is not implemented or performance-qualified. Exact local authority is rechecked at stage boundaries; these small-fixture checks are not a claim of production-scale I/O optimization.
- Phase 1 has no captured supplemental SEC source bundle. The injected offline reader raises `PHASE2_SEC_INPUT_NOT_CAPTURED` if the native publication-date resolver asks for missing SEC input. Native unresolved/PARTIAL handling and existing bootstrap rules remain in force; no synthetic NOT_FOUND result is fabricated. Normal retry horizon **60 days**, retry cap **100 quarters** and resolver semantics are unchanged. A full frozen SEC bundle and its conformance remain unimplemented; required financial evidence must not be bypassed for rollout.
- Automatic separate P/B continuation is not implemented or tested in this backend. Existing P/B code is unchanged. Combined architecture scenario H therefore remains unimplemented, rather than implicitly passed.
- Baseline, ordinary holds and mixed frozen/current changes have dedicated coverage; the complete larger architecture scenario D combining all classes in one run is not tested. Crash tests exercise the three exposed workflow boundaries, not every internal native instruction/activation-intent point. Arbitrary corruption of an active pointer/role file is not newly supported or certified; native recovery preconditions remain unchanged.

These limits prevent claiming complete production Phase 2 readiness. They do not require loosening financial rules or prevent the bounded native disposable publication demonstrated here. Production integration must stop if its required source/date/identity authority cannot be supplied or if native isolation/recovery cannot be retained. No live trial is attempted to resolve these questions.

## Changed files

| File | Purpose |
| --- | --- |
| `rawcandle/fundamentals/admin/refresh_update.py` | Disposable snapshot validation/build/publication/recovery/report integration |
| `rawcandle/fundamentals/admin/review_locality.py` | Reuse archived positive whole-ticker locality; compact incoming fingerprint bound to original snapshot |
| `rawcandle/fundamentals/admin/baseline_carry_forward.py` | Reuse archived full accepted canonical state/degradation checks; inactive-only restore |
| `rawcandle/fundamentals/admin/refresh_copy_runtime.py` | Optional held-state carry-forward hook in native fresh canonical build; default empty for old callers |
| `rawcandle/fundamentals/admin/publication_journal.py` | Optional snapshot authorization metadata discriminator; existing native journal/recovery unchanged |
| `tests/test_fundamentals_snapshot_workflow.py` | Real native SQLite/generation end-to-end and adversarial disposable tests |
| This report and scheduler/history/queue correction report | Scope, actual evidence, limitations and follow-up link |

The two reuse kernels originate from the architecture's archived `temp/fundamentals_baseline_integrity_final_20261111/unqualified_source/` implementation evidence. The whole archived patch is not applied. The locality version is explicitly `FUNDAMENTALS_WHOLE_TICKER_QUARANTINE_V4_SNAPSHOT`; it binds incoming fingerprints without copying raw incoming payloads. No archived runtime database or queue migration is deployed.

## Targeted acceptance

Final Phase 2 integration run: **35 PASS**, 157.49 seconds. Final targeted regression run: **361 PASS**, 258.49 seconds. Total: **396 PASS**, no failures/errors/skips in the final runs. This uses synthetic native SQLite authorities and full native builders, with fake Phase 1 transport only. The complete repository suite is not run.

The regression selection covers native refresh-copy candidates, immutable generations, the backup-binding rejection and representative native crash/rollback regressions, historical freeze, provider capture acceptance, review queue, acquisition snapshots, corrected history/queue semantics, scheduler HOLD, WFRD accounting-boundary review and production-candidate parity. Runs use `PYTHONPATH=.:/tmp`, `PYTHONDONTWRITEBYTECODE=1`, `venv/bin/python -m pytest -q -p no:cacheprovider -p phase2_network_guard`, task-owned `--basetemp` roots and separate retained JUnit XML. One earlier overlapping regression attempt suffered a fixture setup error (`sqlite3.OperationalError: unable to open database file`) when its basetemp was reused prematurely. The final 361-case result passes without a source/policy workaround; the setup error is recorded in `final_test_summary.json`.

Material integration invariants exercised:

- Real candidate and coherent native publication/postflight; exact OLD bytes retained, no fabricated Preview/Test authorization.
- Original expiry and raw-body corruption rejection; no hidden source reacquisition.
- Verified 40-quarter rolling advance/expiry, frozen OLD values/dates and new current quarter; interior removal local hold plus successful safe-peer publication.
- Full OLD-domain degraded holds for one acquired ticker and 100 tickers outside FETCH/queue, including exact economic fingerprints and still-broken provenance after publication.
- Native ordinary quarantine; shared accepted-source identity and foreign incoming identity fail closed; unapproved changes excluded and exact native approval finalized only after commit.
- Original legacy extended queue evidence readable without migration or approval-by-presence; repeated NO_CHANGE has no build; a candidate is built only once.
- Market/queue/code/source-age/candidate/read-copy drift and decision tampering reject stale authority; explicit disposable confirmation required.
- Ordinary rollback and interrupted-journal recovery at all three exposed boundaries, with snapshot unavailable during recovery; healthy completed journal not replayed; post-commit bookkeeping failure stays a committed financial outcome.
- Disposable path/ownership/symlink/hardlink/traversal gates and foreign journal recovery paths rejected.

Both final runs install a task-owned autouse socket guard that fails on any attempted outgoing socket, even if application code catches its exception. Phase 1 fixtures use injected fake native responses. Subsequent source and SEC entry points are denied. Actual Sharadar HTTP calls and outbound attempts: **0**. No full repository suite is invoked.

## Protected production state

Read-only pre/post audit interval: `2026-11-12T16:03:24.025014+00:00` to `2026-11-12T16:36:36.801492+00:00`, including the completed final regression run. All nine protected files have identical sizes and SHA-256 values. Active role bytes also match native manifest verification. No production copies, locks, journal recovery, refresh, queue writes or publication are performed.

Active generation remains `current_rebuild_2a684ef130c6a540de4adc560ab171ad`. Published watermark remains `2026-10-28`, query start `2026-10-25`. Journal remains `COMPLETED / PASSED / NOT_REQUIRED`. All 581 existing review rows decode read-only (579 OPEN, 2 RESOLVED); these are observed counts, not forced targets. Scheduler typed configuration remains `fundamentals_refresh_preview_enabled=false`, mode `FULL_WORKFLOW`. All other jobs/configuration are unchanged.

| Protected file | Bytes | SHA-256 before = after |
| --- | ---: | --- |
| Active manifest | 1387 | `82afaa462cc12ef41616c10d3ad011bac266b452cca02e6abea605c8d5b97097` |
| Active analysis role | 912351232 | `6feb14748b4088096d96287d7f3b1c812faed4dc8e2352a81b390d8b86d11d8f` |
| Active provider role | 968331264 | `14a032489577c079607e16986380076986ab8206ed1d96aa135700499432de4f` |
| Active canonical role | 749371392 | `2178d467a12a601e9554353fea8a3f8354444cb9347be000c3dca6c13b3e0a6d` |
| Publication journal | 589170 | `91fadb71f55be7bad2107db8948744abb17a1a7494bfb3d64d78fe2d155c1e72` |
| Taxonomy `data/analysis.db` | 14288310272 | `8573ce35ca06ad1ddde3c145e067971b09ca5b05f5d71f9d38572d9f0f476f10` |
| Market `data/osakedata.db` | 2039455744 | `bbf1972608d41022502da1ba3bff29aad24e3aed43ae9c0c6d2a0e1927a4a759` |
| Live review queue | 882065408 | `913c454dcc93dafa706ab00c42f6a6f921f56cf93b17a59fb2c4187c61ef1355` |
| Scheduler configuration | 1974 | `c9d5e669937e2f47e8c0c5d251122a29ae099dc08a5f76fe85247cfa0a607948` |

Financial acceptance relaxation: **NO**. Production financial writes: **NO**. Active generation/watermark/queue/scheduler changes: **NO**. Market/StockCore/taxonomy changes: **NO**. Only synthetic phase-owned fixtures are writable.

Local audit JSON, JUnit XML, source acceptance fingerprints and compact retired-fixture reports are retained under `temp/fundamentals_phase2_local_20261112/`, excluded from Git. Synthetic test databases are reproducible and have no production authority. Their owner, purpose, total size, terminal metadata and retirement are recorded in `disposable_retirement.json`. Unrelated runtime state, earlier task archives, OHLCV work and the pre-existing untracked rollout report are preserved and excluded from the commit.

After final acceptance, all eight task-owned `/tmp/fundamentals-phase2-{initial,material,material2,baseline,approval,final-scenarios,acceptance,regression}` roots were retired: **3,023,635,436 bytes**, including **842,047,793 bytes** in synthetic `.db` files. Zero of these roots remain. Purpose: native deterministic build/publication/recovery testing; owner: this task; retention condition: until final acceptance and compact evidence capture; retirement condition: tests accepted and no remaining recovery dependency. Example native full source copies were 77,824-byte market and 20,480-byte taxonomy fixtures, not copies of live databases. Marker identities, source/validation references, candidate role verification, build counts, dependency-copy sizes and journal outcomes were recorded before deletion. XML and compact human-readable reports remain; raw synthetic payloads, databases and backups have no ongoing evidence/recovery role.

## Next operator decision

Review this bounded disposable backend and the explicit unimplemented integration items before commissioning the remaining production-capable source/UI/P/B integration. A separately authorized controlled live UPDATE requires a fresh current baseline and proper update operation, not an ACQUIRE_ONLY snapshot relabeled as production permission. Scheduler reactivation requires separate explicit authorization after accepted live behavior. This task performs neither action and does not push.

## Subsequent Phase 3B integration

The [Phase 3B snapshot integration report](fundamentals_phase3b_snapshot_integration_2026-11-12.md) records the subsequent default-off production adapter, common service/scheduler routing, persistent SEC capture/replay, native production-source integration, reporting and separate ownership continuation. Its tests extend the shared kernels above; the original Phase 2 acceptance remains historical. Effective production selection remains LEGACY and nightly Fundamentals remains on HOLD. No live rollout is implied by either report.

## Subsequent Phase 3D FIX2 source exclusion

[FIX2](fundamentals_phase3d_fix2_acquisition_quarantine_2026-11-13.md) adds explicit
`LOCAL_ACQUISITION_QUARANTINE` input to these kernels for bound `UPDATE_FETCH`
snapshots. VALIDATE excludes both incoming dimensions before reading their
financial source, verifies the native identity, and binds the exclusion through
the existing local-held/carry-forward authority. BUILD and publication retain
whole-ticker OLD, including existing degraded-baseline restrictions. Financial
review rows and approvals remain unchanged for acquisition quarantines; normal
safe financial decisions retain the original approval rules. Missing source is
never deletion authority or complete history. Original acquisition-only
acceptance and all global financial gates remain unchanged. This follow-up
records isolated implementation/tests, not live UPDATE or publication authority.
