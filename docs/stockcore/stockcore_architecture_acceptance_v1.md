# StockCore Architecture Acceptance V1

2026-10-15 · Future architecture acceptance criteria, documentation only.

Authority and boundaries: [Architecture Specification V1](stockcore_architecture_spec_v1.md). Inventory: [database responsibilities](stockcore_database_responsibilities_v1.csv). Definition/evidence gates: [open design questions](stockcore_open_design_questions_v1.csv).

**Runtime status: NOT EXECUTED.** StockCore has not been created by this task. The criteria below are future acceptance requirements and proposed verification methods, not test results, an implementation backlog or permission to run production/provider jobs. Any detail still open must be settled in its named contract before the corresponding assertion can be evaluated; an implementation's current output cannot supply its own expected definition.

Acceptance needs independently derived mathematical expectations, small adversarial synthetic fixtures, isolated storage/crash fixtures and later explicitly authorized bounded pilot evidence. No production application constructors or nominal dry-run jobs are appropriate substitutes. Historical evidence E01–E06 refers to the source index in specification §1; those prior findings/tests were not rerun here. No legacy-output equality or profitability requirement is implied.

## Identity and metadata — D01/D02

| ID | Verifiable property and required evidence |
|---|---|
| ID-01 | A selective identity fixture preserves accepted security_id/company_id, reviewed provider/permaticker mappings and review evidence/confidence byte-for-byte or through a documented lossless field mapping. Adding an instrument outside Sharadar/Fundamentals neither reallocates existing IDs nor requires financial-pipeline initialization. |
| ID-02 | A handoff/restart fixture has exactly one active ID allocator at every stage. Before activation legacy allocation remains authoritative; after separately authorized handoff all allocating requests use StockCore or hold. Test stale active-generation references and ensure no flat/preparing file is mistaken for accepted authority. Q01 gates activation. |
| ID-03 | Date-bound rename and ticker-reuse fixtures resolve each session to the correct security. Two unrelated issuers sharing a symbol never merge. Boundary dates and overlapping/unknown alias intervals return the documented route or explicit hold, with no guessed first-listing date. Q02/Q04 supply expected edges. |
| ID-04 | Issuer CIK normalization produces the accepted issuer key without conflating security/share class; sourced SIC/type/class/exchange/currency/country retain provenance and unknown status. A missing field is not manufactured from sector, suffix or issuer country. |
| ID-05 | Sharadar AVAILABLE/NOT_FOUND/UNCERTAIN/NOT_CHECKED, permaticker and last-check are independently represented; absent cache does not become NOT_FOUND. AVAILABLE with incomplete Fundamentals history remains a valid combination. |
| ID-06 | Collection, Fundamentals, research and strategy membership can differ for the same security without changing identity. Delisted history remains readable. A current-roster/current-sector-only fixture cannot be emitted as certified historical membership/classification. |
| ID-07 | Metadata reads identify the current external RawCandle ticker_meta authority and freshness. Synchronization never writes that source or resurrects inline price labels. External missing/stale metadata is visible. Q05 supplies actual maintainer contract. |

## Safe source ingestion and bases — D03

