# Forecast storage-growth audit — 2026-10-26

Decision: **FORECAST_STORAGE_OPTIMIZATION_READY** for a measured optimization proposal; implementation is **not authorized by this audit**. Production, acquisition, linking, research, schemas, identity rules, schedules and backups were not changed.

## 1. Executive summary

`data/forecasts.db` is **2,193,960,960 bytes / 2.043 GiB**. All 2,624,780 application rows and the entire collected history were measured read-only. Growth is real retained data and index amplification, rather than a freelist leak:

- Fiscal-link table/indexes: **923,713,536 bytes / 42.10%**.
- Normalized fiscal estimates/indexes: **573,775,872 bytes / 26.15%**. Together these two areas are **68.26%** of the DB.
- Raw provider bodies: **118,700,714 bytes / 5.41%**. Raw table plus its index is 6.63%. The reported ~118 MB raw evidence is correct and does not explain the other storage layers.
- Fetch-specific fetch/identity/link representation costs about **37.94 MiB per full run**, including when existing semantic snapshots are reused.
- `currentPrice` alone explains **39,638/70,895 transitions (55.91%)**. Excluding it reduces PRICE_TARGET identities **46,860 → 8,539 (81.78%)**, but the estimated whole-DB counterfactual saving is only **114,469,926 bytes / 5.22%**.
- Backups are the larger physical multiplier: **35 full images / 33,413,648,384 bytes / 31.119 GiB**, versus 2.043 GiB live. The daily service creates full images but does not invoke the existing manual tier-retention function.

The last 12 full runs averaged **72,441,856 bytes / 69.09 MiB growth per run**. With one full run every future day and no pruning, the +365-day extrapolation is **26.669 GiB live + 5,258.733 GiB backups**. This extrapolation exceeds the filesystem's capacity; it is a trajectory, not a promise that such storage can be allocated.

Prior context reconciles: the October 14 report measured **1,324,658,688 bytes before that day's collection**; the persisted October 14 daily report records **1,413,865,472 bytes after collection**. The approximate 1.41 GB checkpoint refers to the latter.

## 2. DB health and safety

| Measurement | Result |
|---|---|
| Path | `/home/kalle/projects/rawcandle/data/forecasts.db` |
| Apparent / filesystem allocated bytes | 2,193,960,960 / 2,193,965,056 |
| SHA-256 before = after | `711a6341ec141c51956192f8a52e3fed62d52c462e8000c8ee5edf07e9427bca` |
| Page size / page count | 4,096 / 535,635 |
| Page-count × size | 2,193,960,960 bytes |
| Freelist / freelist bytes | 0 pages / 0 bytes |
| Journal mode / auto_vacuum | DELETE / 0 (NONE) |
| Schema contract | `forecasts_v2_fiscal_links`; SQLite user_version 0 is the existing contract |
| quick_check / foreign_key_check | ok / 0 violations |
| WAL / SHM / rollback journal | None at both checks; no checkpoint or journal-mode change |
| Owner | Forecast service inactive, no open DB owner; no writer lock active |

File identity, allocation, mtime/ctime and SHA stayed unchanged. The 4,096-byte `stat` allocation excess is outside the DB's apparent page count; it is not extra database pages. No filesystem reallocation operation was attempted.

Connections were `mode=ro&immutable=1` after absence of a writer/hot sidecar was established, with query-only and in-memory query scratch. No Fundamentals or OHLC database was opened. No provider, migration, VACUUM, ANALYZE, REINDEX, checkpoint, retention apply, backup or production research export ran. No broad pytest suite ran.

Starting HEAD: `a69b8fbd29906a8b5bbf19c43956967637f533de`, branch `chore/ignore-backups`. All 12 unrelated original worktree entries were preserved. Temporary scripts/compact receipts are ignored under `temp/forecast_storage_audit_20261026/`; only this report and the explicitly retained compact object CSV belong to the local audit commit. No applicable RawCandle/ancestor AGENTS.md was found. No StockCore change was made.

## 3. Table/storage ranking

Bytes below are **table b-trees only**; the last column separately reports their indexes. Shared family/mode page attribution later uses measured serialized-record-payload ratios, not invented exact page ownership.

| Table | Rows | Table bytes | Cell payload bytes | Table B/row | DB % | Own index bytes |
|---|---:|---:|---:|---:|---:|---:|
| `forecast_fiscal_link` | 549,746 | 751,894,528 | 683,364,679 | 1,367.7 | 34.27% | 171,819,008 |
| `forecast_estimate` | 1,405,921 | 280,518,656 | 263,389,556 | 199.5 | 12.79% | 293,257,216 |
| `forecast_snapshot` | 64,870 | 207,532,032 | 171,098,905 | 3,199.2 | 9.46% | 17,055,744 |
| `forecast_fetch` | 220,308 | 150,646,784 | 136,438,113 | 683.8 | 6.87% | 52,871,168 |
| `forecast_raw_evidence` | 65,518 | 139,919,360 | 128,743,386 | 2,135.6 | 6.38% | 5,480,448 |
| `forecast_identity_resolution` | 73,436 | 50,262,016 | 43,672,143 | 684.4 | 2.29% | 18,210,816 |
| `forecast_price_target` | 234,300 | 25,812,992 | 23,879,752 | 110.2 | 1.18% | 25,067,520 |
| `forecast_earnings_history_reference` | 10,647 | 2,072,576 | 1,930,679 | 194.7 | 0.09% | 991,232 |
| `forecast_run` | 33 | 516,096 | 498,875 | 15,639.3 | 0.02% | 4,096 |
| `sqlite_schema` | 32 | 16,384 | 9,983 | 512.0 | 0.00% | 0 |
| `forecast_schema_version` | 1 | 4,096 | 65 | 4,096.0 | 0.00% | 4,096 |

