# Phase 13F.4.7 Structural-Regime Production Activation

Status: `OUTCOME C - DEPLOYMENT FAILED AND COMPLETE BACKUP SET RESTORED SUCCESSFULLY`.

Phase 13F.4.7 was run on 2026-09-13 as the single protected production write attempt authorized
by the phase prompt. The run crossed the production write boundary, created fresh verified backups,
completed the first production apply, completed an independent second full-pipeline pass with
logical `NO_CHANGE` results, then failed the final inventory no-change gate. The runner restored the
complete writable database set from the fresh Phase 13F.4.7 backups. No second production write
attempt was made.

## Paths

- Artifact root: `temp/fundamentals_v4_phase13f4_7_structural_production/20260913T_PHASE13F4_7_PRODUCTION_ACTIVATION`
- Result file: `phase13f4_7_result.json`
- Backup root: `backups/fundamentals_v4_phase13f4_7_structural_production/20260913T_PHASE13F4_7_PRODUCTION_ACTIVATION`
- Writable set: provider, canonical, analysis
- Read-only roles: market, taxonomy

## Pre-Write Reconciliation

The Phase 13F.4.6 acceptance correction was present at commit `caaff47`. Active expectations no
longer used the stale structural source fingerprint `043393...`, package economic fingerprint
`55a971...` or package physical fingerprint `718e3f...`.

The normalized acceptance checker passed against the retained Phase 13F.4.6 candidate with no
blockers. Phase 13F.4.5 fixed-point lane A/B/C/D and replay lane evidence all matched:

- Structural source fingerprint: `c9fd41fdedc7b926d801bf7d56884746e552bc6593fba92c22db1e522c1a63d6`
- Structural event fingerprint: `085690bdb3479a88f53cac4248e0ab970a0a743934eca29d1d867a8eba57096d`
- Structural regime fingerprint: `57e2827981be62c9c300ac0e0a71a26afefd04dd9b9f85670593c57ebcdff8e5`
- Structural package fingerprint: `748cd15828bef0bd57f75f977aadea571053940e94b38c2a221b43335e0d6c9a`
- Package economic fingerprint: `1700f71e13935fccf7509cf8b9e99fb9f6705cfe9ddf5f49157b53d59a85e4d5`
- Package physical fingerprint: `f6144cc126d1a5c3af8735841800903e5e233a1953712ca4b5dd1ba0b67f654a`
- Relative Valuation snapshot: `1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b`
- Relative Valuation result fingerprint: `9c642e80b06fdbb8c6e703a46a6bda2c7031bc270fbd195b0a3acd7cdeba30f3`
- Relative Valuation source fingerprint: `af0e480b64d57bfc8f65fe2ddf9777cfdf5d7b8afbb801bcf95aaea44ebc61ee`

## Baseline And Gates

Before the production write attempt:

- Worktree was clean.
- Lock `temp/.fundamentals_phase9e.lock` was available.
- No conflicting writer process was found.
- Storage gate required about 11.5 GB and had about 771 GB available.
- `PRAGMA quick_check` returned `ok` for provider, canonical, analysis, market and taxonomy.
- `PRAGMA foreign_key_check` returned zero rows for provider, canonical and analysis.
- Expected active OI persistence fingerprint was present:
  `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- Expected active RV snapshot was present:
  `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`

The taxonomy database had a pre-existing WAL/SHM state. Opening it through normal SQLite checks
checkpointed the non-empty WAL before production writes, changing the taxonomy main-file physical
hash from `c99db877cabe7ea9e97207689d1ccddb6409284dab9c5ad4067b247996f240da` to
`244d152094f8577d9673b93b1b321ca2975dc94b5cd0475512f8fd12c9a08943`. Taxonomy remained read-only
for the production runner and passed `quick_check`.

## Production Attempt

The prewrite candidate passed acceptance. The production attempt then created fresh backups and
performed restore rehearsal on safe copies.

Backup files retained:

- `fundamentals_provider.db`
- `fundamentals_v4.db`
- `fundamentals_analysis.db`
- `backup_manifest.json`

First production apply:

- Package first apply: `APPLIED`
- Package inner second apply: `NO_CHANGE`, logical changes `0`
- Package economic fingerprint: `1700f71e13935fccf7509cf8b9e99fb9f6705cfe9ddf5f49157b53d59a85e4d5`
- Package physical fingerprint: `f6144cc126d1a5c3af8735841800903e5e233a1953712ca4b5dd1ba0b67f654a`
- RV first apply: `ACTIVATED`
- RV second apply: `NO_CHANGE`
- RV snapshot: `1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b`

Independent second full pass:

- Provider staging changes: `0`
- Package first apply: `NO_CHANGE`, logical changes `0`
- Package inner second apply: `NO_CHANGE`, logical changes `0`
- Relative Position: `NO_CHANGE`
- Relative Valuation first apply: `NO_CHANGE`
- Relative Valuation second apply: `NO_CHANGE`
- Active RV snapshot remained `1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b`

Failure reason:

`PHASE13F4_2_SECOND_RUN_NOT_NO_CHANGE`

The no-change payload showed all economic/calculation outcomes were fixed-point, but
`inventory_normalized_no_change` was false. The only field named by the runner as content-identical
metadata was taxonomy `shm` mtime drift. Because the failure occurred after production writes began,
the phase policy required immediate rollback and prohibited a second production attempt.

## Rollback Verification

The runner restored provider, canonical and analysis from the fresh backup set. Restoration had no
restore error.

Restored writable database hashes:

- Provider: `7957c44632ff98eda87b12014152eb26b9fd3d445c5d8d2510b7b0f9eca03e11`
- Canonical: `554aaa3c8fc359b08ed0c9171f62e08e2cd59c3be2bfed1fa6ff09713275e736`
- Analysis: `a46ab948a9b6b3d12078b7f09158ccde603d28ab649e6bd9015273aa3e54e8d2`

Post-restore active production identities reverted to the pre-attempt baseline:

- Active OI package persistence fingerprint:
  `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- Active OI package economic fingerprint:
  `7448d7b9212ce4645cf000d6264d824f3f488cdf5d7fce3ba7f6df839c3b8e78`
