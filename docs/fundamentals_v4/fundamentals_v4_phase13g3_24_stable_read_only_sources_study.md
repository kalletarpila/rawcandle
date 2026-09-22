# Phase 13G.3.24: Stable read-only source architecture study

## Scope and conclusion

This study covers the two inputs that Fundamentals reads but never publishes or restores:

- `data/osakedata.db` (`market`)
- `data/analysis.db` (`taxonomy`)

It does not change the atomic provider + canonical + analysis publication contract. The recommended design is a versioned, purpose-built **immutable read-only source bundle** containing only the semantic rows consumed by a full V2 rebuild. The current full SQLite online backups remain the fail-closed fallback until source closure and parity have been proven.

No runtime behavior was changed in this phase.

## Current architecture

### Role separation

The publication roles are `fundamentals_provider.db`, `fundamentals_v4.db`, and `fundamentals_analysis.db`. Their candidates, rollback backups, journal transitions, atomic replacements, and recovery form one independent three-database contract.

The read-only roles are `osakedata.db` and `analysis.db`. Fundamentals does not publish or restore them. They provide current price/classification and active taxonomy inputs to V2, RP V2, RV, and validation.

### Where copies are made

`batch_add_tickers.create_copy_lane()` calls SQLite `online_backup()` for all five roles in `ROLE_ORDER`. Add Tickers Preview and Test use the copied paths. Provider, canonical, and analysis copies are writable candidate state; market and taxonomy are immutable input snapshots. The lane is removed at terminal cleanup unless the explicit test-only `keep_copies` option retains it.

Refresh Test calls `prepare_full_v2_read_only_copies()` after copying provider and canonical candidates. The helper copies `market` and `taxonomy`, and `run_full_v2_downstream()` receives those copies.

Refresh Production uses the same helper before candidate construction. Candidate validation also rereads the same copies. The terminal `_cleanup_candidate_lane()` removes the complete lane. An incomplete publication journal conservatively retains the lane until recovery; terminal recovery removes the entire run-owned lane, including market and taxonomy copies.

Add Tickers Production currently differs: `production_transaction.run_transaction()` holds the Fundamentals Production lock and scheduler lock, but passes live market and taxonomy paths to `rebuild_v2_analysis()`. It uses source rechecks rather than immutable copies. A later change must remove this Test/Production semantic difference.

### Why copies exist

SQLite online backup provides a valid, internally consistent snapshot of each database even if that database has an active writer. Once created, every path-based reader in the rebuild sees the same immutable file generation.

This matters because the current rebuild does not use one source session. `phase10b.calculate()`, `load_relative_valuation_source()`, `validate_rebuild()`, taxonomy loaders, snapshot readers, and their helpers open multiple independent connections at different times. Direct live reads could therefore combine generations.

The read-only copies provide:

- stable per-database read semantics across all connections;
- isolation from concurrent source writers after copy completion;
- a path-based source that works with current reader APIs;
- durable copy manifests and candidate lineage.

They do not provide rollback or recovery capability. They are not journal publication roles and must never be restored. They also do not create a cross-database atomic snapshot: market and taxonomy are copied sequentially.

### Data actually consumed

The market source supplies:

- `ticker_meta`: ticker, market, sector, and industry;
- `osakedata`: the latest valid OHLC row on or before each TTM availability date;
- up to 32 recent OHLC rows per relevant ticker on or before the calculation date;
- a small amount of sample-reader/source-state validation data.

The taxonomy source supplies the active taxonomy graph from:

- `ec_taxonomy_version`;
- `ec_ecosystem`;
- `ec_entity`;
- `ec_membership`.

Most of `analysis.db` is unrelated to the Fundamentals taxonomy dependency.

## Actual consistency requirement

### Required guarantee

One rebuild must use one immutable semantic generation of each read-only source. Every calculation and post-build validation in that run must read the same source bundle. The exact bundle content and semantic fingerprints must be persisted in candidate and run evidence.

Test and Production must use equivalent source selection and fingerprint rules. Production may build a fresh bundle, but its relevant semantic fingerprints must equal the successful bound Test fingerprints. A mismatch makes the Test stale and stops Production before publication.

