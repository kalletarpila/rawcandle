# Retired compatibility surface audit

## Executive summary

This document started as an audit-only step for retired compatibility surfaces left after old `eco_*` and Canonical Report V2 cleanup. R1 implementation has now removed the retired V3 scheduler/config/output compatibility surface.

Assessment: retired compatibility cleanup is complete for R1 and R2. Migration-file cleanup remains a separate later decision.

R1 status: scheduler `v3_reports_*` result fields, `datacenter_v3_reports_*` config fields, neutralized V3 helper functions, and CLI `SUMMARY v3_reports.*` output were removed. Old config keys are no longer accepted by the strict scheduler config parser. No DB, migration, current `dc_*`, current `ec_*`, `ec_source_layer`, Datacenter, dashboard, or Canonical Report V2 retired-stub behavior was changed.

R2 status: Canonical Report V2 retired dev_tools stubs and their retired-stub test were removed. The deleted files were compatibility/discoverability stubs only; no DB, migration, current `dc_*`, current `ec_*`, `ec_source_layer`, Datacenter, dashboard, or scheduler behavior was changed.

R4 status: resolved by `docs/legacy_migration_policy_decision.md`. Migrations `004`-`014` and `015`-`018` are kept as historical inert migrations for now.

Recommended next Codex step: move to a new cleanup target only if desired; no immediate migration-file action is recommended.

## Scope

Original audit scope:

- V3 scheduler/config/report compatibility fields.
- `datacenter_v3_reports_*` config parsing and defaults.
- `v3_reports_*` scheduler result fields and CLI summary output.
- Tests that enforce retired V3 scheduler behavior.
- Retired Canonical Report V2 dev_tools stubs.
- Tests that enforce Canonical Report V2 retired-stub behavior.
- Related active, audit, retirement, and archive documentation references.

Excluded:

- Current `dc_*` source facts.
- Current `ec_*` sidecar tables, loaders, planners, and migrations.
- `ec_source_layer`.
- Completed `analysis.db` old `eco_*` and `dc_report_*_v2` table cleanup.
- Deferred migration-file cleanup for `004`-`014` and `015`-`018`.
- Scheduler runtime behavior and `scheduler_config.json`.

## Inventory

| Path | Symbol/pattern | Category | Reason | Suggested next action |
|---|---|---|---|---|
| `rawcandle/scheduler/runner.py` | retired V3 result fields and helpers | SAFE_REMOVE_LATER | R1 removed the retired V3 result fields, JSON/result population, and neutralized helper call path. | Complete for R1. |
| `rawcandle/scheduler/config.py` | retired V3 config fields | SAFE_REMOVE_LATER | R1 removed the old config dataclass fields, optional keys, parsing, validation, serialization, and defaults. | Complete for R1. |
| `rawcandle/cli/run_stock_update_scheduler.py` | retired V3 CLI summary output | SAFE_REMOVE_LATER | R1 removed the retired V3 summary lines. | Complete for R1. |
| `tests/test_stock_update_scheduler_runner.py` | retired V3 compatibility assertions | TEST_ONLY | R1 removed V3 compatibility assertions and added absence/rejection checks without preserving the old output shape. | Complete for R1. |
| `tests/test_stock_update_scheduler_cli.py` | retired V3 CLI summary assertions | TEST_ONLY | R1 removed old V3 summary assertions and verifies no retired V3 summary prefix is printed. | Complete for R1. |
| `dev_tools/report_canonical_v2_retired.py` | retired stub implementation | SAFE_REMOVE_LATER | R2 removed the shared retired-stub implementation. | Complete for R2. |
| `dev_tools/run_report_canonical_v2_*.py` | retired CLI stubs | SAFE_REMOVE_LATER | R2 removed all retired Canonical Report V2 dev_tools stubs. | Complete for R2. |
| `tests/test_report_canonical_v2_retired_cli.py` | retired-stub test | TEST_ONLY | R2 removed the test because the stubs no longer exist. | Complete for R2. |
| `docs/dc_report_v2_retirement_decision.md` | V2 stub policy | DOCS_ONLY | Active retirement decision updated for R2 removal. | Complete for R2. |
| `docs/dc_report_v2_removal_audit.md` | retired V2 stubs and migrations | DOCS_ONLY | Historical audit/status document updated with R2 status. | Keep as audit trail. |
| `docs/eco_legacy_migration_cleanup_strategy.md` | `v3_reports_*` compatibility fields | DOCS_ONLY | Documents intentional deferred V3 compatibility fields. | R3: update after R1. |
| `docs/datacenter_legacy_report_generation_reference.md` | `v3_reports.*` summary mentions | DOCS_ONLY | Legacy reference still mentions scheduler V3 summary fields. | R3: update after R1. |
| `docs/archive/old_v3_eco/**` | old V3/eco references | DOCS_ONLY | Archived historical docs only. | Keep unless documentation retention policy changes. |
| `docs/archive/canonical_report_v2/**` | old Canonical V2 references | DOCS_ONLY | Archived historical docs only. | Keep unless documentation retention policy changes. |
| `rawcandle/sqlite/migrations/004`-`014` | `dc_report_*_v2` schema | AMBIGUOUS | Historical inert V2 migrations remain; cleanup is a separate migration-history decision. | R4 only after migration archive/removal decision. |
| `rawcandle/sqlite/migrations/015`-`018` | `eco_*` schema | AMBIGUOUS | Historical inert old V3/eco migrations remain; cleanup is a separate migration-history decision. | R4 only after migration archive/removal decision. |
| `rawcandle/cli/preflight_dc_report_v2_db_cleanup.py` | known `dc_report_*_v2` table names | PRESERVE_CURRENT | Read-only cleanup verification utility; not retired runtime. | Preserve unless preflight tooling is intentionally retired later. |

