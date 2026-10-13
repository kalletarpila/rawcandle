# SetupMaster Phase 1 Research Readiness Audit

13 October 2026. Initial code baseline: `358857e5d0a19db5381716dc6bcd33cbee00c268`. Updated after the user's canonical-universe decision and critical review.

**Proceed only to Phase 2 data qualification. The provisional starting boundary is 2,547 canonical Fundamentals companies, represented by 2,560 securities.** It is not the 2,468-company published operational universe or the USA ticker population in `osakedata.db`. Locally corroborated instrument eligibility covers 2,541 companies and 2,554 securities; six companies remain unresolved. No historical setup dataset is yet qualified: adjustment provenance, dated identity, concentrated session gaps and selection bias require explicit treatment.

This is a read-only audit and design. No SetupMaster engine, backtest, state machine, production job or source-database change is included. Counts below distinguish **verified stored facts**, **proposed research policies** and **unresolved guarantees**. “Verified” means supported by inspected local records, not independently certified vendor accuracy or current listing status.

## Existing infrastructure

| Source | Findings and safe reuse |
|---|---|
| `data/osakedata.db` | Primary daily OHLCV. `osakedata` has ticker/date, OHLCV, market, sector and industry, with unique `(osake,pvm)` and indexed market/ticker/date. No security ID, row provider, acquisition time, currency, adjustment basis or revision history. `ticker_meta` does not establish historical membership. |
| `data/analysis.db` | Findings, divergences, sparse pattern results, blackout dates, Dow events and Swing/ecosystem outputs. Read selected data only; never persist SetupMaster here. Root `analysis.db` contains no user tables. |
| Fundamentals | Resolve the active generation once from `data/fundamentals_active_generation.json`, using `rawcandle/fundamentals/generations.py` semantics. Provider, canonical and analysis roles are separate. Do not use stale flat files or the manifest's historical staging verification paths. |
| `data/forecasts.db` | Fetch histories, raw evidence, deduplicated snapshots, estimates, targets, earnings references and temporal identity/fiscal links. Observation-time design is reusable; historical span is short. |
| Read interfaces | Useful patterns in `analysis/stock_dow_structure.py::fetch_price_bars`, `rawcandle/technical_signal_relevance_sources.py` and publication daily lookup. Require explicit SQLite `mode=ro` and `query_only=ON`. `market_repository.list_markets` initializes schema; `DatabaseManager` includes migrations/writes. Do not instantiate these as presumed read-only adapters. |

Maintain an independent `rawcandle/setupmaster/` namespace, database and research history. Reuse mathematical functions and audited read adapters where appropriate. Do not inherit SwingMaster states, transitions, minimum durations, resets or risk rules. Leave the Analysis Engine POC unchanged. Existing Dow structure can supply optional causally available context, not SetupMaster lifecycle behavior.

## Universe authority and reconciliation

### Canonical boundary

The exact canonical database is:

`data/fundamentals_generations/refresh_20261013T042603Z_refresh_fundamentals_3d9f10e1f3f2_production_25d220d5/fundamentals_v4.db`

The boundary is **every `company.company_id`**, joined to **`security.company_id`**, with security-level keys **`security.security_id`** and routes **`security.current_ticker`**. Inspect `company.status`, `security.active`, `exchange`, `valid_from` and `valid_to` separately; none is silently an inclusion filter. The retained [security roster](phase1_fundamentals_universe_roster.csv) contains every canonical route and its eligibility, coverage and supporting-data measurements.

Verified counts:

- 2,547 companies: 2,546 `ACTIVE`, one `RETIRED` (BNC).
- 2,560 securities with distinct current ticker strings: 2,542 active and 18 inactive.
- 2,518 companies have one active security, 12 have two, and 17 have none. Inactive securities remain relevant to historical research; company and security counts must not be interchanged.

The published population is selected through `fundamentals_operational_universe_active_version.universe_version_id` and `fundamentals_operational_universe_member`, version `3b8121b74c852f08575fa1e2b70004e6`, activated 20 September 2026. It contains 2,468 companies: 2,441 `ACTIVE_SINGLE_SECURITY`, 11 `ACTIVE_MULTI_SECURITY`, 16 historical retained. Those statuses are stale relative to canonical identities: CYCN's company now also contains successor KRSA. The published version is reconciliation evidence, **not SetupMaster's boundary**.

