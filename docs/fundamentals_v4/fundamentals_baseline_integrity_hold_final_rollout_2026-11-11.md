# Fundamentals baseline-integrity hold final rollout — 2026-11-11

Status: **STOP — shared authenticated source HTTP 429**. Targeted/disposable and pre-live candidate UI acceptance PASS. One fresh live workflow was interrupted during Preview; Test and Production were not entered. Candidate source is archived and removed from the active checkout. This is a STOP report, not a successful rollout.

## Fresh authoritative baseline

The fresh audit at 2026-11-11T16:05:44Z acquired the native admin operation, production and scheduler locks. Active generation: `current_rebuild_2a684ef130c6a540de4adc560ab171ad`. All three immutable roles passed SQLite verification and matched the active manifest. Journal: `COMPLETED`; postflight: `PASSED`; recovery: `NOT_REQUIRED`. No recovery was invoked.

Provider/canonical/analysis SHA-256:

- `14a032489577c079607e16986380076986ab8206ed1d96aa135700499432de4f`
- `2178d467a12a601e9554353fea8a3f8354444cb9347be000c3dca6c13b3e0a6d`
- `6feb14748b4088096d96287d7f3b1c812faed4dc8e2352a81b390d8b86d11d8f`

Manifest SHA-256: `82afaa462cc12ef41616c10d3ad011bac266b452cca02e6abea605c8d5b97097`. Journal SHA-256: `91fadb71f55be7bad2107db8948744abb17a1a7494bfb3d64d78fe2d155c1e72`. Provider watermark: `2026-10-28`, overlap query start `2026-10-25`, established by successful run `20261029T054405Z_refresh_fundamentals_4c3b99953d00_production_a7f5b976`.

Latest completed scheduler receipt remains `stock_update_scheduler_summary_20261111T044713Z.json`, finished `2026-11-11T08:13:15Z`. Its parent `20261111T072655Z_refresh_fundamentals_d00eb7239fed_full_workflow_d07cf1a4` stopped at Preview with 1,170 effective safe changes, 406 local holds and 19 globals (425 review cases) under the then-deployed policy. Native Preview child: `20261111T072655Z_refresh_fundamentals_8d7ad5f72900`. Neither Test nor Production was invoked.

The later, separately stopped manual workflow has a completed authoritative Preview child `20261111T122146Z_refresh_fundamentals_8d7ad5f72900`, but no successful Test or Production. A fresh read of that child's evidence finds 1,170 effective safe changes, 408 ordinary local holds, 171 baseline-integrity holds and no data-derived globals. These historical artifacts remain unchanged and do not authorize this task's live publication.

The complete current canonical/provider relationship scan finds 171 degraded-baseline tickers. Queue: 579 OPEN, two RESOLVED; provider-review audit: 1,632 rows. Current preserved-history projection: N=559, M=559 using the latest completed Preview. WFRD boundary and all 13 P/B ownership rows have unchanged digests relative to the accepted performance task. Before qualification, nine protected runtime files and both unrelated market/taxonomy source databases were hashed for collateral comparison.

## Archived implementation and prerequisite compatibility

Source HEAD at start: `abce59ad8ecf63acd5940642b03f837129aab1d4`. Both this compact parent-evidence commit and recovery commit `9ed344e397fde8912eba5b0ebf38f285e7d4751d` are verified ancestors.

The prior rollout report identifies the archive as `temp/fundamentals_baseline_integrity_hold_20261111/implementation.patch`, SHA-256 `d96975901b5dd818faaa4f52612b7300ff83d9d0f8664a745bc6a64286ede5cf`. All 23 archived source/test snapshots matched their frozen inventory. Only `full_workflow.py` and `ui_service.py` had intervening changes among those paths. Their archive additions are a small financial Preview metadata sidecar and a read-only preserved-history service method. The patch's functionality was reconciled on current HEAD without replacing either current module.

Restored source inventory: admin page; scheduler UI CSV route; Full Workflow metadata; Refresh Preview, copy runtime, operational decision, Production and review queue; review presentation; UI service; and the three new modules `baseline_carry_forward`, `review_locality`, `preserved_history_presentation`. Direct tests cover baseline carry-forward, locality, preserved history, native Refresh copies/publication, historical freeze, operational presentation, P/B publication and WFRD.

