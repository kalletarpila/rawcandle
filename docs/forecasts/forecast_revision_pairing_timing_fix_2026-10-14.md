# Forecast revision pairing and timing fix — 2026-10-14

Decision: **FORECAST_REVISION_PAIRING_FIX_NEEDS_REVISION** — the code correction and frozen-input 27-event QA succeed, but live production OHLC changes during validation. All 34 focused test assertions pass; the repository production-file safety guard makes pytest exit 1. The live research rerun also fails closed with SOURCE_DATABASE_CHANGED_DURING_RESEARCH. The required unchanged-production-OHLC acceptance gate is therefore outstanding. Do not describe this as a clean live validation.

## Narrow change

Only `rawcandle/research/forecast_revision_research.py` and `tests/test_forecast_revision_research.py` changed in source. No collection, persistence, database schema, production linker, future-quarter rule, publication authority, scheduler, price-target research or scoring code was changed. Production database connections use mode=ro and query_only. No historical links were rerun or reconciled.

`reconstruct_fetch` now carries the provider endDate from the selected immutable normalized occurrence, retaining all existing AS_KNOWN identity/rule-version/knowledge-cutoff checks. Conflicting dates inside an occurrence become missing continuity evidence. Canonical fiscal identity still comes exclusively from fetch-specific linked FY/FQ. Provider endDate never creates a fiscal target or canonical quarter ID.

The existing latest PRE +1q / earliest POST 0q candidate selection is preserved. It is not advanced past a bad candidate to enlarge the validated cohort. `validate_pair` requires reconstructed target equality, then produces one of four controlled states:

| State | Meaning | Included in strict comparable counts |
| --- | --- | --- |
| VALIDATED_PROVIDER_DATE_MATCH | Both provider dates present and equal; reconstructed targets equal | Yes |
| REJECT_PROVIDER_DATE_MISMATCH | Both dates present but differ; reconstructed targets equal | No |
| PROVISIONAL_PROVIDER_DATE_MISSING | One or both dates missing; reconstructed targets equal | No |
| NO_PAIR | Candidate unavailable or reconstructed targets differ | No |

Raw PRE/POST values, fetch/link/snapshot/resolution evidence and dates are retained for every candidate. Rejected/provisional pairs have null EPS/revenue revisions, analyst-count deltas and range deltas; they do not enter revision summary distributions. Checkpoints also require validated date continuity. Existing numerical percentage-denominator guards are unchanged.

## Provider timing separated from linker timing

`provider_rollovers` groups observations by fetch and compares consecutive numeric-usable 0q occurrences, independent of the FY/FQ currently assigned to them. Equal dates produce no episode. Forward dates produce FORWARD_MATCHED_PLUS1Q or FORWARD_NO_PLUS1Q_MATCH; backward dates produce BACKWARD_DATE_REGRESSION and are never forward rollovers. The +1q check uses the immediately preceding usable 0q fetch, with one numeric-usable +1q whose date equals the new 0q date. An older matching +1q is not substituted. Missing dates and duplicate 0q occurrences break continuity. Failed/no-data fetches supply no usable estimate.

For an event, the provider forward episode is anchored to old 0q dates observed on the reported target before publication and, when available, the PRE candidate’s provider date for the new target. Only POST_RESULT episodes supply event rollover timing. This checks provider continuity without reassigning fiscal identity. Earlier provider rollovers remain observable even when a later candidate is rejected.

Output adds explicit pair QA, provider old/new dates, last-old/first-new fetches, +1q continuity, `linker_transition_at`, `linker_transition_status`, and `timing_basis`. Legacy transition timestamps/delays now prefer the provider rollover; the linker timestamp remains diagnostic. A linker-only identity change with unchanged provider date uses LINK_IDENTITY_CHANGE_ONLY and no provider-rollover fields. No available event transition uses NONE. Consumers must check timing_basis before interpreting a delay.

The true provider update lies in (last old observation, first new observation]; daily acquisition does not identify the exact analyst/provider update time. Revision-value endpoints remain the original fiscal-identity-qualified candidate fetches; first provider rollover timing may precede the POST candidate’s later linker-qualified fetch. These are deliberately distinct measurements.