## V3 compatibility assessment

R1 removed the retired V3 scheduler/config/output compatibility surface.

Current assessment:

- Scheduler result objects and summary JSON no longer carry the retired V3 result fields.
- Scheduler config no longer exposes or accepts the retired V3 config keys.
- Scheduler CLI no longer prints retired V3 summary lines.
- The removed fields were compatibility-only and did not run old V3 report generation.
- Current Datacenter, dashboard, `ec_source_layer`, `dc_*`, and `ec_*` behavior is preserved.

## V2 retired stub assessment

R2 removed the Canonical Report V2 retired dev_tools stubs:

- `dev_tools/report_canonical_v2_retired.py`
- `dev_tools/run_report_canonical_v2_*.py`
- `tests/test_report_canonical_v2_retired_cli.py`

The deleted files were compatibility/discoverability-only stubs. They did not import removed V2 core modules, open DBs, or write outputs. After R2, running `dev_tools/run_report_canonical_v2_*` is unsupported because those files no longer exist.

## Phased removal plan

### R1: remove V3 scheduler/config/output compatibility

Status: complete.

Removed the retired V3 scheduler result fields, neutralized V3 helper functions, CLI retired V3 summary output, and retired V3 config dataclass fields, optional keys, parsing, validation, serialization, and skip-reset propagation. Old retired V3 config keys now fail as unexpected config keys.

Checks before and after R1:

- targeted search for retired V3 scheduler/config/output strings in `rawcandle` and `tests`
- `pytest -q tests/test_stock_update_scheduler_runner.py -k "ec_source_layer or datacenter_pipeline or dashboard"`
- `pytest -q tests/test_stock_update_scheduler_cli.py -k "summary or datacenter"`
- `python3 -m py_compile rawcandle/scheduler/runner.py rawcandle/scheduler/config.py rawcandle/cli/run_stock_update_scheduler.py`

### R2: remove V2 retired dev_tools stubs and tests

Status: complete.

Deleted `dev_tools/report_canonical_v2_retired.py`, all `dev_tools/run_report_canonical_v2_*.py` stubs, and `tests/test_report_canonical_v2_retired_cli.py`.

Checks before and after R2:

- `find dev_tools -maxdepth 1 -type f -name "run_report_canonical_v2_*.py" | sort`
- `find tests -maxdepth 1 -type f -name "test_report_canonical_v2*.py" | sort`
- `rg -n "run_report_canonical_v2|Canonical Report V2 has been retired|report_canonical_v2" dev_tools tests rawcandle`
- Scheduler-focused tests from R1 if any shared imports are touched.

### R3: archive/update documentation mentioning removed fields

Update active docs that mention `v3_reports.*`, `datacenter_v3_reports_*`, or V2 retired stubs as present. Keep archive docs as historical records unless a separate retention decision says otherwise.

Checks before and after R3:

- `rg -n "v3_reports|datacenter_v3_reports|run_report_canonical_v2|Canonical Report V2 has been retired" docs`
- Confirm active docs do not instruct users to use removed compatibility surfaces.

### R4: optional migration archive/removal

Handle migration files only after a separate migration-history compatibility decision:

- `004`-`014` for retired `dc_report_*_v2`.
- `015`-`018` for old `eco_*`.

Status: resolved by `docs/legacy_migration_policy_decision.md` with `KEEP_HISTORICAL_INERT_MIGRATIONS`.

This phase must not touch `019`-`024` current `ec_*` migrations. Any future DB table cleanup remains separate from migration-file cleanup and requires explicit backup and confirmation.

## Safeguards

- Do not delete or rename current `dc_*` source facts.
- Do not delete or rename current `ec_*` sidecar paths.
- Do not change `ec_source_layer`.
- Do not run scheduler, stock update, refresh, backfill, recovery, report generation, or DB-writing pipelines during audit-only steps.
- Do not stage DB files, WAL/SHM files, backups, temp artifacts, exports, generated reports, or `scheduler_config.json`.
- Keep migration-file cleanup separate from runtime compatibility cleanup.
- Treat scheduler result/config/output removal as an intentional API compatibility break, even though the underlying V3 implementation is already removed.

## Things not touched in this step

- No runtime code.
- No tests.
- No migrations.
- No DB files or backups.
- No `scheduler_config.json`.
- No scheduler, stock update, refresh, backfill, recovery, or report generation command.
- No current `dc_*`, `ec_*`, or `ec_source_layer` behavior.