All table b-trees total **1,609,195,520 bytes (73.35%)**. No additional forecast checkpoint/audit tables exist beyond the actual schema listed here; run, fetch, resolution and link tables hold that evidence.

The [compact CSV](../../exports/forecasts/forecast_storage_growth_audit_2026-10-26.csv) lists all objects individually, including system schema and the reserved page. Table rows and index rows describe the same underlying records and must not be summed as independent business records.

## 4. Index ranking and query/constraint roles

All **22** indexes total **584,761,344 bytes (26.65%)**. Every index is listed separately in the CSV; the ten largest are:

| Index | Parent table | Bytes | DB % |
|---|---|---:|---:|
| `sqlite_autoindex_forecast_estimate_1` | `forecast_estimate` | 183,377,920 | 8.36% |
| `idx_forecast_estimate_snapshot` | `forecast_estimate` | 109,879,296 | 5.01% |
| `idx_forecast_fiscal_link_fetch` | `forecast_fiscal_link` | 75,497,472 | 3.44% |
| `sqlite_autoindex_forecast_fiscal_link_2` | `forecast_fiscal_link` | 45,883,392 | 2.09% |
| `idx_forecast_fetch_asof` | `forecast_fetch` | 28,520,448 | 1.30% |
| `sqlite_autoindex_forecast_fiscal_link_1` | `forecast_fiscal_link` | 28,352,512 | 1.29% |
| `idx_forecast_fiscal_link_target` | `forecast_fiscal_link` | 22,085,632 | 1.01% |
| `idx_forecast_fetch_run` | `forecast_fetch` | 14,319,616 | 0.65% |
| `idx_forecast_price_target_snapshot` | `forecast_price_target` | 12,533,760 | 0.57% |
| `sqlite_autoindex_forecast_price_target_1` | `forecast_price_target` | 12,533,760 | 0.57% |

The fiscal normalized indexes total **293,257,216 bytes**, **104.54% of their table**. Long snapshot/metric/statistic/source-path keys and a second prefix index amplify storage. PRICE_TARGET indexes total 25,067,520 bytes, 97.11% of their table, partly because the same key is indexed twice.

Narrow role inspection covered `schema.py`, `repository.py::as_known_at`, fiscal `link_fetch/as_known_at` and both forecast research readers. Read-only EXPLAIN QUERY PLAN and full-result comparisons on real snapshots passed:

- `idx_forecast_price_target_snapshot(snapshot_id,statistic)` duplicates the key of `sqlite_autoindex_forecast_price_target_1`; the automatic UNIQUE index enforces the constraint. Explicit duplicate size **12,533,760 bytes**.
- `idx_forecast_history_snapshot(snapshot_id,occurrence_index)` similarly duplicates `sqlite_autoindex_forecast_earnings_history_reference_1`; explicit duplicate **495,616 bytes**. Together **13,029,376 bytes / 0.59% DB** are strong separate-task candidates after regressions. No inspected reader names these indexes with INDEXED BY.
- `idx_forecast_estimate_snapshot(snapshot_id,occurrence_index,metric,statistic)` is a strict prefix of the required UNIQUE key that also includes source_path. Its **109,879,296 bytes / 5.01%** are a candidate, not proof of safe removal. Both indexes answered the actual snapshot/occurrence read with identical rows/sort plans in a bounded sample; group-by and complete daily/research workload performance still need qualification. Retain UNIQUE/PK enforcement and do not drop this prefix on size alone.

No index was dropped or rebuilt. With auto_vacuum NONE, a future index drop would initially release reusable DB pages, not automatically shrink the file. Physical truncation would need separate qualification. Sample query equivalence is not a whole-workload latency guarantee.

## 5. Recent daily row and file growth

UTC collection dates; sizes are MiB (2^20). DB-after sizes come directly from accumulated `logs/forecasts/forecast_scheduler.log`, not interpolation. Fetch/snapshot/raw/normalized/link counts come from persisted timestamps; normalized insertion dates follow their owning snapshot. F/P/E = FISCAL_ESTIMATE / PRICE_TARGET / EARNINGS_HISTORY_REFERENCE. Links = AS_KNOWN / CURRENT_RECONCILED. Backup bytes are images actually created on that date, before collection.

