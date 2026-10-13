# SetupMaster Phase 1 Research Readiness Audit

Date: 13 October 2026. Repository baseline: `358857e5d0a19db5381716dc6bcd33cbee00c268`.

**Decision: proceed to a bounded Phase 2 data qualification deliverable. Current data does not yet support an unbiased USA equity setup study or a claim of historical tradability.** RawCandle offers substantial daily history and useful calculation code, but historical universe completeness, adjustment semantics and raw opening gaps remain blockers. Momentum Breakout research is closer to readiness than earnings-confirmed Episodic Pivot research.

This phase contains repository inspection, read-only aggregate SQL and design only. No setup engine, historical backtest, production job, migration or lifecycle state machine is included. The accompanying [audit evidence](phase1_audit_evidence.json) retains exact SQL, result columns, source paths and the active fundamentals generation. Measurements use one read transaction per database; cross-database observations are not an atomic snapshot. Database counts may change after this audit.

## Existing infrastructure findings

| Infrastructure | Finding and reuse boundary |
|---|---|
| `data/osakedata.db` | Primary OHLCV store. `osakedata(id, osake, pvm, open, high, low, close, volume, market, sector, industry)` has a unique `(osake,pvm)` index and market/ticker/date indexes. It has no stable security ID, row source, acquisition time, currency, adjustment basis or revision history. `ticker_meta` is current metadata, not historical membership. |
| `data/analysis.db` | Existing findings, divergences, sparse pattern results, blackout dates, Dow events/status and Swing/ecosystem outputs coexist here. Read selectively; never use this as SetupMaster persistence. Root `analysis.db` contains no user tables and is not the populated analysis store. |
| Fundamentals | Resolve `data/fundamentals_active_generation.json` once through the contract in `rawcandle/fundamentals/generations.py`. The active generation is `refresh_20261013T042603Z_refresh_fundamentals_3d9f10e1f3f2_production_25d220d5`, with provider, canonical and analysis roles. Do not silently read stale flat files. Manifest verification records contain staging paths; resolve `generation_id` plus `roles`, as the existing resolver does. |
| `data/forecasts.db` | Separate raw evidence, fetches, deduplicated snapshots, estimates, price targets, earnings references, identity resolutions and fiscal links. Useful observation-time design; limited history. |
| Read interfaces | `analysis/stock_dow_structure.py::fetch_price_bars`, `rawcandle/technical_signal_relevance_sources.py` and `rawcandle/research/result_publication_daily_ohlc.py` offer useful read patterns. Wrap audited SQL in explicit `mode=ro` connections with `query_only=ON`; do not assume every repository class is read-only. `market_repository.list_markets` calls schema initialization, and `DatabaseManager` includes migration/write behavior. |

SetupMaster must have its own package, contract versions, output location and database. Its dependency boundary must exclude SwingMaster states, durations, transitions, resets and risk rules. Existing Dow labels can be optional context only; their state or reset machinery must not become SetupMaster behavior. Leave the Analysis Engine POC unchanged.

## Data coverage and quality

The measured USA market bucket has **8,084,150 rows and 4,524 ticker strings**, spanning **2018-01-02 through 2026-10-13**. The last date belongs solely to BTC-USD; SPY, QQQ and the most recent equity rows end **2026-10-12**. These counts describe stored instruments, not a verified USA common-stock universe. BTC-USD, ETFs and indices demonstrate that `market='usa'` alone is insufficient.

| Year | Stored USA rows | Distinct ticker strings |
|---|---:|---:|
| 2018 | 720,677 | 2,943 |
| 2019 | 760,183 | 3,090 |
| 2020 | 804,366 | 3,331 |
| 2021 | 893,323 | 3,733 |
| 2022 | 954,800 | 3,869 |
| 2023 | 980,198 | 3,998 |
| 2024 | 1,030,020 | 4,186 |
| 2025 | 1,093,608 | 4,503 |
| 2026 through audit | 846,975 | 4,519 |

