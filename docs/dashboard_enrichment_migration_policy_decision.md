# Dashboard Enrichment Migration Policy Decision

## Executive summary

Decision: `KEEP_DASHBOARD_ENRICHMENT_MIGRATIONS_AS_HISTORICAL_INERT`.

This decision applies only to these dashboard enrichment migration files:

- `rawcandle/sqlite/migrations/002_create_datacenter_dashboard_enrichment.sql`
- `rawcandle/sqlite/migrations/003_add_high_exit_risk_days_count_to_ticker_enrichment.sql`

The files remain in `rawcandle/sqlite/migrations/` as historical schema and audit artifacts. They must not be moved, deleted, archived, modified, or replaced with tombstones without a separate explicit migration-history decision.

## Scope

In scope:

- Migration `002_create_datacenter_dashboard_enrichment.sql`.
- Migration `003_add_high_exit_risk_days_count_to_ticker_enrichment.sql`.
- Documentation-only policy for their post-retirement handling.

Out of scope:

- Runtime code.
- Tests.
- DB files.
- Scheduler behavior.
- `scheduler_config.json`.
- Current `dc_*` source facts.
- Current `ec_*` sidecar.
- `ec_source_layer`.
- Migration files `004`-`018` and `019`-`024`.

## Current facts

- Dashboard UI/HTML/enrichment has been retired.
- Scheduler/config dashboard hooks have been removed or neutralized.
- Dashboard/enrichment dev_tools, UI, HTML, export tooling, and direct tests have been removed.
- The dashboard enrichment migration hook was removed from `analysis/database_manager.py`.
- `rawcandle/datacenter_dashboard_enrichment_migration.py` was removed.
- The five `dc_dashboard_*_daily` tables were dropped from `/home/kalle/projects/rawcandle/data/analysis.db` after verified backup.
- No `VACUUM` was run during DB cleanup.
- Migrations `002`/`003` are no longer active in current runtime paths.
- Current `dc_*`, current `ec_*`, and `ec_source_layer` remain preserved.

## Alternatives considered

| Option | Description | Outcome |
|---|---|---|
| Keep inert | Keep migrations `002`/`003` as historical inert SQL files. | Selected. |
| Archive/remove | Move or delete the files from the active migrations directory. | Deferred because it adds migration-history churn without current runtime pressure. |
| Tombstone/no-op | Replace the files with no-op migration stubs. | Rejected for now because it destroys historical schema detail and is unnecessary without a broad migration runner. |

## Decision and rationale

Selected option: keep migrations `002`/`003` as historical inert migrations.

Rationale:

- Lowest immediate risk.
- Preserves migration history and schema audit trail.
- Avoids unnecessary numbered migration churn.
- No active runtime path applies these files after the migration hook removal.
- No active DB cleanup pressure remains after the five retired `_daily` tables were removed from `analysis.db`.
- Consistent with the existing policy for migrations `004`-`018`, which keeps retired migration files as historical inert artifacts.

## Operational policy

- Current runtime must not apply migrations `002`/`003`.
- Do not add new runtime imports, hooks, or broad migration runners that apply `002`/`003` without an explicit policy update.
- Do not infer live DB table presence from these migration files.
- Keep DB cleanup separate from migration-file policy.
- If fresh DB bootstrap behavior is formalized, classify `002`/`003` explicitly as historical inert migrations.

## Revisit triggers

Revisit this decision only if one of these concrete conditions appears:

- Packaging or release cleanup needs a cleaner migration directory.
- A broad migration runner is introduced.
- Fresh DB bootstrap policy changes.
- The presence of migrations `002`/`003` creates onboarding confusion.
- Repository archive or compliance policy requires a different handling of obsolete SQL.

## Things not touched

- No migration files changed.
- No DB files changed.
- No runtime code changed.
- No tests changed.
- No scheduler behavior or config changed.
- No `scheduler_config.json` changed.
- No current `dc_*`, current `ec_*`, or `ec_source_layer` behavior changed.
