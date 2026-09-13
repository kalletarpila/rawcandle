# Phase 13F.4.6 Structural-Regime Production Deployment

Status: `OUTCOME B - PRE-WRITE BLOCKER; PRODUCTION REMAINS UNCHANGED`.

Phase 13F.4.6 was run on 2026-09-13 as the single protected production deployment attempt
authorized for this phase. The runner stopped before production backups and before production
writes because the normalized acceptance contract still expected the stale structural source
fingerprint from the pre-13F.4.5 fixed-point repair.

## Executed Paths

- Artifact root: `temp/fundamentals_v4_phase13f4_6_structural_production/20260913T_PHASE13F4_6_PRODUCTION_DEPLOYMENT`
- Result file: `phase13f4_6_result.json`
- Backup root: `backups/fundamentals_v4_phase13f4_6_structural_production`
- Backup files created: none

Production database paths verified before the attempt:

- Provider: `data/fundamentals_provider.db`
- Canonical: `data/fundamentals_v4.db`
- Analysis: `data/fundamentals_analysis.db`
- Market: `data/osakedata.db`
- Taxonomy: `data/analysis.db`

## Pre-Write Gates

- `git status --short`: clean before the apply attempt.
- Disk space: 681 GB free under `/home/kalle/projects/rawcandle`.
- Lock: `temp/.fundamentals_phase9e.lock` was available.
- `PRAGMA quick_check`: `ok` for provider, canonical and analysis.
- `PRAGMA foreign_key_check`: zero rows for provider, canonical and analysis.
- Conflicting production writers: none found by the runner preflight.
- Focused tests before apply: `108 passed in 22.35s`.
- Compile gate: passed.
- `git diff --check`: passed.

Baseline SHA-256 values matched the prompt before the attempt and again after the pre-write stop:

- Provider: `7957c44632ff98eda87b12014152eb26b9fd3d445c5d8d2510b7b0f9eca03e11`
- Canonical: `554aaa3c8fc359b08ed0c9171f62e08e2cd59c3be2bfed1fa6ff09713275e736`
- Analysis: `a46ab948a9b6b3d12078b7f09158ccde603d28ab649e6bd9015273aa3e54e8d2`
- Market: `f550db289b2ce53d76ab6503e85dc04e5bf6232606ca2922cc69efdef1ed094f`
- Taxonomy: `c99db877cabe7ea9e97207689d1ccddb6409284dab9c5ad4067b247996f240da`

## Blocker

The apply result was:

`OUTCOME B - PRE-WRITE BLOCKER; PRODUCTION REMAINS UNCHANGED`

Reason:

`PREWRITE_ACCEPTANCE_BLOCKERS:STRUCTURAL_SOURCE_FINGERPRINT`

The prewrite candidate itself reproduced the Phase 13F.4.5 fixed-point evidence:

- Package first apply: `APPLIED`
- Package second apply: `NO_CHANGE`
- Package economic fingerprint: `1700f71e13935fccf7509cf8b9e99fb9f6705cfe9ddf5f49157b53d59a85e4d5`
- Package physical fingerprint: `f6144cc126d1a5c3af8735841800903e5e233a1953712ca4b5dd1ba0b67f654a`
- Structural event fingerprint: `085690bdb3479a88f53cac4248e0ab970a0a743934eca29d1d867a8eba57096d`
- Structural regime fingerprint: `57e2827981be62c9c300ac0e0a71a26afefd04dd9b9f85670593c57ebcdff8e5`
- Structural package fingerprint: `748cd15828bef0bd57f75f977aadea571053940e94b38c2a221b43335e0d6c9a`
- Relative Valuation first apply: `ACTIVATED`
- Relative Valuation second apply: `NO_CHANGE`
- Relative Valuation snapshot: `1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b`
- Relative Valuation result fingerprint: `9c642e80b06fdbb8c6e703a46a6bda2c7031bc270fbd195b0a3acd7cdeba30f3`
- Relative Valuation source fingerprint: `af0e480b64d57bfc8f65fe2ddf9777cfdf5d7b8afbb801bcf95aaea44ebc61ee`
- AREB post-delisting Relative Valuation rows: `0`

The stale acceptance value was:

`04339360f686ae6d68c6f502139a9af4cf6ebe38699c22ba30d6216a6ff06e1f`

The retained Phase 13F.4.5 fixed-point lane, the Phase 13F.4.5 replay lane and the Phase 13F.4.6
prewrite candidate all report the structural source fingerprint as:

`c9fd41fdedc7b926d801bf7d56884746e552bc6593fba92c22db1e522c1a63d6`

This is a stale acceptance expectation, not a reader defect and not a production-data change.
The acceptance constant was updated to the Phase 13F.4.5 fixed-point value after the attempt.
No second production deployment attempt was made in this phase.

## Production State After Stop

Production remained on the pre-attempt active identities:

- Active OI package persistence fingerprint:
  `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- Active OI package economic fingerprint:
  `7448d7b9212ce4645cf000d6264d824f3f488cdf5d7fce3ba7f6df839c3b8e78`
- Active OI package physical fingerprint:
  `369793b4036a1e407f9721ed6a3f5f455ffc3b7e9500c8ba00ecae92b49ab31d`
- Active Relative Valuation snapshot:
  `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`
- Active Relative Valuation result fingerprint:
  `7a207058792a8e35da35d7a4d4ab384b6621a9ca0ad2ada12f4c883ead652315`

No rollback was required because the stop occurred before production backups and before production
writes. No Phase 13F.4.6 temp database copies remained after runner cleanup.
