# Phase 13F.4.3 Structural-Regime Production Deployment Retry

Date: 2026-09-13

## Outcome

`OUTCOME C — DEPLOYMENT FAILED AND COMPLETE BACKUP SET RESTORED SUCCESSFULLY`

The single allowed Phase 13F.4.3 production retry was executed once and was not repeated. The run failed in the post-build acceptance gate with:

`PHASE13F4_2_ACCEPTANCE_BLOCKERS:STRUCTURAL_SOURCE_FINGERPRINT`

The runner restored the complete fresh Phase 13F.4.3 writable backup set for:

- `data/fundamentals_provider.db`
- `data/fundamentals_v4.db`
- `data/fundamentals_analysis.db`

No Phase 13F.4.2 backup or evidence directory was modified.

## Evidence

Preflight dry-run artifact:

`temp/fundamentals_v4_phase13f4_3_structural_production/20260913T_PHASE13F4_3_PREFLIGHT_DRYRUN`

Production retry artifact:

`temp/fundamentals_v4_phase13f4_3_structural_production/20260913T_PHASE13F4_3_PRODUCTION_RETRY`

Fresh rollback backup set:

`backups/fundamentals_v4_phase13f4_3_structural_production/20260913T_PHASE13F4_3_PRODUCTION_RETRY`

Preflight gates passed before the single retry:

- git status clean: `true`
- conflicting writer processes: `[]`
- free bytes: `780651892736`
- active package before retry: `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- active Relative Valuation snapshot before retry: `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`

The failed retry still rebuilt the production downstream chain before the acceptance failure and rollback far enough to prove the previously accepted package and Relative Valuation identities:

- package economic fingerprint: `55a9713c9f20d122e493bb3c0c3485bf729724ce1914703ad637d2a16346002d`
- package physical fingerprint: `718e3fbe838f273775d77042fa0dbaa706c822277a3e23d5dd7eeaaa4ebb8811`
- Relative Valuation snapshot: `1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b`
- Relative Valuation result fingerprint: `9c642e80b06fdbb8c6e703a46a6bda2c7031bc270fbd195b0a3acd7cdeba30f3`
- structural source fingerprint in RV source metadata: `04339360f686ae6d68c6f502139a9af4cf6ebe38699c22ba30d6216a6ff06e1f`

Post-rollback production state:

- provider restored SHA256: `7957c44632ff98eda87b12014152eb26b9fd3d445c5d8d2510b7b0f9eca03e11`
- canonical restored SHA256: `554aaa3c8fc359b08ed0c9171f62e08e2cd59c3be2bfed1fa6ff09713275e736`
- analysis restored SHA256: `a46ab948a9b6b3d12078b7f09158ccde603d28ab649e6bd9015273aa3e54e8d2`
- active package after rollback: `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- active Relative Valuation snapshot after rollback: `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`
- `PRAGMA quick_check`: `ok` for all three writable databases
- no WAL, SHM or journal sidecars for the three writable databases

## Root Cause

The failure was a stale acceptance-checker field expectation, not a production data defect.

The accepted structural source fingerprint is:

`04339360f686ae6d68c6f502139a9af4cf6ebe38699c22ba30d6216a6ff06e1f`

The accepted structural regime fingerprint is:

`b6c1fbed8182ee589e3f85ee7057571ff34b75f56de7d92f4b1a3d74aac64852`

Phase 13F.3.4 rehearsal artifacts already used the `b6c1...` regime fingerprint while producing the accepted structural package fingerprint:

`4ba542c7e28c2d92ba65863f2932e2683a60b053cb4b2debe344b051a84441ad`

The Phase 13F.4.3 acceptance gate incorrectly compared `structural_contract.regime_fingerprint` to the structural source fingerprint. The gate has been corrected to compare the regime field to the accepted regime fingerprint and to report `STRUCTURAL_REGIME_FINGERPRINT` if it fails.

The dependency metadata helper now records `structural_regime_fingerprint` instead of overloading `structural_source_fingerprint` with a regime value. The independently computed `structural_contract_fingerprint` remains the source-level dependency value produced by `attach_dependencies`.

## Verification

Commands run after the correction:

```text
python3 -m compileall -q rawcandle/fundamentals/phase13f4_2_production.py rawcandle/cli/run_phase13f4_3_structural_production.py
pytest -q tests/test_phase13f4_2_acceptance.py tests/test_phase13f3_4_structural_integration.py tests/test_phase13f3_2_successor_recovery.py tests/test_phase13f3_ticker_transition.py tests/test_phase13b_foundation.py
```

Result:

`23 passed in 12.31s`

The complete repository suite was not run because Phase 13F.4.3 did not reach Outcome A and a second production retry was explicitly disallowed for this run.
