# Phase 13G.3.4 - Refresh Production Publication and Recovery

## 1. Outcome

Phase 13G.3.4 succeeded in development and fixture rehearsal. Refresh Fundamentals now has a guarded manual Production path. No real Refresh Production update was executed in this phase.

## 2. Production Authorization

Production requires the exact successful Preview and Test on copies chain. The backend verifies Preview and Test run IDs, refresh-set and schema fingerprints, successful copy-only status, one READY full V2 rebuild, unchanged identity mapping, zero publication-date repair cases, and unchanged production evidence from Test.

## 3. Source Revalidation

Complete ARQ/MRQ histories are revalidated before candidate creation and again after candidate validation immediately before backup/publication. A mismatch fails as `STALE_REFRESH_TEST` or `STALE_REFRESH_SOURCE_BEFORE_PUBLICATION` and requires a fresh Preview and Test.

## 4. Candidate-First Boundary

Provider, canonical, and analysis candidates are all built and validated before production backup or replacement. A stale source or candidate failure leaves all production databases untouched. The pre-build production size/mtime state is compared again before publication.

## 5. Provider Candidate

The provider candidate starts from SQLite online backup and applies complete authoritative ARQ/MRQ replacement for the bound changed known tickers. True source keys, complete-history trust, unrelated-state invariants, quick check, FK, child ownership, row counts, keys, and source fingerprints remain enforced.

## 6. Canonical Candidate

Canonical uses the Phase 13G.3.3 fresh deletion-safe rebuild. Identity/control tables are retained and derived quarter/financial/TTM/structural state is rebuilt. The invariant is explicit:

`company/security identity mapping before candidate rebuild == after candidate rebuild`

## 7. Publication-Date Production Contract

The preservation map is captured before derived quarter rows are cleared. Established `first_public_result_date` values remain immutable, while `source_availability_date` may follow a revised source winner. New quarters use the existing publication-date policy; removed-quarter dates remain evidence only.

## 8. Analysis Candidate

The canonical candidate feeds exactly one full B1 rebuild: Score V2, Lifecycle, Delta, Diagnostics, Valuation V2, RP V2, Relative Coverage, and RV. Market classification and active `dc_ecosystem` taxonomy remain read-only inputs. Canonical remains ARQ-based; MRQ overlay is deferred.

## 9. Candidate Validation

All candidates receive SQLite quick/FK validation. Provider source equivalence, canonical identity/date/uniqueness contracts, and B1 READY validation must all pass before publication.

## 10. Verified Backups

The old provider, canonical, and analysis generation is captured with SQLite online backup under the production/scheduler lock. Every backup has its own SHA-256, size, quick check, FK result, file fsync, and directory fsync. Source physical SHA is retained as audit evidence; it is not incorrectly required to equal an online backup's potentially different SQLite page layout.

## 11. Publication Journal

The canonical journal is `data/.fundamentals_admin_publication_journal.json`. It is outside the replaced databases and is updated by temp write, temp fsync, `os.replace`, and parent-directory fsync. It records binding, watermarks, role paths, old production hashes, verified backup hashes, candidate hashes, replacement state, postflight, and recovery state.

The durable journal is the single authority after a crash. Recovery does not inspect mtimes, row counts, or guess which production file looks newest.

## 12. Publication Order

The fixed order is provider, canonical, analysis. Before each production `os.replace`, the journal is durably advanced to `REPLACING_<ROLE>`. After replacement, the published file and parent are fsynced, the candidate fingerprint is verified at the production path, and only then is that role marked `REPLACED_AND_VERIFIED`.

## 13. Fsync Contract

Candidates are fsynced before replacement. Published files and their parent directories are fsynced after replacement. Backup files, backup directories, journal temporary files, and journal parent metadata are also fsynced.

## 14. Ordinary Rollback

A catchable failure after the publication boundary restores all three roles, including roles not yet replaced. Each `RESTORING_<ROLE>` intent is journaled and fsynced before restore replacement. Restored files are verified against the verified backup SHA. Only a fully verified old set reaches `ROLLED_BACK`.

## 15. Crash Recovery

Any nonterminal journal restores the complete old generation. Recovery never attempts to finish the new generation. Fault tests cover no replacement, provider replaced, provider+canonical replaced, all three replaced, and postflight-before-commit states.

## 16. Recovery Failure

