# Datacenter Taxonomy Change Orchestrator

## Classification

```text
DATACENTER_TAXONOMY_CHANGE_ORCHESTRATOR_V1_IMPLEMENTED
```

This document describes the first unified backend facade for Datacenter taxonomy
changes. No production taxonomy change, scheduler run, Datacenter pipeline run,
EC loader, cleanup, finalization, activation, migration apply, production DB
write, production config write, production backup, restore, taxonomy CSV edit,
or watchlist edit occurred as part of this implementation.

## Goal

The orchestrator provides one workflow over the production-verified replacement
services:

```text
prepare
-> inspect plan
-> execute rebuild
-> validate/finalize
-> inspect activation plan
-> activate
-> verify status
```

The orchestrator supports explicit full and delta modes, plus an automatic
planner selection mode:

```text
rebuild_mode=FULL_REBUILD
rebuild_mode=DELTA_REBUILD
rebuild_mode=AUTO
```

`AUTO` is not persisted as an execution mode. It resolves to either
`FULL_REBUILD` or `DELTA_REBUILD` in the plan, and state-changing execution must
confirm the selected explicit mode and plan hash.

## Backend Facade

The facade lives in:

```text
rawcandle/datacenter_taxonomy_change_orchestrator.py
```

It coordinates existing backend services instead of duplicating their SQL or
business logic. It delegates to the existing taxonomy replacement backend for:

```text
proposed taxonomy metadata loading
deployment row creation
DC rebuild preparation evidence
EC old-version replacement cleanup planning
whole-range validation
canonical EC watermark finalization
rebuild evidence application
activation planning
guarded activation apply
```

The facade exposes JSON-compatible operations:

```text
prepare_taxonomy_change
build_taxonomy_change_plan
execute_taxonomy_rebuild
resume_taxonomy_rebuild
validate_and_finalize_taxonomy_rebuild
plan_taxonomy_activation
activate_taxonomy_change
inspect_taxonomy_change
```

State-changing production execution uses `build_production_taxonomy_change_services`
to bind the facade to the same Datacenter and EC rebuild backends used by the
production scheduler/rebuild tooling. A missing service set is still a testable
blocked state for isolated callers, but the Scheduler UI and unified run CLI now
construct production services from `scheduler_config.json` instead of returning
`EXECUTION_SERVICES_NOT_CONFIGURED` on the normal production path.

## CLI Facades

Preparation:

```bash
python3 -m rawcandle.cli.prepare_datacenter_taxonomy_change \
  --analysis-db data/analysis.db \
  --proposed-taxonomy-csv data/datacenter_taxonomy_full_v3.csv \
  --date-to YYYY-MM-DD \
  --scheduler-config scheduler_config.json \
  --watchlist watchlists/datacenter_watchlist.txt \
  --evidence-root temp/datacenter_taxonomy_change_<timestamp> \
  --rebuild-mode auto \
  --format json
```

Inspection:

```bash
python3 -m rawcandle.cli.inspect_datacenter_taxonomy_change \
  --analysis-db data/analysis.db \
  --deployment-id <deployment_id> \
  --scheduler-config scheduler_config.json \
  --format json
```

Rebuild execution facade:

```bash
python3 -m rawcandle.cli.run_datacenter_taxonomy_change \
  --analysis-db data/analysis.db \
  --deployment-id <deployment_id> \
  --proposed-taxonomy-csv data/datacenter_taxonomy_full_v3.csv \
  --date-to YYYY-MM-DD \
  --scheduler-config scheduler_config.json \
  --watchlist watchlists/datacenter_watchlist.txt \
  --evidence-root temp/datacenter_taxonomy_change_<timestamp> \
  --confirm-deployment-id <deployment_id> \
  --confirm-proposed-taxonomy-version <version> \
  --confirm-proposed-source-hash <sha256> \
  --confirm-date-from <date> \
  --confirm-date-to <date> \
  --confirm-rebuild-mode FULL_REBUILD|DELTA_REBUILD \
  --confirm-plan-hash <plan_hash> \
  --format json
```

Resume uses the same guarded arguments plus:

