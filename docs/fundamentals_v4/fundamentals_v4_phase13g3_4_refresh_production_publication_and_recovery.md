# Phase 13G.3.4 - Refresh Production Publication and Recovery

## 1. Outcome

Phase 13G.3.4 succeeded in isolated production-shaped acceptance. The guarded manual Refresh Fundamentals Production transaction, rollback, crash recovery, cross-operation blocking, reporting, and UI state are implemented and tested. No real Refresh Production update was run.

## 2. Production Authorization

Production requires the exact successful Preview and Test on copies chain. The backend binds run IDs, refresh-set and schema fingerprints, copy-only success, one READY full V2 rebuild, unchanged identity mapping, zero publication-date repair cases, and Test evidence that production remained unchanged.

## 3. Source Revalidation

Complete ARQ/MRQ history is revalidated both at Production start and after candidate validation. A mismatch returns `STALE_REFRESH_TEST` or `STALE_REFRESH_SOURCE_BEFORE_PUBLICATION`; both leave production unchanged and require a fresh Preview and Test.

## 4. Candidate-First Boundary

Provider, canonical, and analysis candidates are constructed and validated before backup, journal PREPARED, or replacement. Injected provider build, canonical build, analysis build, candidate validation, and final source-check failures all retained the original three production fingerprints, created no publication journal, and removed candidate databases.

## 5. Provider Candidate

The provider candidate begins as a SQLite online copy and receives complete authoritative ARQ and MRQ replacement for the bound known tickers. Refresh state and watermark are written only to this candidate. Provider source equivalence, true source keys, unrelated-state preservation, quick check, FK checks, and semantic fingerprint are validated.

## 6. Canonical Candidate

Canonical uses the deletion-safe fresh rebuild from provider ARQ. Identity/control state is retained while derived quarter, financial, TTM, and structural state is rebuilt. Acceptance proved:

`company/security identity mapping before candidate rebuild == after candidate rebuild`

The same identity fingerprint is required at candidate validation and postflight.

## 7. Analysis Candidate

The canonical candidate feeds exactly one full B1 rebuild: Score V2, Lifecycle, Valuation V2, Delta, Diagnostics, RP V2, Relative Coverage, and RV. Market classification and active `dc_ecosystem` taxonomy are read-only inputs.

## 8. First-Run Bootstrap

The first fixture generation bootstrapped a previously null `first_public_result_date` from the accepted canonical publication-date baseline. This metadata bootstrap is counted separately from financial additions, revisions, removals, and source-availability changes.

## 9. Second-Generation Behavior

A second real canonical fixture generation included one historical Q2 revision and one new Q3. Q2 `source_availability_date` moved from `2026-08-26` to `2026-09-15`, while Q2 `first_public_result_date` remained `2026-08-26`. Q3 received `2026-11-20` as its initial first-public date. Second-generation bootstrap eligibility was zero, the established-date preservation map applied `1/1`, and identity remained unchanged.

## 10. Verified Backups

Before publication, SQLite online backups are made for provider, canonical, and analysis under the production/scheduler lock. Each backup has SHA-256, size, quick check, FK evidence, file fsync, and directory fsync. Backup physical SHA is authoritative for restore; it need not equal the source file SHA because an online SQLite backup may have a different page layout.

## 11. Publication Journal

`data/.fundamentals_admin_publication_journal.json` is the sole post-crash authority. Durable atomic JSON records authorization binding, watermarks, role paths, old production hashes, verified backup hashes, candidate hashes, replacement states, postflight, and recovery. Recovery does not infer state from timestamps, row counts, or whichever file looks newest.

## 12. Publication Order

The fixed order is provider, canonical, analysis. All three candidates validate before the boundary. PREPARED is durable before the first replacement. Each role becomes `REPLACED_AND_VERIFIED` only after its published fingerprint is verified.

## 13. Fsync Contract