| ID | Verifiable property and required evidence |
|---|---|
| SRC-01 | A source adapter fixture captures explicit auto_adjust=False and all six same-response values, including Adj Close and Volume, request range and source observation evidence. Deliberately mixing Adj Close from another response is rejected as a same-vintage product. No automatic Polygon/Massive call path exists in initial configuration. |
| SRC-02 | A holiday/early-close/timezone fixture plans exactly the latest completed market session plus its preceding five trading sessions. A still-open session and host-local tomorrow are never treated as accepted completed bars; range end semantics are explicit. Q06 defines the calendar. |
| SRC-03 | For accepted overlap plus one missing session, publication inserts the missing observation, preserves equal overlap and detects a changed OHLC/Adj Close/Volume under the reviewed comparison convention. A change yields affected source scope and durable invalidation; ticker/date presence alone never means unchanged. |
| SRC-04 | Empty, rate-limited, failed, truncated and missing-sixth-field responses leave previously usable history unchanged. A candidate can be retained as failed/held evidence without being accepted. Incomplete new coverage is reported, not silently certified complete. |
| SRC-05 | Injected failure before/within accepted source publication leaves either prior accepted scope or complete validated new scope, never committed deletion without replacement. Independent ticker success remains isolated from the failed ticker. |
| SRC-06 | Separate fixtures distinguish received zero/negative/missing/nonfinite values, numeric/action qualification, security eligibility and consumer usability. Rejected source observations remain inspectable; no clipping, interpolation, volume truncation or deleted calendar position hides the defect. |
| SRC-07 | A correction outside the six-session overlap is not claimed detected by daily refresh. A separately bounded repair identifies its own scope and triggers appropriate wider derived influence after qualified acceptance. |
| BAS-01 | Ordinary and qualified dividend-adjusted readers return explicitly identified definitions. For finite positive factor f=AdjClose/Close, adjusted OHLC follows the specified reconstruction and volume stays unchanged by f. Zero/negative/missing denominator/factor yields unavailable/held adjusted data with evidence, never an implicit ordinary fallback. |
| BAS-02 | Each persisted feature/event/state/regime/research receipt declares basis/value fields. Reader fixtures reject an incompatible basis/definition/receipt combination. Q03 basis choices are approved before operational use; supporting both interfaces does not select a universal basis. |
| BAS-03 | Split-unit discontinuity and security-boundary fixtures can pass numerical OHLC checks yet fail continuity/action qualification. No accepted return, gap, warm-up or pattern bridges the disallowed boundary. Ordinary Yahoo history is labeled split-adjusted where applicable and never certified exchange-original/PIT by its name. |

## Corporate actions — D04

| ID | Verifiable property and required evidence |
|---|---|
| ACT-01 | A dividend fixture preserves ex-date AND cash amount with supplied currency/type/unit/source/quality. Legacy date-only evidence remains date-only; no payment/tax/entitlement completeness or original-unit cash claim is invented. |
| ACT-02 | A qualified newly confirmed split automatically plans a complete six-field refetch from 2018-01-01 or later verified eligible start, validates expected qualified coverage/route/units and replaces safely without manual confirmation. A fake old corrected flag does not bypass qualification. |
| ACT-03 | Injected split acquisition/coverage/identity/unit failure preserves prior accepted history and records review hold/outcome. Logs report split evidence, refetch scope, affected/change counts and downstream invalidation separately from calculation success. No already split-adjusted prices are multiplied by the ratio again. |
| ACT-04 | Rerunning an unchanged processed action produces no second replacement or duplicate logical action; a revised ratio/effective date/evidence version is requalified and logged. Crash/retry does not lose the processed-action outcome. |
| ACT-05 | Evidence-qualified same-security rename/delisting applies automatically with dated aliases/terminal evidence and retained prices. Missing Yahoo alone and ambiguous M&A/SPAC/reorganization/reuse fixtures hold rather than delist/stitch. Every automatic application and hold appears in the scheduler receipt. Q02 fixes evidence expectations. |

## Shared mathematical definitions — D05

| ID | Verifiable property and required evidence |
|---|---|
| MATH-01 | Hand-computed full-window SMA and SMA-seeded EMA fixtures verify first-ready index and recurrence. A first-price EMA implementation fails the same fixture. Approved definitions explicitly state current versus prior-bar cutoff and output units. |
| MATH-02 | Hand-computed Wilder RSI14 fixtures verify first 14 deltas, recurrence, monotone gains/losses and flat case after Q08 settlement. Rising RSI must not reproduce the known rolling zero-loss bug. An arbitrary short reseed cannot pass exact full-baseline equivalence. |
| MATH-03 | TR/ATR14 fixtures verify selected preceding-close/seed convention and Wilder recurrence, distinguishing it from partial-window arithmetic mean TR. MACD12/26/9 verifies both SMA seeds and first signal readiness without unapproved zero fill. |
| MATH-04 | Independently calculated return-SD, gap O/previousC−1 and h-session close-to-close return fixtures verify units, ddof/horizon and calendar positions. Price-level dispersion and t0-low-normalized levels are separately named and cannot overwrite those features. |
| MATH-05 | Missing/invalid/security/unit boundary fixtures exercise the agreed segment/warm-up contract without compressing sessions or using pre-eligible prices. Full versus checkpoint incremental recurrence agrees for the same inputs and defined numerical equality. A changed seed/source invalidates carried state. |
| MATH-06 | Interface/definition review shows one shared owner per basic formula and no UI or second enrichment writer with different units under the same key. Intentional SwingMaster/domain predicates retain named thresholds/cutoffs and separately identify any deliberately different measure. |