```bash
python3 -m rawcandle.cli.run_datacenter_taxonomy_change \
  <same guarded arguments> \
  --resume \
  --format json
```

Activation facade:

```bash
python3 -m rawcandle.cli.activate_datacenter_taxonomy_change ...
```

The activation facade delegates to the existing guarded activation backend. It
does not add a second activation implementation.

State-changing CLI facades create a durable taxonomy operation log entry before
execution and acquire a cross-process taxonomy operation lock. The lock prevents
concurrent rebuild/resume/activation attempts and can recover a stale lock left
by a dead process.

## Deployment Lifecycle

One taxonomy change uses one durable row in:

```text
ec_taxonomy_change_deployment
```

The orchestrator reuses the existing deployment structure instead of creating a
parallel deployment model. The normalized orchestration status maps the existing
deployment fields into:

```text
DRAFT
PLANNED
REBUILDING
VALIDATING
READY_TO_ACTIVATE
ACTIVATING
ACTIVE
```

Failure and recovery statuses:

```text
BLOCKED
REBUILD_FAILED
VALIDATION_FAILED
ACTIVATION_FAILED
ROLLED_BACK
```

Invalid transitions are blocked:

```text
DRAFT -> ACTIVE
REBUILD_FAILED -> ACTIVATE
READY_TO_ACTIVATE -> REBUILD unless an explicit restart policy is added later
```

`ACTIVE -> ACTIVATE` is an idempotent no-op through the activation backend.

## Prepare

Preparation is read-only first. It:

```text
1. Reads the active taxonomy from EC metadata.
2. Reads and validates the proposed CSV.
3. Derives the proposed taxonomy version from the CSV.
4. Rejects reuse of the active taxonomy version.
5. Computes current and proposed source hashes.
6. Builds a taxonomy diff.
7. Derives the full and delta rebuild ranges.
8. Validates scheduler config still points coherently to the active taxonomy.
9. Produces a deterministic plan hash.
10. Creates or reuses one deployment only after validation gates pass.
```

Preparation does not modify facts, watermarks, scheduler configuration, or
watchlists.

## Taxonomy Diff

The reusable diff model reports deterministic sorted lists:

```text
added_tickers
removed_tickers
unchanged_tickers
primary_membership_changes
secondary_membership_additions
secondary_membership_removals
scope_flag_changes
affected_tickers
affected_groups
delta_scope_summary
dependency_map
estimated_delta_work
estimated_full_work
```

It also detects structural changes:

```text
added_layers
removed_layers
added_subindustries
removed_subindustries
renamed_layers
renamed_subindustries
structural_change_detected
```

Normal monthly delta workflow requires:

```text
structural_change_detected=false
```

If layers or subindustries are added or removed, explicit delta is blocked and
`AUTO` selects the existing full rebuild path. Rename detection is represented
as an explicit future field; version 1 reports renames as empty and treats added
or removed structures as delta blockers.

## Plan Hash

The deterministic plan includes:

```text
deployment_id
ecosystem
current taxonomy version/source/hash
proposed taxonomy version/source/hash
requested_rebuild_mode
recommended_rebuild_mode
selected_rebuild_mode
rebuild_mode
date_from
date_to
taxonomy_diff
delta_scope_summary
dependency_map
estimated_delta_work
expected_counts
backup_policy
phase_sequence
```

State-changing operations must confirm:

```text
deployment_id
proposed taxonomy version
proposed source hash
date range
rebuild mode
plan hash
```

A changed CSV, date range, active taxonomy, rebuild mode, deployment identity, or
plan invalidates the confirmation.

## Delta Rebuild Backend

Delta mode is intended for ordinary monthly taxonomy changes where layers and
subindustries are unchanged. Supported delta-scoped changes are:

```text
added ticker
removed ticker
primary membership change
secondary membership add/remove
scope flag change
```

Structural changes block explicit delta and make `AUTO` recommend full rebuild:

```text
added or removed layer
added or removed subindustry
renamed layer or subindustry
semantic group incompatibility
```

The delta plan derives deterministic affected ticker and group lists. A group is
affected by added/removed ticker membership and primary/secondary membership
changes. A scope-only change affects the ticker classification but does not by
itself dirty group histories.

