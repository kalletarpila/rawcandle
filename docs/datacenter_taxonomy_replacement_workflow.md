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
5. Prepare the taxonomy rebuild deployment.
6. Stop affected Datacenter and EC production execution.
7. Back up production database and scheduler config.
8. Rebuild DC facts from the configured historical start.
9. Rebuild DATACENTER EC facts with explicit taxonomy-rebuild mode.
10. Apply verified rebuild evidence.
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

Historical backfill keeps the ordinary 60 calendar day protection. A longer
range is accepted only through explicit taxonomy-rebuild mode with deployment
and range confirmations. During taxonomy replacement, EC watermark finalization
compares both latest date and taxonomy lineage. An equal latest date still
updates the canonical watermark rows when the lineage changes from V1/NULL to
V2. Ordinary backfill refuses old or NULL lineage instead of silently replacing
it.

Canonical EC watermark scopes are:

```text
TICKER_SWING_BASE -> dc_ticker_swing_signal_daily
GROUP_SWING_BASE -> dc_group_swing_signal_daily
SYNTHETIC_OHLC_BASE -> dc_group_synthetic_ohlc_daily
GROUP_INDEX -> dc_group_index_daily
```

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

When `--scheduler-config` is supplied, activation also updates only these
taxonomy keys after verifying the config still has the expected V1 state:

```text
datacenter_taxonomy_csv
datacenter_taxonomy_version
ec_source_layer_taxonomy_csv
ec_source_layer_taxonomy_version
```

A scheduler config backup is written under `temp/` or the supplied backup
directory. If config write or validation fails, the database activation
transaction is rolled back and the config file is restored from the backup.

## Rebuild Preparation and Evidence

The rebuild preparation CLI is:

```bash
python3 -m rawcandle.cli.prepare_datacenter_taxonomy_rebuild \
  --analysis-db ... \
  --ecosystem DATACENTER \
  --proposed-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --proposed-taxonomy-csv data/datacenter_taxonomy_full_v2.csv \
  --deployment-id ... \
  --expected-active-taxonomy-version DC_TAXONOMY_FULL_V1 \
  --confirm-proposed-taxonomy-version DC_TAXONOMY_FULL_V2
```

It records current V1 DC watermark evidence, confirms V2 has not inherited V1
watermark progress, marks the deployment `REBUILD_IN_PROGRESS`, and does not run
the Datacenter pipeline.

The evidence CLI is:

```bash
python3 -m rawcandle.cli.apply_datacenter_taxonomy_rebuild_evidence \
  --analysis-db ... \
  --ecosystem DATACENTER \
  --proposed-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --proposed-taxonomy-csv data/datacenter_taxonomy_full_v2.csv \
  --deployment-id ... \
  --required-signal-date ...
```

It verifies DC fact heads, EC fact heads, canonical EC watermark lineage,
coverage status, parity status, mismatch count, and stale-row gates before
moving the deployment to `READY_TO_ACTIVATE`. Supplied OK values are not trusted
without matching database evidence.

## Canonical Replacement Validation

Replacement validation rejects stale taxonomy rows in canonical DC or EC fact
tables. After replacement, reports must not mix old and new taxonomy rows, group
rows removed from the new taxonomy must be absent for the affected range, and
ticker/group counts must match the new taxonomy.

For Datacenter taxonomy replacement, V1 and V2 DC facts may coexist before
activation because DC fact primary keys include `taxonomy_version`. EC
DATACENTER facts are a replacement range: old DATACENTER rows in the rebuilt
range are deleted before V2 rows are loaded, while other ecosystems are left
untouched.

Known source-data special cases are accepted explicitly:

```text
CBRS first source date = 2026-05-14
WYFI first source date = 2025-08-07
```

No rows are fabricated before the first available source date. Pre-listing or
short-history dates are not fatal by themselves; Stage 2 uses the established
`MISSING_AS_OF_DATE` and `INSUFFICIENT_HISTORY` contracts. Unexpected missing
latest-date source data remains blocking.

## Durable CSV Policy

The repository ignores generated CSVs broadly, but taxonomy source CSV files are
durable source artifacts. `.gitignore` keeps a narrow exception for:

```text
data/datacenter_ecosystem_taxonomy_full_v1.csv
data/datacenter_taxonomy_full_v2.csv
```

This does not unignore report, export, backup, or generated CSV files.

## Future UI Contract

A future UI should call these backend services. It should allow a user to view
the active taxonomy, duplicate it into a proposed version, edit memberships and
groups, preview deterministic changes, load proposed metadata, follow rebuild
and parity status, explicitly activate a new version, inspect audit history, and
start a guarded rollback or rebuild procedure.