## Confirmed pivots — D06

| ID | Verifiable property and required evidence |
|---|---|
| PIV-01 | Seven-session unique High/Low/scalar-RSI fixtures confirm center p only after p+3 completed qualified bars. Six-bar prefix and clipped left edge produce no full-window confirmed pivot. Fields retain observation, intrinsic kind and availability separately. |
| PIV-02 | Adjacent and nonadjacent equal competitors within r3 and flat plateaus produce no strict pivot. Appending to an unchanged plateau never replaces an already declared confirmed cluster winner because no such non-strict winner is emitted. Retain E05 T09 adversarial meaning. |
| PIV-03 | For every cutoff of a fixture, full-history pivots filtered by true availability equal prefix-calculated pivots. Compare IDs/values/kinds/confirmation, not only centers. A changed historical source is evaluated as revision/invalidation, not mislabeled unchanged-source repainting. |
| PIV-04 | Missing session/value/identity/action boundary fixtures neither form full windows across forbidden segments nor shift p+3 by dropping rows. A valid wide-range candle can supply both intrinsic kinds without an undocumented detector-order change. |

## Unified Dow and exact continuation — D06/D10/D13

| ID | Verifiable property and required evidence |
|---|---|
| DOW-01 | SwingMaster, SetupMaster, relevance and DC/EC adapters identify the same common Dow definition/accepted output; no consumer invokes a second incompatible operational reducer/profile. Domain facts cannot relabel an independent structure as the same Dow. |
| DOW-02 | Retained-high fixture 20→18→19 does not label 19 HH solely because it exceeds 18 while accepted structural high remains 20. Coherent low/update/activation fixtures have independent expected results after Q09 settlement, including equal/near values under Q10. |
| DOW-03 | With prior accepted support7 and completed closes8, intraday lows6 alone emit no BOS/RESET. First Close below the applicable retained threshold emits BOS; second consecutive Close below that same threshold emits RESET; a recovery between them clears count. Equality behavior follows Q10. |
| DOW-04 | A bar where a pivot confirms and Close breaches evaluates Close against previous completed-bar accepted levels, applies BOS/RESET, then processes the pivot and publishes next state. A second-breach reset bar still processes its new pivot; no old reset-day continue skips it. |
| DOW-05 | Same-bar dual pivots/multiple changes produce deterministic Q12 ordering and noncolliding event identity, or the explicitly selected final-bar representation. Repeated publication cannot silently lose an intermediate state through INSERT OR REPLACE under one key. |
| DOW-06 | E05 T26-shaped fixture saves first BOS counter1, processes a silent recovery clearing it, restarts, then breaches again: result is first BOS, not early RESET. Checkpoint carries last processed state or exact replay covers every intervening bar. |
| DOW-07 | Full qualified 2018+ replay equals sequential daily processing and restart at every boundary of adversarial fixtures, including no-event bars, reset+pivot collisions and gaps. Compare events and end-of-bar state/counters/coverage, not just most recent emitted event. Moving 51-row bootstrap is not accepted as full history. |
| DOW-08 | Changing an earlier level-defining pivot invalidates later state/events/checkpoints; replay from a valid earlier state/origin equals fresh full replay. New security/segment starts use Q11 initialization and no prior-security warm-up. |

## Confirmed divergence and patterns — D06

