# G-OPS-05 whole-Analysis backup recovery decisions

**Propose 23 RETIRE_CANDIDATE images: 278,384,205,824 allocated bytes. Retain image
24: 13,213,745,152 bytes. Do not retire all 24.** These are decision-phase proposals,
not deletion approval. All 24 images / 291,597,950,976 bytes remain unchanged.
No new full image was discovered; no deletion or operational publication occurred.

| Classification | Images | Allocated bytes |
|---|---:|---:|
| RETAIN_REQUIRED | 1 | 13,213,745,152 |
| RETAIN_TEMPORARILY | 0 | 0 |
| RETIRE_CANDIDATE | 23 | 278,384,205,824 |
| BLOCKED_UNCERTAIN | 0 | 0 |

All **21** historical proposal images, **252,230,393,856 bytes**, are candidates.
The former parity uncertainty is not a perpetual whole-image recovery obligation.
The exact machine-readable proposal is ignored
`temp/g_ops_05/retirement_proposal.json` (`authorized=false`, `apply=false`).

## Why one full image still matters

Image 24 is the latest existing full snapshot of operational `data/analysis.db`.
Its current obligation is **general Analysis loss/corruption recovery**, including
non-EC data, not preservation of an irreplaceable old EC projection. The online
SQLite backup, G-OPS-04 full-image hash/integrity/schema qualification and unchanged
identity witnesses remain valid. G-OPS-05 inspected all 50 tables in every image,
qualified current-state supplements and exercised bounded restoration.

No independently qualified recent full replacement outside this EC-created family
was found. September weighting backups are older; Fundamentals backups and active
immutable generations protect `fundamentals_analysis.db`, a different role, not
this 13 GB database. Restic's configured job excludes SQLite databases and `temp/`.
Do not count it as an independent qualified Analysis database recovery mechanism.
No new 13 GB permanent copy was created as a procedural substitute.

Preserve image 24 until another equivalent/newer general Analysis point is
qualified with its required controls and later accepted changes. A future cleanup
can adopt/promote this existing file in place, or use a later already-created
qualified image; a rename is neither physical retirement nor extra space recovery.
The current path is locally protected by the unchanged hold and cleanup policy,
not an off-host disaster-recovery guarantee.

## Whole-database protection, not EC-only reasoning

| State | Evidence / preservation |
|---|---|
| Four EC fact tables | Every row identifies its DC source; optional unmapped fields are NULL. Existing metadata plus DC can generate new projections. Current earlier-vintage state is exactly recoverable from image 24 plus its recorded six-date tail. |
| EC-only identity/publication controls | All 12 control tables exported completely with schema/columns/row fingerprints: IDs, taxonomy, memberships, aliases, watchlist, calendar, runs, deployments and audits. These cannot simply be regenerated from DC numeric facts. |
| User/external observations | All 26 excluded-ticker records, 181,136 blackout records and 42 results-metadata records are preserved by image 24. Full blackout payloads and exclusion/metadata fingerprints match across all 24 images and current production. |
| Accepted relevance history | Image 24 preserves all 201 runs and 2,395,200 records. Every earlier run's row count survives; the run owner inserts run identities rather than treating each full EC backup as its archive. Full current relevance payloads equal image 24 in the current-state delta comparison. |
| Older research rows | 115 complete `results_data` rows absent from image 24 are preserved in a **567,436-byte** compact archive, including original schema, values, image associations, IDs and clocks. All 115 exact row-version restoration tests pass in an isolated memory table. No other non-ID/non-clock research-row payload differs across the 24 reviewed versions. |
| Mutable generated findings/divergence/Dow/DC output | The owners insert/replace or rebuild accepted scopes. Intermediate calculation versions are not independent raw-observation archives or active rollback commitments. Current required outputs are protected by the latest full image and the exact supplement; no earlier image is asserted byte-equivalent. |
| Retired DC-report tables / temp_test | All 17 retired-report tables and temp_test are empty; no data capability is lost by retirement of their old physical container. |