Market and taxonomy do not currently share a generation ID, transaction, foreign key, watermark, or writer transaction. They are logically independent inputs. The rebuild needs one stable generation of each, but there is no code-level requirement that both snapshots represent the same wall-clock instant.

### Why before/after file checks are insufficient alone

The current `database_fingerprint()` hashes schema and row counts, not row values. Size/mtime can detect many changes but is not semantic authority. Hashing only the main SQLite file is unsafe as a general WAL-aware content contract. Even strong before/after hashes would detect drift only after calculations that may already have combined different generations through separate connections. A source can also change and change back between checks.

Before/after evidence is useful as an additional anomaly detector, but it cannot replace an immutable calculation source.

### SQLite transactions and connection boundaries

A read transaction can provide a stable snapshot for one SQLite database and one connection. The current path-based APIs repeatedly open their own connections, so holding one transaction elsewhere does not stabilize those readers. Refactoring every reader to accept shared connections would be broad and brittle, and connections cannot be passed safely through future subprocess boundaries.

Long-lived snapshots also have operational costs. Runtime evidence shows:

- `osakedata.db`: `journal_mode=delete`; a long reader may delay writers or produce `SQLITE_BUSY` behavior;
- `analysis.db`: `journal_mode=wal`; a long reader allows writes but can prevent checkpoint progress and grow the WAL.

Short transactions used only to build a small immutable bundle avoid holding either condition for the full rebuild.

### Concurrent writers and locks

The scheduler uses a kernel scheduler lock and can write both price/derived state. Fundamentals Production acquires that scheduler lock. Fundamentals Test does not.

The separate taxonomy program has its own taxonomy operation lock and scheduler guard. That lock is not the same kernel lock as the Fundamentals Production lock. Therefore the current locks do not prove that all writers to both sources are excluded.

Expanding one shared lock to every present and future writer would be possible, but correctness would depend on universal writer participation and a long rebuild would block operational updates. Source snapshot correctness should not depend on that assumption.

## Options comparison

| Option | Correctness | Writer behavior | Disk/runtime | Complexity and portability | Decision |
|---|---|---|---|---|---|
| A. Full SQLite copies | Strong immutable per-DB snapshots; no cross-DB atomicity | Online backup tolerates writers | About 12.17 GiB written per source snapshot | Simple and portable, but expensive | Safe baseline and fallback |
| B. Direct reads + fingerprints | Cannot prevent mixed generations across current connections | Detects some drift after the fact | Minimal disk; repeated hashing can be expensive | Simple-looking but weaker | Reject as primary design |
| C. Long-lived read snapshots | Strong only if every reader shares the transaction | DELETE readers can block; WAL can grow | Minimal disk | Requires broad connection/API refactor; poor subprocess boundary | Reject for current architecture |
| D. Shared writer coordination | Strong if every writer obeys one lock | Blocks writers for the complete rebuild | Minimal disk | Existing locks are incomplete and distinct | Keep as defense in depth, not source authority |
| E. Reflink/COW | Potentially fast full snapshots | Still needs a SQLite-consistent snapshot boundary | Low physical blocks when supported | Filesystem-dependent and unsafe to assume with live WAL state | Optional future accelerator only |
| F. Purpose-built immutable source bundle | Strong immutable semantic input with exact lineage | Only short extraction transactions | Expected tens to low hundreds of MiB | Moderate, bounded implementation; portable SQLite | **Recommended** |

## Recommended architecture

Introduce a `StableReadOnlySourceBundle` abstraction shared by Add Tickers, Refresh Fundamentals, Sector/Industry, and Taxonomy Administration.

### Bundle construction

1. Bind the request to the canonical candidate fingerprint, calculation date, source-contract version, and requested source roles.
2. Open a short read transaction on one live source at a time and force snapshot acquisition before extraction.
3. Build disposable SQLite databases with schemas compatible with existing readers.
4. For taxonomy, include the complete rows required to reconstruct and validate the active ecosystem/version/membership graph. Copying all four small taxonomy tables is acceptable.
5. For market, include all `ticker_meta` rows plus the exact OHLC closure required by the canonical candidate:
   - the latest valid row on or before every TTM source-availability date;
   - the last 32 rows on or before the calculation date for every eligible ticker;
   - explicit compact metadata needed by source-state validation instead of retaining full history solely for `COUNT/MAX` diagnostics.
