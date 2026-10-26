# Forecast storage optimization — 2026-10-26

Decision: **FORECAST_STORAGE_OPTIMIZATION_IMPLEMENTED**.

Starting HEAD: `55edb4d5982d3c94d1c1c1c6ab2986d97cc67548`. This report belongs to the implementation commit; its final hash is reported in the commit receipt, avoiding a self-referential hash in the document. Scope was explicitly authorized by the storage-optimization request and its currentPrice clarification. The earlier read-only audit remains an accurate record of its own separate scope.

## 1. Audit basis and scope

Basis: [Forecast storage-growth audit](forecast_storage_growth_audit_2026-10-26.md), gate `FORECAST_STORAGE_OPTIMIZATION_READY`. The live DB was healthy at 2,193,960,960 bytes. Thirty-five full images consumed 33,413,648,384 bytes before manifests. Forecast PIT history is valuable and cannot be reacquired from today's Yahoo responses.

Implemented only latest-good forecast retention, gzip backup/recovery, two formally qualified exact duplicate indexes and forward-only PRICE_TARGET V2. No provider collection was started for this task. No historical snapshot, fetch, raw body, identity resolution, fiscal link or normalized historical row was changed. No fiscal-link redesign, prefix-index removal, VACUUM, OHLC feature, logging/UI redesign, scheduler change or StockCore/DC dependency was introduced. The user's 12 unrelated worktree entries were preserved and excluded from the commit.

## 2. Backup retention contract

Policy: **LATEST_GOOD_BACKUP_ONLY**. Exactly one ordinary managed image and its paired manifest survive a successfully completed daily workflow. The previous accepted image remains available until the replacement passes SQLite, compression and manifest qualification and the terminal workflow reports SUCCESS. A new manual backup can also be explicitly accepted once fully qualified.

The existing pre-write backup boundary is preserved: the daily image represents the healthy database immediately before that day's acquisition, and is promoted after the complete workflow succeeds. This task's manual production image includes the entire completed October 26 history and the two index removals. It is not a claim that the daily image is a post-acquisition image.

Extra images are permitted only for explicit incomplete recovery/creation pins. Unknown images, manifests and temporary files are `UNKNOWN_KEEP`; no filename or age scan grants deletion authority. Legacy files were retired using a reviewed exact identity/hash allowlist, not an age rule. Failed/partial collection, linking, reconciliation or reporting does not promote or retire the previous good image.

## 3. Recovery dependency analysis

Confirmed from the targeted implementation paths: old backup/restore used explicit image paths and adjacent manifests; rehearsal previously selected newest valid filename. There was no forecast latest-good pointer, recovery journal or run-ID-to-image lookup. The scheduler's failure handling reports the failed/partial operation; it does not replay a historical backup automatically. Existing report/log references are historical evidence, not active recovery obligations. No active forecast recovery obligation requiring any of the 35 old images was found.

The new `.forecast-backup-owner.json` stores one accepted image identity, its acceptance receipt, explicit recovery pins and unfinished retirement intents. `.forecast-backup.lock` serializes directory ownership; the existing per-database daily flock serializes source/target operations. These are small control records, not backup generations or a history framework. State writes and directory operations are fsynced. A corrupt/missing accepted image blocks retirement, even if the filename appears newest. Rehearsal selects the accepted pointer, not a filename heuristic.

Restore pins the exact source before materialization and releases its own token only after target qualification. An existing healthy target gets a separately pinned safety image; successful restore retires that safety image through the same accepted-good guard. Failed/crashed operations retain pins for explicit review. Restore rejects active/open targets and SQLite sidecars. An invalid existing target must be preserved and moved aside in an explicitly reviewed recovery operation before this guarded restore can replace its path; this task performed no production restore.

## 4. Compression decision

Implemented standard-library **gzip**, level 6, deterministic stream header (`mtime=0`), contract `forecast_backup_v2_gzip`. There is no new dependency. Creation first makes a SQLite backup, checks quick_check, foreign keys, schema and all nine core table counts, then compresses. Before publication it streams the gzip round trip and verifies the entire uncompressed SHA and size. The source fingerprint and file identity are also checked for changes during backup creation.

