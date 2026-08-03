# EC Taxonomy Rebuild Proposed Source Validation

The EC source-layer planner has two taxonomy source validation modes.

Ordinary refresh and ordinary historical backfill use the active configured
taxonomy:

```text
taxonomy_validation_mode=ACTIVE_TAXONOMY
```

In this mode the source CSV must match the active loaded taxonomy and the
active expected source shape. Unexpected source drift remains blocking.

Taxonomy full rebuild uses the explicitly selected proposed taxonomy:

```text
taxonomy_validation_mode=PROPOSED_TAXONOMY_REBUILD
taxonomy_expected_source=LOADED_PROPOSED_TAXONOMY
```

This mode is entered only with explicit rebuild context:

```text
taxonomy_rebuild=true
deployment_id=<deployment>
taxonomy_version=<proposed taxonomy>
taxonomy_csv=<proposed CSV>
```

The planner validates the proposed CSV against the loaded proposed
`ec_taxonomy_version`, the sidecar membership/entity graph, and the matching
deployment row. It compares:

```text
source version
source SHA-256
row count
distinct ticker count
layer count
subindustry count
primary membership count
secondary membership count
```

This fixes the blocked V2 retry path where the first EC rebuild chunk compared
the V2 CSV against V1 source counts:

```text
V1 rows=329 tickers=236
V2 rows=350 tickers=257
```

The V2 rebuild path now expects:

```text
taxonomy_expected_version=DC_TAXONOMY_FULL_V2
taxonomy_expected_row_count=350
taxonomy_actual_row_count=350
taxonomy_expected_ticker_count=257
taxonomy_actual_ticker_count=257
taxonomy_source_match=true
taxonomy_source_error=NONE
```

Failure remains strict. The planner still blocks before writes if the proposed
CSV hash differs from the loaded proposed hash, loaded proposed membership
counts differ from the CSV, the deployment version or hash mismatches, the
deployment row is missing, the proposed taxonomy is already active, or ordinary
backfill attempts to use an inactive proposed taxonomy without rebuild mode.

A later controlled retry can start from:

```text
dc_rebuild_status=OK
ec_rebuild_status=FAILED
activation_status=NOT_ACTIVE
```

provided the same deployment ID, proposed taxonomy version, source hash, rebuild
range, inactive V2 state, accepted DC evidence, and V1 scheduler configuration
still match the guarded request.

No production EC retry, scheduler run, Datacenter pipeline run, activation,
database write, watermark update, migration apply, taxonomy CSV edit, or backup
replacement occurred as part of this implementation.
