# G-OPS-06 recovery and preservation

**PASS.** The sole retained full image is the general RawCandle Analysis recovery
point, including DC, EC and non-EC data, rather than a permanently required old
EC projection.

Path:
`/home/kalle/projects/rawcandle/temp/analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261016_20261023__20261024T042011Z.sqlite`

Allocated bytes: **13,213,745,152**. SHA-256:
`97625bb78f207dc10394a80f65498e612dbecbe1a4c3dd57ea22c211ba82447e`.
Fresh full SHA-256, SQLite `quick_check=ok`, unchanged complete file identity and
exact compatible live schema passed. The G-OPS-05 all-50-table census, complete
non-EC comparison and bounded application restore remain hash-qualified. No
additional full-sized restore or permanent Analysis backup was created.

## Recovery contract and procedure

The image binds to operational `data/analysis.db`; it does not replace canonical
Source, market/provider, Fundamentals-generation Analysis or forecast recovery.
The current Fundamentals journal is COMPLETED, postflight PASSED, recovery
NOT_REQUIRED; its generation Analysis role is a different database. All creating
operations are terminal or explicitly forward-resolved; no active rollback plan
requires one of the 23 deleted vintages.

For an actual Analysis recovery, the owning incident procedure must acquire the
normal Production/scheduler and relevant publication ownership, establish the
intended recovery vintage and preserve any later accepted state. Validate this
image identity/hash and the bundle before restoring into an isolated target via
SQLite backup/copy, then run integrity/schema/foreign-key checks. Qualify its
source/taxonomy bindings and EC watermarks before any controlled production
replacement. No live replacement or publication is authorized by this report.

A whole-image restore recovers the coherent October 24 pre-write state. For the
G-OPS-05 qualified later state, the manifest additionally binds the complete EC
controls, exact EC prefix/tail, non-EC inserts/deletes/updates and grouped clock
patches. Existing bounded proof scripts `bounded_recovery.py`,
`qualify_ec_supplement.py`, `qualify_delta.py` and recovery receipts document the
actual owner replay and exact affected-row checks; they are isolated qualification
recipes, not commands to execute against production. The separate historical
research archive restores older accepted research-row versions without requiring
their entire old database containers.

The bundle remains in ignored `temp/g_ops_05/recovery_bundle_manifest.json` and
its exact referenced artifacts. All hashes were rechecked and artifacts/directory
synced before deletion. This includes all **115 complete disappeared research
rows**, verified isolated restoration, full controls and required diagnostic
mismatches. Hold-release state binds these hashes so missing/changed evidence
blocks future pruning. The bundle is locally durable; it is not an off-host
whole-system disaster restore. Restic excludes SQLite/temp, as already documented.
Do not expire the retained image without a separately qualified general Analysis
replacement and updated owner evidence.

## Current production versus recovery vintage

Today's scheduled run preceded this task and added two findings and one divergence
row beyond the G-OPS-05 census. Those remain in production. The G-OPS-05 compact
supplement describes its original qualification vintage; it is not relabeled an
exact October 26 snapshot. The retained image remains the explicit general
recovery point requested by G-OPS-06, with the same bounded recovery limitations.
No older deleted image could preserve today's new rows.

The repeated original 25-date strict audit returned exactly the same **15,269
semantic + 2,033 lineage** differences on 19 dates. Latest six dates pass;
ticker/group-signal parity passes in that requested window. EC/DC heads and
canonical watermarks remain aligned through **October 23**. No global historical
parity claim is added; G-OPS-05's broader pre-window qualifications still apply.

Final checks preserved **244 operational/protected main-file identity and
content-change witnesses**, all **29 inspected EC/DC fact, watermark, taxonomy
and deployment table fingerprints**, publication bytes, Source/Fundamentals/
forecast databases, calculation/taxonomy definitions and configuration. All
recorded SQLite sidecars and every pre-existing temp file outside the exact
allowlist remain. StockCore's recorded operational files, databases, HEAD and
worktree are unchanged. All 12 original RawCandle worktree entries remain.

No provider call, production repair, live EC backfill, Source restore,
Fundamentals publication, compaction or StockCore modification occurred.
See [acceptance](g_ops_06_acceptance_evidence.md).