The paired manifest records source SHA/size/schema, uncompressed SHA/size, compressed SHA/size, compression format/level/version, creation time, quick_check, FK result and counts. For `.db.gz` the manifest is `.db.gz.manifest.json`. Legacy `forecast_backup_v1` `.db` plus `.manifest.json` remains readable and restore-tested. Images/manifests are mode 0444; deletion does not chmod or overwrite unknown files.

Actual production measurement:

| Measurement | Result |
|---|---:|
| Uncompressed image | 2,193,960,960 B |
| Compressed image | 332,158,273 B |
| Compressed / original | 0.151396620 (15.1397%) |
| Image reduction | 84.8603% |
| Complete creation and qualification | 46.422 s |
| Complete production-image restore rehearsal | 34.085 s |

Creation timing includes SQLite copying, integrity/count checks, hashing, gzip and verification, rather than compression CPU alone. Creation requires one transient full SQLite image plus the compressed candidate, about 2.353 GiB, while retaining the previous accepted image. Restore may simultaneously hold the materialized full image and the staged target: about 4.087 GiB of additional scratch, plus an existing target/safety image where applicable. Both restore temporaries are removed after completion. Free space before maintenance was approximately 684 GB; measured overhead is small relative to the existing 9,000-second scheduler timeout. No timeout or cadence was changed.

## 5. Rotation state machine and crash behavior

1. Acquire writer and backup-directory locks; validate existing accepted state.
2. Persist a candidate/creation recovery pin; create exclusive temporary files.
3. SQLite backup → QC/FK/schema/count verification → gzip → full round-trip SHA/size verification.
4. Publish image and manifest, fsync both data and directory entries, then validate their binding.
5. Wait for complete daily SUCCESS (or explicit qualified manual acceptance). Atomically promote the accepted pointer and record the former image as a retirement intent.
6. Revalidate the accepted replacement and exact old identities/hashes; check open references; unlink only the authorized old pair. Persist completion.

Before promotion, exceptions cannot delete the previous good image. Creation errors may clean their own known incomplete artifacts; crashes leave a pin. After promotion, a crash can leave two qualified images or one half-retired pair; the durable exact retirement intent makes a retry idempotent. Missing/corrupt latest blocks that retry. Pins win over retirement. Unknown leftovers are preserved for review. Successful creation never chooses an older point by date; acceptance order is authoritative.

## 6. Existing image qualification and cleanup

All 35 legacy images and 35 paired manifests were inventoried with inode/device/size/mtime, hashes and source manifests. Each image passed SQLite quick_check, FK, schema, counts and manifest SHA validation. Every stored row of `forecast_fetch`, `forecast_snapshot`, all three normalized tables, `forecast_identity_resolution`, `forecast_fiscal_link` and `forecast_raw_evidence` was joined by primary key and compared across **every column** against current production. Missing/different rows: **zero for every image and every table**. Accepted SUCCESS run metadata was also checked for missing/changed status, completion or counters: zero. Old in-progress run metadata and schema applied-at timestamps are workflow state, not unique accepted forecast facts.

Consequently these old points do not protect unique accepted PIT history. A newly qualified full current point protects all their accepted facts and raw evidence. This is evidence about these exact forecast images, not a general claim that old backups are redundant or that provider history is rebuildable.

At cleanup: service inactive, MainPID 0, last Result success, no source or legacy-image open references, source writer lock held. The fully restored copy-rehearsal image was temporarily pinned during the separate schema-only production index transaction. A fresh production image was then qualified and restored independently. Only after these gates did the 70 reviewed legacy files become `SAFE_TO_DELETE`. The new image/manifest were `KEEP_CURRENT_LAST_GOOD`; no recovery-pinned or unknown legacy files required retention. Other backup families were outside this allowlist and 65 other backup files/protected EC image identities were unchanged.

## 7. Forward-only PRICE_TARGET semantic V2

Old contract: `yahoo_price_target_v1`; new contract: **`yahoo_price_target_consensus_v2`**. V2 fingerprints and normalizes low/high/mean/median targets, currency and their existing field states. `currentPrice` is market-price data, not forecast-consensus semantics. It stays recognized as an expected raw field but is excluded from V2 semantic JSON and normalized rows.