| ID | Verifiable property and required evidence |
|---|---|
| DIV-01 | Independent fixtures cover regular bullish, hidden bullish, regular bearish and hidden bearish with approved strict opposing price/RSI inequalities. Equal price or RSI anchors produce no event. Initial product contains no V1 strengths or r2 divergence definition. |
| DIV-02 | Pair gaps4/5/30/31 trading sessions verify inclusive5–30 eligibility. A third intervening same-kind price pivot prevents comparing the outer pair, even when the outer pair matches better. Middle pivot may finish one pair and start the next. |
| DIV-03 | BOTH price anchors require separate confirmed same-kind RSI extrema within−1/0/+1 session. A scalar RSI sample at price1, an opposite-kind match or offset±2 cannot satisfy the requirement. Missing matches do not create a fabricated divergence. |
| DIV-04 | Offset−1 fixture never publishes before the later price pivot confirms; offset+1 waits for its own RSI confirmation. Event availability is at least max(all four component confirmations, selection readiness), including pending no-match logic from Q14. |
| DIV-05 | All-prefix comparison shows full output filtered by availability equals prefix construction, with unchanged strict components. Logical pair/type rerun produces one event; distinct same-day events retain their component identity instead of collapsing into a boolean. |
| PAT-01 | Each retained candle/chart type has one reviewed formula/threshold/cutoff and a hand-derived positive/negative boundary fixture. Catalog selection is Q27; the existence of several legacy Hammer definitions cannot choose one implicitly. |
| PAT-02 | Requesting output for a single completed day reads sufficient earlier qualified context for the retained two/three/many-bar pattern and long warm-up. Missing/boundary bars cannot be bridged by dropped-row indexing. |
| PAT-03 | Positive events and completed-no-event coverage publish together for the affected range. Revising a positive into a negative removes the formerly accepted event without leaving stale findings. Occurrence/availability are explicit; retrospective divergence/candle associations cannot masquerade as earlier actionable events. |

## Relevance and research clocks — D07/D08

| ID | Verifiable property and required evidence |
|---|---|
| REL-01 | Qualified contexts cover RELEVANT/WEAK_CONTEXT/NOISE under reviewed Q18 thresholds; missing/held context yields NOT_EVALUATED/HELD calculation state, not NOISE. Rules consume common Dow, confirmed pivots and true BOS/reset availability. |
| REL-02 | Context containing a later-confirmed event/pivot cannot affect earlier event-time relevance. DC companion and snapshot queries enforce confirmation/availability<=cutoff for every chosen source, not only occurrence date. |
| REL-03 | Repeated overlapping daily runs retain a compact event-owned annotation plus justified receipts, not copies of large projections/traces per run. Concise context/explain serves actual Q19 fields; an explanation from new inputs is labeled current recomputation rather than exact old evidence. |
| RES-01 | Every study/export names descriptive revised-history or historically decision-time-aware mode and records cohort/source/basis/definition/cutoff/horizon. A current-roster/current-taxonomy fixture explicitly discloses limitations and cannot certify historical membership or missing provider vintages. |
| RES-02 | Decision-time-aware feature selection rejects any component/relevance/model input available after its cutoff. Forward values exist only as labeled outcomes, never predictors; five clocks remain distinguishable: observation, confirmation, source/publication, maturity and later execution when relevant. |
| RES-03 | On-demand horizon fixtures verify start/terminal sessions, same basis, denominator, independent maturity and PENDING/AVAILABLE/UNAVAILABLE. Missing outcomes never encode binary failure. Recent events remain visible even if day20 is not mature; delisting without qualified price does not create a fill. |
| RES-04 | New or late-discovered logical events older than global latest result date are still queryable/studied; repeated on-demand requests do not mandate universal daily forward tables or a wide results_data truth. Study cache/results retention identifies its purpose and invalidation dependencies. |
| RES-05 | Seeded/control/outcome-conditioned export receipts expose actual cohort/filter/sampling dependence. Random row splits and full-sample diagnostics are not labeled chronological OOS; any later OOS claim provides time/group/overlapping-label controls and maturity evidence. Publication-window partial statuses and missing offsets remain explicit. |

## SwingMaster functionality and external consumers — D10/D12

