# Price Target Event Research V1 — 2026-10-14

Decision: **PRICE_TARGET_EVENT_RESEARCH_V1_READY**. The live bounded export succeeds with exact publication anchoring, 57 focused research tests pass, two independent live reruns produce identical CSV bytes, and all production input hashes remain unchanged. This is research-engine readiness, not evidence of predictive return performance.

## Contract and scope

New narrow modules: `rawcandle/research/price_target_event_research.py` and `rawcandle/cli/price_target_event_research.py`; focused coverage: `tests/test_price_target_event_research.py`. Acquisition, persistence/schema, fiscal linker, validated fiscal-revision code, publication authority, schedulers, scoring and trading code are unchanged. Optional fiscal-revision context is omitted to keep price-target research independently valid.

Current active canonical generation: `refresh_20261014T095401Z_refresh_fundamentals_43db1c8371f6_production_6917d617`, resolved with `resolve_requested_role_path('canonical', ...)`, not the legacy file. Price-target history spans `2026-09-27T16:27:26.884221Z` through `2026-10-14T12:01:57.494474Z` (18 UTC collection dates). All persisted family attempts establish the available window; only successful snapshot-bearing fetches provide values. Semantic snapshots are dereferenced for each observation, including SUCCESS_UNCHANGED. currentPrice-only snapshot novelty is never a target revision.

Events come from VERIFIED canonical publication authority within that complete timestamp window, projected through the existing DailyResearchPublicationService with no Yahoo or heuristic provider. All 28 current events project to EXACT, with HIGH confidence and SEC_8K_ITEM_2_02 provenance. Events require an unambiguous current active security; no ambiguous/missing active-security event is present in this run. Exclusion counts are explicit in metadata. Forecast values are grouped by persisted company_id/security_id, not joined on ticker alone. Current tickers are output labels and OHLC routes, not permanent identity.

Publication authority is used retrospectively to label events; its later verification timestamp is not treated as the publication timestamp or a fact known at forecast acquisition. `source_availability_date` is retained only as diagnostic context. Every row includes the selected publication evidence ID and PRE/POST fetch/snapshot IDs.

## Numeric revision, PRE/POST and missing-data rules

Target vector = (mean, median, high, low), using existing normalized statistic names. A numeric difference requires the same statistic to be finite numeric at both endpoints and have unequal values. Formatting, currentPrice, unchanged repeats and availability-only changes do not qualify. Field states and original numeric text are retained in PRE/POST state JSON. No zeros are synthesized. Normalized analyst target counts do not exist in this contract; numberOfAnalystOpinions is not fabricated from raw/excluded fields.

PRE is the latest numeric-usable actual acquisition strictly before the exact publication instant. POST is strictly after. Equal-timestamp observations are excluded from both and counted explicitly. A usable vector has at least one finite numeric target. No PRE means NO_PRE_TARGET and no invented first revision. With PRE, first revision is the first later observed vector with at least one comparable numeric statistic differing from that PRE vector. Unchanged POST fetches are skipped. A null intermediate value does not prevent a later finite value from being compared against the actual PRE baseline.

Revision absolute/percentage changes are computed independently for all four statistics when endpoints exist. Percentages require baseline ≥1e-8 and nonnegative after-value, and are null for flagged events. Absolute values remain evidence even when interpretation is unsafe. Missing mean is never silently replaced by median/high/low. Event labels are descriptive: NO_PRE_TARGET, NO_POST_REVISION_YET, POST_REVISION_UP/DOWN/MIXED, POST_REVISION_FLAT_OR_NON_MEAN_CHANGE, or ANOMALY_REVIEW. Mixed means comparable vector components moved in opposite directions; mean direction summaries still count the actual mean movement.

## Timing, lookback and follow-through

All strict event ordering and elapsed hours use UTC instants. Calendar-day lag and the October subset use America/New_York dates, matching the existing market-calendar convention. Thus MU’s 2026-10-01T00:02:22Z event belongs to September 30 locally. UTC October would instead contain 19 events / 16 with revisions; the documented New York October subset is 18 / 15. This timezone choice is fixed, not optimized.

First revision time means FIRST OBSERVED acquisition evidence, not exact analyst action or Yahoo update time. Observed-session lag is supplied only when actual ticker OHLC history reaches the acquisition date. No intraday change time is interpolated.

PRE trend compares numeric mean directions across adjacent usable observations acquired in [publication − 7×24h, publication). At least one comparable pair is required: all unchanged → FLAT; only increases → RISING; only decreases → FALLING; both → MIXED; otherwise INSUFFICIENT_HISTORY. Missing means do not create zero changes or substitute another field. Limited lookback history is not claimed to be a complete seven-day sample.

