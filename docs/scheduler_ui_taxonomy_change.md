# Scheduler UI Taxonomy Change

## Classification

```text
DATACENTER_TAXONOMY_SCHEDULER_UI_IMPLEMENTED
```

No production taxonomy change, Scheduler run, Datacenter pipeline run, Stage 2
run, EC work, cleanup, finalization, activation, migration apply, production DB
write, Scheduler config write, production backup, restore, taxonomy CSV edit,
watchlist edit, or production-backup packaging occurred in this task.

## Old Datacenter Tab Inventory

The retired `Datacenter` tab in `dev_tools/stock_update_scheduler_ui.py`
contained UI-only controls for:

```text
price_db field -> REMOVE from visible UI
analysis_db field -> KEEP_ELSEWHERE in Scheduler tab
taxonomy_csv field -> MOVE_TO_TAXONOMY_TAB as proposed CSV
taxonomy_version field -> REMOVE from visible UI
market/signal/start/base-date fields -> REMOVE from visible UI
output_dir field -> REMOVE from visible UI
expected ticker/group/synthetic counts -> REMOVE from visible UI
watchlist_file field -> RETIRED_COMPATIBILITY_ONLY
Plan Datacenter button -> REMOVE
Run Datacenter Pipeline button -> REMOVE
Run Audit button -> REMOVE
Watermarks button -> REMOVE
report path listing -> REMOVE
Datacenter command/status fields -> REMOVE
```

The underlying legacy command-builder helpers remain as retired compatibility
helpers, but the visible Scheduler UI no longer registers the obsolete
Datacenter tab or invokes individual Datacenter pipeline, audit, or watermark
commands from it.

Scheduler operational status, normal Scheduler logs, skip-next-run controls,
market selection, and config save/load remain in the Scheduler tab.

Legacy Datacenter dashboard/enrichment config keys remain load-compatible
through the existing Scheduler config contract. They are not exposed as new
taxonomy-change controls.

## New Taxonomy Tab

The visible tabs are now:

```text
Scheduler
Taxonomy
```

The Taxonomy tab is the single UI entry point for Datacenter taxonomy changes.
It uses the unified orchestrator backend introduced by:

```text
4e1707a Implement Datacenter taxonomy change orchestrator
c5bc288 Implement Datacenter taxonomy delta rebuild backend
```

The tab does not duplicate taxonomy diff, plan hashing, rebuild-mode selection,
validation, cleanup, watermark, activation, or recovery logic.

## Active Taxonomy Display

Opening the tab performs read-only inspection. It does not create a deployment,
operation, log, archive, database write, or config write.

The active section displays, when available:

```text
active taxonomy version
active taxonomy CSV path
active taxonomy SHA-256
active deployment ID
active deployment status
ticker count
group count
synthetic group count
DC fact head
EC fact head
DC watermark head
EC watermark head
Scheduler Datacenter taxonomy version
Scheduler EC taxonomy version
DB/config consistency status
blocking errors
```

Mixed DB/config taxonomy state is shown as a blocking status.

## Proposed Workflow

The proposed taxonomy section contains:

```text
proposed taxonomy CSV path
rebuild mode: AUTO, DELTA_REBUILD, FULL_REBUILD
optional date_from
optional date_to
Valmistele
Päivitä tila
Vahvista suunnitelma
```

Selecting or typing a CSV path does not normalize, edit, copy, or load that CSV.
Preparation calls the unified `prepare_taxonomy_change` backend.

The plan display renders:

```text
deployment ID
current/proposed taxonomy versions
current/proposed hashes
date range
recommended and selected rebuild mode
execution class
report-status-only safety
Datacenter pipeline / Stage 2 required flags
plan hash
delta safety
blocking reasons
diff counts
affected/unaffected scope counts
relative work estimate
```

Long detailed lists stay in backend JSON artifacts and are rediscoverable from
operation evidence rather than dumped into a fixed label.

## Confirmation And Gating

The rebuild confirmation binds to:

```text
deployment ID
proposed taxonomy version
proposed source hash
date_from
date_to
selected rebuild mode
execution class
plan hash
```

Changing the prepared plan invalidates the confirmation and disables rebuild
until the current plan is confirmed again. This includes changes between
ordinary delta/full execution and the specialized `REPORT_STATUS_ONLY`
execution class.

For `REPORT_STATUS_ONLY` plans, the UI explicitly shows:

```text
Muutosluokka: REPORT_STATUS_ONLY
Laskennallinen rebuild: ei
Datacenter pipeline: ei
Stage 2: ei
DC-faktat: kopioidaan uudelle lineagelle
EC-faktat: muodostetaan uudelle lineagelle
```

The visible rebuild action calls the unified `execute_taxonomy_rebuild`
function. It does not call individual DC rebuild commands, EC rebuild commands,
cleanup commands, finalization commands, watermark commands, direct SQL, or
direct activation replacement commands.

