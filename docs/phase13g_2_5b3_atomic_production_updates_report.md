# Phase 13G.2.5B3: guarded Administration production updates

## Contract and write sets

| Operation | Written production databases | Read-only authoritative databases |
| --- | --- | --- |
| Add Tickers | `fundamentals_provider.db`, `fundamentals_v4.db`, `fundamentals_analysis.db` | `osakedata.db.ticker_meta`, active `analysis.db.dc_ecosystem` |
| Sector/Industry check/synchronize | `fundamentals_analysis.db` only | `osakedata.db.ticker_meta`, provider/canonical inputs, active `analysis.db.dc_ecosystem` |
| Taxonomy rebuild | `fundamentals_analysis.db` only | active `analysis.db.dc_ecosystem`, provider/canonical inputs, `osakedata.db.ticker_meta` |

The separate Sector/Industry program owns edits to `ticker_meta`. Fundamentals Administration has no classification editor and never writes that table. The separate taxonomy program owns CSV validation and activation. Fundamentals Administration accepts no taxonomy CSV and never writes `analysis.db`.

Add Tickers writes company/security identities and plan evidence in the canonical DB, stages provider rows in the provider DB, and reconciles canonical fundamentals, TTM, and structural-break state. It does not write market or taxonomy DBs. Obsolete copied-analysis classification patching and RP V1 refresh are not in the active production route.

## Transaction boundary

1. Validate the saved Preview fingerprint, operation-specific source state, explicit as-of date, active taxonomy semantic identity, and matching successful `COPY_ONLY_APPLY` result with one full V2 rebuild. True no-change returns before locking, backup, or rebuild.
2. Require explicit production intent and exact production paths. A rehearsal must use only copies. Actual production additionally requires a clean Git worktree.
3. Acquire the exclusive Administration `flock` and the existing scheduler `flock`; keep both through postflight or rollback. Lock owner PID/time/log directory are recorded. A stale lock file alone has no authority.
4. Revalidate Preview, fingerprint all source DBs and the current analysis DB, check disk capacity, then make verified SQLite online backups of only the written roles. Each backup is opened, quick-checked, foreign-key-checked, sized, and SHA-256 hashed. Recheck source state after backup.
5. For Add Tickers, perform and record the authoritative provider/canonical mutations. Sector/Industry and Taxonomy perform no source mutation. Run B1 `rebuild_v2_analysis` from provider, canonical, market, and active taxonomy into a new candidate next to the target DB. No old analysis DB is a calculation input.
6. Require B1 `READY`, the complete V2 package/RP V2/RV validation, unchanged authoritative inputs, unchanged active taxonomy version/semantic fingerprint, and unchanged old analysis. The candidate and target must differ and be on the same filesystem, with no SQLite sidecars. Fsync the validated candidate file, atomically `os.replace` the analysis DB, then fsync its directory.
7. Reopen the replaced path and run B1 postflight: SQLite integrity/FKs, V2 package and as-of date, RP V2 snapshot and taxonomy dependency, RV source/result compatibility, V2 reader and Snapshot smoke, no V1 results, and exact candidate SHA-256 match.
8. After a failed source mutation, publication, or postflight, restore whole written DBs from verified backups using fsynced, same-filesystem staged replacements; reopen and verify hashes. Report `FAILED_ROLLED_BACK`, or the distinct `CRITICAL_ROLLBACK_FAILED` if restoration fails. Keep backup evidence for manual recovery; clean candidate scratch files.

The lock coordinates Administration with the scheduler, not every possible ad hoc external writer. A separately authorized production maintenance window must exclude non-cooperating database writers and obtain a fresh Preview/Test; this phase did not run a changed-state production update.

## UI and evidence

`Production update` remains an explicit user action, gated by the current Preview and its successful matching `Test on copies` run. Changing input or operation invalidates the Test binding. Active Taxonomy Preview now exposes its production eligibility correctly. Every transaction writes `result.json`, lifecycle/status artifacts, and a human-readable `operation_report.md` with requested change, Preview/Test IDs, source checks, backup paths, V2/RP/RV counts, taxonomy identity, publication/postflight, and rollback status.

## Copy rehearsals

Taxonomy: completed on a production-shaped copy (`20260918T170614Z_check_update_taxonomy_57bdf81d8356_transaction_rehearsal`). Only the copied analysis DB was backed up/replaced; active `dc_ecosystem` version `DC_TAXONOMY_FULL_V2_1`, semantic fingerprint `801698f6b352c445cc8e6f5fd51a1cac2779d11f6ce72a1c10bf71bb8aae4559`, B1 READY and postflight passed. The candidate had 87,860 Score rows, 13,799 RP result rows, and 2,444 RV inputs. No CSV or taxonomy DB write occurred.

Add Tickers: completed (`20260918T172841Z_add_tickers_4942df1f86f7_transaction_rehearsal`) after a fresh `GFS` Preview and successful matching `Test on copies` (`20260918T171757Z_add_tickers_4942df1f86f7_apply`). The copied provider, canonical, and analysis DBs were backed up; `GFS` gained one security in the copied canonical DB, while the production canonical DB still has zero. B1 returned `READY`; the candidate had 87,882 Score, Lifecycle, Valuation, Delta, and Diagnostics endpoints, 13,807 RP result rows, and 2,444 RV inputs. Atomic same-filesystem replacement and reopened-path postflight passed. Rollback was not required. RP V1 was not invoked.

