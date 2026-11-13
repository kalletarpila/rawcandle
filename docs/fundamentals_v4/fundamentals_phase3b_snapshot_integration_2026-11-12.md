# Fundamentals Phase 3B — default-off snapshot UPDATE integration

[FIX5](fundamentals_phase3d_fix5_representatives_actual_history_2026-11-13.md)
checks actual OLD historical analysis across inactive/missing owners, including
owners outside the discovery/retention plan. Empty history permits BUILD;
unsupported accepted history stops. Historical economic-key coverage is checked
after BUILD and after native publication postflight. This grants no financial
representative selection or production operation permission.

Later [FIX4](fundamentals_phase3d_fix4_identity_retention_2026-11-13.md) permits
retention of already accepted, reviewed new-company OLD with a null provider ID
only through an exact immutable-generation/approval/ownership proof. Incoming
identity rules, installed membership, financial review and publication permission
remain unchanged. Approved historical admission is not a replayable current
identity mutation. Production authority reconciliation and the inactive-analysis
history STOP still require the separate resolutions documented there.

Current scope correction: [Phase 3D FIX3](fundamentals_phase3d_fix3_refresh_universe_2026-11-13.md).
New snapshot Refresh UPDATEs require a pinned installed Phase 13B universe;
raw discoveries, financial reviews and accounting obligations grant no admission.
OLD retention remains separate from incoming eligibility. Ambiguous admitted
identities and internally contradictory membership STOP. The installed CYCN/KRSA
company/security contradiction currently prevents a new production UPDATE.
The native inactive-company analysis-history limitation also remains a STOP
boundary when retained OLD analysis exists. These are unresolved operational
boundaries, not a rollout acceptance or permission to resume the sealed UPDATE.

Subsequent acquisition contract: [Phase 3D FIX2 ticker-local acquisition quarantine](fundamentals_phase3d_fix2_acquisition_quarantine_2026-11-13.md).
For `UPDATE_FETCH`, an isolated source failure now has a separately evidenced,
whole-ticker exclusion outcome. Every slot still requires an actual verified
capture or a durable rejected-response disposition; an unattempted counterpart
cannot be inferred. Safe peers use these same financial/publication kernels;
quarantined incoming ARQ/MRQ is inaccessible to financial consumers and OLD is
retained. Source quarantines grant no financial approval and do not change
existing review rows. Shared contract failures still STOP, credential limits
PAUSE, and sealing requires an intact nonquarantined ARQ/MRQ peer. The original
Phase 3B acceptance and rollout state below are historical observations.

Implemented the production-capable snapshot route around the accepted Phase 2 financial kernels. **The effective route remains LEGACY, nightly Fundamentals remains disabled, and no live acquisition or financial operation is performed.** Code availability, route selection, UPDATE intent, review approval, candidate readiness and publication confirmation are separate facts.

Starting HEAD: `bf407833b2f39a210f7c628db85bca06bddf54e4`. Governing evidence: [Phase 2 acceptance](fundamentals_phase2_local_validation_publication_2026-11-12.md), [scheduler/history/queue correction](fundamentals_scheduler_hold_history_queue_correction_2026-11-12.md), [accepted simplification architecture](fundamentals_simplification_v1_architecture_2026-11-11.md), and the Phase 3A audit supplied in conversation. No repository Phase 3A report was assumed or created.

## Actual route and operator entry points

`StockUpdateSchedulerConfig.fundamentals_refresh_route` accepts exactly `LEGACY` and `SNAPSHOT_V1`; absent configuration means `LEGACY`. No local configuration file is rewritten. `FundamentalsAdminUIService.selected_refresh_route()` is the common selection boundary for manual Full Workflow, Preview, Test on copies and Production update. The scheduler passes its selected route to that same service. There is no failure fallback to the legacy engine.

The existing scheduler chain remains `runner.run_scheduler_config` → `_run_fundamentals_refresh_preview_post_step` → `refresh_scheduler.run_scheduler_refresh_discovery` → `FundamentalsAdminUIService.full_workflow`. Legacy selection retains its existing execution and `full_workflow.run_refresh_full_workflow`. Snapshot selection calls `SnapshotWorkflow` and the shared Phase 2/native kernels instead of nesting the old three-pass financial execution. Legacy source and shared exports are retained.

