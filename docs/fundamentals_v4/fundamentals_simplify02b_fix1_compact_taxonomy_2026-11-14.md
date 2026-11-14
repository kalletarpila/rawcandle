# SIMPLIFY-02B FIX1 — compact disposable taxonomy source

Starting accepted HEAD: `64c61771bee96261635779bac6074b373c8d6dee`.
Scope is disposable qualification only. No live reconciliation, acquisition,
financial publication, scheduler change, storage cleanup or database optimization.
The pre-existing journal modification and unrelated untracked files are excluded
from this change and commit.

## Earlier implementation and full-copy cause

Bounded investigation covered the named source-bundle, Snapshot environment,
Refresh copy, taxonomy acceptance and reconciliation paths, their direct readers
and tests, the source-bundle study/foundation/migration documents, and the
source-bundle history (`e4b3d344`, `d162bd67`, `cfb27f44`, `6ebe7d6c`).
No existing taxonomy-only extractor was found in that scope. This is not a claim
that every historical branch or untracked experiment was searched.

The earlier implemented compact bundle is for **market** data. The Phase
13G.3.25 foundation report explicitly states that no taxonomy SQLite file is
produced. The later Refresh and Add Tickers migrations replaced taxonomy backup
with protected direct reads; they did not introduce a subset producer. There is
no evidence of a taxonomy-only implementation deliberately retired by those
changes. Existing taxonomy `_copy_sqlite` helpers still perform complete backups.

The exact unnecessary copy is in the ignored SIMPLIFY-02B qualification wrapper,
`temp/fundamentals_simplify02b/exercise.py`:

```python
base['taxonomy_isolation'] = online_backup(lp.taxonomy_db, data / 'analysis.db')
```

That conservative fallback made the source local to the owned-copy root, whose
native environment rejects references outside its ownership boundary. Isolation
requires an independent taxonomy file, but does not require unrelated research
tables. Native semantic binding, WAL protection and financial rollback do not
require a full research database. The previous wrapper remains historical
evidence; it is not a tracked runtime integration and was not overwritten.

## Minimal correction and exact closure

`source_bundle.prepare_disposable_taxonomy_source` extracts the fixed taxonomy
closure directly from the source. `SnapshotEnvironment.prepare_taxonomy_from`
provides an owned-copy entry using the native destination path and ownership
checks. The new qualification uses that entry instead of full `online_backup`.
No new mode registry, copy framework, financial role or rollback path was added.

Reused protection and validation: `protected_direct_taxonomy_source`,
`_checkpointed_taxonomy_read`, `_readonly`, native `taxonomy._active_state`, and
`load_active_dc_memberships`. Existing reconciliation preparation, exact candidate
confirmation, publication journal, postflight and retained-A rollback are reused
without changes.

The necessary tables are `ec_ecosystem`, `ec_taxonomy_version`, `ec_entity`,
`ec_membership` and optional `ec_entity_alias`. The optional alias dependency was
missing from the descriptive closure registry and is now recorded there.
`taxonomy._ec_identity_index` reads aliases when present. The V2 peer reader and
snapshot membership reader query all active ecosystems, so extraction retains
the complete contents of these small tables, including inactive versions and
historical memberships. Copying only active DC memberships would be incomplete.

Source schema, constraints, explicit indexes, integer identities, all columns,
rows, `user_version` and `application_id` are preserved. Autoindexes follow the
original CREATE TABLE constraints. Source triggers are not needed for these
read-only consumers. External foreign keys and generated/hidden columns stop
preparation for an explicit closure review. No unrelated research tables or
financial result tables are included.

Native taxonomy writer protection and checkpointed SQLite exclusion cover a
pinned read transaction for schema/row extraction. Every selected row is compared
to the destination; quick_check and foreign_key_check must pass. Full native DC
state (including aliases/version inventory) and canonical ticker/company mapping
must match. Native physical drift checks run before exposing the destination.
A temporary file and exclusive link prevent partial or overwritten destinations;
failed preparation removes its own temporary file. No full-size intermediate,
VACUUM, live checkpoint, sidecar deletion or source DML is performed.

The normal live protected-direct source remains unchanged. Financial publication
roles remain provider/canonical/analysis. The compact taxonomy is an isolated
read-only dependency and is never a financial rollback role.

## Focused regression evidence

The focused run contains **58 PASS**, zero failures/errors/skips, 33.44 seconds:
`test_fundamentals_compact_taxonomy.py`,
`test_fundamentals_admin_source_bundle.py` and
`test_fundamentals_taxonomy_sidecars.py`. The final negative source-type test was
changed to use an isolated native fixture instead of reading local production
metadata; that replacement passed separately (1 PASS, 8.91 seconds).

Coverage includes full table/index/version/alias parity, unrelated-table exclusion,
DC semantic and ticker/company mapping parity, peer and snapshot classifications,
multiple ecosystems and historical versions, query-only consumption, empty WAL
and normal SHM, unsafe/ambiguous sidecars, physical drift rejection with no exposed
partial copy, and native candidate publication/postflight/recovery with unchanged
OLD role hashes. Existing exact financial acceptance rules are unchanged. Socket
guards recorded zero connection attempts. No full suite or unrelated suite ran.