Checkpoints use the latest actual POST observation at or before publication +1×24h / +3×24h / +7×24h. They are elapsed-day windows, not end-of-calendar-day buckets. Each compact checkpoint JSON includes usable/window_complete, fetch/snapshot provenance, original field states, all four values and changes versus PRE. No PRE value is carried forward as a fake POST observation. The CSV also exposes latest_1d_mean/latest_3d_mean/latest_7d_mean.

post_result_revision_count_7d counts adjacent numeric target-vector transitions first observed in (publication, publication +7×24h], seeded with the real PRE observation when present. Null-to-numeric availability alone does not count. This adjacent-transition count differs deliberately from first revision’s comparison to PRE. Windows ending after the available history are marked incomplete: 17 complete and 11 right-censored event windows in this run. None-observed-yet is not evidence that no future revision will occur.

## Conservative anomaly guard

SCALE_CHANGE_REVIEW flags a positive numeric mean ratio ≥5× or ≤0.2×. It is an explicit starting review rule, not a split detector or optimized threshold. Negative/nonfinite/malformed numeric targets, inverted high/low ranges and observed currency changes also receive explicit quality flags. Evidence is preserved. Anomalies are inspected in the PRE lookback, first revision, adjacent first-seven-day transitions and checkpoint comparisons. A later flagged transition suppresses earlier percentage summaries for that event too. Flagged events remain exported but are excluded from ordinary mean-direction summaries.

No current exact-publication event is anomaly flagged. A separately inspected persisted GUTS mean transition from 5.03333 at 2026-10-04T11:25:06.902944Z to 60.40002 at 2026-10-05T11:25:08.470678Z is approximately 12.00001× and meets SCALE_CHANGE_REVIEW. GUTS is outside this exact publication cohort; no synthetic publication event was introduced to include it. No corporate action or split cause was externally researched or asserted.

## Full cohort and October results

| Measure | Full history | October (New York publication date) |
| --- | --- | --- |
| Publication events | 28 | 18 |
| PRE target available | 27 | 17 |
| First numeric POST revision / PRE+POST | 24 | 15 |
| No revision yet with PRE | 3 | 2 |
| No PRE target | 1 | 1 |
| Anomaly flagged | 0 | 0 |
| Mean target raised | 9 | 4 |
| Mean target lowered | 15 | 11 |
| Non-mean-only numeric revision | 0 | 0 |
| Median first revision lag (hours) | 24.57256263958333 | 21.217467899444443 |

| First revision calendar-day lag | Full | October |
| --- | --- | --- |
| 0–1d | 13 | 9 |
| 2–3d | 9 | 4 |
| 4–7d | 2 | 2 |
| >7d | 0 | 0 |

| PRE mean trend | Full | October |
| --- | --- | --- |
| RISING | 4 | 1 |
| FALLING | 8 | 7 |
| MIXED | 1 | 1 |
| FLAT | 14 | 8 |
| INSUFFICIENT_HISTORY | 1 | 1 |

The full cohort contains 24 revisions and four events without a first revision: three with PRE (NEOG, PRGS, WS) and one without numeric PRE (SMXT). October contains 15 revisions and three without: NEOG/WS with PRE and SMXT without. There are zero exactly-equal publication/fetch timestamps in the production cohort.