The complete **34-table non-EC** source-to-current comparison was read-only. Its
**231,243-byte** supplement records all differences: 11 added findings; 9 added
and 180 updated divergence rows; 48 removed/50 added Dow event rows; 9 Dow status
updates; 9 watermark updates; and losslessly grouped timestamp-only rewrites for
92,448 index and 16,430 synthetic rows. Unchanged tables have full row fingerprints.
Every affected-row patch was applied and checked against current accepted rows in
isolated memory SQLite tables. This is a precise supplement, not an unqualified
assumption that matching row counts mean matching data.

The **537,335-byte** EC/control/sequence export and **3,754,667-byte** exact
2,508-row current EC tail preserve original provenance and clocks. Together with
the non-EC delta and research archive, these core supplements total **5,090,681
bytes**, plus small manifests and diagnostic receipts. The retained full image
remains necessary: these extracts alone are **not** a full Analysis restore.
The bundled manifest binds image identity/hash and artifact hashes.

Old generated values can have distinct historical vintages; this is not proof
that every old snapshot remains required. The explicit user policy ends routine
pre-write rollback once its accepted operation is closed, unless an independent
current owner needs it. No active publication journal, generation manifest or
scheduler state references a candidate as a pending restore. Completed reports
are provenance, not permanent retention commands. Missing-day insert receipts
and accepted EC recovery evidence preserve the specific diagnostic history.
The existing missing August pre-taxonomy image reference is a separate recovery
gap: none of these September/October images can provide that earlier reversal.
Retaining all 24 would not repair that missing capability.

## Individually reviewable matrix

Every filename below resolves exactly under
`/home/kalle/projects/rawcandle/temp/`. Exact absolute paths, apparent and allocated
sizes, hashes, device/inode/link/owner identity, originating receipt paths and
intervals, EC/DC state, all-table census, alternatives and expiration conditions
are in `temp/g_ops_05/backup_recovery_decisions.json`.

Reason/expiration codes:

- **A:** pre-V2 routine operation closed; complete accepted V1 facts survive with
  original migration hashes in image 24/current. Preserve the compact bundle;
  separate cleanup authorization and fresh identity/owner checks end this image's role.
- **B:** original version-selection failure closed by explicit-version forward
  catchup and subsequent accepted recovery. Failure remains historically FAILED;
  no automatic rollback or relabeling is assumed. Same cleanup prerequisites.
- **C:** October 3 manual catchup's selected scope accepted; later accepted state
  supersedes its rollback. Historical diagnostics and research rows preserved compactly.
- **D:** October 14 recovery R1/R2/R3 PASS and no EC retry pending; its source-input
  transition is preserved by receipts/mismatch evidence. No current full-image restore need.
- **E:** ordinary accepted selected-scope run superseded; keep image 24 and compact
  non-EC/research controls rather than every intermediate whole Analysis state.
- **R:** retain for general Analysis recovery until a separately qualified
  replacement covers required non-EC state and accepted dependencies. Do not expire
  it based only on EC parity, age or a changed filename.