Previously normalized currentPrice: **yes**, one of five rows per V1 snapshot. Future normalized currentPrice: **stopped**; V2 creates four rows. Every fetch is still persisted, including currentPrice-only changes. Full raw Yahoo body, its SHA and the fetch-to-raw reference preserve the changed currentPrice exactly. No fetch-scoped quote accessor or replacement quote projection was needed.

The existing raw purge would have nulled fetch/snapshot references before deleting expired bodies, defeating this lossless requirement. Its narrow safeguard now permits deletion only of expired **unreferenced orphan** bodies. Referenced evidence remains regardless of the old 30-day expiry marker. Production raw evidence was not purged; all 65,518 rows and bodies are unchanged. No compression/rewrite of raw DB bodies was introduced.

Mean/median/high/low changes still create semantic snapshots. Field-state and currency changes retain their existing semantics. A quote-only response with no target consensus is VALID_NO_DATA under V2, with fetch/raw evidence retained. This changes consensus availability intentionally; no quote is substituted for an analyst target.

## 8. Backward compatibility and research

All V1 snapshots, IDs, hashes, canonical JSON, five-row normalized records and historical currentPrice rows are unchanged. The explicit V1 canonicalizer argument remains available for deterministic historical replay; the default is V2 for future acquisition. `as_known_at` continues to select the observed fetch and return its stored snapshot contract and rows, so old five-row and new four-row states coexist.

The first V2 observation for an identity establishes a new versioned baseline even if its targets equal V1; this is a version transition, not automatically an analyst revision. The existing **Price Target Event Research V1** compares only mean/median/high/low numeric vectors and remains logically unchanged. Tests prove an equal-target V1→V2 boundary is not a research revision. No production/research computation depending on normalized currentPrice was found in the narrowly inspected persistence, as-known reader, forecast revision and price-target event research paths. The generic reader can still expose historical current rows for compatibility.

Market-price source for future daily historical-close research: **`data/osakedata.db` OHLC**. The researcher must choose the appropriate PIT/trading-day close boundary explicitly. A fixture using the existing historical-close loader resolves the earlier requested date rather than the latest quote. No new upside feature, latest-close substitution or provider-currentPrice dependency was added. The test uses a miniature osakedata.db; production OHLC was not modified.

## 9. Exact duplicate-index qualification

| Removed explicit index | Retained UNIQUE constraint index | Reusable bytes |
|---|---|---:|
| `idx_forecast_price_target_snapshot` | `sqlite_autoindex_forecast_price_target_1` | 12,533,760 |
| `idx_forecast_history_snapshot` | `sqlite_autoindex_forecast_earnings_history_reference_1` | 495,616 |
| Total | Both constraints remain enforced | **13,029,376** |

Qualification checks the actual table, exact expected key columns, collation, order, absence of predicates/expressions, explicit nonunique origin and an intact matching UNIQUE constraint index including index_xinfo metadata. A modified/custom index is left intact. There was no inspected INDEXED BY dependency on either removed name. Query-plan testing confirms the surviving UNIQUE index covers the price-target lookup. Schema creation no longer recreates the two twins; the migration's guarded removal is idempotent and preserves changed definitions. Operator verification no longer requires the redundant explicit names.

Production used a separate guarded transaction calling only this remover, **not** the general schema migration/upsert. All ten application tables, including schema-version applied-at metadata, have identical pre/post row fingerprints. Dropped pages are reusable: 3,181 × 4,096 = 13,029,376 B. Live file size did not shrink. Index saving means freed database pages, not additional filesystem GiB reclaimed. No VACUUM ran.

## 10. Deferred prefix index

**FORECAST_PREFIX_INDEX_OPTIMIZATION — DEFERRED.** `idx_forecast_estimate_snapshot`, 109,879,296 B, remains present. Its UNIQUE counterpart has an extra source_path column, so it is not an exact twin. Benchmark actual queries and plans before a separate removal proposal.

## 11. Deferred fiscal-link and other backlog

