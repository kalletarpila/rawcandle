# Fundamentals scheduler HOLD, rolling history and review evidence correction

**Nightly Fundamentals remains on HOLD.** The existing scheduler enable flag was disabled before source implementation. Rolling-history coverage now separates captured response integrity from OLD financial authority, and all 189 queue binding mismatches have a proven writer/reader compatibility correction. No live financial operation, provider request, queue migration or approval change was performed.

Governing baseline: architecture `1926f78cb368d3374c302265dd27e61b131eafc5`, acquisition foundation `28f85ee3bf1a376797e9174cbd193ba8918b48d6`, current-runtime recheck `b16983045dd17cdfbd0ab718797b4de49dbad980`. Scope is integration preparation, not the complete Phase 2 coordinator or a financial rollout.

## 1. Scheduler HOLD — first authorized action

Inspected the effective root `scheduler_config.json`, native `read_scheduler_config` validation and `run_scheduler_config`. The latter reads that file on each entry and invokes `_run_fundamentals_refresh_preview_post_step` only when `fundamentals_refresh_preview_enabled` is true. Its FULL_WORKFLOW production-lock choice uses that same enable flag. Other market, technical and DC dispatch is outside that conditional.

Before mutation, scheduler status reported `is_running=false`, last outcome FAILED, completed at `2026-11-12T08:11:42Z`; read-only nonblocking kernel-lock checks found no exclusive owner of `temp/.fundamentals_admin_production.lock` or `logs/stock_update_scheduler.lock`. Native financial journal was healthy COMPLETED/PASSED. No process was killed, suspended or recovered.

| Setting | Previous | Effective after HOLD |
| --- | --- | --- |
| `fundamentals_refresh_preview_enabled` | `true` | **`false`** |
| `fundamentals_refresh_mode` | `FULL_WORKFLOW` | `FULL_WORKFLOW`, preserved for a later deliberate reactivation |
| `enabled_markets` | `omxh`, `usa` | unchanged |
| `run_time` / `timezone` | `04:30` / `Europe/Helsinki` | unchanged |
| `skip_next_run` | `false` | unchanged; the whole nightly job is not skipped |
| `technical_relevance_enabled` | `true` | unchanged |
| `datacenter_stage2_incremental_enabled` / `ec_source_layer_enabled` | `true` / `true` | unchanged |
| Other serialized/effective settings, including P/B preference | original settings | identical |

The same existing configuration file was updated atomically/fsynced; native configuration validation and reload verify the result. It is a one-field semantic change, with no second HOLD flag, service or schedule. The previous raw file and effective value are preserved in local task evidence. `scheduler_config.json` is untracked and ignored by `.gitignore:110`; it is changed in place and **not forced into Git**.

Read-only comparison proves every other raw key and effective dataclass field unchanged. The next native scheduler entry therefore skips Fundamentals while retaining its normal price/StockCore market dispatch, technical analysis, DC and EC processing. A disposable run of the real scheduler dispatcher, with fake job boundaries, verifies both markets and all those post-steps execute while Fundamentals never executes; a second reload/run preserves the same HOLD. A native status query dispatches no work and changes no fixture file. This verifies dispatch/configuration behavior, not a new live run of those jobs.

Reverting source code must not restore the old enable flag. No automatic reactivation is installed. Reactivation requires the complete four-stage architecture, accepted disposable end-to-end behavior, a separately authorized successful controlled live update, verified publication/recovery/source/history/locality safety, and **explicit operator authorization**. None of that later authorization is supplied by this task.

## 2. Original history-coverage error and corrected contract

Phase 1 treated the set of OLD source keys whose `date` lay inside requested `from`/`to` as a mandatory subset of every newly returned response. Any absence raised `OLD_WINDOW_COVERAGE_MISSING`. That conflated three separate facts: request date scope, the provider's actual retained financial periods, and financial authority to change OLD. The subscription's approximate ten-year retention does not make the explicit lower-bound request a guarantee that every older OLD observation remains available.