There are 2,787 ticker strings starting at the database boundary, 278 ending before October 2026, and 4,224 ending on 12 October. SPY and QQQ each contain 2,206 bars from January 2018; SPX and NDX each have 2,204. No pre-2018 OHLCV was established in the inspected primary store. Older split records and 2015 fundamentals do not extend price coverage. Backups and archives were not exhaustively inventoried and must not be presumed reliable extensions.

Read-only checks of the USA bucket found:

- Zero duplicate ticker/date keys; two rows with at least one null OHLC field.
- 2,320 rows with at least one nonpositive OHLC value.
- 12,583 rows violating `low <= open,close <= high` or `low <= high`; these counts can overlap other failures. Of the range failures, 7,040 occur in 2026, so the latest period especially needs source reconciliation.
- No null or negative volume, but 103,534 zero-volume rows.
- 8,838 absent ticker/SPY-date pairs inside each ticker's first-to-last stored span. These are candidate gaps, not proven feed failures: trading suspensions, identity changes and listing status require classification.
- 2,403 adjacent stored close ratios above 2 or below 0.5. These need corporate-action and source review; do not automatically remove legitimate extreme returns.

**Longest reliable period remains undetermined.** January 2018 is the candidate acquisition boundary. Reliability must be determined by instrument, session and price basis, with feature warm-up. The earliest usable event date will be later than the first price date. Basic range failures, unexplained gaps and unknown adjustments prevent treating the full span as qualified.

### Corporate actions and price semantics

`stock/splits.py` records split dates/ratios; all 6,426 stored events across 2,269 tickers are marked corrected, with dates back to 1962. That flag means an operational correction workflow completed, not that raw and adjusted prices are independently verified.

`services/stock_update_service.py::fetch_history_for_date_ranges` and `analysis/splits_price_backfill.py` call Yahoo history without explicit adjustment arguments. The latter deletes and refetches prices from 2018, replacing prior history. Polygon/Massive fallback requests `adjusted=true`; Stooq recovery supplies OHLCV without retained row-level adjustment provenance. The installed library behavior and source mixture cannot be reconstructed from an OHLCV row. Do not infer that all rows are unadjusted, split-only adjusted or total-return adjusted.

Preserve three distinct concepts in research: actual traded nominal OHLC; split-consistent OHLC and volume; and dividend-inclusive total returns, if supported. A raw opening gap is `raw_open[t] / raw_close[t-1] - 1`. A split on that boundary can create a mechanical raw gap, so retain the raw value and flag the action; calculate a separately named split-neutral gap for screening. Entry-to-exit returns require consistent split adjustment. Dividend cash belongs in a separate total-return label. Current storage cannot certify these distinctions; return labels must remain explicitly unverified until reconciled.

### Delistings and security identity

Canonical fundamentals contain 2,560 securities, including 18 inactive, and 2,575 ticker aliases; some alias `valid_from` values are empty. Provider metadata contains 14,632 delisted and 6,317 active `stocks` rows, and 12,305 delisted `fundamentals` rows. These metadata rows demonstrate identity resources, **not corresponding historical prices or delisting proceeds**. Action metadata is sparse: four `delisted` rows and 85 split rows, mostly in 2025–2026.

`remove_low_volume.py` can delete entire ticker histories using average 2025 volume. This audit does not establish whether it ran. Its existence, current operational universes and the absence of historical membership reconciliation create a material survivorship/selection risk. Stale tickers cannot establish completeness. No complete delisting-return or liquidation-price coverage was established.

Use security identity rather than ticker as the research key; reconcile dated aliases and provider permatickers against prices. Treat ticker reuse, class changes, mergers, spinoffs and reverse mergers explicitly. Never merge different share classes by company ID, or bridge an economic discontinuity merely because ticker spelling matches. Historical listing/exchange/type intervals and terminal outcomes require qualification or supplementary data.

## Reusable features and missing information

