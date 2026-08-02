# Datacenter Taxonomy Replacement Workflow

## Operating Model

Datacenter uses one active taxonomy at a time. A taxonomy content change is a
controlled replacement and full rebuild, not a permanent parallel V1/V2 fact
model.

EC uses one active taxonomy per ecosystem. Multiple ecosystems can coexist later,
for example `DATACENTER`, `ENERGY`, `DEFENCE`, and `HEALTHCARE`, but a single
ecosystem does not need two active taxonomy fact sets at the same time.

The current production Datacenter taxonomy remains:

```text
taxonomy_version_code=DC_TAXONOMY_FULL_V1
taxonomy_csv=data/datacenter_ecosystem_taxonomy_full_v1.csv
source_sha256=1ad6ef41b91ef429174090bfcd338acf1e79680d939b4b788c834a79c73e9e5d
```

This implementation does not create, load, activate, or run a production V2.

## Immutable Versions

A taxonomy version is immutable after it has been loaded. This remains invalid:

```text
same taxonomy_version_code + different CSV source hash
```

A content change requires a new version code such as
`DC_TAXONOMY_FULL_V2`. Loading metadata for that version does not activate it and
does not change scheduler configuration.

## Lifecycle

The controlled replacement sequence is:

```text
1. Create proposed taxonomy CSV.
2. Assign a new immutable taxonomy version code.
3. Run read-only taxonomy change plan.
4. Load proposed taxonomy metadata as not active.
5. Stop affected Datacenter and EC production execution.
6. Back up production database and scheduler config.
7. Reset affected DC and EC rebuild state for the ecosystem.
8. Rebuild DC facts from the configured historical start.
9. Rebuild EC facts for the affected ecosystem.
10. Run coverage, parity, and replacement validation.
11. Plan activation.
12. Activate taxonomy and guarded scheduler config in a separate deployment.
13. Resume scheduler.
```

Rollback before activation means marking or discarding the proposed deployment
while keeping the current active taxonomy unchanged. Rollback after activation is
not a version-string flip; it requires restoring database/config backups or
performing an explicit rebuild using the previous taxonomy.

## Planning

The read-only planner is:

```bash
python3 -m rawcandle.cli.plan_datacenter_taxonomy_change \
  --analysis-db ... \
  --current-taxonomy-version DC_TAXONOMY_FULL_V1 \
  --current-taxonomy-csv data/datacenter_ecosystem_taxonomy_full_v1.csv \
  --proposed-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --proposed-taxonomy-csv ... \
  --format json
```

It uses the production taxonomy parser and reports deterministic sorted changes:

```text
added_tickers
removed_tickers
added_memberships
removed_memberships
moved_primary_memberships
changed_role_weights
changed_report_group_statuses
added_layers
removed_layers
added_subindustries
removed_subindustries
```

The default policy is always a full historical rebuild for additions, removals,
primary moves, secondary membership changes, role-weight changes, and layer or
subindustry changes. Narrow incremental taxonomy rebuilds are intentionally out
of scope.

## Metadata Load

The guarded metadata loader is:

```bash
python3 -m rawcandle.cli.apply_datacenter_taxonomy_version \
  --analysis-db ... \
  --current-taxonomy-version DC_TAXONOMY_FULL_V1 \
  --current-taxonomy-csv data/datacenter_ecosystem_taxonomy_full_v1.csv \
  --proposed-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --proposed-taxonomy-csv ... \
  --confirm-proposed-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --format json
```

It loads taxonomy metadata, entities, hierarchy, and memberships in one
transaction with deployment evidence. The new taxonomy is inserted with
`activation_status=NOT_ACTIVE`; canonical builders are not run automatically.

The durable audit state is stored in:

```text
ec_taxonomy_change_deployment
```

The row records source hash, change counts, rebuild requirement, rebuild start,
DC/EC rebuild status, coverage status, parity status, activation status, and
invocation source.

## Watermarks

`dc_pipeline_watermark` already includes `taxonomy_version` in its identity:

```text
component_name
taxonomy_version
market
signal_version
calc_version
```

New taxonomy runs must not inherit old taxonomy progress. The replacement plan
marks affected Datacenter components for reset and full rebuild from the
configured historical start, currently `2025-08-01`.

`ec_pipeline_watermark` keeps its active identity scoped to:

```text
ecosystem_id
pipeline_name
source_table
```

It now has taxonomy lineage via:

```text
taxonomy_version_id
```

This supports one active watermark set per ecosystem while proving which
taxonomy produced the current progress. Resetting `DATACENTER` watermarks must
not affect another ecosystem.

## Scheduler Configuration

The active Datacenter taxonomy is configurable with:

```text
datacenter_taxonomy_csv
datacenter_taxonomy_version
```

Defaults remain the current V1 path and version. Existing scheduler configs
without these keys remain backward compatible. Validation requires a readable CSV
whose internal `taxonomy_version` matches the configured version.

Loading a proposed taxonomy does not change scheduler configuration. Config is
changed only by a separately guarded activation operation.

## Activation Boundary

Activation planning is read-only:

```bash
python3 -m rawcandle.cli.plan_datacenter_taxonomy_activation \
  --analysis-db ... \
  --proposed-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --proposed-taxonomy-csv ... \
  --required-signal-date ...
```

Activation is refused unless the proposed metadata exists, source hashes match,
DC and EC rebuild evidence is complete, fact heads reach the required date,
watermarks belong to the proposed taxonomy, coverage and parity are accepted,
and no unresolved rebuild debt remains.

`apply_datacenter_taxonomy_activation` is a guarded write boundary. It verifies
the same gates before marking the proposed taxonomy active, marking the previous
taxonomy inactive for that ecosystem, and recording activation evidence. It must
only be run during a separately confirmed deployment step.

## Canonical Replacement Validation

Replacement validation rejects stale taxonomy rows in canonical DC or EC fact
tables. After replacement, reports must not mix old and new taxonomy rows, group
rows removed from the new taxonomy must be absent for the affected range, and
ticker/group counts must match the new taxonomy.

## Future UI Contract

A future UI should call these backend services. It should allow a user to view
the active taxonomy, duplicate it into a proposed version, edit memberships and
groups, preview deterministic changes, load proposed metadata, follow rebuild
and parity status, explicitly activate a new version, inspect audit history, and
start a guarded rollback or rebuild procedure.