Ignored evidence is retained under `temp/fundamentals_simplify02b_fix1/`;
`regression.xml`, `source_guard.xml`, logs and database files are not committed.

## Actual-source disposable qualification

Verdict: **COMPACT_TAXONOMY_DISPOSABLE_PASSED**. One new owned environment used
current production OLD financial contents, a logical review-queue copy, native
compact market staging, and the new owned-copy taxonomy entry. It did not copy
the prior qualification's full taxonomy database, nor read it as an intermediate.

Native reconciliation operation:
`20261114T134436Z_refresh_fundamentals_cce2b9c73301_universe_reconciliation_848806d6`.
One B was prepared, exactly confirmed in copy scope, activated and postflight
passed (`COMPLETED / PASSED`). Native journal recovery returned `RECOVERED` and
restored A `current_rebuild_2a684ef130c6a540de4adc560ab171ad`. All three retained
A role hashes remained identical to production OLD. No extra OLD rollback role
copies were created. The accepted SIMPLIFY-02 pointer/retained-generation engine
performed recovery; taxonomy did not enter its role set. Candidate B and its
staged market source were cleaned by existing native recovery, not by a new
storage cleanup operation.

Source/copy version is `DC_TAXONOMY_FULL_V2_1`, with 350 active DC memberships.
The semantic fingerprint matches production and the previous qualification:
`801698f6b352c445cc8e6f5fd51a1cac2779d11f6ce72a1c10bf71bb8aae4559`.
Native source-state fingerprint:
`39e89421ca228c87767cac3f159623822698049e0693a474f41095b394785522`.

| Copied table | Actual rows |
|---|---:|
| ec_ecosystem | 1 |
| ec_taxonomy_version | 3 |
| ec_entity | 335 |
| ec_membership | 1,188 |
| ec_entity_alias | 1 |

| Measurement | Actual result |
|---|---:|
| Previous full taxonomy copy | 14,471,372,800 bytes |
| Compact taxonomy copy | 290,816 bytes |
| Avoided taxonomy-copy bytes | 14,471,081,984 bytes |
| Taxonomy-copy reduction | 99.9979904% |
| Compact preparation, including native validation | 21.168692 seconds |
| Whole new isolation preparation | 102.456254 seconds |
| New prepare/publish/postflight | 150.943441 seconds |
| Previous whole isolation preparation | 90.273455 seconds |
| Previous prepare/publish/postflight | 151.144046 seconds |
| New retained task tree after completion | 3,586,765,761 logical bytes |
| New retained allocated disk blocks | 3,587,411,968 bytes |
| Sample with B still present | 6,232,618,504 logical bytes |
| Previous retained qualification tree | 18,016,576,586 logical bytes |
| Free disk after completion | 526,080,987,136 bytes |

There is a measured storage reduction, not a demonstrated end-to-end speedup.
The earlier backup's isolated preparation duration was not recorded, so no
like-for-like source-copy time claim is made. Timings include native checks and
different local cache/load conditions. Disk numbers include this task's tests,
logs and evidence. The B sample is an observed point, not a continuous peak;
short-lived SQLite journal maxima were not measured. A separate sample while B
existed measured 6,233,194,496 allocated bytes. Initial capacity exceeded the
native bounded isolation requirement; no low-space condition occurred.

No new full taxonomy copy remains. The earlier task's 14.47 GB taxonomy copy and
other historical/recovery artifacts remain untouched. This task retains three
necessary isolated OLD financial files (2,630,053,888 bytes), the review queue
(882,114,560 bytes), compact market inputs, the tiny taxonomy and audit evidence.
The largest remaining consumers are the OLD provider/analysis/canonical files and
review queue, not taxonomy. Later operator-reviewed retirement of disposable
qualification artifacts could reclaim space; no deduplication, queue redesign,
retention change, compaction, VACUUM or other optimization was implemented.

## Production preservation and use

The wrapper compared before/after size/inode/mtime for the production financial
roles, taxonomy, market database, review queue, active manifest, journal and
scheduler configuration. It also compared control-file hashes. All matched.
The taxonomy extraction additionally passed its native main/sidecar drift checks.
There was no production database DML, sidecar manipulation, live UPDATE/FETCH,
review write, active-generation change or financial watermark change. Watermark
remains `2026-10-28`; the production installed universe remains
`3b8121b74c852f08575fa1e2b70004e6`. Socket attempts and Sharadar/SEC HTTP calls: 0.
Fundamentals HOLD remains true. Normal scheduler configuration is untouched:
the coordination guard used the requested 04:45 Helsinki boundary; the existing
configuration's run_time is 04:30 Helsinki, as before this task. This discrepancy
was not changed by a storage-source fix; daytime execution finished well before
both boundaries and acquired native leases without conflict.

For future owned-copy qualification, after ordinary owner/OLD preparation, use:

```python
copy = SnapshotEnvironment(copy_owner=owner)
taxonomy_evidence = copy.prepare_taxonomy_from(SnapshotEnvironment())
```

This entry acquires native source protection itself; call it outside an already
held taxonomy lock. Existing destination files are refused. Normal live Refresh
continues using protected direct taxonomy; no global caller migration occurred.
The qualification does not authorize any production activation. No implementation
blocker remains within FIX1 scope. Only task-owned source, tests and this report
are committed; no push is performed.