The compact parent's control state, verified child RESULT/SUMMARY/PREVIEW/REPORT references, status/manifest validation, exact Preview/Test binding, bounded history readers and exact full-scope P/B no-op metadata remain in place. No old inline child-result reader or repeated parent evidence embedding was restored. Native three-role publication, backup binding and recovery implementation remain unchanged.

## Financial and operational semantics

Quarantine requires positive whole-ticker identity, source scope, disjoint partition and accepted baseline proof. Unknown review shapes are evaluated without ticker exceptions or a finite review-reason allowlist. Existing approval contracts stay separate from exclusion authority. Shared failures, foreign identities, invalid immutable roles, unsafe recovery, collisions and inconsistent partitions fail globally.

`LOCAL_BASELINE_INTEGRITY_HOLD` excludes all incoming evidence for an isolated ticker whose accepted canonical authority is valid but whose old provider lineage is incomplete. The active immutable generation authorizes carry-forward only. It does not validate or repair the broken provenance. Every canonical financial/provenance/parent-equity row is carried through the inactive full rebuild with permitted physical-ID remapping. Full OLD/candidate authority fingerprints must match before publication and again after enrichment. Provider replacement must exactly equal the authorized safe set.

The complete canonical domain is scanned independently of discovery, watermark and queue membership. Degraded identities outside discovery are added to reevaluation. Durable queue/audit evidence retains generation, canonical fingerprint, missing references, incoming source context and repair guidance. Pending cases remain reevaluable after safe-peer watermark advancement. No provider observations or lineage repairs are manufactured, and no new persistent store is added.

Historical financial freeze, complete provider payload/capture acceptance, WFRD boundary decisions, first-public dates and P/B ownership policy retain their governing contracts. P/B continuation consumes only active published financial state through the native continuation path.

Pure passive frozen-history rows are hidden only from normal presentation; mixed/actionable, capture, fiscal, baseline, approval and unknown actionable cases stay visible. Explicit historical evidence remains accessible. The shared pure aggregation deduplicates N/M and CSV by ticker. The on-demand UTF-8 CSV route `/fundamentals/admin/preserved-history.csv` quotes fields, neutralizes formulas, uses attachment/no-store/nosniff headers and creates no persistent CSV or database.

## Qualification and rollout evidence

Temporary task-owned receipts: `temp/fundamentals_baseline_integrity_final_20261111/`. They are excluded from commits. Runtime state, unrelated OHLCV/StockCore files and the previous STOP report are also excluded.

The combined implementation's fresh synthetic 2 GiB/100-update benchmark passes: 9,573.98 bytes written per event, 4,621-byte largest parent snapshot during progress, median 0.028424 seconds per event, 1.288273-second Preview-to-Test transition, 2,339,819-byte traced peak allocation, zero child reads during progress/UI. Small-versus-large evidence differs by four bytes per event. This measures parent orchestration, not live provider/financial execution time; hashing at stage boundaries and original native child artifacts remain intentional.

All 1,031 distinct targeted cases PASS, with no failures/errors/skips in the selected final JUnit receipts:

| Batch | PASS |
| --- | ---: |
| Combined baseline/locality/preserved-history/native immutable workflow/compact evidence | 104 |
| Generations, recovery binding, payload completeness/workflow, WFRD, freeze, P/B publication/new quarter | 413 |
| Native UI, operational presentation, history and scheduler | 243 |
| Native 100-hold immutable publication with discovery-absent ticker | 1 |
| Refresh copy/Production/review queue/Preview/orchestration/payload rebaseline | 215 |
| Future P/B workflow and automatic continuation | 55 |

Disposable acceptance A–J PASS: safe peers with ordinary fiscal hold; one baseline hold; 100 baseline holds including a ticker absent from discovery; mixed ordinary/baseline holds; genuine shared/global STOP; native complete OLD rollback; crash recovery requiring retry; financial publication followed by native active-generation P/B continuation; read-only native UI/CSV projection; and 2 GiB compact-parent transitions with exact/tampered artifact binding. The combined financial/P/B fixture has no eligible continuation candidates; separate native eligible P/B publication and idempotency scenarios PASS. No live financial mutation was used for qualification.