Before every publication or restore `os.replace`, its journal intent is atomically persisted and fsynced. Candidate/restore staging files are fsynced before replacement. The published/restored DB and parent directory are fsynced after replacement, fingerprint verification follows, and only then is the completed role transition journaled and fsynced.

## 14. Ordinary Rollback

Catchable failures after provider, canonical, analysis, and postflight publication boundaries each restored and verified the complete OLD generation. The terminal state was `ROLLED_BACK`; old Refresh state and first-public state returned with the old provider/canonical files, and no candidate DB remained.

## 15. Crash Recovery

Process-crash-style faults were injected after PREPARED, after each of the three replacements, after all replacements before postflight, and after postflight before COMPLETED. Startup recovery restored all three OLD roles from journal-bound backups and ended `RECOVERED`. A crash after backups but before PREPARED changed no production DB and required no recovery.

## 16. Recovery During Recovery

Faults at `RESTORING_PROVIDER`, `RESTORING_CANONICAL`, and `RESTORING_ANALYSIS` left durable role-specific intent. The next recovery invocation restored the entire OLD generation again, including roles already restored before interruption, and then verified the three-role set.

## 17. Idempotence

Calling recovery after `RECOVERED` performs no DB mutation or backup replay. `COMPLETED` and `ROLLED_BACK` are also inert terminal evidence. Only nonterminal journal states invoke recovery; `RECOVERY_FAILED` blocks production writes.

## 18. Recovery Failure

A missing required backup produced `RECOVERY_FAILED`. Recovery did not guess or continue mutation, all Fundamentals writers remained blocked, and the human-facing message requires operator resolution. Journal-referenced verified backups are retained.

## 19. Cross-Operation Guard

The exact sequence was tested: incomplete Refresh journal -> Add Tickers Production attempt -> automatic complete-generation recovery -> Add Tickers `RETRY_REQUIRED` with no mutation -> second Add Tickers invocation reruns normal Preview/Test/source/preflight checks and may proceed. Terminal journals do not delay or block normal writes. Sector/Industry and Taxonomy production routes use the same shared transaction guard.

## 20. Refresh State / Watermark

The fixture starts in `BOOTSTRAP_BASELINE`; candidate-only state becomes `ESTABLISHED_PUBLISHED_STATE` with source watermark, provider semantic fingerprint, source schema fingerprint, Production run ID, and completion UTC. Journal `COMPLETED` is the semantic generation commit. The next Preview uses the established watermark with the three-day overlap.

## 21. Production Postflight

Postflight verifies provider history/state/fingerprint, canonical identity/uniqueness/date contracts, B1/RP/RV analysis health, exact role candidate fingerprints, and cross-role lineage. It explicitly requires `repair_required == 0` and `preservation_map_applied == preservation_map_applicable_existing_quarters`. Any failure triggers whole-generation rollback.

## 22. First-Public Contract

The preservation map is captured before derived quarter rows are cleared. Reports and postflight retain:

`first_public_result_date preservation map applied: X/X surviving existing quarters`

`first_public_result_date repair_required: 0`

Established dates are immutable in routine Refresh, new quarters use the accepted canonical policy, and removed-quarter dates remain evidence rather than stale canonical rows.

## 23. ARQ/MRQ Semantics

Provider Refresh stores complete ARQ and MRQ histories. Canonical and TTM/downstream financial values remain ARQ-based.

`MRQ overlay intentionally deferred for a later impact study.`

## 24. Production Report

The fixture report covers the executive result, duration, classification counts, old-to-new watermark, full V2/RP/RV status, source fingerprints, provider replacement, source-driven canonical changes, separate first-public metadata work, verified backups, role publication state, postflight, rollback, and per-ticker outcomes. Large raw JSON is kept in structured artifacts rather than printed inline.

## 25. Failure Reports