Ticker technical history is treated as taxonomy-independent except for embedded
taxonomy metadata. Safe carry-forward copies active-version ticker rows to the
proposed taxonomy and rewrites `taxonomy_version`, `primary_layer`, and
`primary_subindustry` from the proposed primary membership. Added tickers are
rebuilt, removed tickers are omitted, and affected groups are recalculated.

The backend exposes `copy_delta_carry_forward` for safe DC fact copies in test
or controlled execution databases. EC construction remains the existing
canonical DC-to-EC loading path from the completed proposed DC state. This keeps
EC taxonomy-scoped and complete without making the current DC-to-EC bridge a
long-term EC architecture.

## Rebuild Phase Order

The unified execution facade represents this full rebuild order:

```text
1. Rerun plan and confirmation checks.
2. Set scheduler guard.
3. Verify no active writer.
4. Create or validate the one deployment backup.
5. Ensure proposed taxonomy metadata is loaded.
6. Run DC full rebuild.
7. Run EC chunked full rebuild.
8. Run coverage and parity.
9. Run old-version EC replacement cleanup.
10. Run whole-range validation.
11. Finalize canonical EC watermarks.
12. Apply rebuild evidence.
13. Produce activation plan.
14. Restore scheduler guard.
```

Version 1 exposes this phase contract and testable sequencing. The default CLI
does not embed production-specific subprocess commands; production execution
must be wired deliberately through the existing verified services in a controlled
run task.

Activation is not automatic.

For delta plans, the execution facade inserts a `DELTA_CARRY_FORWARD` phase
after backup validation and before the injected DC rebuild service. Affected
ticker/group rebuilds, EC loading, coverage, parity, cleanup, watermark
finalization, and activation planning still use the same injected service and
validation boundaries as full rebuilds.

## Resume And Idempotency

The orchestrator inspects durable deployment state before execution:

```text
completed phase -> do not repeat unnecessarily
failed phase -> resume from earliest safely repeatable phase
READY_TO_ACTIVATE -> no rebuild
ACTIVE -> ALREADY_ACTIVE / no-op
changed plan/source -> block
```

The inspection result exposes:

```text
normalized_orchestration_status
per_phase_status
safe_next_action
```

Examples:

```text
PLANNED -> execute_rebuild
REBUILD_FAILED -> resume_from_failed_phase
VALIDATION_FAILED -> validation_only_recovery
READY_TO_ACTIVATE -> inspect_activation_plan
ACTIVE -> no_change
```

## Failure Output

Failures stop at the first failed phase and preserve structured resume evidence:

```text
failed_phase
failure_code
failure_message
completed_phases
resume_from_phase
retry_safe
restore_required
cleanup_required
current_taxonomy_remains_active
scheduler_guard_restored
```

The full production DB backup is not restored automatically by the orchestrator.

Validation-only recovery is available when rebuilt facts already exist but
cleanup, watermark finalization, or rebuild evidence finalization did not reach
`READY_TO_ACTIVATE`. It applies the existing guarded EC cleanup when safe and
then calls the existing whole-range validation/evidence/watermark finalizer
without rerunning DC or EC loaders.

## Backup Policy

The policy is:

```text
ONE_FULL_BACKUP_PER_DEPLOYMENT
```

Runtime and backup artifacts belong under:

```text
temp/
```

A resumed run must reuse the deployment's existing verified backup. Config
backups used by activation remain separate and small.

## Delta Rebuild

`DELTA_REBUILD` is a supported planner and execution-backend mode for ordinary
monthly taxonomy changes that pass delta safety gates. Details are documented in:

```text
docs/datacenter_taxonomy_delta_rebuild.md
```

## Scheduler UI

The Scheduler UI now exposes the unified taxonomy-change workflow through a
`Taxonomy` tab and removes the obsolete visible `Datacenter` tab. Details are
documented in:

```text
docs/scheduler_ui_taxonomy_change.md
```

The UI rebuild, resume, validate/finalize, and activation actions are guarded by
the same operation lock used by the CLI facades. Rebuild and resume use the
production service factory by default, while tests can still inject service
doubles through the page object.
