# OHLCV gap repair handover

Historical handover of the October 13 stopped task. Git status and missing-row counts below refer to that stop. This documentation commit does not include or qualify the draft repair script or its generated evidence.

13 October 2026. Stopped at the user's request in favor of a future reusable recovery function in the existing RawCandle web UI. No UI work was started.

## Safe stop and production status

No production write transaction was opened. No production OHLCV rows were inserted, updated or deleted. All database inspection used read-only connections, which have finished. No repair backup, insert manifest or apply receipt was created. Existing evidence was preserved. No further provider requests are running or scheduled by this task.

The standalone draft `scripts/repair_targeted_ohlcv_gaps.py` is uncommitted and untested. **Do not run its fetch or apply commands.** Its proposed four-worker Yahoo fetch was rejected before execution by automatic approval review because it lacked conservative pacing and adaptive throttling. No large Yahoo batch ran. The draft has not been accepted as a safe recovery implementation; use it only as design material for the next task.

## Reproduced gaps

Boundary: active canonical Fundamentals generation `refresh_20261013T042603Z_refresh_fundamentals_3d9f10e1f3f2_production_25d220d5`, 2,547 companies / 2,560 securities. The published 2,468-company population is not the boundary.

| Date | Missing inside stored first/last price span | All canonical missing routes | Still missing at stop |
|---|---:|---:|---:|
| 2023-06-30 | 1,197 | 1,275 | 1,275 |
| 2026-09-22 | 2,271 | 2,282 | 2,282 |

Both are regular sessions in the [NYSE 2023 calendar](https://www.nyse.com/publicdocs/ICE_NYSE_2023_Yearly_Trading_Calendar.pdf) and [NYSE 2026 calendar](https://www.nyse.com/publicdocs/nyse/ICE_NYSE_2026_Yearly_Trading_Calendar.pdf). No current missing count decreased.

Preliminary screening identified 1,192 June candidates and 83 pre-start exclusions; September had 2,264 candidates, five unresolved identities and 13 post-history/successor exclusions. These are **screening labels, not final repair eligibility**. In particular, provider first/last price dates do not independently prove IPO, delisting or suspension dates. Validate actual target-day trading and dated identity before inserting. The retained diagnosis includes the supporting metadata and adjacent stored bars.

Known issues: VAI, NXH, VMRK, IA and NMAD have unresolved transition/alias histories. BNC is administratively retired with removed corroborating Fundamentals data. CYCN must not be extended across the reviewed KRSA successor start on 2026-09-09. KRSA and PSQL already contain pre-successor history; current-ticker availability alone is insufficient. See the committed Phase 1 report and temporal-identity evidence for the complete context.

## Provider and adjustment findings

- Existing Polygon/Massive grouped-daily infrastructure successfully returned 2026-09-21, 2026-09-22 and 2026-09-23. Raw responses are retained locally. Requests for June/July 2023 returned HTTP 403; the June 30 error explicitly states historical entitlement limits. A temporary HTTP 429 occurred during probing; the later September request succeeded. Do not assume either unlimited access or a fixed safe request rate.
- Eight small Yahoo probes succeeded: AAPL, NVDA, AMD and TSLA, each around both dates. Each returned three daily bars, including the target session, using explicit `auto_adjust=False`, `back_adjust=False`, actions and Adj Close. This proves sample recoverability, not coverage of all missing routes.
- Installed Yahoo history defaults to `auto_adjust=True`; RawCandle acquisition omits an explicit option. Polygon/Massive `adjusted=true` means split-adjusted, according to its [endpoint documentation](https://massive.com/docs/rest/stocks/aggregates/daily-market-summary). The bases are not generally interchangeable.
- For 2023, AAPL and NVDA's stored adjacent prices match neither the current Yahoo raw/split-adjusted values nor its current Adj Close adjustment exactly. Historical adjustment vintage is a possible explanation, not a verified cause. Leave affected inserts blocked unless the local convention is resolved. AMD and TSLA probes match the inspected neighboring stored opens, but full candidate validation is unfinished.
- A preliminary September 21 comparison found 2,201 missing-route neighbors within 0.1% on OHLC, 63 mismatches and 18 without comparisons. This is not an accepted tolerance or completed validation. Target and both adjacent sessions, volume, finite values, range consistency and identity still require checks. Do not infer a scale factor or interpolate a missing bar.

## Rate limiting and next task

Existing stock-update sleeps are 0.1 seconds after history ranges, 0.25 after successful tickers and five seconds per 500 tickers. Forecast transport provides a configurable sequential `YahooRequestLimiter`, minimum intervals and exponential retry backoff. These mechanisms do not establish a guaranteed safe rate and are not a cross-process account/IP budget.

Installed `yfinance.download` delegates to per-ticker history calls; grouping tickers through that API does not prove a single efficient upstream batch request. The next implementation needs validated batching where available, conservative configurable pacing, bounded work, adaptive cooldown/backoff, a persistent circuit breaker on throttling and protection of normal daily collection. No replacement rate-limiting implementation was completed in this stopped task.

Before any future write: reviewed per-row insert manifest, verified restorable backup, current missing-key checks, explicit identity and adjustment validation, insert-only transaction, existing-row preservation proof, integrity checks and idempotence verification. Avoid downstream Swing/Fundamentals/forecast execution.

## Preserved artifacts and Git status

`outputs/ohlcv_gap_repair_20261013/` contains the diagnosis, three Massive responses, eight Yahoo probes and the preliminary neighbor comparison, approximately 8 MB total. These files remain uncommitted; no API credentials were printed or added to them. No artifact or backup was deleted.

Latest commit remains `09f5e959` (Phase 1 audit); this stopped repair task created no commit and staged no files. New uncommitted work is the standalone draft, this handover and the evidence directory. Pre-existing unrelated changes remain in the Fundamentals publication journal, active-generation files/directories and PE research artifacts. Production database files must not be committed.