6. Deduplicate selected OHLC rows by stable primary identity and create only the indexes used by current readers.
7. Compute deterministic semantic fingerprints from normalized selected rows, plus a physical bundle SHA-256, schema fingerprint, row counts, source file identity, source pragmas, extraction policy version, canonical binding, and as-of date.
8. Recompute the relevant live semantic projection after extraction. If it differs from the bundle, report `READ_ONLY_SOURCE_DRIFT` and discard the candidate. Changes outside the selected/as-of semantic projection do not stale the run.
9. Validate bundle integrity and make all rebuild and validation readers use only bundle paths.

The selection contract must be centralized. A new market/taxonomy query cannot silently bypass it; changing consumed tables or query semantics requires a source-contract version change and fixture update.

### Test and Production binding

Test persists the complete bundle manifest and semantic fingerprints in its durable result. Production creates its own fresh bundle using the same contract and requires exact semantic fingerprint equality with the bound Test before candidate construction. Drift returns a retry-required/stale-Test result before the publication boundary.

Production should retain its existing scheduler/Production locks as defense in depth. The bundle transaction and fingerprint contract remain the correctness authority because taxonomy and other writers do not all share that lock today.

### Crash and rollback behavior

Bundles are disposable candidate inputs. A crash before publication cannot affect Production. A publication crash continues to recover only provider, canonical, and analysis from the durable journal backups. Market and taxonomy are never restored.

An incomplete journal may conservatively retain the run lane until recovery, matching current behavior. Terminal recovery or terminal completion removes the bundle with the rest of the lane. Lightweight manifests remain as audit evidence.

### Fallback

If projection construction encounters an unknown schema, unsupported reader requirement, incomplete selection closure, extraction drift, or validation mismatch, fail closed. During staged rollout, the caller may explicitly use the current full SQLite online-backup implementation. It must never silently fall back to direct live multi-connection reads.

## Explicit safety contract

- The three publication databases and their journal/recovery rules are unchanged.
- The source bundle is immutable after validation and is never a publication target.
- Every full V2 calculation and validation reads only the bound bundle.
- Test and Production use the same extraction contract and matching semantic fingerprints.
- Source drift before or during extraction stops the run before publication.
- Source changes after extraction cannot alter that run because all later reads use the bundle.
- No source database is mutated, backed up for rollback, or restored by Fundamentals.
- File metadata and source pragmas are audit evidence, not semantic authority.
- Dirty Git remains an audit warning only.

## Disk and runtime impact

Runtime measurements on 2026-09-22:

| Source | Current size |
|---|---:|
| `osakedata.db` | 1,990,488,064 bytes / 1.854 GiB |
| `analysis.db` | 11,078,471,680 bytes / 10.318 GiB |
| Total per full source snapshot | 13,068,959,744 bytes / 12.171 GiB |

The live market database has 8,796,437 price rows for 4,914 tickers. The current canonical input has 89,872 V4 TTM rows and 2,542 active securities. The upper bound before deduplication is therefore roughly one selected price per TTM endpoint plus 32 recent rows per active ticker, about 171,000 rows, versus 8.8 million source rows.

The active taxonomy has one active version, 1,188 active memberships, and 335 active entities. The four relevant taxonomy tables and indexes occupy well under 1 MiB, while `analysis.db` is 10.318 GiB.

Expected per-snapshot savings are conservatively more than 11 GiB and likely about 12 GiB, or roughly 98-99%, subject to implementation measurement and indexes. A full workflow that currently snapshots the sources in both Test and Production would avoid roughly twice that write volume.

Runtime should improve by avoiding sequential reads and writes of 12.17 GiB. Costs shift to indexed semantic extraction, deterministic hashing, and compact bundle validation. Market extraction performance is the main measurement target; no precise wall-clock claim is made before a fixture and production-shaped benchmark.

