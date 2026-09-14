# Phase 13F.4 Structural Regime Production Deployment Runbook

Status: attempted on 2026-09-13 and stopped at the mandatory pre-write identity gate.

Phase 13F.4 returned `OUTCOME B - PRE-WRITE BLOCKER; PRODUCTION REMAINS UNCHANGED`.
See `docs/fundamentals_v4/fundamentals_v4_phase13f4_production_deployment.md` for the
executed record. The runbook remains the required procedure for a later deployment after a
copy-only verification proves durable structural package/dependency identity.

Phase 13F.4.1 subsequently returned `OUTCOME C - CURRENT PERSISTENCE ARCHITECTURE CANNOT
SAFELY VERSION STRUCTURAL-AWARE PACKAGES; REDESIGN REQUIRED`. Do not use this runbook for
production until a redesign has proven package-generation coexistence on copies. The next
production attempt, if later authorized, must be named Phase 13F.4.2.

Phase 13F.4.2 later superseded the immutable-coexistence requirement by accepting full coordinated
database-backup rollback as the only rollback mechanism. The first Phase 13F.4.2 production
attempt failed in an acceptance-check field lookup after package/RV refresh and restored the full
writable database set from verified backups. See
`docs/fundamentals_v4/fundamentals_v4_phase13f4_2_production_deployment.md`.

Phase 13F.4.3 corrected the Relative Valuation snapshot accessor but failed in a separate
acceptance-field mixup between structural source and structural regime fingerprints. It restored
the full writable database set from fresh backups. See
`docs/fundamentals_v4/fundamentals_v4_phase13f4_3_production_retry.md`.

Phase 13F.4.4 added a normalized acceptance contract and proved it on a real-shaped copy
candidate. The production first apply matched the accepted package and Relative Valuation
identities, but the independent second full-pipeline pass changed the structural/score package
fingerprints and failed the no-change gate. The full writable database set was restored from fresh
Phase 13F.4.4 backups. See
`docs/fundamentals_v4/fundamentals_v4_phase13f4_4_production_deployment.md`.

Phase 13F.4.5 reproduced the second-run drift on isolated copies and repaired the fixed-point
defect. The root cause was identity-resolution-path metadata (`identity_status`) participating in
structural event IDs and downstream fingerprints. Phase 13F.4.5 proved A/B/C/D fixed-point
stability and an independent replay lane. A future Phase 13F.4.6 production retry is justified only
after a separate explicit production authorization. See
`docs/fundamentals_v4/fundamentals_v4_phase13f4_5_determinism.md`.

Phase 13F.4.6 was explicitly authorized for one protected production attempt. The runner stopped
before production backups and before production writes with
`OUTCOME B - PRE-WRITE BLOCKER; PRODUCTION REMAINS UNCHANGED` because the acceptance contract
still expected the stale pre-13F.4.5 structural source fingerprint. The Phase 13F.4.5 fixed-point
lane, replay lane and Phase 13F.4.6 prewrite candidate all proved the current structural source
fingerprint is `c9fd41fdedc7b926d801bf7d56884746e552bc6593fba92c22db1e522c1a63d6`. See
`docs/fundamentals_v4/fundamentals_v4_phase13f4_6_production_deployment.md`.

Phase 13F.4.7 used the corrected acceptance expectation and crossed the production write boundary.
The first production apply activated the accepted package and Relative Valuation snapshot, and the
independent second full pass returned logical `NO_CHANGE` for provider staging, package, Relative
Position and Relative Valuation. The run nevertheless failed closed at the final inventory
no-change gate because metadata-only SQLite mtime drift was not fully normalized. The full writable
set was restored from fresh Phase 13F.4.7 backups. A follow-up comparison correction now treats
content-identical main database `mtime_ns` drift as metadata-only, matching the existing
content-identical WAL/SHM mtime handling. No second Phase 13F.4.7 production attempt was made. See
`docs/fundamentals_v4/fundamentals_v4_phase13f4_7_production_activation.md`.

Phase 13F.4.8 simplified acceptance to five blocking gates: accepted economic results, independent
logical idempotency, correct active package/dependency/RV identities, database integrity and working
Snapshot readers. Raw SQLite file SHA, file mtime, page-layout/allocation differences,
content-identical WAL/SHM timestamp drift and run-local audit timestamps are audit evidence, not
deployment blockers, when normalized logical content and active identities are unchanged. The
attempt again activated the accepted package/RV in the first pass and returned logical `NO_CHANGE`
in the second pass, but the legacy runner still failed the inventory gate before the last
physical-layout normalization was in place and restored the writable set from fresh Phase 13F.4.8
backups. A post-attempt comparator correction now treats raw database SHA, size, page count and
freelist drift as nonblocking when schema, row counts and integrity are unchanged. No second
Phase 13F.4.8 production attempt was made. See
`docs/fundamentals_v4/fundamentals_v4_phase13f4_8_simplified_activation.md`.

