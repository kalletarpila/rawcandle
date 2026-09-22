# Phase 13G.3.26: Production-shaped market bundle validation

## Outcome

Closure classification: `PRODUCTION_SHAPED_CLOSURE_PROVEN`.

The compact market bundle was built twice from the local production-shaped
`data/osakedata.db`, bound to `data/fundamentals_v4.db` at calculation date
2026-09-22, and exercised through the existing source-facing readers. Both
bundles were deleted after validation. No Fundamentals workflow ran and no
runtime caller was changed.

`No Refresh, Add Tickers, Production, Test-on-copies, or other Admin workflow was migrated to the compact market bundle in Phase 13G.3.26.`

`A Full Workflow end-to-end acceptance test remains mandatory after Refresh Test and Refresh Production share the new source-consistency contract.`

## Environment and source evidence

The benchmark ran locally on 2026-09-22 using the current production-shaped
databases. It did not create a full market or taxonomy copy.

| Evidence | Before | After |
|---|---:|---:|
| `osakedata.db` size | 1,990,488,064 bytes | 1,990,488,064 bytes |
| inode | 88025 | 88025 |
| mtime | 2026-09-20 22:43:04.386758830 +0300 | unchanged |
| SHA-256 | `42c9ca45e1726e6d0f18c4236e72c49a9ca9e26f468c0a8f370532602f97d279` | same |
| journal mode | `delete` | `delete` |
| `quick_check` | `ok` | `ok` |

The source contains 8,796,437 price rows for 4,914 physical ticker strings,
5,068 classification rows, and 6,405 split rows. No source file was replaced or
modified. The scheduler had no matching running process before or after the
benchmark and its state was not changed.

## Foundation defect found and fixed

Production shape exposed two foundation assumptions before caller migration.

First, 8,489 V4 TTM rows have a null `ttm_source_available_date`. They are not
unresolved securities: all 89,872 TTM rows resolve both security and ticker. The
real `load_canonical_source()` result proved this exact partition:

| Reader state | TTM rows |
|---|---:|
| `HAS_CUTOFF` | 81,383 |
| `NO_CUTOFF` | 8,489 |
| Total | 89,872 |

All 8,489 `NO_CUTOFF` rows had empty price bars. The RV source query uses
`ttm_source_available_date <= as_of`, so none of those rows enters RV. The bundle
now records `NO_CUTOFF` explicitly, including a deterministic sorted TTM-ID
fingerprint. It does not invent a date, ticker, or price requirement.

Second, the original foundation issued `UPPER(osake)=?` once per recent ticker.
SQLite planned each query as a full table scan. The corrected contract discovers
physical ticker spellings once with `SELECT DISTINCT osake`, then performs all
price-window reads with exact ticker predicates. Conflicting OHLC values for the
same normalized ticker/date fail closed.

Focused fixture regressions cover both fixes. No runtime caller was modified.

## Query and index evidence

`EXPLAIN QUERY PLAN` after the fix reported:

```text
SELECT DISTINCT osake ...
SEARCH osakedata USING COVERING INDEX idx_osake_pvm (osake>?)

SELECT ... WHERE osake=? AND pvm<=? ORDER BY pvm DESC LIMIT 32
SEARCH osakedata USING INDEX idx_osake_pvm (osake=? AND pvm<?)
```

Filing-date requirements are cached by exact `(ticker, cutoff)` and use the same
exact ticker/date index. There were 89,872 TTM rows and 81,382 distinct non-null
ticker/cutoff pairs. The remaining query count is linear in canonical
requirements, not ticker count multiplied by all market rows.

## Actual closure

| Requirement or result | Count |
|---|---:|
| V4 TTM requirements | 89,872 |
| TTM requirements with cutoff | 81,383 |
| `NO_CUTOFF` | 8,489 |
| Recent-window tickers | 2,523 |
| Filing prices found | 75,983 |
| No matching valid filing price | 5,400 |
| Selected unique `osakedata` rows | 157,305 |
| `ticker_meta` rows | 5,068 |
| `splits_data` rows | 6,405 |
| Validation sample ticker | `A` |

The 5,400 cutoff-bearing no-price rows were classified independently: 5,376
cutoffs predate the exact ticker's first market row, and 24 have only invalid OHLC
on or before the cutoff. This is accepted reader absence semantics, not missing
bundle coverage. The production reader and compact reader produced identical V2
valuation source rows and fingerprints across all 89,872 TTM rows.

Coverage status counts and identity fingerprints in the production-shaped
manifest were:

| Status | Count | TTM-ID fingerprint |
|---|---:|---|
| `PRICE_FOUND` | 75,983 | `f92af1df2b633a0b4be714031cef51a950a690406618db0ec60ea2e9fdf16ab9` |
| `NO_MATCHING_VALID_PRICE` | 5,400 | `6539c03be4f79fdf9a0835f770788cd79350e0657654c1ee1e743cbc2b65e859` |
| `NO_CUTOFF` | 8,489 | `aadc87fcb4620d0d0f51f1063fe38c8d4f0eb4761bd34a8e5ba962996f6916cf` |
| `NO_TICKER` | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |

## Size and timing

| Measurement | Result |
|---|---:|
| Market source | 1,990,488,064 bytes / 1.854 GiB |
| Compact market DB | 14,508,032 bytes / 13.836 MiB |
| Manifest | 5,021 bytes |
| First canonical + market projection | 1.542 s |
| Drift projection + compact write | 1.969 s |
| Publish + internal validation | 0.465 s |
| Total first build | 3.976 s |
| Separate validation | 0.171 s |
| Repeat build | 3.925 s |

The compact DB is 99.271% smaller than `osakedata.db`. The semantic fingerprint
was `bfb74e478fd8fc3ba17577cac5dcf8da74006f29efd09fc9d1bdd99305e5683c`.
The repeat build produced the same semantic fingerprint, physical SHA-256
`527d5eafb97e1a5ef51db83e66cbfd68ad026a95c3ec91bfa5e1212b1d59ef3f`,
and row counts.

Because taxonomy remains a full-copy runtime dependency, replacing only the
market copy would reduce the old 12.171 GiB combined market+taxonomy footprint to
approximately 10.331 GiB, a 15.120% combined reduction. A larger taxonomy saving
must not be claimed until direct locked reads are independently authorized.

## Reader compatibility

The live market path and compact market path produced semantically equal results:

| Existing entry point | Result | Combined live + compact time |
|---|---|---:|
| V2 canonical valuation source | PASS | 93.573 s |
| RP/peer classification source | PASS | 0.019 s |
| V2 split-event loader | PASS | 0.011 s |
| Full RV source loader, 2,443 inputs | PASS | 7.034 s |
| Rebuild/source-state reader | PASS | 0.452 s |
| V2 snapshot assembler for validation sample `A` | PASS | 1.791 s |

The long V2 parity time is the cost of running the existing complete source
reader twice, not bundle extraction. No analysis or canonical output was written.

## Taxonomy and remaining risk

No taxonomy rows or taxonomy DB were packaged. The bundle manifest still names
`FULL_SQLITE_BACKUP` as the runtime-authorized taxonomy policy. A direct locked
read remains a candidate with `runtime_authorized=false`; proving complete writer
lock coverage is deferred.

The main remaining risk is caller integration, not extraction performance. Refresh
Test and Refresh Production must be migrated together, bind equivalent manifests,
and reject stale source state before candidate construction. The later Full
Workflow acceptance must prove that publication, postflight, recovery, cleanup,
and retry semantics all consume one bound source generation.

All phase-owned benchmark bundles and manifests were removed. Phase-owned large
files remaining: 0.
