# Phase 13G.3.59 Refresh Backlog Closure

Date: 2026-10-02

## Status

| Backlog item | Implemented | Default enabled | Live migration required | Operator action |
|---|---:|---:|---:|---|
| `CONFIRM_TRUE_SOURCE_REMOVAL` | Yes | N/A | No | Review exact durable evidence and confirm per ticker |
| Terminal cleanup reporting | Yes | Yes | No | Use existing **Accept run and cleanup backups** action when rollback backups may be deleted |
| Generation-directory activation | Yes | No until migration | Yes | Run the explicit generation migration command |
| Scheduler `FULL_WORKFLOW` | Yes | No | No | Explicitly change mode with the confirmation token |

No production financial database, operational Review Queue, live scheduler configuration,
systemd state, or real backup was changed while implementing this phase.

## True Source Removal

`CONFIRM_TRUE_SOURCE_REMOVAL` is a distinct, production-durable approval. It is
eligible only for the existing ticker-local true-removal classification when complete
provider histories, exact removed keys, unambiguous identity, current published-state
binding, valid evidence fingerprint, and absence of newer conflicting evidence all
match. Rolling-window aging, retained-history cases, incomplete responses, ambiguous
short windows, and global blockers fail closed.

The lifecycle is:

`OPEN -> RETRY_REEVALUATION -> matching Preview -> matching Test -> matching Production -> RESOLVED`

Preview and Test do not resolve the approval. Interrupted attempts reuse unchanged
durable evidence. Reappearing keys or any relevant evidence drift invalidate the
approval and reopen review. The provider candidate may omit only the accepted keys;
canonical and V2/RP/RV state continue through the established rebuild contracts.

## Terminal Cleanup

Production reports now contain `## Terminal Cleanup`. The section separately reports:

- candidate databases, compact market bundle, taxonomy/runtime temporary artifacts,
  and other phase-owned temporary files as automatically disposable;
- provider, canonical, and analysis rollback backups as intentionally retained;
- retained backup count and bytes/GiB;
- whether operator acceptance is required;
- cleanup verification status and remaining paths.

Full Workflow surfaces the Production child summary. It does not implement another
cleanup path. Rollback backups remain run-bound and are deleted only by the existing
**Accept run and cleanup backups** operation.

## Generation Activation

The active layout is:

```text
data/fundamentals_generations/<generation_id>/
  fundamentals_provider.db
  fundamentals_v4.db
  fundamentals_analysis.db
data/fundamentals_active_generation.json
```

The manifest is replaced with `os.replace` and directory fsync, so activation is one
filesystem-visible boundary. Provider, canonical, and analysis candidates are complete,
integrity-checked, and journaled before activation. Add Tickers, Remove Tickers, and
Refresh Fundamentals production publication all use this contract after migration.

Supported readers resolve the active manifest once at logical operation start and keep
the resulting immutable role paths for that operation. A reader already bound to OLD
continues to read complete OLD while activation occurs. A later reader resolves complete
NEW. Snapshot batch generation pins one binding for the whole batch; Forecast fiscal
acquire/link/reconcile and Fundamentals Admin operations resolve through the same central
path contract.

The journal records OLD, NEW, the active-manifest path, readiness, activation, postflight,
and rollback state. Failure before activation leaves OLD active. Failure after activation
atomically reactivates and verifies OLD. Crash recovery chooses OLD unless journal state
proves completed NEW, and the first recovering invocation returns `RETRY_REQUIRED`.

Generation IDs are restricted to one safe path component. Migration copies and verifies
all role hashes, preserves the flat files, fsyncs the new generation, atomically activates
it, resumes safely after the generation-directory rename boundary, and is idempotent.
Ordinary Refresh never migrates automatically.

### Migration Operator Action

Run only in a reviewed maintenance window after ensuring no Fundamentals or scheduler
writer is active:

```bash
python3 -m rawcandle.cli.migrate_fundamentals_generation \
  --confirm CONFIRM_FUNDAMENTALS_GENERATION_MIGRATION
```

The command acquires Admin Production and scheduler locks, requires a clean publication
journal, verifies SQLite integrity and SHA-256 equality, retains the flat files, and then
activates the copied generation. Re-running it reports `ALREADY_MIGRATED`.

## Scheduler Rollout

`fundamentals_refresh_mode` accepts:

- `PREVIEW_ONLY`: default and existing behavior;
- `FULL_WORKFLOW`: explicit opt-in Preview -> Test on copies -> Production orchestration.

The existing `fundamentals_refresh_preview_enabled` switch remains the master enable.
`FULL_WORKFLOW` does not create or click Review Queue approvals. It uses only previously
human-approved, exact-match durable evidence; safely quarantined ticker-local items may be
held while safe changes proceed. Global blockers, failed Preview/Test, stale bindings,
publication recovery, writer contention, taxonomy/source-lock failure, or file-state drift
stop before Production.

In `FULL_WORKFLOW`, the scheduler acquires locks in this order:

`Admin Production -> scheduler -> taxonomy`

The production lock is reentrant only for the identical in-process lock path and scheduler
log directory. The scheduler result records configured mode, Preview result, held tickers,
global blockers, Test/Production invocation, Production run ID, Production decision reason,
and final outcome. A retry always starts with a fresh Preview.

### Scheduler Activation Operator Action

After generation migration and reviewed readiness, enable with:

```bash
python3 -m rawcandle.cli.configure_fundamentals_refresh_scheduler \
  --config scheduler_config.json \
  --mode FULL_WORKFLOW \
  --confirm CONFIRM_SCHEDULER_FULL_WORKFLOW
```

The scheduler UI exposes the same mode and requires the same confirmation when changing
from `PREVIEW_ONLY`. To roll back scheduler automation without touching data:

```bash
python3 -m rawcandle.cli.configure_fundamentals_refresh_scheduler \
  --config scheduler_config.json \
  --mode PREVIEW_ONLY
```

Neither command was executed during this phase.

## Verification

Focused and regression coverage includes true-removal eligibility/lifecycle, terminal
cleanup rendering, migration and crash boundaries, pointer compare-and-swap, OLD/NEW reader
pinning, journal recovery, Add/Remove/Refresh generation publication, Snapshot and Forecast
reader routing, scheduler configuration confirmation, human-only approvals, lock order,
and scheduler summary reporting.

Final acceptance result:

```text
3305 passed, 8 warnings in 1149.89s (0:19:09)
```
