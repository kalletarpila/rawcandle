# Phase 13G.3.23: Production run acceptance and backup cleanup UI

## Operator workflow

Open Fundamentals Administration, select a Production run from Run history, and inspect its details. An eligible run shows **Accept run and cleanup backups**. The confirmation identifies the run, backup count, approximate space to be freed, and states that live Production databases are not modified.

After confirmation, the backend reloads and verifies the durable run evidence before deleting anything. A successful action displays **Accepted / backups cleaned**. The action is run-specific; there is no global cleanup command.

## Eligibility contract

A run is eligible only when structured evidence proves all of the following:

- mode is `PRODUCTION_APPLY` and outcome is terminal `COMPLETED`;
- rollback status is `NOT_REQUIRED`;
- publication and postflight evidence is complete;
- retained backups and their recorded SHA-256 values are present;
- every backup is owned by the selected run under the configured Production backup root;
- every backup role is bound to the corresponding current Production database;
- no incomplete or recovery-failed publication journal is active.

Failed, rolled-back, nonterminal, structurally ambiguous, and ownership-unproven runs fail closed. Eligibility inspection is performed only for the selected detail view and does not hash backup files. General history remains lazily loaded with 8/16/24 paging and newest-first ordering.

## Verification and cleanup

Invocation runs under the shared Production/scheduler lock, reloads the selected `result.json`, rechecks eligibility, hashes every retained backup, checks backup SQLite integrity, and checks the live databases for the written roles in read-only mode. It then reloads the run result and journal immediately before deletion.

Only the exact verified database paths recorded by that run are unlinked. The run-specific directory is removed only when empty. Reports, result JSON, workflow evidence, terminal journals, and unrelated backup directories are preserved. No Preview, Test, Production, rebuild, replacement backup, or scheduler operation is invoked.

Production rollback backups are retained until explicit operator acceptance. Acceptance cleanup is run-specific and never deletes unrelated backups.

## Idempotency and evidence

Successful cleanup writes `backup_cleanup.json` in the existing run artifact directory. It records the source run ID, timestamp, action, deleted paths, recorded and verified hashes, bytes freed, live integrity results, journal state, and outcome.

A repeat invocation with valid completed cleanup evidence returns `ALREADY_CLEANED`. Missing backups without completed cleanup evidence are not interpreted as success and fail closed.

## Tests and safety

Fixture-sized tests cover eligible and ineligible runs, rollback states, nonterminal journals, hash mismatch, live integrity failure, exact deletion scope, unrelated backup preservation, evidence, bytes freed, idempotency, partial loss, UI state, and lazy history behavior. Tests use temporary roots and do not touch real Production backups or execute live workflows.