A missing, corrupt, or fingerprint-mismatched backup produces `RECOVERY_FAILED`. Production-writing Fundamentals operations remain blocked. Read-only diagnosis remains possible.

## 17. Cross-Operation Guard

The guard is shared with existing Administration production transactions. An incomplete Refresh journal is recovered before Add Tickers can mutate anything, and the attempted Add Tickers invocation is stopped with a retry requirement. A `COMPLETED` journal is audit evidence only and neither blocks nor invokes recovery for normal Add Tickers execution.

## 18. Refresh State / Watermark

Refresh state is written only into the provider candidate. The source watermark is the highest relevant Sharadar `lastupdated` date from the validated published source state, never local wall-clock time. The journal's `COMPLETED` state is the semantic generation commit marker. The next Preview uses published watermark minus three calendar days.

## 19. First-Run Bootstrap Reporting

Reports separate source-driven added/changed/removed quarters and source-availability changes from metadata-only first-public bootstrap. They include:

`first_public_result_date preservation map applied: X/X surviving existing quarters`

`first_public_result_date repair_required: 0`

## 20. Production Postflight

Postflight runs against production paths before journal completion. It verifies provider source and Refresh state, canonical identity/quarter/publication-date contracts, analysis package health, exact published candidate fingerprints, and taxonomy/cross-role lineage.

## 21. UI State

Refresh exposes Preview, Test on copies, and Production update. Production is enabled only after the matching successful Test. Successful Production clears prior authorization. Stale source disables direct retry. A recovery failure is shown as a prominent production safety block. Refresh full workflow remains unavailable.

## 22. Future Trigger Architecture

Production is a UI-independent backend call with `trigger_source=MANUAL`. A future scheduler or full-workflow trigger must call this same backend rather than implement separate refresh logic.

## 23. Failure Reports

Pre-publication failures state that no production database was modified and whether direct Production retry remains valid. Stale source requires Preview and Test again. Post-boundary failure reports verified restoration of the old three-database generation. Recovery failure explicitly requires operator action.

## 24. Fault Injection

Tests assert durable intent before each publication and recovery replacement. Every replacement boundary retains enough journal evidence to restore the complete old set solely from recorded backup paths and fingerprints. Recovery is idempotent, completed journals are inert, and corrupt backup evidence fails closed.

## 25. End-to-End Rehearsal

A production-shaped fixture rehearsal executes authorization, two source checks, candidate-first construction, candidate validation, verified backups, PREPARED journal, provider/canonical/analysis publication, postflight, COMPLETED commit, and candidate cleanup. A separate postflight failure rehearsal restores all three old fixture databases and records `ROLLED_BACK`.

## 26. Production Safety

Development baseline hashes were captured for all five production/read-only databases. Before development, canonical held 88,835 quarters and zero established first-public dates; provider had no Refresh state table. Final verification confirms these remain unchanged. No live source request or real Production update was run for phase acceptance.

## 27. Runtime and Storage

The two focused production-shaped fixture rehearsals completed in about 7.5 seconds together. Real runtime remains dominated by provider/canonical copies and full V2/RP/RV rebuild. Storage preflight reserves a candidate set, backup set, rebuild/SQLite scratch, and 25 percent safety margin per filesystem.

## 28. Cleanup

Phase-owned candidate directories are removed after success, pre-publication failure, rollback, or recovery. Verified production backups, terminal lightweight journal, operation report, and structured evidence remain. Backups referenced by an incomplete journal must not be deleted.

## 29. Tests

Focused Refresh Production, Preview, copy-Test, UI, progress, foundation, and shared transaction suites passed 132 tests. Adjacent Add Tickers, full workflow, full V2 downstream, canonical rebuild, Sharadar provider, and RV production suites passed 85 tests. Python compilation and `git diff --check` pass. Ruff is not installed in the environment.

## 30. Remaining Issues

Three independent file replacements are not reader-atomic as a set. A reader can observe an intermediate generation during the bounded publication window. Strict reader-level generation atomicity requires the deferred generation-directory plus active-pointer architecture.

## 31. Next Phase

Phase 13G.3.5 may generalize the full-workflow orchestrator, retain stage reports, and add scheduler discovery using the same backend. Scheduled Production remains disabled until the manual journal/recovery path has operational history.

## 32. Git

The intended commit message is `feat: add guarded fundamentals refresh publication`. Final status and commit hash are recorded after all regression suites pass.
