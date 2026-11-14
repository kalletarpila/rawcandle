# SIMPLIFY-03 — lighter VALIDATE and decision evidence

**PASS.** Starting HEAD `92b94e3318e1bda04e067b6cbfe579c8c3d570cf`. This changes only the existing validation/source handoff and decision serialization/readers. Financial policy, selection, SEC publication-date authority, BUILD/publication eligibility and native generation recovery remain unchanged.

Consulted SIMPLIFY-01, SIMPLIFY-02, compact taxonomy FIX1 and the accepted production activation operator report. Current production is the verified B `20261114T151806Z_refresh_fundamentals_cce2b9c73301_universe_reconciliation_b80ba048`, universe `2113bb9da2e5d620a8aa4de67c53f208`. Pre-existing runtime journal/untracked work is excluded from this commit.

## Measured causes and operation map

Trace is bounded to acquisition_snapshot, refresh_update, snapshot_workflow and their immediate financial-history, review, writer and BUILD/report consumers. The historical 3,203,120,851-byte decisions file was not loaded wholesale or changed. A 1 MiB prefix yielded one complete AA decision (918,211 formatted bytes): its largest fields were source_payload_changes (440,979 compact JSON bytes), source_history_events (58,067) and historical_freeze (52,765). These detailed financial/review projections are useful; the same complete change was also written again under safe/held.change/global.change. Indentation and whole-tree redaction/dumps added further serialization cost. This sample explains structure, not the total distribution of all historical decisions.

| Work | Before | After |
|---|---|---|
| Fresh workflow → VALIDATE | Workflow open + preflight, then core open + preflight: four full graph verifications | Core owns one verified open plus OLD/age eligibility inside its lock |
| Core VALIDATE, BUILD or publication entry | open_snapshot and immediately validate_preflight reverify the same graph | Combined fresh open/preflight verifies the graph once at each independent entry |
| Financial versus source-window comparison | Decode/validate both incoming dimensions and read OLD, then reload/reparse them for the window comparison | Reuse the actual current ticker's verified ARQ/MRQ/OLD objects; keep both distinct policy calculations |
| Decision output | Same full change in changes and a partition; whole redacted tree and formatted JSON string | One partition detail plus local changes reference; redact/encode each record separately and atomically commit |
| Decision fingerprint | Canonicalize/stringify all partitions together | Same exact canonical digest, one partition record at a time |
| Existing/resumed validation or delayed BUILD/publication | Fresh integrity and authority checks | Retained: no verified-forever flags or global cache |

Full graph verification still checks manifest/slot identity, request/plan/index/checkpoints, captures/body correspondence, source provenance/coverage, explicit ticker-local quarantine and ARQ/MRQ pairing. Standalone validate_preflight always re-verifies content. read_slot still checks consumed bytes. OLD roles/current authority, source age, review/identity scope and publication checks remain. A corruption test changes body content while preserving both size and mtime and still fails; BUILD rejects source corruption before candidate creation.

Only repeated loads in the same ticker decision scope were removed. The independent public compare_source_history path still loads and verifies its own data. The internal loaded-history calculation preserves the original source-day/request-window axis; it does not substitute the financial/as-of merge. OLD-domain scans, degraded baselines, global identity collisions and OLD-only names were not skipped.

## Evidence and reader compatibility

New decisions.json retains complete safe, held and global objects, plans, source/provenance/publication evidence and OLD retention. Its changes entries reference those existing local partitions by ticker/partition/index; nonpartitioned NO_CHANGE details stay inline. The optional change_references=1 representation marker does not migrate the financial contract or any database. Required approval-grade projections inside a record are deliberately unchanged. No source payload/provenance field was discarded or replaced by an unchecked filename.

_read_decisions resolves references to the same in-memory detail objects and rejects malformed targets. BUILD/publication and review finalization use it after the existing receipt/file hash checks; legacy files without the marker remain readable. Existing raw held/safe/global readers retain their full object shape, including the workflow review summary. plans and _hydrate_plan are unchanged. The decision fingerprint is byte-for-byte equivalent to the prior canonical fingerprint; only redundant file representation/whitespace and its receipt-bound file hash change.

Atomic writing uses a task-local temporary file, fsync and replace; a serialization interruption leaves any previous destination intact and cleans its own temporary file. Redaction still uses AdminRunWriter's existing sanitizer, bounded to a detail record. No new cache, registry, evidence database, acceptance issuer, publication engine or streaming framework was introduced.

## Identical-input equivalence and performance

Four frozen, isolated native fixtures were prepared once. Each before/after pair consumed the same immutable snapshot/OLD database paths, with the mutable fixture review queue restored to its original state. No production UPDATE was rebound to B or a new universe. The before process loaded the exact three original modules from starting commit 92b94e33; after loaded the changed implementation. Each implementation was loaded once in a fresh process to avoid double-import RSS bias. Fake native capture responses were local fixtures, not Sharadar/SEC network acquisition.

Wall time covers core.validate_snapshot plus receipt/hash-bound decision readback. Peak RSS is the fresh child process high-water at that point, including imports; equivalence hashing happens afterward. Counters measure actual _verify_snapshot, _validate_checkpoint, validate_complete_history and load_current_history entries, not invented SQL-query counts. One paired observation per case, no production-scale extrapolation.

