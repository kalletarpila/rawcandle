# Datacenter Taxonomy V2 Activation - 2026-08-04

## Final Classification

```text
DATACENTER_V2_ACTIVATION_VERIFIED
```

Backend commit:

```text
d89c7acf719c6c42dbb19f3616209edcbebf47d0
Fix Datacenter taxonomy activation transition plan
```

Activation target:

```text
ecosystem=DATACENTER
deployment_id=1
current_taxonomy_version=DC_TAXONOMY_FULL_V1
proposed_taxonomy_version=DC_TAXONOMY_FULL_V2
required_signal_date=2026-07-31
```

## Source Verification

Repository state before activation:

```text
branch=chore/ignore-backups
HEAD=d89c7acf719c6c42dbb19f3616209edcbebf47d0
origin/chore/ignore-backups=d89c7acf719c6c42dbb19f3616209edcbebf47d0
```

Input hashes:

```text
data/datacenter_ecosystem_taxonomy_full_v1.csv=1ad6ef41b91ef429174090bfcd338acf1e79680d939b4b788c834a79c73e9e5d
data/datacenter_taxonomy_full_v2.csv=178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1
temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/analysis_before_datacenter_v2_full_rebuild.sqlite=ef63868f55073dd3a9eedccea5097871446b02af1577f8c4659fe6dd325db3ea
```

## Evidence Directory

```text
temp/datacenter_taxonomy_v2_activation_20260804T090051Z/
```

Key artifacts:

```text
scheduler_config.before_activation_guard.json
scheduler_guard_apply.json
pre_activation_snapshot.json
final_activation_plan_pre_apply.json
activation_apply.json
scheduler_config.json.before_taxonomy_activation_20260804T090251Z.json
post_activation_snapshot_guarded.json
idempotency_plan_after_activation.json
scheduler_guard_restore.json
final_activation_snapshot.json
```

## Scheduler Guard

Before activation, only `skip_next_run` was changed:

```text
guard_status=APPLIED
backup_path=temp/datacenter_taxonomy_v2_activation_20260804T090051Z/scheduler_config.before_activation_guard.json
backup_sha256=f5cb0c2ae125b5eb43a7e4b2806bbd6953a4607dded6917c189e81db12cdf595
changed_keys=[skip_next_run]
unexpected_changed_keys=NONE
skip_next_run_before=false
skip_next_run_after=true
datacenter_taxonomy_version_after=DC_TAXONOMY_FULL_V1
ec_source_layer_taxonomy_version_after=DC_TAXONOMY_FULL_V1
```

After all post-activation checks passed, only `skip_next_run` was restored:

```text
guard_restore_status=RESTORED
changed_keys=[skip_next_run]
unexpected_changed_keys=NONE
skip_next_run_before=true
skip_next_run_after=false
datacenter_taxonomy_version_after=DC_TAXONOMY_FULL_V2
ec_source_layer_taxonomy_version_after=DC_TAXONOMY_FULL_V2
datacenter_stage2_incremental_enabled_after=true
datacenter_stage2_overlap_trading_days_after=5
```

## Active Writer Checks

Host-level process checks found no active scheduler, Datacenter, EC taxonomy,
migration, or `analysis.db` command-line process before activation. `fuser`
reported no open user for `analysis.db`; WAL and SHM files did not exist.

The same no-active-user result was checked after activation.

## Pre-Activation State

Read-only snapshot before activation:

```text
V1 active=true
V2 active=false
deployment_status=READY_TO_ACTIVATE
activation_status=NOT_ACTIVE
scheduler_datacenter_taxonomy=DC_TAXONOMY_FULL_V1
scheduler_ec_taxonomy=DC_TAXONOMY_FULL_V1
skip_next_run=true
stale_v1_ec_rows_in_replacement_range=0
```

V2 fact heads already covered the required date:

```text
DC V2 fact heads=2026-07-31
EC V2 fact heads=2026-07-31
canonical EC V2 watermark heads=2026-07-31
```

Coverage and parity evidence were already accepted:

```text
dc_rebuild_status=OK
ec_rebuild_status=OK
coverage_status=OK
parity_status=OK
total_mismatch_count=0
```

## Final Read-Only Activation Plan

Command:

```bash
python3 -m rawcandle.cli.plan_datacenter_taxonomy_activation --analysis-db /home/kalle/projects/rawcandle/data/analysis.db --ecosystem DATACENTER --deployment-id 1 --current-taxonomy-version DC_TAXONOMY_FULL_V1 --current-taxonomy-csv data/datacenter_ecosystem_taxonomy_full_v1.csv --proposed-taxonomy-version DC_TAXONOMY_FULL_V2 --proposed-taxonomy-csv data/datacenter_taxonomy_full_v2.csv --required-signal-date 2026-07-31 --scheduler-config scheduler_config.json --format json
```

Result:

```text
exit_code=0
activation_plan_status=READY_TO_ACTIVATE
safe_to_activate=true
blocking_errors=[]
current_db_taxonomy_status=EXPECTED_CURRENT
current_scheduler_taxonomy_status=EXPECTED_CURRENT_V1
current_scheduler_config_safe_to_transition=true
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

## Activation Apply

The guarded activation apply was run exactly once.

Command:

```bash
python3 -m rawcandle.cli.apply_datacenter_taxonomy_activation --analysis-db /home/kalle/projects/rawcandle/data/analysis.db --ecosystem DATACENTER --deployment-id 1 --current-taxonomy-version DC_TAXONOMY_FULL_V1 --current-taxonomy-csv data/datacenter_ecosystem_taxonomy_full_v1.csv --proposed-taxonomy-version DC_TAXONOMY_FULL_V2 --proposed-taxonomy-csv data/datacenter_taxonomy_full_v2.csv --required-signal-date 2026-07-31 --scheduler-config scheduler_config.json --expected-scheduler-taxonomy-version DC_TAXONOMY_FULL_V2 --expected-scheduler-taxonomy-csv data/datacenter_taxonomy_full_v2.csv --confirm-activate-taxonomy-version DC_TAXONOMY_FULL_V2 --expected-current-scheduler-taxonomy-version DC_TAXONOMY_FULL_V1 --expected-current-scheduler-taxonomy-csv data/datacenter_ecosystem_taxonomy_full_v1.csv --target-scheduler-taxonomy-csv data/datacenter_taxonomy_full_v2.csv --config-backup-dir temp/datacenter_taxonomy_v2_activation_20260804T090051Z --format json
```

Result:

```text
exit_code=0
activation_apply_status=ACTIVE
activation_performed=true
activation_db_status=OK
activation_config_status=OK
activation_consistency_status=OK
activation_rollback_attempted=false
activation_rollback_status=NOT_NEEDED
activation_error=null
```

Activation-created scheduler config backup:

```text
config_backup_path=temp/datacenter_taxonomy_v2_activation_20260804T090051Z/scheduler_config.json.before_taxonomy_activation_20260804T090251Z.json
config_backup_sha256=6c7602cdbf2a0eb36ccbad1d4f9fc99a392c049fcd8e1ca63407a78996b5510b
```

Config transition:

```text
changed_keys=[
  datacenter_taxonomy_csv,
  datacenter_taxonomy_version,
  ec_source_layer_taxonomy_csv,
  ec_source_layer_taxonomy_version
]
unexpected_changed_keys=NONE
```

## Post-Activation Guarded Verification

While `skip_next_run=true`, read-only verification confirmed:

```text
V1 active=false
V2 active=true
deployment_status=ACTIVE
activation_status=ACTIVE
scheduler_datacenter_taxonomy=DC_TAXONOMY_FULL_V2
scheduler_ec_taxonomy=DC_TAXONOMY_FULL_V2
skip_next_run=true
datacenter_stage2_incremental_enabled=true
datacenter_stage2_overlap_trading_days=5
```

Only the intended taxonomy config keys changed relative to pre-activation:

```text
unexpected_changed_keys=NONE
scheduler_non_taxonomy_unchanged=true
```

Canonical fact and watermark non-impact:

```text
fact_hashes_unchanged=true
dc_watermarks_unchanged=true
ec_watermarks_unchanged=true
stale_v1_ec_rows_in_replacement_range=0
```

## Idempotency Plan

The planner was run again after activation. No second apply was run.

```text
activation_plan_status=ALREADY_ACTIVE
blocking_errors=[]
config_transition_required=false
scheduler_changed_keys=[]
scheduler_unexpected_changed_keys=[]
safe_to_activate=false
```

`safe_to_activate=false` is the implementation's no-op-safe value for
`ALREADY_ACTIVE`.

## Final State

Final read-only production state:

```text
deployment_status=ACTIVE
activation_status=ACTIVE
DC_TAXONOMY_FULL_V1 status=INACTIVE is_active=0
DC_TAXONOMY_FULL_V2 status=ACTIVE is_active=1
```

Final scheduler config:

```text
config_valid=true
skip_next_run=false
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V2
datacenter_taxonomy_csv=data/datacenter_taxonomy_full_v2.csv
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V2
ec_source_layer_taxonomy_csv=data/datacenter_taxonomy_full_v2.csv
datacenter_stage2_incremental_enabled=true
datacenter_stage2_overlap_trading_days=5
```

Final scheduler config SHA-256:

```text
scheduler_config.json=f3ecdc488c0b08bea7ce22d757056bfb7539723fee994589c27989ba33c83089
```

Watchlist evidence:

```text
watchlist_sha256=5dfa86d390202fb6bd561fad43967a382de9012ccfbb01f5a725042eefd087e8
watchlist_unchanged_during_task=true
```

## Explicit Non-Actions

The following were not performed:

```text
scheduler run
Datacenter pipeline run
Datacenter stage run
EC loader run
EC refresh/backfill/rebuild
taxonomy cleanup
migration apply
external fetch
new full production DB backup
full DB restore
taxonomy CSV edit
watchlist edit
unrelated cleanup
```

Production writes were limited to:

```text
taxonomy activation state in analysis.db
deployment activation state/evidence in analysis.db
four scheduler taxonomy configuration keys
temporary skip_next_run guard apply/restore
```
