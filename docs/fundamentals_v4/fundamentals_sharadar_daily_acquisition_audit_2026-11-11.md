# Fundamentals Sharadar daily acquisition audit — 2026-11-11

Audit and design only. No acquisition optimization was implemented, no Sharadar request was made, and no financial operation, queue update, recovery, publication or scheduler configuration change was invoked. The pending baseline-integrity/locality/UI implementation remains archived. Source HEAD at audit start: `598765153d2b394e09ecbca01533fe51cafbe310`; accepted prerequisites `abce59ad8ecf63acd5940642b03f837129aab1d4` and `9ed344e397fde8912eba5b0ebf38f285e7d4751d` remain governing.

## Findings and evidence limits

Daily Refresh already selects tickers through discovery, then fetches complete **ARQ and MRQ** source histories for every selected known ticker. It also selects unresolved reviews and accounting-boundary cases independently of discovery. It does not compare discovery rows against individual stored provider observations before requesting both histories. The historical financial freeze acts after acquisition and comparison; it does not reduce network requests.

The incident's **1,810 is a ticker count**, representing **3,620 planned ticker/dimension history calls**, before retries, schema or discovery. Its 1,531 progress count proves that both dimension calls returned for 1,531 ticker iterations, not that those responses were successful or trusted. No independently reusable histories from that attempt survived termination. The exact HTTP-attempt total is not recorded and cannot honestly be reconstructed. At least **3,066 HTTP attempts** are provable; this is a lower bound, not an actual total.

A large part of this scope concerns recent financial information: the last completed scheduler Preview records **1,512 ARQ latest-quarter advances**. Its zero final `NEW_QUARTER` classifications are misleading for acquisition analysis because payload changes can overwrite the classification with `HISTORICAL_REVISION`. Historical change labels must not be used as a request-skipping rule.

The active provider database retains 192,986 observations, but **zero have a V1 source-capture envelope**. Existing accepted legacy evidence remains usable under its existing contract. It cannot be retrospectively promoted to a fresh attested acquisition or a verified complete-history cache.

The recommended initial design combines durable native acquisition checkpoints, process-independent pacing/429 coordination, existing discovery selection, and explicit bounded reevaluation of excluded holds. Retain full source acquisition for fresh financial authorization. Defer blanket current-period filtering and cross-stage cache substitution. On the corroborated incident scope, a narrower hold-recheck policy could defer **310 base history calls per pass, approximately 8.6%**, subject to the conditions below. There is **no proven immediate request elimination under the unchanged current contracts**, and no defensible steady-state daily percentage from this backlogged sample.

Evidence is classified throughout as **verified**, **reconstructed**, **conditional estimate**, or **recommendation**. Missing transport telemetry and the interrupted run's missing discovery manifest are findings, not facts to fill with estimates.

## Authoritative runtime and inspected evidence

The audit's read-only initial hash snapshot was taken at `2026-11-11T17:24:02Z`. Active generation: `current_rebuild_2a684ef130c6a540de4adc560ab171ad`. All three role hashes match the active manifest. The nine protected files comprise provider/canonical/analysis roles, manifest, publication journal, review/audit DB, scheduler configuration and market/taxonomy databases. No native operation lock was written or recovery method called for this audit.

Current configuration enables Fundamentals `FULL_WORKFLOW`. The provider publication watermark remains `2026-10-28`; its three-day inclusive overlap starts `2026-10-25`. The completed discovery evidence covers updates through `2026-11-10`; the run date is `2026-11-11`. Repeated blocked/non-published attempts do not advance that financial watermark. Consequently the inclusive range from the lower-bound date through the run date spans 18 calendar days, not a healthy single-day workload. The normal unpartitioned request has only `lastupdated.gte`, with no explicit upper date bound; the run date bounds the fallback daily partition loop.

Inspected native evidence:

| Evidence | Run / artifact |
| --- | --- |
| Latest completed scheduler receipt | `logs/stock_update_scheduler_summary_20261111T044713Z.json`, finished `2026-11-11T08:13:15Z` |
| Scheduler parent / Preview | `20261111T072655Z_refresh_fundamentals_d00eb7239fed_full_workflow_d07cf1a4` / `20261111T072655Z_refresh_fundamentals_8d7ad5f72900` |
| Later completed manual Preview, used only for corroboration | `20261111T122146Z_refresh_fundamentals_8d7ad5f72900` |
| Interrupted parent / Preview | `20261111T162424Z_refresh_fundamentals_d00eb7239fed_full_workflow_988506e3` / `20261111T162424Z_refresh_fundamentals_8d7ad5f72900` |
| Incident's source, preflight and transport diagnostics | `temp/fundamentals_baseline_integrity_final_20261111/` |
| Archived incident source | That folder's `unqualified_source/` and `implementation_rebased.patch`, SHA-256 `913b5c164a6ace12cb740ed97df6a70ac3e0811d39b767b63cd2c87e5e56084b` |
| This audit's read-only inventories, projections and offline receipts | `temp/fundamentals_sharadar_daily_acquisition_audit_20261111/` |

