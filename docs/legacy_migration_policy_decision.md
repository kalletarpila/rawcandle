# Legacy Migration Policy Decision

## Executive summary

DECISION: KEEP_HISTORICAL_INERT_MIGRATIONS

This decision applies to:

- Migrations `004`-`014` for retired Canonical Report V2 / `dc_report_*_v2`.
- Migrations `015`-`018` for old legacy `eco_*`.

The files remain in `rawcandle/sqlite/migrations/` as historical schema and audit artifacts. They should not be applied by current runtime paths, and they should not be moved, deleted, or replaced with tombstones without a separate explicit migration-history compatibility decision.

## Scope

This decision covers only historical migration files.

It does not reopen or change:

- Completed DB table cleanup.
- Runtime code removal.
- Scheduler compatibility cleanup.
- Current `dc_*` source facts.
- Current legacy Datacenter reports.
- Current `ec_*` sidecar.
- `ec_source_layer`.

## Current facts

- Old `eco_*` tables are gone from `analysis.db`.
- Known retired `dc_report_*_v2` tables are gone from `analysis.db`.
- Current `dc_*` and `ec_*` tables were present in the final read-only legacy cleanup verification.
- Current `rawcandle/ec_sidecar_migration.py` uses an explicit `MIGRATION_SQL_PATHS` tuple for migrations `019`-`024`.
- The current `ec_*` sidecar migration path does not glob every SQL file under `rawcandle/sqlite/migrations/`.
- No current `dc_*`, `ec_*`, or `ec_source_layer` path identified in the prior audits depends on migrations `004`-`018`.
- Migrations `004`-`018` remain in the repository only as historical SQL files.

## Alternatives considered

| Option | Description | Outcome |
|---|---|---|
| A | Keep migrations as historical inert migrations. | Selected. |
| B | Move or archive migrations outside the active migration directory. | Deferred. |
| C | Replace migrations with tombstone/no-op files. | Rejected for now. |
| D | Delete migrations entirely. | Rejected for now. |

## Decision and rationale

Selected option: Option A, keep migrations `004`-`018` as historical inert migrations.

Rationale:

- Lowest immediate risk.
- Preserves historical schema and audit trail.
- Avoids migration-history churn.
- Avoids possible unknown manual or fresh-bootstrap expectations.
- Avoids ambiguity around numbered migration gaps.
- There is no active runtime pressure to remove the files.
- Database cleanup was completed independently from migration-file policy.

## Operational policy

- Current runtime must not apply migrations `004`-`018`.
- New current schema work should use current paths only.
- Migrations `019`-`024` remain the current `ec_*` sidecar migrations.
- No new dependencies should be added to migrations `004`-`018`.
- If future tooling introduces a broad migration runner, it must explicitly exclude or classify historical migrations `004`-`018`.
- Do not infer live DB table presence from historical migration files.

## Revisit triggers

Revisit this decision only if one of these concrete conditions appears:

- Packaging or release work needs a cleaner migration directory.
- A new migration runner starts globbing all SQL files.
- A fresh DB bootstrap process becomes formalized.
- Migrations `004`-`018` confuse onboarding or tests.
- Security or compliance policy requires removal of obsolete SQL.
- Repository archive policy changes.

## Safeguards

- Do not delete or move migrations `004`-`018` without explicit approval.
- Do not replace migrations `004`-`018` with tombstones without explicit approval.
- Do not run old migrations against production DBs.
- Do not infer DB table presence from migration files.
- Keep DB cleanup separate from migration-file policy.
- Preserve current `dc_*` source facts.
- Preserve current legacy Datacenter reports.
- Preserve current `ec_*` sidecar and `ec_source_layer`.

## Things not touched

- No migration files changed.
- No DBs touched.
- No runtime code changed.
- No tests changed.
- No scheduler behavior or config changed.
- No `scheduler_config.json` changed.
- No current `dc_*`, `ec_*`, or `ec_source_layer` behavior changed.

## Recommended next step

No immediate migration action is recommended.

Move to a new cleanup target only if desired. One optional later target is a read-only audit of tracked risky fixtures such as `test.db`, `tmp_analysis.db`, or virtualenv files if they are still relevant.