## AIR, MU and NKE regression evidence

| AIR fact | Corrected result |
| --- | --- |
| Publication UTC | 2026-09-28T20:58:22Z |
| Last old provider 0q UTC | 2026-09-28T11:02:21.626036Z |
| First new provider 0q UTC | 2026-09-29T11:02:26.051928Z |
| Provider old → new date | 2026-08-31 → 2026-11-30 |
| Immediately preceding +1q matches new 0q | True |
| Publication → first provider observation | 14.067792202 hours |
| Later linker identity change UTC | 2026-10-02T11:03:13.828041Z |
| Publication → later linker observation | 86.081063345 hours |
| Timing basis | PROVIDER_0Q_ROLLOVER |
| Pair status | VALIDATED_PROVIDER_DATE_MATCH |

| Rejected ticker | PRE fiscal target / provider date | POST fiscal target / provider date | Status |
| --- | --- | --- | --- |
| MU | 1494/2027/Q1 / 2026-11-30 | 1494/2027/Q1 / 2026-08-31 | REJECT_PROVIDER_DATE_MISMATCH |
| NKE | 1545/2027/Q2 / 2026-11-30 | 1545/2027/Q2 / 2026-08-31 | REJECT_PROVIDER_DATE_MISMATCH |

Both rejected candidates retain the 2026-11-30 → 2026-08-31 contradiction. Each also retains its earlier genuine forward provider rollover separately. Neither contributes a validated same-target revision metric. Regression fixtures use local IDs and reproduce AIR’s exact timing and MU/NKE’s fiscal/date contradictions without editing production evidence.

## Same bounded 27-event cohort

The source forecasts DB is current and includes October 14 collection. Two optional history-bound arguments restrict the actual research input to the original reviewed history: **2026-09-27T16:27:26.679445Z through 2026-10-13T12:01:55.287946Z, inclusive**. The bounds apply to both cohort determination and reconstruction; October 14 observations cannot change the candidate or transition selection. The 27 stable (company_id, fiscal_year, fiscal_quarter) identities were compared with the committed October 14 state cohort and are identical.

Pinned canonical generation: `refresh_20261014T095401Z_refresh_fundamentals_43db1c8371f6_production_6917d617`. Current exact publication authority was projected using the existing exporter, Yahoo mode none, no heuristic provider, same companies, and the original history lower bound. All 27 overlapping rows are EXACT. Publication input CSV SHA-256: `cc0dc5e7d193aa03f888aa0c7234b9fe06626c2a515a33a073739a7bdb36f17c`. No authority was enriched or changed. Current production authority is used retrospectively to label the events; forecast values remain acquisition-specific PIT evidence.

| Measure | Corrected count |
| --- | --- |
| Exact publication-overlap events | 27 |
| PRE available | 26 |
| POST available | 25 |
| Both PRE and POST | 25 |
| Nominal candidate pairs | 25 |
| Validated provider-date-match pairs | 23 |
| Rejected provider-date mismatches | 2 |
| Provisional missing-date pairs | 0 |
| NO_PAIR events | 2 |
| Event-associated provider forward rollovers | 25 |
| Event forward rollovers with immediately prior +1q match | 25 |
| Forward episodes across full histories of the 27 cohort companies | 32 |
| Matched forward episodes across those histories | 27 |
| Backward date-regression episodes across those histories | 7 |
| Linker identity-change events | 25 |
| Linker-only event transitions | 0 |
| D5 available, full cohort | 12 |
| D20 available, full cohort | 0 |
| D5 available, quality-approved pairs | 10 |
| Quality-approved cohort size | 23 |

Episode counts include repeated forward/backward moves within one company’s history and are not independent publication-event counts. The 32/27/7 episode totals are deliberately scoped to the 27 cohort companies, unlike the prior whole-universe 74/37/12 counts. SMXT has no usable pair; WS has PRE only under existing identity-qualified reconstruction.

