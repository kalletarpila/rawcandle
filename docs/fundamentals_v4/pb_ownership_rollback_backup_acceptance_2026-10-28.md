# P/B ownership rollback-backup acceptance — blocked

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
