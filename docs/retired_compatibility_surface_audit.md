# Retired compatibility surface audit

## Executive summary

This is an audit-only step for retired compatibility surfaces left after old `eco_*` and Canonical Report V2 cleanup. No runtime code, tests, migrations, scheduler configuration, database files, or generated artifacts were changed.

Assessment: remove in phases, not as one broad cleanup.

The old V3/eco implementation is already removed or neutralized, but the scheduler still exposes `v3_reports_*` result fields, accepts `datacenter_v3_reports_*` config fields, and prints `SUMMARY v3_reports.*` CLI lines. Those fields are compatibility surface only; when `datacenter_v3_reports_enabled=true`, the scheduler returns `SKIPPED_REMOVED` and does not import removed V3 writer/query modules.

Canonical Report V2 active code has also been removed. The remaining `dev_tools/run_report_canonical_v2_*.py` files are retired stubs that import only `dev_tools.report_canonical_v2_retired`, print a retirement message to stderr, return exit code `2`, and do not open databases or write outputs.

Recommended next Codex step: implement R1 first if config/output compatibility can be intentionally broken now. R1 removes scheduler `v3_reports_*` result/output fields and `datacenter_v3_reports_*` config fields/tests. This should happen before deleting V2 stubs, because it touches active scheduler result shape.

## Scope

Included:

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
| `rawcandle/scheduler/runner.py` | `v3_reports_*` fields on `ScheduledStockUpdateRunResult` | KEEP_TEMPORARILY | Active scheduler result shape still carries retired V3 fields for compatibility. | R1: remove result fields and JSON population after compatibility decision. |
| `rawcandle/scheduler/runner.py` | `_default_v3_reports_post_step_result` | SAFE_REMOVE_LATER | Helper only returns retired `SKIPPED_REMOVED` state. | R1: delete with result fields. |
| `rawcandle/scheduler/runner.py` | `_run_v3_datacenter_report_generation` | SAFE_REMOVE_LATER | Function no longer runs V3 generation and imports no removed V3 modules. | R1: remove call path and helper. |
| `rawcandle/scheduler/runner.py` | `datacenter_v3_reports_*` copied into reset config | KEEP_TEMPORARILY | Preserves config shape during `skip_next_run` reset. | R1: remove if old config keys no longer need acceptance. |
| `rawcandle/scheduler/config.py` | `_OPTIONAL_CONFIG_KEYS` `datacenter_v3_reports_*` | KEEP_TEMPORARILY | Current config reader accepts legacy keys instead of rejecting existing configs. | R1: remove or explicitly deprecate with a migration note. |
| `rawcandle/scheduler/config.py` | `StockUpdateSchedulerConfig.datacenter_v3_reports_*` | KEEP_TEMPORARILY | Dataclass still contains disabled-by-default V3 compatibility fields. | R1: remove if scheduler config compatibility can be broken. |
| `rawcandle/scheduler/config.py` | validation for `datacenter_v3_reports_*` | KEEP_TEMPORARILY | Only validates obsolete compatibility fields. | R1: delete with config fields. |
| `rawcandle/scheduler/config.py` | default `datacenter_v3_reports_enabled=False` | KEEP_TEMPORARILY | Confirms old path is disabled by default, but still present. | R1: remove after config compatibility decision. |
| `rawcandle/cli/run_stock_update_scheduler.py` | `SUMMARY v3_reports.*` | KEEP_TEMPORARILY | CLI still prints retired V3 summary lines from scheduler result. | R1: remove after result fields are removed. |
| `tests/test_stock_update_scheduler_runner.py` | `v3_reports_*`, `SKIPPED_REMOVED`, `datacenter_v3_reports_enabled=True` | TEST_ONLY | Tests prove the retired V3 path does not import old writer/resolver modules and returns skipped state. | R1: replace/remove with tests for absence of V3 fields if fields are deleted. |
| `tests/test_stock_update_scheduler_cli.py` | `SUMMARY v3_reports.*` assertions | TEST_ONLY | Tests enforce current CLI compatibility output, including historic OK/FAILED V3 values via fake result objects. | R1: delete/update after CLI output removal. |
| `dev_tools/report_canonical_v2_retired.py` | `RETIRED_MESSAGE`, `main` returns `2` | KEEP_TEMPORARILY | Shared retired-stub implementation; no DB or output writes. | R2: delete when retired stubs are removed. |
| `dev_tools/run_report_canonical_v2_*.py` | `from dev_tools.report_canonical_v2_retired import main` | SAFE_REMOVE_LATER | Stubs are compatibility/discoverability only and do not import removed V2 core modules. | R2: delete all stubs after R1. |
| `tests/test_report_canonical_v2_retired_cli.py` | exit code `2` and retirement message | TEST_ONLY | Tests enforce retired-stub behavior. | R2: delete with stubs. |
| `docs/dc_report_v2_retirement_decision.md` | V2 stub policy | DOCS_ONLY | Active retirement decision explaining why stubs remain. | R3: update if stubs are deleted. |
| `docs/dc_report_v2_removal_audit.md` | retired V2 stubs and migrations | DOCS_ONLY | Historical audit/status document. | R3: update status only if useful; otherwise keep as audit trail. |
| `docs/eco_legacy_migration_cleanup_strategy.md` | `v3_reports_*` compatibility fields | DOCS_ONLY | Documents intentional deferred V3 compatibility fields. | R3: update after R1. |
| `docs/datacenter_legacy_report_generation_reference.md` | `v3_reports.*` summary mentions | DOCS_ONLY | Legacy reference still mentions scheduler V3 summary fields. | R3: update after R1. |
| `docs/archive/old_v3_eco/**` | old V3/eco references | DOCS_ONLY | Archived historical docs only. | Keep unless documentation retention policy changes. |
| `docs/archive/canonical_report_v2/**` | old Canonical V2 references | DOCS_ONLY | Archived historical docs only. | Keep unless documentation retention policy changes. |
| `rawcandle/sqlite/migrations/004`-`014` | `dc_report_*_v2` schema | AMBIGUOUS | Historical inert V2 migrations remain; cleanup is a separate migration-history decision. | R4 only after migration archive/removal decision. |
| `rawcandle/sqlite/migrations/015`-`018` | `eco_*` schema | AMBIGUOUS | Historical inert old V3/eco migrations remain; cleanup is a separate migration-history decision. | R4 only after migration archive/removal decision. |
| `rawcandle/cli/preflight_dc_report_v2_db_cleanup.py` | known `dc_report_*_v2` table names | PRESERVE_CURRENT | Read-only cleanup verification utility; not retired runtime. | Preserve unless preflight tooling is intentionally retired later. |