| Date | DB after MiB | Fetches | New raw rows / body MiB | New snapshots F/P/E | New normalized rows F/P/E | Links AS/CR | New backup MiB |
|---|---:|---:|---:|---|---|---|---:|
| 2026-10-14 | 1,348.37 | 7,323 | 3,105 / 5.52 | 772/2307/6 | 70978/11535/24 | 9148/9140 | 1,263.29 |
| 2026-10-15 | 1,442.93 | 7,323 | 3,311 / 6.47 | 960/2332/6 | 88251/11660/24 | 9149/9141 | 1,348.37 |
| 2026-10-16 | not recorded | 0 | 0 / 0.00 | 0/0/0 | 0/0/0 | 0/0 | 0.00 |
| 2026-10-17 | 1,546.96 | 7,323 | 3,489 / 7.35 | 1135/2325/9 | 104374/11625/36 | 9153/9145 | 1,442.93 |
| 2026-10-18 | 1,594.43 | 7,323 | 335 / 1.00 | 176/68/2 | 16192/340/8 | 9153/9145 | 1,546.96 |
| 2026-10-19 | 1,634.72 | 7,323 | 70 / 0.24 | 44/25/1 | 4025/125/4 | 9153/9145 | 1,594.43 |
| 2026-10-20 | 1,712.84 | 7,323 | 2,974 / 4.82 | 629/2311/13 | 57845/11555/52 | 9153/9145 | 1,634.72 |
| 2026-10-21 | 1,785.50 | 7,323 | 2,863 / 4.27 | 518/2292/30 | 47541/11460/120 | 9148/9140 | 1,712.84 |
| 2026-10-22 | 1,858.23 | 7,323 | 2,850 / 4.33 | 536/2259/40 | 49174/11295/156 | 9155/9147 | 1,785.50 |
| 2026-10-23 | 1,932.16 | 7,323 | 2,924 / 4.46 | 546/2287/75 | 50209/11435/300 | 9154/9146 | 1,858.23 |
| 2026-10-24 | 1,996.66 | 7,323 | 2,656 / 3.45 | 363/2262/9 | 33327/11310/36 | 9154/9146 | 1,932.16 |
| 2026-10-25 | 2,049.87 | 7,323 | 548 / 1.64 | 289/75/8 | 26565/375/32 | 9154/9146 | 1,996.66 |
| 2026-10-26 | 2,092.32 | 7,323 | 169 / 0.49 | 85/69/6 | 7820/345/22 | 9154/9146 | 2,049.87 |

There is **no persisted October 16 run/fetch or backup**; its DB size is not recorded. This audit does not invent a missed-run cause or repair scheduling. The 12 observed full runs cover 13 calendar dates, so the historical calendar mean is **66,869,406 B/day**, while the per-observed-run mean is **72,441,856 B/run**. Future projections assume one full run/day rather than permanently assuming one missing day every 13 days.

Recent UTC weekdays averaged 69.98 MiB/run (8 runs), weekends 67.30 MiB/run (4 runs). Sunday/Monday averaged 45.86 MiB/run. These are observation-date descriptions, not exchange-calendar classifications: Saturday can reflect Friday market-price changes. Result-season fiscal activity is nonuniform.

The latest run still added **44,519,424 bytes** with only **69 PRICE_TARGET snapshots** and **85 fiscal snapshots**: repeated fetch-specific linking costs remain even on low-novelty days.

## 6. PRICE_TARGET currentPrice transitions

All **73,336 successful observations** were sorted by fetched_at_utc and fetch row order within provider/identity_key. There are **2,441 one-to-one ticker identities**, no symbol/identity handoff in this dataset. Initial observations (2,441) are baselines, leaving **70,895 comparable consecutive pairs**.

| Class | Count | % of comparable pairs |
|---|---:|---:|
| TARGET_VECTOR_CHANGED | 6,169 | 8.70% |
| CURRENT_PRICE_ONLY_CHANGED | 39,638 | 55.91% |
| OTHER_NON_TARGET_CHANGED | 0 | 0.00% |
| UNCHANGED_REUSE | 25,088 | 35.39% |

The target vector uses canonical states/values of mean/median/high/low; numeric text is compared as Decimal, preserving absent/null/zero distinctions. A current-only classification also requires currency/version and every other included field to match. Mixed current+other-field changes were checked separately and are **0**, so the four requested classes reconcile exactly. Of target-vector changes, **6,163 are numeric and 6 are availability/state-only**. Provider target changes still need corporate-action/unit QA before economic attribution to an analyst decision.

Current-only changes are **86.53% of changed transitions**. They inserted **38,250** new snapshots; 1,388 other current-only transitions reused older content. Transition counts therefore differ from avoidable distinct-snapshot counts. These current-only insertions account for roughly **112,079,026 bytes** of the PRICE_TARGET snapshot/normalized/index layer under proportional allocation; raw/fetch observations remain necessary.

| Date | Target vector | Current-only | Other | Reuse | Actual new snapshots | Hypothetical new consensus states |
|---|---:|---:|---:|---:|---:|---:|
| 2026-10-14 | 304 | 2,083 | 0 | 54 | 2,307 | 301 |
| 2026-10-15 | 309 | 2,089 | 0 | 43 | 2,332 | 304 |
| 2026-10-16 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2026-10-17 | 551 | 1,844 | 0 | 46 | 2,325 | 549 |
| 2026-10-18 | 68 | 0 | 0 | 2,373 | 68 | 65 |
| 2026-10-19 | 24 | 2 | 0 | 2,415 | 25 | 23 |
| 2026-10-20 | 387 | 1,995 | 0 | 59 | 2,311 | 379 |
| 2026-10-21 | 307 | 2,070 | 0 | 64 | 2,292 | 303 |
| 2026-10-22 | 295 | 2,068 | 0 | 78 | 2,259 | 293 |
| 2026-10-23 | 361 | 2,020 | 0 | 60 | 2,287 | 355 |
| 2026-10-24 | 256 | 2,118 | 0 | 67 | 2,262 | 250 |
| 2026-10-25 | 75 | 0 | 0 | 2,366 | 75 | 73 |
| 2026-10-26 | 68 | 1 | 0 | 2,372 | 69 | 66 |

## 7. Identity simulation without currentPrice