| Ticker / reported FY/FQ | Pair validation | Provider first-new observation UTC | Linker identity-change UTC | D5 / D20 |
| --- | --- | --- | --- | --- |
| AIR 2027/Q1 | VALIDATED_PROVIDER_DATE_MATCH | 2026-09-29T11:02:26.051928Z | 2026-10-02T11:03:13.828041Z | True / False |
| ANGO 2027/Q1 | VALIDATED_PROVIDER_DATE_MATCH | 2026-10-09T11:04:38.715344Z | 2026-10-10T11:04:31.274364Z | False / False |
| APLD 2027/Q1 | VALIDATED_PROVIDER_DATE_MATCH | 2026-10-08T11:04:50.133223Z | 2026-10-09T11:05:01.251303Z | False / False |
| APOG 2027/Q2 | VALIDATED_PROVIDER_DATE_MATCH | 2026-10-07T11:04:52.290530Z | 2026-10-09T11:05:04.246478Z | False / False |
| BYRN 2026/Q3 | VALIDATED_PROVIDER_DATE_MATCH | 2026-10-09T11:10:13.722551Z | 2026-10-10T11:10:06.245982Z | False / False |
| CAG 2027/Q1 | VALIDATED_PROVIDER_DATE_MATCH | 2026-10-01T11:10:46.647095Z | 2026-10-02T11:10:47.297946Z | True / False |
| CALM 2027/Q1 | VALIDATED_PROVIDER_DATE_MATCH | 2026-10-01T11:10:52.669038Z | 2026-10-02T11:10:53.290317Z | True / False |
| CCL 2026/Q3 | VALIDATED_PROVIDER_DATE_MATCH | 2026-09-30T11:10:40.576926Z | 2026-10-02T11:11:26.318461Z | True / False |
| CNXC 2026/Q3 | VALIDATED_PROVIDER_DATE_MATCH | 2026-09-30T11:13:04.875671Z | 2026-10-09T11:13:31.862805Z | True / False |
| DAL 2026/Q3 | VALIDATED_PROVIDER_DATE_MATCH | 2026-10-10T11:16:17.242808Z | 2026-10-11T11:16:18.030803Z | False / False |
| HOVR 2027/Q1 | VALIDATED_PROVIDER_DATE_MATCH | 2026-10-10T11:26:31.586106Z | 2026-10-11T11:26:32.563374Z | False / False |
| IDT 2026/Q4 | VALIDATED_PROVIDER_DATE_MATCH | 2026-09-29T11:27:32.510459Z | 2026-10-02T11:28:17.207014Z | True / False |
| KMX 2027/Q2 | VALIDATED_PROVIDER_DATE_MATCH | 2026-09-30T11:30:44.392683Z | 2026-10-02T11:31:30.313147Z | True / False |
| LEVI 2026/Q3 | VALIDATED_PROVIDER_DATE_MATCH | 2026-10-08T11:32:19.563045Z | 2026-10-09T11:32:32.784056Z | False / False |
| LW 2027/Q1 | VALIDATED_PROVIDER_DATE_MATCH | 2026-10-07T11:33:51.713275Z | 2026-10-09T11:34:07.407305Z | False / False |
| MKC 2026/Q3 | VALIDATED_PROVIDER_DATE_MATCH | 2026-10-02T11:36:26.803159Z | 2026-10-02T11:36:26.803159Z | True / False |
| MTN 2026/Q4 | VALIDATED_PROVIDER_DATE_MATCH | 2026-09-29T11:37:00.858233Z | 2026-10-02T11:37:48.223122Z | True / False |
| MU 2026/Q4 | REJECT_PROVIDER_DATE_MISMATCH | 2026-10-01T11:38:01.712363Z | 2026-10-11T11:37:30.434457Z | True / False |
| NEOG 2027/Q1 | VALIDATED_PROVIDER_DATE_MATCH | 2026-10-08T11:38:18.552026Z | 2026-10-09T11:38:31.943509Z | False / False |
| NKE 2027/Q1 | REJECT_PROVIDER_DATE_MISMATCH | 2026-10-02T11:39:18.606339Z | 2026-10-03T11:38:37.395900Z | True / False |
| PEP 2026/Q3 | VALIDATED_PROVIDER_DATE_MATCH | 2026-10-09T11:43:17.342661Z | 2026-10-11T11:43:07.027642Z | False / False |
| PRGS 2026/Q3 | VALIDATED_PROVIDER_DATE_MATCH | 2026-10-01T11:45:14.476264Z | 2026-10-02T11:45:14.497540Z | True / False |
| RGP 2027/Q1 | VALIDATED_PROVIDER_DATE_MATCH | 2026-10-08T11:47:02.745464Z | 2026-10-09T11:47:16.123817Z | False / False |
| RPM 2027/Q1 | VALIDATED_PROVIDER_DATE_MATCH | 2026-10-07T11:47:54.461618Z | 2026-10-09T11:48:10.225577Z | False / False |
| SMXT 2026/Q2 | NO_PAIR | — | — | False / False |
| STZ 2027/Q2 | VALIDATED_PROVIDER_DATE_MATCH | 2026-10-08T11:52:30.213006Z | 2026-10-09T11:52:43.620866Z | False / False |
| WS 2027/Q1 | NO_PAIR | — | — | False / False |