### The 79-company difference

The [79-row reconciliation](phase1_canonical_79_reconciliation.csv) records company/security IDs, ticker, creation time, published-absence reason, matching application markers, prior memberships and eligibility for every company.

| Difference | Verified evidence | Interpretation |
|---|---|---|
| BNC: 1 company | `RETIRED`, inactive security, no canonical quarters; earlier published membership exists. Removal code explicitly retires it and copies the prior roster minus BNC. Repository Phase 13G.3.14 records a completed BNC-removal journal. | Explicit administrative removal, not evidence that BNC is a non-equity or should be omitted from historical price research. Its removed corroborating data needs review. |
| Batch additions: 76 companies | Created 19–20 September; each creation time matches a `GENERIC_BATCH_ADD_TICKERS` applied-plan marker. None appears in any retained published membership version. | Canonical additions were not reflected in the published roster. The identity application path creates canonical identities without rebuilding published member tables; BNC removal copies the old roster. No per-company business rejection reason is recorded. Do not invent one. |
| PSQL and QVCG: 2 companies | Created 22 September, after published activation; timestamp-matched batch marker, approved new/successor identities and no published membership. | Reviewed additions absent from the older published population. |

Of the 76 batch additions, 36 predate published activation and 40 follow it. Therefore “all 79 were added after the snapshot” is false. The supported explanation is **one explicit retirement and 78 canonical additions without published membership**. Code and timestamp evidence explain the divergence; they do not establish an operator's intention for every unpublished company.

### Instrument eligibility and exclusions

The proposed instrument policy accepts US-listed common shares, including ADRs and Canadian issuers listed on US exchanges, with separate domicile/share-class reporting. It does not equate USA scope with US incorporation.

Provider identity plus `sharadar_ticker_metadata(table_name='stocks')` corroborates common-share categories for 2,556 canonical securities: 2,474 domestic, 63 ADR and 19 Canadian routes, including 17 flagged delisted. Five of these have no canonical exchange and unresolved dated price identity: **VAI, NXH, VMRK, IA and NMAD**. Three additional routes—**KRSA, PSQL and QVCG**—lack provider stock-category metadata but have explicit approved identity evidence and canonical NASDAQ/start dates. BNC's corroborating provider records were removed.

| Audit disposition | Companies | Securities | Reason |
|---|---:|---:|---|
| Locally corroborated instruments | 2,541 | 2,554 | Common-share category plus canonical US exchange, or one of three reviewed identities. Historical date eligibility still needs qualification. |
| Unresolved and held from an initial research cohort | 6 | 6 | Five transition routes above; BNC needs listing/identity evidence after administrative retirement. |
| Proven unrelated instrument exclusions | 0 | 0 | No ETF, index or crypto category was found in the corroborated routes. Unknown identifiers remain held, not asserted valid. |

This is the final **audit disposition**, not certification of 2,554 historical price series. All 2,547 companies remain in the starting roster. Six evidence-based holds do not modify Fundamentals. Current corroboration cannot prove historical exchange/type validity; the final date-qualified research count remains unresolved. Multiple classes and successors are distinct securities, with company-level clustering to prevent false independence.

## Restricted OHLCV readiness

Prices were joined by exact canonical `current_ticker` and `market='usa'`, through **12 October 2026**, the last common benchmark session. This measures route availability, not verified historical ownership of every row. No unrelated instruments expand the universe. SPY and QQQ are benchmark inputs only.

| Measurement | All 2,560 canonical routes | 2,554 corroborated routes |
|---|---:|---:|
| Stored OHLCV rows | 5,022,847 | 5,009,668 |
| Routes with some prices / missing prices | 2,560 / 0 | 2,554 / 0 |
| Null OHLC / null volume / negative volume rows | 0 / 0 / 0 | 0 / 0 / 0 |
| Rows with nonpositive OHLC | 2,275 | 2,275 |
| Invalid OHLC range rows | 6,304 | 6,303 |
| Zero-volume rows | 48,640 | 48,361 |
| Union of basic unusable rows | 55,536 | 55,256 |
| Absent interior SPY-session pairs | 3,781 | 3,776 |
| Off-SPY-calendar rows / weekend rows | 6 / 0 | 6 / 0 |
| Adjacent close ratios above 2 or below 0.5 | 1,271 | 1,266 |

