# Owner-driven rehearsal storage lifecycle proposal

Proposal only, based on the 2026-11-04
[G-OPS audit](g_ops_rehearsal_cleanup_2026_11.md). No automatic deletion, global
Temp policy, production source or existing native acceptance rule was changed.

## Observed cause and cost

The two P/B harnesses copied the three Fundamentals roles, market, global
Analysis/taxonomy and queue into outer projects. `FutureOwnershipWorkflow.test()`
then copied those dependencies again into nested projects and exercised native
immutable generation/publication preparation. D1-A retains a failed source-drift
attempt, a successful attempt and an interrupted parallel setup. D1-B retains its
outer project and successful nested Test. The successful outer publications cleaned
their own three native rollback backups; nested Tests only recorded backup cleanup
eligibility. No owner snapshot-retirement inventory or retention-discharge receipt
followed the PASSED task closeouts.

This explains why publication-backup cleanup succeeded while 128,284,467,200
allocated bytes of nonempty SQLite mains persisted. The global Analysis/taxonomy
inputs are about 13.48 GB per D1 copy; duplicating them dominates storage. The
native receipt validator still reads the copied completed journal and hashes its
published roles, so deleting all files under a completed task would break a real
contract. Neither age nor a PASSED flag resolves that distinction.

## Proposed owner contract

The rehearsal owner should write a small storage manifest when allocating each
snapshot. Keep it in the approved ignored task directory and bind it to the task
ID and run ID. List exact canonical paths, device/inode, link count, logical and
allocated bytes, SQLite sidecars, source generation/input fingerprints and purpose.
Separate rebuildable scratch, original source evidence, current/previous copied
generations, native journal-owned backups and receipt-validation dependencies by
explicit role. A classification is evidence; it does not itself grant deletion.

Use four explicit lifecycle states: CREATED, OWNER_CLOSED, RETENTION_DISCHARGED
and RETIRED. CLOSED records the completed, failed or interrupted outcome and open
cases. DISCHARGED binds an exact inventory revision and explains why losing each
selected file cannot break accepted publication, native rollback/recovery,
restart safety or a promised reproducibility requirement. The existing Test and
Production receipts remain immutable and authoritative.

For each candidate, record one supported retention argument:

- An exact equivalent is retained at a verified owned durable path and all
  necessary consumers can resolve it under their existing contract.
- The owner proves no exact-byte obligation remains after the terminal operation,
  including failed/interrupted attempts, and retained reports/source vintages are
  sufficient for the explicitly promised audit/recovery level.
- A later separately reviewed contract explicitly retires an offline receipt's
  executable-validation dependency while preserving its historical seal and
  explaining its limits. Do not rewrite historical paths or pretend a hash
  reconstructs deleted observations.

Anything uncertain stays retained. Current operational Test inputs, accepted
current/previous generations, native backups pending acceptance, immutable source
evidence and open recovery artifacts are positive holds. A lightweight per-owner
hold list is preferable to a global scan that infers eligibility from directory age.
Concurrent development must be treated as real ownership; an unattended scavenger
must not race a user investigation.

## Retirement boundary for a later implementation

First extend the owning harness to emit the manifest and storage summary without
changing deletion behavior. Then add an explicit dry-run eligibility command that
resolves current/previous generations, operational Test/Production journal sources,
receipt validation dependencies, pending recovery and live configuration. Native
backup acceptance remains exclusively with its existing owner; arbitrary snapshots
must not be routed through `run_acceptance_cleanup`.

A later authorized exact-file executor may consume only the positively discharged
revision. It should read-open and hold the established relevant locks without
changing services or schedules, verify no active SQLite descriptor/mapping/writer,
check every parent against symlinks and scope, and recheck references immediately
before each unlink. Validate device/inode/link count, sizes/mtime, sidecar state and
decision identity. Prefer directory-relative exact names with guarded directory
descriptors; reject a changed path or inventory. A separate ownership protocol is
needed for harnesses that do not honor native publication locks. Holding a global
lock alone cannot prove an arbitrary copied-project writer is excluded.

Write and fsync the per-file decision before unlink, then durably record the
outcome and sync the owning directory. On a crash or ambiguous unlink, reconcile
the exact recorded identity and postconditions; never retry by filename alone.
Stop the affected pass on mismatch, an active/uncertain owner, reference drift or
failed invariants. Never recurse through directory trees. Reports, seals, original
receipts, script/test evidence and the cleanup ledger survive; empty directories
may remain. Postflight compares protected path identities/content, active/previous
and Test references, operational state and actual allocation release. Disk free
delta is supplementary because other host activity can change it.

This proposal does not discharge the present D1 files. Releasing generation or
native backup material would require the applicable owner contract and a scope
that explicitly permits those files.

## Reduce allocation before improving cleanup

Use small isolated SQLite fixtures for policy branches, sequencing, drift rejection,
idempotency and source-repair protection where equivalent assurance is demonstrable.
Keep actual native SQLite/publication/recovery integration tests for the contracts
they exercise. Tiny mocks cannot establish real WAL, crash or atomic-publication
behavior.

For the occasional authorized real-state rehearsal, pin one consistent input set
and record its owners. Investigate an immutable shared read-only snapshot for
market/taxonomy only after proving that the native paths and SQLite mode cannot
write or create sidecars there. Do not hardlink mutable databases or raw-copy an
active main file without its consistency requirements. Do not assume filesystem
reflinks, sparse files or a provider refetch are equivalent evidence. Preserve
provider-source vintages needed for accepted recovery; avoid another complete
project or Analysis copy merely as an insurance backup.

After a failed attempt, the owner should explicitly classify each partial snapshot
before retrying into another directory. A corrected attempt must not silently
orphan the earlier queue/WAL/journal. At successful closeout, report storage
disposition alongside behavioral acceptance so that copy retention is deliberate.

## Storage accounting and a bounded rollout

Record allocated bytes created, retained, eligible and actually retired per
rehearsal, with logical bytes separately. Count each device/inode once and account
for remaining hardlinks and open descriptors before claiming physical release.
Include sidecar allocation and distinguish newly allocated bytes from reused inputs.
A compact closeout table should explain each retained category and its owner/hold;
do not add permanent every-generation history.

Suggested first later implementation scope: the two P/B harnesses' storage
manifest/closeout emission and a read-only validator. Validate synthetic examples
for live Test references, current/previous generations, failed/interrupted recovery,
WAL/SHM/journal presence, symlink/hardlink/path replacement, concurrent ownership,
stale inventory, ambiguous unlink and double-counted yield. Use tiny isolated
fixtures below approved ignored Temp. Actual deletion requires a separately scoped
executor change and explicit runtime authority; no production provider workflow or
new full-sized copy is needed to develop those guards.

The first operational follow-up should settle exact D1 source/queue retention,
then review D2-A's six explicitly enumerated rehearsal/fresh-Test role files.
D2-B remains with its Fundamentals investigation owner; D2-C is held by live
Test-journal references. Host VHDX reclamation is a separate later maintenance
decision after useful ext4 allocation is actually retired.
