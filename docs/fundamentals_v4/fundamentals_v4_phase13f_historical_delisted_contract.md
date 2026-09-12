# Fundamentals V4 Phase 13F Historical/Delisted Contract

Date: 2026-09-12

Outcome: **OUTCOME B — CONTRACT READY, AREB HISTORY PARTIALLY LIMITED**

Phase 13F adds a copy-only historical/delisted-security contract and proves it with AREB without writing production data. The contract preserves current SNDK, active Operational Universe, Relative Position, Relative Valuation, Snapshot, Scheduler and Datacenter taxonomy behavior.

## AREB Identity

- Ticker: `AREB`
- Company: American Rebel Holdings Inc.
- Canonical company/security: `company_id=192`, `security_id=192`
- Stable provider identity: permaticker `637535`, CIK `0001648087`
- Exchange/market evidence: NASDAQ, local market `usa`
- Provider listing interval: `2022-02-07` to `2026-05-12`, `isdelisted=Y`
- Local OHLC evidence: first price `2022-02-07`; later local OHLC rows exist but are not carried beyond provider delisting for investability.
- Current Operational Universe status: historical retained only, not active, reason `DELISTED_SECURITY`

## Classification Source Of Truth

For Fundamentals V4 sector/industry, the operational source of truth is `data/osakedata.db.ticker_meta`, resolved by stable security identity plus ticker and market.

AREB resolves to:

- sector: `Consumer Cyclical`
- industry: `Footwear & Accessories`
- source: `ticker_meta(ticker='AREB', market='usa')`
- historically versioned: `false`

External/user-supplied `Industrials / Commercial Services & Supplies` remains secondary conflicting evidence only. Sharadar descriptive data, Datacenter taxonomy, aliases and company-name matching must not override `ticker_meta` sector/industry. Datacenter taxonomy remains a separate thematic ecosystem; AREB status is `NOT_MEMBER_BY_DESIGN` and no Datacenter membership is created.

If market-aware `ticker_meta` resolution is missing, incomplete, ambiguous or crosses ticker reuse boundaries, classification-dependent paths must return explicit not-ready/review status rather than guessing. This does not block classification-independent historical score calculations.

## Dependency Matrix

| Consumer | Current source after Phase 13F | Required source | Complies | Correction | Missing/ambiguous behavior |
| --- | --- | --- | --- | --- | --- |
| Valuation applicability | `ticker_meta` joined by ticker + market/security identity | `ticker_meta` | Yes | Market-aware join added | `VALUATION_NOT_READY` via missing sector/industry |
| Valuation rehearsal | `ticker_meta` joined by ticker + market | `ticker_meta` | Yes | Market-aware join added | Missing sector/industry propagates to not-ready applicability |
| Relative Position grouping | shared market-aware classification resolver | `ticker_meta` | Yes | Resolver now keys `(ticker, market)` and records resolution counts | sector/industry peer groups get `PEER_CLASSIFICATION_MISSING` |
| Relative Valuation peer grouping | shared Relative Position resolver | `ticker_meta` | Yes | Datacenter memberships stay independent from sector/industry | missing classification becomes explicit metadata and no guessed peer group |
| Snapshot presentation | persisted valuation/RP/RV source fields | `ticker_meta`-derived fields | No code change required | Preserved; no production Snapshot write | missing fields display as unavailable through existing readers |
| Onboarding/readiness | market evidence + `ticker_meta` classification evidence | `ticker_meta` | Yes for Phase 13F evidence | AREB records source/provenance and mismatch | review-required if ticker/market identity is not resolved |
| Historical/delisted pilot readers | copy-only historical membership + `ticker_meta` evidence | `ticker_meta` | Yes | historical provenance explicitly says not PIT-versioned | blocks only PIT-classification claims |
| Datacenter taxonomy | `ec_*` thematic membership | Independent, not sector/industry | Yes | no AREB membership created | remains `NOT_MEMBER_BY_DESIGN` |

## Pilot Evidence

