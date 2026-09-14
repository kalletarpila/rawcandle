# Phase 13F.4.12 Structural-Regime Production Activation

Status: `OUTCOME B - PRE-WRITE BLOCKER; PRODUCTION REMAINS UNCHANGED`.

Phase 13F.4.12 was authorized for one protected production activation attempt. The phase prepared
and entered the protected runner, but did not produce a conclusive production apply result. The run
created a fresh verified backup set and restore-rehearsal copies after an accepted prewrite
candidate, then stopped without `first_apply` or `second_apply` artifacts. Production hashes and
active pointers remained at the verified baseline, so no rollback was required.

## Verified Baseline

Required commits were present before the attempt: `1c35b1c`, `863af30` and `7de588e`.

The Phase 13F.4.11.1 full-suite gate was reused because no shared calculation or persistence code
changed before the production attempt:

- exit code: `0`
- result: `2961 passed, 14 deselected, 8 warnings in 795.83s (0:13:15)`
- evidence root: `temp/fundamentals_v4_phase13f4_11_1_full_suite_gate/full_active_suite_after_fix`

Configured production paths:

- provider: `data/fundamentals_provider.db`
- canonical: `data/fundamentals_v4.db`
- analysis: `data/fundamentals_analysis.db`
- market: `data/osakedata.db`
- taxonomy: `data/analysis.db`

Initial active identities:

- package: `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- Relative Valuation snapshot: `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`

## Pre-Write Gates

Pre-apply verification passed:

- `python3 -m compileall rawcandle/cli/run_phase13f4_12_structural_production.py rawcandle/fundamentals/phase13f4_2_production.py`
- `pytest -q tests/test_phase13f4_12_activation.py tests/test_phase13f4_2_acceptance.py tests/test_phase13f3_4_structural_integration.py tests/test_production_database_isolation.py`: `48 passed in 13.28s`
- `git diff --check`: passed
- no conflicting writer process was reported by the runner preflight
- storage gate required about `11.5 GB`; final free space after cleanup was about `618 GB`
- production `PRAGMA quick_check` returned `ok` for provider, canonical, analysis, market and taxonomy

The wrapper added a Phase 13F.4.12-specific gate for the required commits and durable
Phase 13F.4.11.1 full-suite evidence. That gate passed.

## Accepted Candidate

The copy prewrite candidate completed with no acceptance blockers.

Accepted fingerprints:

- structural contract: `ECONOMIC_STRUCTURAL_BREAK_CONTRACT_V1`
- structural source: `c9fd41fdedc7b926d801bf7d56884746e552bc6593fba92c22db1e522c1a63d6`
- structural event: `085690bdb3479a88f53cac4248e0ab970a0a743934eca29d1d867a8eba57096d`
- structural regime: `57e2827981be62c9c300ac0e0a71a26afefd04dd9b9f85670593c57ebcdff8e5`
- structural package: `748cd15828bef0bd57f75f977aadea571053940e94b38c2a221b43335e0d6c9a`
- package economic: `1700f71e13935fccf7509cf8b9e99fb9f6705cfe9ddf5f49157b53d59a85e4d5`
- package persisted content: `f6144cc126d1a5c3af8735841800903e5e233a1953712ca4b5dd1ba0b67f654a`
- Relative Valuation snapshot: `1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b`
- Relative Valuation result: `9c642e80b06fdbb8c6e703a46a6bda2c7031bc270fbd195b0a3acd7cdeba30f3`
- Relative Valuation source: `af0e480b64d57bfc8f65fe2ddf9777cfdf5d7b8afbb801bcf95aaea44ebc61ee`

The candidate reported dependency status `COMPATIBLE` and AREB post-delisting Relative Valuation
rows `0`.

## Backup And Restore Rehearsal

Fresh backups were created and retained under:

`backups/fundamentals_v4_phase13f4_12_structural_production/20260914T_PHASE13F4_12_PRODUCTION_ACTIVATION`

Backup manifest:

`backups/fundamentals_v4_phase13f4_12_structural_production/20260914T_PHASE13F4_12_PRODUCTION_ACTIVATION/backup_manifest.json`

Backup hashes:

- provider: `7957c44632ff98eda87b12014152eb26b9fd3d445c5d8d2510b7b0f9eca03e11`
- canonical: `554aaa3c8fc359b08ed0c9171f62e08e2cd59c3be2bfed1fa6ff09713275e736`
- analysis: `a46ab948a9b6b3d12078b7f09158ccde603d28ab649e6bd9015273aa3e54e8d2`

Each backup had `quick_check=ok` and zero foreign-key errors. Restore-rehearsal database copies
were created, then removed during cleanup because they were phase-owned transient artifacts.

## Production Apply

The protected command was:

`python3 -m rawcandle.cli.run_phase13f4_12_structural_production --output temp/fundamentals_v4_phase13f4_12_structural_production/20260914T_PHASE13F4_12_PRODUCTION_ACTIVATION --apply --confirm-production`

The command did not return a final production apply JSON. Artifact inspection showed:

- no `first_apply` directory;
- no `second_apply` directory;
- the previous dry-run `phase13f4_12_result.json` remained the only result file;
- backup and restore-rehearsal artifacts existed;
- production active package and Relative Valuation pointers remained at baseline.

The hanging tool session was interrupted only after production hashes and active pointers proved
baseline state.

## Production State Afterward

Post-attempt hashes:

- provider: `7957c44632ff98eda87b12014152eb26b9fd3d445c5d8d2510b7b0f9eca03e11`
- canonical: `554aaa3c8fc359b08ed0c9171f62e08e2cd59c3be2bfed1fa6ff09713275e736`
- analysis: `a46ab948a9b6b3d12078b7f09158ccde603d28ab649e6bd9015273aa3e54e8d2`
- market: `0079fe29cc55765fe387d980fc52f20f8c87c33b084fd9c86e4e08c656795dd4`
- taxonomy: `b88bdd6d885b5bf59781a3f048a521c771a7117eaba546c6b5ed7fd3af4958d0`

Post-attempt active identities:

- package: `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- Relative Valuation snapshot: `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`

`PRAGMA quick_check` returned `ok` for all five configured production databases. No rollback was
performed because the writable production databases remained unchanged.

## Cleanup

Removed phase-owned restore-rehearsal database copies:

- `restore_rehearsal/provider.restored.db`
- `restore_rehearsal/canonical.restored.db`
- `restore_rehearsal/analysis.restored.db`

Retained:

- compact temp evidence under `temp/fundamentals_v4_phase13f4_12_structural_production`
- full backup set under `backups/fundamentals_v4_phase13f4_12_structural_production`

Final artifact root size was about `496K`; retained backup set size was about `3.0G`; free space was
about `618G`.

## Remaining Risks

The economic candidate remains accepted by the prewrite copy gate, but production activation is not
complete. Do not treat the structural-regime package or the new Relative Valuation snapshot as
active in production. A later phase must first explain why the protected apply command failed to
return an authoritative result after backup/restore rehearsal and before visible `first_apply`
artifacts.

Deployment code commit used for the attempted run: `562ccae`.