**FORECAST_FISCAL_LINK_STORAGE_OPTIMIZATION — DEFERRED/BACKLOG.** Investigate repeated CURRENT_RECONCILED/per-fetch context without losing PIT reconstruction, clocks, identities or evidence. All 549,746 fiscal-link rows and all fiscal-link indexes remain unchanged. The combined fiscal-link and estimate representation remains the principal DB growth driver. Existing forecast logging/UI usability backlog remains separate and unimplemented here.

## 12. Full-size copy rehearsal

Result: **COPY_REHEARSAL_PASS**. Made a SQLite backup of the locked production DB into task-owned scratch. Captured every row of every application table in stable rowid order using SHA-256 of newline-delimited canonical JSON tuples. Created and verified the first gzip point, removed only the qualified indexes on the copy, verified all row hashes unchanged, created a replacement, verified previous image/manifest retirement and exactly one remaining managed image, restored into a fresh DB and compared complete historical row hashes again.

Measured first backup 47.214 s; replacement/rotation 59.088 s; restore 35.128 s; gzip ratio 0.151396620. Production main-file SHA remained unchanged throughout rehearsal. Scratch data images were subsequently removed after production acceptance; compact ignored receipts remain under `temp/forecast_storage_optimization_20261026/`.

## 13. Production acceptance

Result: **PRODUCTION_CLEANUP_PASS**. A separate schema-only operation removed the two duplicate indexes. Then the newly created production point passed full compressed restore qualification, whole restored-image SHA and all historical table hashes. Cleanup subsequently deleted exactly **35 images + 35 manifests = 70 files**. During backup cleanup itself the production DB SHA did not change. No normal forecast collection was started, interrupted or rescheduled.

Retained image: `/home/kalle/projects/rawcandle/backups/forecasts/forecast_20261026T164151313975Z.db.gz`.

Retained manifest: `/home/kalle/projects/rawcandle/backups/forecasts/forecast_20261026T164151313975Z.db.gz.manifest.json`.

Created at UTC: `2026-10-26T16:41:51.313975Z`. Retained image and manifest final classification: **KEEP_CURRENT_LAST_GOOD**. Remaining recovery pins/retirement intents: zero. Final owner acceptance is `MANUAL_QUALIFIED_BACKUP`.

## 14. Measured storage before / after

| Item | Before | After |
|---|---:|---:|
| Live forecasts.db bytes | 2,193,960,960 | 2,193,960,960 |
| Live application rows | 2,624,780 | 2,624,780 |
| Snapshot / fetch / raw rows | 64,870 / 220,308 / 65,518 | unchanged |
| Backup image count | 35 uncompressed | 1 gzip |
| Image + manifest bytes | 33,413,681,813 | 332,159,459 |
| Image + manifest GiB | 31.118916 | 0.309348 |
| Net apparent backup bytes freed | — | **33,081,522,354 / 30.809569 GiB** |
| Backup image/manifest allocated bytes | 33,413,832,704 | 332,169,216 |
| Allocated bytes freed (image/manifest pairs) | — | **33,081,663,488 B** |
| Removed legacy files bytes | — | 33,413,681,813 |
| Duplicate-index reusable DB bytes | 0 | 13,029,376 |

Net backup saving subtracts the newly retained compressed image/manifest from the retired legacy total; it does not count deleted scratch or reusable index pages as filesystem savings. Control state/lock are additional non-image files: 951 B and 0 B, respectively. No immediate historical PRICE_TARGET shrink is claimed: V2 reduces future novelty and normalized-row writes only.

Production SHA before schema-only index removal: `711a6341ec141c51956192f8a52e3fed62d52c462e8000c8ee5edf07e9427bca`.

After indexes and after backup cleanup (equal): `443e8098d62c4bc6d6c61207a0c264fe9ac6ceb76360403eb52b4334f78e1044`.

The main-file SHA changed only for index-schema/page changes, not historical row changes. Retained compressed SHA: `8b328df0b42f11ab6e21f51f8f0de6dd76d8b72ff346480e84e67e80825f1ffd`. Restored uncompressed SHA: `dbc5944d3f52fe1fba78fe5be4bcbf45c46c9461dac09f02f7a7779647a79599`. Source SHA in the manifest: `443e8098d62c4bc6d6c61207a0c264fe9ac6ceb76360403eb52b4334f78e1044`. SQLite backup may adjust file-header bytes; source and backup fingerprints are recorded independently.

