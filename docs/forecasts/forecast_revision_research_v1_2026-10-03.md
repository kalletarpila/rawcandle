# Forecast revision research V1 availability gate

Date: 2026-10-03

Decision: `FORECAST_REVISION_RESEARCH_V1_INSUFFICIENT_HISTORY`

## Objective and available history

The first step measures whether persisted Yahoo fiscal-estimate observations overlap result events in the retained publication export. Acquisition spans 2026-09-27T16:27:26.679445Z through 2026-10-03T12:01:47.212172Z. The frozen export's latest first-full-day is 2026-09-25. No EXACT publication timestamp or heuristic daily boundary occurs inside the acquisition window. There are zero eligible result events, PRE/POST pairs, observed regime transitions, or comparable next-quarter revisions.

This implements the task's availability gate before building revision analytics. The module is an availability implementation, not a completed transition/revision engine. It explicitly stops if a nonempty cohort is supplied, so it cannot silently label a usable future cohort as insufficient.

## Current forecast health

The database contains 11 runs, 59,202 fetches, 20,914 snapshots, and 4,155 FISCAL_ESTIMATE snapshots. Fiscal history covers 2,441 acquisition company IDs. Fiscal fetch statuses are 4,159 SUCCESS_CHANGED, 14,315 SUCCESS_UNCHANGED, 1,121 VALID_NO_DATA, 100 TRANSIENT_FAILURE, and 39 MALFORMED_OR_SCHEMA_MISMATCH.

The latest run, d0a1b8b64259490489a1a3fe5fa7a803, completed on October 3 with SUCCESS. October 2 was PARTIAL with one transient failure; October 1 was SUCCESS. These are persisted workflow statuses. Run scope is OPERATOR with a full bounded universe; the database does not independently prove whether each invocation originated from a timer. No systemd state is used to infer workflow failure.

## Publication source

The retained input is `exports/result_publication/result_publication_daily_research_fy2025plus_2026-09-29.csv`, SHA-256 `76c6b5bb01e0849fbdfcc76058f6e14a997d84d86d332f75275c31a9b4d7cf52`, with 13,352 rows. Existing publication metadata validation checks version, hash, counts, and usable-only semantics. The frozen file supplies canonical timestamps for EXACT rows and first-full-day boundaries for heuristic rows. No boundary is recomputed.

## PIT and moving horizons

The availability scan reads every FISCAL_ESTIMATE fetch, including unchanged references and failures. A focused chronology helper retains SUCCESS_CHANGED, SUCCESS_UNCHANGED and explicit VALID_NO_DATA observations, orders timestamps with persisted rowid ties, and excludes failures from usable observation chronology. No-data remains a state rather than zero.

Future value reconstruction must join each fetch to its snapshot, latest eligible AS_KNOWN fiscal link and resolved identity. CURRENT_RECONCILED links cannot silently substitute for acquisition-time knowledge. The existing fiscal-link reader excludes AS_KNOWN links whose fundamentals knowledge time exceeds acquisition time. This research has not yet implemented or claimed full PIT value reconstruction.

Provider horizons 0q, +1q, 0y and +1y move over time. A new 0q pointing to another quarter is a regime transition, not a same-target revision. A future comparable pair must join pre +1q and post 0q on stable canonical quarter identity and preserve numeric/null/empty field states.

## Transition and revision methodology deferred

The planned interval is (last old-0q fetch, first new-0q fetch], censored by daily acquisition. Heuristic boundaries cannot support exact hour precision. Same-target EPS/revenue changes, near-zero EPS guards, analyst-count changes and +1/+2/+5 observed trading-day checkpoints require an actual PRE/POST cohort. They are deferred rather than populated with synthetic values.

## Initial cohort and results

The eligible cohort is empty. PRE, POST, both, observed transitions, NOT_YET_OBSERVED transitions and comparable +1q-to-0q counts are zero within that cohort. Transition delays and revision medians are null, not zero. Older publication events may have post-only acquisitions, but no prior forecasts exist to recover their publication-time baseline; this implementation does not claim an event-level post-only identity join.

Representative company QA and D+5/D+20 relationships are unavailable because no qualifying event overlaps. There is no descriptive revision conclusion or trading inference.

## Output and tests

`exports/forecasts/forecast_revision_research_v1_2026-10-03.csv` is a header-only artifact with the requested stable-identity, pre/post, revision, transition and quality columns. SHA-256: `fe042ffa2d02961298fcc3b6922aebae7569ecb789a6798ad75e762ac10ecba7`.

The adjacent metadata records current health, acquisition window, zero cohort, null metrics, source hashes and integrity. Focused tests verify unchanged/no-data fetch chronology, failed-fetch exclusion, exact timestamp precedence and the empty-window gate. Transition/value tests remain deferred with their implementation.

## Database safety

All database connections use mode=ro and query_only=ON. Current pre/post hashes matched:

- forecasts.db: d31d72a7ab74340a15adfc8cdf5573f64bb2b17fd2c292a515f381b056f172cc
- active fundamentals_v4.db: 765a5efdc601dc99c6969ef0e3fe80c2206472b91437486cf5b6b73fa8370a89
- osakedata.db: c04c7fc523f966f649aecc3d6e58885f5cb61cc6e4a4656c45fadb8cba66e168

Each quick_check returned ok. Scheduler, publication authority and acquisition behavior were unchanged.

## Recommendation

Retain daily forecast collection. The next reviewed task should create a separately named publication export covering results from September 27 onward while retaining the existing frozen artifact, then implement fetch-specific AS_KNOWN reconstruction and same-target revisions against that new overlapping cohort. Waiting alone will not extend the September 29 frozen publication export.

Gate: `FORECAST_REVISION_RESEARCH_V1_INSUFFICIENT_HISTORY`.
