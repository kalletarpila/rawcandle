# P/B.14 — Production ownership workflow operational acceptance

**Operational acceptance: PASS**, 2026-10-08 (Europe/Helsinki). P/B.12 review and P/B.13 controlled publication are available through the normal Fundamentals Admin code path. Enablement required only the existing additive migration of the live operational Review Queue. No source/configuration changes, financial DB writes, fabricated cases, ownership approvals, Production publication or active-generation change occurred.

Implementation HEAD was exactly **18a3604d56cbeae8f64f778462bb051c738044e8**, containing P/B.12 **92e4f94f94ec50167ed67243fe694ec5a439b08c** and P/B.13. Source/test files had no unexpected changes. Previously existing unrelated worktree files and the publication-journal worktree difference were preserved and excluded from this documentation commit.

## Production readiness

| Operational state | Accepted value |
|---|---|
| Active generation | `pb_quarterly_ownership_v2_20261008T080025Z` |
| Active ownership contract | `PB_OWNERSHIP_BASIS_V2` |
| Effective from | `2026-10-08` |
| Supported reviewed scopes | 31: 16 ordinary/common, nine identity overrides, six ADR-factor |
| Review type | `PB_OWNERSHIP_NEW_QUARTER` |
| OPEN / HELD / APPROVED unpublished / PUBLISHED ownership cases | 0 / 0 / 0 / 0 |
| Queue schema | Ready; additive/idempotent migration completed |
| Admin ownership review / publication actions | Available; distinct human decisions |
| Detector / normal refresh queue hook | Integrated |
| Automatic approval / publication | NO / NO |
| Pending action | NONE |
| Production generation publication | Not executed |

The existing Admin launcher `dev_tools/stock_update_scheduler_ui.py` invokes `build_fundamentals_admin_page`; that component exposes the ownership section and calls the production-default service methods. No feature flag or alternate queue/publisher is needed. The publication action appears only on APPROVED cases, with stale/unavailable cases disabled. Zero live cases is the expected ready state.

## Preflight and immutable-generation safety

All three active role hashes matched the active manifest, with **quick_check = ok** and **zero foreign-key errors**. The active contract/pin and V1/V2 bundled artifact hashes matched the committed P/B.11 contract. Publication journal remained **COMPLETED / PASSED**, with no incomplete recovery and writes unblocked.

| Protected file | SHA-256, unchanged throughout acceptance |
|---|---|
| Provider role | `2b3a57add8b51413d98f220d4cdd313994d1a4079f987a94796bf6a2b6db5fbb` |
| Canonical role | `185597dc364c8cd1642d53054af485c5d4f690b49df18d38dbe911b3220fd924` |
| Analysis role | `a8dcc37e1a0e2442dd44023b63d8c6ba91ee5fdce3ab05e2fa5407413a0355ce` |
| Active manifest | `7c103baedea1f7f0808388bec8138dea238951cf9c9ab476e727cf7d07ba0fa8` |
| V1 registry | `0baaf493afa2faa52c2179a2353fb9089d834ef2bcb91f6e088e58f1bae068bf` |
| V2 registry and active pin | `7b7d0cdd9bce7d448b70c7c46af54d3401f4fb0005b4f94f021d29c0e0e460e6` |
| Publication journal | `196c6cf98db2ef02dea6653b95aea15aa0e946f5c473a94a634acf7d702b8191` |
| Scheduler configuration | `3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894` |

Market and taxonomy main/WAL hashes also remained unchanged. Whole analysis-file equality covers Fundamental/Valuation Scores, relative positions, fingerprints/history and unrelated valuation state. Whole canonical-file equality covers parent equity, financial statements, provenance and publication authority. Provider equality and complete P/B report equality independently cover Provider P/B/history.

Existing Admin-operation, Production, scheduler and taxonomy locks were acquired successfully in the normal order. The existing verified-backup directory was tested with an exclusively created empty probe that was fsynced and removed. No generation candidates or generation rollback backups were created. Immutable-generation preparation, atomic activation and restore-OLD recovery APIs are available; their already-tested P/B.13 behavior was not repeated against live data.

