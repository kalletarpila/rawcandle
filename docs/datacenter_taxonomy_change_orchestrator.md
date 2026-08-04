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

Version 1 supports only:

```text
rebuild_mode=FULL_REBUILD
```

`DELTA_REBUILD` is part of the interface but intentionally returns an explicit
unsupported-mode error.

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
finalize_ec_taxonomy_rebuild_validation delegation
plan_taxonomy_activation
activate_taxonomy_change
inspect_taxonomy_change
```

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
  --confirm-rebuild-mode FULL_REBUILD \
  --confirm-plan-hash <plan_hash> \
  --format json
```

Activation facade:

```bash
python3 -m rawcandle.cli.activate_datacenter_taxonomy_change ...
```

The activation facade delegates to the existing guarded activation backend. It
does not add a second activation implementation.

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
7. Derives the full rebuild range.
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

Normal monthly workflow requires:

```text
structural_change_detected=false
```

If layers or subindustries are added or removed, the normal workflow is blocked
with a structural-change error. Rename detection is represented as an explicit
future field; version 1 reports renames as empty and blocks based on added or
removed structures.

## Plan Hash

The deterministic plan includes:

```text
deployment_id
ecosystem
current taxonomy version/source/hash
proposed taxonomy version/source/hash
rebuild_mode
date_from
date_to
taxonomy_diff
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

## Full-Rebuild Phase Order

The unified execution facade represents this order:

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

## Future Delta Rebuild

`DELTA_REBUILD` is now a named rebuild mode, but it is unsupported in version 1.
The taxonomy diff already exposes affected tickers and groups so the next phase
can implement delta planning and execution without changing the deployment
contract.

## Future Scheduler UI

The new JSON-compatible prepare and inspect outputs are suitable for a future
Scheduler UI workflow. This phase does not modify Scheduler UI and does not
remove the existing Datacenter UI tab.
