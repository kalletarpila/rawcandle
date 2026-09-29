# Daily-research result-publication heuristic V1

Date: 2026-09-29

Rule version: `result_publication_daily_research_v1`

Decision: `RESEARCH_HEURISTIC_V1_ACCEPTABLE`

## 1. Rationale

Canonical result-publication authority remains intentionally strict. Daily OHLC research needs a practical first full post-result trading day and can tolerate explicitly disclosed uncertainty of about one trading day. This implementation therefore adds a pure, rebuildable research projection. It does not update canonical timestamps, statuses, selected evidence, or evidence dispositions.

The projection is implemented in `rawcandle/fundamentals/result_publication_daily_research.py`. It accepts canonical authority, current SEC evidence candidates, a ticker's observed OHLC trading dates, optional Yahoo event observations, and an optional separately validated SEC V2 candidate identifier. It returns a `DailyResearchResult`; it has no database-writing API.

## 2. Canonical and research layers

`VERIFIED` canonical authority always produces `EXACT` and cannot be overridden. Non-VERIFIED authority can produce `HEURISTIC_HIGH`, `HEURISTIC_MEDIUM`, or `UNUSABLE`, but never a canonical transition.

The research result carries company/fiscal identity, research publication date/session, first full post-result trading date, research status/confidence/method, canonical status/timestamp, candidate count, selected research candidate timestamp/reference, Yahoo timestamp/date and distance, and rule version. For daily-equivalent ambiguity, no exact research candidate is selected: publication date/session and selected timestamp/reference remain null while the common effective trading day is retained.

UNRESOLVED and NOT_FOUND currently have no persisted SEC evidence candidates. Because Yahoo cannot create a candidate, all 2,777 such rows correctly remain `UNUSABLE`.

## 3. Deterministic rule order

The implementation stops at the first applicable rule:

1. Canonical `VERIFIED` -> `EXACT`, `CANONICAL_VERIFIED`.
2. Every SEC candidate implies the same effective trading day -> `HEURISTIC_HIGH`, `ALL_CANDIDATES_SAME_EFFECTIVE_DAY`, without selecting an exact timestamp.
3. The separately validated V2 identifier names a current SEC candidate -> `HEURISTIC_HIGH`, `SEC_V2_STRONG_INITIAL`.
4. Yahoo event context yields one local eligible SEC boundary -> `HEURISTIC_HIGH`, `YAHOO_NEAR_UNIQUE_SEC`.
5. Multiple candidates in one Yahoo-local cluster have the same effective day -> choose the latest only within that cluster, `YAHOO_NEAR_CLUSTER_LATEST`.
6. Yahoo is unavailable and the complete SEC effective-day span is at most one trading day -> choose the latest only within that cluster, `HEURISTIC_MEDIUM`, `SEC_LOCAL_CLUSTER_LATEST`.
7. Otherwise -> `UNUSABLE`.

Reversing candidate input order produces the same result. Globally latest is never a rule.

## 4. One-trading-day tolerance

Distance is the signed index difference between effective days in the security's observed `osakedata.db` calendar, not elapsed calendar days. Candidate and Yahoo timestamps are first converted to the reviewed daily boundary; eligibility is `abs(distance) <= 1`.

This means a Friday after-market event and the following Tuesday after a Monday market holiday are adjacent trading boundaries. A filing weeks later cannot become eligible merely because it is globally latest.

The FY2025+ validation used each company's available security ticker calendar from `data/osakedata.db`; no company required a fallback calendar. The previous 651-quarter review had already confirmed that the two dual-ticker companies derive agreeing effective days.

## 5. Latest inside a cluster

Latest is only a tie-breaker after a local cluster is established. For Yahoo, candidates are evaluated separately around each observed event. Two distinct Yahoo event clusters cannot be merged: if they support different candidates, the result is `UNUSABLE`.

Within one event, the closest effective-day distance wins. If equally close candidates imply different effective days, the projection abstains. Only candidates sharing the winning effective day may use latest timestamp as a tie-breaker.

No current production quarter reached `YAHOO_NEAR_CLUSTER_LATEST` or `SEC_LOCAL_CLUSTER_LATEST`: same-effective-day cases were consumed by the earlier stronger rule, and all other accepted Yahoo clusters had one effective candidate. Both branches remain covered by focused synthetic tests.