Large completed artifacts were streamed one ticker at a time or projected by top-level field. No full multi-gigabyte parent or child JSON was eagerly loaded. The archived modules were inspected as source; they were not installed or deployed.

## Current daily call graph

These are normal daily functions, except where repair/backfill is expressly identified. Database names below refer to the active immutable role paths, not an assumption that legacy flat paths are authoritative.

| Step and exact entry points | Network and local authority | Writes and local reuse |
| --- | --- | --- |
| `scheduler.runner.run_scheduler_config` → `_run_fundamentals_refresh_preview_post_step` | Runs once as the configured post-step after the market/DC work; reads scheduler config | Scheduler status/receipt only here. FULL_WORKFLOW owns native production/scheduler locks. This audit does not invoke it. |
| `admin.refresh_scheduler.run_scheduler_refresh_discovery` → `FundamentalsAdminUIService.full_workflow` → `full_workflow.run_refresh_full_workflow` | Checks publication safety; orchestrates native stages | Admin lock, compact parent control artifacts and native child references; no substitute acquisition engine. |
| `refresh_fundamentals.resolve_refresh_state` | Read-only provider `sharadar_refresh_state`; bootstrap path derives an initial watermark if absent | No network or watermark write. Published watermark is not a record of the latest download. |
| `source_schema` → `SharadarClient.schema` | `GET https://api.sharadar.com/v1.0/schema/fundamentals`, unauthenticated | Validates required schema fields; source schema fingerprint retained only in completed stage evidence. |
| `_discovery_call` / `discover_changed_tickers` | Two normal projected `GET /data/fundamentals` calls: one per ARQ/MRQ with `fields=ticker,dimension,lastupdated`, `lastupdated.gte`, limit 10,000 | In-memory discovery set. No provider replacement. Exact-limit responses cause daily partitions and fail closed if still at limit. |
| `resolve_identity`, `RefreshReviewQueue.pending_tickers`, accounting boundary `read_items` / `installed_decisions` | Read canonical active universe/security/provider mapping, provider ticker metadata and operational queue/boundary decisions | No network. Unknown/outside-universe identities do not receive full-history requests. Pending statuses are OPEN, WAITING_PROVIDER and RETRY_REEVALUATION. |
| `run_preview` → `fetch_complete_history` | For each selected KNOWN ticker, sequential ARQ then MRQ `GET /data/fundamentals?ticker=...&dimension=...&limit=10000`; **no fields projection and no date/reportperiod cutoff** | Full responses and `HistoryTrust` remain in process memory. No per-history checkpoint. Both dimensions are requested even if discovery only indicated one. |
| `load_current_history` → `compare_ticker_histories` / `build_source_history_merge` | Read saved provider headers, native typed rows, raw payloads and provenance; compare only after acquisition | Reuses old retained rows, resolves latest local versions, compares additions/removals/financial/fiscal/metadata/payload differences. No new network here. |
| `historical_freeze.apply_to_comparison` / `accepted_history` | Reads accepted canonical quarters/provenance and referenced provider evidence | Protects accepted financial periods; creates/enriches review evidence after full source comparison. No acquisition cutoff. |
| `partition_changes`, queue upsert and final Preview artifacts | Positive local/global scope and exact binding | Preview may write the existing operational queue/audit and child artifacts; never active provider/canonical/analysis. Persistence happens after acquisition/comparison. |
| `refresh_copy_runtime.run_apply` → `revalidate_bound_source` | **Fresh schema + discovery + complete histories again**, including held and approved scopes; reads original bound Preview and OLD roles | Creates isolated candidate copies, replaces safe provider histories, rebuilds canonical/analysis and persists Test evidence. Original Preview is not a freshness cache. |
| `refresh_production.run_production_apply` | `revalidate_bound_source` before candidate preparation and again at FINAL_SOURCE_RECHECK | Exact tested scope, candidate validation, complete OLD backups, native three-role generation activation, journal/postflight and watermark publication. Local rebuild reads all relevant stored history. |

Production's candidate result-publication enrichment can also use SEC through `candidate_publication.run_candidate_publication` / `SecClient`. That is separate from Sharadar request accounting. P/B continuation consumes published active financial authority; it must not use rejected incoming held evidence.

The two Production revalidations and the Test revalidation are normal financial authorization, not repair/backfill. With an unchanged 1,810-ticker scope, a successful financial Full Workflow would make four acquisition passes: **14,480 base history calls plus 12 base schema/discovery calls**, before retries/partitioning. This is a conditional workload calculation, not what the interrupted attempt actually executed. It entered neither Test nor Production.

`provider_payload_workflow`, `current_state_rebuild`, Add Tickers, phase12c bulk/backfill and checksum-bound `source_capture.archive_records` provide other acquisition/replay paths. They are not an automatic daily Refresh cache or a resume path for this incident. Normal Refresh does not fetch ART/ARY/MRT/MRY merely because these dimensions exist in storage.

## What discovery proves, and why unchanged local data is still fetched

Verified discovery output is a normalized set of `(ticker, dimension, lastupdated)` tuples and then a ticker union. It does **not** retain source row identity `(ticker,dimension,date,reportperiod)`, report period, filing/source-availability date, fiscal identity, full financial values, payload hash, deletion tombstone, ETag, immutable row version or complete-history membership proof. `lastupdated` is parsed as a date. Multiple different source rows sharing the same normalized tuple collapse into one entry.