Acceptance covers distinct user messages for stale source, candidate validation failure, verified ordinary rollback, successful prior-publication recovery with retry required, and fail-closed recovery failure. Technical exceptions remain in structured evidence and the report appendix.

## 26. UI State

Initial state enables Preview only. A changed, review-free Preview enables Test; successful Test enables Production. Running Production disables all Refresh actions. Success invalidates prior authorization. Stale source requires fresh Preview/Test. Incomplete/recovery-failed journal state is visible and blocks writers. Refresh `Run full workflow` remains unavailable.

A material acceptance defect was fixed: a `NO_CHANGE` Preview no longer sets `future_test_authorized=true`, so Test and Production remain disabled.

## 27. End-to-End Rehearsal

The production-shaped fixture completed authorization, start source recheck, provider/canonical/analysis candidate builds, candidate validation, final source recheck, unchanged-production boundary proof, three verified backups, durable PREPARED, provider/canonical/analysis publication, postflight, COMPLETED, watermark publication, report creation, and candidate cleanup.

## 28. Next Preview NO_CHANGE

An established-state Preview against identical complete ARQ/MRQ source returned `NO_CHANGE`, `effective_changed_known=0`, retained the published watermark, and set `future_test_authorized=false`. Therefore neither Test nor Production is authorized for the unchanged generation.

## 29. Runtime and Storage

The focused Refresh Production plus copy acceptance set completed 52 tests in 19.47 seconds. The broader 239-test regression completed in 166.23 seconds. Real runtime remains dominated by three SQLite copies and full V2/RP/RV rebuild. Storage preflight reserves candidate, backup, rebuild/SQLite scratch, and 25 percent margin per filesystem.

## 30. Production Safety

No live Refresh Production or source mutation ran. Baseline writable DB hashes were:

- provider: `b71dfbb0128a4e5404a18c608e31e16ec08c07b75bbe416e1a48a62112469468`
- canonical: `4bedbf6b1bace42fe7bf708e1c7b502873c348d1c5aa95e3f3550d1a85d93790`
- analysis: `969eb38504893b260206f07033a292b0587c16164720556f11d1b77e69b834f2`

Baseline canonical state was `88835` quarters and `0` established first-public dates. Provider had no production Refresh-state table. Final checks repeat these facts and the five production/read-only DB size/mtime records.

## 31. Cleanup

Every `COMPLETED`, pre-publication `FAILED`, `ROLLED_BACK`, `RECOVERED`, and `RECOVERY_FAILED` rehearsal verifies that phase-owned provider/canonical/analysis candidates are absent. Recovery cleanup is journal-bound and cannot target production or backup paths. Lightweight JSON/report evidence and terminal journal evidence remain. Verified backups referenced by an incomplete journal are never deleted.

## 32. Tests

- Focused Refresh Production and copy acceptance: `52 passed, 0 skipped, 0 failed`.
- Full required regression selection: `239 passed, 0 skipped, 0 failed`.
- Final Preview suite after the `NO_CHANGE` correction: `17 passed, 0 skipped, 0 failed`.
- Touched-module `py_compile`: passed.
- `git diff --check`: passed.

## 33. Remaining Issues

There is no material Phase 13G.3.4 blocker. Three file replacements are journal-atomic and recoverable but not reader-atomic as one filesystem event; a reader can observe a bounded intermediate generation. Strict reader-level generation activation remains a future generation-directory/active-pointer concern.

## 34. Next Phase

Phase 13G.3.5 may generalize `Run full workflow` for Refresh, keep distinct Preview/Test/Production reports, add a workflow report, and introduce scheduler discovery through the same backend. Unattended scheduled Production remains disabled until the manual publication/recovery path has operational history.

## 35. Git

Phase implementation commits are:

- `d03ff75 feat: add guarded fundamentals refresh publication`
- `3126d03 fix: harden publication recovery retries`
- closure commit: `test: complete refresh production acceptance` (hash recorded in the final phase response)

The closure commit is not pushed.