Snapshot Full Workflow defaults to FETCH/VALIDATE/one BUILD and **CANDIDATE_READY**, without activation. Publication requires explicit `snapshot_publish_confirmed=True` for the UPDATE invocation/resume, or the existing Production confirmation action bound to the exact `local_…` validation/candidate ID. The scheduler API has the same explicit per-invocation argument, default false. The normal scheduler runner does not silently supply this new publication intent. Selecting a route or retaining FULL_WORKFLOW configuration alone grants no publication permission.

Existing Preview opens a named UPDATE and classifies locally; it cannot start a hidden acquisition. Test on copies builds/reuses that operation's one real inactive candidate. Production update requires the exact current candidate reference and the existing confirmation token. Old `refresh_preview.json`/COPY_ONLY_APPLY artifacts do not become snapshot authority, and new UPDATE artifacts cannot be submitted as old receipts. Native journal Preview/Test IDs remain `None` for the new contract.

Preview/Test require a completed sealed FETCH bundle; they cannot resume missing SEC/source acquisition. The existing Preview control passes the selected UPDATE identity through its real request reference. Explicit local retry also rejects an unsealed FETCH. Local-only NO_CHANGE validation/build never invokes ownership publication: its independently authorized safe-no-op continuation belongs only to the Full Workflow completion path. Failed/stale results clear publication-readiness controls.

The existing UI receives normal `run_id/outcome/mode/stages` projections, real candidate references and readiness controls. Its Full Workflow button resumes a paused snapshot UPDATE with the same identity; it does not start a replacement FETCH implicitly. Detailed stage names and the existing operator terminology are mapped truthfully: FETCH; Preview/local VALIDATE; Test on copies/one BUILD; Production update/PUBLISH and VERIFY. No broad UI redesign is included.

## UPDATE/source/approval binding

`SnapshotWorkflow.start` creates an immutable `update_request.json` with contract `FUNDAMENTALS_SNAPSHOT_UPDATE_V1`, explicit UPDATE intent, trigger, FULL_WORKFLOW mode, effective relevant configuration, as-of/source day, policy, exact OLD authority, source operation ID and independent ownership intent. Local validation attempts are linked in order. NEW generation names include the UPDATE ID and validation-attempt identity.

The acquisition foundation now also supports the explicit `UPDATE_FETCH` profile bound to that exact request. Existing acquisition-only calls still write `ACQUISITION_ONLY` and `publication_authorized=false`. A previously sealed acquisition-only snapshot is rejected by the UPDATE adapter. A source snapshot remains acquisition evidence, not publication authorization.

Discovery reuses native ARQ/MRQ overlap/limit/partition logic and the union of changed tickers, pending financial reviews and accounting-boundary queue/installed decisions. Complete histories are fetched ticker-serial ARQ then MRQ through the native capture/checkpoint boundary. Rate-limit pauses retain committed slots. Resume uses the same request and original timestamps and does not reacquire completed ARQ slots. Discovery rate limits are reported as FETCH_PAUSED; the native shared credential limiter retains its cooldown authority.

`update_sources.json` seals references to the immutable Sharadar snapshot, discovery digest and persistent SEC manifest. The original 168-hour snapshot checks remain; UPDATE-created time also bounds discovery/operation age conservatively. No local retry refreshes original timestamps. An OLD/source/configuration/approval/code/dependency drift invalidates the corresponding authority. Rebase is never an implicit replacement of OLD: a new explicitly bound UPDATE is required when OLD changes.

Validation reuses native financial comparison, review approval matching, freeze, rolling retention, WFRD and positive locality/carry-forward. The full OLD domain remains protected, including names outside FETCH/queue. Incoming held data is excluded. Exact retained-history approval is consumed only after a verified commit. The native OLD publication-date prerequisite from legacy Preview is explicitly retained: missing/unapproved historical bootstrap dates or required repairs stop routine UPDATE rather than being filled merely to pass BUILD.

Financial queue binding deliberately treats an absent financial table and an empty financial table as the same empty review material. Native ownership synchronization can create those empty tables during BUILD; that does not invent a financial approval or invalidate an otherwise identical receipt. Existing nonempty financial rows remain decoded and fingerprint-bound; unrelated ownership tables confer no financial authority.

## Native production environment and financial transaction

`SnapshotEnvironment` provides either exact native live paths or a checked Phase 2-owned copy environment. Live role/run/queue/journal paths have no arbitrary caller overrides. Copy ownership, symlink/hardlink/path checks and journal recovery scope checks remain enforced. Financial and ownership publication use the same native project manifest, journal and lock domain in the production-like copy.