The current selector does not first ask whether each discovered row is already identical to a local row. Any ticker with an update in the inclusive overlap, or in the pending/boundary union, receives both full histories. Locally unchanged data establishes only the OLD accepted state. The local/remote equality determination happens afterwards. Same `lastupdated` or absence from discovery is not a sufficient proof that all remote keys, raw fields and source memberships remain identical.

Unchanged tickers **outside every selection set** already avoid full-history calls. The interrupted Preview's 1,222 NOT_IN_CANONICAL_UNIVERSE identities also avoid history acquisition. Broadening this to all discovered tickers would add 2,444 base history calls per pass; the current implementation already avoids them.

This large run is explained by the unchanged publication watermark, a broad overlapping discovery window, current-quarter advances, unresolved-review reevaluation, an explicit WFRD boundary check and the absence of a reusable acquisition checkpoint. It is not evidence that all tickers are downloaded every healthy day.

## Scope reconstruction and HTTP units

Verified interrupted events record: discovery **2,876 tickers / 5,783 normalized tuples**; identity evaluation **3,032 tickers**; KNOWN history scope **1,810 tickers**; completed ticker iterations **1,531**. These numbers describe distinct units.

The interrupted run did not save its full discovery membership or remaining acquisition plan. Its exact processed prefix is available: 1,531 unique, monotonically numbered ticker events ending at STE. The remaining **279 ticker names and actual dimension-level transport outcomes are not independently retained**. All 1,531 processed names exactly match the prefix of the earlier completed 1,810-ticker scope, and recombining that earlier discovery with the unchanged queue/baseline/boundary state produces the same 3,032/1,810 totals. The following membership breakdown is therefore a **corroborated reconstruction**, not an invented interrupted-run manifest or execution authority.

| Selection mechanism | Tickers | Base ARQ/MRQ call equivalents | Overlap / authority limit |
| --- | ---: | ---: | --- |
| Discovery, all identities | 2,876 | Not all fetched | Includes 1,222 outside the canonical universe |
| Discovery, known identities | 1,654 | 3,308 | Main acquisition set |
| Current unresolved queue participation | 579 | 1,158 | 424 already overlap prior discovery; do not add these calls again |
| Queue-only, absent prior discovery | 155 | 310 | All 155 are baseline-integrity holds |
| WFRD boundary-only | 1 | 2 | Outside both prior discovery and current provider-review queue; keep its special revalidation |
| Degraded-baseline scan participation | 171 | 342, already included | All 171 already in current unresolved queue; **zero additional unique requests** from the archived scan in this incident |
| Historical freeze itself | 0 extra | 0 extra | Applied after acquisition; no direct selector |
| Rolling source retention itself | 0 extra | 0 extra | Comparison/merge policy; a resulting pending review can select a later run |
| Test/Production revalidation executed in incident | 0 | 0 | Neither entered |
| Total planned original pass | **1,810** | **3,620** | 1,810 ARQ and 1,810 MRQ logical calls if completed |

Precisely **1,531 ARQ and 1,531 MRQ history calls returned** before the last completed ticker event. One next ticker's dimension request was interrupted during native HTTP retry sleep. Whether that was its first or second dimension is not retained; an additional completed dimension result may also have been lost before the pair's progress event. Do not invent an exact count for that partial iteration.

There is no durable per-attempt HTTP ledger. The lower bound is **3,062 returned history calls + at least one current HTTP attempt + at least one schema and two discovery attempts = 3,066**. Retries and any unrecorded partitioning only increase it. The in-memory `SharadarClient.request_count` does not survive termination. The actual interrupted discovery partition flag was not saved. The earlier completed Previews explicitly say `partitioned=false`; that does not justify fabricating the interrupted flag.

Two separate previously completed Previews on the same UTC date have known base logical call counts: scheduler **3,315** and later manual Preview **3,623**, together **6,938 before retries**. These explain why the interrupted run's counter alone cannot describe credential-wide preceding volume. They do not establish Sharadar's quota, reset window or the complete account-wide request total.

## Provider storage and trustworthy reuse

Read-only inventory of active immutable provider storage:

| Item | Verified population |
| --- | ---: |
| `provider_observation`, SHARADAR/fundamentals/SUCCESS | 192,986 |
| ARQ / MRQ observations | 92,617 / 93,323 |
| Distinct ARQ/MRQ tickers | 2,541 each |
| Other stored dimensions: ART / ARY / MRT / MRY | 2,814 / 967 / 2,540 / 725 |
| Explicit retained-outside-window ARQ / MRQ | 407 / 460 |
| Raw objects with 29 / 112 / 113 keys | 12,940 / 167,556 / 12,490 |
| V1 source-capture envelopes | **0** |
| Source-key groups with multiple stored versions | 670 |
| Provider run rows | 35 |
| Provider rows attributed to interrupted run | **0** |
| Canonical quarters frozen / current by actual `period_end` | 74,637 / 15,504 |