Unsafe force/ignore/activate-anyway controls are not present.

## Status, Resume, And Activation

The status view exposes backend status fields:

```text
normalized_orchestration_status
safe_next_action
per_phase_status
activation_readiness
```

Resume is enabled when inspection reports:

```text
safe_next_action=resume_from_failed_phase
```

Validation/finalization is enabled when inspection reports:

```text
safe_next_action=validation_only_recovery
```

Both actions call the unified backend and are protected by the durable taxonomy
operation lock. They do not invoke individual Datacenter or EC phase commands
from UI code.

Activation planning is available only when backend inspection reports:

```text
normalized_orchestration_status=READY_TO_ACTIVATE
```

The activation confirmation binds to the guarded activation backend plan:

```text
deployment ID
current taxonomy version
proposed taxonomy version
required signal date
DB taxonomy status
Scheduler taxonomy status
proposed Scheduler taxonomy status
expected Scheduler changed keys
blocking errors
safe_to_activate
```

`Aktivoi` is enabled only when:

```text
orchestration_status=READY_TO_ACTIVATE
activation_plan_status=READY_TO_ACTIVATE
safe_to_activate=true
blocking_errors=[]
activation confirmation matches the current activation plan
no taxonomy operation is active
```

The visible activation action calls the unified guarded
`activate_taxonomy_change` backend. It does not write taxonomy state directly.
The backend updates the DB active taxonomy state and the four Scheduler taxonomy
config keys only after the plan is safe, validates the scheduler transition, and
rolls back DB/config changes on activation failure.

`READY_TO_ACTIVATE` and `ACTIVE` remain backend states. Duplicate rebuild and
activation are disabled by default unless a different proposed taxonomy is
prepared and confirmed.

## Operation Logs

Taxonomy-change operations use a durable filesystem operation model under:

```text
temp/datacenter_taxonomy_changes/
  deployment_<deployment_id>/
    operation_<operation_id>/
```

Each operation has:

```text
operation.json
taxonomy_change.log
artifact_manifest.json
approved JSON artifacts
optional packages/
```

The operation manifest stores:

```text
operation_id
deployment_id
operation_type
started_at_utc
completed_at_utc
status
failed_phase
resume_from_phase
evidence_root
primary_log_path
artifact_manifest_path
```

Failed and resumed attempts are separate operations with separate logs.
Automatic deletion is disabled.

A single cross-process taxonomy operation lock is stored under the same evidence
root. Rebuild, resume, validation/finalization, and activation acquire the lock
before state-changing work. A live lock disables competing operations; a stale
dead-process lock can be recovered by the lock backend.

## Log Viewing And Downloads

The Taxonomy tab exposes:

```text
Näytä loki
Lataa loki
Lataa evidence-paketti
```

Operation lookup is by trusted `deployment_id + operation_id`, not by arbitrary
user-supplied filesystem paths. The newest operation is selected by default.

Log reading is bounded and includes:

```text
source path
last modified timestamp
text chunk
next offset
truncation flag
```

The download-log action returns the exact selected primary log plus a suggested
download filename and SHA-256. Missing logs produce visible non-destructive
errors.

## Evidence Package

Evidence packages are generated only on explicit request. Package generation:

```text
uses deterministic ordering
stays under temp/
verifies paths stay under the approved evidence root
rejects path traversal and symlink escape
does not modify source evidence
is idempotent
cleans only its own failed temporary archive
```

The ZIP includes approved artifacts such as:

```text
taxonomy_change.log
operation.json
artifact_manifest.json
prepare.json
plan.json
run_summary.json
activation_result.json
other safe JSON summaries
```

The generated `package_manifest.json` contains:

```text
deployment_id
operation_id
operation_type
operation_status
created_at_utc
included files
per-file SHA-256
excluded files
exclusion reasons
```

Excluded by default:

```text
production SQLite databases
full production DB backups
WAL files
SHM files
backup/config artifacts
arbitrary files outside the evidence root
source-code files outside the operation root
```

Activation config backup references should be represented as metadata, not
downloaded as unrestricted Scheduler config contents.

## Restart Rediscovery

After UI restart, the Taxonomy tab can reconstruct:

```text
read-only active taxonomy state
selected deployment inspect state
operation list
primary log metadata
artifact metadata
latest operation selection
available log/package actions
```

The durable deployment state and operation manifests are the source of truth.

## Background Execution

The UI provides a reusable `start_taxonomy_background_operation` helper for
long-running taxonomy actions. Production wiring should run long operations
through that mechanism so the UI event loop remains responsive and the durable
operation log remains available while the operation is running.

## Next Dry Run

The next safe task is an end-to-end UI dry-run using:

```text
temporary analysis DB
temporary Scheduler config
test taxonomy CSV
temporary evidence root
mocked or injected rebuild services
```

That dry-run should not touch production DB, production config, Scheduler,
Datacenter pipeline, Stage 2, EC work, cleanup, or production backups.
