# P/B ownership rollback-backup acceptance — completed

**Current outcome: cleanup COMPLETED. Exactly 3 rollback backups deleted, 2,629,734,400 bytes freed, 0 selected backups remaining. No unrelated backup or live financial state changed.**

2026-10-28, Europe/Helsinki. Follow-up task P/B-OWNERSHIP-ROLLBACK-CLEANUP-INTEGRATION-1 explicitly authorized the bounded native integration and deletion in the same phase if all fresh gates passed. The original stop at commit `6a34dbadd08c88c119fb83a9a2aa8544004c0b34` was respected; its historical report is retained below. See [ownership cleanup integration contract and tests](ownership_publication_cleanup_contract_2026-10-28.md).

## Final acceptance and exact selection

Publication/NEW active generation remains `pb_ownership_903cf258a97f4873aa0f4797404a61ac`; OLD remains `payload_repair_03a973f7d891b895_b68015aea920`. No generation, generation manifest or source-repair backup was deleted.

Before any source edit, fresh reproduction again returned the exact original refusals: `CLEANUP_RUN_DIRECTORY_INVALID` at the default root and `CLEANUP_EVIDENCE_INVALID:result.json` with diagnostic native-lane inspection. Publication health, exact backup provenance and unchanged queue were proven. The generic read-only ownership adapter now maps native preview/completed receipts into the existing locked cleanup owner; no fabricated Production result or separate deletion path was introduced.

Fresh pre-delete snapshot: **2026-10-28T21:49:14.834317+02:00**. Final live/collateral verification: **2026-10-28T21:49:50.381847+02:00**. Read-open nonblocking preflight confirmed free UI/Production/scheduler locks, no active taxonomy operation, terminal journal, no pending recovery and no `.preparing` generation. Exact native inspection returned **ELIGIBLE / OWNERSHIP_PUBLICATION**, exactly three bound paths and 2,629,734,400 bytes. Classification: **ACCEPTANCE_READY_DELETE_CANDIDATES**. Provenance **PASS**; recovery independence **PASS** under the extended current-publication contract.

Fresh backup identity/size/hash validation agreed with the canonical completed journal, archived receipt, preview, OLD role manifests/actual files and successful publication evidence. The complete pre-delete backup inventory equals the fresh reproduction inventory, including inode/ctime/mtime/size. Thus the filesystem birth times and exact paths in the historical inventory below identify these same freshly revalidated files. All selected backup, OLD role and current role quick/FK/hash checks passed. Current/OLD role files were distinct from selected backups; no sidecar/in-use or nonterminal recovery dependency existed.

| Selected role | Fresh selected bytes | Deleted | Remaining |
| --- | ---: | --- | --- |
| analysis | 912,031,744 | YES | NO |
| canonical | 749,371,392 | YES | NO |
| provider | 968,331,264 | YES | NO |

Selected count: **3**. Deleted count: **3**. Deleted roles: **provider, canonical, analysis**. Selected/deleted bytes: **2,629,734,400**. Selected remaining: **0**.

## Execution and durable receipt

After all focused tests and runtime gates passed, the normal `FundamentalsAdminUIService.accept_run_and_cleanup_backups` entry point acquired its UI-operation guard and invoked the existing public cleanup owner with default Production/scheduler locking. No lock factory override, bypass, manual unlink or `rm` was used in the live invocation. The shared mechanism revalidated exact receipts/generations/role bytes and terminal safety before its native deletion loop. Cleanup returned COMPLETED; no exception or partial deletion occurred. No second YES was requested because this task explicitly authorized the exact deletion.

Durable native audit: `/home/kalle/projects/rawcandle/fundamental_reports/admin_runs/pb_ownership_publications/pb_ownership_903cf258a97f4873aa0f4797404a61ac/backup_cleanup.json`. Audit SHA-256: `a38e476313b60b6968b0445f851fcac371e59291dce4ef5bd5be66dfe2f4a20e`. It records exact deleted paths, verified backup hashes, sizes, integrity, OLD/NEW generation identities, preview hash and completed-receipt hash. The run directory and original preview/completed receipt remain. A fresh post-cleanup inspector returns **ALREADY_CLEANED**, recorded count 3 and bytes 2,629,734,400.