| Ticker / FY/FQ | Publication UTC | PRE mean → first changed mean | Mean % | First changed fetch UTC | Lag hours | 7d revisions | PRE trend |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AIR 2027/Q1 | 2026-09-28T20:58:22Z | 144.8 → 150.25 | 3.7638121546961245 | 2026-09-30T11:02:27.916458Z | 38.068 | 2 | FALLING |
| ANGO 2027/Q1 | 2026-10-08T15:17:49Z | 20.0 → 19.75 | -1.25 | 2026-10-14T11:04:48.058654Z | 139.783 | 1 | FLAT |
| APLD 2027/Q1 | 2026-10-08T00:43:31Z | 65.36667 → 64.56667 | -1.2238653123985008 | 2026-10-08T11:04:50.632492Z | 10.355 | 3 | FALLING |
| APOG 2027/Q2 | 2026-10-06T17:44:57Z | 44.0 → 45.5 | 3.4090909090909087 | 2026-10-08T11:04:53.634894Z | 41.332 | 1 | FLAT |
| BYRN 2026/Q3 | 2026-10-08T16:10:10Z | 6.83333 → 6.66667 | -2.4389280189892815 | 2026-10-09T11:10:14.223417Z | 19.001 | 2 | FLAT |
| CAG 2027/Q1 | 2026-09-30T11:32:13Z | 14.44375 → 14.38125 | -0.43271311120726963 | 2026-10-01T11:10:47.147116Z | 23.643 | 2 | RISING |
| CALM 2027/Q1 | 2026-09-30T10:07:27Z | 75.0 → 72.5 | -3.3333333333333335 | 2026-10-01T11:10:53.163661Z | 25.057 | 2 | FLAT |
| CCL 2026/Q3 | 2026-09-29T13:16:12Z | 33.98846 → 34.02692 | 0.11315605355462853 | 2026-09-30T11:10:41.071188Z | 21.908 | 3 | FLAT |
| CNXC 2026/Q3 | 2026-09-30T00:10:45Z | 36.25 → 36.0 | -0.6896551724137931 | 2026-10-01T11:13:50.466815Z | 35.052 | 2 | FLAT |
| DAL 2026/Q3 | 2026-10-09T14:30:47Z | 101.27083 → 101.47917 | 0.20572557764164928 | 2026-10-10T11:16:17.732776Z | 20.759 | 3 | FALLING |
| DPZ 2026/Q3 | 2026-10-13T14:05:16Z | 373.14816 → 372.03705 | -0.29776644215530806 | 2026-10-14T11:18:18.884438Z | 21.217 | 1 | FALLING |
| HOVR 2027/Q1 | 2026-10-09T15:24:51Z | 8.2395935 → 8.227164 | -0.15085088845705372 | 2026-10-10T11:26:32.094461Z | 20.028 | 4 | MIXED |
| IDT 2026/Q4 | 2026-09-28T20:31:47Z | 75.0 → 85.0 | 13.333333333333334 | 2026-10-01T11:28:19.004645Z | 62.942 | 1 | FLAT |
| KMX 2027/Q2 | 2026-09-29T11:00:30Z | 57.15385 → 62.61538 | 9.555839195434784 | 2026-10-01T11:31:29.817446Z | 48.517 | 1 | FLAT |
| LEVI 2026/Q3 | 2026-10-08T00:12:53Z | 27.53333 → 27.33333 | -0.7263923397569393 | 2026-10-08T11:32:20.064964Z | 11.324 | 3 | FALLING |
| LW 2027/Q1 | 2026-10-06T16:02:01Z | 54.33333 → 55.90909 | 2.900171957065769 | 2026-10-07T11:33:52.223388Z | 19.531 | 3 | FLAT |
| MKC 2026/Q3 | 2026-10-01T11:31:11Z | 60.07692 → 58.46154 | -2.6888528905942612 | 2026-10-02T11:36:27.287344Z | 24.088 | 2 | FLAT |
| MTN 2026/Q4 | 2026-09-28T20:06:47Z | 144.76923 → 143.84615 | -0.6376216824528244 | 2026-09-30T11:37:02.169598Z | 39.504 | 1 | FLAT |
| MU 2026/Q4 | 2026-10-01T00:02:22Z | 1520.7609 → 1533.8043 | 0.8576890686760831 | 2026-10-01T11:38:02.222183Z | 11.595 | 4 | RISING |
| NEOG 2027/Q1 | 2026-10-07T00:05:19Z | 14.0 →  | — | — | — | 0 | RISING |
| NKE 2027/Q1 | 2026-10-01T20:15:15Z | 45.62778 → 40.51667 | -11.201750337184942 | 2026-10-03T11:38:37.882834Z | 39.39 | 4 | FALLING |
| PEP 2026/Q3 | 2026-10-08T01:57:44Z | 148.63635 → 146.31818 | -1.559625219537469 | 2026-10-09T11:43:17.834130Z | 33.759 | 3 | FALLING |
| PRGS 2026/Q3 | 2026-09-30T20:07:19Z | 56.2 →  | — | — | — | 0 | RISING |
| RGP 2027/Q1 | 2026-10-08T00:05:26Z | 5.66667 → 6.5 | 14.705814878932427 | 2026-10-13T11:47:20.217293Z | 131.698 | 1 | FLAT |
| RPM 2027/Q1 | 2026-10-06T14:53:29Z | 129.8 → 126.33333 | -2.6707781201849055 | 2026-10-07T11:47:54.952410Z | 20.907 | 5 | FLAT |
| SMXT 2026/Q2 | 2026-10-10T01:05:28Z |  →  | — | — | — | 0 | INSUFFICIENT_HISTORY |
| STZ 2027/Q2 | 2026-10-07T00:18:54Z | 162.04349 → 153.91304 | -5.017449327955104 | 2026-10-08T11:52:30.686074Z | 35.56 | 2 | FALLING |
| WS 2027/Q1 | 2026-10-07T14:30:19Z | 46.0 →  | — | — | — | 0 | FLAT |


