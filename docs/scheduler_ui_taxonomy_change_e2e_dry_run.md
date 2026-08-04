# Scheduler UI Taxonomy Change E2E Dry Run

## Classification

```text
DATACENTER_TAXONOMY_UI_END_TO_END_DRY_RUN_VERIFIED
```

This document records the isolated dry-run verification for the Scheduler UI
Datacenter taxonomy-change workflow.

## Scope

The verification covered the UI/controller path for:

```text
read-only taxonomy state inspection
guarded activation planning
activation confirmation invalidation model
Aktivoi button gating
guarded activation backend execution
ALREADY_ACTIVE idempotency
operation artifact creation
```

The tested activation path used `activate_taxonomy_change`, which delegates to
the guarded activation backend. The UI does not update the active taxonomy or
Scheduler taxonomy config keys directly.

## Isolated Inputs

The dry-run test fixture uses only temporary files:

```text
active_taxonomy_v1.csv
proposed_taxonomy_v2.csv
analysis_test.sqlite
scheduler_config_test.json
watchlist_test.txt
temp/datacenter_taxonomy_ui_e2e_dry_run/evidence/
```

The synthetic database contains the minimum accepted production-like evidence:

```text
current active taxonomy = DC_TAXONOMY_FULL_V1
proposed taxonomy = DC_TAXONOMY_FULL_V2
deployment status = READY_TO_ACTIVATE
dc fact heads >= 2026-07-31
ec fact heads >= 2026-07-31
canonical EC watermark heads >= 2026-07-31
canonical EC watermark lineage = proposed taxonomy_version_id
coverage_status=OK
parity_status=OK
```

## Activation Gate

`Aktivoi` remains disabled until all of the following are true:

```text
orchestration_status=READY_TO_ACTIVATE
activation_plan_status=READY_TO_ACTIVATE
safe_to_activate=true
blocking_errors=[]
activation confirmation key matches the current activation plan
```

Changing the effective activation plan changes the confirmation key and makes
the previous confirmation stale.

## Verified Result

The UI activation test verified:

```text
Scheduler config transitioned from V1 to V2
DB active taxonomy transitioned from V1 to V2
deployment transitioned to ACTIVE
activation_result.json operation artifact was created
post-activation activation plan reports ALREADY_ACTIVE
ALREADY_ACTIVE does not re-enable the activation button
```

## Negative Scope

No production action is part of this dry run:

```text
no production DB write
no production Scheduler config write
no scheduler run
no Datacenter pipeline run
no Stage 2 run
no EC refresh or backfill
no migration apply against production
no production backup or restore
no watchlist modification
```

## Verification Commands

Focused tests:

```bash
python3 -m pytest tests/test_stock_update_scheduler_ui.py -q
python3 -m pytest tests/test_datacenter_taxonomy_operation_log.py tests/test_datacenter_taxonomy_change_orchestrator.py tests/test_datacenter_taxonomy_replacement.py -q
```