Invalid range means `low > high`, or open/close outside low/high. Unusable is the union of null/nonpositive OHLC, range failures and null/nonpositive volume; individual counts overlap. Zero volume can represent suspension or missingness and requires classification, not automatic deletion. There are no duplicate canonical-route/date keys in the current direct join. Economic duplication across differently named histories is a separate risk.

| Year | Canonical rows / routes | Corroborated rows / routes |
|---|---:|---:|
| 2018 | 457,575 / 1,867 | 456,121 / 1,861 |
| 2019 | 482,168 / 1,962 | 480,656 / 1,956 |
| 2020 | 510,821 / 2,124 | 509,303 / 2,118 |
| 2021 | 570,618 / 2,388 | 569,106 / 2,382 |
| 2022 | 609,062 / 2,452 | 607,556 / 2,446 |
| 2023 | 619,954 / 2,515 | 618,454 / 2,509 |
| 2024 | 639,431 / 2,545 | 637,919 / 2,539 |
| 2025 | 637,565 / 2,553 | 636,065 / 2,547 |
| 2026 through cutoff | 495,653 / 2,560 | 494,488 / 2,554 |

### Complete, partial and missing histories

The inspected price boundary is **2018-01-02 to 2026-10-12**. SPY supplies 2,206 observed dates as an audit calendar proxy; it is not yet an independently certified exchange calendar.

| Coverage classification | Canonical routes | Corroborated routes |
|---|---:|---:|
| All proxy sessions present, ignoring quality | 110 | 109 |
| Complete window: all proxy sessions, no basic unusable/off-calendar rows | 61 | 61 |
| Partial window: some prices, fails complete-window definition | 2,499 | 2,493 |
| Missing: no direct-route prices | 0 | 0 |
| Clean complete observed span, allowing later start/earlier end | 89 | 89 |

Partial includes legitimate later IPOs and ended listings; it is not synonymous with defective data. Do not require full-window completeness for event eligibility. Among corroborated routes, 1,762 begin at the database boundary and 2,529 end at the cutoff; 2,383 have at least one interior proxy gap, and 1,306 have a basic quality issue somewhere. Events should use qualified local lookback/outcome windows rather than drop an entire security for an unrelated bad day.

Gaps concentrate on **2026-09-22 (2,271 canonical routes)** and **2023-06-30 (1,197)**: together 3,468 of 3,781 missing pairs. These are priority feed/session reconciliation targets. Their cause is unresolved; neither automatic forward filling nor declaring all gaps exchange closures is justified. The six off-proxy rows also require reconciliation. Earlier broad USA-bucket figures remain in the initial evidence archive solely as infrastructure context and are superseded for research readiness.

**Longest reliable research interval is not established.** January 2018 is the candidate price boundary. Fundamentals beginning in 2015 and older split dates do not extend OHLCV coverage. Identity bounds, causal feature warm-up and action reconciliation determine each security's usable dates.

## Historical identity, actions and selection bias

### Identity failures that price availability hides

There are 2,575 aliases, 2,475 with unknown starts, affecting 2,470 security routes. Likewise 2,470 securities lack `valid_from`. No alias matching another security's current ticker was found; this does not exclude historical ticker reuse or overlapping alias intervals.

Targeted temporal checks found **6,079 stored rows before recorded security start dates**, across 11 routes, plus 16 BNC rows after its administrative end date. These are discrepancies requiring interpretation; canonical validity dates may represent listing, successor or administrative boundaries and cannot all be assumed interchangeable.

Most critically, KRSA starts canonically on **2026-09-09** but its price route begins in **2019**. It overlaps CYCN on 1,880 dates, including 297 exactly identical OHLCV rows. PSQL starts canonically on **2026-08-28** but has 147 earlier rows. Do not assign these pre-successor prices to the new securities, use them for warm-up, or count them as independent company observations. Other pre-start discrepancies include SNDK, ALOY, ECG, ERO, HUT, HYFT, IPHA, VNTG and CAN. QVCG's observed prices start after its canonical start; that does not independently certify their basis.

