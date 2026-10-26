# G-OPS-06 retention hold release

**Historical hold: RELEASED. Future EC cleanup: ACTIVE, conditional on each run's
existing acceptance and recovery checks.** No production EC run was launched to
test this policy.

`temp/.ec-backup-retention-hold.json` remains present. The existing EC retention
owner now exposes `release_historical_hold`; G-OPS-06 used that checked transition
under Production/scheduler, temporary-cleanup and retention ownership. It preserved
the original hold reason/evidence, recorded `previous_state=BLOCKED_UNCERTAIN`,
and bound release to exact reconciliation and recovery artifact hashes. It was
not removed or bypassed.

Release required the unchanged G-OPS-05 matrix and operation receipts, reconciled
23-image deletion, qualified retained image, durable historical/research/control
bundle, no active recovery owner and completed publication journal. The release
receipt is `temp/g_ops_06/hold_release_qualification.json`; the resulting state is
also recorded in `hold_release_receipt.json`. A failed prerequisite preserves the
hold. The release API verifies the execution ledger, absent retired paths,
retained qualification/identity, evidence hashes and current publication state.

The 19-date discrepancies remain 15,269 semantic plus 2,033 required-lineage
mismatches. G-OPS-05 discharged the old rollback obligations through accepted
forward recovery and established source/publication vintage differences. It did
not require historical recalculation as a storage prerequisite. Release follows
those qualified obligations and the explicit G-OPS-06 authorization, rather than
assuming aligned heads alone prove historical acceptance. No arithmetic repair,
historical EC publication or calculation-definition change occurred.

## Future terminal lifecycle

| EC outcome / obligation | Existing owner behavior after release |
|---|---|
| Accepted BACKFILL_COMPLETED / REFRESH_COMPLETED | Persist immutable acceptance, verify identity/hash/integrity and closed scope; an older registered ACCEPTED point can expire. |
| Accepted EC within overall PARTIAL or FAILED | Same EC acceptance rules; unrelated scheduler status alone does not prevent release. Whole-publication recovery must still be closed. |
| Genuinely PARTIAL, FAILED, CANCELLED or missing terminal completion | Retain recovery image; never infer closure from time/process absence. |
| Interrupted copying / crashed operation | Unknown or RECOVERY_REQUIRED images remain; proven failed-copy scratch before EC writes follows existing isolated scratch cleanup. |
| Explicit backup reuse / RECOVERY_REQUIRED / RETIRE_PENDING | Preserve for owner review; replaying an old receipt cannot erase protection. |
| Unresolved publication journal | New explicit journal guard blocks terminal acceptance/pruning. |
| Active image user, changed file/hash, sidecar or unknown identity | Preserve; fail closed and report the reason. |
| Re-entry or crash during automatic retirement | RETIRED is idempotent; unresolved RETIRE_PENDING is retained for review. Historical allowlist cleanup has its own durable intent reconciliation. |
| Required general Analysis image | Explicitly excluded even if later registered as ACCEPTED. Its identity and release/bundle hashes are checked before future pruning. |

The October 24 point is adopted in place as the explicitly bound general Analysis
recovery image. It remains an unregistered legacy image as an additional existing
safeguard. A normal steady state can retain that fixed general point plus the
latest registered accepted EC pre-write point; successive accepted points replace
the earlier registered accepted point. It does not add a permanent whole image
for every accepted day. Unresolved failures may still accumulate and require
owner review; no automatic expiry is granted to them.

No new daemon, scheduled task or backup database was introduced. The existing
scheduler still invokes the same terminal owner after durable final reporting,
under its existing execution lock. No scheduler source/configuration/timing change
was needed. The owner gained guarded hold release, general-point protection,
publication-state gating and current-image open-reference protection.

## Windows coexistence

The installed `/home/kalle/scripts/rawcandle_temp_cleanup.sh` is byte-unchanged
and still matches the maintained repository script. Its entire EC source-layer
family protection includes empty destinations and sidecars; no generic EC wildcard
deletes remain. The existing task remains Ready/enabled at **21:00**, invoking
that script with `--apply`; unrelated cleanup rules are unchanged. The shared
cleanup flock excluded overlap during this one-time retirement. Future Windows
cleanup cannot delete the protected image because it excludes the whole family.

See [acceptance](g_ops_06_acceptance_evidence.md) and
[remaining owner limitations](operational_maintenance_backlog.md).