`provider_observation` stores exact JSON objects as supplied to its insertion path in `payload_json`, typed identity/header fields, `provider_record_key`, `content_hash`, observation/run IDs, `observed_at_utc`, `fetched_at_utc` and `provenance_json`. Legacy 29-key projections demonstrate that “payload_json exists” does not prove a complete upstream object. The native typed child table stores source dates, fiscal metadata and selected financial columns; it is not a substitute for complete raw payload storage.

The source key is `(ticker, dimension, date, reportperiod)`. Refresh observation IDs hash provider/table, record key and content hash. The default Refresh content hash uses the normalized Refresh projection; controlled full-payload paths can use a full raw hash. Neither every `content_hash` nor the field called `raw_source_fingerprint` universally proves equality of all upstream keys: `history_fingerprints` hashes the Refresh projection. Separate payload fingerprints/capture guards remain essential, including P/B fields.

`load_current_history` groups local source keys, selects maximum `lastupdated`, rejects conflicting latest effective/raw versions and prefers a source-backed equivalent over a retained equivalent. Retained observations are exact OLD evidence, not newly observed remote rows. `replace_provider_histories` keeps their original header/raw/capture identity when carrying them forward in an inactive candidate. The storage is versioned accepted provider evidence, not an immutable archive of every received response; non-retained histories for selected safe tickers can be replaced in the candidate.

`provider_run.request_scope`, `source_version` and metadata record application run contracts, ticker selections and some archive/source hashes. In this database `source_version` values are application versions such as `PHASE13G3_58...` and `FUNDAMENTALS_CONTROLLED_CURRENT_STATE_REBUILD_V1`, not remote immutable row versions. Run metadata key sets include ticker lists, bulk/archive hashes and a preview fingerprint; they do not reconstruct this interrupted HTTP pass.

The V1 native HTTP boundary, when used for future writes, binds full unprojected raw record keys, field states, normalized projection, acquisition timestamp, endpoint, request fingerprint and response SHA-256. It creates capture objects in memory. It does not by itself persist the original HTTP body, full parameters, response headers or a complete-history coverage manifest. A row capture is not proof that an entire ticker/dimension series is complete.

| Evidence kind | Permitted use / limitation |
| --- | --- |
| Complete retained provider observation | Exact existing accepted carry-forward under native retention/provenance rules; not a new acquisition or proof of current remote absence |
| Current accepted provider observation | OLD comparison baseline and canonical provenance where references validate; not proof that the remote row is unchanged |
| Legacy unverified observation | Existing grandfathered use only where its established validation permits; never manufacture V1 attestation |
| Previous acquisition response | Independently usable only with retained native capture, complete request scope, body/record integrity and freshness authority; not inferred from provider SUCCESS |
| Cached complete source history | No dedicated authoritative reusable history cache exists in the daily path; completed Preview comparison artifacts do not generally contain its complete response series |
| Interrupted/incomplete response | Diagnostic only; no COMPLETE status, acceptance or reusable-history claim |

Canonical financial authority references provider observation IDs through financial/provenance/parent-equity tables. Degraded accepted references remain a separate reviewed-repair backlog. This audit does not reconstruct, repair, rewrite or delete those observations.

## What survived the 1,531 ticker iterations

The interrupted Preview contains exactly six native files: `request.json` (488 B), `status.json` (349 B), `progress_stages.json` (1,025 B), `progress_status.json` (762 B), `heartbeat.jsonl` (659 B) and `progress_events.jsonl` (1,098,408 B). No `refresh_preview.json`, `refresh_ticker_changes.json`, `result.json`, completed manifest, raw-history file or acquisition cache exists. The Preview has no Test lane, provider run or candidate database from this attempt. Parent/observer files preserve interruption metadata, not response bodies.

`run_preview` holds `histories[ticker][dimension]` in memory. Full-history acquisition finishes for the whole set before comparison and final artifacts. KeyboardInterrupt escapes its ordinary `except Exception` path; the parent records STOPPED/interrupted. The captured records/envelopes and any successful histories in that process disappear on termination. An empty progress error list does not attest HTTP success: `fetch_complete_history` can return FAILED/INCOMPLETE trust and the loop still emits “Fetched complete-history responses”.

| Classification | Exact retained evidence and unit |
| --- | --- |
| VERIFIED_REUSABLE | **0 complete histories**, 0 complete raw HTTP responses |
| STORED_BUT_NOT_AUTHORITATIVE | **1,531 ticker-completion progress records** plus control artifacts; **0 stored raw histories** |
| INCOMPLETE | **1 Preview run** and its interrupted acquisition iteration; **0 persisted partial response bodies** |
| NOT_RETAINED | Results of **3,062 known returned dimension-history calls**, plus an unquantified possible dimension result in the partial next pair; successful/failed split unknown |

For an unchanged reconstructed scope, a fresh Preview must obtain all **3,620** dimension histories again, not just 558 for the 279 uncompleted tickers. No data is reused in this audit. The exact count of successful histories lost is unknown; it must not be advertised as 3,062 verified successes.

## Historical freeze, source retention and the request categories

