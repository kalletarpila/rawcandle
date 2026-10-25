# G-OPS-04 EC backup retention policy

**Current release state: BLOCKED.** A durable scope-specific hold at
`temp/.ec-backup-retention-hold.json` preserves all historical and future images
for the current DATACENTER/V2_1 scope. Nineteen historical dates have substantive
semantic/required-lineage parity failures. Latest-head or six-date success cannot
release this hold; separate owner qualification is required. The lifecycle below
is implemented and tested, but pruning remains held for this scope.

Scope: ordinary RawCandle EC backfill/refresh pre-write images. This is an
operation rollback lifecycle, not an archive of historical whole Analysis states.
The latest accepted operation keeps its pre-write image. An earlier **accepted**
operation in the same database/ecosystem/taxonomy scope expires when another
operation has passed all EC acceptance gates and persisted its terminal report.
No keep-three or age threshold governs these images.

`rawcandle/ec_backup_retention.py` owns only exact identity-bound EC images.
`_create_backup()` in both existing CLIs still uses SQLite's online backup API;
it now reserves its filename exclusively and registers the image as
RECOVERY_REQUIRED. A same-second collision fails before EC writes instead of
overwriting an existing image. Successful registration binds device/inode,
link count, ownership, type, timestamps, allocated bytes, SHA-256 and source scope
in an adjacent `.ec-owner.json` receipt. Receipts stay in ignored runtime storage.

The existing scheduler calls `terminal_retention()` after writing its final
summary and status, while its execution lock remains held. Acceptance requires
EC COMPLETED, bridge OK, no retry, accepted coverage/parity, zero mismatches,
four canonical watermark rows and a terminal timestamp. The new retained image
must match its registered bytes/identity and pass SQLite quick_check. Only prior
ACCEPTED receipts in that exact scope, with unchanged terminal summary/hash and
older completion clocks, can retire. Explicit backup reuse reopens its recovery
obligation before any EC writes; replaying its old summary cannot release it.

There is no later EC acceptance phase after the bridge in this source scheduler.
Fundamentals runs afterward under its own publication/generation recovery
contract; its failure does not invalidate accepted EC facts. Overall scheduler
PARTIAL/FAILED is therefore evaluated using the EC outcome. EC partial writes
currently return BACKFILL_FAILED: they remain recovery-required even if some
individual dates committed. No invented PARTIAL acceptance flag is introduced.

| Outcome | Image handling |
|---|---|
| Accepted COMPLETE EC | Keep current pre-write point; release earlier accepted points in the same scope |
| PARTIAL overall scheduler, complete accepted EC | Same EC policy; independent failed scope retains its own recovery |
| EC partial writes / FAILED / CANCELLED | Keep image; never infer forward repair or release from age |
| Interrupted / stale / unknown ownership | Keep image, even when the process is dead |
| Explicit existing-backup reuse | Mark RECOVERY_REQUIRED before writes; require a fresh owner review |
| Failed backup copy before any EC writes | Close connections; retain compact diagnostics; remove only the exact exclusively created scratch file if identity, sidecars and open-reference checks permit |
| Crash during unlink/receipt transition | RETIRE_PENDING remains an explicit review obligation; never infer completion |
| Unlink failure | Retain image/receipt, report hold, allow idempotent retry |

Before unlink, reject symlinks, hard links, unexpected owners/devices, mounted or
aliased paths, changed content/identity, any SQLite sidecar and open file references.
An exclusive stable flock serializes retention/reuse. An ownership/content error
stops that pruning pass. Manifests and terminal reports remain after retirement;
no SQLite images or runtime receipts enter Git. Maintenance report failure does
not rewrite an already committed scheduler outcome.

Direct standalone backfills and taxonomy/recovery operations keep their registered
images until their own acceptance is qualified. They are not silently interpreted
as ordinary accepted scheduler runs. Historical unregistered images cannot be
swept by the new function; G-OPS-04 qualifies them separately. Once the explicit historical hold is resolved, normal accepted
scheduled runs retain one rolling full image, plus any explicitly unresolved
failed/reused/manual recovery points. Failed runs are not forcibly bounded by age.

The maintained `scripts/rawcandle_temp_cleanup.sh` is installed at the existing
`/home/kalle/scripts/rawcandle_temp_cleanup.sh`. Its refresh keep-three branch is
removed; every EC backfill/refresh filename (including empty interrupted copies
and sidecars) is protected from its other rules. Existing smoke/before/empty
policies otherwise remain unchanged. The Windows task still runs at 21:00;
no new scheduler or daemon exists. Source 04:30 and forecast 14:00 are unchanged.

The release policy ends old operation-specific full-image rollback, not an
independent migration or historical-data obligation. Named weighting migration
backups, Fundamentals generations, forecast backups and non-EC files are outside
this policy. See [inventory](g_ops_04_ec_backup_inventory.md),
[execution](g_ops_04_cleanup_execution.md) and
[acceptance](g_ops_04_acceptance_evidence.md).