## Collateral and final live invariance

Bounded backup inventory changed from **53 to 50 files**, with the only removed paths being the three exact selected role backups. Every retained file has identical path, inode, size, mtime, ctime and symlink status. The selected owner’s seven original publication-evidence JSON files remain. Earlier payload-repair/source-repair backups and all unrelated historical backups are untouched. The native cleanup audit is retained outside the backup root, so it does not alter that collateral inventory. The historical directory table below describes the original 53-file pre-delete inventory; only the selected owner now has 7 files / 1,803,216 evidence bytes instead of 10 files / 2,631,537,616 bytes.

| Final invariant | Result |
| --- | --- |
| Active generation / all three financial DBs / active manifest | Unchanged, exact successful publication baseline |
| Provider watermark | 2026-10-27 → 2026-10-27 |
| Main journal / postflight / recovery | Unchanged: COMPLETED / PASSED / NOT_REQUIRED |
| Live provider/canonical/analysis SQLite quick/FK health | PASS / zero FK errors |
| Complete Review Queue logical content, decisions and audit | Unchanged |
| Source-repair decisions / WFRD / unrelated ownership reviews | Unchanged |
| Scheduler config / market / protected workflow code | Unchanged; only the cleanup module intentionally changed |
| OLD immutable generation / current generation | Retained, unchanged |
| Unrelated backup deletion or metadata change | NO |

| Ticker | Final Current P/B | Status / reason |
| --- | ---: | --- |
| GE | 17.55436232103115 | OK / OK |
| RTX | 3.7920742076120066 | OK / OK |
| T | 1.3211122199455392 | OK / OK |

Every full final Current P/B result equals the successful publication readback and fresh pre-delete result, with independent Decimal reconstruction from accepted current inputs. Final live role SHA-256 values and active manifest SHA remain those listed in the original audit below. Complete queue equality preserves GE/RTX/T ownership publication and all original source-only approval boundaries.

## Tests, scope and next phase

**324 compatibility/lifecycle tests passed**, plus **31 final-source focused tests passed** (353 distinct cases, two repeated compatibility cases). Coverage includes standard Production and source-repair envelope compatibility, native ownership cleanup, both publication/recovery lifecycles, existing current/historical drain cleanup, WFRD candidate parity, exact refusal matrix, locks, boundary drift and collateral retention. See the linked integration contract for exact modules, commands/logs, limits and timings. Full suite: **NO**.

Working runtime evidence: `/tmp/pb_ownership_cleanup_integration_20261028/before.json`, `cleanup_returned.json` and `after.json`. Final evidence SHA-256: `ae4b343fc89b2979362d1fd9cb3fdd72b94246b402fe7e830835b79557f0d2e4`. Original publication and source-repair evidence remain untouched; no runtime DB, journal, manifest, log or evidence JSON is part of the source/documentation commit.

**Recommended next Fundamentals phase:** formal closeout of this ownership publication/rollback-cleanup phase using the retained receipts, then resume the separately prioritized Fundamentals backlog. Historical generation retention, unrelated source-repair backup acceptance and broader disk cleanup remain separate work. No automatic follow-on cleanup is authorized.

---

**Historical section:** the original blocked acceptance result and its then-current recommendations below are superseded by the completed integration/cleanup above. They are preserved as the reason no deletion occurred before native support existed.

# Original acceptance stop — historical evidence

2026-10-28, Europe/Helsinki. Governing [successful ownership publication](pb_ownership_publication_ge_rtx_t_2026-10-28.md), documentation commit `925a3a3a558eb425824145492c8bea52271b51bd`.

**Cleanup BLOCKED: the existing locked cleanup contract cannot accept this ownership-publication operation. Deleted 0 backups / 0 bytes; all 3 selected backups remain.** The prompt already authorized deletion if every gate passed. No additional approval is needed; the blocker is missing native cleanup integration. The task explicitly requires stopping on a cleanup-contract defect, so no deletion API was invoked and no source or receipt was changed.

## Exact publication and fresh preflight

