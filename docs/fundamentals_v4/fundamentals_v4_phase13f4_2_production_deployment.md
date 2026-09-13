# Phase 13F.4.2 Structural-Regime Production Deployment

Outcome: `OUTCOME C - DEPLOYMENT FAILED AND COMPLETE BACKUP SET RESTORED SUCCESSFULLY`.

Date: 2026-09-13.

## Authorization

Phase 13F.4.2 explicitly accepted the current mutable Operating-Income V2 persistence model and
authorized production writes after pre-write gates, protected by complete coordinated backups of
the writable production database set.

The immutable old/new package coexistence redesign remains deferred. Old package manifests are
audit records only; pointer-only rollback is not valid after shared economic rows have been
replaced.

## Writable Set

The executed write set was:

- `data/fundamentals_provider.db`
- `data/fundamentals_v4.db`
- `data/fundamentals_analysis.db`

Read-only sources remained:

- `data/osakedata.db`
- `data/analysis.db`

No network request, scheduler change, UI change, automatic Relative Valuation scheduling,
formula change, V3 work, historical fact deletion, production report overwrite or push was
performed.

## Source And Preflight

- Source commit for the production attempt: `a825dd975fb65bd112eb2694c2358e3411caa23a`.
- Branch: `chore/ignore-backups`.
- Required commits present: `0804609`, `34be0c6`, `a01fc83`.
- Source archive SHA-256 verified:
  `dc9d3f729830c1881873d10dec2dc2a3e7035d2a247e1737983bdb64cd0e0d36`.
- Accepted source observations: ARQ 199, MRQ 202, total 401.
- Conflicting writer processes: none.
- Required free-space estimate: 11,508,113,408 bytes.

## Backups And Restore Rehearsal

Verified backups were created under:

`backups/fundamentals_v4_phase13f4_2_structural_production/20260913T_PHASE13F4_2_PRODUCTION_APPLY`

Backup SHA-256 values:

| Role | SHA-256 |
| --- | --- |
| provider | `7957c44632ff98eda87b12014152eb26b9fd3d445c5d8d2510b7b0f9eca03e11` |
| canonical | `554aaa3c8fc359b08ed0c9171f62e08e2cd59c3be2bfed1fa6ff09713275e736` |
| analysis | `a46ab948a9b6b3d12078b7f09158ccde603d28ab649e6bd9015273aa3e54e8d2` |

The restore rehearsal opened the backup set independently and reconciled schema, row counts,
`quick_check` and foreign keys before production writes.

## Apply Progress Before Failure

The production apply reached the structural-aware package and Relative Valuation refresh.

Package evidence:

- package first apply: `APPLIED`
- package second apply: `NO_CHANGE`
- package economic result fingerprint:
  `55a9713c9f20d122e493bb3c0c3485bf729724ce1914703ad637d2a16346002d`
- package physical content fingerprint:
  `718e3fbe838f273775d77042fa0dbaa706c822277a3e23d5dd7eeaaa4ebb8811`
- Score rows: 87,525
- Score component rows: 612,675
- Lifecycle rows: 87,525
- Valuation rows: 87,525
- Delta rows: 87,525
- Delta component rows: 612,675
- Diagnostic endpoints: 87,525
- Diagnostic evaluations: 700,200
- Relative Position coverage rows: 19,620
- Relative Position result rows: 13,755

Relative Valuation evidence before rollback:

- first apply: `ACTIVATED`
- refreshed snapshot:
  `1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b`
- result fingerprint:
  `9c642e80b06fdbb8c6e703a46a6bda2c7031bc270fbd195b0a3acd7cdeba30f3`
- second apply: `NO_CHANGE`
- companies: 2,435
- components: 7,305
- Own-History rows: 2,435
- peer rows: 9,740

## Failure

The deployment failed in the Phase 13F.4.2 acceptance checker, not in the economic calculation.
The checker attempted to read `relative_valuation.snapshot.snapshot_id`, but the persisted
Relative Valuation apply report stores the identifier under
`relative_valuation.first_apply.snapshot_id`.

Failure:

`KeyError: 'snapshot_id'`

Because production writes had already occurred, the deployment stopped and restored the complete
write set from the verified pre-write backups. No second production deployment attempt was made in
this run.

## Restoration

Restored roles:

- provider
- canonical
- analysis

Post-rollback verification showed:

- active package restored to
  `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`;
- active Relative Valuation snapshot restored to
  `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`;
- provider, canonical and analysis `quick_check=ok`;
- provider, canonical and analysis foreign-key violations: 0;
- existing production report fingerprint unchanged.

The restored writable database SHA-256 values equal the verified backup SHA-256 values listed
above. Market and taxonomy remained read-only; taxonomy has pre-existing WAL/SHM sidecars and was
not part of the write set.

## Follow-Up Correction

The acceptance-check bug was corrected after the rollback by reading the RV snapshot identifier
from `relative_valuation.first_apply.snapshot_id`.

This correction prepares a later separately authorized Phase 13F.4.2 retry. It does not constitute
a second production deployment attempt.

## Evidence

Primary artifact directory:

`temp/fundamentals_v4_phase13f4_2_structural_production/20260913T_PHASE13F4_2_PRODUCTION_APPLY`

Post-rollback verification directory:

`temp/fundamentals_v4_phase13f4_2_structural_production/20260913T_PHASE13F4_2_POST_ROLLBACK_VERIFY`

Retained large files:

- verified production backup set;
- restore rehearsal copies under the failed run artifact directory.

Cleanup was intentionally conservative after Outcome C so recovery evidence remains available.