Two independent copy-only pilots were run from production read-only sources:

- `temp/fundamentals_v4_phase13f_historical_delisted/20260912T_PHASE13F_AREB_COPY_ONLY_PILOT`
- `temp/fundamentals_v4_phase13f_historical_delisted/20260912T_PHASE13F_AREB_COPY_ONLY_PILOT_R2`

Both produced:

- outcome: `OUTCOME B — CONTRACT READY, AREB HISTORY PARTIALLY LIMITED`
- deterministic fingerprint: `ee3d6f074fa350e60b93a9d7f39e4e482891cce1ad4abef0d42a960b606f18e5`
- production immutability: `true`
- rollback injection: schema and member-history failures rolled back byte-identically
- no-change replay: `NO_CHANGE`, logical writes `0`, byte/metadata state equal `true`
- candidate report hash: `e90c5a670e52c1ce8f150ff86d1f550586d8b774f8f204fa7f606e0362f31043`

AREB data counts:

- provider observations: 89 (`ARQ=47`, `MRQ=42`)
- canonical quarters / TTM endpoints: 39
- prelisting warmup endpoints: 22
- listed-period investable endpoints: 17
- post-delisting endpoints in current canonical data: 0
- post-delisting price carry-forward cases: 0

Downstream evidence:

- Score rows: 58 total, 34 listed-period rows
- Diagnostic endpoints: 96 total; evaluation-count distribution `7 -> 57`, `8 -> 39`
- Current active Relative Position rows for AREB remain present: 12
- Current active Relative Valuation rows for AREB remain present: 1
- Historical peer result: `HISTORICAL_PEER_UNIVERSE_NOT_READY`

## Readiness Matrix

| Area | Status |
| --- | --- |
| identity_status | `RESOLVED` |
| fundamentals_status | `HISTORICAL_REVISED_HISTORY_READY_WITH_PRELISTING_WARMUP` |
| operational_universe_status | `CURRENT_NOT_ELIGIBLE_DELISTED_SECURITY` |
| taxonomy_status | `NOT_MEMBER_BY_DESIGN` |
| classification_status | `TICKER_META_READY_REVISED_NOT_PIT` |
| downstream_status | `INTRINSIC_HISTORY_READY_WITH_DIAGNOSTIC_LIMITATION` |
| relative_position_status | `CURRENT_LAYER_CONTAINS_AREB_ROWS; HISTORICAL_PEER_UNIVERSE_NOT_READY` |
| relative_valuation_status | `CURRENT_LAYER_CONTAINS_AREB_ROWS; ACTIVE_UNIVERSE_FILTER_REQUIRED_BEFORE_PRODUCTION_MIGRATION` |

## Limits

Phase 13F does not migrate production data, activate AREB, write production reports, change formulas, call network APIs, activate Scheduler/UI behavior or create Datacenter taxonomy membership. Production migration for historical/delisted securities remains deferred.

The current `ticker_meta` classification is revised-history, not point-in-time. Therefore Phase 13F can support ordinary revised-history Fundamentals calculations, but cannot claim PIT sector/industry classification until a historically versioned classification source exists.

The current RP/RV production layers retaining AREB rows is intentionally reported as a blocker for production migration, not corrected in Phase 13F.

## Verification

- `python3 -m compileall rawcandle/fundamentals/phase13f_historical_delisted.py rawcandle/cli/run_phase13f_historical_delisted.py rawcandle/fundamentals/relative_position/source.py rawcandle/fundamentals/relative_valuation/source.py rawcandle/fundamentals/valuation/persistence.py rawcandle/fundamentals/valuation/rehearsal.py`
- `python3 -m pytest tests/test_phase13f_historical_delisted.py tests/test_fundamentals_v4_relative_position_source.py tests/test_fundamentals_v4_relative_valuation_source.py tests/test_fundamentals_v4_valuation_persistence.py`
- Production preflight quick_check: `fundamentals_provider.db=ok`, `fundamentals_v4.db=ok`, `fundamentals_analysis.db=ok`
