# Phase 13G.2.5D: Fundamentals V1 Runtime Retirement

Current Fundamentals Administration and Snapshot use the active full V2 package.
Add Tickers, Sector/Industry synchronization, and Taxonomy synchronization use
the same fresh full V2 + RP V2 + RV rebuild and guarded publication workflow.
Taxonomy is read from the active `dc_ecosystem` version in `data/analysis.db`;
Sector/Industry is read from `data/osakedata.db.ticker_meta`. Neither is edited
by these downstream rebuilds. A missing or invalid V2 activation fails closed.

The scheduler has no RawCandle Fundamentals recalculation command. Its
SwingMaster Fundamentals post-step is a separate pipeline. Legacy Score,
Lifecycle, Valuation, Delta, Diagnostics, and Relative Position V1 commands and
production writers have been retired. Relative Valuation (RV) remains active;
its model version ending in `V1` does not denote legacy Relative Position V1.

## Runtime Ownership

| Role | Current owner | Retirement classification |
| --- | --- | --- |
| Score, Lifecycle, Valuation, Delta, Diagnostics | `operating_income_v2` | V1 engines and writers removed |
| Peer ranking math | `operating_income_v2.peer_ranking_core` | extracted neutral utility |
| Identity, classification, taxonomy lookup | `operating_income_v2.peer_source_context` | extracted neutral utility |
| V2 source-only Snapshot scaffold | `snapshot.v2_scaffold` | V1 assembler removed |
| Delta/Diagnostics table layout and shared SQL | `schema.analysis_runtime_layout`, `schema.analysis_compat_schema` | shared schema kept |
| RV calculation and persistence | `relative_valuation` | current non-V1 model kept |
| Historic Phase 9/10 and Phase 13E/F scripts | Git history and historical docs | executable V1 routes removed |

## Deferred Schema Inventory

This phase does not change any production schema or rows. For a later,
separately authorized migration:

| Object | Classification | Reason |
| --- | --- | --- |
| `lifecycle_result`, `valuation_result` | `SAFE_TO_REMOVE_NEXT_PHASE` after backup and independent audit | legacy-only result tables; current V2 rebuild requires them empty |
| `score_result`, `score_component`, `lifecycle_revised_result`, `valuation_revised_result` | `SHARED_KEEP` | current V2 rows live here; some legacy-capable columns remain |
| `fundamental_delta_*`, `diagnostic_flag_*` | `SHARED_KEEP` | current V2 package uses these versioned tables |
| `relative_position_snapshot`, `relative_position_result`, `relative_position_coverage`, `relative_position_active_snapshot`, `relative_position_schema_meta` | `SHARED_KEEP` | RP V2 uses these; old model values and pointer capability require a future targeted migration |
| `relative_position_refresh_audit`, `analysis_model_run`, package manifest/history | `HISTORICAL_KEEP` or `NEEDS_MIGRATION` | inspect retained audit and version rows before any deletion |
| legacy EBIT/EBIT-yield and run-local columns in revised result tables | `NEEDS_MIGRATION` | do not drop until current readers and semantic fingerprints are independently validated against a migrated copy |
| archived DB backups and historical runbooks | `HISTORICAL_KEEP` | retain rollback and audit evidence |

V1-capable schema is not proof of active V1 state. Check model fingerprints,
active pointers, and current package identity before deciding on cleanup.

## Acceptance Evidence (2026-09-18)

The post-retirement fresh rebuild from the four authoritative source DBs ran
at `as_of_date=2026-09-18` with the V1 modules absent and finished `READY`.
Its package held 87,860 each of Score, Lifecycle, Valuation, Delta, and
Diagnostics endpoints; 13,799 RP V2 results; and 2,444 RV companies. The
economic package fingerprint matched current production exactly:
`f377ebd50789b2f9ed6d7932528fb8c2faeb7f779a35ab03dea9cad27026980c`.
The RP result fingerprint was
`8933e92bfa6e1c6993992935fea84e0d2647990f74f55a35327a83fac26e33bf`;
RV source/result fingerprints were
`68c7ccd463e096335cfa2849a423d750346f20e5fd805a5573ee6a73ebd99c9c`
and `38bad6944e6272052b3f14ea4fde17579e189ada5a13c306f0199eb3eca1cc94`.
The active taxonomy was `dc_ecosystem` / `DC_TAXONOMY_FULL_V2_1` with semantic
fingerprint `801698f6b352c445cc8e6f5fd51a1cac2779d11f6ce72a1c10bf71bb8aae4559`.