## Queue-only additive migration

The existing queue database was accessible at `fundamental_reports/fundamentals_refresh_review_queue.db`, but `pb_ownership_review` was absent. Before migration, all existing schemas, table row counts and ordered-row SHA digests were captured, and a verified queue-only SQLite backup was made under `/tmp/pb14_acceptance/queue_before.db`.

Under existing locks, the approved migration path was the existing `RefreshReviewQueue.sync_ownership` → P/B.12 `sync` → existing queue `_connect` plus ownership `CREATE TABLE IF NOT EXISTS`. Read-only detection first confirmed zero genuine candidates. Both consecutive sync calls returned **candidate_count = 0, created = 0**. The only new table was the empty ownership child table, plus its normal primary-key index. No queue case or migration audit event was fabricated.

| Pre-existing table | Rows before/after | Ordered-row SHA-256 before = after |
|---|---:|---|
| `refresh_review_queue` | 6 / 6 | `f7266ad08dad1487fd812944c1efa48fdd91f091c86082487039f0da046039df` |
| `refresh_review_queue_audit` | 38 / 38 | `3f8d56c3bdf9fc5cc6adcc8ce52b86e357157fb544a5daebdba8ef55aa52dfa0` |
| `sqlite_sequence` | 1 / 1 | `42033a9883a7a9e66e0e8cff013cc4100e569a33471578d965d55bccb56d2f27` |

All pre-existing schema entries were also unchanged. First/second post-migration logical state matched exactly. Queue quick_check passed with zero FK errors. Its physical file hash changes as expected for the additive schema; the CSV distinguishes this from unchanged pre-existing review state. No financial DB or active manifest was used as a migration target.

## Live detector and zero-case Admin smoke

Read-only detection ran across every supported scope. All **31** matched the currently accepted company/security identity, observation ID, content hash, fiscal quarter and report period; there were **zero superseded observations and zero false candidates**. Those results matched the empty live ownership queue.

A fresh instance of the **actual production-default `FundamentalsAdminUIService`**, connected to the live operational queue, loaded the normal Admin component with a headless page adapter. Refreshing both pending and resolved-history views rendered **“No quarterly ownership reviews pending.”** without errors. The queue refresh control returned to its enabled state; approved pending publication count was **0**. Review preview, explicit continuation approval, Keep on hold, publication preview and controlled publication service methods were callable. Standard Refresh Fundamentals Preview/Test/Production capabilities remained enabled.

The actual Production publication-preview service was invoked with **an empty selection only**. It rejected the request with `PB_PUBLICATION_EXPLICIT_UNIQUE_SELECTION_REQUIRED`, without creating a candidate lane or backup set. The publication service without explicit confirmation rejected before any write boundary. Successful-receipt synchronization returned zero and changed no queue rows, since the current journal is the prior P/B.11 publication. The composed zero-case readiness result was:

```text
Approved ownership cases pending publication: 0
Active generation: pb_quarterly_ownership_v2_20261008T080025Z
Publication workflow ready: YES
Action required: NONE
```

No live review approval or valid publication request was submitted. The separate approval/publication dialogs and eligibility-dependent actions were checked with isolated UI smoke fixtures. No approve-all or publish-all action exists.

## Normal-refresh integration and minimum tests

Inspection confirmed the normal copy and Production refresh orchestration pass the operational queue path into `fresh_rebuild_canonical` and `reconcile_canonical`. Ownership detection follows financial acceptance. Queue failures produce diagnostics while accepted financial data remains accepted. Production refresh invokes successful P/B receipt synchronization immediately after its existing recovery guard; it does not import or auto-publish pending approvals.

**10 targeted smoke tests passed**. No source change required a broader regression group, and neither the P/B.13 255-test set nor the full suite was rerun. The selected tests cover empty/missing/corrupt queue UI states, normal Admin Production routing, normal Production-shaped copy orchestration through postflight, copy Preview/Test reconciliation/retained history, diagnostic-only queue failure, explicit ownership approval dialog, separate publication confirmation and absence of automatic activation.

