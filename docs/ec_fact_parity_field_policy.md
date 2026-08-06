# EC Fact Parity Field Policy

## Classification

```text
DATACENTER_RSO_SOURCE_RUN_ID_METADATA_PARITY_POLICY_FIXED
```

This document defines the field-level parity policy used by Datacenter DC/EC
fact parity audits and by `REPORT_STATUS_ONLY` EC revalidation.

No production resume, Scheduler run, Datacenter pipeline, Stage 2, EC rebuild,
EC loader, EC chunk, cleanup, activation, migration, production DB write,
Scheduler config write, taxonomy CSV edit, watchlist edit, backup creation, or
restore occurred while defining this policy.

## Field Classes

Parity fields are classified explicitly:

```text
KEY
SEMANTIC
REQUIRED_LINEAGE
OPERATIONAL_METADATA
IGNORED_DIAGNOSTIC
```

The default policy is strict:

```text
GLOBAL_STRICT_PARITY_POLICY
```

The report-status-only resume policy is:

```text
RSO_REVALIDATION_METADATA_POLICY_V1
```

Under the strict policy, `source_run_id` remains a required lineage equality
check. Under the RSO revalidation policy, only these fields are accepted as
operational metadata drift:

```text
ec_group_signal_daily.source_run_id
ec_group_synthetic_ohlc_daily.source_run_id
```

No other provenance field is broadly ignored. `source_table`, `source_pk_json`,
and `source_row_hash` remain required lineage presence checks.

## `source_run_id`

In Datacenter source tables the corresponding field is `run_id`. It is not part
of the DC primary key for group signal or synthetic OHLC facts. In EC fact
tables, `source_run_id` is non-null, indexed, and references
`ec_signal_run(run_id)`. It is operational provenance for the source loader/run
that produced the copied fact row.

The EC loaders write `source_run_id` by copying the DC source row `run_id`:

```text
rawcandle/ec_ticker_signal_daily_loader.py
rawcandle/ec_group_signal_daily_loader.py
rawcandle/ec_group_synthetic_ohlc_daily_loader.py
rawcandle/ec_group_index_daily_loader.py
```

They do not generate an independent EC operation identifier for
`source_run_id`. Loader operation time is stored separately in `created_at_utc`.

## Consumer Analysis

Production readers use `source_run_id` for audit and provenance summaries,
loader summaries, schema integrity, and parity diagnostics. No Datacenter
calculation, report decision, Scheduler decision, watermark advancement,
cleanup scope, activation gate, or downstream business calculation depends on
the exact string equality of DC `run_id` and EC `source_run_id` when all
semantic fields and key universes already match.

Normal strict parity still treats `source_run_id` equality as required. The
relaxation is deliberately scoped to RSO revalidation of already materialized
target EC facts.

## Successful-Run Evidence

Read-only production comparison of active V2 rows showed that ordinary accepted
DC/EC lineage normally has equal run IDs:

```text
2026-07-31 group_signal: rows=54 equal=54 different=0
2026-07-31 synthetic_ohlc: rows=53 equal=53 different=0
2026-08-03 group_signal: rows=54 equal=54 different=0
2026-08-03 synthetic_ohlc: rows=53 equal=53 different=0
2026-08-04 group_signal: rows=54 equal=54 different=0
2026-08-04 synthetic_ohlc: rows=53 equal=53 different=0
```

Deployment 2 is different because the target V2.1 EC facts were already
materialized, and later DC V2.1 group facts acquired newer `run_id` values while
their semantic payloads remained equal. In that recovery context, rebuilding EC
solely to refresh `source_run_id` would not change fact correctness.

## Mismatch Output

Parity output separates:

```text
semantic_field_mismatch_count
required_lineage_mismatch_count
operational_metadata_drift_count
ignored_diagnostic_difference_count
total_blocking_mismatch_count
```

Operational metadata drift is not hidden. It is reported as:

```text
warning_code=EC_OPERATIONAL_METADATA_DRIFT
field=source_run_id
data_correctness_affected=false
ec_rebuild_required=false
```

## Deployment 2 Read-Only Preflight

After applying the policy, deployment 2 read-only preflight produced:

```text
plan_reconciliation_status=SAFE_AMENDMENT_READY
plan_drift_classification=SAFE_IMPLEMENTATION_RECONCILIATION
ec_revalidation_parity_policy=RSO_REVALIDATION_METADATA_POLICY_V1
dc_repair_scope=ECOSYSTEM_AGGREGATE_ONLY
repair_candidate_count=506

ec_resume_action=REVALIDATE_EXISTING_FACTS
ec_rebuild_required=false
ec_loaders_required=false
ec_chunks_required=false
ec_revalidation_required=true

parity_status=OK_WITH_WARNINGS
semantic_field_mismatch_count=0
required_lineage_mismatch_count=0
operational_metadata_drift_count=106
total_blocking_mismatch_count=0
```

Structured warnings:

```text
ec_group_signal_daily.source_run_id=53
ec_group_synthetic_ohlc_daily.source_run_id=53
```

The read-only evidence is under:

```text
temp/datacenter_v2_1_source_run_id_policy_preflight/
```

## Policy Scope

This is not a global weakening of full or delta parity. Ordinary parity remains
strict unless the caller explicitly selects
`RSO_REVALIDATION_METADATA_POLICY_V1`. Semantic mismatches, key-universe
mismatches, taxonomy-lineage mismatches, and required-lineage mismatches remain
blocking for RSO revalidation.