## Precise comparison with the 31 / 25 / 23 quick study

The prior quick study used October Sharadar source-availability dates: 31 result tickers, 25 with any lifetime target revision, and 23 with an October numeric revision on/after the source date. The forecast DB hash still equals that study’s source hash, so newer observations do not explain this comparison. This V1 changes the event boundary to exact publication timestamps and counts actual numeric target evidence relative to the latest strict PRE state.

| Disposition of the original 31 tickers | Count | Tickers |
| --- | --- | --- |
| BEFORE_HISTORY | 7 | COST, CTAS, DRI, EBF, KBH, LEN, SNX |
| EXACT_OCTOBER_COHORT | 18 | ANGO, APLD, APOG, BYRN, DAL, DPZ, HOVR, LEVI, LW, MKC, NEOG, NKE, PEP, RGP, RPM, SMXT, STZ, WS |
| NO_VERIFIED_TIMESTAMP | 4 | HELE, SEGG, TLRY, WOR |
| SEPTEMBER_IN_FULL_COHORT | 2 | CNXC, MU |

The 18 exact New York October events are therefore a narrower, independently defined population than 31 October source-date rows. The eight earlier quick-study post-result tickers outside that exact October population are CNXC, COST, DRI, HELE, KBH, LEN, MU and TLRY. Removing those from the earlier 23 leaves 15, matching current exact-October revision coverage. This equality does not make their timing definitions interchangeable.

Seven source-October results were publicly released before forecast history began; four lack VERIFIED exact authority; CNXC and MU were September events locally. APLD’s October 7 source-date revision precedes its exact publication instant; the proper strict PRE already contains that state and the first qualifying POST is October 8. WS’s availability date is October 13 but exact publication is October 7. These differences explain shifted timing buckets without inventing result timestamps.

| Diagnostic ticker | Sharadar source date | Exact publication UTC | Disposition |
| --- | --- | --- | --- |
| APLD | 2026-10-07 | 2026-10-08T00:43:31Z | EXACT_OCTOBER_COHORT |
| CNXC | 2026-10-07 | 2026-09-30T00:10:45Z | SEPTEMBER_IN_FULL_COHORT |
| LEVI | 2026-10-07 | 2026-10-08T00:12:53Z | EXACT_OCTOBER_COHORT |
| MU | 2026-10-09 | 2026-10-01T00:02:22Z | SEPTEMBER_IN_FULL_COHORT |
| WS | 2026-10-13 | 2026-10-07T14:30:19Z | EXACT_OCTOBER_COHORT |


## Persisted-history QA examples

The following samples were independently reread from forecast_fetch and forecast_price_target, checking latest strict PRE, the absence of an earlier qualifying POST, and every adjacent numeric transition in the seven-day window. This check used stored normalized target values directly, not currentPrice or snapshot insertion counts.

| Case | PRE UTC / mean | First changed POST UTC / mean | 7d numeric changes |
| --- | --- | --- | --- |
| CCL | 2026-09-29T11:10:40.507779Z / 33.98846 | 2026-09-30T11:10:41.071188Z / 34.02692 | 3 |
| APLD | 2026-10-07T11:04:49.803731Z / 65.36667 | 2026-10-08T11:04:50.632492Z / 64.56667 | 3 |
| RPM | 2026-10-06T11:48:01.748898Z / 129.8 | 2026-10-07T11:47:54.952410Z / 126.33333 | 5 |
| NEOG | 2026-10-06T11:38:23.527612Z / 14.0 | None / None | 0 |

CCL: immediate increase, 33.98846 → 34.02692, high/low/median unchanged. APLD: immediate decrease, 65.36667 → 64.56667, high/low/median unchanged. RPM: 129.8 → 126.33333 at first revision, five genuine target-vector transitions within seven days. NEOG: mean/median/high/low stay 14 and no numeric target change follows publication. Fetch/snapshot identifiers for these exact states are retained in CSV. The supplementary GUTS scale move and synthetic focused tests cover anomaly handling even though no cohort row currently triggers it.

## Outcomes

Reuses the existing DailyResearchPublicationService first-full-post-result-trading-date boundary and the existing OHLC loading, observed-index _at and percentage _pct helpers. D0 is that first full post-result observed session. D5/D20/D30/D60 use the ticker’s observed session offsets from D0; returns are percent changes from the D−1 close, matching existing event-window return_D* semantics. D30/D60 are narrow local offset attachments; no shared OHLC/fiscal logic was changed.

