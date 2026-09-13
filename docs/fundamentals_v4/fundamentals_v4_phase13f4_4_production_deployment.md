# Phase 13F.4.4 Structural-Regime Production Deployment Final Retry

Date: 2026-09-13

## Outcome

`OUTCOME C — DEPLOYMENT FAILED AND COMPLETE BACKUP SET RESTORED SUCCESSFULLY`

Exactly one Phase 13F.4.4 production attempt was run. It failed after production writes in the independent second full-pipeline no-change gate and restored the complete fresh Phase 13F.4.4 writable database backup set. No second production attempt was made.

## Evidence Roots

- Dry-run/preflight: `temp/fundamentals_v4_phase13f4_4_structural_production/20260913T_PHASE13F4_4_PREFLIGHT_DRYRUN`
- Production attempt: `temp/fundamentals_v4_phase13f4_4_structural_production/20260913T_PHASE13F4_4_PRODUCTION_FINAL_RETRY`
- Fresh protected backups: `backups/fundamentals_v4_phase13f4_4_structural_production/20260913T_PHASE13F4_4_PRODUCTION_FINAL_RETRY`

Earlier Phase 13F.4.2 and 13F.4.3 backups and evidence were preserved unchanged.

## Baseline

Configured production database paths:

- provider: `data/fundamentals_provider.db`
- canonical: `data/fundamentals_v4.db`
- analysis: `data/fundamentals_analysis.db`
- market: `data/osakedata.db`
- taxonomy: `data/analysis.db`

Pre-write production state:

- active package: `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- active Relative Valuation snapshot: `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`
- writer conflicts: `[]`
- write-set sidecars: none
- free space before dry-run: `774407303168` bytes
- conservative required space estimate: `11508113408` bytes

The write set remained provider, canonical and analysis. Market and taxonomy remained read-only.

## Acceptance Contract

Phase 13F.4.4 added a compact machine-readable acceptance contract:

`temp/fundamentals_v4_phase13f4_4_structural_production/20260913T_PHASE13F4_4_PRODUCTION_FINAL_RETRY/acceptance_contract.json`

The checker now consumes a normalized acceptance view with separate semantic fields for:

- structural contract version: `ECONOMIC_STRUCTURAL_BREAK_CONTRACT_V1`
- structural source fingerprint: `04339360f686ae6d68c6f502139a9af4cf6ebe38699c22ba30d6216a6ff06e1f`
- structural event fingerprint: `5ec6403d231e41a52fdf04609892df1c9bdd841805180a52578b638114bf5bfd`
- structural regime fingerprint: `b6c1fbed8182ee589e3f85ee7057571ff34b75f56de7d92f4b1a3d74aac64852`
- structural package fingerprint: `4ba542c7e28c2d92ba65863f2932e2683a60b053cb4b2debe344b051a84441ad`
- package economic fingerprint: `55a9713c9f20d122e493bb3c0c3485bf729724ce1914703ad637d2a16346002d`
- package physical fingerprint: `718e3fbe838f273775d77042fa0dbaa706c822277a3e23d5dd7eeaaa4ebb8811`
- Relative Valuation snapshot: `1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b`
- Relative Valuation result fingerprint: `9c642e80b06fdbb8c6e703a46a6bda2c7031bc270fbd195b0a3acd7cdeba30f3`

The pre-write real-shaped copy candidate passed this contract with no blockers. Its acceptance view is retained in:

`temp/fundamentals_v4_phase13f4_4_structural_production/20260913T_PHASE13F4_4_PRODUCTION_FINAL_RETRY/prewrite_candidate/prewrite_candidate_result.json`

The pre-write candidate also generated Snapshot smoke reports for `AREB`, `IA`, `NMAD`, `NVDA`, `NXH`, `VAI` and `VMRK`; all were created without internal database identifiers. `SNDK` was not in the current runner smoke-list and therefore was not independently verified in Phase 13F.4.4 before the rollback outcome.

## Failure

The production first apply matched the accepted package and Relative Valuation identities:

- package first apply: `APPLIED`
- package second apply: `NO_CHANGE`
- package economic fingerprint: `55a9713c9f20d122e493bb3c0c3485bf729724ce1914703ad637d2a16346002d`
- package physical fingerprint: `718e3fbe838f273775d77042fa0dbaa706c822277a3e23d5dd7eeaaa4ebb8811`
- RV first apply: `ACTIVATED`
- RV second apply: `NO_CHANGE`
- RV snapshot: `1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b`
- RV result fingerprint: `9c642e80b06fdbb8c6e703a46a6bda2c7031bc270fbd195b0a3acd7cdeba30f3`

The subsequent independent full-pipeline no-change pass failed:

`PHASE13F4_2_SECOND_RUN_NOT_NO_CHANGE`

Field-level evidence:

- provider replay changes: `0`
- package first apply outcome in second full pass: `APPLIED`
- package inner second apply outcome in second full pass: `NO_CHANGE`
- Relative Position outcome: `NO_CHANGE`
- Relative Valuation first apply outcome: `NO_CHANGE`
- Relative Valuation second apply outcome: `NO_CHANGE`
- package economic fingerprint changed in the second full pass: `55a971...` -> `4f1fab...`
- package physical fingerprint changed in the second full pass: `718e3f...` -> `128a6a...`
- package calculation fingerprints changed in `structural` and `score`
- taxonomy SHM mtime changed without content hash change, but this was not the material blocker

This is a real full-pipeline determinism/no-change blocker, not the Phase 13F.4.2 RV snapshot accessor bug and not the Phase 13F.4.3 structural source/regime field mixup.

## Rollback

The runner restored the coordinated writable backup set:

- provider restored SHA256: `7957c44632ff98eda87b12014152eb26b9fd3d445c5d8d2510b7b0f9eca03e11`
- canonical restored SHA256: `554aaa3c8fc359b08ed0c9171f62e08e2cd59c3be2bfed1fa6ff09713275e736`
- analysis restored SHA256: `a46ab948a9b6b3d12078b7f09158ccde603d28ab649e6bd9015273aa3e54e8d2`

Post-rollback production state:

- active package: `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- active Relative Valuation snapshot: `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`
- provider, canonical and analysis `PRAGMA quick_check`: `ok`
- provider, canonical and analysis `PRAGMA foreign_key_check`: zero rows
- write-set WAL/SHM/journal sidecars: none