| Source | Assessment |
|---|---|
| `simu/indicators.py` | RSI uses chronological Wilder smoothing; volume growth uses preceding bars and excludes today's volume from its baseline. Good candidates for isolated reuse with sorted validated inputs and explicit warm-up. |
| `analysis/results_generator.py` | Implements MA slopes/regimes, ATR, EMA/MACD, volume impulse and trailing pivot strength. Reuse mathematical definitions after temporal tests, not the findings-driven generator. `results_data` has only 37,363 rows across 3,122 tickers and ends 2026-02-11; it is neither complete nor current daily feature history. Its columns mix backward features with future outcomes (`t1`, `t5`, `t20`, etc.). Use an explicit predictor allowlist. |
| Dow structure | 948,397 events across 4,908 tickers, confirmed dates 2018-01-10 to 2026-10-12, across markets. `_build_pivot_candidates` uses a symmetric window and delays confirmation by `pivot_radius` bars. Join by `confirmed_as_of_date`, never pivot/event date alone. Validate prefix replay and calculation version; retain context snapshots without importing reset rules. |
| Divergences | 8,860,146 rows across 4,915 tickers; their existence does not certify causal availability. Audit pivot confirmation before optional reuse. They are not required for initial setup definitions. |
| Earnings blackout | 108,628 earnings rows across 4,135 tickers, 2018-01-02 to 2026-09-02, plus 72,508 dividend rows. `blackout/fetch_blackouts.py` reduces provider earnings timestamps to dates and requests bounded recent earnings history. Cannot reliably distinguish premarket, intraday and after-hours events or prove historical completeness. |
| Canonical fundamentals | 89,938 quarters across 2,540 companies, 2015-05-28 to 2026-09-30; all have `first_public_result_date`. This date alone does not prove original values were available then. The existing [Phase 12B contract](../fundamentals_v4/fundamentals_v4_phase12b_research_contract.md) explicitly describes revised history reconstructed from a 2026 snapshot. ARQ presence alone does not resolve this. Exclude revised financial scores, current taxonomy and valuation ranks from primary historical predictors. |
| Publication authority | 12,983 VERIFIED quarter records, timestamps 2024-05-14 through 2026-10-10; 629 AMBIGUOUS, 1,871 NOT_FOUND and 771 UNRESOLVED. This is a limited timing-qualified subset, not complete 2018 earnings coverage. Source evidence, timezone and session mapping still require checks. A verified publication timestamp does not certify PIT financial values. |
| Forecasts | Snapshot history begins 2026-09-27. Fiscal estimates cover 2,302 symbols, targets 2,441, earnings references 2,379 in observed snapshots. Reference EPS surprises are retrospective provider references, not a historical consensus archive. Only observations actually available before an event can be predictors; fiscal links must use AS_KNOWN, not CURRENT_RECONCILED. |
| Publication research utilities | Daily OHLC boundary lookup and event-window exports supply useful timing and missingness patterns. Existing exports admit heuristic publication classifications and use sparse offsets ending at 20. SetupMaster needs strict timing tiers, every daily offset and horizons through 60. |

EP therefore needs two clearly separated cohorts: a price/volume shock proxy, which must not be called an earnings-confirmed EP, and an earnings-timestamp-confirmed cohort. Non-earnings catalysts remain unknown without dated news evidence. Historical EPS/revenue surprise predictors require original actuals and pre-release consensus; current data cannot supply them across the price history. Momentum Breakout can start with trailing price/volume definitions once price and universe gates pass.

## Proposed architecture and persistent model

Use `rawcandle/setupmaster/` for future source adapters, data qualification, causal features, versioned setup hypotheses, event extraction, outcome construction and evaluation. Use `data/setupmaster/research.db` for metadata and indexed observations, and `outputs/setupmaster/<run_id>/` for immutable manifests and larger daily-path Parquet artifacts. These locations are proposed only. Keep every prior completed run; publish a new run rather than overwriting history.

Read-only source adapters → pinned source snapshots → quality and identity qualification → causal daily features → event observations → daily paths and labels → frozen evaluation → research report. Data acquisition, if needed, is a separately reviewed deliverable. An absent source or contract mismatch fails explicitly, with no automatic fallback to a different database.