```sh
pytest -q \
  tests/test_fundamentals_admin_ui.py::test_refresh_review_queue_ui_handles_empty_missing_and_corrupt_states \
  tests/test_fundamentals_admin_refresh_production.py::test_ui_service_routes_refresh_production_to_shared_backend \
  tests/test_fundamentals_admin_refresh_production.py::test_production_shaped_rehearsal_commits_only_after_postflight \
  tests/test_fundamentals_pb_new_quarter_review.py::test_queue_failure_does_not_block_financial_acceptance \
  tests/test_fundamentals_pb_new_quarter_review.py::test_admin_ui_explicit_dialog_before_action \
  tests/test_fundamentals_pb_ownership_publication.py::test_approval_and_normal_refresh_never_activate_generation \
  tests/test_fundamentals_pb_ownership_publication.py::test_admin_ui_separate_publication_preview_and_confirmation \
  tests/test_fundamentals_admin_refresh_copy_test.py::test_retention_merge_persists_provenance_rebuilds_canonical_and_stabilizes
```

## Current P/B and data invariance

Complete live P/B reports for the same **2,468-member operational universe**, at **2026-10-08**, matched exactly before/after migration and Admin readiness checks. Every Current/Provider P/B value and reason also matched the committed P/B.11 coverage artifact. No input drift was observed and counts were not forced:

| Metric | Before | After |
|---|---:|---:|
| Operational universe | 2,468 | 2,468 |
| Valid Current P/B | 1,721 | 1,721 |
| Available Provider P/B | 2,133 | 2,133 |
| Complete valid 4Q history | 2,081 | 2,081 |
| Active reviewed releases | 31 | 31 |
| Additional ownership releases | 0 | 0 |

Financial/score state, publication authority, active generation, registry binding and scheduler configuration remained unchanged. Only the operational queue schema was enabled.

## First real new-quarter case: operator procedure

1. Run normal Fundamentals Refresh Preview/Test and its separately confirmed Production refresh to accept the real new quarter.
2. Open Fundamentals Admin → Review Queue and refresh the list; locate `PB_OWNERSHIP_NEW_QUARTER`.
3. Compare prior/new quarter, observation/hash, shares, raw/exact factor, category, parent equity and classification.
4. Open the review preview. For a supported continuation, enter operator/note and explicitly confirm **Approve quarterly ownership continuation**; otherwise choose **Keep on hold**.
5. For the resulting APPROVED case, separately select **Publish approved P/B ownership reviews**.
6. Inspect the current-generation rebase, exact selection/artifact, candidate role hashes, P/B effect and invariance checks.
7. Enter the publishing operator and explicitly confirm Production publication. Regenerate a preview if the source or date has changed.
8. Verify successful postflight, case **PUBLISHED**, and the recorded generation/artifact/approval bindings.
9. Verify Current P/B uses the new accepted quarter's shares and parent equity. Any independent price/equity hard gate remains visible and must be resolved normally.
10. For the unchanged accepted quarter, no daily ownership re-review is needed. Normal price/equity freshness rules and the quarterly-share approximation disclosure continue to apply.

No direct JSON/DB edits are required. A stale/newer-quarter approval is rejected, and normal reconciliation produces the distinct new-quarter case.

## Limits and retained evidence

There is no genuine live ownership case to approve or publish at acceptance. Real first-case activation still requires the operator's separate explicit confirmation. Live readiness used the actual service and UI component with a headless adapter; no browser session or GUI-process restart was performed. A long-running Admin session must load the committed implementation before using the new actions.

Temporary preflight/after state, full comparison reports, queue-only backup and smoke logs remain outside the commit under `/tmp/pb14_acceptance` and `/tmp/pb14_*.log`. The compact [validation CSV](fundamentals_v4_pb_ownership_operational_acceptance.csv) records readiness, protected hashes and queue invariance. This phase commits documentation/compact evidence only; no runtime database, journal, backup, candidate or generated company report is committed. Nothing is pushed.