## Validation and live OHLC limitation

Command: `python3 -m pytest -q tests/test_forecast_revision_research.py`. Final result: **34 assertions/tests passed in 5.52s; command exit 1 because the repository safety guard observed concurrent production market-data drift**. The guard remained enabled. An earlier MU fixture erroneously used AIR’s old Q1 identity for MU’s Q4 report; the local fixture was corrected before the final run. No broad Fundamentals, valuation or DC suites ran.

Focused coverage includes valid legacy pairs; same fiscal identity with matching, mismatching and absent provider dates; date equality without fiscal equality; AIR first-provider timing versus later linker relabel; MU/NKE rejection with an independently retained earlier forward rollover; backward regression; immediately preceding +1q continuity; missing-date continuity breaks; unchanged-date linker-only transitions; unchanged snapshot acquisition-specific reconstruction; bounded input excluding later fetches; unchanged temporary source hashes; and failure before artifact output when a source hash changes.

The production OHLC file changed during several read-only validation attempts. Because this task has issued no writable production connections and has not touched collection/scheduler processes, the evidence indicates a concurrent writer outside this task. Its process identity was not established. No writer was stopped, no guard was disabled, and no attempt was made to restore production bytes.

A consistent SQLite backup was made from a mode=ro production source into `/tmp/pairing_fix_ohlc_snapshot.db`. The existing research engine and event-window helper completed on that frozen input, preserving all three of their input hashes and passing quick_check. This yields reproducible fiscal QA and D5/D20 availability while avoiding mixed OHLC read states. It does **not** satisfy the requested unchanged-live-OHLC gate.

Frozen OHLC snapshot SHA-256: `9b7cb272b6fd4124a08309583d2e58c6d2253634140433ddd884af50e3f91d4e` (engine before = after). The live rerun using `data/osakedata.db` aborted at the unchanged existing hash guard with `SOURCE_DATABASE_CHANGED_DURING_RESEARCH`, before writing corrected live artifacts. The compact retained CSV is the successful frozen-OHLC rerun, not the failed live attempt.

| Required production DB | Explicit safety-baseline SHA-256 | Final observed SHA-256 | Result |
| --- | --- | --- | --- |
| data/forecasts.db | 167a7a8d4ff1ad7b318e708e422ef00fca02bec118f3ab8587a9060129967638 | 167a7a8d4ff1ad7b318e708e422ef00fca02bec118f3ab8587a9060129967638 | UNCHANGED |
| /home/kalle/projects/rawcandle/data/fundamentals_generations/refresh_20261014T095401Z_refresh_fundamentals_43db1c8371f6_production_6917d617/fundamentals_v4.db | aec33d93fdcb060c8986a4b5fa6fbb8d70bf8aa94cc3da909c993f66239c64fa | aec33d93fdcb060c8986a4b5fa6fbb8d70bf8aa94cc3da909c993f66239c64fa | UNCHANGED |
| data/osakedata.db | 440450d2ff0488b8c03c601fd288cd548c28b7616805221382961134152766ef | b88ef95cd22cf00a09d224eca95a31104b782977950236cfe65cfb8ef8997a52 | CHANGED CONCURRENTLY — acceptance gate failed |