NEW/current generation and operation ID: `pb_ownership_903cf258a97f4873aa0f4797404a61ac`. OLD generation: `payload_repair_03a973f7d891b895_b68015aea920`. Operation: `PUBLISH_PB_OWNERSHIP_REVIEWS`. Starting HEAD: `925a3a3a558eb425824145492c8bea52271b51bd`.

Audit began 2026-10-28T21:37:12.273347+02:00 and finished 2026-10-28T21:37:59.084806+02:00. The existing read-open, nonblocking `provider_payload_workflow.preflight` acquired the scheduler, UI-operation and Production kernel locks and held them throughout the audit. Taxonomy-operation and journal safety checks passed. No lock was bypassed or waited for. No visible or hidden `.preparing` generation existed. No concurrent native publication/scheduler operation held these locks.

Active generation resolution and manifest binding passed. Main publication journal equals both the native `completed_journal.json` and the retained successful publication evidence. Journal remains **COMPLETED / PASSED / NOT_REQUIRED**; no pending recovery is indicated. The journal is terminal but still retains the backup paths as historical rollback provenance.

## Live health and protected state

Every live role passed read-only SQLite `quick_check=ok` and `foreign_key_check` with zero errors. SHA-256, manifest, market, scheduler configuration and tracked workflow-code fingerprints equal the successful publication baseline exactly, before and after this audit. This verifies the completed publication is still current, including the WFRD state and canonical financial/publication-authority content; no WFRD workstream was reopened.

| Role | Live bytes | Live SHA-256 |
| --- | ---: | --- |
| analysis | 912,031,744 | `ce5a09a8782660703e5160aa44a798ea2029318732466f0aa90b28c38321e3e8` |
| canonical | 749,371,392 | `b40e552d8a3afd547b08a8c3b66906e5168300c9050180294c45e40c832eb689` |
| provider | 968,331,264 | `45883cb5083d2847876b29f350387e56d1a0476eb8cfb853fe3e6c5646da123a` |

Active manifest SHA-256: `e1b8075f7c6b3becd5eb2ac439e34b8a102803269ad2b17930de09c84865bd6b`. Provider published-source watermark remains **2026-10-27 → 2026-10-27**. Generic journal ownership as-of/source-date fields do not constitute a provider watermark advance.

Whole logical Review Queue content matches the successful publication snapshot and is unchanged before/after, covering `pb_ownership_review`, `provider_payload_repair_review`, both accounting-boundary tables, `refresh_review_queue` and its audit. Thus the three source-repair decisions, GE/RTX/T publication decisions, unrelated ownership reviews and all other queued decisions/audit rows remain unchanged.

| Ticker | Current P/B | Status / reason | Independent Decimal reconstruction |
| --- | ---: | --- | --- |
| GE | 17.55436232103115 | OK / OK | 17.554362321031148464910249971464444698093824905833 |
| RTX | 3.7920742076120066 | OK / OK | 3.7920742076120066856225236101083032490974729241877 |
| T | 1.3211122199455392 | OK / OK | 1.3211122199455392049804650995083118707562631702177 |

Each fresh full Current P/B result equals the successful publication readback. Reconstruction uses current price × accepted economic units / parent equity USD at 50-digit Decimal precision, within 1e-12 relative/absolute tolerance. All three retain their published approved ownership basis; quote date is 2026-10-27 and report as-of is 2026-10-28.

## Exact backup inventory and provenance

Backup directory: `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/pb_ownership_903cf258a97f4873aa0f4797404a61ac`. Exact selection comes from the terminal journal’s role-specific `backup_path` and `verified_backup_fingerprint`, cross-checked against the retained successful publication `publication_evidence/result.json`; filenames and age alone were not used.

| Role / filename | Bytes | Filesystem creation time, Helsinki | SHA-256 |
| --- | ---: | --- | --- |
| analysis / `analysis.db` | 912,031,744 | 2026-10-28 21:23:18.715513760 +0200 | `ce5a09a8782660703e5160aa44a798ea2029318732466f0aa90b28c38321e3e8` |
| canonical / `canonical.db` | 749,371,392 | 2026-10-28 21:23:17.219518212 +0200 | `147e6ef965af071062fb89170d62b9bb471267c2cc5ac6cad4278afa2dbba054` |
| provider / `provider.db` | 968,331,264 | 2026-10-28 21:23:15.579523058 +0200 | `45883cb5083d2847876b29f350387e56d1a0476eb8cfb853fe3e6c5646da123a` |