The adapter uses native production/scheduler ownership, SQLite sidecar checks and storage preflight. The snapshot scheduler holds its real scheduler lease across its job, and acquires the financial writer only for local financial stages. A native process-context ownership check permits those stages to reuse that already-held scheduler lease without holding a financial writer during FETCH. Taxonomy is acquired after financial ownership and is not held over network requests or cooldowns. Legacy scheduler lock behavior is unchanged.

BUILD uses existing `prepare_compact_read_only_sources` and `protected_direct_taxonomy_source`. The former creates the native compact market bundle; taxonomy remains the protected direct source. Taxonomy protection remains held through each consumer lifetime, including financial postflight. Dependency identity and semantic taxonomy binding are rechecked. The disposable-only 64 MiB source-copy restriction remains on the old disposable helper, not on the production adapter. Financial market/taxonomy are never additional publication/rollback roles.

There is one native provider build, one fresh canonical reconstruction and one full V2/package/RP/RV financial build per local attempt. The existing candidate is prepared once without activation. Publishing checks the exact receipt/candidate/source/OLD/config/code/queue/dependency bindings and explicit confirmation; then reuses native OLD byte backups, backup-manifest binding, PREPARED/activation intent, expected-OLD atomic activation and `_postflight`. No alternative transaction or approval engine is introduced.

Successful finance reaches native COMPLETED/PASSED/NOT_REQUIRED before financial review finalization. Ordinary failure uses native full OLD restoration and ROLLED_BACK. Interrupted preparation/activation/postflight uses native source-independent OLD recovery and returns RETRY_REQUIRED; healthy completed finance is not replayed. Missing original source blocks republishing, not native OLD restoration. A durable financial commit remains committed when review synchronization or ownership continuation fails. `finalize_reviews` / `finalize_snapshot_reviews` provide explicit local review-bookkeeping retry without source acquisition.

## Persistent SEC capture and native replay

`sec_snapshot.py` records the exact submission/primary/exhibit response bytes requested by the existing SecClient, with URL, original acquisition timestamp, SHA-256 and explicit failure records. Bodies are separate content-addressed children, not embedded in parent reports. An operation/snapshot-bound atomic manifest seals the bundle. Interrupted capture retains/checks its pending index and reuses original verified bytes/timestamps. Its original budget start is checkpointed too: resume cannot reset the 300-second HTTP allowance, and elapsed budget produces explicit unresolved input without another request. There is no new crawler or generalized document service.

Planning uses a conservative superset of incoming NEW fiscal identities and the native OLD recent retry scope; accounting-boundary cases may require a wider source-period superset. Actual candidate enrichment retains the existing new-quarter/retry selector. Before preparing NEW, the adapter verifies actual CIK/period scope is covered by the captured plan. Uncovered planning scope stops with `UPDATE_SEC_SCOPE_NOT_CAPTURED`.

Offline replay subclasses the real SecClient and changes only URL byte access. It therefore retains native submissions parsing, archived metadata, primary/exhibit handling, date filters and resolver semantics. Missing/failed captured requests raise an explicit local error; no HTTP fallback is possible. Captured bytes/manifests are verified before use. Normal authority retry remains **60 days / 100 retry quarters**, with the existing **300-second** SEC client budget; new-quarter scope is not replaced by backlog cleanup. Independent publication/backlog workflows are unchanged.

Fixture acceptance compares native resolver outputs from original fixture inputs with durable offline replay for success, missing primary document and missing exhibit. Actual candidate publication verifies accepted evidence/timestamp binding for a new 2026-Q3 quarter and the explicitly UNRESOLVED/PARTIAL result for its missing primary document.

Native policy does not require every SEC enrichment to become VERIFIED before publishing finance whose canonical date prerequisites are already satisfied. That behavior is preserved: PARTIAL is reported, not presented as independent verified date authority. Established first-public dates are not replaced; new dates use the unchanged accepted native canonical policy. The missing-document fixture has no fabricated SEC authority timestamp. Changing this into a blanket VERIFIED requirement would be a separate policy change; no such change is made. Mandatory missing OLD first-public-date prerequisites are separately rejected by the native gate above.

## Separate P/B ownership continuation

