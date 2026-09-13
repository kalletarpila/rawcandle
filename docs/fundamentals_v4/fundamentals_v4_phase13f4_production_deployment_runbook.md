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

Verify the candidate being activated matches the Phase 13F.3.4 rehearsal evidence:

- Structural package fingerprint: `4ba542c7e28c2d92ba65863f2932e2683a60b053cb4b2debe344b051a84441ad`.
- Event fingerprint: `5ec6403d231e41a52fdf04609892df1c9bdd841805180a52578b638114bf5bfd`.
- Current structural source fingerprint: `04339360f686ae6d68c6f502139a9af4cf6ebe38699c22ba30d6216a6ff06e1f`.
- Package economic result fingerprint: `55a9713c9f20d122e493bb3c0c3485bf729724ce1914703ad637d2a16346002d`.
- Package physical content fingerprint: `718e3fbe838f273775d77042fa0dbaa706c822277a3e23d5dd7eeaaa4ebb8811`.
- Relative Valuation refreshed snapshot candidate: `1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b`.

If any fingerprint differs, stop and run a new copy-only rehearsal. Do not activate.

Additional Phase 13F.4 identity gate requirement:

- The persisted package or deterministic package dependencies must name
  `ECONOMIC_STRUCTURAL_BREAK_CONTRACT_V1`, the structural package fingerprint, the event
  fingerprint and the structural source/regime fingerprint. Formula/model identities may remain
  unchanged, but changed structural economics must not be able to masquerade as the prior
  active package under indistinguishable persisted metadata.

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
8. Generate production Snapshots for `AREB`, `IA`, `NMAD`, `NVDA`, `NXH`, `VAI` and `VMRK`.

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