## Cleanup

Removed Phase 13F.4.4-owned transient restore rehearsal databases:

- `temp/.../restore_rehearsal/canonical.restored.db`
- `temp/.../restore_rehearsal/analysis.restored.db`
- `temp/.../restore_rehearsal/provider.restored.db`

Retained:

- fresh Phase 13F.4.4 production backups
- compact JSON evidence
- package and Relative Valuation telemetry JSON
- previous Phase 13F.4.2 and 13F.4.3 evidence

Final free space after cleanup: approximately `719G`.

## Verification

Commands run:

```text
python3 -m compileall -q rawcandle/fundamentals/phase13f4_2_production.py rawcandle/cli/run_phase13f4_4_structural_production.py rawcandle/cli/run_phase13f4_3_structural_production.py
pytest -q tests/test_phase13f4_2_acceptance.py tests/test_phase13f3_4_structural_integration.py tests/test_phase13f3_2_successor_recovery.py tests/test_phase13f3_ticker_transition.py tests/test_phase13b_foundation.py
git diff --check
python3 JSON parse check over retained Phase 13F.4.4 JSON evidence
```

Focused tests passed: `42 passed`.

The full repository suite and post-success UI/Snapshot/RP/RV regression set were not run because Phase 13F.4.4 did not reach Outcome A and production was restored.

## Remaining Risk

Before another production attempt, the second full-pipeline determinism mismatch must be resolved on copies. The likely investigation surface is the structural/regime and score fingerprint drift between first and second full-pipeline passes after the shared current economic rows have already been replaced. Do not treat the taxonomy SHM mtime-only observation as sufficient explanation for the economic fingerprint change.