## Staged implementation plan

1. Add a source-contract module with `StableReadOnlySourceBundle`, a versioned manifest, extraction policies, semantic fingerprints, and the current full-copy fallback. Do not change callers.
2. Centralize and test the complete market/taxonomy read closure used by `canonical_valuation_source`, `peer_source_context`, `relative_valuation.source`, taxonomy loaders, and snapshot validation.
3. Add fixture and concurrency tests, including DELETE and WAL modes, source replacement, value-only changes, and irrelevant post-as-of changes.
4. Route Refresh Test through the bundle and compare candidate results byte-for-byte/semantically with the current full-copy path.
5. Route Refresh Production through the same contract and bind its manifest to the successful Test manifest. Keep publication behavior unchanged.
6. Split `batch_add_tickers.create_copy_lane()` into mutable publication-role candidates and the shared read-only bundle. Route Add Tickers Test and Preview as appropriate.
7. Route `production_transaction.run_transaction()` and the Sector/Industry and Taxonomy workflows through the same bundle so all Admin Test/Production paths have parity.
8. Run production-shaped parity and fault-injection acceptance. Only then remove the default full-copy path; retain it as an explicit fail-closed compatibility fallback for one release.

Likely modules and symbols:

- `rawcandle/fundamentals/admin/refresh_copy_runtime.py`: replace `prepare_full_v2_read_only_copies()`;
- `rawcandle/fundamentals/admin/refresh_production.py`: bind Production to the Test source manifest;
- `rawcandle/fundamentals/admin/batch_add_tickers.py`: split `create_copy_lane()` roles;
- `rawcandle/fundamentals/admin/production_transaction.py`: remove direct live source semantics;
- `rawcandle/fundamentals/admin/full_v2_downstream.py`: accept only validated bundle paths/manifests;
- `rawcandle/fundamentals/operating_income_v2/full_rebuild.py` and source readers: validate source-contract version and avoid unregistered source queries.

Rollback of the code change is configuration-based: switch the abstraction back to `FULL_SQLITE_BACKUP`, rerun Preview and Test, and proceed only with newly bound evidence. No database rollback is involved.

## Future test plan

Minimum acceptance matrix:

1. unchanged sources produce the same V2, RP V2, RV, taxonomy, and lineage fingerprints as full copies;
2. a relevant change before extraction produces a new bundle and makes an older Test stale;
3. a relevant change during extraction is detected and fails closed;
4. an irrelevant or post-as-of change does not alter the semantic bundle fingerprint;
5. separate concurrent market and taxonomy writers cannot produce an internally mixed bundle;
6. DELETE-mode market extraction is bounded and either succeeds or fails without writer starvation;
7. WAL-mode taxonomy extraction remains stable and does not permit unbounded WAL growth;
8. atomic source-file replacement during extraction is detected or safely bound to one old inode snapshot;
9. interruption leaves only disposable bundle files and never mutates sources;
10. Test and Production manifests must match before Production candidate construction;
11. unknown schema/table/query requirements fail closed to the full-copy fallback;
12. source DB size, mtime, and semantic fingerprints remain unchanged by Fundamentals;
13. publication failure restores only provider, canonical, and analysis;
14. recovery cleanup removes retained bundles without deleting rollback backups;
15. all Admin workflows use the same source-consistency abstraction.

## Unresolved risks and questions

The main risk is proving complete price-row closure. Current readers express price needs in several forms, including per-TTM latest valid bars, RV 32-bar windows, and snapshot validation. Missing one query would make a compact bundle semantically incomplete. The implementation must centralize this contract before optimization.

Other remaining risks are extraction query cost against `osakedata.db`, short DELETE-journal reader impact, schema evolution, and the operational frequency of Test becoming stale after a relevant nightly source update. A production-shaped benchmark is required to establish actual bundle size and extraction duration.

Reflink support in the present ext4/WSL stack was not assumed or probed destructively. It may be evaluated later as an optional acceleration for the full-copy fallback, never as the only safety mechanism.
