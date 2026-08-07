# Datacenter Taxonomy V3 AI Software Layer Production Change Plan

## Purpose And Scope

This is a read-only production taxonomy-change planning and preflight report for
later activation of `DC_TAXONOMY_FULL_V3`.

No V3 activation, production taxonomy-change execution, production database
mutation, scheduler config update, watermark update, Datacenter report run,
Datacenter pipeline run, EC job, market fetch, production backup, or full pytest
run was performed for this plan.

## Current State Observed

Audit time:

```text
2026-08-07 Europe/Helsinki
```

Current active taxonomy observed from readonly EC metadata:

```text
DC_TAXONOMY_FULL_V2_1
taxonomy_version_id=3
source_reference=data/datacenter_taxonomy_full_v2_1.csv
source_hash=2e27c6e68aa22c53c04e123f79744058b39a6a22b465634fda7510971c3159ef
status=ACTIVE
is_active=1
```

Inactive Datacenter taxonomy versions observed:

```text
DC_TAXONOMY_FULL_V1
DC_TAXONOMY_FULL_V2
```

Current scheduler taxonomy config observed from `scheduler_config.json`:

```text
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V2_1
datacenter_taxonomy_csv=data/datacenter_taxonomy_full_v2_1.csv
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V2_1
ec_source_layer_taxonomy_csv=data/datacenter_taxonomy_full_v2_1.csv
skip_next_run=false
```

Current canonical active heads observed from readonly DB metadata:

```text
DC V2.1 canonical fact head=2026-08-06
EC V2.1 canonical fact head=2026-08-06
canonical EC watermarks for ticker/group/synthetic/index=2026-08-06
```

The later production run should recompute the final `date_to` from the active
source head at execution time. Based on the observed state, the current planning
range is:

```text
date_from=2025-08-01
date_to=2026-08-06
```

## V3 Draft Inputs

V3 draft CSV:

```text
temp/datacenter_taxonomy_v3_ai_software_layer/datacenter_taxonomy_full_v3.csv
```

V3 pre-activation audit:

```text
docs/datacenter_taxonomy_v3_ai_software_layer_pre_activation_audit.md
```

Validator result:

```text
taxonomy_version=DC_TAXONOMY_FULL_V3
taxonomy_rows=384
unique_tickers=278
layer_count=17
subindustry_count=43
core_rows=242
extended_rows=125
watch_only_rows=17
duplicate_rows=0
validation_status=OK
```

V3 source hash from the read-only taxonomy-change planner:

```text
d64f39bc3ec70ddde887d9d438736fe5c83553bc0d67b728d98d5c0514eed977
```

## V3 Change Summary

Compared with active `DC_TAXONOMY_FULL_V2_1`:

```text
current_row_count=350
proposed_row_count=384
current_ticker_count=257
proposed_ticker_count=278
current_layer_count=16
proposed_layer_count=17
current_subindustry_count=37
proposed_subindustry_count=43
added_ticker_count=21
removed_ticker_count=0
added_membership_count=34
removed_membership_count=0
primary_membership_change_count=0
secondary_membership_change_count=34
affected_ticker_count=33
affected_group_count=7
changed_report_group_statuses=0
changed_role_weights=0
```

New layer:

```text
AI software & data workloads
```

New subindustries:

```text
Enterprise AI operating platforms
AI data cloud / vector data platforms
AI observability / agent operations
Agentic automation / workflow AI
AI edge delivery / inference gateways
Vertical AI applications / monetization engines
```

New ticker entities:

```text
ADBE, AI, AKAM, APP, BBAI, CFLT, CRM, DUOL, FSLY, GTLB, IBM, MDB,
MNDY, NET, PATH, PLTR, SOUN, TDC, TEAM, TEM, UPST
```

Existing primary memberships are preserved. `PLTR` is a `CORE` primary in:

```text
AI software & data workloads / Enterprise AI operating platforms
```

CORE AI-layer secondary memberships:

```text
SNOW, ESTC, DDOG, DT, NOW
```

EXTENDED AI-layer secondary memberships:

```text
MSFT, GOOGL, AMZN, ORCL, PANW, FTNT, CRWD, GTLB
```

`GTLB` is the 13th secondary membership. It also has an `EXTENDED` primary row
under `Agentic automation / workflow AI`.

WATCH_ONLY inclusions:

```text
BBAI, FSLY, SOUN
```

Explicit exclusions absent from the V3 AI layer:

```text
AAPL, TSLA, META, NFLX, SHOP, UBER, ABNB, SEZL, RDDT, HOOD
```

## Change Execution Class

The V3 change is:

```text
change_execution_class=FULL_REBUILD
recommended_rebuild_mode=FULL_REBUILD
selected_rebuild_mode=FULL_REBUILD
report_status_only_safe=false
computational_rebuild_required=true
datacenter_pipeline_required=true
stage2_required=true
delta_safe=false
```

It must not be treated as `REPORT_STATUS_ONLY`. Report-status-only is blocked
because V3 adds ticker entities, membership rows, a layer, subindustries, and
secondary memberships. Explicit delta is blocked because structural changes
require the full structural replacement workflow.

## Affected Tables

Taxonomy metadata and deployment state affected later:

```text
ec_taxonomy_version
ec_entity
ec_entity_alias
ec_membership
ec_taxonomy_change_deployment
```

Canonical DC fact tables affected later:

```text
dc_ticker_swing_signal_daily
dc_group_swing_signal_daily
dc_group_synthetic_ohlc_daily
dc_group_index_daily
dc_pipeline_watermark
```

Canonical EC fact tables affected later:

```text
ec_ticker_signal_daily
ec_group_signal_daily
ec_group_synthetic_ohlc_daily
ec_group_index_daily
ec_pipeline_watermark
```

Scheduler config keys affected only during the later activation step:

```text
datacenter_taxonomy_csv
datacenter_taxonomy_version
ec_source_layer_taxonomy_csv
ec_source_layer_taxonomy_version
```

Downstream outputs affected after activation:

```text
Datacenter daily report
Datacenter rolling 2/5/30 reports
pipeline audit outputs
decision-summary/report consumers that read taxonomy-scoped DC/EC facts
```

## Rebuild Scope

The code default rebuild start is:

```text
DEFAULT_DATACENTER_REBUILD_START_DATE=2025-08-01
```

The current observed active head is:

```text
2026-08-06
```

Expected later rebuild range if executed immediately from current state:

```text
2025-08-01..2026-08-06
```

The final later execution must use the active source head at that time. If the
normal scheduler advances V2.1 before V3 execution, `date_to` must advance too,
and the prepare plan hash and confirmations must be regenerated.

Expected counts from the V3 plan:

```text
ticker_rows=278
group_rows=61
synthetic_ohlc_rows=61
index_rows=61
taxonomy_rows=384
membership_rows=384
```

Computational impact:

```text
ticker signal rebuild required=yes
group signal rebuild required=yes
group synthetic OHLC rebuild required=yes
group index rebuild required=yes
EC bridge/rebuild required=yes
downstream reports affected=yes
```

## Expected Execution Phases

The unified facade phase model is:

```text
DRAFT
PLANNED
REBUILDING
VALIDATING
READY_TO_ACTIVATE
ACTIVATING
ACTIVE
```

For this structural V3 change, the later production execution should follow the
full rebuild order documented by the orchestrator:

```text
1. Rerun plan and confirmation checks.
2. Set scheduler guard.
3. Verify no active writer.
4. Create or validate one deployment backup.
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

Activation is a separate guarded step after `READY_TO_ACTIVATE`.

Post-activation work:

```text
switch scheduler taxonomy config during guarded activation
verify DB/scheduler consistency
run the next normal Datacenter report/pipeline path under V3 only after activation
verify post-activation report and decision-summary behavior
```

## Validation Gates

Required before activation:

```text
V3 CSV validation OK
taxonomy load validation OK
source hash matches loaded V3 metadata
deployment row exists and matches V3 source hash
active taxonomy remains expected current version before activation
scheduler config still points coherently to expected current taxonomy before activation
DC canonical fact heads cover required_signal_date
EC canonical fact heads cover required_signal_date
DC row coverage validation OK
group membership coverage validation OK
EC coverage validation OK
DC/EC parity validation OK
old-version EC cleanup evidence OK
whole-range stale-row validation OK
canonical EC watermark lineage finalized to V3
deployment statuses: dc_rebuild_status=OK, ec_rebuild_status=OK, coverage_status=OK, parity_status=OK
activation plan safe_to_activate=true
activation apply consistency verification OK
```

The activation planner also requires scheduler transition safety: only the four
taxonomy config keys should change.

## Stale-Row Risk Assessment

Risk:

```text
HIGH unless old-version EC cleanup completes before whole-range validation.
```

Historical evidence:

```text
docs/datacenter_taxonomy_v2_ec_full_rebuild_retry6_20260803.md
```

The V2 full EC rebuild completed all chunks with coverage and parity OK, but
whole-range validation failed because same-ecosystem EC rows existed in the
requested range with taxonomy ids other than the target taxonomy id.

The blocking stale counts in that failure were:

```text
ec_ticker_signal_daily=12272
ec_group_signal_daily=2808
ec_group_synthetic_ohlc_daily=2756
ec_group_index_daily=2808
```

The current stale-row validation code checks canonical EC fact tables for:

```text
ecosystem_id = target ecosystem
taxonomy_version_id <> target taxonomy_version_id
date between date_from and date_to
```

Therefore, after V3 metadata is loaded and V3 facts are rebuilt, existing V2.1
EC rows in the same date range would block V3 whole-range validation unless
the guarded cleanup phase deletes non-V3 EC rows first.

The unified V3 execution order now includes:

```text
OLD_EC_CLEANED before WHOLE_RANGE_VALIDATED
```

The cleanup planner/apply path exists and deletes only canonical EC rows for the
same ecosystem/date range whose `taxonomy_version_id` is not the target
taxonomy id. It validates the target fact hashes before and after cleanup and
records cleanup evidence into the deployment row. No cleanup was run in this
planning step.

Conclusion:

```text
The stale-row risk is known and handled by current tooling only if the later
run reaches and successfully applies OLD_EC_CLEANED before whole-range
validation. Skipping cleanup or running validation before cleanup would block
V3 readiness.
```

## Backup And Rollback Plan

Later production execution must use:

```text
backup_policy=ONE_FULL_BACKUP_PER_DEPLOYMENT
```

The production service factory creates or validates a SQLite backup under:

```text
<ec_source_layer_backup_dir or evidence_root>/taxonomy_change_backups/
```

The backup filename pattern is:

```text
analysis_taxonomy_change_<deployment_id>_<timestamp>.sqlite
```

A resumed run must reuse the deployment's existing verified backup via:

```text
--confirm-existing-backup-path
--confirm-existing-backup-sha256
```

If failure occurs before activation, the current active taxonomy should remain
active and scheduler taxonomy config should remain on the current taxonomy
after guard restoration. The orchestrator does not automatically restore the
full production DB backup; restore is a separate operator decision.

Activation creates its own scheduler config backup and must roll back config/DB
activation state only if the guarded activation apply fails consistency checks.

## Exact Later Commands

Do not run these commands in this planning step.

Read-only legacy planner used for this report:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m rawcandle.cli.plan_datacenter_taxonomy_change \
  --analysis-db data/analysis.db \
  --current-taxonomy-version DC_TAXONOMY_FULL_V2_1 \
  --current-taxonomy-csv data/datacenter_taxonomy_full_v2_1.csv \
  --proposed-taxonomy-version DC_TAXONOMY_FULL_V3 \
  --proposed-taxonomy-csv temp/datacenter_taxonomy_v3_ai_software_layer/datacenter_taxonomy_full_v3.csv \
  --ecosystem DATACENTER \
  --rebuild-start-date 2025-08-01
```

Later production prepare command:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m rawcandle.cli.prepare_datacenter_taxonomy_change \
  --analysis-db data/analysis.db \
  --ecosystem DATACENTER \
  --proposed-taxonomy-csv temp/datacenter_taxonomy_v3_ai_software_layer/datacenter_taxonomy_full_v3.csv \
  --date-from 2025-08-01 \
  --date-to <current_required_head_date> \
  --scheduler-config scheduler_config.json \
  --watchlist watchlists/datacenter_watchlist.txt \
  --evidence-root temp/datacenter_taxonomy_v3_ai_software_layer_production_<timestamp> \
  --rebuild-mode auto \
  --format json
```

Later production rebuild command, after prepare returns a deployment id, source
hash, date range, selected rebuild mode, and plan hash:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m rawcandle.cli.run_datacenter_taxonomy_change \
  --analysis-db data/analysis.db \
  --deployment-id <deployment_id> \
  --proposed-taxonomy-csv temp/datacenter_taxonomy_v3_ai_software_layer/datacenter_taxonomy_full_v3.csv \
  --date-to <current_required_head_date> \
  --scheduler-config scheduler_config.json \
  --watchlist watchlists/datacenter_watchlist.txt \
  --evidence-root temp/datacenter_taxonomy_v3_ai_software_layer_production_<timestamp> \
  --confirm-deployment-id <deployment_id> \
  --confirm-proposed-taxonomy-version DC_TAXONOMY_FULL_V3 \
  --confirm-proposed-source-hash <prepare_plan_proposed_source_sha256> \
  --confirm-date-from 2025-08-01 \
  --confirm-date-to <current_required_head_date> \
  --confirm-rebuild-mode FULL_REBUILD \
  --confirm-plan-hash <prepare_plan_hash> \
  --format json
```