For every existing PRICE_TARGET snapshot, the original canonical SHA was recomputed and matched. The hypothetical JSON removes only `values.current`, preserving mean/median/high/low states and values, currency and the existing version marker. Distinct keys remain **(provider, identity_key, hypothetical_hash)**; equal numbers across companies are never merged. The V1 marker is retained in this simulation to isolate one variable; deployment would require a new version.

| Quantity | Actual | Hypothetical |
|---|---:|---:|
| PRICE_TARGET semantic snapshots | 46,860 | 8,539 |
| Normalized PRICE_TARGET rows | 234,300 (5/snapshot) | 34,156 (4/snapshot) |
| Distinct snapshot reduction | — | 38,321 / 81.78% |
| PRICE_TARGET canonical JSON bytes | 15,981,964 | 2,508,003 |
| Recent new snapshots/full run | 1,551 | 246.75 |

Recent snapshot-growth reduction is **1,304.25/run / 84.09%**. Full-history distinct reduction is slightly larger than current-only insertions because 71 target-change states also become reuses of earlier consensus content.

Retrospective storage estimate: snapshot-table reduction 60,948,294, snapshot-index reduction 10,075,430, normalized-table reduction 22,032,998, normalized-index reduction 21,413,204 bytes: **114,469,926 bytes / 5.22% of the DB**, approximately **3.88 MB/full run** less future growth at recent novelty rates. Estimates use exact SQLite record payload sizes (which reconcile to dbstat), shared-page payload allocation and index row shares; they are not a measured VACUUM result or a newly written compacted database.

A forward-only deployment has **zero immediate historical byte reclamation**: old snapshots/IDs remain immutable. New rule-version baselines and quote/compatibility metadata have their own small initial cost. Fetches, raw bodies, fiscal links and fiscal normalized fields are unchanged by this hypothesis.

**Contract answers:**

- OHLC supplies market-price history, but exact provider `currentPrice` need not equal a daily close: observation instant, session, currency, route and adjustment basis can differ. No OHLC store was opened and no exact equivalence is claimed. OHLC is not a replacement for the captured quote.
- The quote belongs in reproducible provider evidence. Every successful PRICE_TARGET fetch retains a raw reference today. All **47,454 distinct successful raw/snapshot bindings** were replayed through the existing parser and reproduced their original semantic content, covering all 73,336 successful observations.
- Raw-only retention of currentPrice is feasible only with a durable evidence/quote contract. Existing 30-day raw expiry plus explicit cleanup is incompatible with assuming raw remains forever; see §8.
- Existing target-event research uses only four target statistics (`STATS`) and both successful fetch statuses. Its changes/checkpoints are observation-based, rather than snapshot insertion based. Independent normalized-row samples and its pure `changed()` function agree. Preserved V1 history can reproduce existing results with the same pinned ancillary inputs/version; the full multi-store research export was not rerun. New V2 provenance IDs need version-aware readers and cannot be advertised as byte-identical old exports.
- The generic repository as-known API returns all five normalized V1 statistics, including current. An unversioned field removal would break that contract or expose a stale shared-snapshot quote. **Do not remove currentPrice under V1.** A forward-only versioned design must preserve per-fetch quote access and validate mixed-version readers.

## 8. Raw provider evidence

Bodies are uncompressed UTF-8 TEXT. `raw_hash` is their SHA-256 primary key; `INSERT OR IGNORE` already content-addresses exact byte duplicates globally. All 65,518 raw body hashes were verified. No duplicate body is stored under a second hash.

| Stored family | Raw rows | Body bytes | Mean / median / p95 B | In-memory per-row zlib6 bytes |
|---|---:|---:|---:|---:|
| EARNINGS_HISTORY_REFERENCE | 2,704 | 3,136,937 | 1,160.1 / 1,183 / 1,206 | 1,036,572 |
| FISCAL_ESTIMATE | 15,360 | 80,279,089 | 5,226.5 / 5,265 / 5,350 | 15,732,542 |
| PRICE_TARGET | 47,454 | 35,284,688 | 743.6 / 762 / 800 | 20,069,793 |

Overall mean/median/p95: **1,811.7 / 782 / 5,306 bytes**. There are **220,007 fetch raw references**, 65,518 distinct hashes and **154,489 reused references / 70.22%**. Without byte dedup the referenced bodies would total 507,145,574 bytes, versus 118,700,714 stored body bytes. Content addressing already avoids 388,444,860 body bytes before table/index overhead. Family labels describe the stored raw record's family; provider references and raw insertions are different counts.

Recent unique-body growth is **3,848,154 B/full run**, approximately **1,404,576,088 bytes/year** in bodies or **1,720,504,340 bytes/year** with today's raw table/index ratio. This assumes one run/day and preserving PIT evidence; seasonality can change novelty.

There are **0 expired rows today**, but **all rows have a 30-day retain_until**. Earliest expiry is **2026-10-27T16:27:26.679445Z / October 27 18:27 Helsinki**. INSERT OR IGNORE does not renew that first-seen expiry on reuse. `cleanup_raw_evidence(apply=True)` explicitly nulls fetch/snapshot raw references and deletes expired bodies. It is a manual CLI, not called by the inspected daily service. This deletion policy is a material conflict with indefinite non-rebuildable provider evidence; do not casually invoke it or make V2 rely on it. A durable lossless raw archive/reference policy must be qualified first. No raw retention setting or body was changed in this task.

Per-row lossless compression reduced 118,700,714 body bytes to **36,838,907 bytes** in memory. That is a smaller opportunity than backup compression and needs a versioned decoder/checksum/restore contract. Deleting raw is not recommended.