| Frozen case | Status / safe / local HOLD / global | Time before → after (s) | Peak RSS before → after (MiB) | Decision bytes before → after |
|---|---|---:|---:|---:|
| rolling | VALIDATED / 2 / 1 / 0 | 1.643 → 0.978 | 200.520 → 197.695 | 438,767 → 168,947 |
| baseline | VALIDATED / 2 / 13 / 0 | 1.126 → 0.761 | 200.113 → 197.777 | 559,359 → 236,761 |
| quarantine | VALIDATED / 2 / 1 / 0 | 1.040 → 0.654 | 200.215 → 197.547 | 58,174 → 23,836 |
| global | BLOCKED / 1 / 0 / 1 | 0.239 → 0.165 | 194.059 → 193.699 | 21,637 → 10,669 |

Rolling covers a ten-year ARQ/MRQ window and an unresolved review; baseline includes twelve OLD-only degraded baseline HOLDs; quarantine excludes both dimensions for the affected ticker while preserving safe peers; global injects a synthetic cross-company OLD provenance fault before pinning its snapshot and remains BLOCKED. The latter is an isolated fault fixture, not a modification/rebinding of any production source.

For every pair, comparison required equality of full normalized decisions, unchanged exact decision fingerprint, complete BUILD plans, OLD-retention projection, classifications, counts and validation/publication eligibility. This is not a count-only equivalence claim. Combined shared proof digest: `8d877506325eb7890294b08b4c3c58c44a50505574750781cb6819673e0cce1b`; individual fingerprints are retained in final_metrics.json. All fixture financial DB hashes and immutable snapshot file hashes were unchanged after validation. No previously held value became safe. Across cases, seven safe classifications, fifteen local HOLDs (including twelve baseline and one acquisition quarantine) and one global blocker stayed identical; the safe classification within the global case never authorizes BUILD.

| Aggregate measurement (four bounded cases) | Before | After |
|---|---:|---:|
| Wall time sum | 4.048148 s | 2.556687 s |
| Peak RSS, maximum of separate child processes | 210,259,968 bytes | 207,384,576 bytes |
| Decision file bytes sum | 1,077,937 | 440,213 |
| snapshot_verifications | 8 | 4 |
| body_capture_parses | 82 | 41 |
| history_parses | 122 | 61 |
| old_history_reads | 40 | 20 |

Observed bounded time reduction: 36.84%; evidence reduction: 59.16%. RSS improvement is modest in this import-dominated workload; it does not establish a production-scale memory reduction. The historical 65m26s / 22.98 GiB / 3.2 GB execution used an older incorrectly scoped UPDATE and is not the baseline for these timings. A full historical rerun was deliberately not performed: it requires its compatible old authority and large historical scope; that immutable operation was not rebound to the newly active universe. No full-production runtime or RSS is predicted.

## Focused qualification and production preservation

Final primary run: **146 PASS**, 282.44 seconds, zero failures/errors/skips. Scope: new simplification regressions, acquisition snapshot integrity, native snapshot workflow, acquisition quarantine and selected representative/all-twelve-selection cases. Follow-up: **3 PASS**, 10.67 seconds, covering fresh/reused workflow verification, nonempty OLD-retention roundtrip and same-stat corruption. One integrated native BUILD/publication/service-history case: **1 PASS**, 10.04 seconds, entirely on owned fixtures. Follow-ups include overlaps with the primary selection; these are not 150 distinct tests or a full repository suite. No unrelated StockCore suite ran. Socket guards and benchmark subprocesses recorded zero real network attempts.

Tests cover safe effective changes, ordinary/unresolved review, baseline/OLD-only holds, quarantine with safe peers, global identity faults, OLD retention, all twelve approved tuples/companions, explicit review approval/finalization, native candidate/publication gates, age/authority/code drift, capture/index/body corruption, delayed/resumed use, interrupted serialization, legacy evidence and native failure/recovery. Product financial formulas, thresholds, SEC date rules, share/price/P/B semantics and publication-date handling were untouched.

Production postflight compares current financial role, active manifest, publication journal, review queue and scheduler configuration metadata/SHA-256 to the pre-task baseline. Active generation and installed universe remain the expected B/universe above; all twelve selections still resolve correctly; watermark remains 2026-10-28; SNAPSHOT_V1 and automatic Fundamentals HOLD remain unchanged. No production writer lease was held for benchmarking; isolated copy/fixture locks and task-owned evidence paths were used. No production financial/review write, live UPDATE/FETCH, BUILD, PUBLISH, cleanup, VACUUM, storage migration, scheduler change or Sharadar/SEC HTTP call occurred.

## Remaining bottlenecks and deliberate deferrals

- Whole OLD-generation hashing, baseline validation and legitimate per-phase integrity checks remain; their different authority boundaries were not conflated.
- Per-slot plan/index/transport metadata walks and the graph-versus-consumed-slot verification remain. Safely fusing them would need a separately proven lifetime/reader contract.
- Financial and request-window merges remain separate because their policy axes differ.
- Complete decision projections, approval-grade nested details and all plan references remain in memory for whole-domain locality checks. BUILD/review still decode the smaller aggregate file; end-to-end per-ticker random-access evidence/sharding is deferred rather than adding another store or framework.
- No SEC acquisition slice redesign or publication/recovery change belongs in this task. Existing code-bound receipts still require their native current-code checks; legacy JSON readability does not authorize a stale candidate.

**Remaining blockers: none within this bounded simplification.** Ignored reproducible evidence and source snapshots: temp/fundamentals_simplify03/ (original modules, frozen cases, final_metrics.json, equivalence.json, JUnit/logs and production before/after). Only the three task-owned modules, new regression test file and this report are committed. Generated databases, snapshots, queues, logs and benchmark evidence remain uncommitted. Push: NO.