## 15. Focused tests

**138 passed**, final focused run 33.46 seconds. Files:

- `tests/test_forecast_storage_optimization.py`
- `tests/test_forecast_operational_hardening.py`
- `tests/test_forecast_persistence_v1.py`
- `tests/test_price_target_event_research.py`
- `tests/test_forecast_operator.py`
- `tests/test_forecast_scheduler_rollout.py`
- `tests/test_forecast_scheduler_ui.py`

Coverage includes exception/crash injection after pin persistence, SQLite creation/validation, gzip creation/roundtrip, image/manifest publication and before/after pointer promotion; crashes before unlink and after the first pair artifact unlink; retry/idempotence; missing/corrupt latest preventing old deletion; pinned old points and unknown artifacts preserved; gzip corruption rejection and exact restore; interrupted restore pins; explicit legacy V1 restore; complete versus partial daily acceptance; currentPrice-only raw/fetch retention and snapshot reuse; no new normalized current row; unchanged old rows and mixed PIT reads; all four target fields creating snapshots; equal-vector V1/V2 research boundary; quote-only no-consensus classification; historical OHLC close lookup; expired referenced raw preservation versus orphan cleanup; exact-index lookup/constraint/custom-definition/idempotence checks. Existing event-research regression and scheduler/operator integration tests passed. No unrelated Fundamentals/DC/valuation suite ran.

The early focused runs caught expected old five-row assertions after V2, unordered SQL comparison in a new test, and a test's still-open SQLite connection before restore. Assertions were updated to the new contract, comparisons made deterministic, and handles explicitly closed. Production cleanup began only after the final 138-test pass and copy rehearsal.

## 16. Recovery and integrity evidence

Production and restored image: quick_check **ok**, foreign_key_check **0 violations**. Schema contract remains `forecasts_v2_fiscal_links`. All original data-table row fingerprints are identical before/after both index maintenance and cleanup:

| Table | Rows | SHA-256 of ordered complete rows |
|---|---:|---|
| `forecast_earnings_history_reference` | 10,647 | `06c37ea5147eb562aa6f79964433342ff205b7ac195838ef8f308aad774ef883` |
| `forecast_estimate` | 1,405,921 | `040d90867640f4af4fa37e2d6adc94421abfafadf8293745a35c21172cf41c0a` |
| `forecast_fetch` | 220,308 | `cc79c2afa0202925c4372810e837f09c509db73fc6d4b048d834b9b52e27aa08` |
| `forecast_fiscal_link` | 549,746 | `f06f08a852d3605f81a84d5072d8186636cf32a2c0f818f752f97662140bfe0b` |
| `forecast_identity_resolution` | 73,436 | `3322a3906a738da0754da1e0dc0040cb533b2cfa2b6fdad12dee2264b4a7266a` |
| `forecast_price_target` | 234,300 | `c33a9beeb4b667a2f6fba924e481125bd2b7b4e04972ca1b277e7e09638fe976` |
| `forecast_raw_evidence` | 65,518 | `9a4e1675b293e55ddd46f3aeca9137fffe029c049ed4d2e8ecd3508e7cc0dd80` |
| `forecast_run` | 33 | `a7ad4b23db498c202c4107bed244ca68ef8360ca6d526502fcedecce3e7d98f4` |
| `forecast_schema_version` | 1 | `041512b0c00f4f9214b6c8f59c97cc3271a5b5ccfab36e940a563d949176f795` |
| `forecast_snapshot` | 64,870 | `3367ad17203e35fb9e260e9a6e08d698840ae6ca5ed17062396758e109aea089` |

Compact runtime receipts retain the full pre/post file identities, per-image legacy coverage/count checks, retirement allowlist, cleanup classifications, exact deleted path list, source/restored hashes and timing under the ignored task directory. The permanent inventory below preserves hashes for both members of every retired pair. For each row the image path is `backups/forecasts/<basename>.db`; its paired manifest is `backups/forecasts/<basename>.manifest.json`. Both were classified **SAFE_TO_DELETE** and both were deleted.