At 2026-11-11T16:20:03Z the repeated native-lock audit verified all nine protected runtime files, watermark and WFRD/P/B digests unchanged. The qualification seal pins 34 relevant source/test files. The full test suite has not been run. A fresh guarded live boundary, one native Full Workflow, postflight and actual UI/HTTP acceptance remain required before an implementation commit.


## Guarded live boundary and pre-live UI

The qualified UI was reloaded under native locks with a healthy completed journal; process 1574922 returned HTTP 200. Actual pre-live HTTP CSV and native page-control acceptance PASS: N=559, M=559, CSV=559 unique rows, 349 pure rows hidden normally, 210 mixed/actionable preserved rows visible, 171 baseline holds visible, explicit hidden evidence available, approval authority unchanged. All protected runtime hashes remained unchanged. Native controls and real HTTP were exercised; no browser screenshot was taken.

Fresh preflight rebound all protected runtime hashes, exact qualified source, immutable role verification and native scheduler/production/admin lock availability. The one-live marker was written at `2026-11-11T16:24:24.937242Z`. Parent: `20261111T162424Z_refresh_fundamentals_d00eb7239fed_full_workflow_988506e3`. Preview child: `20261111T162424Z_refresh_fundamentals_8d7ad5f72900`. Preview acquisition was interrupted at the mandatory shared-source STOP below. Test and Production were never authorized or entered. Source and publication authority remain native; the observer wrapper grants no financial authority and will not retry a stopped workflow.


## Mandatory live STOP: shared authenticated source rate limiting

At 1,529/1,810 completed ticker-history response pairs, acquisition slowed. The native client remained alive in I/O/retry handling. A separate read-only unauthenticated schema probe at `2026-11-11T16:53:53Z` returned SUCCESS / HTTP 200 in 0.174 seconds. This did not establish authenticated financial-source availability.

At `2026-11-11T16:54:23Z`, separate native read-only authenticated probes for **STBA and MSFT** both returned **RATE_LIMITED / HTTP 429**, zero records, in 0.157 and 0.498 seconds. This establishes an operation-wide authenticated source availability gate; it is not a ticker-local financial anomaly. No assumption is made about the quota window or reset time. The existing native client's rate-limit/retry policy was not altered or bypassed.

The user-authorized workflow was interrupted with SIGINT after verifying its exact PID, command and working directory. SIGTERM was not needed. The parent durably records `STOPPED`, `interrupted=true`, `production_completed=false`, no completed child stages and completion time `2026-11-11T16:55:15Z`. The native Preview remains historical partial evidence at `PREVIEW_STARTED`, `write_boundary_crossed=false`; its last completed history response pair was STE, 1,531/1,810. It has no completed Preview authorization. No historical artifact was rewritten to claim completion.

No Test child, Production entry, fresh authorized safe/held scope or financial publication was produced. Safe tickers published: **0**. Ordinary held incoming tickers published: **0**. Baseline-integrity held incoming tickers published: **0**. This task's one permitted live attempt is consumed; no second workflow, standalone replacement Preview or retry was started. The last completed older Preview's 1,170/408/171/0 counts were never reused as execution authority.

There is one demonstrated shared operational blocker: authenticated source rate limiting. The unfinished new Preview has no final data-derived blocker count or fresh accepted partition. Current queue population and the complete degraded-baseline population remain those freshly audited before the attempt: 579 OPEN, two RESOLVED, 408 ordinary holds and 171 baseline-integrity holds from the latest completed evidence.

## Parent performance during the stopped live attempt

The parent remained bounded through actual acquisition and interruption: maximum `workflow_result.json` and compatibility `result.json` **1,176 bytes**, progress **367 bytes**. No multi-gigabyte parent serialization regression was observed. No large native child completion artifact or Preview-to-Test transition was reached, so this stopped attempt cannot establish live completed-child transition timing. The combined 2 GiB synthetic and disposable exact-reference acceptance remains PASS.

## Financial, recovery and collateral state after STOP

