# Forecast revision research V1: overlap export and AS_KNOWN engine

Date: 2026-10-03

Decision: `FORECAST_REVISION_RESEARCH_V1_INSUFFICIENT_HISTORY`

## Reviewed scope and finding

The previous gate used the immutable September 29 publication export, whose latest
first-full-day boundary was September 25. This task regenerated the publication
projection from the CURRENT ACTIVE canonical generation, not the legacy flat DB.
It evaluated 16,210 FY2025+ authority rows with the accepted pipeline, frozen Yahoo
observations and the reviewed V2 artifact (all 83 selections validated).

The separately named overlap export has zero rows. This is NOT merely the old
CSV's filter: current canonical authority's latest timestamp is
2026-09-24T20:16:39Z, and the latest ACCEPTED/CONFLICT SEC Item 2.02 evidence
timestamp is also 2026-09-24T20:16:39Z. Both have zero rows since September 27.
The full current projection produces 12,782 EXACT, 570 HIGH and 2,858 UNUSABLE
rows before overlap filtering. No usable current publication event overlaps
forecast history. This proves absence in available official data, not absence
of real-world earnings releases. Yahoo cannot supply missing official authority;
live Yahoo collection therefore would not remedy this gap and was not requested.

## Retained publication artifacts

Old stem: `exports/result_publication/result_publication_daily_research_fy2025plus_2026-09-29`

All three old files were hashed before and after generation and remain unchanged:

- CSV: `76c6b5bb01e0849fbdfcc76058f6e14a997d84d86d332f75275c31a9b4d7cf52`
- Metadata: `547e7b2c52212d61a0d3de227577a16182ba2d0d4183c236e9af1d3f891bf5a3`
- Yahoo: `1042bfe59ca3be579c0e59b80f9d47b7a54edb7869996c3063dcdc04068053ce`

New stem: `exports/result_publication/result_publication_daily_research_forecast_overlap_2026-10-03`

- CSV: `b06e345e1f9e703daf763081777a4323aa4a47eeb1528d566d02eddf0329ddde`
- Metadata: `be85918213cb0cacd412a0f42d1e31a2d933d168ab45185cbdd7c0d74f4c314b`
- Adjacent Yahoo artifact: `1042bfe59ca3be579c0e59b80f9d47b7a54edb7869996c3063dcdc04068053ce`

The adjacent Yahoo artifact is a byte-identical retained copy of the reviewed
655-observation source, preserving its original dates and scope, not new evidence.
The final export used frozen mode. V2 input hash remains
`922b8b829da8fdc4107fefb80ff2708fd5b456a9148f7c4ca444be530f1d92e1`.
Artifacts remain local under the accepted ignored `exports/` policy.

Reproduction uses `run_research_export(ExportRequest(...))` with active canonical
and `data/osakedata.db`, `from_fiscal_year=2025`, `include_unusable=False`, the
adjacent frozen Yahoo path, and the reviewed V2 artifact. New filter parameters:
`first_full_day_from="2026-09-27"` OR
`exact_timestamp_from="2026-09-27T16:27:26.679445Z"`.
The exact branch requires EXACT; the daily branch uses the retained first-full-day.
There is no upper filter on the publication export; the revision cohort itself
requires an exact timestamp or heuristic boundary inside actual acquisition history.
Metadata preserves evaluated counts separately from filtered output counts.

## Current forecast history

First fiscal fetch: 2026-09-27T16:27:26.679445Z.
Latest fiscal fetch: 2026-10-03T12:01:47.212172Z.
Counts: 11 runs, 59,202 fetches, 20,914 snapshots, 4,155 fiscal snapshots.
Fiscal statuses: 4,159 changed, 14,315 unchanged, 1,121 no-data,
100 transient failures, 39 malformed. There are 2,441 observed acquisition companies.
Recent workflow states are October 3 SUCCESS, October 2 PARTIAL, October 1 SUCCESS.
Systemd service status is neither queried nor substituted for application status.

## Fetch reconstruction and PIT

`rawcandle.research.forecast_revision_research` now implements
`build_forecast_revision_research`, `reconstruct_fetch`, `analyze_event` and the
existing summary API. Inputs are hash-validated through publication metadata;
the previous hardcoded old-CSV-only hash restriction is removed.

