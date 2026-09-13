# Phase 13F.4.5 Second-Run Determinism Repair

Outcome: **OUTCOME A - SECOND-RUN ROOT CAUSE REPAIRED AND FULL PIPELINE FIXED POINT VERIFIED**

Phase 13F.4.5 was run strictly copy-only. No production deployment, production activation, network request, Scheduler change or UI change was performed.

## Root Cause

The Phase 13F.4.4 second full-pipeline drift was reproduced on isolated production-shaped copies:

- Cycle 1 package economic fingerprint: `55a9713c9f20d122e493bb3c0c3485bf729724ce1914703ad637d2a16346002d`
- Cycle 2 package economic fingerprint: `4f1fab7915c07f6e0f2b601c5a732ad6f721ee40a56e60d870cb407be161b52c`
- Changed calculation fingerprints: `structural`, `score`
- Unchanged calculation fingerprints: `delta`, `diagnostic`, `lifecycle`, `relative`, `valuation`

The first differing dependency was structural contract identity metadata. `structural_break.apply_contract` built `event_id` from a payload that included `identity_status`. When provider identity links were materialized in the copy, the second calculation resolved the same company/security/event through `PROVIDER_SECURITY_IDENTITY` instead of the previous fallback path. Structural regime counts and economic status assignments were unchanged, but `event_id`, structural fingerprints, score evidence metadata and package fingerprints changed.

Classification: `TECHNICAL_METADATA_CHANGE`, not economic value, readiness, reason or eligibility change.

Field-level diff artifacts:

- `temp/fundamentals_v4_phase13f4_5_determinism/20260913T_PHASE13F45_DIAGNOSTIC_REPRO/field_level_diff.json`
- `temp/fundamentals_v4_phase13f4_5_determinism/20260913T_PHASE13F45_DIAGNOSTIC_REPRO/field_level_diff.csv`

## Repair

`rawcandle/fundamentals/structural_break.py` now derives structural `event_id`, event economic fingerprint and returned event rows from the economic event payload, excluding only the technical identity-resolution path field `identity_status`. Persisted evidence still records `identity_status` for audit.

The repair preserves sensitivity to real economic changes. A regression test verifies that provider-identity resolution and unique-active-ticker fallback produce the same structural fingerprints, while a changed event date changes the event and regime fingerprints.

The copy path-safety gate was also tightened to reject SQLite `file:` URI variants resolving to production paths, in addition to direct and symlink path checks.

## Fixed Point

Fixed-point lane:

`temp/fundamentals_v4_phase13f4_5_determinism/20260913T_PHASE13F45_FIXEDPOINT_LANE1`

- Cycle A package: `APPLIED`
- Cycle B package: `NO_CHANGE`
- Cycle C package: `NO_CHANGE`
- Fresh-process Cycle D package: `NO_CHANGE`
- Package economic fingerprint A/B/C/D: `1700f71e13935fccf7509cf8b9e99fb9f6705cfe9ddf5f49157b53d59a85e4d5`
- Package physical fingerprint A/B/C/D: `f6144cc126d1a5c3af8735841800903e5e233a1953712ca4b5dd1ba0b67f654a`
- Structural calculation fingerprint A/B/C/D: `3928f2adde7074f79250f0893d38ada3dc9429aea4b9f5d61540d377316e4cd3`
- Score calculation fingerprint A/B/C/D: `f40bbd1db1c338c06d6a3a1df2b05dfcb4eca2273bf99682c402e1f8667b0ad6`
- Relative Valuation B/C/D: `NO_CHANGE`
- SNDK Snapshot smoke: `CREATED`, content fingerprint `513f8cf14ebbf20f47696de0ca6a9aa933d435bd491b795ed3cf63a1f0148db4`, no internal IDs.

Structural candidate identities after repair:

- Structural event fingerprint: `085690bdb3479a88f53cac4248e0ab970a0a743934eca29d1d867a8eba57096d`
- Structural regime fingerprint: `57e2827981be62c9c300ac0e0a71a26afefd04dd9b9f85670593c57ebcdff8e5`
- Structural package fingerprint: `748cd15828bef0bd57f75f977aadea571053940e94b38c2a221b43335e0d6c9a`

## Independent Replay

Independent replay lane:

`temp/fundamentals_v4_phase13f4_5_determinism/20260913T_PHASE13F45_REPLAY_LANE2`

- Replay Cycle A package: `APPLIED`
- Replay Cycle B package: `NO_CHANGE`
- Replay package economic fingerprint: `1700f71e13935fccf7509cf8b9e99fb9f6705cfe9ddf5f49157b53d59a85e4d5`
- Replay package physical fingerprint: `f6144cc126d1a5c3af8735841800903e5e233a1953712ca4b5dd1ba0b67f654a`
- Replay calculation fingerprints matched lane 1.
- Replay SNDK Snapshot smoke matched lane 1.

## Production Immutability

Production postflight:

- `data/fundamentals_provider.db`: `quick_check=ok`
- `data/fundamentals_v4.db`: `quick_check=ok`
- `data/fundamentals_analysis.db`: `quick_check=ok`
- Active operating-income package remained `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- Active Relative Valuation snapshot remained `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`

Production hashes after the copy-only run:

- provider: `7957c44632ff98eda87b12014152eb26b9fd3d445c5d8d2510b7b0f9eca03e11`
- canonical: `554aaa3c8fc359b08ed0c9171f62e08e2cd59c3be2bfed1fa6ff09713275e736`
- analysis: `a46ab948a9b6b3d12078b7f09158ccde603d28ab649e6bd9015273aa3e54e8d2`
- market: `f550db289b2ce53d76ab6503e85dc04e5bf6232606ca2922cc69efdef1ed094f`
- taxonomy: `c99db877cabe7ea9e97207689d1ccddb6409284dab9c5ad4067b247996f240da`

`production_immutability` was true in fixed-point lane 1, fresh-process Cycle D and replay lane 2.

## Tests

Commands run:

- `python3 -m compileall -q rawcandle/fundamentals/structural_break.py rawcandle/fundamentals/phase13b_foundation.py rawcandle/fundamentals/phase13f4_2_production.py rawcandle/fundamentals/phase13f3_ticker_transition.py tests/test_structural_break_contract.py tests/test_phase13b_foundation.py tests/test_phase13f4_2_acceptance.py`
- `python3 -m pytest -q tests/test_structural_break_contract.py tests/test_phase13b_foundation.py tests/test_phase13f4_2_acceptance.py tests/test_phase13f3_4_structural_integration.py tests/test_phase13f3_2_successor_recovery.py tests/test_phase13f3_ticker_transition.py`: `49 passed`
- `git diff --check`: passed
- `python3 -m pytest -q`: `2947 passed, 14 deselected, 8 warnings`

## Cleanup

Phase-owned database copies were removed after evidence capture. Compact JSON, CSV, Markdown and telemetry evidence were retained under `temp/fundamentals_v4_phase13f4_5_determinism`.

## Remaining Risk And Phase 13F.4.6

The fixed-point requirement is satisfied. A future Phase 13F.4.6 production retry is justified only as a separately authorized production deployment, using the repaired fingerprints and the full backup/rollback runbook gates. This report does not authorize or execute production deployment.