## V3 compatibility assessment

`rawcandle/scheduler/config.py` still accepts and serializes:

- `datacenter_v3_reports_enabled`
- `datacenter_v3_reports_output_dir`
- `datacenter_v3_reports_ecosystem`
- `datacenter_v3_reports_taxonomy_version`

The default is `datacenter_v3_reports_enabled=False`. This confirms the old V3 path is not the default primary path, but it does not remove compatibility acceptance.

`rawcandle/scheduler/runner.py` still defines `v3_reports_*` fields on the scheduler result and writes them into summary JSON/result objects. The active V3 execution helper is neutralized:

- `_run_v3_datacenter_report_generation(...)` ignores the old config and returns `_default_v3_reports_post_step_result(...)`.
- `_default_v3_reports_post_step_result(...)` returns `attempted=0`, `status="SKIPPED_REMOVED"`, and error text `old V3/eco report generation has been removed`.
- Targeted tests assert that enabling `datacenter_v3_reports_enabled=True` returns the removed status and that old V3 resolver/writer symbols are not present on `rawcandle.scheduler.runner`.

`rawcandle/cli/run_stock_update_scheduler.py` still prints `SUMMARY v3_reports.*` lines. These lines are compatibility output, not evidence of current V3 report generation.

Current assessment: V3 compatibility fields are safe to remove later only through an active scheduler API/output change. They are not a DB risk and do not currently call old V3 code.

## V2 retired stub assessment

The remaining Canonical Report V2 entrypoints are:

- `dev_tools/run_report_canonical_v2_all_outputs_smoke.py`
- `dev_tools/run_report_canonical_v2_daily_csv.py`
- `dev_tools/run_report_canonical_v2_daily_markdown.py`
- `dev_tools/run_report_canonical_v2_daily_markdown_smoke.py`
- `dev_tools/run_report_canonical_v2_output.py`
- `dev_tools/run_report_canonical_v2_parity_audit.py`
- `dev_tools/run_report_canonical_v2_publish_outputs.py`
- `dev_tools/run_report_canonical_v2_rolling2_csv.py`
- `dev_tools/run_report_canonical_v2_rolling2_markdown.py`
- `dev_tools/run_report_canonical_v2_rolling30_csv.py`
- `dev_tools/run_report_canonical_v2_rolling30_markdown.py`
- `dev_tools/run_report_canonical_v2_rolling5_csv.py`
- `dev_tools/run_report_canonical_v2_rolling5_markdown.py`

Each imports only `main` from `dev_tools.report_canonical_v2_retired` and exits through that function. The shared retired implementation prints `Canonical Report V2 has been retired. See docs/dc_report_v2_retirement_decision.md.` to stderr and returns code `2`.

The stubs do not import removed Canonical Report V2 core modules. The targeted retired CLI test passes a fake DB path and asserts there is no stdout, the stderr retirement message is exact, and the exit code is `2`.

Current assessment: these stubs are safe to delete later if compatibility/discoverability is no longer needed. Deleting them should be R2, after the active scheduler V3 result/config shape is handled.

## Phased removal plan

### R1: remove V3 scheduler/config/output compatibility

Remove the scheduler `v3_reports_*` result fields, `_default_v3_reports_post_step_result`, `_run_v3_datacenter_report_generation`, and CLI `SUMMARY v3_reports.*` output. Remove `datacenter_v3_reports_*` config dataclass fields, optional keys, parsing, validation, serialization, and skip-reset propagation if backward compatibility can be intentionally broken.

Checks before and after R1:

- `rg -n "v3_reports|datacenter_v3_reports|SKIPPED_REMOVED" rawcandle tests`
- `pytest -q tests/test_stock_update_scheduler_runner.py -k "ec_source_layer or datacenter_pipeline or dashboard"`
- `pytest -q tests/test_stock_update_scheduler_cli.py -k "summary or datacenter"`
- `python3 -m py_compile rawcandle/scheduler/runner.py rawcandle/scheduler/config.py rawcandle/cli/run_stock_update_scheduler.py`

### R2: remove V2 retired dev_tools stubs and tests

Delete `dev_tools/report_canonical_v2_retired.py`, all `dev_tools/run_report_canonical_v2_*.py` stubs, and `tests/test_report_canonical_v2_retired_cli.py`.

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

This phase must not touch `019`-`024` current `ec_*` migrations. Any DB table cleanup remains separate from migration-file cleanup and requires explicit backup and confirmation.

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