**Found exactly 3 selected files, total 2,629,734,400 bytes. Provenance PASS.** Each selected file is a regular non-symlink at the journal’s exact path; its native `_validate_backup` read-only quick/FK/hash validation passed. Each hash also equals the corresponding retained OLD immutable-generation role and the successful publication’s backup evidence. Provider and analysis happen to be byte-identical between OLD and NEW; operation ownership is established by the exact journal bindings, not by those shared hashes.

Exact OLD role links:

- analysis: `/home/kalle/projects/rawcandle/data/fundamentals_generations/payload_repair_03a973f7d891b895_b68015aea920/fundamentals_analysis.db`; backup is the distinct path `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/pb_ownership_903cf258a97f4873aa0f4797404a61ac/analysis.db`.
- canonical: `/home/kalle/projects/rawcandle/data/fundamentals_generations/payload_repair_03a973f7d891b895_b68015aea920/fundamentals_v4.db`; backup is the distinct path `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/pb_ownership_903cf258a97f4873aa0f4797404a61ac/canonical.db`.
- provider: `/home/kalle/projects/rawcandle/data/fundamentals_generations/payload_repair_03a973f7d891b895_b68015aea920/fundamentals_provider.db`; backup is the distinct path `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/pb_ownership_903cf258a97f4873aa0f4797404a61ac/provider.db`.

All selected paths are distinct from current role paths and retained OLD paths. They belong to this ownership publication, not the earlier payload repair, WFRD, scheduler incidents or Test copies. All remain retained and cleanup-ineligible. Creation times above are filesystem birth times (`stat %w`), not inferred modification times.

## Recovery independence and cleanup contract

**Recovery independence: FAIL for release acceptance.** The operational recovery subchecks pass: terminal COMPLETED journal, PASSED postflight, NOT_REQUIRED recovery, healthy current generation and available native operation locks. No current native operation was active during the locked audit. However, the required condition “cleanup contract permits release after successful publication” fails. This is not a finding that rollback is currently running or required. The backups cannot be classified safe to release under the existing mechanism; no independent per-process open-file proof or bypass was substituted for that missing contract.

The approved entry point is `run_acceptance_cleanup.accept_run_and_cleanup_backups`, serialized by `production_lock`; its locked implementation calls the eligibility inspector before any deletion. It validates exact role manifests, source/ownership paths, hashes, SQLite health, current result/journal and live invariance, then retains `backup_cleanup.json` for supported runs. The UI delegates to this same mechanism. Its supported standard result is a `PRODUCTION_APPLY` run; its explicit other-operation adapter handles `RESULT_PUBLICATION_BACKLOG_DRAIN`, not `PUBLISH_PB_OWNERSHIP_REVIEWS`.

Fresh read-only inspector results:

| Inspection | Status | Reason |
| --- | --- | --- |
| Public inspector, default run root, exact operation ID | NOT_ELIGIBLE | `CLEANUP_RUN_DIRECTORY_INVALID` |
| Diagnostic only: inspector pointed at the native ownership lane parent | NOT_ELIGIBLE | `CLEANUP_EVIDENCE_INVALID:result.json` |

The actual lane `fundamental_reports/admin_runs/pb_ownership_publications/pb_ownership_903cf258a97f4873aa0f4797404a61ac/` contains exactly `preview.json`, `completed_journal.json` and `market.db`. `_run_dir` searches direct standard admin runs and the established publication-drain sibling; it does not select this nested ownership lane. Even a diagnostic lane-root override encounters the missing required `result.json`. The ownership publisher natively archives its completed journal and finalizes the queue, without emitting that standard Production result or an ownership cleanup adapter.

The helper-created `publication_evidence/result.json` is a publication verification report, not a native `PRODUCTION_APPLY` cleanup receipt. It was neither moved nor fabricated into one. No alternative root was used for deletion, no cleanup bypass was introduced and no standard metadata was rewritten. The approved mechanism therefore cannot safely target this exact set today. **Gate H fails; the release condition in G fails; cleanup acceptance criteria are not met.**

