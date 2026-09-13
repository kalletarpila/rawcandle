# Phase 13F.3.4 Structural Regime Integration

Date: 2026-09-13

Outcome: OUTCOME A - FIRST-CLASS STRUCTURAL-REGIME CANDIDATE VERIFIED END TO END AND READY FOR SEPARATELY AUTHORIZED PRODUCTION DEPLOYMENT.

This phase promoted the Phase 13F.3.3 economic structural-break contract from an isolated copy-only contract into the active operating-income v2 package calculation path on rehearsal copies. No production data was modified.

## Scope

- Added structural-regime awareness to Score history windows, Score component readiness, Lifecycle state continuity, Valuation readiness reasons, Delta history selection, Diagnostics, Relative Position source selection and Relative Valuation source compatibility.
- Preserved legacy behavior when structural metadata is absent.
- Preserved formula/model identities for the existing Score, Lifecycle, Valuation, Delta, Diagnostic, Relative Position and Relative Valuation contracts. The structural layer is an additional economic dependency, not an unreviewed formula rewrite.
- Reused the Phase 13F.3.3 rehearsal runner as the copy-only orchestration harness. The runner's internal result label still says `VERSIONED STRUCTURAL-BREAK CONTRACT IMPLEMENTED`, but the executed code path includes the Phase 13F.3.4 structural-regime integration changes.

## Code Changes

- `rawcandle/fundamentals/score/engine.py`: Score now rejects five-observation trajectory windows that cross incompatible structural regimes, prevents prior-quarter share comparisons across structural boundaries and forces structural-not-ready endpoints to `SCORE_NOT_READY`.
- `rawcandle/fundamentals/valuation/engine.py`: Valuation now preserves structural blocker reasons such as `CURRENT_REPORT_REQUIRES_POST_EVENT_CLEAN_TTM` instead of collapsing them into generic `TTM_NOT_READY`.
- `rawcandle/fundamentals/operating_income_v2/rehearsal.py`: The package rehearsal now annotates TTM rows with structural metadata, resets Lifecycle across structural regimes, scopes Delta history to compatible regimes, blocks structurally ineligible current endpoints from current cross-sectional source layers and records structural fingerprints.
- `rawcandle/fundamentals/operating_income_v2/phase10b.py`: The candidate package apply path now accepts intentional structural contract differences and derives diagnostic consistency with structural-regime awareness.
- `rawcandle/fundamentals/phase13f3_3_structural_break_contract.py`: Failure evidence now includes tracebacks for rehearsal debugging.
- `tests/test_phase13f3_4_structural_integration.py`: Added focused structural integration coverage.

## Rehearsal

Artifact root:

`temp/fundamentals_v4_phase13f3_4_structural_regime_integration/20260913T_PHASE13F3_4_FINAL3`

Command:

```bash
python3 -m rawcandle.cli.run_phase13f3_3_structural_break_contract --output temp/fundamentals_v4_phase13f3_4_structural_regime_integration/20260913T_PHASE13F3_4_FINAL3
```

Result:

- Blockers: none.
- Determinism: `match=true`.
- Deterministic economic fingerprint: `f48e674136b3c1a41b0200ed4257f6453a3a177aae94497dde41591cd0711a83`.
- Elapsed time: 993.749 seconds.
- Production immutability: true after normalized comparison.
- Ignored metadata-only drift: taxonomy `-shm` mtime changed while sidecar content hash and size were unchanged.
- Retained machine artifacts: 12 JSON files, all parsed successfully. No CSV files were emitted.
- Cleanup: no `.db`, `-wal`, `-shm` or `-journal` files remained under FINAL3 after cleanup.

## Structural Evidence

- Contract: `ECONOMIC_STRUCTURAL_BREAK_CONTRACT_V1`.
- Structural package fingerprint: `4ba542c7e28c2d92ba65863f2932e2683a60b053cb4b2debe344b051a84441ad`.
- Event fingerprint: `5ec6403d231e41a52fdf04609892df1c9bdd841805180a52578b638114bf5bfd`.
- Current structural source fingerprint: `04339360f686ae6d68c6f502139a9af4cf6ebe38699c22ba30d6216a6ff06e1f`.
- Event count: 5.
- Quarter regime rows: 197.
- TTM regime rows: 197.
- Current eligibility reason counts: `ELIGIBLE=2`, `CURRENT_REPORT_REQUIRES_POST_EVENT_CLEAN_TTM=3`.

Company matrix:

| Company | Successor | Structural status | Review status | Current eligibility |
| --- | --- | --- | --- | --- |
| 787 | VMRK | MAJOR_BUSINESS_COMBINATION | ACCEPTED | CURRENT_REPORT_REQUIRES_POST_EVENT_CLEAN_TTM |
| 1166 | IA | NO_ECONOMIC_BREAK | ACCEPTED | ELIGIBLE |
| 82 | VAI | BUSINESS_COMPARABILITY_REVIEW_REQUIRED | REVIEW_REQUIRED | CURRENT_REPORT_REQUIRES_POST_EVENT_CLEAN_TTM |
| 278 | NXH | TICKER_REUSE_SEPARATION | ACCEPTED | ELIGIBLE |
| 1304 | NMAD | REVERSE_MERGER_MAJOR_BUSINESS_CHANGE | ACCEPTED | CURRENT_REPORT_REQUIRES_POST_EVENT_CLEAN_TTM |

## Package Evidence