Sector/Industry: completed (`20260918T173025Z_check_update_sector_industry_219147e5d2c6_transaction_rehearsal`) after a changed-state `NVDA` Preview and matching `Test on copies` (`20260918T172018Z_check_update_sector_industry_219147e5d2c6_apply`). The fixture's copied `ticker_meta` was changed to Financial Services/Banks - Diversified before Preview; the Administration transaction reported `ticker_meta=READ_ONLY`, backed up and wrote only copied analysis, and left the market DB's fixture value untouched. Production NVDA remains Technology/Semiconductors. B1 returned `READY`; the candidate had 87,860 Score rows, 13,795 RP result rows, and 2,444 RV inputs. Atomic replacement and reopened-path postflight passed. Rollback was not required.

Before removing phase-owned scratch databases, all Add and Sector/Industry backup files were rehashed and matched their recorded SHA-256 values. The source-copy and backup DB files were then cleaned (Add: 7 source files + 3 backups; Sector/Industry: 7 source files + 1 backup). Run results and reports remain available under their `/tmp/rawcandle-b3-*-test` roots; production backup retention behavior in the code is unchanged.

Synthetic copy fault tests cover rebuild failure after Add source writes, rejected candidate validation, post-replacement postflight/RV/taxonomy/integrity failure, changed market source during rebuild, changed active taxonomy during rebuild, invalid backup, missing Test, and unsafe publication paths. The pre-operation written DB state is restored for failures after the write boundary; failures before it leave it unchanged.

| Injected fault | Expected and observed copy outcome |
| --- | --- |
| Add source mutation followed by rebuild exception | `FAILED_ROLLED_BACK`; provider, canonical, and analysis rows restored |
| B1 candidate not `READY` | `FAILED_ROLLED_BACK`; old analysis retained and Add sources restored |
| Failure after atomic replacement | `FAILED_ROLLED_BACK`; each restored file matches its verified backup SHA-256 |
| RV/taxonomy/integrity postflight exception | `FAILED_ROLLED_BACK`; old analysis restored |
| Market source or active taxonomy changes during rebuild | Candidate rejected at source recheck; no analysis publication |
| Invalid backup or missing matching Test | Failure before source mutation or publication |
| Concurrent Administration/scheduler lock or stale owner text | Kernel lock excludes live owner, releases after failure, stale text does not block |

SQLite online backup can change file-level page/header bytes relative to the live pre-backup file. Rollback is therefore verified against the backup's SHA-256 plus the original logical source state, not against the original live file's byte hash.

## Tests and restrictions

- Final focused Administration suite: 109 passed, 0 skipped, 0 failed.
- Broader V2/RP/RV/Admin/scheduler suite: 283 passed, 0 skipped, 0 failed.
- Additional final transaction/UI suite: 47 passed; standalone production transaction suite: 21 passed; Add/Sector CLI suite: 35 passed.
- No changed-state production operation, production source write, production analysis replacement, taxonomy write, V1 deletion, or push was performed.

Commands used (all with the repository `venv`):

```bash
venv/bin/pytest -q tests/test_fundamentals_admin_batch_add_tickers.py tests/test_fundamentals_admin_sector_industry.py tests/test_fundamentals_admin_ui.py tests/test_fundamentals_admin_full_v2_downstream.py tests/test_fundamentals_admin_production_transaction.py tests/test_fundamentals_admin_taxonomy_production.py
venv/bin/pytest -q tests/test_fundamentals_v4_full_rebuild.py tests/test_fundamentals_v4_operating_income_v2.py tests/test_fundamentals_v4_operating_income_v2_current_sources.py tests/test_fundamentals_v4_operating_income_v2_persistence.py tests/test_fundamentals_v4_relative_position_source.py tests/test_fundamentals_v4_relative_position_persistence.py tests/test_fundamentals_v4_relative_position_production.py tests/test_fundamentals_v4_relative_valuation_source.py tests/test_fundamentals_v4_relative_valuation_persistence.py tests/test_fundamentals_v4_relative_valuation_production.py tests/test_fundamentals_admin_foundation.py tests/test_fundamentals_admin_progress.py tests/test_fundamentals_admin_taxonomy.py tests/test_fundamentals_admin_taxonomy_acceptance.py tests/test_fundamentals_admin_verification_plan.py tests/test_stock_update_scheduler_runner.py tests/test_stock_update_scheduler_config.py
venv/bin/pytest -q tests/test_fundamentals_admin_ui.py tests/test_fundamentals_admin_production_transaction.py
```

No skipped tests or unresolved test failures in these runs. A temporary assertion that live SQLite DB bytes equal online-backup bytes was corrected to the appropriate verified-backup invariant and passed afterward.

## Completion and next phase

All three active Administration operations now use one guarded full V2 + RP V2 + RV transaction model. The changed-state copy rehearsals and controlled rollback failures succeeded. No production correction was attempted. The remaining prerequisites for any real production update are a newly created matching Preview/Test, an explicitly authorized maintenance window excluding non-cooperating writers, sufficient disk space, a clean worktree, and the normal scheduler lock. There is no B3 code/test blocker known from the completed copy evidence.

Recommended next phase: **13G.2.5C -- Execute Guarded Production V2 Rebuild and Verify Current Production State**. It is not executed here.

The separately authorized next phase is **13G.2.5C: Execute Guarded Production V2 Rebuild and Verify Current Production State**. It must create fresh production Preview/Test evidence and perform its own maintenance and postflight checks.