Structural contracts explicitly distinguish VMRK business combination, NXH ticker reuse, NMAD reverse merger, VAI comparability review and IA continuity. Preserve these distinctions and dated evidence; do not bridge whole histories by ticker text or company ID. The five held transitions remain potentially eligible equities, not proven bad identifiers.

### Adjustment provenance

Corroborated routes have 3,961 stored split events, all marked corrected. This operational flag does not certify price basis. Yahoo acquisition/backfill calls omit explicit adjustment arguments; split backfill replaces history from 2018. Polygon fallback requests `adjusted=true`; Stooq fallback does not retain per-row basis evidence. Installed-provider behavior and mixed historical sources cannot be recovered from an OHLCV row.

Keep nominal traded OHLC, split-consistent OHLC/volume and dividend-inclusive returns distinct. Raw gap is `nominal_open[t]/nominal_close[t-1]-1`; retain corporate-action flags and calculate a separately named split-neutral gap. Return labels require a consistent basis across entry and exit. Current storage cannot certify either raw gaps or split-only returns. Future split-adjusted prices can also corrupt historical absolute price/dollar-volume eligibility; dividend-adjusted history can alter apparent chart structure. Do not double-adjust or assume that all retrospective normalization is harmless.

### Survivorship and selection bias

**The canonical population is a current maintained selection, not a historical PIT universe.** It contains a small retained inactive subset, administrative removals and later manual additions. Broad provider delisting metadata does not establish prices or liquidation proceeds for all formerly listed stocks. `remove_low_volume.py` can delete full histories using 2025 average volume; its execution was not established.

Within the authorized boundary, Phase 2 can reconcile identity/listing intervals, available delistings, selection dates and terminal outcomes. It **cannot recover omitted companies outside canonical Fundamentals or eliminate this selection bias**. Retrospective results must describe associations conditional on this selected cohort. A temporal holdout addresses tuning leakage, not survivorship or future-informed universe selection. A fully representative USA-market claim would require a separately authorized universe change; none is proposed here. Future freezing of this roster supports forward observation but does not repair the past. Price-only studies should not silently require available fundamentals or forecasts, which would add another selection filter.

## Supporting data and reusable features

| Source | Restricted availability and validity |
|---|---|
| Fundamentals | All canonical: 89,938 quarters across 2,540 companies; corroborated: 89,741 across 2,535. Six corroborated companies lack quarters: BATRK, BELFB, RIO, SIMO, MT and NOK. Periods span 2015-05-28 to 2026-09-30. Existing Phase 12B contract explicitly calls the reconstructed history revised, not original PIT history. A first-public date or ARQ label does not certify original values. |
| Publication authority | Canonical: 12,983 VERIFIED quarter records across 2,289 companies; corroborated: 12,964 across 2,286. Verified timestamps span 2024-05-14 to 2026-10-10. Corroborated unresolved statuses: 629 AMBIGUOUS, 1,856 NOT_FOUND, 771 UNRESOLVED. A verified timestamp establishes timing evidence, not PIT financial values. |
| Earnings/date blackouts | Corroborated routes: 70,187 earnings-date rows across 2,476 securities; 29,715 dividend-date rows across 1,107. Timestamp-to-date conversion loses premarket/after-hours information; bounded Yahoo history does not certify completeness. Current-ticker mapping also misses some historical aliases. |
| Forecast snapshots | Canonical fiscal estimates: 2,302 securities; targets: 2,441; earnings references: 2,379. Corroborated counts: 2,299, 2,436 and 2,376 respectively. Observed archive begins 2026-09-27. Counts mean ever-observed snapshots, not simultaneous or per-event coverage. Exact company/security IDs were required. Retrospective EPS surprise references are not an original pre-release consensus archive. Use AS_KNOWN fiscal links and observations available before decisions. |
| Mathematical indicators | `simu/indicators.py` RSI is chronological Wilder smoothing; volume growth excludes today's bar from its baseline. MA/slope, ATR, EMA/MACD, trailing pivot strength and volume impulse definitions in `analysis/results_generator.py` are reuse candidates after causal/warm-up tests. Reuse calculations, not the findings-driven generator or mixed predictor/outcome rows. |
| Dow and divergence | Dow's symmetric pivot window delays availability by `pivot_radius`; join on `confirmed_as_of_date`, not pivot date. Validate prefix replay and versions. Do not inherit its resets. Divergence confirmation needs a separate audit before reuse and is optional initially. |
| Existing research helpers | Publication daily lookup provides read-only timing/missingness patterns. Existing sparse event-window exports end at 20 and admit heuristic timing; they do not satisfy daily paths through 60. |