| Proposed table | Key and essential fields |
|---|---|
| `research_run` | PK `run_id`; status, parent run, UTC times, code SHA, dependency versions, seed, contract/config hashes, source snapshot ID, semantic mode, artifact manifest/hash. |
| `source_snapshot` and `source_manifest` | PK snapshot and `(snapshot_id, source_role)`; resolved generation/path, coherent SQLite backup identifier, logical/file hashes, observation cutoff, source versions, adjustment policy and retained archive URI. Hash coherent snapshots, including committed WAL contents through SQLite backup; do not hash a changing main file as proof of full contents. |
| `research_security` and `security_alias` | Security key and `(security_id, provider, ticker, valid_from)`; company/provider IDs, listing/type/exchange/currency intervals, valid-to, identity source, confidence, knowledge timestamp and conflicts. Reject ambiguous overlapping aliases. |
| `universe_member` | PK `(snapshot_id, security_id, effective_from)`; effective-to, inclusion reason, knowledge-time basis, universe policy/version. Retain excluded members and reasons. |
| `session` and `price_observation` | Calendar key `(calendar_id, session_date)` with index and open/close UTC; price PK `(snapshot_id, security_id, session_date, price_basis)` with OHLCV, row provenance, adjustment factors and quality status. Large price panels may live in hashed Parquet partitions referenced here. |
| `corporate_action` and `publication_event` | Versioned source-event IDs; security, effective timestamp, action/factor/cash/currency or publication timestamp/session/confidence, evidence reference, observed-at and availability-at. Unknown timing remains unknown. |
| `quality_issue` | PK issue ID; snapshot/security/session/field, rule version, severity, reason and disposition. Never silently repair source values. |
| `feature_definition` and `daily_feature` | Definition/version/hash, lookback, input basis, warm-up, causal availability rule; PK `(run_id, security_id, session_date, feature_id)` with value/status and available-at. |
| `setup_definition` and `setup_event` | Immutable definition/config hash; event PK event ID, unique `(run_id, security_id, setup_definition_id, event_session, occurrence)`; event/knowledge/decision timestamps, feature snapshot, catalyst class, eligibility, overlap cluster and rejection reasons. |
| `event_day` | PK `(event_id, offset)` for every calendar session from event day through at least entry plus 60 sessions; date, basis-specific OHLCV, benchmark prices, dynamic features, missingness, cumulative return and observable path statistics. A separate feature-as-of timestamp prevents later evolution becoming entry predictors. |
| `event_outcome` | PK `(event_id, entry_policy_id, horizon, return_basis)`; entry and scheduled exit session/price, gross/net/excess return, excursions, maturity/censoring/terminal status and cost model. CHECK horizon in `(5,10,20,30,60)`. |
| `split_assignment`, `experiment`, `evaluation_result` | Frozen temporal partitions/purge rules; all attempted hypotheses and parent experiments; metric/cohort/horizon, sample counts, intervals, multiplicity adjustment and artifact references. |

Enable foreign keys, unique constraints and explicit status enumerations. Nullable values require reason codes; distinguish unknown, not applicable, invalid, immature and delisted. Completed runs and their linked definitions are immutable. Resume only incomplete runs with matching hashes. Persist entry policies, cost assumptions and calendar versions. Research processing statuses are not trading lifecycle states.

## Research methodology and recommended defaults

**Universe and features.** Default to historically listed USA exchange common shares; exclude funds, indices, crypto, OTC and ambiguous instruments, while retaining exclusion counts. Decide ADR/foreign-issuer treatment explicitly and report a separate sensitivity cohort. Eligibility uses only prior-session price and trailing dollar volume; never current active status or future-year liquidity. Store continuous gap, relative volume, prior returns, volatility, distance to trailing highs, consolidation width and trend measures before selecting threshold families. Published Kullamägi thresholds are hypotheses, not optimized constants. Register a small development-only parameter budget and all tried variants. Use trailing highs through `t-1` for breakouts and trailing volume baselines through `t-1`.

**Event and entry clocks.** Preserve catalyst publication time, first affected session, feature availability, decision time and entry separately, using exchange calendar and America/New_York session rules with UTC storage. Map after-hours publications to the next session; date-only or ambiguous timing cannot enter the timing-confirmed primary cohort. Default first study: evaluate full-day EP proxy/breakout conditions at close `t`, then enter the next scheduled session's opening auction price plus costs. Full-day volume/high/close cannot justify entry at that same day's open. The nominal opening price must be verified; adjusted prices are used for consistent returns. Premarket/open-gap entry is a separate later hypothesis requiring genuinely pre-entry information and execution evidence. Daily OHLCV cannot validate intraday trigger ordering or exact stop fills.