The existing enabled ownership configuration is preserved. Successful financial VERIFY and completed review finalization permit the independently authorized ownership intent to invoke native `FutureOwnershipWorkflow` and `OwnershipPublicationWorkflow`. Their source is the actual committed generation, not incoming held rows or an earlier candidate prediction. Native ownership Preview/Test/publication/recovery/cleanup rules remain intact. The ownership transaction can legitimately activate a second, separately identified generation; it is not counted as another financial build or activation.

For NO_CHANGE, independent ownership intent, complete safe local classification, unchanged OLD/source bindings and native ownership source/journal gates are required. NO_CHANGE's display label alone grants no permission. Disabled intent performs no ownership work. Completed ownership is linked durably and not replayed for the same UPDATE; retry attempts retain separate native artifact directories.

Acceptance includes an actual full financial build/activation/postflight followed by a real native automatic ownership copy test and publication on the newly committed financial source. A separate injected ownership failure proves financial completion/generation are retained; existing native ownership continuation/idempotency is also exercised. P/B remains reporting-only, outside Valuation Score. Quarterly accepted economic units, provider observation dates, historical slots, provider P/B versus calculated P/B and native ordinary/ADS eligibility are unchanged. No daily-share requirement, calculation/schema change or terminal-decision reopening is introduced.

The native ownership copy-test mechanism still makes its established full source copies. That mechanism is not redesigned in this phase; all copies made here contain small synthetic fixtures. Production-scale resource/live acceptance is not claimed.

## Source/test/documentation inventory

| File | Change |
| --- | --- |
| `admin/snapshot_workflow.py` | One UPDATE coordinator, source planning/binding, progress/report projection, explicit publication and separate ownership linkage |
| `admin/snapshot_environment.py` | Exact native production/owned-copy paths, locks, dependencies, date prerequisites and publication authorization adapter |
| `admin/sec_snapshot.py` | Bounded persistent raw SEC capture, interrupted capture and native offline replay |
| `admin/refresh_update.py` | Shared Phase 2 kernel hooks; one common publication implementation, source hooks and truthful mutation metadata |
| `admin/acquisition_snapshot.py` | Explicit bound UPDATE_FETCH profile, zero-slot UPDATE no-op and compact progress callback; acquisition-only compatibility |
| `admin/ui_service.py` | One route selector across actions, exact candidate-reference confirmation, result projection and review retry API |
| `admin/refresh_scheduler.py` | Shared route invocation, explicit per-call publication intent and truthful snapshot outcomes |
| `admin/production_transaction.py`, `scheduler/runner.py` | Existing scheduler lease reuse for local stages; no financial writer across snapshot FETCH |
| `scheduler/config.py` | Strict default-LEGACY route setting; no effective configuration mutation |
| `dev_tools/fundamentals_admin_page.py` | Reuse existing controls/readiness and resume the same paused UPDATE |
| Two `test_fundamentals_snapshot_*integration.py` modules | Native SQLite/SEC/routing/approval/quarantine/publication/recovery/P/B/UI acceptance |
| This report and Phase 2 follow-up link | Exact scope, acceptance and rollout boundary |

Paths prefixed `admin/` are under `rawcandle/fundamentals/`; `scheduler/` is under `rawcandle/`. No financial model/schema, source taxonomy, market/StockCore, P/B calculation, legacy workflow removal or authority-backlog change is included.

## Tests, protected state and retention

**354 distinct targeted test cases PASS.** Accepted runs have zero failures/errors/skips:

| Accepted run | Cases | Evidence |
| --- | ---: | --- |
| Primary new integration | 37 | `acceptance.xml`, 191.94 seconds |
| Additional integrated global blocker | 1 | `global.xml`, 9.64 seconds |
| Targeted existing/Phase 2 regressions | 310 | `regression.xml`, 292.69 seconds |
| NO_CHANGE/local-stage authority checks | 6 | `stage_authority.xml`, 21.70 seconds; includes two additional cases and affected-case rechecks |
| Final adapter/local-control/native financial→ownership checks | 8 | `boundary_accepted.xml`, 22.20 seconds; includes three additional cases and affected-case rechecks |
| Existing Admin UI after the final control changes | 59 | `ui_final.xml`, 95.83 seconds; rechecks cases already in the regression selection |
| Final SEC budget/replay/native financial→ownership checks | 8 | `sec_budget_final.xml`, 20.72 seconds; includes one additional interrupted-budget case and affected-case rechecks |