All seven calculation-layer fingerprints matched the pre-deletion rebuild.
NVDA, AMZN, SNDK, and IA Snapshots matched production semantically after
excluding run-local timestamps; source-state fingerprints matched exactly.
The production analysis file SHA-256 remained
`7ed45dd8e8ae902d66022d3dcdbfc1b9140c2a7710391f2f5046738c817782b7`.
All four authoritative source file SHA-256 values remained unchanged from the
Phase 13G.2.5C closure. The disposable failed/ready candidates (846 MiB and
two at 851 MiB) were deleted; lightweight event and result reports remain in
`temp/phase13g25d/evidence*`. The verified Phase C rollback backup remains.

The production analysis DB has zero rows in `lifecycle_result` and
`valuation_result`, one active RP V2 pointer, and only V2 model values in the
Score, Lifecycle, Valuation, and RP snapshot tables. No schema was dropped.

## Route and Reference Audit

- `ACTIVE_RUNTIME_DEPENDENCY` / `V2_IMPLEMENTATION_DEPENDENCY`: none on retired
  Score, Lifecycle, Valuation, Delta, Diagnostics, or RP V1 modules. A subprocess
  import test blocks all six old engines while loading full rebuild, Admin, and
  Snapshot.
- `LEGACY_CLI`, `LEGACY_WRITER`, `LEGACY_READER`, `DEAD_CODE_CANDIDATE`:
  retired V1 CLI files; old Score/Lifecycle/Valuation/Delta/Diagnostics/RP
  packages; Phase 9D/9E/9G/10C and old Phase 13E/F production scripts; V1
  Snapshot assembler; and the Phase 13G.2.5A V1 digest command. The current
  RV production command remains and is bound to the current V2 package.
- `LEGACY_ADMIN_ROUTE`: none. Add Tickers, Sector/Industry, and Taxonomy use
  the shared full V2 rebuild. The Add Tickers structural-event context was
  extracted from an old Phase 13F module into `admin.structural_context`.
- `LEGACY_SCHEDULER_ROUTE`: none for RawCandle Fundamentals. SwingMaster's
  similarly named scheduler step is separate and was not changed.
- `TEST_ONLY`: retired V1-only test modules removed; V2 tests were converted
  where they still asserted current behavior. Historical Phase 9/13 runbooks
  remain for audit, with the current architecture contract pointing here.
- `CURRENT_NON_V1_MODEL`: RV's `...RELATIVE_VALUATION_V1`, the canonical
  `V4_TTM_EBIT_FIRST_V1` source model, and V2 eight-flag/Snapshot contract
  version suffixes are current. Admin contract versions and report format
  versions ending in `V1` are protocol identifiers, not legacy engines.
- `SHARED_NEUTRAL_UTILITY`: V2-owned ranking, source-identity/taxonomy lookup,
  Score/Valuation arithmetic, canonical valuation source, and shared schema
  DDL/layout. An internal Score input alias named `ttm_ebit` preserves its
  existing V2 arithmetic contract; it imports or writes no Score V1 model.
- `HISTORICAL_DOCUMENTATION` / `UNCLEAR`: earlier runbooks are retained for
  audit. No unresolved active-runtime V1 dependency remains.

## Test and Safety Closure

`venv/bin/pytest -q tests/test_fundamentals* \
tests/test_phase12d_operational_rebuild.py \
tests/test_production_database_isolation.py` finished with **562 passed,
14 deselected, 0 failed**. The V2 Score/full-rebuild targeted rerun finished
with **25 passed, 0 failed**. Test collection had no import errors after
retiring V1-only tests. `git diff --check` passed. No production DB, taxonomy,
or `ticker_meta` write, production analysis replacement, schema/data cleanup,
or push was performed. The recommended next step is **Phase 13G.2.5E** for
separately authorized V1 schema/data cleanup after a verified backup and
recovery review; it was not started here.