- Package first apply: `APPLIED`.
- Package second apply: `NO_CHANGE`.
- First apply logical changes: 2,396,550.
- Second apply logical changes: 0.
- Package economic result fingerprint: `55a9713c9f20d122e493bb3c0c3485bf729724ce1914703ad637d2a16346002d`.
- Package physical content fingerprint: `718e3fbe838f273775d77042fa0dbaa706c822277a3e23d5dd7eeaaa4ebb8811`.
- Diagnostic source fingerprint: `5d7fa30e1649d6c51c29cb80171790d90b05a5a532863a9b71fe1bb4f215048c`.
- Diagnostic economic fingerprint: `d6d5efb849a9d1e968d2f7ea01e5f9aa3d61db4d774f3af4ca1846ff7ecdb1c9`.
- Diagnostic physical fingerprint: `3c4c3d7703c3fb1320e006b66204b7327961feaf81a2b5b6790dfe3d2e3f96db`.

Persisted package rows:

| Layer | Rows |
| --- | ---: |
| score | 87,525 |
| score_component | 612,675 |
| lifecycle | 87,525 |
| valuation | 87,525 |
| delta | 87,525 |
| delta_component | 612,675 |
| diagnostic_endpoint | 87,525 |
| diagnostic_evaluation | 700,200 |
| relative_coverage | 19,620 |
| relative_result | 13,755 |

## Relative Valuation

- Pre-refresh compatibility: `OPERATIONAL_UNIVERSE_MISMATCH`.
- Pre-refresh snapshot: `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`.
- Post-refresh compatibility: `COMPATIBLE`.
- Post-refresh snapshot: `1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b`.
- Manual refresh first apply: `ACTIVATED`.
- Manual refresh second apply: `NO_CHANGE`.
- Second refresh logical zero writes: true.
- Second refresh physical no change: true.
- Current company count: 2,435.
- Current fresh count: 2,427.
- Component rows: 7,305.
- Own-history rows: 2,435.
- Peer rows: 9,740.
- Snapshot result fingerprint: `9c642e80b06fdbb8c6e703a46a6bda2c7031bc270fbd195b0a3acd7cdeba30f3`.

## Snapshot Evidence

Snapshots were generated for `AREB`, `IA`, `NMAD`, `NVDA`, `NXH`, `VAI` and `VMRK`; all returned `CREATED` and none exposed internal IDs.

AREB remained date-aware:

- Post-delisting Relative Valuation rows: 0.
- Relative Position rows retained for historical coverage: 12.

## Defects Found And Corrected

- The first rehearsal exposed `AttributeError: 'ScoreObservation' object has no attribute 'current_observation_id'` in Delta history filtering. The fix uses the actual fiscal observation identity.
- The second rehearsal exposed `KeyError: 82` after structurally not-ready current endpoints were filtered out of their own Delta history. The fix keeps the current endpoint in Delta history and restricts only non-current history to compatible structural regimes.
- Failure evidence was enhanced with tracebacks to make any future rehearsal failure field-local instead of opaque.

## Tests

Focused and regression tests passed:

- `python3 -m py_compile rawcandle/fundamentals/score/engine.py rawcandle/fundamentals/valuation/engine.py rawcandle/fundamentals/operating_income_v2/rehearsal.py tests/test_phase13f3_4_structural_integration.py`
- `pytest tests/test_phase13f3_4_structural_integration.py tests/test_fundamentals_v4_operating_income_v2.py::test_score_v2_uses_operating_income_and_preserves_unaffected_components tests/test_fundamentals_v4_operating_income_v2.py::test_valuation_v2_operating_yield_missing_negative_and_not_applicable`
- `pytest tests/test_fundamentals_v4_operating_income_v2.py tests/test_fundamentals_v4_operating_income_v2_persistence.py tests/test_structural_break_contract.py tests/test_fundamentals_v4_relative_position_source.py tests/test_fundamentals_v4_relative_valuation_source.py`
- `pytest tests/test_fundamentals_v4_operating_income_v2_phase10c.py tests/test_fundamentals_v4_diagnostic_flags_phase10b.py tests/test_phase13f3_4_structural_integration.py`
- `python3 -m py_compile rawcandle/fundamentals/operating_income_v2/phase10b.py rawcandle/fundamentals/operating_income_v2/rehearsal.py rawcandle/fundamentals/score/engine.py rawcandle/fundamentals/valuation/engine.py`
- `pytest tests/test_phase13f3_4_structural_integration.py tests/test_fundamentals_v4_diagnostic_flags_phase10b.py::test_candidate_has_new_identities_and_is_activation_eligible tests/test_fundamentals_v4_operating_income_v2_persistence.py::test_complete_parallel_apply_noop_readers_and_v1_coexistence`
- Full repository suite: 2,923 passed, 14 deselected, 8 warnings in 589.57 seconds.

## Production State

Production databases were opened only through read-only and copy-only paths. Production quick checks after rehearsal were ok for the analysis, canonical, market, provider and taxonomy databases. Active production package and active production Relative Valuation snapshot remained unchanged:

- Active package family: `OPERATING_INCOME_MODEL_FAMILY_V2`.
- Active package family fingerprint: `634824f179652da81ea6f38962d9a7c87df37c0627fed089a918ce9efa83d8e9`.
- Active package persistence fingerprint: `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`.
- Active Relative Valuation snapshot: `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`.

Final free space reported by the rehearsal was 732.87 GiB. A later workspace check showed 696 GB available on `/home/kalle/projects/rawcandle` and `/tmp`.