| ID | Exact filename | Allocated bytes | Origin EC outcome | Decision / reason |
|---|---|---:|---|---|
| 1 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260911_20260918__20260920T034202Z.sqlite` | 11,078,078,464 | COMPLETE | RETIRE_CANDIDATE / A |
| 2 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260914_20260923__20260924T042100Z.sqlite` | 11,172,302,848 | COMPLETE | RETIRE_CANDIDATE / A |
| 3 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260917_20260924__20260925T041337Z.sqlite` | 11,264,593,920 | COMPLETE | RETIRE_CANDIDATE / A |
| 4 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260918_20260925__20260926T111845Z.sqlite` | 11,356,659,712 | COMPLETE | RETIRE_CANDIDATE / A |
| 5 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260921_20260928__20260929T041800Z.sqlite` | 11,469,307,904 | FAILED; forward recovered | RETIRE_CANDIDATE / B |
| 6 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260922_20260929__20260930T041342Z.sqlite` | 11,555,975,168 | FAILED; forward recovered | RETIRE_CANDIDATE / B |
| 7 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260923_20260930__20261001T041542Z.sqlite` | 11,644,329,984 | FAILED; forward recovered | RETIRE_CANDIDATE / B |
| 8 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260924_20261001__20261002T041851Z.sqlite` | 11,736,100,864 | FAILED; forward recovered | RETIRE_CANDIDATE / B |
| 9 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260924_20261002__20261003T135514Z.sqlite` | 11,827,843,072 | COMPLETE | RETIRE_CANDIDATE / C |
| 10 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260928_20261005__20261006T041910Z.sqlite` | 11,915,485,184 | COMPLETE | RETIRE_CANDIDATE / E |
| 11 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260929_20261006__20261007T042129Z.sqlite` | 12,002,193,408 | COMPLETE | RETIRE_CANDIDATE / E |
| 12 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260930_20261007__20261008T041913Z.sqlite` | 12,091,564,032 | COMPLETE | RETIRE_CANDIDATE / E |
| 13 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261001_20261008__20261009T041929Z.sqlite` | 12,183,887,872 | COMPLETE | RETIRE_CANDIDATE / E |
| 14 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261002_20261009__20261010T042304Z.sqlite` | 12,276,498,432 | COMPLETE | RETIRE_CANDIDATE / E |
| 15 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261005_20261012__20261013T041830Z.sqlite` | 12,362,510,336 | COMPLETE | RETIRE_CANDIDATE / E |
| 16 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261006_20261013__20261014T094436Z.sqlite` | 12,450,455,552 | COMPLETE | RETIRE_CANDIDATE / D |
| 17 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261007_20261014__20261015T042325Z.sqlite` | 12,584,992,768 | COMPLETE | RETIRE_CANDIDATE / E |
| 18 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261008_20261015__20261016T041944Z.sqlite` | 12,682,313,728 | COMPLETE | RETIRE_CANDIDATE / E |
| 19 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261009_20261016__20261017T042428Z.sqlite` | 12,773,339,136 | COMPLETE | RETIRE_CANDIDATE / E |
| 20 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261012_20261019__20261020T042221Z.sqlite` | 12,858,425,344 | COMPLETE | RETIRE_CANDIDATE / E |
| 21 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261013_20261020__20261021T042349Z.sqlite` | 12,943,536,128 | COMPLETE | RETIRE_CANDIDATE / E |
| 22 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261014_20261021__20261022T042600Z.sqlite` | 13,032,247,296 | COMPLETE | RETIRE_CANDIDATE / E |
| 23 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261015_20261022__20261023T042325Z.sqlite` | 13,121,564,672 | COMPLETE | RETIRE_CANDIDATE / E |
| 24 | `analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20261016_20261023__20261024T042011Z.sqlite` | 13,213,745,152 | COMPLETE | RETAIN_REQUIRED / R |

Rows 1–21 are the exact older proposal. Manual rows 9/16 bind the October 3/14
recovery receipts; other rows bind their dated scheduler summaries. Actual
originating intervals are encoded in the filenames and machine matrix.

## Minimal separately authorized cleanup

1. Revalidate the exact 23-file proposal, unchanged identity/hash and no active
   owner/open reference; verify no new failed operation has reused a candidate.
2. Preserve/qualify image 24 as the general Analysis recovery point and retain
   the compact bundle, including all 115 historical research rows and current
   controls/supplements. Verify artifact hashes and bounded restoration receipts.
3. Delete only the individually approved candidate files under existing owner
   locks; retain compact receipts and measure actual allocation afterward. No
   live EC/DC repair, provider call or general directory cleanup is needed.
4. Separately qualify the existing retention hold for release using the clarified
   rebuildability/general-recovery obligations. G-OPS-05 does **not** edit it.

The G-OPS-04 lifecycle can bound qualified accepted runs, but **the present hold
still prevents automatic pruning and qualifying future runs may continue adding
full images**. Failed/interrupted/reused recovery remains protected. The current
image is unregistered legacy material and is not silently swept by the new
terminal function. Existing Windows cleanup protects the family. Do not claim
recurrence is operationally resolved until the separately authorized owner review
covers the general Analysis point and releases/replaces the hold. No new cleanup
scheduler or backup framework is proposed.

See [rebuildability](g_ops_05_ec_historical_parity_analysis.md),
[versions](g_ops_05_version_and_lineage_matrix.md) and
[acceptance](g_ops_05_acceptance_evidence.md).