| ID | Verifiable property and required evidence |
|---|---|
| SM-01 | Selected Q15 policy emits only six approved states. Graph, minimum-age and stable-reason fixtures validate final evaluator output after proposal/guards, including stays and prohibited transitions. Retain actual existing contract meanings, not filenames as proof of collected tests. |
| SM-02 | Named decline/stabilization/entry/reclaim/invalidation predicates have reviewed formula/input/cutoff and controlled fixtures for meaningful thresholds. Q16 history/ticker/date delivery and actual used configuration are demonstrated through full policy composition; a helper signature alone does not establish causal history use. |
| SM-03 | Controlled old/new technical-input pairs identify changes in structural facts and final guarded state/reason/age behavior. First-BOS pulses, second-close RESET and persistent NEW_LL/HH-like predicates have explicit mapping; no second Dow is restored to force legacy parity. Standard Wilder ATR/basis changes cannot be hidden inside an unchanged feature name. |
| SM-04 | Regime fixtures cover BULL/BEAR/CRASH/SIDEWAYS, configured consecutive CRASH confirmation, exact200-bar warm-up and combined agree/disagree behavior. Missing/stale one-index input is unavailable, not fabricated SIDEWAYS consensus. Shared SMA/basis/calendar receipts are recorded. |
| SM-05 | Ordered full/daily/restarted lifecycle replay on identical accepted inputs and selected policy/initial state produces identical final states/attributes/reasons/coverage. Later source revisions invalidate dependent state. Compact local browser inspection exposes six-state and combined-regime results in V1. |
| CON-01 | Fundamentals owns external financial provider/canonical/analysis/active-generation responsibilities; its interface uses accepted preserved identity and separate coverage after authorized handoff. No StockCore source fetch requires financial valuation/scoring or a second allocator. |
| CON-02 | DC/EC adapters preserve domain taxonomies, weights, synthetic methodology and signal/projection/report ownership. Shared fields identify common definition/basis/availability/quality; NULL/hold are not silently replaced with valid metrics. Group/entity keys are not indiscriminately converted into security IDs. |
| CON-03 | A source or confirmation correction invalidates affected accepted DC/EC/snapshot/report projections and caches. Consumers acknowledge the source/definition receipt or expose stale status; a copied r3 flag or old report date cannot certify freshness. Q28 gates external adapter activation. |

## Invalidation, publication and recovery — D13/D14

| ID | Verifiable property and required evidence |
|---|---|
| REV-01 | Revision fixture changes a historical existing value without adding dates; indicators, pivots, Dow, events, relevance, dependent state/consumer projections and affected study caches receive their real influence scope. Maximum-date/run-existence-only gates fail this fixture. |
| REV-02 | Recursive influence and pivot/match lookahead are included in replay planning. The source fetch overlap is never reused as an assumed universal calculation tail. A removed event and its obsolete annotation/projection cease being accepted together. |
| REV-03 | Definition/basis/identity/calendar revision invalidates incompatible outputs/checkpoints. A fresh full replay and revision replay have equal accepted events/state/coverage for the same final inputs and definitions. |
| PUB-01 | Fault injection around source local commit leaves durable accepted source plus pending invalidation or intact old source. A crash before derived publication never advertises compatible current derivatives automatically. |
| PUB-02 | Fault injection during derived local publication leaves intact old derived scope marked stale where necessary, or the complete new outputs/removals/processed state/coverage receipt. Failure in one ticker cannot commit its partial deletes while other tickers commit. |
| PUB-03 | A source update during derived computation makes the computed dependency receipt fail acceptance/retry as appropriate. Accepted readers never combine incompatible source/derived definitions, even though the two SQLite commits are not globally atomic. Partial compatible scopes remain distinguishable from complete cross-scope results. |
| PUB-04 | Isolated restore drill restores independently captured source/derived stores and detects receipt mismatch; mismatched derived scopes are stale/rebuilt before current use. Verify shared identity allocator state and external accepted-generation dependencies separately before enabling writes. |
| PUB-05 | Supported Restic/SQLite-consistent backup includes required WAL state and evidence/config/definitions. Main-file-only copying of active WAL databases is not presented as recoverable evidence. No permanent every-generation full-copy archive is required; unique source/user/model artifacts have explicit retention/restoration policy. Q07/Q24 gate claims. |
| OPS-01 | Scheduled, CLI and browser-triggered writes acquire the same operation locks/service boundaries. Concurrent intents cannot bypass the sole source writer; there is no RawCandleApp manufactured object dependency or transplanted second scheduler. |
| OPS-02 | One ticker's failure permits independent successes but overall job remains PARTIAL/FAILED when required work failed. Stage receipts distinguish fetch/qualification/source acceptance/derived acceptance, expected versus received coverage and held securities. |
| OPS-03 | Restart after accepted source and before calculation rediscovers durable invalidation; rerun after already accepted result is idempotent. Latest-date or mere run-existence cannot suppress required replay. Missing prerequisite holds dependent work with a reason. |
| OPS-04 | Job report exposes split/rename/delisting automatic actions, action/identity holds, changed/affected rows, source/calculation errors and recovery outcomes. Cancellation/service interruption cannot leave an advertised accepted half-publication. |