The observed `results_data` table is sparse and ends in February 2026; it is not a daily feature panel and contains future-outcome columns. The earlier global analysis row counts do not establish restricted-universe feature readiness. Initial features should be computed causally from qualified prices rather than assume stored outputs are complete.

EP needs separate **price/volume shock proxy** and **timestamp-confirmed earnings** cohorts. Unknown catalysts remain unknown. Historical earnings surprises require original actuals and pre-release consensus; current data does not support them across 2018–2026. Momentum Breakout is closer to price-only readiness, but its gaps, identity and adjustment risks still apply.

## Simplified architecture and persistent model

Start with one independent package, one SQLite research metadata database (`data/setupmaster/research.db`) and immutable run directories (`outputs/setupmaster/<run_id>/`). Store large qualified price panels and daily paths in hashed Parquet artifacts only if needed. Do not build a generic feature store, copy every source database into another normalized schema, or add an orchestration service in Phase 2.

Read-only source adapters → pinned source evidence → identity/session/quality qualification → causal setup observations → daily paths and labels → frozen evaluation. Each later stage depends on explicit acceptance of the preceding deliverable.

| Initial persistent entity | Minimal contract |
|---|---|
| `research_run` | PK run ID; status, parent, code/dependency versions, seed, contract/config hashes, source manifest, timestamps and artifact hashes. Preserve completed runs. |
| `universe_security` | PK `(run_id,security_id)`; canonical company, current/dated routes, listing evidence, eligibility and reason, membership/knowledge dates, unresolved boundaries. Preserve every canonical member including holds. |
| `quality_issue` | Run/security/session/field, rule, severity, source reference and disposition. Include missing-data and temporal-identity issues, not just bad prices. |
| `setup_event` | Event ID; unique run/security/setup-version/session/occurrence; event, information and decision times, frozen features/config, catalyst confidence, overlap cluster, eligibility/rejection reason. |
| `event_day` or its immutable artifact | `(event_id,session_offset)`; every scheduled session through entry plus 60, OHLCV basis, feature-as-of, benchmark, missingness and observable path statistics. |
| `event_outcome` | `(event_id,entry_policy,horizon,return_basis)`; horizons 5/10/20/30/60, exact entry/exit sessions/prices, gross/net/excess returns, maturity/censoring/terminal reason and cost model. |
| `experiment_result` | Experiment/parent IDs, frozen partitions and tried definitions, cohort/endpoint, counts, metric, intervals, multiplicity adjustment and result artifact. |

Source manifests retain resolved generation paths, coherent snapshot identifiers, content hashes, adjustment/calendar policies and observation cutoffs. Hash coherent SQLite backups including committed WAL contents; a changing main-file hash is insufficient. Different databases are not automatically atomic together. Pin the fundamentals generation and record market/forecast snapshot cutoffs separately. Use foreign keys, unique constraints and immutable completed runs; reason-coded nulls distinguish unavailable, invalid, immature and not applicable. Research processing statuses are not lifecycle states. Additional normalized tables are optional later, justified by measured volume or query needs.

## Research methodology and defaults

**Events and features.** Evaluate every eligible daily session, not quarterly samples. Register continuous gap, relative volume, prior momentum, trailing-high distance, consolidation width and volatility before defining a small development-only threshold family. Kullamägi thresholds are hypotheses. Breakout levels and volume baselines end at `t-1`. Store rejected candidates and every searched variant. Historical nominal liquidity/price filters require certified bases; do not select using future-year volume or current financial readiness.

**Timing and feasible entry.** Preserve catalyst, first affected session, feature availability, decision and entry separately. Use exchange sessions with America/New_York rules and UTC storage. Premarket publication maps to that session; after-close publication maps to the next session. Intraday publication uses a separate tier and defaults to the next full session for this daily-only design. Date-only publications cannot enter the timing-confirmed primary EP cohort. Default: observe full day `t`, decide after its close, enter the next scheduled session at verified nominal opening-auction price plus costs. Full-day volume cannot justify an entry at that day's open. Opening auction availability is a research execution assumption requiring validation. Intraday/open-gap triggers require separate evidence; daily OHLCV cannot determine intraday trigger/stop ordering.