Each successful fetch dereferences its own persisted FISCAL_ESTIMATE snapshot,
including SUCCESS_UNCHANGED. The latest eligible AS_KNOWN link per occurrence is
selected using the accepted link version, excluding fundamentals knowledge after
acquisition. CURRENT_RECONCILED cannot substitute. The referenced identity must
belong to that fetch, use the accepted version, be RESOLVED, have the same
company/security as the link, and carry the exact acquisition timestamp.
Links with the wrong snapshot are rejected. Link/resolution/snapshot/fetch IDs
are retained for QA. Link processing time may naturally follow acquisition;
knowledge time, not processing completion time, is the PIT gate.

Chronology includes changed, unchanged and explicit VALID_NO_DATA states.
Failures remain counted in metadata but supply no estimates. No-data does not
become zero. All persisted metric/statistic states, text and numeric values are
carried in JSON, including growth and annual horizons. Missing keys remain absent;
explicit null/empty remain their original states; numeric zero remains zero.

## Boundaries, transitions and revisions

EXACT: timestamp < publication is PRE, >= is POST. Heuristic: observations on or
after first-full-day are POST; dates strictly before a known research publication
date are PRE. The uncertain day, or uncertain pre dates when publication date is
unknown, are not fabricated PRE baselines. No exact-hour heuristic relation exists.

The next target must be the immediately next fiscal quarter present in canonical
quarter data; missing quarters cannot be skipped. Old 0q targets the result quarter;
new 0q targets the next quarter through fetch-specific links. The reported transition
is (last old before first new, first new], not an instantaneous switch.
Statuses distinguish OBSERVED, NOT_YET_OBSERVED, INSUFFICIENT_PRE_HISTORY,
INSUFFICIENT_POST_HISTORY and NO_USABLE_0Q. NOT_YET requires an old baseline and
post-result 0q observations. Delays use observed ticker trading dates; unavailable
calendar coverage yields null, not a weekday approximation. Exact hour and calendar
day relations require EXACT. Daily date arithmetic uses America/New_York.

Revision compares latest PRE +1q with earliest POST 0q only when both target the
same company/FY/FQ. Pre old-quarter 0q can never be its baseline. Checkpoints at
+1/+2/+5 observed trading days after first post 0q choose nearest on/after
observations, preserve their states and never interpolate. Absolute/pct EPS and
revenue changes, analyst counts and range widths are retained. Near-zero (<1e-8),
negative or sign-changing denominators suppress pct while preserving absolute
change and flags. Annual estimates are reconstructed but annual comparisons are deferred.

## Results and QA

Events, PRE, POST, both, transitions and comparable pairs: all zero.
Transition/revision/count-change medians are null, not zero. There is no event-level
representative sample and no trading inference. Metadata retains three deterministic
production-fetch reconstruction probes independent of the empty event cohort.
Synthetic tests prove old/new target identity, unchanged snapshot dereference,
AS_KNOWN selection, future/reconciled exclusion, censoring, exact/daily boundaries,
same-target continuity, cross-quarter rejection, zero/null semantics and checkpoints.
Optional D5/D20 relation is skipped: no overlapping publication events.

Revision CSV: `exports/forecasts/forecast_revision_research_v1_2026-10-03.csv`.
SHA: `a747d1e8973a9db2c958d64b0fa7507dd377d79ed821081fdcc7f7756f824e00`.
Adjacent metadata records the current health, output hash, QA and safety.

## Safety and next step

All source connections are mode=ro with query_only. Current before/after hashes match:

- Forecasts: `d31d72a7ab74340a15adfc8cdf5573f64bb2b17fd2c292a515f381b056f172cc`
- Active canonical: `765a5efdc601dc99c6969ef0e3fe80c2206472b91437486cf5b6b73fa8370a89`
- OHLC: `c04c7fc523f966f649aecc3d6e58885f5cb61cc6e4a4656c45fadb8cba66e168`

All quick_check results are ok. No concurrent source write was detected; no research
snapshot was necessary. Changed source hashes abort rather than claim research mutation;
a concurrent scheduler write requires rerunning from a stable reviewed copy.
Scheduler, acquisition, canonical authority and publication heuristics are unchanged.

Verification: only the revision and publication-export test modules are run; the
full suite and unrelated Fundamentals/DC suites are not run.

Next step: refresh official publication evidence through the existing reviewed
authority workflow for events since 2026-09-27, then generate a separately named
frozen overlap export and rerun this engine. Keep forecast acquisition running;
waiting alone cannot extend the current official evidence boundary. Production
READY requires an actual event and an observed transition or a valid same-target pair.
