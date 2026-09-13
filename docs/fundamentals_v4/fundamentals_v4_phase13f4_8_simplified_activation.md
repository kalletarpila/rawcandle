# Phase 13F.4.8 Simplified Structural-Regime Production Activation

Status: `OUTCOME C - BLOCKING DEPLOYMENT FAILURE; COMPLETE BACKUP SET RESTORED`.

Phase 13F.4.8 attempted one protected production activation on 2026-09-13 using the simplified
five-gate acceptance policy requested for this phase. The run crossed the production write
boundary, created fresh verified backups, activated the accepted candidate in the first pass, and
proved logical no-change in the independent second pass. The established runner still failed the
final inventory gate, so it restored the complete writable database set from the fresh Phase 13F.4.8
backups. No second production write attempt was made.

## Pre-Write Corrections

Commit `966efb1` prepared the simplified acceptance path before production writes:

- phase-specific outcome labels were parameterized for the shared Phase 13F.4 runner;
- inventory comparator tests were expanded for active package/RV identity and dependency changes;
- comparator behavior already accepted content-identical database and sidecar mtime drift from
  Phase 13F.4.7.

After the failed attempt, the comparator was further corrected so raw SQLite file SHA, file size,
page count and freelist differences are nonblocking when schema fingerprint, row counts and
integrity checks are unchanged. Scheduler `mtime_ns` is also normalized when scheduler content is
unchanged. Regression tests verify that schema, row-count, integrity, active identity and dependency
changes still fail.

This post-attempt correction was not used for a second production write attempt in Phase 13F.4.8.

## Baseline

Before the attempt:

- Worktree was clean at `966efb1`.
- Lock `temp/.fundamentals_phase9e.lock` was available.
- No conflicting writer process was active.
- Free space was about 716 GB; runner peak-space estimate was about 11.5 GB.
- Writable set: provider, canonical, analysis.
- Read-only roles: market, taxonomy.
- Provider, canonical, analysis, market and taxonomy passed `quick_check`.

Expected restored economic baseline was present:

- Active OI package persistence fingerprint:
  `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- Active OI economic fingerprint:
  `7448d7b9212ce4645cf000d6264d824f3f488cdf5d7fce3ba7f6df839c3b8e78`
- Active OI physical/content fingerprint:
  `369793b4036a1e407f9721ed6a3f5f455ffc3b7e9500c8ba00ecae92b49ab31d`
- Active RV snapshot:
  `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`
- Active RV result fingerprint:
  `7a207058792a8e35da35d7a4d4ab384b6621a9ca0ad2ada12f4c883ead652315`

Taxonomy remained in the checkpointed physical state first observed after Phase 13F.4.7:

- Taxonomy main-file SHA: `244d152094f8577d9673b93b1b321ca2975dc94b5cd0475512f8fd12c9a08943`
- Taxonomy WAL: present, size `0`
- Taxonomy SHM: present, size `32768`

## Accepted Candidate

The Phase 13F.4.5 fixed-point candidate was used:

- Structural source fingerprint: `c9fd41fdedc7b926d801bf7d56884746e552bc6593fba92c22db1e522c1a63d6`
- Structural event fingerprint: `085690bdb3479a88f53cac4248e0ab970a0a743934eca29d1d867a8eba57096d`
- Structural regime fingerprint: `57e2827981be62c9c300ac0e0a71a26afefd04dd9b9f85670593c57ebcdff8e5`
- Structural package fingerprint: `748cd15828bef0bd57f75f977aadea571053940e94b38c2a221b43335e0d6c9a`
- Package economic fingerprint: `1700f71e13935fccf7509cf8b9e99fb9f6705cfe9ddf5f49157b53d59a85e4d5`
- Package persisted-content fingerprint: `f6144cc126d1a5c3af8735841800903e5e233a1953712ca4b5dd1ba0b67f654a`
- RV snapshot: `1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b`
- RV result fingerprint: `9c642e80b06fdbb8c6e703a46a6bda2c7031bc270fbd195b0a3acd7cdeba30f3`
- RV source fingerprint: `af0e480b64d57bfc8f65fe2ddf9777cfdf5d7b8afbb801bcf95aaea44ebc61ee`

## Production Attempt

The prewrite candidate passed acceptance and matched the accepted candidate.

First production pass:

- Package first apply: `APPLIED`
- Package logical writes: `2396550`
- Package inner second apply: `NO_CHANGE`, logical writes `0`
- RV first apply: `ACTIVATED`
- RV second apply: `NO_CHANGE`
- RV snapshot activated: `1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b`

Independent second full pass:

- Provider staging changes: `0`
- Package first apply: `NO_CHANGE`
- Package logical writes: `0`
- Package inner second apply: `NO_CHANGE`
- Relative Position: `NO_CHANGE`
- Relative Valuation: `NO_CHANGE`
- RV second apply: `NO_CHANGE`

Blocking runner failure:

`PHASE13F4_2_SECOND_RUN_NOT_NO_CHANGE`

The failure payload still showed all economic/logical gates at no-change:

- `provider_replay_changes`: `0`
- `package_outcome`: `NO_CHANGE`
- `package_second_apply_outcome`: `NO_CHANGE`
- `relative_position_outcome`: `NO_CHANGE`
- `relative_valuation_outcome`: `NO_CHANGE`
- `relative_valuation_second_outcome`: `NO_CHANGE`

The runner’s remaining blocker was `inventory_normalized_no_change=false`. It listed taxonomy SHM
mtime drift as content-identical metadata, but the normalized inventory fingerprint still differed.
The post-attempt comparator correction addresses the remaining physical SQLite layout fields as
nonblocking when logical content is unchanged.

## Rollback Verification

The fresh backup set is retained at:

`backups/fundamentals_v4_phase13f4_8_structural_production/20260913T_PHASE13F4_8_PRODUCTION_ACTIVATION`

Retained backup files:

- `fundamentals_provider.db`
- `fundamentals_v4.db`
- `fundamentals_analysis.db`
- `backup_manifest.json`

The runner restored the complete writable database set with no restore error.

Restored writable database hashes:

- Provider: `7957c44632ff98eda87b12014152eb26b9fd3d445c5d8d2510b7b0f9eca03e11`
- Canonical: `554aaa3c8fc359b08ed0c9171f62e08e2cd59c3be2bfed1fa6ff09713275e736`
- Analysis: `a46ab948a9b6b3d12078b7f09158ccde603d28ab649e6bd9015273aa3e54e8d2`

Post-restore active production identities reverted to baseline:

- Active OI package: `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- Active RV snapshot: `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`