`FUNDAMENTALS_HISTORICAL_FREEZE_V1` uses **accepted canonical `period_end <= 2024-12-31`**. It does not filter discovery, add a request date bound, suppress full-history fetch, or prevent initial full-history/provider payload comparison. It checks accepted financial/source/parent-equity authority, routes conflicts into review, and `validate_candidate` protects the final canonical rebuild. Exact reviewed true-removal and WFRD accounting-boundary rules remain separate narrow repair authorities.

The freeze does not imply a filing/update before 2025. An older accounting period can have a later source availability date or `lastupdated`; filtering by filing date or the discovery date is not equivalent to the freeze. Source `reportperiod` is useful diagnostic evidence, but must not replace accepted canonical `period_end` for the freeze decision.

Two other windows are separate: the rolling source-history retention contract and its configured three-year historical source-window review horizon (`2023-11-11` in these runs). `build_source_history_merge` validates absent prefixes/current source coverage and carries exact old retained rows; it does not fetch a special historical repair endpoint. A complete current source window is not necessarily lifetime history. Normal new quarters and recent revisions are still acquired and accepted only through the normal safe Test/Production path. Future revalidations currently repeat acquisition, comparison and freeze checks.

The table below measures **observed ticker associations × two base history calls**, not actual HTTP attempts or disjoint causes. Early-return reviews omit some detailed delta arrays; unknown is not zero. No new completed financial comparison exists for the interrupted attempt.

| Observed category | Latest scheduler Preview: tickers / base-call equivalents | Later completed manual Preview: tickers / equivalents | Interpretation |
| --- | ---: | ---: | --- |
| Total known acquired scope | 1,656 / 3,312 | 1,810 / 3,620 | Actual completed logical history passes; retries unknown |
| ARQ latest-quarter advance | 1,512 / 3,024 | 1,512 / 3,024 | Fresh current-quarter acquisition needed; full-history bytes may be separately optimized only with a new coverage contract |
| Current source-key/payload delta, period diagnostic > cutoff | 1,521 / 3,042 | 1,675 / 3,350 | Freshness/completeness/current-period work; not a pure frozen-only population |
| Historical source-key/payload delta, period diagnostic <= cutoff | 1,521 / 3,042 | 1,675 / 3,350 | Completely overlaps the preceding observed set; cannot count as removable whole requests |
| Current delta without ARQ latest-quarter advance | 9 / 18 | 163 / 326 | Current revisions/payload differences, not necessarily new quarters |
| Frozen conflict held | 405 / 810 | 559 / 1,118 | 380 / 534 also have observed current-key deltas; the other 25 have insufficient key-delta detail |
| Retention/carry-forward/reappearance involved | 1,165 / 2,330 | 1,283 / 2,566 | Overlaps financial changes and holds; not separate extra HTTP requests |
| SOURCE_HISTORY_CHANGE final class | 31 / 62 | 31 / 62 | Required by current complete-history membership/retention contract |
| No effective or metadata-only change final class | 61 / 122 | 61 / 122 | Retrospective equality; not proof those requests were safely skippable beforehand |
| Capture/payload review issue | 17 / 34 | 17 / 34 | Compared evidence issue, not a cache-miss selector |
| Detailed key deltas unavailable | 43 / 86 | 43 / 86 | 30 true-removal, 9 fiscal-revision, 2 untrusted-history and 2 ambiguous-removal early returns |
| Proven exclusively frozen-historical-only request population | **0 established** | **0 established** | Does not assert that no such opportunity exists; available evidence proves no whole-request elimination here |

There are 3,028 added current-period source keys, 912 changed current keys, 2,555 changed historical keys and 29 added historical keys in both completed comparisons. These are row-key counts, not requests. The 1,512 latest-quarter advances are defined on ARQ; 1,138 safe tickers retain `latest_quarter_advanced=true` while their final label becomes HISTORICAL_REVISION. Another 374 advances belong to review cases. A label-only optimization would therefore skip valid newly reported quarters.

There are **zero explicit requests triggered by a history-cache miss** because no such cache lookup exists. Local invalid/ambiguous provider histories are detected after selection/acquisition. Source-key changes, payload regressions and frozen conflicts can lead to future queue-driven requests but are not independently timestamped HTTP categories. Exact mutually exclusive HTTP totals for these reasons are unavailable. Summing this table would double-count the same requests many times.

Safe opportunities differ by resource: skipping routine frozen financial-value comparison could reduce CPU/artifact volume while still retaining and validating source/provenance. A current-period HTTP filter could reduce bytes per response, but one ARQ plus one MRQ query is still two requests. Neither is automatically an HTTP-count or 429 solution, and neither may turn unrequested older rows into source removals.

## Existing pacing and the actual 429 evidence