**Labels and paths.** Define entry session as index zero; horizon `h` exits at close of exchange session `entry_index+h` for 5, 10, 20, 30 and 60. Preserve event-to-entry evolution and every subsequent daily session, including missing observations; do not count the next available stock bar as the next exchange session. Calculate split-consistent price returns and synchronized SPY excess returns; add dividend-inclusive labels only when certified. Retain high/low-based favorable/adverse excursions as daily path summaries, with no implied intraday execution order. Missing scheduled exits remain censored or receive a documented terminal corporate-action outcome; no forward-fill or later substitute exit. Keep immature recent events in the event ledger without usable labels. Report delisting-loss sensitivity and missing-outcome bounds instead of dropping failed companies from conclusions.

**Independence and controls.** Default candidate partition, subject to qualified data counts: 2018–2022 development, 2023 validation, 2024–2025 untouched final temporal holdout, 2026 prospective/report-only. Split by tradable entry date. If any final period has already influenced SetupMaster hypothesis selection, relabel it and reserve a genuinely unseen future holdout. Earnings-confirmed EP needs its own chronology because verified timestamps begin in 2024; do not borrow a fictitious 2018 cohort or repeatedly tune on the short archive. Fit transformations and choose parameters on development data only. Purge labels crossing boundaries and embargo 60 exchange sessions at the start of later partitions. Keep repeated events, record their overlap and use security/company and calendar-time dependence-aware intervals; predeclare a nonoverlapping-event sensitivity view without inventing lifecycle resets.

Compare events with SPY and with date/liquidity/size/prior-momentum/volatility-matched controls using only historical information. Size matching is optional until PIT size exists. Include simple momentum-only and volume-shock-only baselines, setup ablations, time-placebo controls and market-regime stability. Report distributions, mean/median and tail excess returns, win rates, drawdown/excursions, event counts, independent firms and months, and cost sensitivity. Separate statistical association from practical portfolio capacity: use a later research-only overlapping-position/capital-allocation simulation before claiming tradability. No production risk rules are selected here.

Pre-register one primary endpoint (recommended 20-session net excess return), treat other horizons as secondary and control multiple testing across setups, horizons and all searched variants. Use calendar block bootstrap of at least the 60-session outcome span with firm clustering/sensitivity and fixed seeds; avoid independent-event t-tests. Suggested exploratory cell floor is 200 mature events, 100 companies and 24 entry months; power and effective sample size determine final adequacy. These are proposed research defaults, not evidence of profitability.

## Implementation master plan

| Deliverable | Independently testable completion condition |
|---|---|
| Phase 2 Data qualification and frozen research contract | Read-only adapters and coherent snapshots; security/session/type reconciliation; coverage and exclusion ledger; action/adjustment reconciliation; reviewed interval and entry contracts. Fixtures cover ticker reuse, split boundaries, dividends, halts, delisting, missing sessions and earnings around session boundaries. No signal engine is needed. |
| Phase 3 Causal feature panel and event ledger | Dedicated persistence and deterministic incremental/replay behavior; prefix invariance and future-data perturbation tests; full predeclared parameter inventory; events and rejected candidates for EP proxy and Momentum Breakout. Separate catalyst-confirmed eligibility. No performance-based filter selection in this deliverable. |
| Phase 4 Daily evolution and outcome dataset | Exact 5/10/20/30/60-session labels, all intervening days, benchmark alignment, costs, maturity and terminal-outcome statuses; hand-calculated action and missing-exit fixtures; no predictor access to label tables. |
| Phase 5 Independent evaluation | Locked partitions, parameter budgets and multiplicity rules; dependence-aware inference, controls, sensitivity, attrition and reproducibility reports. Freeze configurations before opening holdout results. Preserve negative and null results. |
| Phase 6 Research decision | Independent review of statistical and economic evidence; reject, collect more data or authorize a separately designed lifecycle study. States, transition rules and production integration require new evidence and scope. |

