# Datacenter Taxonomy Activation Config Transition

## Classification

```text
DATACENTER_TAXONOMY_ACTIVATION_TRANSITION_PLAN_FIXED
```

This document describes the activation contract fixed after the V2 EC cleanup
and finalization. No production activation, scheduler run, pipeline run, EC
loader, rebuild, production DB write, production config write, migration, backup,
restore, or taxonomy CSV edit occurred as part of this backend contract change.

## Problem

Activation planning previously treated the current production scheduler
configuration as if it already had to point to the proposed taxonomy. That was
backwards for a guarded transition.

Before activation, the safe state is:

```text
DB active taxonomy=DC_TAXONOMY_FULL_V1
scheduler Datacenter taxonomy=DC_TAXONOMY_FULL_V1
scheduler EC taxonomy=DC_TAXONOMY_FULL_V1
deployment=READY_TO_ACTIVATE
```

After activation, the intended state is:

```text
DB active taxonomy=DC_TAXONOMY_FULL_V2
scheduler Datacenter taxonomy=DC_TAXONOMY_FULL_V2
scheduler EC taxonomy=DC_TAXONOMY_FULL_V2
deployment=ACTIVE
```

A coherent V1 scheduler configuration is therefore a required precondition, not
a blocking error.

## Read-Only Planner Contract

The planner distinguishes current and proposed state:

```bash
python3 -m rawcandle.cli.plan_datacenter_taxonomy_activation \
  --analysis-db /home/kalle/projects/rawcandle/data/analysis.db \
  --ecosystem DATACENTER \
  --deployment-id 1 \
  --current-taxonomy-version DC_TAXONOMY_FULL_V1 \
  --current-taxonomy-csv data/datacenter_ecosystem_taxonomy_full_v1.csv \
  --proposed-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --proposed-taxonomy-csv data/datacenter_taxonomy_full_v2.csv \
  --required-signal-date 2026-07-31 \
  --scheduler-config scheduler_config.json \
  --format json
```

The planner verifies the current scheduler state:

```text
current_scheduler_taxonomy_status=EXPECTED_CURRENT_V1
current_scheduler_datacenter_version=DC_TAXONOMY_FULL_V1
current_scheduler_ec_version=DC_TAXONOMY_FULL_V1
current_scheduler_config_safe_to_transition=true
```

It then builds the proposed V2 scheduler configuration in memory and validates
it with the real scheduler config loader:

```text
proposed_scheduler_taxonomy_status=VALID
proposed_scheduler_config_safe=true
config_transition_required=true
scheduler_changed_keys=[
  datacenter_taxonomy_csv,
  datacenter_taxonomy_version,
  ec_source_layer_taxonomy_csv,
  ec_source_layer_taxonomy_version
]
scheduler_unexpected_changed_keys=[]
```

The planner does not write `scheduler_config.json`.

## Preserved Database Gates

The scheduler transition check is additive. It does not weaken database
activation gates:

```text
deployment READY_TO_ACTIVATE
DC rebuild OK
EC rebuild OK
coverage OK
parity OK
mismatch count zero
stale rows zero
V2 DC fact heads complete
V2 EC fact heads complete
DC watermark evidence belongs to V2
EC watermark lineage belongs to V2
V2 source hash matches loaded metadata
V1 active
V2 inactive
```

The ready state is:

```text
activation_plan_status=READY_TO_ACTIVATE
safe_to_activate=true
blocking_errors=[]
current_taxonomy_version=DC_TAXONOMY_FULL_V1
proposed_taxonomy_version=DC_TAXONOMY_FULL_V2
current_scheduler_taxonomy_status=EXPECTED_CURRENT_V1
proposed_scheduler_taxonomy_status=VALID
config_transition_required=true
```

## Guarded Apply Contract

`apply_datacenter_taxonomy_activation` must rerun the activation plan immediately
before production writes. A successful guarded activation sequence is:

```text
1. Verify exact expected V1 DB and scheduler starting state.
2. Create scheduler-config backup under repository temp/.
3. Build and validate V2 config in memory.
4. Begin narrow DB activation transaction.
5. Mark V2 active.
6. Mark V1 inactive or superseded.
7. Mark deployment ACTIVE.
8. Record activation time and evidence.
9. Write only the four taxonomy config keys.
10. Validate persisted config using the real config loader.
11. Verify DB and scheduler are now consistently V2.
12. Complete successfully.
```

Activation apply must not run scheduler, Datacenter pipeline stages, EC loaders,
refresh, backfill, or rebuild.

## Compensating Rollback

SQLite database writes and scheduler config writes are separate resources. The
activation command therefore reports explicit rollback fields:

```text
activation_db_status
activation_config_status
activation_consistency_status
activation_rollback_attempted
activation_rollback_status
activation_error
config_backup_path
```

Failure behavior:

```text
DB activation failure before config write
  -> rollback DB transaction
  -> leave config on V1

Config write or config validation failure
  -> restore scheduler config backup
  -> rollback DB transaction
  -> leave DB V1 active, V2 inactive, deployment READY_TO_ACTIVATE

Final consistency verification failure
  -> restore scheduler config backup
  -> restore DB activation state to V1 active, V2 inactive, deployment READY_TO_ACTIVATE
```

No normal activation result may leave:

```text
DB V2 / config V1
DB V1 / config V2
Datacenter config V2 / EC config V1
```

## Idempotency And Mixed States

Supported states:

```text
DB=V1, config=V1, deployment=READY_TO_ACTIVATE
  -> READY_TO_ACTIVATE

DB=V2, config=V2, deployment=ACTIVE
  -> ALREADY_ACTIVE from planner
  -> NO_CHANGE from apply
```

Blocked states:

```text
DB=V2, config=V1
DB=V1, config=V2
Datacenter config=V2, EC config=V1
configured version/path mismatch
unexpected third taxonomy
missing or unreadable taxonomy CSV
taxonomy CSV internal version mismatch
source-hash mismatch
```

Mixed states are not silently repaired by the normal activation command. They
require an explicit recovery task with its own evidence and confirmations.
