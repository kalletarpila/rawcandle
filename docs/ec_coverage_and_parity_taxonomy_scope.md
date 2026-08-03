# EC Coverage And Parity Taxonomy Scope

This note documents the audit-scope fix added after the DATACENTER
`DC_TAXONOMY_FULL_V2` EC rebuild retry 5 coverage failure.

No production scheduler, Datacenter stage, EC rebuild, EC backfill, activation,
watermark update, migration, backup, restore, cleanup, taxonomy CSV edit,
watchlist edit, or production DB write occurred as part of this code change.

## Incident

Retry 5 loaded all four canonical V2 EC fact tables for `2025-08-01`, but
stopped at coverage:

```text
failed_step=audit_dc_facts_against_ec_sidecar
coverage_status=FAILED
total_mismatch_count=0
watermark_finalization_performed=false
```

The first-date V2 fact counts matched:

```text
ticker=257
group_signal=54
synthetic_ohlc=53
group_index=54
```

The root cause was taxonomy scope missing from DC source queries in the
coverage audit. The audit read all DC ticker rows for the date, including
active V1 rows, then required V2 primary memberships for V1-only tickers such
as `ABB`, `BLD`, `COMM`, `GOOG`, `HAYW`, `HPQ`, `ILU.AX`, `INFN`, `IQE`,
`JNPR`, `LOGI`, `LPKF`, `MIDD`, `OLED`, and `PSTG`.

The parity audit had the same DC source-scope defect and would have compared
unfiltered DC source rows against V2 EC target rows if execution had reached
parity.

## Contract

Every audit has one explicit taxonomy context:

```text
ecosystem_code or ecosystem_id
taxonomy_version_code
taxonomy_version_id
signal_date
signal_version or calc_version where applicable
```

For V2 rebuilds, this means:

```text
active scheduler taxonomy=DC_TAXONOMY_FULL_V1
requested audit taxonomy=DC_TAXONOMY_FULL_V2
```

is a valid and expected transition state.

DC source queries must be scoped by:

```text
taxonomy_version
date column
signal_version or calc_version where applicable
```

EC target queries remain scoped by:

```text
ecosystem_id
taxonomy_version_id
signal_date
signal_version or calc_version
```

Audits must not infer source scope from active taxonomy state, scheduler config,
unfiltered date-level source rows, or hardcoded expected counts.

## Coverage

Coverage checks sidecar readiness and source presence:

```text
entity existence
primary ticker membership
group hierarchy
source group/ticker presence
watchlist metadata warnings
```

Coverage accepts expected non-OK rows when they are present and mapped
consistently. Examples from the V2 first date include:

```text
CBRS=MISSING_AS_OF_DATE
WYFI=MISSING_AS_OF_DATE
group row=TOO_SMALL
```

Coverage must still fail for genuinely missing requested-taxonomy source rows,
unexpected source taxonomy rows, missing entities, missing primary memberships,
incomplete group hierarchy, or missing required target coverage.

## Parity

Parity checks canonical fact equivalence:

```text
missing target rows
extra target rows
field mismatches
duplicate key effects
```

The mismatch count is a fact-parity measure. A coverage failure can occur with
`total_mismatch_count=0` when parity was not run. Backfill now exposes explicit
execution state, such as:

```text
coverage_execution_status=COMPLETED
parity_execution_status=NOT_RUN_COVERAGE_FAILED
```

## Orchestrator Aggregation

The chunked EC taxonomy rebuild orchestrator no longer treats an empty
`per_date_results` list as successful audit evidence. If a chunk fails before a
completed per-date result exists, chunk audit status is non-OK and records
where the status came from:

```text
coverage_status=FAILED
coverage_execution_status=FAILED_BEFORE_ACCEPTED_DATE_RESULT
coverage_status_source=chunk_failure_no_per_date_results
parity_status=NOT_RUN_COVERAGE_FAILED
parity_execution_status=NOT_RUN_COVERAGE_FAILED
parity_status_source=chunk_failure_no_per_date_results
```

## Retry Safety

The partial V2 `2025-08-01` state remains safe for an idempotent controlled
retry after this code fix. The canonical loaders delete and replace by:

```text
ecosystem_id
taxonomy_version_id
signal_date
signal_version or calc_version
```

That scope does not touch active V1 rows or other ecosystems. No production
retry was executed as part of this change.