Later activation planning command, only after rebuild returns
`READY_TO_ACTIVATE`:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m rawcandle.cli.plan_datacenter_taxonomy_activation \
  --analysis-db data/analysis.db \
  --ecosystem DATACENTER \
  --deployment-id <deployment_id> \
  --current-taxonomy-version DC_TAXONOMY_FULL_V2_1 \
  --current-taxonomy-csv data/datacenter_taxonomy_full_v2_1.csv \
  --proposed-taxonomy-version DC_TAXONOMY_FULL_V3 \
  --proposed-taxonomy-csv temp/datacenter_taxonomy_v3_ai_software_layer/datacenter_taxonomy_full_v3.csv \
  --required-signal-date <current_required_head_date> \
  --scheduler-config scheduler_config.json \
  --format json
```

Later activation apply command, only after activation plan reports
`safe_to_activate=true`:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m rawcandle.cli.activate_datacenter_taxonomy_change \
  --analysis-db data/analysis.db \
  --ecosystem DATACENTER \
  --deployment-id <deployment_id> \
  --current-taxonomy-version DC_TAXONOMY_FULL_V2_1 \
  --current-taxonomy-csv data/datacenter_taxonomy_full_v2_1.csv \
  --proposed-taxonomy-version DC_TAXONOMY_FULL_V3 \
  --proposed-taxonomy-csv temp/datacenter_taxonomy_v3_ai_software_layer/datacenter_taxonomy_full_v3.csv \
  --required-signal-date <current_required_head_date> \
  --scheduler-config scheduler_config.json \
  --expected-scheduler-taxonomy-version DC_TAXONOMY_FULL_V3 \
  --expected-scheduler-taxonomy-csv temp/datacenter_taxonomy_v3_ai_software_layer/datacenter_taxonomy_full_v3.csv \
  --confirm-activate-taxonomy-version DC_TAXONOMY_FULL_V3 \
  --expected-current-scheduler-taxonomy-version DC_TAXONOMY_FULL_V2_1 \
  --expected-current-scheduler-taxonomy-csv data/datacenter_taxonomy_full_v2_1.csv \
  --target-scheduler-taxonomy-csv temp/datacenter_taxonomy_v3_ai_software_layer/datacenter_taxonomy_full_v3.csv \
  --config-backup-dir temp/datacenter_taxonomy_v3_ai_software_layer_production_<timestamp> \
  --format json
```

## Go/No-Go Checklist

Go conditions for later production execution:

```text
working tree clean except approved local runtime artifacts
remote branch contains V3 draft, audit, and plan commits
current active DB taxonomy is still expected current version
scheduler Datacenter/EC taxonomy config still matches expected current version
V3 CSV hash matches reviewed source hash or changed source is re-reviewed
date_to chosen from current active source head
prepare plan selects FULL_REBUILD
prepare plan reports no blocking errors
deployment id and plan hash are recorded before rebuild
production backup is created or an existing backup is verified
no active scheduler/writer before writes
DC rebuild completes
EC chunked rebuild completes
old-version EC cleanup applies or reports NO_CHANGE with valid evidence
whole-range stale-row validation OK
coverage/parity OK
canonical EC watermarks finalized to V3
activation plan safe_to_activate=true
scheduler config transition changes only the four taxonomy keys
post-activation idempotency plan reports already active/no change
```

No-go conditions:

```text
active taxonomy is not DC_TAXONOMY_FULL_V2_1 at execution start
scheduler config is mixed or already partially transitioned
V3 source hash differs from reviewed draft without a new audit
prepare selects DELTA_REBUILD or REPORT_STATUS_ONLY
backup cannot be created/validated
active writer is detected
DC or EC fact heads do not cover required_signal_date
cleanup plan is blocked
whole-range stale-row validation reports stale DC or EC rows
coverage/parity fails
EC watermark lineage is not V3 after finalization
activation plan is blocked
```

## Unresolved Questions Or Blockers

No code blocker was identified for planning. Current tooling appears sufficient
to execute V3 as a full structural taxonomy change later.

Operational items still required before execution:

```text
choose final execution window
choose final evidence root
derive current_required_head_date immediately before prepare
record deployment id, V3 source hash, selected rebuild mode, and plan hash from prepare
verify production backup before writes
review cleanup candidate counts before OLD_EC_CLEANED applies
```

## Recommendation

The V3 AI software & data workloads draft is ready for later production
taxonomy-change execution planning and controlled preflight.

It is not ready for direct activation. It must go through the full structural
taxonomy-change workflow with DC rebuild, EC rebuild, old-version EC cleanup,
whole-range validation, watermark finalization, rebuild evidence application,
activation planning, and a separate guarded activation step.