**Outcomes and evolution.** Entry session is index zero; horizon `h` exits at exchange-session close `entry_index+h`. Preserve event-to-entry movement and every subsequent scheduled session, including missing observations. Use consistent split-adjusted price returns and synchronized SPY excess returns; dividend-inclusive returns require additional certification. No forward filling or later substitute exits. Retain immature events and missing/terminal outcomes. Report delisting-loss and missing-outcome bounds. Daily high/low excursions describe paths without claiming achievable intraday fills.

**Independent evaluation.** Candidate price-only split: 2018–2022 development, 2023 validation, 2024–2025 frozen temporal holdout, 2026 report-only/forward observation. This is a proposed allocation, conditional on qualified counts and prior research exposure. Earnings-confirmed EP needs a separate chronology because verified timing begins in 2024. Pre-lock 2026 observations are not automatically prospective. An already inspected/tuned period cannot become untouched holdout by renaming it.

Fit transformations and parameters on development only; purge outcomes crossing partition boundaries and embargo 60 sessions at later partition starts. Retain repeated events with overlap identifiers; predeclare nonoverlapping sensitivity without introducing lifecycle resets. Use firm/company and calendar-time dependence-aware uncertainty, not independent-event t-tests. Compare against SPY and date/liquidity/prior-momentum/volatility-matched controls **inside the authorized cohort**; size matching waits for PIT size. Add momentum-only and volume-only baselines, ablations, regime checks and time placebos.

Recommended primary endpoint is 20-session net excess return; all five horizons remain required, with other endpoints secondary and multiplicity control across setup families and tried variants. Report distributions, mean/median/tails, win rate, excursions, firm/month counts, censoring and costs. Suggested descriptive floor: 200 mature events, 100 companies and 24 entry months; it is not a substitute for effective-sample/power analysis. A bootstrap block of at least 60 sessions is a candidate default, to be stress-tested for residual dependence. Cost scenarios of 10/25/50 basis points per side are illustrative, not measured execution estimates. Practical tradability additionally requires credible spread/impact and a later research-only capital/overlap analysis. No production risk rules are selected.

## Implementation master plan and acceptance gates

| Deliverable | Independent acceptance test |
|---|---|
| Phase 2 Qualification dossier | Freeze the 2,547-company boundary and eligibility ledger; pin read-only sources; resolve priority identity intervals/successor history, the two concentrated gap dates, price/volume adjustments and raw opening-price recoverability. Produce covered/excluded dates, terminal-outcome limitations and the longest qualified intervals. No event engine or historical setup backtest. |
| Phase 3 Causal event dataset | Dedicated persistence; prefix invariance/future perturbation, sorted-session and warm-up tests; immutable definitions/search budget; EP proxy and Momentum Breakout candidate/rejection ledger. Timing-confirmed EP remains gated separately. |
| Phase 4 Daily paths and labels | Hand-calculated split/dividend/entry/calendar fixtures; exact horizons, every intervening day, costs and reason-coded immature/censored/delisted outcomes. Predictor construction cannot access labels. |
| Phase 5 Frozen evaluation | Locked cohort/partitions; dependence-aware inference, controls, multiplicity, attrition and cost/missingness sensitivity. No holdout-driven refit. Reproduce prior completed runs from retained sources. |
| Phase 6 Evidence decision | Reject, gather more data or separately authorize lifecycle research. Statistically positive selected-cohort associations alone cannot establish broad-market performance or production suitability. |

**Phase 2 may begin** as a bounded qualification project with the canonical boundary accepted. **Setup extraction may begin only when**:

1. Source writes fail, generation/cutoffs/hashes and dependencies are pinned, and Swing/POC mutation paths are absent.
2. Accepted security/session identities and US-listing/type evidence are unambiguous; successor warm-up cannot consume predecessor prices. Six held identities and all known pre-start discrepancies have explicit dispositions. Unknown dates remain excluded or clearly limited.
3. Concentrated calendar gaps and material OHLC anomalies are reconciled or quarantined with retained denominators. Accepted event windows satisfy predeclared local-history rules; source data remains unchanged.
4. Raw opening-price and split-consistent return examples pass action-boundary reconciliation. If nominal history is unavailable, raw-gap EP research stays blocked; Momentum Breakout proceeds only under its certified basis. Dividend and terminal-return limitations remain explicit.
5. Historical results are labeled conditional on the current selected canonical cohort. Omitted-company survivorship cannot pass an unbiased-universe gate within this scope. Optional fundamentals/forecast subsets have separate selection accounting.
6. Information/entry timing, calendar, horizons, missingness, overlap, cost assumptions, search budget and holdout policy are frozen before extraction. Timing-confirmed EP requires timestamp evidence and adequate distinct firms/time; revised values and post-event consensus remain prohibited predictors.

Positive later evidence requires a frozen holdout effect with dependence-aware uncertainty and multiplicity control, realistic costs/capacity, temporal stability and sensitivity to missing/terminal outcomes. Null, underpowered and data-blocked results are valid outcomes. No state names, transitions, minimum durations or reset/risk rules are predetermined.

## Critical review conclusions and evidence

**Verified corrections:** company, security and published counts differ; all direct routes have prices but many dates are unqualified; the 79-company difference is not 79 business rejections; known successor histories overlap; an inactive/retired flag alone does not prove non-equity status. Broad USA statistics and global indicator row counts cannot substitute for restricted readiness.

**Reasonable assumptions requiring validation:** local common-share/category and reviewed identity evidence can provisionally corroborate instruments; SPY dates approximate sessions; next-open entry and illustrative costs are plausible research conventions. None certifies historical tradability.

**Unresolved:** original vendor adjustment behavior, row source revisions, actual exchange/type intervals, six held instruments, missing-session causes, terminal proceeds, original consensus/financial values, and the final usable interval/sample size. Within the fixed canonical boundary, historical selection bias remains a permanent interpretation limit. Phase 2 must resolve the blocking measurement questions or narrow the permitted hypotheses, rather than promise to eliminate every risk.

Evidence artifacts retain SQL, source paths, results and per-security/79-company ledgers. Some large query results are represented by counts/hashes and the derived roster. SQL connections were read-only; attached sources do not imply a globally atomic snapshot. No expensive integrity scan or historical strategy backtest was run.

- [Restricted source measurements](phase1_fundamentals_universe_evidence.json), [final eligibility summary](phase1_final_eligibility_summary.json), [additional price checks](phase1_canonical_additional_checks.json), [canonical source checks](phase1_canonical_source_checks.json), [calendar gaps](phase1_calendar_gap_checks.json), [temporal identity checks](phase1_temporal_identity_checks.json). [Initial broad infrastructure evidence](phase1_audit_evidence.json) is retained as superseded context.
- [Generation resolution](../../rawcandle/fundamentals/generations.py), [batch identity application](../../rawcandle/fundamentals/admin/batch_add_tickers.py), [published retirement logic](../../rawcandle/fundamentals/admin/universe_removal.py), [completed BNC journal evidence](../fundamentals_v4/fundamentals_v4_phase13g3_14_refresh_production_copy_sources.md).
- [Reviewed identity approvals](../fundamentals_v4/fundamentals_v4_phase13g3_20_identity_review_approvals.md), [new-issuer lineage](../fundamentals_v4/fundamentals_v4_phase13g3_20b_reviewed_new_company_analysis_linkage.md), [structural breaks](../fundamentals_v4/fundamentals_v4_phase13f3_3_structural_break_contract.md), [revised-history restriction](../fundamentals_v4/fundamentals_v4_phase12b_research_contract.md).
- [Price acquisition](../../services/stock_update_service.py), [split backfill](../../analysis/splits_price_backfill.py), [Polygon](../../services/polygon_massive_grouped_daily_provider.py), [Stooq](../../services/stooq_fallback_provider.py), [volume deletion utility](../../remove_low_volume.py).
- [Indicator definitions](../../analysis/results_generator.py), [RSI/volume](../../simu/indicators.py), [Dow confirmation](../../analysis/stock_dow_structure.py), [blackout acquisition](../../blackout/fetch_blackouts.py), [publication lookup](../../rawcandle/research/result_publication_daily_ohlc.py), [forecast schema](../../rawcandle/forecasts/schema.py).