## 6. Session handling

UTC and timezone-aware provider timestamps are converted to `America/New_York`:

- before 09:30 -> `PRE_MARKET`;
- 09:30 through 15:59:59 -> `REGULAR_HOURS`;
- 16:00 or later -> `AFTER_MARKET`.

PRE_MARKET on an observed trading day uses that day. REGULAR_HOURS and AFTER_MARKET use the next observed trading day. A non-trading publication date uses the first observed trading date after it.

Same calendar date does not imply equivalence. ABG 2025-Q1 has PRE_MARKET and AFTER_MARKET candidates; Yahoo's PRE_MARKET context independently selects the PRE candidate and effective day. ORN 2025-Q3 has the same session split; its issuer release is dated the prior evening and the next-morning SEC acceptance produces the same practical effective day. Both were manually reviewed.

One canonical VERIFIED after-market row on the latest available OHLC date has no subsequently observed trading day yet. It remains `EXACT`, with its publication date/session present and effective date temporarily null until OHLC advances.

## 7. Optional SEC V2 selector

V2 is not embedded in or deployed by the canonical resolver. The projection accepts only an optional candidate identifier produced by the separately researched `initial_result_sec_semantic_v2_research` rule. It must identify an existing current SEC evidence candidate.

V2 selected 83 of the 651 ambiguous quarters. Seven were already captured by all-candidates-same-effective-day, so its incremental contribution here is 76 `HEURISTIC_HIGH` quarters. Yahoo does not participate in this decision.

## 8. Full FY2025+ validation

The read-only validation evaluated all 16,210 canonical FY2025+ authority rows.

| Research status | Quarters | Percent |
|---|---:|---:|
| `EXACT` | 12,782 | 78.85% |
| `HEURISTIC_HIGH` | 570 | 3.52% |
| `HEURISTIC_MEDIUM` | 0 | 0.00% |
| `UNUSABLE` | 2,858 | 17.63% |
| Daily-research usable | 13,352 | 82.37% |

Usable coverage increases by 570 quarters beyond canonical VERIFIED. Status by canonical population is:

| Canonical status | Research result |
|---|---|
| VERIFIED 12,782 | 12,782 EXACT |
| AMBIGUOUS 651 | 570 HIGH; 81 UNUSABLE |
| UNRESOLVED 864 | 864 UNUSABLE |
| NOT_FOUND 1,913 | 1,913 UNUSABLE |

## 9. Method distribution

| Method | Count |
|---|---:|
| `CANONICAL_VERIFIED` | 12,782 |
| `ALL_CANDIDATES_SAME_EFFECTIVE_DAY` | 11 |
| `SEC_V2_STRONG_INITIAL` | 76 |
| `YAHOO_NEAR_UNIQUE_SEC` | 483 |
| `YAHOO_NEAR_CLUSTER_LATEST` | 0 |
| `SEC_LOCAL_CLUSTER_LATEST` | 0 |
| `YAHOO_NO_UNIQUE_LOCAL_CLUSTER` | 52 |
| `SEC_CANDIDATES_TOO_DISPERSED` | 29 |
| `NO_SEC_CANDIDATE` | 2,777 |

The zero medium count is evidence of appropriate abstention, not a disabled branch. Of 32 Yahoo-unavailable ambiguous quarters, three are selected by V2 and the remaining 29 have SEC effective-day spans over one trading day.

## 10. Coverage gain

Before this V1 hierarchy, the reviewed safe daily-equivalent ambiguity rule admitted 11 of 651 AMBIGUOUS quarters. V1 admits 570, or 87.56%. It adds 559 usable materially ambiguous cases, reducing the prior 640 materially ambiguous daily-OHLC cases to 81.

No coverage is claimed for UNRESOLVED or NOT_FOUND because their current canonical records contain no eligible SEC candidates. Adding Yahoo-only dates would violate the research contract.

## 11. Yahoo agreement audit

Of 570 heuristic selections, 567 have Yahoo evidence and three V2 selections have no Yahoo event. Among the 567:

- first-full-post-result day agrees exactly: 554;
- first-full-post-result day differs by one trading day: 13;
- difference greater than one trading day: 0.