## Browser UI, databases, release boundary and production isolation — D09/D11/D13/D14

| ID | Verifiable property and required evidence |
|---|---|
| UI-01 | With browser closed and browser adapter unavailable, scheduled/headless collection/calculation service fixtures still run. Browser actions call those same services and own no mathematical kernels, SQL writes or independent price acquisition. |
| UI-02 | Windows browser reaches the WSL-hosted local service through intended local access. Default listener/forwarding is localhost-only; no cloud/public service is necessary. Test actual bind/forwarding behavior rather than assuming a setting name guarantees local-only exposure. |
| UI-03 | Initial pages show collection/calculation progress, accepted/missing/stale/held market/quality coverage, identity/action holds, logs/receipts and compact event/relevance/state/regime inspection. Later research/chart/Master views can be added without moving business logic into the browser. |
| DB-01 | Inventory review finds approved source identity/metadata/OHLCV/actions in osakedata_ng.db and derived technical responsibility in analysis_ng.db. Every additional counterpart has evidenced owner/lifecycle/source/restoration justification and preserves original root plus _ng before .db. Conditional examples are not mandatory database creation. |
| DB-02 | Transfer manifest, if later authorized, distinguishes selective accepted IDs/user/source/model evidence from rebuildable technical histories. No universal copy of analysis/results/relevance/SM/fundamentals tables or lossless six-field inversion of adjusted-only legacy rows is claimed. No legacy financial/source DB is discarded from a technical audit alone. |
| SCOPE-01 | First-release capability review covers identity, USA metadata/rosters, six-field Yahoo, safe maintenance, standard indicators, confirmed r3 pivots/common Dow/divergences/selected patterns, compact relevance, simple on-demand research, six states and combined regime, persistence/invalidation/recovery, scheduler and local browser admin. No required capability is silently deferred. |
| SCOPE-02 | First release deploys no trained prediction, automatic retraining, extended macro, episode-history/transaction platform or genuine simulator. Preserved fitted models/manifests remain evidence. Later use qualifies new definitions, training/model availability and label maturity; exit-time data never becomes entry prediction. |
| SCOPE-03 | Production-isolation review confirms only the four documentation deliverables changed by this task. No future StockCore repo/modules/DDL/DB/migrations, provider requests, live jobs/recalculations/training/backtests, financial/forecast/DC/EC changes, SwingMaster file copying or push occurred. Unrelated worktree changes are preserved and excluded from the local commit. |

## Acceptance evidence limits and documentation validation

Passing artifact checks for this package establishes readable, internally consistent documentation; it does **not** satisfy the runtime criteria above. Future acceptance records should identify definition approvals, fixture inputs/expected outputs, isolated environment, actual collected/executed checks and publication/source evidence. In particular, E05's 26 prior synthetic families are evidence of legacy differences, not tests of the new unified reducer; six nested legacy test helpers were not independently collected. Legacy assertions of early divergence timing are not oracles to preserve.

Document validation checks all D01–D14 links, CSV structure and IDs/statuses, all cited Q/DB/criterion identifiers, naming/optional-store distinctions and local Markdown references. Worktree/source baselines and the staged file set establish task isolation. Application tests and production/provider operations remain unexecuted for this documentation-only task. These files receive one descriptive local commit; **NOT PUSHED**.
