# Phase 13G.3.62 Generation-Aware Run History And Cleanup

Date: 2026-10-03

## Result

Run History now presents the authoritative Full Workflow changed-ticker count and
recognizes eligible generation-directory Production publications through the existing
run-specific backup-cleanup contract.

Generation-aware Run History reuses the existing run-specific backup-cleanup backend. Active generations, the active manifest, migration generations, and legacy flat production databases are not cleanup targets.

## Observed Regression

The first reader-atomic live Full Workflow completed and published three changed
tickers, but its aggregate Run History row displayed zero. Its completed Production
child also retained three verified rollback backups totaling 2,553,339,904 bytes, but
the cleanup action was absent because eligibility compared the backups' source paths
with the newly active generation rather than the old generation that was backed up.

## Workflow Count Authority

New workflow results persist `changed_ticker_count` in their terminal summary from the
same structured child payload that supplies terminal authority:

- completed Production uses the Production child;
- a workflow stopped at Test uses the latest material Test evidence;
- a Preview review stop uses Preview evidence;
- `NO_CHANGE` remains zero.

Run History reads this self-contained terminal value without loading child reports.
Historical workflow results without the newer field fall back to the existing
self-contained `source_summary.effective_changed_known` value. Child counts are never
summed.

The live workflow
`20261003T105251Z_refresh_fundamentals_d00eb7239fed_full_workflow_2ee0b6f7`
was checked read-only and now presents `3 changed tickers`.

## Generation Cleanup Eligibility

For `GENERATION_POINTER` publications, eligibility now validates the persisted
Production result's structured evidence:

- journal state and publication step are `COMPLETED`;
- postflight is `PASSED`;
- rollback recovery is `NOT_REQUIRED`;
- generation activation is verified;
- the journal belongs to the selected Production run;
- backup source paths match the journal's old generation role paths;
- when terminal cleanup evidence is present, it is complete and verified, requires
  operator acceptance, and its retained paths exactly match the backup manifest.

Historical generation results without terminal cleanup evidence retain the existing
journal and backup-manifest fallback. Present but inconsistent terminal cleanup
evidence fails closed.

The current global publication journal must be absent or `COMPLETED`; incomplete,
recovered, rolled-back, and recovery-failed states block cleanup.

The current active generation remains the live-integrity verification target. The old
generation is only the durable ownership reference for the rollback backup source.
Actual deletion remains limited to exact `<backup-root>/<run-id>/<role>.db` paths.

The live Production run
`20261003T110448Z_refresh_fundamentals_33afa113e7cf_production_8278e7a6`
was inspected read-only and is now eligible with three backups totaling 2,553,339,904
bytes. No live cleanup was executed.

## Compatibility And Protection

Legacy flat-layout eligibility remains unchanged: its backup source paths continue to
match the live role paths. Existing already-cleaned evidence remains idempotent and
renders `Backups cleaned`.

Ownership validation continues to require backup-root containment, the selected run
directory, exact role filenames, non-symlink paths, recorded hashes, and one owned
directory. Tests prove that an active-generation database, active manifest, or
migration-generation database cannot be substituted as a cleanup target.

## Lazy History Behavior

Initial history rendering still reads one projection per visible run and does not read
child reports, hash backups, or scan generation directories. Newest-first ordering,
8/16/24 paging, details, downloads, row deletion, and affected-row refresh behavior
remain unchanged.

## Focused Verification

- Exact new workflow and generation-cleanup tests: `8 passed`.
- Generation protection and confirmation tests: `4 passed`.
- Full Workflow and cleanup contract modules: `49 passed`; final cleanup rerun after
  the historical and journal fail-closed additions: `33 passed`.
- Named Run History UI and generation regressions: `10 passed`.
- Compile/import validation: passed.
- `git diff --check`: passed.
- Repository-wide test suite run: `NO`.

## Safety

- Production financial databases changed: `NO`
- Active generation changed: `NO`
- Active manifest changed: `NO`
- Operational Review Queue changed: `NO`
- Real rollback backups deleted: `NO`
- Live workflows executed: `NO`
- Scheduler or systemd state changed: `NO`
- Phase-owned large files remaining: three live rollback backups, 2,553,339,904 bytes
- Git push performed: `NO`