| Outcome available with numeric return | Full | October |
| --- | --- | --- |
| D0 | 27 | 17 |
| D5 | 12 | 2 |
| D20 | 0 | 0 |
| D30 | 0 | 0 |
| D60 | 0 | 0 |

Unavailable outcomes remain null and have explicit status: PENDING_D0, MISSING_D0, BOUNDARY_UNAVAILABLE, PENDING_FOLLOWUP or MISSING_PRICE. DPZ’s first full session is not in available OHLC yet, so its D0 is pending, not fabricated. Observed sessions are not a complete exchange-calendar guarantee: gaps can affect elapsed-session offsets. No return model, correlation test, significance claim or trading score is produced.

## Validation and database safety

Focused command: `python3 -m pytest -q tests/test_price_target_event_research.py tests/test_forecast_revision_research.py` → **57 passed in 6.07s, exit 0**, with repository database guards enabled. This is 23 new price-target tests plus the 34 existing fiscal-revision tests. No unrelated Fundamentals/DC/valuation suite ran.

Coverage includes currentPrice-only/unchanged fetch exclusion; each target statistic; latest PRE/first changed POST; all five PRE trend states; null/availability-only semantics; strict equality ordering; seven-day windows; missing PRE/post; scale and invalid-value evidence/percentage suppression; 30/60 observed offsets; pending D0; deterministic runs; read-only SQL connections; input-overwrite prevention; and fail-closed source-hash drift before artifact output.

Two live CLI exports, including independent return attachment, are byte-identical. Both engine before/after hash guards pass; all three quick_check results are ok. Task-wide explicit baseline/post hashes match. The fiscal-revision module’s SHA-256 matches its pre-task value. Generation pointer, both scheduler configurations, forecast scheduler source and production linker sources also match their pre-task hashes. No scheduler/systemd command was issued and no production write connection was opened.

| Production input | Pre = post SHA-256 |
| --- | --- |
| data/forecasts.db | 167a7a8d4ff1ad7b318e708e422ef00fca02bec118f3ab8587a9060129967638 |
| /home/kalle/projects/rawcandle/data/fundamentals_generations/refresh_20261014T095401Z_refresh_fundamentals_43db1c8371f6_production_6917d617/fundamentals_v4.db | aec33d93fdcb060c8986a4b5fa6fbb8d70bf8aa94cc3da909c993f66239c64fa |
| data/osakedata.db | cfc0ee127cf080a5fbfdc7f550f1b64569fa73656cd45a48b19f159e004429f4 |


No legitimate concurrent-writer exception was needed in the accepted runs. Source drift would raise SOURCE_DATABASE_CHANGED_DURING_RESEARCH before CSV/metadata writes; the focused test asserts this behavior. CSV/metadata output paths cannot overwrite input DBs, must use .csv/.json extensions, and cannot write inside the repository production data directory.

## Reproduction and artifacts

```bash
python3 -m rawcandle.cli.price_target_event_research \
  --forecasts-db data/forecasts.db \
  --canonical-db data/fundamentals_v4.db \
  --ohlc-db data/osakedata.db \
  --output exports/forecasts/price_target_event_research_v1_2026-10-14.csv \
  --metadata-output /tmp/price_target_event_research_v1.metadata.json
```

CSV: `exports/forecasts/price_target_event_research_v1_2026-10-14.csv`; 28 event rows; 93,157 bytes; SHA-256 `bcb9ecdc3df87b4e822c5be5f0657340d3f49833b1a108d120a8b4b93c7f6a11`. The bounded CSV contains compact checkpoints, not raw provider payloads. Temporary metadata records source paths/hashes, exact exclusions, summary populations and output hash; this report retains the accepted measurements and provenance. Output ordering and content are deterministic for identical inputs. Unrelated pre-existing workspace changes were untouched.

## Limitations and exact next step

This is 18 daily collection dates and 24 observed first revisions, not a mature revision-versus-return dataset. Multiple targets and windows for one event are correlated observations. Current active ticker routing, retrospective authority and observed OHLC gaps limit inference. Absence of a flagged ≥5× move does not prove that smaller corporate-action/unit effects are absent. Incomplete windows and provider availability transitions must not be treated as flat consensus. Mean direction is descriptive and may reflect changed analyst composition, which is not normalized here.

Exact next step: keep passive collection unchanged, then assess whether the exact-event cohort and D5/D20/D30/D60 follow-up are sufficient for a bounded revision-versus-return study. Do not fit a model, optimize review thresholds, or create a score from this V1 export.

**PRICE_TARGET_EVENT_RESEARCH_V1_READY**