For the 556 cases with a selected exact SEC candidate, publication calendar date agrees in 522 and differs in 34; session labels agree in 523 and differ in 33. The other 11 are all-candidates-same-effective-day records with no selected exact timestamp, so date/session comparison is intentionally not fabricated.

Yahoo status among all 570 high-confidence rows is 524 `SUPPORTS_DATE_ONLY`, 33 `CONFLICTS`, 10 `DOES_NOT_DISCRIMINATE`, and 3 `UNAVAILABLE`. Yahoo remains a consistency/cluster input and is not treated as truth.

## 12. Manual error-risk sample

Deterministic SHA-256 order selected up to eight rows from Yahoo-assisted, V2, one-day-edge, medium, and latest-inside-cluster strata. The populated review sets covered 24 selections with overlap, plus targeted same-day/session and known next-day artifacts. Medium and latest-cluster had no production rows and were validated synthetically.

Yahoo-assisted examples included BKD, HLMN, UTZ, EOG, FWRD, LPG, and TXG. V2 examples included FDMT, LENZ, DTE, TNXP, KLXE, GUTS, GSIT, and PLCE. One-day edges included RRC, AIRJ, ADSK, PSX, PTEN, and RDVT.

Findings:

- No reviewed Yahoo selection was a later supplemental filing masquerading as the result boundary.
- V2 labeled two selected IPAR releases supplemental, but direct exhibit inspection shows explicit issuer headlines reporting the canonical quarter results. These are conservative V2 false negatives, not heuristic false selections.
- The known V1 canonical next-day artifacts remain bounded: FCN abstains; RDVT and TNXP 2025-Q4 differ from issuer/Yahoo context by at most one practical trading boundary, as allowed for hobby research.
- ABG and ORN session splits resolve from explicit Yahoo event session/effective context rather than calendar-date collapse.
- LPG's SEC acceptance is the evening before its issuer-dated/Yahoo event, but both imply the same next trading day; no foreign/calendar rollover error results.
- Thirty-seven quarters contain multiple Yahoo events. Separate-cluster protection prevents an adjacent-quarter event from authorizing a global-latest filing.
- No quarter rollover or systematic PRE/AFTER inversion was found.

This review supports the requested pragmatic daily-use confidence, not scientific event-study precision.

## 13. Remaining unusable cases

The 81 remaining AMBIGUOUS quarters consist of 52 with no unique Yahoo-local SEC cluster and 29 Yahoo-unavailable cases whose SEC effective-day span exceeds one trading day. They retain no research date or false precision.

The additional 2,777 unusable rows are all 864 UNRESOLVED and 1,913 NOT_FOUND quarters. A later coverage phase would first need to create reviewed SEC/issuer candidates; this heuristic must not fill them from Yahoo alone.

## 14. Read-only production proof

Before and after implementation and validation:

- `data/fundamentals_v4.db` SHA-256: `9c1c14be2f52165f93d4c9d30aba8bb64fc5489e37190ed9fb672ffa993caaad`, unchanged;
- authority counts: 12,782 VERIFIED, 864 UNRESOLVED, 651 AMBIGUOUS, 1,913 NOT_FOUND, unchanged;
- evidence counts: 12,782 ACCEPTED and 1,318 CONFLICT, unchanged;
- `PRAGMA quick_check`: `ok`;
- `PRAGMA foreign_key_check`: zero rows;
- `data/forecasts.db` SHA-256: `8fc6785ce83f8a94a0cb80be8d1514e6a9f3ea1d42ac33b9d2081f83ffc9cd42`, unchanged.

All production validation connections used SQLite URI `mode=ro`. The full output was written only to `/tmp/result_publication_daily_research_v1_validation.json`. No canonical schema/table, migration, forecast workflow, or scheduler was changed.

## 15. Recommendation

Gate: `RESEARCH_HEURISTIC_V1_ACCEPTABLE`.

The exact next step is to add a read-only application query/service that loads current canonical/evidence rows and OHLC calendars into this projection, supplies Yahoo and validated V2 observations with their provenance, and exposes the research result without persistence. Add an explicit UI/export warning that `HEURISTIC_HIGH` is suitable for hobby daily-OHLC work but not canonical publication authority or precision event studies. Keep the 81 ambiguous, 864 unresolved, and 1,913 not-found quarters excluded until new reviewed SEC/issuer evidence exists.