| Property | Current verified behavior |
| --- | --- |
| Normal Preview concurrency | One sequential network call at a time; ARQ then MRQ per ticker |
| Minimum start interval | 0.5 seconds, one `_PROCESS_REQUEST_LIMITER` pacing clock |
| Sharing | Schema, discovery, full histories, retries and different native clients share the process clock |
| Limiter mutex scope | Protects pacing-clock updates/sleep, not the entire opener/response. Other threads can have overlapping in-flight requests after spaced starts. |
| Retry count / timeout | One retry after initial attempt, two maximum attempts; 30-second opener timeout |
| Retry backoff | Fixed 1 second fallback; numeric Retry-After used, clamped to 0–60 seconds; no exponential backoff or jitter |
| Retry-After limitations | HTTP-date unsupported; values above 60 clipped; zero falls through `or` to fallback. This is not complete adherence to arbitrary server guidance. |
| HTTP 429 | Classified RATE_LIMITED; one permitted retry, then FAILED history trust. Preview does not immediately stop the remaining ticker loop. |
| Per-endpoint / credential-global control | No independent endpoint bucket, durable quota ledger or shared cross-process credential limiter |
| Locks | Native scheduler/admin/production locks exclude their corresponding workflows; direct standalone clients/read-only probes do not acquire these locks |

The incident's retained existing diagnostics—not new audit requests—show unauthenticated `GET /schema/fundamentals` SUCCESS/200 at 16:53:53Z in 0.174 seconds; authenticated `GET /data/fundamentals` with ticker STBA, dimension ARQ, limit 1, then MSFT with the same dimension/limit both returned RATE_LIMITED/429 at 16:54:23Z in 0.157 and 0.498 seconds. These two credential-using probes occurred while the native workflow still owned its locks, demonstrating that the workflow locks are not an account-wide acquisition lock. The three diagnostic requests are separate from the interrupted workflow's unknown total.

No response headers, Retry-After value or response body were retained in those diagnostic receipts. The native traceback shows interruption in `_request`'s retry sleep; it does not retain the request ticker/dimension/header/body or the exact native failure count. Progress gaps STAA→STAG and STAG→STE are 121.537 and 121.274 seconds, versus approximately one second per earlier pair; they are timing evidence, not proof of a specific rate-limit quota or header. No other concurrent account usage is established by this evidence. No requests were made to measure or discover a server limit.

## Design comparison and selected policy

| Strategy | Evaluation |
| --- | --- |
| A. Discovery-first selective acquisition | Already partly implemented. Retain it, preserve dimension/row identity in future discovery evidence, and stop using broad ticker labels as change categories. Current three-field discovery cannot prove complete history equality or removal absence. |
| B. Verified history reuse | Useful for independently sealed, completed acquisition checkpoints under explicit freshness/scope rules. Current legacy provider rows and partial Preview evidence do not qualify. Never replace independently required fresh Test/Production revalidation with an older checkpoint. |
| C. Current-period window | Potential byte/CPU benefit, not automatic request-count benefit. Defer it: current complete-history replacement/removal/retention and binding contracts cannot accept a filtered window as a complete history. |
| D. Interrupted acquisition checkpointing | Primary robustness improvement. Persist each completed native response/history independently before processing the next; failed/incomplete inputs remain diagnostic. Avoid losing every successful response at a later 429. |
| E. Centralized pacing and 429 handling | Primary operational improvement. Credential-scoped process-independent start/in-flight control, actual attempt ledger, server-guided cooldown and fail-fast operation pause/STOP. |

**Recommendation:** one native acquisition plan/receipt path within existing admin run artifacts, used by current discovery/fetch stages, with D+E as the first mechanisms and explicit B reuse only for the Preview acquisition segment. Keep A; do not add a second provider database or caching/version graph. Retain fresh independent financial Test and both Production source checks. Bounded source reevaluation for still-excluded holds is an explicit additional policy decision, not a silent change in acceptance.

### Request and reuse conditions

1. Run normal daily schema/discovery and retain their exact query scope plus dimension/source-key detail where obtained. Discovery is a trigger, not financial acceptance. Preserve the published watermark semantics; any acquisition checkpoint date is separately named and must never advance it.
2. Request complete fresh source history for a known ticker/dimension when there is a new/current financial event, changed identity/schema, stale/missing/unverified history coverage, suspected source membership loss, due source review or explicit operator force. With today's incomplete discovery/cache authority, preserve paired ARQ/MRQ acquisition rather than claiming a dimension is unchanged from absent projected tuples.
3. Reuse OLD accepted observations for exact retained financial/provenance carry-forward under their established rules. Never fabricate capture envelopes, fill missing payload keys, rewrite broken references, or accept disputed incoming data because local storage exists.
4. A completed checkpoint may be reused only within a newly specified Preview-resume freshness policy: native unprojected capture, exact ticker/dimension/filter/limit/schema/normalization/identity, complete response body and row-set validation, no truncation/pagination uncertainty, verified hashes, trusted paths and retained acquisition timestamp. Partial/empty/untrusted responses never become COMPLETE. A stopped Preview does not become execution authorization; build a new bound Preview from eligible inputs.
5. Initial conservative resume policy should allow reuse within the same credential cooldown/acquisition segment and UTC source day, while requiring normal fresh discovery and exact source/identity checks on resume. Crossing that boundary, unresolved freshness, changed discovery evidence or any new revision requires reacquisition. This is a proposed policy change: even same-day timestamps do not prove remote immutability. If the operator requires independently fresh remote evidence for every Preview input, disable cross-invocation reuse and retain checkpoints as diagnostics only. No such policy is implemented here.
6. Still-held cases with no discovery event may wait for an explicit bounded scheduled source recheck, proposed every seven days, with earlier recheck on an operator retry, source/identity/schema change, reviewed repair or relevant new discovery event. They remain pending throughout. Local identity/OLD financial carry-forward/isolation must be reverified on every financial workflow even when remote reevaluation is deferred. Record EXCLUDED_NOT_REACQUIRED truthfully; do not mark the old source evidence fresh or resolve a hold because it was omitted. A missing due-time record defaults to due, not unlimited skipping.
7. Keep WFRD's reviewed boundary acquisition/revalidation and all new/recent financial events on their native path. A pure frozen presentation label does not establish exclusive historical scope or authorize skipping a newly reported quarter. An operator-reviewed historical repair still needs exact independent acquisition and the existing narrow approval/binding contracts.
8. Test and Production must acquire/validate fresh independent source evidence under their established contracts. Any future proposal to use cache/discovery as a substitute for those checks requires a separate explicit freshness/coverage policy change; it is not part of this recommendation's preserved authorization contract.