- Active OI package physical fingerprint:
  `369793b4036a1e407f9721ed6a3f5f455ffc3b7e9500c8ba00ecae92b49ab31d`
- Active RV snapshot:
  `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`
- Active RV result fingerprint:
  `7a207058792a8e35da35d7a4d4ab384b6621a9ca0ad2ada12f4c883ead652315`

Post-restore checks:

- Provider quick_check: `ok`
- Canonical quick_check: `ok`
- Analysis quick_check: `ok`
- Market hash remained `f550db289b2ce53d76ab6503e85dc04e5bf6232606ca2922cc69efdef1ed094f`
- Taxonomy quick_check: `ok`

## Snapshot Smoke

Snapshot reports were generated during the first and second apply attempts for:

- `VMRK`: Relative Position available; Relative Valuation unavailable for the report date.
- `IA`: Relative Position available; Relative Valuation available on snapshot `2026-09-12`.
- `VAI`: Relative Position available; Relative Valuation unavailable for the report date.
- `NXH`: Relative Position available; Relative Valuation available on snapshot `2026-09-12`.
- `NMAD`: Relative Position available; Relative Valuation unavailable for the report date.
- `AREB`: Relative Position available; Relative Valuation unavailable for the report date.
- `NVDA`: Relative Position available; Relative Valuation available on snapshot `2026-09-12`.
- `SNDK`: Relative Position available; Relative Valuation available on snapshot `2026-09-12`.

The smoke reports did not expose `company_id`, `security_id` or other internal-ID strings.

## Follow-Up Correction

After rollback, `compare_production_inventory` was corrected to treat content-identical main
database `mtime_ns` drift as metadata-only, matching the existing behavior for content-identical
WAL/SHM mtime drift. A regression test verifies that this does not mask SHA/content changes.

This correction was not used for a second production deployment attempt in Phase 13F.4.7.

## Tests

Before production:

- Compile checks for structural/deployment modules: passed.
- `git diff --check`: passed.
- Focused pre-production suite: `109 passed in 21.64s`.

After rollback and compare correction:

- Compile checks: passed.
- `tests/test_phase12d_operational_rebuild.py`, `tests/test_phase13f4_2_acceptance.py`,
  `tests/test_production_database_isolation.py`: `44 passed in 14.48s`.
- Expanded focused suite including Phase 12D comparison tests: `115 passed in 22.38s`.
- `git diff --check`: passed.

The full active repository suite was not run because production activation did not succeed; the
full-suite gate remains a post-success requirement.

## Cleanup

Removed Phase 13F.4.7-owned restore rehearsal copies:

- `restore_rehearsal/provider.restored.db`
- `restore_rehearsal/canonical.restored.db`
- `restore_rehearsal/analysis.restored.db`

Retained:

- Fresh verified Phase 13F.4.7 backup set: about 3.0 GB.
- Compact JSON evidence, snapshot smoke Markdown, acceptance contract and preflight report.

Final Phase 13F.4.7 temp root size: about 956 KB. Final free space: about 716 GB.

## Remaining Risk

The structural-regime package was not left active in production. The economic/calculation fixed
point was reached during the second pass, but the production attempt correctly failed closed on the
inventory gate and rolled back the writable set. A later production attempt must start from a clean
prompt authorization and should use the updated metadata-only mtime comparison.