## Collateral inventory

Bounded scope: files underneath `backups/fundamentals_admin_production` only. Before/after inventory records every file path, size, inode, mtime, ctime and symlink status. No whole-disk cleanup scan was performed. Every inventory record is identical after the audit. Classification: the three exact journal-bound files are the requested candidates, retained because blocked; their seven publication-evidence files are protected evidence; every file in the other operation directories is unrelated retained material. No ambiguous extra file was selected. Recovery dependencies of unrelated backups were not assessed or released.

| Backup-owner directory | Retained files | Total bytes, including evidence |
| --- | ---: | ---: |
| `20260918T182639Z_check_update_taxonomy_293c901ce1dd_production_12a72eb2` | 1 | 1,582,403,584 |
| `20260919T113359Z_add_tickers_8bbcda32e218_production_38f7bfac` | 3 | 2,492,153,856 |
| `20260919T151515Z_add_tickers_b99c78e6879b_production_53c729c1` | 3 | 2,503,581,696 |
| `20260919T_phase13g25f_final_v2_publication` | 1 | 892,256,256 |
| `20260926T163001Z_first_public_result_date_bootstrap_production` | 3 | 2,545,537,024 |
| `payload_repair_03a973f7d891b895_b68015aea920` | 14 | 2,631,800,584 |
| `pb_ownership_903cf258a97f4873aa0f4797404a61ac` | 10 | 2,631,537,616 |
| `pb_quarterly_ownership_v2_20261008T080025Z` | 3 | 2,628,182,016 |
| `pb_reporting_20261007T193505Z` | 3 | 2,553,917,440 |
| `publication_drain_20261005T064921Z_43a1e040` | 3 | 2,553,729,024 |
| `publication_drain_20261006T110330Z_2d836e37` | 3 | 2,553,741,312 |
| `publication_drain_20261006T150551Z_9cfd3ca0` | 3 | 2,553,880,576 |
| `publication_drain_20261007T093516Z_fd654a20` | 3 | 2,553,917,440 |

Total bounded inventory: 53 retained files. The selected owner has 3 DB backups plus 7 protected evidence JSON files; the directory total is not the deletable byte count. Source-repair backups, historical backups, existing evidence and all immutable generations remain intact. No WFRD cleanup was attempted.

## Execution, final invariance and next phase

Deletion invocation: **NO**. Cleanup outcome: **BLOCKED_CONTRACT_UNSUPPORTED**. Deleted backups: **0**; deleted roles: **NONE**; deleted bytes: **0**. Selected remaining: **3 / 2,629,734,400 bytes**. Unrelated backups deleted: **NO**. No partial cleanup occurred and no native cleanup-success receipt was created. Manual deletion was not used.

Final checks: active generation, all three financial DB hashes, active manifest, actual provider watermark, complete queue content, scheduler configuration, workflow code, main journal and bounded backup inventory are unchanged. GE/RTX/T Current P/B remains as above. Source-repair decisions, WFRD and unrelated ownership reviews are unchanged. No financial/schema/source changes, recovery, publication, broad cleanup, pytest or full suite were run. Existing unrelated worktree changes were preserved. Only this report is to be committed; no push.

Machine audit: `/tmp/pb_ownership_backup_acceptance_20261028/audit.json`, SHA-256 `5086ce19ed0c184785479752c241d94dcf63f849946201eec806fd97bac00820`. This temporary audit is supporting evidence; the exact identity, refusal, inventory totals and invariance results are recorded here durably. Original publication evidence remains untouched under the selected backup directory.

**Recommended next Fundamentals phase:** a separately scoped ownership-publication rollback-cleanup integration task. Extend the approved locked cleanup contract to recognize and validate the native ownership preview/completed-journal receipt, exact OLD/NEW binding and role backup identities, recovery-release conditions and retained cleanup evidence, with focused refusal/invariance tests. Then rerun fresh acceptance for this exact operation. No implementation of that extension is authorized or included in this documentation-only task.