The explicit safety baseline above was recorded after initial test-guard evidence had already shown OHLC drift; it is not claimed to precede that earlier drift. The first test guard observed OHLC hashes `a6137f2a369e1672a2797a685eed03ffc38be0b9fa98c9ecb857896a8200a214` → `a0fb0a431d6dd98a48ce4c67ee80e65792de5f2bd0777e8827394ef6bc25992f`. The final focused-test guard observed `4d2ff9f325bcde732b223df4638fe15ed8b6e7a8cd12d879ee107ad537fb5e96` → `ace3c8415874ff2a6593ded13629524dd00db6312bf1499d3f6c95affaad99e1`. Therefore no task-wide unchanged-OHLC claim is made.

Generation pointer, forecast scheduler configuration, Fundamentals scheduler configuration, forecast scheduler source and production linker source hashes match their captured baselines. No systemd timer/service/scheduler command was issued. Unrelated pre-existing working-tree changes were left untouched.

## Readiness and next bounded step

| Area | Assessment | Reason |
| --- | --- | --- |
| Collection health | READY | Existing daily collection unchanged; forecast DB hash stable |
| Revision-history depth | EARLY_BUT_USABLE | Original 17-date history preserved; no history fabricated |
| Exact publication overlap | EARLY_BUT_USABLE | 27 events |
| Quality-approved same-target cohort | EARLY_BUT_USABLE | 23 validated pairs, below roughly 30–50 good events |
| Provider rollover evidence | EARLY_BUT_USABLE | 25 observed event-associated forward rollovers; daily timing intervals |
| Outcomes | NOT_YET_READY | 12 D5 across the full cohort; 10 quality-approved D5; no D20 |
| Broader revision-versus-return interpretation | NOT_YET_READY | Quality-approved cohort too small and follow-up incomplete |
| Fix live acceptance | NEEDS_REVISION | Concurrent OHLC drift prevents clean command exit and unchanged-production-hash gate |

Exact next step: once the unrelated OHLC writer finishes normally, rerun this same focused test module and the same 27-event live read-only QA with the recorded inclusive history bounds and pinned generation, and require stable before/after production hashes. No further feature or production-data change is justified by the current results. Continue daily collection unchanged; defer broader interpretation until roughly 30–50 quality-approved publication-linked events and required outcomes accumulate.

## Artifacts and reproduction

Compact corrected cohort CSV: `exports/forecasts/forecast_revision_research_validated_2026-10-14.csv` — 17,296 bytes, 27 rows, SHA-256 `ba61ef124335b98f62774b796a0fa2ea9c58d86972f322d9e2f50b6740c2a35c`. It includes explicit pre/post targets and provider dates, validation states, independent provider/linker timestamps, numeric raw endpoints, approved-only revision metrics, provenance fetch/link IDs, and D5/D20 availability. No large state/checkpoint dump is retained in the repository.

The existing exporter/API rerun used:

```python
run_research_export(ExportRequest(
    canonical_db=pinned_active_canonical, ohlc_db=ohlc_input,
    output=publication_csv, company_ids=same_27_company_ids,
    from_fiscal_year=2025, yahoo_mode="none",
    exact_timestamp_from="2026-09-27T16:27:26.679445Z"))
build_forecast_revision_research(
    publication_csv, publication_metadata, Path("data/forecasts.db"),
    pinned_active_canonical, ohlc_input, temporary_full_csv, temporary_metadata,
    history_start_utc="2026-09-27T16:27:26.679445Z",
    history_end_utc="2026-10-13T12:01:55.287946Z")
# Existing validate_publication_input / build_event_window_rows supply D5/D20.
# Compact export omits state/checkpoint JSON and retains the explicit QA columns.
```

CSV row count, exact identity-set equality, MU/NKE rejected states with null revision metrics, AIR provider/linker timestamps, frozen input hash equality, production forecasts/canonical hash equality and protected-source/config hashes were checked directly. `git diff --check` was also run.

**FORECAST_REVISION_PAIRING_FIX_NEEDS_REVISION**