Phase 13F.4.9 added protected logical table-content fingerprints for every non-`sqlite_` user table
in the writable production inventory. The guard accepted simulated physical SQLite drift but
rejected same-row-count numeric, status/reason, structural, row-count, schema and integrity
mutations. The one authorized production attempt crossed the write boundary and restored from fresh
backups after the independent second pass changed protected logical content despite package/RP/RV
outcomes reporting `NO_CHANGE`. Blocking tables were canonical identity tables
(`company_cik`, `provider_company_identity`, `provider_security_identity`),
`fundamentals_economic_structural_event`, `fundamentals_result_dependency` and
`relative_position_refresh_audit`. The last table may be audit-only in a future contract, but the
identity, structural and dependency changes are protected content and cannot be normalized away. No
second Phase 13F.4.9 production attempt was made. See
`docs/fundamentals_v4/fundamentals_v4_phase13f4_9_logical_guard_activation.md`.

This runbook is intentionally non-executing documentation. It does not authorize production deployment by itself. Production activation requires a separate explicit user request and the exact gates below.

## Preconditions

- Phase 13F.3.4 report outcome is OUTCOME A.
- Full repository suite remains green.
- Current branch contains the committed Phase 13F.3.4 code and documentation changes.
- No production database writes are performed before all gates are checked.
- No network request is required for the structural-regime activation path.

## Required Inputs

- Canonical database: `data/fundamentals_v4.db`.
- Provider database: `data/fundamentals_provider.db`.
- Analysis database: `data/fundamentals_analysis.db`.
- Market database: `data/osakedata.db`.
- Taxonomy database: `data/analysis.db`.
- Report date: `2026-09-12`, unless a later production prompt explicitly replaces it.
- Expected current active package family: `OPERATING_INCOME_MODEL_FAMILY_V2`.
- Expected current active package family fingerprint: `634824f179652da81ea6f38962d9a7c87df37c0627fed089a918ce9efa83d8e9`.
- Expected current active package persistence fingerprint: `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`.
- Expected current active Relative Valuation snapshot: `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`.

## Gate 1 - Preflight

Verify:

- `git diff --check` passes.
- Production database paths are exact canonical paths, not symlinks or aliases.
- `PRAGMA quick_check` returns `ok` for all required production databases.
- `PRAGMA foreign_key_check` returns zero violations for all required production databases.
- Production inventory fingerprint is captured before any write.
- Free disk space is sufficient for backup plus rollback copies.

## Gate 2 - Expected Candidate Identity

Verify the candidate being activated matches the Phase 13F.4.5 fixed-point evidence:

- Structural package fingerprint: `748cd15828bef0bd57f75f977aadea571053940e94b38c2a221b43335e0d6c9a`.
- Event fingerprint: `085690bdb3479a88f53cac4248e0ab970a0a743934eca29d1d867a8eba57096d`.
- Current structural source fingerprint: `c9fd41fdedc7b926d801bf7d56884746e552bc6593fba92c22db1e522c1a63d6`.
- Structural regime fingerprint: `57e2827981be62c9c300ac0e0a71a26afefd04dd9b9f85670593c57ebcdff8e5`.
- Package economic result fingerprint: `1700f71e13935fccf7509cf8b9e99fb9f6705cfe9ddf5f49157b53d59a85e4d5`.
- Package physical content fingerprint: `f6144cc126d1a5c3af8735841800903e5e233a1953712ca4b5dd1ba0b67f654a`.
- Relative Valuation refreshed snapshot candidate: `1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b`.

If any fingerprint differs, stop and run a new copy-only rehearsal. Do not activate.

Additional Phase 13F.4 identity gate requirement:

- The persisted package or deterministic package dependencies must name
  `ECONOMIC_STRUCTURAL_BREAK_CONTRACT_V1`, the structural package fingerprint, the event
  fingerprint and the structural source/regime fingerprint. Formula/model identities may remain
  unchanged, but changed structural economics must not be able to masquerade as the prior
  active package under indistinguishable persisted metadata.

Additional Phase 13F.4.10 fixed-point gate requirement:

- Before any new production activation attempt, the copy-only Phase 13F.4.10 fixed-point rehearsal
  must have `OUTCOME A`, empty protected table diffs for primary cycles B/C and replay cycle B, and
  production immutability under the Phase 13F.4.9 logical-content comparator. The accepted evidence
  root is
  `temp/fundamentals_v4_phase13f4_10_fixed_point/20260914T_PHASE13F4_10_FIXED_POINT_R2`.
- The production deployment phase must include the Phase 13F.4.10 corrections: Relative Position
  identical-content no-change must not write refresh audit rows, transition identity replay must
  report real row-change semantics, provider identity links must read provider metadata from the
  active copy or production lane path, and dependency persistence must preserve existing
  `dependency_id` values for unchanged natural dependency keys.
- Phase 13F.4.10 itself does not authorize production activation. Treat the next production write
  as a separate Phase 13F.4.11 action requiring explicit user authorization, fresh verified backups
  and the full preflight/postflight gates below.
- Phase 13F.4.11 prepared the final activation path but stopped with
  `OUTCOME B - PRE-WRITE BLOCKER; PRODUCTION REMAINS UNCHANGED` because the mandatory full active
  repository suite did not return a conclusive final pytest result. Do not cross the production
  write boundary until that full-suite gate is conclusively green.
