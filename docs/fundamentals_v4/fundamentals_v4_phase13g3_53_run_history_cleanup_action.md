# Phase 13G.3.53 - Run-History Backup Cleanup Action

## Scope

Fundamentals Administration Run history exposes a cleanup action on an eligible
`Production update / Completed` row. Preview, Test, failed Production, and
unverifiable rows do not expose an active cleanup action.

The Run history cleanup action is only a UI entry point to the existing
run-specific acceptance/backup-cleanup backend. It does not implement a second
cleanup mechanism.

## Eligibility Authority

The UI obtains eligibility from
`FundamentalsAdminUIService.cleanup_eligibility()`. The service delegates to the
existing `inspect_cleanup_eligibility()` backend contract. Eligibility requires
durable evidence for terminal Production completion, successful postflight,
`NOT_REQUIRED` rollback, run-owned retained backups, and an inert publication
journal.

The detail inspection validates paths, ownership, evidence shape, backup
presence, and recorded sizes. It does not hash backup contents. Hash and SQLite
integrity verification remain in the existing locked cleanup apply operation.

## Historical Runs

Eligibility is evidence-based and has no Phase 13G.3.53 creation-date boundary.
An older Production run is cleanup-capable when its durable result, journal,
backup ownership, and recorded verification evidence satisfy the same backend
contract. Age, filename, and directory layout alone never authorize cleanup.

An older run with completed cleanup evidence is shown as `Backups cleaned`.
Missing or incomplete evidence, unproven ownership, and hash mismatch fail
closed.

## UI Behavior

Only visible completed Production candidates receive a lightweight eligibility
lookup during lazy history rendering. Results are cached for the current UI
session. Preview, Test, and failed Production rows do not trigger cleanup
inspection.

An eligible row shows `Accept run and cleanup backups`. Clicking it revalidates
eligibility and opens a confirmation containing:

- run ID;
- verified rollback-backup count;
- approximate bytes in GiB to be freed; and
- an explicit statement that live Production databases are not modified.

The confirmed action calls the existing service/backend cleanup method. A
successful result or `ALREADY_CLEANED` updates the cached row to the disabled
`Backups cleaned` state without reloading all history. Backend rejection is
shown as a concise status and performs no deletion.

## Lazy Loading

Newest-first ordering and 8/16/24 paging are unchanged. Initial history
construction does not hash backups, read every child report, or inspect
non-Production rows. Expensive verification occurs only after explicit operator
confirmation through the existing backend.

## Tests

Focused coverage proves:

- eligible historical Production rows expose the action;
- Preview, Test, and failed Production rows do not invoke eligibility lookup;
- already-cleaned historical runs show a terminal indicator;
- confirmation reports run ID, backup count, GiB, and live-DB safety;
- cleanup and `ALREADY_CLEANED` update only the in-memory row state;
- incomplete durable evidence fails closed;
- hash mismatch blocks backend deletion;
- row eligibility inspection performs no backup hashing; and
- existing history paging and row actions remain covered by Admin UI tests.

All tests use fixture run and backup roots. No live workflow, Production
financial database, retained Production backup, scheduler, or systemd state is
modified.
