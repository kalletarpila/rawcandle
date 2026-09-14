# Phase 13F.4.13 Durable Structural-Regime Production Activation

Status: `OUTCOME A - STRUCTURAL-REGIME PACKAGE AND RELATIVE VALUATION ACTIVE AND STABLE IN PRODUCTION`.

Phase 13F.4.13 diagnosed the Phase 13F.4.12 non-return, added a non-economic durable runner
correction, and completed one protected production activation attempt.

## Phase 13F.4.12 Stop Cause

The Phase 13F.4.12 apply command did not fail an economic gate. It was externally interrupted with
`SIGINT`/`KeyboardInterrupt` after the backup/restore-rehearsal artifacts existed and before any
`first_apply` or `second_apply` artifact was present. The previous runner caught `Exception` but
not `KeyboardInterrupt`, so it did not persist an authoritative failure JSON or final exit-code
file. Because restore-rehearsal completion was not checkpointed, the exact internal substep could
only be bounded to the uncheckpointed region after restore copy creation and before production
apply dispatch. Production hashes and active pointers remained at baseline after that phase.

## Correction

The correction was limited to runner orchestration and durability:

- stage journal with atomic current-stage snapshots;
- heartbeat file;
- final exit-code file;
- `KeyboardInterrupt`/`BaseException` failure capture;
- pre-write versus post-write failure distinction;
- rollback only after the write boundary is armed;
- bounded restore-rehearsal validation using schema, row counts, hash, quick check and foreign-key
  checks instead of full logical table-content fingerprints.

No economic formulas, structural-break semantics, identity resolution rules, dependency
fingerprints or date-aware listing eligibility were changed.

## Tests

Pre-activation:

- `python3 -m compileall rawcandle/fundamentals/phase13f4_2_production.py rawcandle/cli/run_phase13f4_13_structural_production.py`
- `pytest -q tests/test_phase13f4_13_durable_runner.py tests/test_phase13f4_12_activation.py tests/test_phase13f4_2_acceptance.py`: `32 passed`
- `pytest -q tests/test_phase13f4_13_durable_runner.py tests/test_phase13f4_2_acceptance.py tests/test_phase13f3_4_structural_integration.py tests/test_production_database_isolation.py`: `49 passed`
- `git diff --check`: passed

Post-activation:

- `pytest -q tests/test_phase13f4_13_durable_runner.py tests/test_phase13f4_2_acceptance.py tests/test_phase13f3_4_structural_integration.py tests/test_production_database_isolation.py tests/test_fundamentals_v4_relative_valuation_production.py tests/test_fundamentals_v4_company_snapshot.py tests/test_fundamentals_snapshot_ui.py`: `148 passed in 31.56s`

The Phase 13F.4.11.1 full active suite remains the full-suite gate for the accepted code base:
`2961 passed, 14 deselected, 8 warnings in 795.83s (0:13:15)`.

## Deployment Evidence

Activation command:

`python3 -m rawcandle.cli.run_phase13f4_13_structural_production --output temp/fundamentals_v4_phase13f4_13_structural_production/20260914T_PHASE13F4_13_DURABLE_PRODUCTION_ACTIVATION --apply --confirm-production`

Artifact root:

`temp/fundamentals_v4_phase13f4_13_structural_production/20260914T_PHASE13F4_13_DURABLE_PRODUCTION_ACTIVATION`

Fresh backup set:

`backups/fundamentals_v4_phase13f4_13_structural_production/20260914T_PHASE13F4_13_DURABLE_PRODUCTION_ACTIVATION`

Durable files:

- `stage_journal.jsonl`
- `stage_current.json`
- `heartbeat.jsonl`
- `exit_code`
- `phase13f4_13_result.json`

Exit code file: `0`.

Stage sequence:

`PREFLIGHT_STARTED`, `PREFLIGHT_ACCEPTED`, `BACKUP_STARTED`, `BACKUP_COMPLETE`,
`RESTORE_REHEARSAL_STARTED`, `RESTORE_REHEARSAL_COMPLETE`, `WRITE_BOUNDARY_ARMED`,
`FIRST_APPLY_STARTED`, `FIRST_APPLY_COMPLETE`, `SECOND_APPLY_STARTED`,
`SECOND_APPLY_COMPLETE`, `POSTFLIGHT_STARTED`, `POSTFLIGHT_COMPLETE`, `SUCCESS`.

## Activation Results

First production pass:

- package outcome: `APPLIED`
- package economic fingerprint: `1700f71e13935fccf7509cf8b9e99fb9f6705cfe9ddf5f49157b53d59a85e4d5`
- package content fingerprint: `f6144cc126d1a5c3af8735841800903e5e233a1953712ca4b5dd1ba0b67f654a`
- Relative Valuation outcome: `ACTIVATED`
- Relative Valuation snapshot: `1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b`
- dependencies: `COMPATIBLE`
- acceptance blockers: none

Independent second pass:

- provider replay changes: `0`
- package outcome: `NO_CHANGE`
- package second apply: `NO_CHANGE`
- Relative Position outcome: `NO_CHANGE`
- Relative Valuation outcome: `NO_CHANGE`
- Relative Valuation second apply: `NO_CHANGE`
- protected logical diff: empty
- normalized inventory no-change: true

The active package family pointer remains
`f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`; the package manifest and
dependency row carry the accepted structural economic/content fingerprints. The active Relative
Valuation snapshot is now
`1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b`.

## Company Acceptance

- AREB retained historical Relative Position rows: `12`.
- AREB post-delisting current Relative Valuation rows: `0`.
- Structural eligibility reason counts: `CURRENT_REPORT_REQUIRES_POST_EVENT_CLEAN_TTM=3`,
  `ELIGIBLE=2`.
- Snapshot smoke reports were generated for `AREB`, `IA`, `NMAD`, `NVDA`, `NXH`, `SNDK`, `VAI`
  and `VMRK`.
- Snapshot smoke reported no internal identifier leakage.

## Integrity And Hashes

`PRAGMA quick_check` returned `ok` for provider, canonical, analysis, market and taxonomy.

Post-activation database hashes:

- provider: `bbfbff45f1d3128a8e7aa9a9d5646e687943b35cf26166525eeb82d12936ad76`
- canonical: `b6521168b4dc1ce191f79bf1de13555d6786420685afb3fdb0401efb2becce2e`
- analysis: `a4207a42bf0c2d954ee3302caac938093d923e058b6edfb8426cb1c0983dddbd`
- market: `0079fe29cc55765fe387d980fc52f20f8c87c33b084fd9c86e4e08c656795dd4`
- taxonomy: `b88bdd6d885b5bf59781a3f048a521c771a7117eaba546c6b5ed7fd3af4958d0`

Market and taxonomy hashes remained unchanged.

## Rollback

Rollback was not required. The fresh verified backup set was retained.

## Cleanup

Removed phase-owned restore-rehearsal DB copies from the temp artifact root. No `.db`, `-wal`,
`-shm` or `-journal` files remain under the Phase 13F.4.13 temp artifact root.

Retained artifact root size: about `1.5M`.

Retained backup set size: about `3.0G`.

Final free space: about `615G`.

Deployment code commit used for activation: `d216f71`.