## 9. Fetch-history cost

`forecast_fetch`: **220,308 rows**, **150,646,784 table bytes + 52,871,168 index bytes = 203,517,952 bytes / 9.28%**. Fiscal identity resolution adds **68,472,832 bytes**; fiscal links add **923,713,536 bytes**. Total fetch-specific fetch/identity/link storage is **1,195,704,320 bytes / 54.50%**. These categories overlap the separately reported link footprint and must not be added twice.

Using current average physical costs and recent insertion counts, a full run costs approximately **6,764,902 B fetch**, **2,276,025 B identity**, **30,743,068 B links**, together **39,783,995 B**: **1.112 GiB/30 runs** or **13.524 GiB/365 runs**, before new raw/snapshots/normalization.

Unchanged successful fetches reuse snapshot/normalized rows but are not just cheap references. There are **53,724 unchanged fiscal fetches** with **213,810 AS_KNOWN links**, and 53,668 with **213,586 CURRENT_RECONCILED links**, plus their fetch/identity records. Identity resolution exists once per fiscal attempt, including snapshotless outcomes. Observation clocks and knowledge evidence are PIT facts; dropping unchanged fetches would remove evidence of availability and the exact observed sequence.

## 10. Fiscal-link history cost and rebuildability

| Mode | Rows | Exact record-payload bytes | evidence_json bytes | Table + index bytes, estimated split |
|---|---:|---:|---:|---:|
| AS_KNOWN | 274,993 | 330,021,492 | 215,979,876 | 449,064,041 |
| CURRENT_RECONCILED | 274,753 | 353,343,187 | 231,306,848 | 474,649,495 |

Combined: **549,746 rows / 923,713,536 allocated object bytes**. There are 274,753 distinct CURRENT_RECONCILED fetch/occurrence/rule groups and exactly one row per such group today; no runaway repeated reconciliation versions were found.

All **274,753** current rows pair with their AS_KNOWN inputs. **100% have identical target/status/canonical-quarter fields** and **100% have identical base evidence after removing `current_reconciliation`**. The cloned base alone is **215,869,356 bytes**. Additional current-reconciliation JSON values occupy **11,871,176 bytes**; separate mode-specific reasons, row IDs/hashes, as-of/link clocks and source binding are also material.

AS_KNOWN records the accepted interpretation at fetch knowledge time and is mandatory PIT evidence. CURRENT_RECONCILED provides a later canonical view. Most of its present representation is duplicate/reconstructible from its retained AS_KNOWN base, but the **entire historical row cannot be regenerated from today's mutable canonical state alone**. No canonical history requalification was attempted. Deleting the mode would discard its knowledge clock/overlay/history contract.

A future lossless AS_KNOWN-reference plus retained current overlay can target roughly the 216 MB duplicated text, less reference/index costs, while reconstructing exact existing row/JSON semantics. This is a meaningful production-storage candidate, not permission to delete CURRENT_RECONCILED. It requires an owned, versioned storage/read/restore contract and exact historical reconstruction tests. Full row-level contexts and reasons must survive.

## 11. Normalized field storage

| Table | Rows | Semantic parents | Rows/snapshot | Table bytes | Index bytes | DB % including indexes |
|---|---:|---:|---:|---:|---:|---:|
| `forecast_estimate` | 1,405,921 | 15,307 | 91.848 | 280,518,656 | 293,257,216 | 26.15% |
| `forecast_price_target` | 234,300 | 46,860 | 5.000 | 25,812,992 | 25,067,520 | 2.32% |
| `forecast_earnings_history_reference` | 10,647 | 2,703 | 3.939 | 2,072,576 | 991,232 | 0.14% |

Normalized fields are inserted **once per new semantic snapshot**, not repeatedly per fetch. Fiscal snapshots hold roughly four horizon occurrences × 23 fields, with mixed/missing cases preserved explicitly; the measured average is 91.848 fields/snapshot. PRICE_TARGET has exactly five rows per snapshot, including current. Earnings history averages 3.939 reference rows/snapshot.

Canonical JSON plus normalized tables intentionally hold two query representations. For example fiscal canonical JSON is 100,206,614 bytes while fiscal normalized table/index storage is 573,775,872 bytes. Rebuilding normalization from immutable canonical JSON would require the exact retained contract version/field-state/path logic; this audit does not remove either representation or introduce a schema redesign.

Another measured representation cost is **83,103,021 bytes of repeated diagnostic/schema-drift JSON text**. Only **123,665 bytes** are needed to spell the distinct exact bodies once, before references/indexes. PRICE_TARGET alone repeats 49,448,222 fetch diagnostic bytes and 30,869,926 snapshot drift bytes. Lossless shared dictionaries or versioned compression can preserve every distinct warning; deleting all diagnostics would not. This opportunity is separate from price semantic identity.

## 12. Freelist, page utilization and VACUUM

Freelist: **0 pages / 0 bytes / 0.00%**. dbstat reports **212,724,755 bytes / 9.70%** unused inside allocated b-tree pages. This is reusable page slack, not a freelist and not automatically an equal physical shrink. Table/index cells, headers and overflow counts are in `page_utilization.json`; logical b-tree page distribution does not prove physical filesystem extent fragmentation.