| Retired basename | Image bytes | Image SHA-256 | Manifest SHA-256 |
|---|---:|---|---|
| `forecast_20260927T174304257344Z` | 598,016 | `1f48ded14069cd9f6c0e1703dfc724e787340ff14bacc00840c48898fde64f8b` | `09d19667c3808efad03af7eb0e89ef406eb74ea65ff384c56becf0f9e75e076a` |
| `forecast_20260927T185204266430Z` | 598,016 | `1f48ded14069cd9f6c0e1703dfc724e787340ff14bacc00840c48898fde64f8b` | `cc7800fe39eaf4e62ed4e0594c52794f899b767a0756e288d1bc77c41950b593` |
| `forecast_20260927T191419466265Z` | 917,504 | `0ceef9250f636ac73e2734687d0acf689a51fc4290101aab4684b3eabb7a3252` | `0e101dd38fea0432f4ecb08a77eb0a67e380ba37d072885dc32041591f353602` |
| `forecast_20260927T193934723866Z` | 8,167,424 | `ec258b15446faa82d9756cd3e4c23edb762d8d3560906e2622a97e47ef355ec2` | `9f9c6667f47ba9174b8e647a2135907ac914d840c6e3f49f7df543b4ddfb319e` |
| `forecast_20260927T204445452888Z` | 183,095,296 | `d8d94db994ceea22af6cbad01063084f2e460930acb86336b1dab5ca74c70856` | `483557cb6c7f44e9e3beb0ba1d5e3de79225aa3f48b89ddabf3a2d7fa68f20a5` |
| `forecast_20260927T204846170498Z` | 183,111,680 | `c1b3dbb3bfdcbaa4695e695b331bdc55a605cade3c2e50d50d20ed78eabb1249` | `038a38cb56c8380c939f19e32839975881aaf82b494a50f10079b73e8d80f8d1` |
| `forecast_20260928T043011800370Z` | 183,111,680 | `c1b3dbb3bfdcbaa4695e695b331bdc55a605cade3c2e50d50d20ed78eabb1249` | `dd3bfdd25f40ec222737ec117118567fef05e689ab668491167dab881a390437` |
| `forecast_20260928T110011609595Z` | 223,006,720 | `ca68641f7c20f43005e0647278751b75dae3059c26d719862d4cbdd32c2c8edf` | `36c41a3f0ea111bc6f8498ef43d75a9ab43803a5dd0f979f20029b21c4c4cf23` |
| `forecast_20260929T110015803132Z` | 271,114,240 | `6358728ff64920e67d729f7002c80a9ee883a2ce0fd79bd0e84a7811cadf37e4` | `c31a9f1b7a198f0588c60944b0e266ae2087e36770f84f839618d6b539368ef1` |
| `forecast_20260930T110016952191Z` | 335,138,816 | `730388861c7470e008ce20f23f9b38dc6339b13d282c448c7524197c1d58e158` | `d34a05965f7636acfdba342dd00a5ec862be37ed4740a1ab989b8ab2f9c91333` |
| `forecast_20261001T110102042071Z` | 401,285,120 | `46a8d07beec4bb970129648cbc5a1f5872d99914b2f706ad057d67f70beb0eb7` | `474e6b4639ef39d7787e15b9c1ea81aec063573df46ea83ec1a32e898568b4ec` |
| `forecast_20261002T110103114475Z` | 472,186,880 | `c0aa92e664a276cd42ecabf7dbb28879ae045f84bed8286d00b9833b343cd39c` | `d94412b46fa12ab19c123532c9e63bdaf9e22208c551f7704472e88e3b763e5d` |
| `forecast_20261003T110021812402Z` | 535,232,512 | `58f679b2b51f88f0d814601e068ee73d3947c71faeeec4b30d4a86a3a3db5cad` | `5551a8f9d247a00c484c42f62136a8e1efb5728bede8db9ae3661b21525ea326` |
| `forecast_20261004T110022313057Z` | 604,946,432 | `ee2106ba9d2b6e65794db72706f5716ef243348780791a904cc0dfcf314137f1` | `a6abc1093a54b081a7df3bb0d67251b56a09c78d03c8bebc421769b60059203c` |
| `forecast_20261005T110023280993Z` | 686,645,248 | `364a5a9b7138241f4ad85c81ffa8f62642417a4f1e2c4e92acc758e03a9f0459` | `0c4f247963a7e2dba72131a055ff65c85da9f525aeeedbd033ff7a9c937c08fa` |
| `forecast_20261006T110025118756Z` | 773,488,640 | `3ecc1436a8798652b84bed2f65e82baa79872e7d6c630af0d260b1d8fe33bd83` | `9633305a54d359698963a55b8695900376db0232db026e3928bb7438e3532f3b` |
| `forecast_20261007T110026886990Z` | 849,448,960 | `d4c1c0bce406d68ee1cb560478d321e9a8a0316a9832235d0c71a0355a78ba78` | `0cffa9a82d6058de53a3e107c4f7d2bb8632f119ae96eff9b8cba8ab5c917180` |
| `forecast_20261008T110027716948Z` | 925,569,024 | `6aba43643138f08f6608117173ffc8a64e798c1e135e08699a2c77ff65fd8e17` | `07a29f0f065446e8ecfbbe171e1f6c794814c7ca3b82e4f9672b9d66ef93d603` |
| `forecast_20261009T110039844604Z` | 1,003,212,800 | `d90b9658e32d5f4b9d84ceaed5695d6c2dc90f7923c358b01ad7fbc6a6fd2179` | `89e97796e25f8dd22f5b6dd638f4439125831c1fe2ad20c73d45e64167d6b610` |
| `forecast_20261010T110030661253Z` | 1,073,770,496 | `3480e32a98769b3587b8c71c166625f43db188f0ecf05674041cb185312af6b9` | `9aa51760448a27b1cd3706d7308a6beb637966948b738235f508ea19b5486801` |
| `forecast_20261011T110031526961Z` | 1,144,713,216 | `95b2047e47b500cc3f9a9060dc7112f128ecfcb5c742c68c20d1e16af733d1f7` | `2dd1078d24d0c1bf6f3570097f28c4e7152971bd792942c9325f9f7d28a865b2` |
| `forecast_20261012T110033772324Z` | 1,184,395,264 | `d08ad0c0ba9636dbd9fe6885c713de6694da60b339ebf5920ca6bbc3254ffd86` | `eeb08b766cb9b66607dbf525bccbeae610b335a3f80f98eff9cb6452347fd083` |
| `forecast_20261013T110033405620Z` | 1,224,368,128 | `083d775be0cb6d627a496d9e7121b1044253519c6f14ca05d8a5e7b7712b8887` | `70d5222473fa276e1a2da46baa597e1e5ba18de7d1549cfb7caabaaeaf54d770` |
| `forecast_20261014T110045814711Z` | 1,324,658,688 | `8abbcf94031328d11c31096ed5c4020e36db68f03cf44729720ebd31171d62b9` | `b6fbaa053f7e2167527ef98a1f556c8e2ec6e9288203c213d1d6fc5283993445` |
| `forecast_20261015T110108413896Z` | 1,413,865,472 | `c93f60c69acf966fd14d5cb80efc4f4317852ad0e4008a3ea2d5d8756493bb19` | `88a861326669d87ed723b604c309e86ec25003e4b88bdd683a64aa691f62fd40` |
| `forecast_20261017T110110528171Z` | 1,513,025,536 | `5e325dd0b49f3d3fea51c10a3fb0d5cc1861c860d14b1055ba67957a60569374` | `0cd5f0f285b6e0ff7f6feb7e9a2eb22a379e4548432685695e03eb1bf2de305d` |
| `forecast_20261018T110109988781Z` | 1,622,102,016 | `b6247de8ae334ed171e69505c0810e96709d37b846c61bdb0a7f347170ca39f4` | `ab750b569cb8a8b7571252e56b166de82ee8ad569e11d9e9082b1938a98a80b0` |
| `forecast_20261019T110111291722Z` | 1,671,876,608 | `65fc5ea9a9681071896f4d91dd93e004d07c8113447ff85959626c55ac600e7a` | `b3090fdbc48124a69d5ad57b6cd288ea15627ed6ab4c3a5b3a22bb075309248b` |
| `forecast_20261020T110112817471Z` | 1,714,126,848 | `dbb413da801522321082ff8fbba0d4b1223fd84efcbd0bb23f9526514f72f72e` | `739a149e0f114b840591d4e319e6048b4c87e6d4bc72106441f977453d39bc58` |
| `forecast_20261021T110116106166Z` | 1,796,042,752 | `46efbde4111e51589caa4631ecffc2bf59831f7059f6ad0a68451788c18d73b6` | `8688266c00536b3dc0257cd9fed4bab6c8083a0fda80dc6720ed2efee712f7b7` |
| `forecast_20261022T110115976856Z` | 1,872,232,448 | `d37304c77f8d1030733b224f41bf4dd2591aca9b45690dc7a6490f385a77bc9a` | `3badb68a69d641297433b8cbf7f0bc44c971cd046a751f36baec1e0cfa00384b` |
| `forecast_20261023T110054798903Z` | 1,948,495,872 | `00d96cf324c65ff9abc97f2ba530cb9e8e54861ab6efd3cfa39b6cc381916de9` | `bae680d610a49dc2f1f0cd3114ed0b7f8b57e2eb11d37d5a22d20d877045c213` |
| `forecast_20261024T110104218444Z` | 2,026,012,672 | `eeeede5ceb7f1c7d2752886d037400b7b6fc2dc7134f219aec9d8e127d9ec80a` | `4f18cb677d337716c3567579e3ffe3f307d41eae3853c553a3230275ecf469f9` |
| `forecast_20261025T120104757576Z` | 2,093,645,824 | `aa7d1178bd6e31d4be34ec6e1a32f4d2ce2cc96ba970205a9b2b8fdbdc6def39` | `b42d433ca66dc42ee3b528e5617330db8a7700ee445134fcab0e96af699c962f` |
| `forecast_20261026T121149569963Z` | 2,149,441,536 | `4876f8cf895a847b5ccf64ecd6b3263d8ce1191e89bb09f7d73ce7ef19afdecb` | `0cc10e59f50c657d9a5f6119856169cb28ce0ac4d4e99d28224d60c272b3adef` |