- Phase 13F.4.11.1 closed that pre-write test gate with durable evidence:
  `2961 passed, 14 deselected, 8 warnings in 795.83s (0:13:15)`. The durable log and atomic
  exit-code evidence live under
  `temp/fundamentals_v4_phase13f4_11_1_full_suite_gate/full_active_suite_after_fix`.
  This authorizes only preparation of a separately authorized Phase 13F.4.12 production activation.
- Phase 13F.4.12 was explicitly authorized for one protected production activation attempt. The
  prewrite copy candidate passed all accepted fingerprint and dependency gates, and a fresh verified
  backup set was created, but the protected apply command did not return an authoritative production
  apply result and no `first_apply`/`second_apply` artifacts were present. Production hashes and
  active package/RV pointers remained at the verified baseline, so the phase returned
  `OUTCOME B - PRE-WRITE BLOCKER; PRODUCTION REMAINS UNCHANGED`. See
  `docs/fundamentals_v4/fundamentals_v4_phase13f4_12_production_activation.md`.
- Phase 13F.4.13 diagnosed the Phase 13F.4.12 non-return as an external interrupt of a long
  uncheckpointed runner region plus missing `KeyboardInterrupt`/final-result handling. It added a
  durable stage journal, heartbeat, exit-code file, bounded restore-rehearsal validation and
  pre-write/post-write failure distinction without changing economic calculations. The one protected
  activation attempt completed with
  `OUTCOME A - STRUCTURAL-REGIME PACKAGE AND RELATIVE VALUATION ACTIVE AND STABLE IN PRODUCTION`.
  The active Relative Valuation snapshot is
  `1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b`; the package manifest and
  dependencies carry package economic fingerprint
  `1700f71e13935fccf7509cf8b9e99fb9f6705cfe9ddf5f49157b53d59a85e4d5` and content fingerprint
  `f6144cc126d1a5c3af8735841800903e5e233a1953712ca4b5dd1ba0b67f654a`. See
  `docs/fundamentals_v4/fundamentals_v4_phase13f4_13_durable_activation.md`.

## Gate 3 - Backup And Rollback

Before production writes:

- Create verified backups of all databases in the write set.
- Record size, SHA-256, schema fingerprint, row counts, `quick_check` and `foreign_key_check` for each backup.
- Confirm restore procedure can replace the exact production files and remove sidecars.
- Keep the backup root outside the active production database directory.

Rollback condition:

- Any failed write, failed validation, mismatched fingerprint, unexpected row count, unexpected active pointer state or failed postflight check requires restoring the full write set from backups.

## Gate 4 - Production Apply Order

Only after explicit authorization:

1. Apply the structural-aware operating-income v2 package refresh.
2. Verify package first apply is `APPLIED`.
3. Re-run the package apply and verify `NO_CHANGE`.
4. Verify pre-refresh Relative Valuation compatibility is incompatible for the expected structural dependency reason.
5. Invoke the separate explicit full-universe Relative Valuation refresh.
6. Verify the refreshed Relative Valuation snapshot is active and compatible.
7. Re-run Relative Valuation refresh and verify `NO_CHANGE`.
8. Generate production Snapshots for `AREB`, `IA`, `NMAD`, `NVDA`, `NXH`, `SNDK`, `VAI` and `VMRK`.

The Relative Valuation refresh must remain a separate explicit operation. Compatibility must not be restored by silently reusing or mutating the old snapshot.

## Gate 5 - Postflight

Verify:

- `quick_check=ok` for all production databases.
- `foreign_key_check=0` for all production databases.
- Exactly one active operating-income v2 package family pointer exists.
- Exactly one active Relative Valuation snapshot pointer exists.
- Package second apply remains `NO_CHANGE`.
- Relative Valuation second apply remains `NO_CHANGE`.
- Snapshot reports contain no internal IDs.
- AREB has zero post-delisting Relative Valuation rows and retains historical Relative Position rows.
- VMRK, VAI and NMAD current structural blockers are visible as structural reasons, not generic TTM failures.
- IA and NXH remain eligible under the structural contract.
- Production inventory is captured after postflight and compared to the expected write set.

## Stop Conditions

Stop without production activation if:

- Any preflight production inventory does not match the expected active identities.
- Any structural fingerprint differs from Phase 13F.3.4 evidence.
- Any copy-only replay cannot reproduce deterministic fingerprints.
- Any production guard requires a path exception.
- Any database integrity check fails.
- Any current report requires a structural review not represented in the contract.
- Relative Valuation compatibility is restored without the explicit full-universe refresh.

## Evidence To Persist

Persist the production report with:

- Exact command lines.
- Exact database paths.
- Preflight and postflight inventories.
- Backup manifest and restore instructions.
- Active package and Relative Valuation identities before and after activation.
- Structural fingerprints.
- Package and Relative Valuation first/second apply summaries.
- Snapshot paths and fingerprints.
- Production immutability comparison for all databases outside the authorized write set.