Post-restore integrity:

- Provider quick_check: `ok`
- Canonical quick_check: `ok`
- Analysis quick_check: `ok`
- Taxonomy quick_check: `ok`

## Snapshot Smoke

First-pass and second-pass smoke reports were generated for all required tickers:

- `VMRK`: Relative Position available; Relative Valuation unavailable for the report date.
- `IA`: Relative Position available; RV available on snapshot `2026-09-12`.
- `VAI`: Relative Position available; Relative Valuation unavailable for the report date.
- `NXH`: Relative Position available; RV available on snapshot `2026-09-12`.
- `NMAD`: Relative Position available; Relative Valuation unavailable for the report date.
- `AREB`: Relative Position available; Relative Valuation unavailable for the report date.
- `NVDA`: Relative Position available; RV available on snapshot `2026-09-12`.
- `SNDK`: Relative Position available; RV available on snapshot `2026-09-12`.

No `company_id`, `security_id`, `provider_identity` or `internal` strings were found in the
generated smoke reports.

## Tests

Pre-write correction tests:

- Compile checks: passed.
- Comparator, acceptance and production-isolation tests: `47 passed in 15.98s`.

Before production:

- Compile checks: passed.
- Focused pre-production suite: `118 passed in 22.38s`.
- `git diff --check`: passed.

After rollback and the additional simplified-comparator correction:

- Compile checks: passed.
- Comparator, acceptance and production-isolation tests: `48 passed in 14.79s`.
- Expanded focused suite: `119 passed in 23.31s`.
- `git diff --check`: passed.

The full active repository suite was not run because production activation did not succeed; the
full-suite requirement remains a post-success gate.

## Cleanup

Removed Phase 13F.4.8-owned restore rehearsal database copies:

- `restore_rehearsal/provider.restored.db`
- `restore_rehearsal/canonical.restored.db`
- `restore_rehearsal/analysis.restored.db`

Retained compact JSON/Markdown evidence under the Phase 13F.4.8 temp root and retained the fresh
verified backup set. Final Phase 13F.4.8 temp root size is about 952 KB. Backup root size is about
3.0 GB. Final free space is about 713 GB.

## Remaining Risk

The structural-regime package is not active in production after this phase. The economic and
logical pipeline reached the expected fixed point in the failed attempt, but the established runner
rolled back because its inventory gate had not yet fully implemented the simplified physical-drift
policy. A later production attempt needs fresh explicit authorization and should start from the
post-attempt comparator correction.