Repeated cases are counted once in the 354-case total. The final boundary refinements were validated with focused affected-case runs, rather than repeating the full regression selection. XML and `final_test_summary.json` retain exact case identities and results. Intermediate fixture/adapter failures were corrected; notable integration corrections were the empty-financial-queue normalization and preserving the committed financial outcome when ownership reporting fails. No financial policy or native resolver workaround was used to make tests pass.

Coverage includes default legacy selection; shared manual/scheduler routing and explicit publication intent; sealed UPDATE versus acquisition-only identity; 168-hour expiry and source/code/queue/config/OLD/market drift; no refetch after seal; rolling/frozen OLD preservation; ordinary and 100 degraded local holds; a non-isolatable shared baseline blocker; exact native review approval and post-commit finalization; coherent one-build/one-financial-activation publication; ordinary rollback and crashes at preparation/activation/postflight with missing source; native SEC resolver/authority equivalence and explicit partial outcomes; same-UPDATE pause/resume without duplicate completed ARQ; actual financial→native ownership publication; ownership failure/idempotency; local-only NO_CHANGE without ownership side effects; exact phase-control candidate references, UI resume/local Preview, native scheduler HOLD and existing UI/history behavior.

The 310-case regression selection covers Phase 2 financial publication, acquisition, history/queue correction, Admin UI, existing financial Full Workflow, scheduler Full Workflow/configuration/HOLD, native production transaction, compact/direct source bundle, existing ownership continuation and native publication authority. No complete repository suite is run. Crash coverage exercises the three exposed workflow boundaries; arbitrary corrupt active-pointer/role repair and every internal instruction-level crash point are not newly certified.

Tests use deterministic fake transport through native capture, real disposable SQLite/generations and native builders/postflight/recovery. A task-owned autouse outgoing-socket guard fails even if application code catches a forbidden connection attempt. Fixture transport-attempt ledger counters describe injected responses, not real server calls. **Actual Sharadar HTTP: 0; actual SEC HTTP: 0; outbound connection attempts: 0.**

Fresh read-only pre/post evidence covers all nine protected live files: three active financial roles, active manifest, journal, live review queue, scheduler configuration, market and taxonomy. The task-owned JSON/XML/compact fixture metadata is retained only under `temp/fundamentals_phase3b_20261112/`, excluded from Git. Test roots are retired only after final acceptance and compact evidence capture; no active/shared/unresolved production recovery evidence is deleted.

Audit interval: `2026-11-12T17:07:28.285525+00:00` → `2026-11-12T18:02:06.246869+00:00`, covering all final tests. Every protected file's size/SHA-256 is identical, and active role hashes also match native manifest verification:

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

Active generation remains `current_rebuild_2a684ef130c6a540de4adc560ab171ad`; watermark `2026-10-28`, query start `2026-10-25`; journal COMPLETED/PASSED/NOT_REQUIRED. Typed configuration confirms route LEGACY, Fundamentals enabled false, mode FULL_WORKFLOW and ownership continuation true. Other nightly configuration is byte-identical. Production financial DB writes, live queue writes, active-generation/watermark changes, scheduler changes and policy relaxation: **NO**.

All **16** phase-owned `/tmp/fundamentals-phase3b-*` test roots listed in `disposable_retirement.json` were retired after acceptance: **3,126,983,326 bytes**, including **912,924,674 bytes** of synthetic `.db` files. Owner: this task. Purpose: native deterministic production-like financial/SEC/ownership/routing acceptance and regressions. Retention: until accepted checks and compact evidence capture. Retirement: no remaining live/shared recovery dependency; source tests regenerate these synthetic fixtures. Compact UPDATE reports, request/source references, journal terminal states, candidate verification, build counts and dependency-copy metadata were retained before deletion. None of those 16 roots remain. Unrelated earlier archives, live generations/journal, untracked prior rollout report and OHLCV/research work are preserved and excluded from the commit.

## Remaining operational boundary

This is implementation and disposable acceptance, not live conformance or rollout. Phase 3C must separately authorize a fresh current UPDATE/FETCH/publication, inspect current native runtime/recovery/source/approval/resource state, and accept its actual outcome. The prior acquisition-only snapshots cannot serve as that production grant. The ordinary scheduler runner intentionally supplies no new standing snapshot publication permission; unattended publication intent and scheduler reactivation require separate explicit authorization. Nightly Fundamentals remains on HOLD throughout this task.