The first deliverable is intentionally large but ends at data readiness. Later phases can be accepted independently without authorizing subsequent production work.

## Acceptance criteria and unresolved decisions

**To begin Phase 2:** accept the independent namespace/database boundary; adopt the data qualification scope; name owners for universe, adjustment and publication evidence; record the unresolved vendor/entitlement and historical extension decisions. Current infrastructure is sufficient for this bounded work. No approval of profitability or full-history validity is implied.

**To exit Phase 2 and start setup extraction:**

1. Pin every source and the research contract, with reproducible hashes and a tested read-only boundary. Attempts to write to source databases must fail; source mutation APIs and Swing/POC orchestration must be absent from the dependency path.
2. Every eligible security/date has unambiguous dated identity and instrument eligibility. Produce annual active/delisted coverage against an independent historical listing authority, including unavailable prices and terminal outcomes. Unresolved historical selection makes the dataset explicitly survivor-biased and exploratory; it cannot pass the primary unbiased-study gate.
3. Every accepted input bar is finite, positive where required, range-valid and has certified price/volume adjustment semantics. Quarantine all failures and retain row counts. Explain candidate session gaps, compare provider/action samples and reconcile material differences without editing production prices. Set the longest usable interval from this evidence, not from nominal minimum dates.
4. Certify opening-price basis and split-consistent return examples across action boundaries; verify dividend treatment. Raw gap studies remain blocked if nominal prices cannot be recovered reliably.
5. Give every earnings-confirmed EP event a supported publication timestamp, source evidence, session mapping and confidence. Revised fundamentals, current classifications and post-event forecasts are prohibited historical entry predictors. Separate price/volume-only research may proceed if its own gates pass.
6. Freeze event timing, entry, horizon, missingness, overlap, costs, primary hypothesis, search budget and holdout policy before extraction. Complete synthetic temporal/identity/action tests and a coverage-based sample/power assessment without running a historical setup backtest.

**Later evidence gate:** a positive result requires a frozen holdout primary effect with dependence-aware uncertainty supporting positive net excess return after predeclared multiplicity control, stability across time/liquidity strata, plausible costs and capacity, and no result driven by omitted delistings or unresolved adjustments. Default cost sensitivity: 10, 25 and 50 basis points per side as illustrative scenarios, plus a liquidity-aware estimate; these are not measured execution costs. Insufficient power, a null finding or failed data gates is a valid stopping outcome. Statistical significance alone cannot authorize lifecycle development.

Outstanding decisions are historical common-share/ADR scope, listing and delisting data source, acquisition rights/cost, availability of raw and split-only OHLCV, treatment of dividends/terminal proceeds, minimum liquidity and price, and the final holdout dates. Recommended defaults above allow design progress; data-dependent choices must be resolved before affected research claims. No SetupMaster states, minimum durations, reset logic or risk rules are predetermined.

## Repository evidence references

- [Market schema and metadata](../../market_repository.py), [update acquisition](../../services/stock_update_service.py), [Polygon fallback](../../services/polygon_massive_grouped_daily_provider.py), [Stooq fallback](../../services/stooq_fallback_provider.py).
- [Splits](../../stock/splits.py), [price replacement](../../analysis/splits_price_backfill.py), [volume deletion utility](../../remove_low_volume.py).
- [Feature calculations](../../analysis/results_generator.py), [RSI and volume](../../simu/indicators.py), [Dow confirmation](../../analysis/stock_dow_structure.py), [technical read interfaces](../../rawcandle/technical_signal_relevance_sources.py).
- [Fundamentals generation resolution](../../rawcandle/fundamentals/generations.py), [forecast schema](../../rawcandle/forecasts/schema.py), [forecast baseline](../forecasts/forecast_full_universe_baseline_2026-09-27.md), [blackout acquisition](../../blackout/fetch_blackouts.py).
- [Publication daily lookup](../../rawcandle/research/result_publication_daily_ohlc.py), [existing event windows](../../rawcandle/research/result_publication_event_window.py), [revised-history restriction](../fundamentals_v4/fundamentals_v4_phase12b_research_contract.md).