The held-source deferral in item 6 changes the current requirement to reacquire every unresolved ticker at every source check. It can be safe only while **all its incoming evidence is excluded**, isolation and OLD carry-forward are independently proven, the same policy is included in Preview/Test/Production partitions and no source-dependent approval is inferred. It requires the separately accepted locality/baseline preservation implementation where relevant; that pending implementation is not deployed by this audit. Safe accepted incoming tickers still undergo all independent fresh checks.

### Durable checkpoints and pacing

Add an optional native acquisition sink at the successful unprojected transport boundary. Save the exact received response body before discarding it, with a separate safe receipt containing endpoint, full non-secret query parameters, response status, selected retry/version/date headers if present, credential-scope identifier without the secret, timestamps, byte hash, parsed record hash, source capture policy, schema and completion/coverage result. Seal each completed ticker/dimension item atomically under the existing native run root and use existing artifact manifests/reference verification. Avoid another financial store or a new persistent database; use compact native per-run indexes/references. Existing provider storage is written only through normal accepted candidate publication.

Incomplete bodies and failed transport/status/profile validation may be retained for diagnosis but cannot enter the reusable index. A completed ARQ checkpoint can survive a later failed MRQ; financial authorization still requires coherent evidence for both. A prior complete item must not authorize a different ticker, filter, field projection, generation binding, source contract or age. Record explicit reuse provenance, never a new acquisition timestamp.

Coordinate native requests by credential scope across processes. Keep transport attempt accounting (including retries), schema/discovery/history category, stage, ticker/dimension, result status and cooldown in compact control evidence. Enforce bounded in-flight concurrency and paced starts. Honor numeric and HTTP-date Retry-After as a minimum deadline; if server guidance exceeds the allowed operation wait, save checkpoints and STOP/PAUSE until that deadline instead of shortening it. Use bounded fallback backoff/jitter when guidance is absent. Do not continue thousands of per-ticker retry loops after a shared credential 429. Do not claim that a chosen interval guarantees an undocumented account quota. Background/direct clients using the credential must participate, or coverage must be reported incomplete.

### Defensible reduction estimates

- **Unchanged policy, existing storage:** zero requests proven safely removable immediately. There are no verified cached histories from the incident and no V1-attested rows in active provider storage.
- **Explicit not-due held-source policy, corroborated scope:** 155 queue-only degraded baselines, all absent prior discovery, represent up to **310 of 3,620 base history calls per pass (8.56%)**. Do not include WFRD's two calls, double-count the 171 overlapping baseline population, or skip held tickers with relevant new events. No advance of financial authority is granted. This depends on exact fresh selection, due state, generic isolation/OLD carry-forward and matching revalidation semantics; it is not an already available saving.
- **Checkpointed resume:** only independently verified successful checkpoints would avoid reissuing their matching acquisition calls within the explicitly approved resume freshness window. The incident retained zero such checkpoints, and its successful response count is unknown. The 3,062 returned dimension-call positions quantify lost work, not a guarantee that all 3,062 would be eligible for future reuse.
- **No-effect results:** 61 tickers/122 paired calls are an investigation pool, not an additional promised saving. Discovery/version/coverage evidence is insufficient to preclassify them as unchanged, and WFRD participates independently.
- **Freeze-only elimination/current-window filters:** no positive whole-request saving is established by this trace. Filtering old rows can reduce bytes/CPU while leaving the HTTP call count unchanged.
- **Steady daily volume after safe publication:** unknown from these backlogged stopped runs. Advancing the published watermark through a separately authorized successful workflow should shorten later discovery selection under its existing meaning; no numerical daily reduction is claimed.

Do not sum these overlapping or conditional scenarios. Fresh accepted financial revalidation remains a substantial workload: four unchanged 1,810-ticker passes would require 14,492 base financial-source calls including schema/discovery. Quota/operation-budget planning and a successful resumable acquisition policy must account for this; checkpointing alone does not eliminate independently fresh revalidation requests.

## Exact future implementation scope and acceptance

Proposed source scope, **not changes made by this audit**:

| Module | Narrow future responsibility |
| --- | --- |
| `providers/sharadar.py` | Native response sink, actual attempt receipt, shared credential limiter/cooldown, correct Retry-After handling; preserve unprojected capture boundary |
| `source_capture.py` | Independently verified replay/receipt validation using existing V1 semantics; no legacy attestation or normalized payload reconstruction |
| `admin/refresh_fundamentals.py` | Explicit acquisition plan, durable per-dimension completion, dimension/change-category metadata, safe checkpoint consumption and shared failure STOP |
| `admin/artifacts.py` and existing verified artifact helpers | Atomic native checkpoint manifests and compact references; preserve the accepted compact parent design |
| `admin/refresh_review_queue.py` | Existing queue/audit evidence for source recheck due time and unchanged pending cases, only if the deferred-hold policy is separately accepted |
| `admin/refresh_copy_runtime.py` / `refresh_production.py` | Preserve independent fresh accepted-source checks; bind any explicitly approved deferred-held scope identically and fail on divergence |
| `admin/refresh_scheduler.py` / `ui_service.py` | Expose acquired/reused/deferred/failed/cooldown counts and units through existing controls; no independent provider store or second publication mechanism |

Future focused acceptance must include all of the following; none is claimed implemented by this audit:

1. No relevant discovery change and a valid not-due excluded hold does not trigger an unnecessary full-history request; a missing proof/due state fails to due/reacquire.
2. A new ARQ quarter is acquired even if its final payload class is HISTORICAL_REVISION; current revisions also force acquisition.
3. Frozen-only incoming revisions do not change accepted canonical finances, and existing historical source/provenance is retained.
4. Verified checkpoints replay only their exact complete scope with original capture time; missing/tampered/partial/projected/unverified/stale items fail closed.
5. Interrupt after completed ARQ and after N completed tickers: independently valid items survive, partial next response is ineligible, resume reacquires missing/stale items without inventing success counts.
6. New discovery revision, identity/schema change, age boundary or operator force invalidates reuse. Same date alone is insufficient version proof.
7. Due source reviews recheck remotely; not-due holds stay visible and pending after safe-peer watermark advancement. No omitted hold resolves or gains approval.
8. Shared 429 pauses/stops the operation with durable checkpoints and bounded retries; numeric, HTTP-date, zero, long and malformed Retry-After cases are covered without retrying before a valid server deadline.
9. Multiple processes sharing a credential obey the same in-flight/start/cooldown controls; unrelated credentials remain isolated; every actual retry is counted.
10. V1 raw fields, null-versus-absent states, source identity and coverage checks are unchanged; legacy local rows are never relabeled as fresh captures.
11. Fresh Test and both Production source checks remain independent. Stale/changed scopes, safe/held collisions and authorization/hash mismatches fail before publication.
12. Safe peers publish through native immutable generations while all held incoming evidence remains excluded and complete OLD economic/provenance authority is preserved, including discovery-absent degraded baselines.
13. Publication dates, WFRD boundary decisions, P/B published-state use, three-role verification, ordinary rollback and crash recovery/RETRY_REQUIRED retain their existing native tests.
14. Compact parent progress and Run History stay bounded with large source checkpoints; full response bodies remain native child artifacts, not repeated parent embeddings.
15. Read-only Preview/source cache reads never mutate active provider/canonical/analysis, the publication journal or the financial watermark. No full suite is required for this targeted implementation boundary.

STOP future optimization if completeness/identity/freshness cannot be proved, a partial window is being treated as complete, a legacy record is being attested, historical source would be deleted/repaired, held incoming data becomes authoritative, due review evidence disappears, scopes diverge, shared source failure persists, or native generation/recovery safety fails. Unknown server quota or missing acquisition ledger must not be replaced by an assumed limit.

## Audit diagnostics and non-mutation

Verified offline diagnostics: **34 existing targeted tests PASS** covering the Sharadar transport/status/retry/limiter, structural full-history completeness, unprojected authority, inclusive discovery, exact-limit partitioning and payload fingerprint/binding behavior. Additional no-network probes verify that discovery collapses different source keys into ticker/dimension/day tuples, a 429 returns FAILED trust rather than immediately raising from the fetch helper, numeric 120-second Retry-After is clipped to 60, and HTTP-date Retry-After is unsupported. Live acquisition calls in this audit: **0**. Full test suite: **not run**.

Read-only SQL inventoried actual storage and queue populations. Native progress and completed ticker comparisons were streamed into small audit projections. No data was reused as financial authority, no pending implementation was deployed, and no StockCore/OHLCV file, backup, scheduler setting or publication state was changed. The final read-only hash audit at `2026-11-11T17:44:29.348760+00:00` verified all nine protected files byte-for-byte equal to the initial snapshot and the active generation unchanged. Source/test files have no diff from accepted HEAD, both governing prerequisites remain ancestors, and the pending implementation patch retains its recorded SHA-256. The audit is complete with the explicitly documented transport-count and interrupted-membership evidence gaps.

Only this audit document is intended for the required documentation commit. Runtime state, temp evidence, large artifacts, archived implementations and unrelated worktree changes are excluded. No push is authorized or performed.