The native documentation describes explicit `from`/`to` request bounds and a one-year default when no lower bound is supplied. It also distinguishes the filing-time AR series from the report-period-indexed MR series. These are not canonical `period_end`. This correction keeps the explicit, bounded singleton request and never uses a freeze date or a subtraction of ten years as proof of the actual retention boundary. [Native Fundamentals documentation](https://sharadar.com/docs/fundamentals), [native query documentation](https://sharadar.com/docs/getting-started).

New requests use `SINGLETON_ARQ_MRQ_WINDOW_V2`, with the same one-ticker ARQ→MRQ sequence, explicit request horizon, unprojected native transport and 168-hour freshness. Coverage receipts retain the OLD anchor count and add missing-key count/digest, `source_history_comparison_required`, `absence_authorizes_deletion=false` and an explicit statement that the provider retention boundary is not inferred from request `from`. Missing identities are reproducible from the hash-bound anchors and captured source; large lists are not embedded into root/control files.

A successful complete native bounded response may contain a source-history difference and still be transport/source-profile COMPLETE_VERIFIED. That state **does not accept the financial difference**. `read_slot` marks incoming eligibility false when OLD keys are absent, pending local history comparison. Empty/limit-hit/truncated/wrong-identity/malformed/unverified-capture responses retain their fail-closed protections. Diagnostic rows with an invalid normalized projection are replayed by validating their exact original raw/envelope pair; no fresh capture is constructed and those rows never become eligible incoming finance.

`AcquisitionSnapshot.compare_source_history(ticker, project_root=...)` is a narrow read-only preparation interface:

1. Pin the expected native immutable OLD manifest before and after local reads. Full OLD role hashing remains a phase-entry/preflight check, rather than a multi-GiB operation repeated for every ticker.
2. Read OLD through the native read-only provider-history loader, including legacy payload/provenance and ambiguity checks. No grandfathered V1 attestation is manufactured.
3. Read the two already captured dimensions, verify their checkpoint/capture evidence, and use native structural/history and rolling-retention logic. The unrelated three-year historical-review shortcut is explicitly disabled (`historical_source_window_review_years=0`).
4. Preserve all OLD observations outside the requested source-date scope. Such filtered absence is not a removal request or proof of a remote retention boundary.
5. For absent OLD keys inside the request scope, require the native oldest-prefix, report-period chronology, no same-fiscal replacement and companion-consistency rules. Automatic rolling-expiry readiness additionally requires both **observed source** dimensions to span at least the native 41-quarter boundary span minus one, in fiscal labels **and actual report periods**. A 41-quarter distance from an OLD row to a single recent source row is insufficient.
6. Return explicit native source-history events and observed report-period boundaries. Positively supported rolling expiry preserves exact OLD and allows current-source readiness without a new local hold. An interior/rekey/removal discrepancy, or insufficient effective-window proof, requires ticker-local review and prevents incoming eligibility. Unknown boundaries are not guessed.

The returned native `TRUE_SOURCE_REMOVAL` event is a comparison finding, **not deletion authority**: `automatic_deletion_authorized=false` and `publication_authorized=false` are unconditional. The preparation result does not authorize the final financial locality partition either. Phase 2 must apply its strict financial checks, exact whole-ticker OLD carry-forward/locality proof, source-removal approvals, frozen-history and WFRD boundary contracts before any candidate/publication. Shared source/identity/transport corruption still blocks safely. No hold becomes global merely because many independent tickers need review.

Existing `SINGLETON_ARQ_MRQ_WINDOW_V1` operations remain readable/verifiable under their original receipt and subset contract, including original timestamps. New semantics are not silently applied by rewriting old manifests. Eligible V1 checkpoints are preserved; V2 operations make the new distinction explicitly. Original capture/normalization versions, seven-day sealing/preflight limits, operation identity, resume verification, journal, rollback and active-generation mechanisms are unchanged. The requested history window is not expanded indefinitely.

## 3. Queue root cause — all records assessed

Observed failed scheduler operation: `20261112T072624Z_refresh_fundamentals_d00eb7239fed_full_workflow_0e019ef0`; Preview child `20261112T072624Z_refresh_fundamentals_6f16ade3451f`. Failure before financial writes was `REFRESH_REVIEW_QUEUE_EVIDENCE_TAMPERED`, in `_decode_row` during source comparison. That name did not establish malicious modification.

Read-only SQLite inspection assessed every one of **581 rows**, including all **189** mismatches. All rows have stored queue evidence fingerprints. The root cause is **historical writer/reader contract divergence (case A)** after the incomplete baseline-hold candidate was archived and accepted source restored:

- The archived writer's `_queue_evidence_binding` bound conditional `quarantine_locality` and `baseline_integrity_hold` objects in addition to the current base fields.
- The restored reader omitted both objects before recomputing the fingerprint.
- For every one of the 189 mismatches, the stored fingerprint equals the archived full binding **exactly**. The other 392 rows match the base native binding.
- The archived helper was inspected/executed in isolation for this read-only classification; the archived application/patch was not deployed. The independent fixture writer reproduces the original contract in tests.

This is not a guessed normalization fallback, ignored fingerprint, rewritten fingerprint or assumed corruption. No mismatch remains unexplained; no genuinely corrupt row was established in this dataset. The archived source helper's file SHA and per-row raw hashes, original/current fingerprints and classifications are retained in excluded task evidence.

| All affected rows | Count | Extra original bound objects | Status / operator action |
| --- | ---: | --- | --- |
| `LOCAL_BASELINE_INTEGRITY_HOLD` | 171 | `quarantine_locality`, `baseline_integrity_hold` | OPEN / none |
| `REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION` | 9 | `quarantine_locality` | OPEN / none |
| `SOURCE_PAYLOAD_KEY_REGRESSION` | 6 | `quarantine_locality` | OPEN / none |
| `AMBIGUOUS_SOURCE_REMOVAL` | 2 | `quarantine_locality` | OPEN / none |
| `COMPLETE_HISTORY_NOT_TRUSTED` | 1 | `quarantine_locality` | OPEN / none |
| **Total** | **189** | exact original binding matches | **189 OPEN; no approvals** |

All 189 have first/last-seen run `20261111T122146Z_refresh_fundamentals_8d7ad5f72900`. Of the baseline group, 170 also contain bound historical-freeze evidence; one does not. Of the remaining 18, 13 contain historical-freeze evidence and five do not. The complete affected ticker enumeration follows, so no partial subset is described as the correction.

**Baseline-integrity group — all 171:** `ABAT`, `ABM`, `ACI`, `ACN`, `ADBE`, `AEO`, `AI`, `AIR`, `ALMU`, `ALZN`, `AMST`, `ANAB`, `ANGO`, `APLD`, `APOG`, `ASO`, `ASX`, `AVAV`, `AVGO`, `AYTU`, `AZZ`, `BB`, `BBW`, `BKE`, `BNED`, `BRZE`, `BTDR`, `BYRN`, `CAG`, `CAL`, `CALM`, `CAPS`, `CASY`, `CBRL`, `CCL`, `CDT`, `CELU`, `CHWY`, `CLF`, `CMC`, `CMTL`, `CNM`, `CNXC`, `COO`, `COST`, `CPB`, `CPRT`, `CRMT`, `CTAS`, `CTNT`, `CURV`, `DAL`, `DBI`, `DCI`, `DDS`, `DELL`, `DLTH`, `DPZ`, `DRI`, `DXLG`, `EBF`, `EFX`, `FAST`, `FDS`, `FEIM`, `FIZZ`, `FLWS`, `FNGR`, `FOXX`, `FRGT`, `FUL`, `GCO`, `GIII`, `GIS`, `GITS`, `GME`, `GOSS`, `GPC`, `GPMT`, `GPRO`, `GUTS`, `GWRE`, `HAIN`, `HELE`, `HOVR`, `IBEX`, `IDT`, `INM`, `IPDN`, `IRDM`, `IRM`, `JAGX`, `JILL`, `KBH`, `KFY`, `KITT`, `KMX`, `KR`, `LAKE`, `LEN`, `LEVI`, `LITS`, `LNAI`, `LOVE`, `LPTH`, `LW`, `M`, `MCFT`, `MIND`, `MKC`, `MLKN`, `MMM`, `MSCI`, `MTN`, `MU`, `NAMS`, `NB`, `NEOG`, `NEUP`, `NFE`, `NFLX`, `NKE`, `NRIX`, `NTNX`, `NXXT`, `OCC`, `ORCL`, `PANW`, `PAYX`, `PEGA`, `PENG`, `PEP`, `PLAB`, `PLAY`, `PLCE`, `PRGS`, `REBN`, `RENT`, `REVB`, `RGP`, `RH`, `RPM`, `RZLT`, `SCHL`, `SEGG`, `SFIX`, `SGLY`, `SHPH`, `SIG`, `SKIN`, `SMXT`, `SNX`, `STZ`, `TGL`, `THO`, `TLRY`, `TRUG`, `UAL`, `UNFI`, `UPXI`, `URBN`, `URI`, `USAU`, `VNCE`, `VRA`, `WHLR`, `WOR`, `WS`, `XTIA`, `YYAI`, `ZUMZ`.

**Other original bound-locality rows — all 18:** `AG`, `AIOT`, `ARM`, `BBAI`, `CAMT`, `CHRD`, `CIFR`, `KLXE`, `MIR`, `NXH`, `OSK`, `PI`, `RCEL`, `SNDK`, `SUPN`, `TDW`, `VMRK`, `VTOL`.


### Compatible reader correction and authority limits

`refresh_review_queue._queue_evidence_binding` now includes those two conditional objects exactly as the original writer did. Rows without them retain the same base fingerprint; there is no try-an-arbitrary-reduced-layout fallback. `_review_context` preserves/binds those objects when a legitimate future writer supplies them, instead of dropping their evidence. An explicit evidence-version discriminator, if present, is checked and bound; unknown versions fail closed. Extended contexts without a binding are rejected. No version field is added to existing stored rows.

Fresh read-only verification with the corrected source accepts **581/581 rows**, leaving **zero binding mismatches**. The exact queue bytes remain unchanged. The 189 affected rows still have no operator action and remain OPEN; native retained-history, fiscal-revision and source-removal approval eligibility checks remain false for all 189. The existing two terminal resolutions remain terminal. Source/material fingerprints remain opaque but exactly bound references; restoring row readability does not certify that incoming finance, generic archived locality proof or a stale approval may be accepted.

The original native status/action, material-drift, approval fingerprint, published-generation, resolution and audit checks are retained. No queue migration, row rewrite, evidence replacement, review clearing or automatic approval is required or performed. Genuine mutation of any bound field still fails fingerprint verification. Unsupported/shared binding corruption remains a blocker rather than being relabeled LOCAL. A separately queried valid ticker may remain readable, but a shared invalid review scope cannot authorize publication. Existing native positive-locality partitioning retains no count threshold; 125 independent local reviews with a safe peer remain local in disposable acceptance.

This is a complete code-only correction for the observed 189-row mismatch mechanism. A fresh process reading the updated source was verified; no long-lived UI process or live scheduler/financial job was restarted to deploy it during this task.

## 4. Exact source/test/documentation changes

| File | Change |
| --- | --- |
| `rawcandle/fundamentals/admin/acquisition_snapshot.py` | Explicit V2 response/history distinction; V1 compatibility; absent-key digest/count; conservative read-slot eligibility; read-only paired native history comparison with observed financial-period coverage; original diagnostic raw/envelope replay |
| `rawcandle/fundamentals/admin/refresh_review_queue.py` | Restore exact archived conditional binding fields, preserve them in new contexts, fail closed for unknown versions/missing extended bindings; no financial classification or approval-rule relaxation |
| `tests/test_fundamentals_acquisition_snapshot.py` | Replace the obsolete OLD-subset failure expectation with explicit discrepancy/eligibility assertions |
| `tests/test_fundamentals_history_queue_correction.py` | Native disposable provider/canonical/generation fixtures and fake HTTP; rolling expiry/interior discrepancy/short-window/OLD preservation, original queue writers, tamper/versions/terminal authority and 125 local reviews |
| `tests/test_fundamentals_scheduler_hold.py` | Real dispatcher with disposable paths/fake job boundaries: both markets and technical/DC/EC continue, finance absent across reloads, read-only status query |
| `docs/fundamentals_v4/fundamentals_single_fetch_acquisition_foundation_v1_2026-11-11.md` | Mark the original subset contract superseded by this correction, preserving historical acceptance |
| This report | Exact configuration, cause/classification, acceptance, runtime and remaining rollout boundaries |

The local scheduler configuration is changed but excluded from Git because it is ignored/untracked. No scheduler source change or second scheduling control is needed. Generation/journal/recovery, capture/normalization contract, current financial route, WFRD, history/freeze, StockCore/OHLCV/DC source and all financial databases remain untouched.

## 5. Focused disposable acceptance

**253 PASS**, no failures/errors/skips in the final two targeted runs:

- 78 cases: new history/queue corrections, scheduler HOLD and the acquisition foundation (38.75 seconds).
- 175 cases: native review queue/approvals/resolutions, source-window retention, historical freeze, capture contract, scheduler Full Workflow configuration and disabled dispatch, scheduler configuration and immutable generations (35.73 seconds).

The first group uses real native HTTP/capture with fake transport and disposable native SQLite/generation roots. It covers an OLD quarter outside observed remote coverage; interior/current-window missing keys; current-quarter advance alongside expiry; incomplete/limit/truncated/wrong/projected payloads; actual report periods versus misleading fiscal labels; old rows/first-public dates/frozen canonical values and all role hashes preserved; no new OLD captures; V1 manifest/checkpoint compatibility; exact seven-day ages, resume, corruption and original capture provenance; native writer/current/extended queue evidence; bound-field tampering; known/unknown versions; terminal resolution and approval non-broadening; valid isolated queries versus shared corruption; and more than 100 local holds. Full role hashing is not repeated per ticker; manifest drift still rejects a local comparison.

A discovered diagnostic replay inconsistency was corrected and tested: when a source row's projection is invalid, the original received envelope still binds that raw diagnostic row. Replaying a wire wrapper previously changed its reported failure reason. The reader now verifies the original raw/envelope pair consistently while keeping that row ineligible. This is not manufacture of a new envelope or financial acceptance.

The scheduler acceptance runs the real dispatcher twice with fake isolated job boundaries, not a live nightly workload. Existing regression cases also retain native frozen-history and recovery/generation protections. No full repository suite, provider API call, live Preview/Test/Production or financial recovery is run. Only public native documentation was browsed.

## 6. Runtime authority and intentional configuration mutation

A fresh baseline was established before HOLD; today's market/taxonomy versions are preserved. No comparison restores obsolete previous-day files. The active generation remains `current_rebuild_2a684ef130c6a540de4adc560ab171ad`; published source watermark remains `2026-10-28` and query start `2026-10-25`. Native journal remains COMPLETED/PASSED/NOT_REQUIRED.

All eight protected financial/review/journal/market/taxonomy files below have identical size/SHA before and after this task. The ninth audited file, scheduler configuration, changes intentionally and is reported separately.

| Protected file / role | Size, bytes | SHA-256 before = after |
| --- | ---: | --- |
| `data/fundamentals_active_generation.json` | 1387 | `82afaa462cc12ef41616c10d3ad011bac266b452cca02e6abea605c8d5b97097` |
| `data/fundamentals_generations/current_rebuild_2a684ef130c6a540de4adc560ab171ad/fundamentals_analysis.db` | 912351232 | `6feb14748b4088096d96287d7f3b1c812faed4dc8e2352a81b390d8b86d11d8f` |
| `data/fundamentals_generations/current_rebuild_2a684ef130c6a540de4adc560ab171ad/fundamentals_provider.db` | 968331264 | `14a032489577c079607e16986380076986ab8206ed1d96aa135700499432de4f` |
| `data/fundamentals_generations/current_rebuild_2a684ef130c6a540de4adc560ab171ad/fundamentals_v4.db` | 749371392 | `2178d467a12a601e9554353fea8a3f8354444cb9347be000c3dca6c13b3e0a6d` |
| `data/.fundamentals_admin_publication_journal.json` | 589170 | `91fadb71f55be7bad2107db8948744abb17a1a7494bfb3d64d78fe2d155c1e72` |
| `data/analysis.db` | 14288310272 | `8573ce35ca06ad1ddde3c145e067971b09ca5b05f5d71f9d38572d9f0f476f10` |
| `data/osakedata.db` | 2039455744 | `bbf1972608d41022502da1ba3bff29aad24e3aed43ae9c0c6d2a0e1927a4a759` |
| `fundamental_reports/fundamentals_refresh_review_queue.db` | 882065408 | `913c454dcc93dafa706ab00c42f6a6f921f56cf93b17a59fb2c4187c61ef1355` |

Audit interval: `2026-11-12T08:53:22.711589+00:00` to `2026-11-12T09:09:26.281549+00:00`. Scheduler configuration SHA: `f4ba4fc0fde48e3ac82f5314353556ae35a0327a2e568b41abf9c759c35bb8a3` → `c9d5e669937e2f47e8c0c5d251122a29ae099dc08a5f76fe85247cfa0a607948`; semantic change is solely `fundamentals_refresh_preview_enabled: true → false`. Native typed reload remains false.

Runtime JSON/hash receipts, exact previous/current local configuration, complete per-row classifications and raw-row hashes, read-only post-correction queue verification and JUnit XML are retained only in `temp/fundamentals_scheduler_hold_history_queue_20261112/`. They are excluded from Git. No queue/audit database, financial DB, active manifest, journal, logs, capture bodies, archived patches or unrelated work is staged.

## 7. Phase 2 readiness and remaining boundaries

The identified queue-reader defect is resolved without a data migration. Singleton source capture/checkpoint identity and seven-day freshness remain intact. The local comparison interface distinguishes normal supported rolling expiry from a genuine source-history review, preserving OLD rather than accepting absent rows as deletions. Shared source/identity/capture uncertainty and unsupported review versions still fail closed; generic baseline-hold financial locality needs the full upcoming Phase 2 proof and carry-forward implementation.

The complete one-snapshot VALIDATE/PUBLISH/VERIFY coordinator, native candidate/publication integration and its disposable end-to-end acceptance remain future work. This task does not activate them, perform a controlled live update, or certify unknown live server/account retention behavior. Short or ambiguous effective windows conservatively remain ticker review; no guessed boundary is promoted to safe finance. Further live conformance or financial execution needs its separately authorized task.

**Nightly Fundamentals stays disabled.** Re-enable only after accepted complete implementation, verified native publication/rollback/recovery/source/history/local-hold behavior, a separately authorized successful controlled live update, and explicit operator reactivation approval. No push is performed.

### Subsequent bounded Phase 2 implementation

The [Phase 2 local validation/publication report](fundamentals_phase2_local_validation_publication_2026-11-12.md) records the subsequent disposable-only backend, native generation/postflight/recovery acceptance and remaining production integration limits. It consumes the corrected snapshot and queue contracts above and includes full-domain degraded-baseline preservation. This historical correction report's original acceptance remains unchanged. The new backend does not activate a production route or re-enable the scheduler.