At `2026-11-11T16:56:34Z`, another native admin/production/scheduler-lock audit verified all nine protected files byte-for-byte equal to the initial baseline. These include OLD provider/canonical/analysis, active manifest, publication journal, review/audit database, scheduler configuration and unrelated market/taxonomy databases. The WFRD boundary and P/B table digests also remain identical.

Active generation before and after: `current_rebuild_2a684ef130c6a540de4adc560ab171ad`. Number of generation activations: **0**. Journal remains `COMPLETED`; postflight `PASSED`; recovery `NOT_REQUIRED`. These are the healthy prior publication's terminal states, not a claim that this stopped workflow published or passed postflight. No recovery was called on the healthy journal, and no new backup/restoration boundary was entered.

Because immutable role bytes are unchanged, every held ticker's full economic, fiscal, parent-equity, source/provenance, first-public-date and degraded-lineage state is unchanged. There is no actual provider replacement set or fresh authorized set to compare in this stopped attempt. Watermark remains `2026-10-28`. All held cases remain durably pending and reevaluable; none was auto-resolved or hidden by watermark advancement. P/B continuation was not entered, terminal ownership cases were not reopened, WFRD authority and boundary semantics are unchanged, and provider payload/capture acceptance was not relaxed.

The OLD/NEW backup-binding and crash-recovery requirements PASS in isolated native qualification. There is no new live generation or live rollback to audit. Runtime collateral mutation: **none**. No queue/audit updates were reverted; this Preview stopped before queue persistence, and the queue itself was byte-identical.

## Recoverable source archive and final deployed state

Live publication and post-live UI acceptance are required before an implementation commit. They did not pass because of the genuine external source boundary. Therefore the candidate implementation is not committed or left in the active scheduler checkout.

Under native locks and a verified healthy immutable generation, the qualified candidate UI was stopped. All 23 reconciled source/test files were copied with hashes to `temp/fundamentals_baseline_integrity_final_20261111/unqualified_source/`. The complete patch against `abce59ad8ecf63acd5940642b03f837129aab1d4` is:

`temp/fundamentals_baseline_integrity_final_20261111/implementation_rebased.patch`

SHA-256: **`913b5c164a6ace12cb740ed97df6a70ac3e0811d39b767b63cd2c87e5e56084b`**.

The archive includes the additional native 100-hold publication test with discovery-absent protection. Seventeen task-owned tracked files were restored to current HEAD; six new task-owned files were removed only after archiving. Reapplication validation PASS. Unrelated worktree files, financial/runtime state, scheduler configuration and the previous baseline STOP report were untouched. Neither governing prerequisite commit was reverted.

The original UI command was restarted on restored accepted source as PID 1582437. Actual HTTP root returned 200. The proposed CSV URL returned Flet HTML (`text/html; charset=utf-8`), confirming that the candidate CSV route and preserved-history UI compaction are **not deployed** in the restored checkout. The current preserved-history projection remains N=559/M=559 because queue and latest completed Preview evidence are unchanged. The earlier actual 559-row CSV and native control acceptance belongs to the qualified candidate before STOP; it must not be described as post-publication or final deployed UI acceptance. No browser screenshot was taken.

## Remaining boundary and commit scope

The 171 degraded published baselines still need separately reviewed provenance repair. This task grants no automatic historical source repair, approval expansion or incoming evidence acceptance. Resuming rollout requires authenticated source availability and a newly authorized fresh live attempt with normal preflight, Preview, Test, revalidation and Production guards; no old or partially acquired evidence grants authorization.

A report-only STOP commit is appropriate under the task's explicit exception. It contains this final report only. Candidate source/tests remain recoverable in temporary evidence. Financial databases, journal, manifest/generations, queue/audit, scheduler config, temporary artifacts, the old report and unrelated OHLCV/StockCore files are excluded. No push is performed.


Final restoration audit at `2026-11-11T16:58:14Z` again acquired all native locks and verified all nine protected files, watermark and special review-state digests equal to the initial baseline. All 17 restored tracked source/test files match accepted HEAD exactly, and all six new candidate files are present only in the hash-verified temporary archive. The remaining worktree changes are the initial runtime/unrelated items plus this report.