Exact accounting is **1,609,195,520 table + 584,761,344 index + 4,096 reserved lock-byte-page + 0 freelist = 2,193,960,960 bytes**. SQLite dbstat intentionally omits the lock page ([dbstat documentation](https://www.sqlite.org/dbstat.html), [file-format lock page](https://www.sqlite.org/fileformat.html#the_lock_byte_page)).

VACUUM has **zero freelist bytes to recover**. Repacking may recover part of the ~203 MiB gross page slack; the entire 9.70% is only a loose ceiling, not a measured reclaim estimate. Actual output size needs a separately authorized isolated test. Even that ceiling is about three recent runs of growth and does not solve append-only evidence or accumulating full images. Production VACUUM is not recommended as the first optimization and was not run.

## 13. Forecast backup footprint

Directory: `/home/kalle/projects/rawcandle/backups/forecasts/` only. **35 DB images + 35 manifests**, all regular single-link files, mode 0444. Images total **33,413,648,384 apparent / 33,413,689,344 filesystem allocated bytes**; manifests total **33,429 apparent bytes**. Oldest: `forecast_20260927T174304257344Z.db` (598,016 bytes); newest: `forecast_20261026T121149569963Z.db` (2,149,441,536 bytes). The newest is a pre-run point, explaining why it is smaller than the live post-run DB.

`create_backup` uses SQLite's online backup API, verifies core counts/schema/integrity, publishes a full `.db` and SHA-bound manifest, then makes both read-only. These are **full physical copies**, not deltas. Every daily run adds another copy of all preceding collected history. All file sizes/manifests were inventoried; not every old image was needlessly rehashed. The newest complete image was freshly SHA-verified by the compression round trip, and the following exact duplicates were freshly rehashed:

- `forecast_20260927T174304257344Z.db` = `forecast_20260927T185204266430Z.db`; one extra copy 598,016 bytes, freshly SHA-matched.
- `forecast_20260927T204846170498Z.db` = `forecast_20260928T043011800370Z.db`; one extra copy 183,111,680 bytes, freshly SHA-matched.

Only **183,709,696 bytes / 0.55%** are excess exact copies. The other distinct daily byte states share much data but contain real additional observations/knowledge history. They are not declared equivalent or arbitrarily deleted.

| UTC date | Images created | Per-image range MiB | Total image MiB |
|---|---:|---:|---:|
| 2026-09-27 | 6 | 0.57–174.63 | 359.05 |
| 2026-09-28 | 2 | 174.63–212.68 | 387.30 |
| 2026-09-29 | 1 | 258.55–258.55 | 258.55 |
| 2026-09-30 | 1 | 319.61–319.61 | 319.61 |
| 2026-10-01 | 1 | 382.70–382.70 | 382.70 |
| 2026-10-02 | 1 | 450.31–450.31 | 450.31 |
| 2026-10-03 | 1 | 510.44–510.44 | 510.44 |
| 2026-10-04 | 1 | 576.92–576.92 | 576.92 |
| 2026-10-05 | 1 | 654.84–654.84 | 654.84 |
| 2026-10-06 | 1 | 737.66–737.66 | 737.66 |
| 2026-10-07 | 1 | 810.10–810.10 | 810.10 |
| 2026-10-08 | 1 | 882.69–882.69 | 882.69 |
| 2026-10-09 | 1 | 956.74–956.74 | 956.74 |
| 2026-10-10 | 1 | 1,024.03–1,024.03 | 1,024.03 |
| 2026-10-11 | 1 | 1,091.68–1,091.68 | 1,091.68 |
| 2026-10-12 | 1 | 1,129.53–1,129.53 | 1,129.53 |
| 2026-10-13 | 1 | 1,167.65–1,167.65 | 1,167.65 |
| 2026-10-14 | 1 | 1,263.29–1,263.29 | 1,263.29 |
| 2026-10-15 | 1 | 1,348.37–1,348.37 | 1,348.37 |
| 2026-10-17 | 1 | 1,442.93–1,442.93 | 1,442.93 |
| 2026-10-18 | 1 | 1,546.96–1,546.96 | 1,546.96 |
| 2026-10-19 | 1 | 1,594.43–1,594.43 | 1,594.43 |
| 2026-10-20 | 1 | 1,634.72–1,634.72 | 1,634.72 |
| 2026-10-21 | 1 | 1,712.84–1,712.84 | 1,712.84 |
| 2026-10-22 | 1 | 1,785.50–1,785.50 | 1,785.50 |
| 2026-10-23 | 1 | 1,858.23–1,858.23 | 1,858.23 |
| 2026-10-24 | 1 | 1,932.16–1,932.16 | 1,932.16 |
| 2026-10-25 | 1 | 1,996.66–1,996.66 | 1,996.66 |
| 2026-10-26 | 1 | 2,049.87–2,049.87 | 2,049.87 |

**Current policy:** `backup_retention` implements newest protection plus all valid images ≤14 days, one per ISO week through eight weeks, and one per month through 366 days. Its CLI exists, but neither the inspected daily code nor effective systemd unit invokes it. The 21:00 generic temp cleanup targets `temp/`, not this backup directory. Thus the observed active daily path accumulates full images. Manual outside-scope invocation history is not fabricated.

The manual retention CLI also lacks the daily writer-lock wrapper used by raw cleanup/restore; the retention function checks hash/schema/counts/integrity but has no explicit open-user/current rollback-obligation qualification. **Do not simply schedule `--apply`.** Any rollout must coordinate with the existing forecast owner, preserve active recovery points and validate that retiring images do not uniquely preserve PIT evidence.

Future options, under the same linear growth model:

| Option | Storage evidence / estimate | Recovery / complexity |
|---|---|---|
| Last 14 daily images | +365d about 366.277 GiB versus 5,258.733 GiB unpruned | Simple; 14-image whole-store rollback window. Full PIT payload must survive in current qualified point. |
| Existing 14d / 8w / 366d tiers | Today models 17 images / 23.737 GiB; hypothetical saving 7.382 GiB. +365d 33 points / 675.824 GiB | Preserves coarse older rollback milestones; owner/coverage gates first; not an executable deletion list. |
| Milestones only after a period | Illustrative day-90/180/270/360 points plus day-365 latest: ~95.22 GiB at +365d | Less fine-grained older rollback. Keep current PIT image and explicitly approved incidents; no implicit historical purge. |
| Filesystem compression | Current root is ext4 with no configured transparent compression; no supported transparent option demonstrated here | Do not change filesystem or VHDX flags for this audit; storage savings unmeasured. |
| Lossless compressed SQLite backup archive | Newest image **2,149,441,536 → 325,264,779 bytes**, **84.87%** reduction, gzip6; exact restored-stream SHA matches manifest | Measured in memory with no archive/database copy. Existing validator/retention understands `.db`, not compressed archives. Needs explicit archive/decoder/manifest/restore ownership before replacing an image. |
| Hardlinks / clever shared inodes | Exact duplicates save only 0.55%; hardlinks would share mutable inode/permission state | Not recommended. Keep independently owned immutable images or separately qualified archive payloads. |
| Durable raw PIT DB plus fewer full points | Removes the daily whole-file multiplier while retaining actual observation history | Preferred simple direction if all accepted history/raw/links remain covered; 30-day raw cleanup must not make older backups the sole evidence. |

Applying the measured gzip ratio to all current images gives a **proxy ~4.709 GiB**, not a measured archive of every image. Tiering plus that ratio models **102.269 GiB** backups at +365d. Compression varies with future content. Restore verifies decompressed original SHA, schema/core counts and lineage before any recovery use; original uncompressed points cannot expire merely because compression returned success.

## 14. Future growth estimates

Projection basis: **D0=2,193,960,960, B0=33,413,648,384, g=72,441,856 bytes/day**, one full run and one pre-write backup/day; no deletes, automatic pruning or semantic changes. g is the observed full-run mean from October 14–26, not a fit to approximate checkpoint dates. The current raw-expiry marker does not itself purge rows.

- Production: `D(n)=D0+n*g` (linear).
- Additional full backups: `n*D0 + g*n*(n-1)/2`; total `B(n)=B0+...`. Individual DB growth is linear, but accumulating growing full copies makes backup footprint **quadratic**.
- Combined: `D(n)+B(n)`; manifests and filesystem allocation overhead are small and omitted from the future model.

| Horizon | Production bytes / GiB | Backups total bytes / GiB | Combined bytes / GiB |
|---|---:|---:|---:|
| +30 days | 4,367,216,640 / 4.067 | 130,744,684,544 / 121.765 | 135,111,901,184 / 125.833 |
| +90 days | 8,713,728,000 / 8.115 | 520,999,768,064 / 485.219 | 529,713,496,064 / 493.334 |
| +365 days | 28,635,238,400 / 26.669 | 5,646,521,892,864 / 5,258.733 | 5,675,157,131,264 / 5,285.402 |

At today's constant DB size with no further growth, backup totals would still be **92.417 / 215.015 / 776.918 GiB** at +30/+90/+365 days. That lower scenario deliberately isolates backup multiplication from production growth.

Seasonal target/fiscal updates, holiday/market timing, new universe members, provider field changes and future failures can change both novelty and bytes/run. The 13-day calendar average including the unobserved October 16 is lower; it is a sensitivity, not a justification to assume daily collection will remain missing. No new acquisition or scheduler behavior was introduced to produce a projection.

## 15. Ranked optimization candidates

Ranking considers storage, PIT risk, complexity and reversibility, not snapshot count alone. All are proposals for separate authorization.

| Rank / candidate | Category | Measured value | PIT risk / complexity / reversibility |
|---|---|---|---|
| **1. Owner-qualified backup retention** | **SAFE / HIGH VALUE**, after recovery gates | Current tier-model saving 7.93 GB; +365d 725.66 GB versus 5,646.52 GB unpruned | Low logical-history risk only with complete retained PIT coverage and released image obligations; medium owner integration; deletion physically irreversible. |
| **2. Lossless backup compression** | **SAFE / HIGH VALUE**, after archive restore qualification | Fresh newest-image gzip round trip saves **84.87%** | Byte-exact input proof; restore/format integration medium; reversible while original image retained. |
| **3. Redundant-index cleanup qualification** | **SAFE / MEDIUM VALUE** | Two exact duplicate keys **13.03 MB**; another **109.88 MB** prefix candidate needs workload proof | No intended data/constraint loss; low–medium implementation/performance risk; indexes rebuildable. Keep automatic constraints. |
| 4. Factor CURRENT_RECONCILED base evidence | REQUIRES CONTRACT CHANGE | **215.87 MB** exact duplicated base JSON, before new references | Preserve every clock/reason/overlay/ID and exact expansion; medium–high storage/reader migration complexity; do not drop the mode. |
| 5. Versioned PRICE_TARGET identity excluding currentPrice | REQUIRES CONTRACT CHANGE | **81.78%** fewer distinct PT states but **5.22%** DB counterfactual saving | V1 API current value and raw expiry require compatibility work; preserve all old IDs/history; forward-only switch can be rolled back by rule version. |
| 6. Compact repeated fetch/drift metadata | SAFE / MEDIUM VALUE, with lossless reader versioning | **83.10 MB** text versus **0.124 MB** distinct bodies before references | Keep exact warning/evidence semantics; dictionary/compression has schema/decoder integration cost; do not delete diagnostics wholesale. |
| 7. Raw evidence compression/dedup | SAFE / MEDIUM VALUE only if exact bytes/refs survive | Per-row compressed bodies ~36.84 MB versus 118.70 MB; exact-byte dedup already exists | Irreplaceable provider layer; checksummed decoder required; no casually expiring PIT evidence. |
| 8. VACUUM as a growth fix | NOT RECOMMENDED first | **0 freelist bytes**; 9.70% gross b-tree slack is only a ceiling | One-off repack does not stop row growth; future isolated estimate first; no production VACUUM now. |
| 9. Remove old/unchanged fetch history | NOT RECOMMENDED | Large bytes but destroys observed timing/availability/link context | PIT sequence and audit loss; not rebuildable from sparse revisions. |
| 10. Remove old snapshots | NOT RECOMMENDED | Destroys historic provider states and provenance | Non-rebuildable history; proposed semantic rule does not authorize deleting V1 states. |

## 16. Recommended currentPrice architecture

The safe target is a **new consensus contract**, rather than changing V1 equality in place:

1. Keep raw provider bodies, currentPrice states/values, exact hashes and acquisition clock under durable PIT retention, or an explicitly qualified immutable archive with stable references.
2. New PRICE_TARGET semantic snapshots contain mean/median/high/low, currency and other explicitly contract-approved consensus fields. Existing V1 has no semantic analyst-count field: `numberOfAnalystOpinions` must not be silently invented. Exclude market-driven currentPrice only in the new rule version.
3. Each fetch still records provider/identity/request/fetch times, status and semantic/raw references. A quote accessor resolves **that fetch's** raw currentPrice, or a lossless fetch-scoped quote projection if required for query performance. It must not return the first snapshot's quote on subsequent reuse.
4. Keep target normalization snapshot-scoped and target-only in V2. Preserve states, currency and identity; support V1 five-row and V2 four-row records through version-aware readers.
5. Research continues to iterate observations, classify only actual target-vector changes and retain fetch/snapshot provenance. Success counters will shift from CHANGED to UNCHANGED, but observed-day coverage and raw acquisition do not change. Test those reporting semantics explicitly.

This design preserves target revision history without semantic novelty on price movement. The audit proves raw/state recoverability and current target-reader behavior; it does **not** qualify an unversioned removal or claim every consumer already supports V2. The as-known quote API, raw expiry, mixed-version dispatch, backups and export lineage need explicit compatibility tests before implementation.

## 17. Migration / existing history

**Historical rewrite recommended: NO.** Retain all existing snapshots, canonical JSON, normalized records, raw references, fetches, AS_KNOWN/current overlays and public IDs. Introduce a forward-only PRICE_TARGET consensus-rule version when separately approved. Because canonical JSON contains contractVersion, its hash namespace can distinguish future V2 states while the existing public identity remains unchanged.

A new version can coexist with V1, but reader/normalizer/manifest support must be deliberate. Initial V2 consensus baselines may add rows; reduced future novelty does not shrink old history. Existing V1 research remains reproducible with pinned ancillary inputs and preserved IDs. Migration must not reinterpret old current-only snapshots as analyst revisions or replace captured quotes with later OHLC/provider downloads.

## 18. Exact next step, evidence and decision

**Next bounded task to authorize:** qualify an owner-aware forecast-backup lifecycle using the existing forecast daily lock and existing tier parameters, with explicit latest accepted recovery/active-user/PIT-coverage gates and crash/idempotence tests; document an enforceable durable raw-evidence invariant before any older point is retired. Then qualify lossless compressed-archive restore/manifest support on isolated fixtures and an existing immutable image before replacing originals. No live `--apply` is authorized by this report. Keep semantic V2 as a separate versioned consumer/retention contract task, not a prerequisite for stopping the full-image multiplier.

Runtime evidence: `baseline_before.json`, `health.json`, `schema.json`, `objects.json`, `indexes.json`, `page_reconciliation.json`, `daily.json`, `price_target.json`, `raw_evidence.json`, `payload_attribution.json`, `storage_estimates.json`, `link_history.json`, `reconciled_comparison.json`, `diagnostic_repetition.json`, `index_role_checks.json`, `backup_inventory.json`, `duplicate_backup_proof.json`, `backup_compression.json`, `models.json`, `classification_validation.json` and `acceptance.json` under the ignored audit directory. Only compact aggregate evidence/samples are retained; no full DB/provider dump or replacement backup was created.

Focused validation passed: page/file/CSV sums including lock page; all table counts; original canonical hashes for 46,860 PT states; deterministic hypothetical hashes; normalized transition samples and current research helper; 47,454 successful raw/snapshot bindings; exact duplicate-image hashes; gzip stream round-trip SHA; backup byte sums; all 70 backup-file identities; production pre/post SHA. Full pytest: **NO**. Provider calls **0**, production/backup mutations **0**, Fundamentals/OHLC opens **0**, scheduler changes **0**. Original unrelated worktree entries remain preserved. Local documentation/CSV commit and final status are recorded in `commit_receipt.json`; push **NO**.

**FORECAST_STORAGE_OPTIMIZATION_READY**