## 17. Operational policy going forward

The normal 14:00 Europe/Helsinki service remains unchanged. Final systemd inspection reports an active timer with next execution **2026-10-27 14:00 EET** and an inactive successful service (MainPID 0). Configuration SHA before/after is `67e55b992b6144306b8b96a23157d4879490256c3af1d267f3852da5f1587e79`. Scheduler/service/timer source and installed units were not changed. Daily backup operations use the accepted owner pointer; a successful workflow promotes and prunes, while failure preserves the old point plus explicit unfinished-operation pins. Re-running `backup-retention --apply` is safe for pending authorized retirement intents and does not adopt old unknown files. Manual `backup` explicitly creates/qualifies/promotes a new current point. Restore/rehearsal transparently materialize either qualified gzip or legacy SQLite.

For recovery, inspect the owner record and exact manifest first. Use the existing explicit-path `restore` command to a fresh, non-production target and verify QC/FK/hash/PIT data before an explicitly approved production restore. Production-path overwrite still requires `--apply-production`, the daily lock, a healthy closed target and safe sidecar state. Failed/crashed operations leave durable pin tokens: establish that the operation is finished or abandoned, validate its retained good replacement and exact artifacts, then explicitly release only the reviewed token using the lifecycle owner API; do not edit/delete pins or unknown files by age. A failed candidate without a complete manifest stays recovery-pinned/unknown until reviewed. There is no automatic rollback to an older image and no replay of a partial daily acquisition.

Recommended next step: let the next scheduled forecast run proceed normally and review its terminal SUCCESS, one accepted gzip image and empty recovery-pin/retirement sets. Separately investigate the named fiscal-link and prefix-index backlog items; no repair or collection run is needed now.

**FORECAST_STORAGE_OPTIMIZATION_IMPLEMENTED**
