# Fundamentals V4 Phase 12C.3 Historical Research Universe

## Decisions

- Operational track: `OPERATIONAL_PHASE12D_READY`.
- Broad research track: `BROAD_RESEARCH_METADATA_ACQUISITION_REQUIRED`.
- Phase 12D is not authorized by Phase 12C.3 itself.
- Research contract: `HISTORICAL_RESEARCH_UNIVERSE_CANDIDATE_V1`.
- Contract fingerprint:
  `27bf55b2a6b02f9b5a5a66966b7637f4f85a2fa69983c6a0cca8ad3987d0a06e`.
- Risk: `HIGH - CURRENTLY_REVISED_NON_PIT_HISTORY`.

The operational Fundamentals V4 and Company Snapshot universe is unchanged.
The proposed broad universe is research-only and must never be substituted into
current production readers. It is intended for screening candidates for
further analysis, not as a buy/sell model or investable backtest.

## Durable source archive

The complete source ZIP was copied, not moved, to:

`data/source_archives/sharadar/fundamentals/phase12c_20260910/sharadar_fundamentals_10y.zip`

- size: 235,876,508 bytes;
- SHA-256:
  `dc9d3f729830c1881873d10dec2dc2a3e7035d2a247e1737983bdb64cd0e0d36`;
- member: `fundamentals-10Y.csv`, 802,067,611 bytes;
- `unzip -t`: passed;
- source/archive byte comparison: passed;
- acquisition: `2026-09-10T13:32:21Z`, `GET /data/fundamentals?years=10`.

The narrow `.gitignore` rule covers only Sharadar fundamentals archive ZIPs and
their local archive manifests. The original ZIP and extracted CSV remain in
`temp`; no large binary is committed.

## Universe reconciliation

The verified source contains 227,460 ARQ provider rows, 217,638 latest-revision
logical endpoints and 9,017 tickers.

| Population | Tickers |
|---|---:|
| Source and current operational intersection | 2,449 |
| Historical-only source tickers | 6,568 |
| Global source | 9,017 |
| Append-only production ARQ | 2,451 |

The two production-only tickers are valid rows retained from earlier snapshots;
they are not present in the current global source snapshot. The reconciliation
therefore remains `9,017 = 2,449 + 6,568` without changing production retention.

## Identity and eligibility

Sharadar `fundamentals` ticker metadata contains one current metadata row per
ticker with permaticker, category, exchange, delisted status, first/last price,
first/last quarter, and a SEC filing URL from which CIK can be parsed.

- 8,993 tickers have a dated provider permaticker/CIK candidate and recognized
  common-stock category;
- 24 historical-only tickers require identity and security-type metadata;
- no multiple permatickers per provider ticker or multiple local markets per
  OHLC ticker were observed;
- 3,686 tickers have an exact ticker plus non-conflicting date-overlap OHLC
  candidate: 2,449 operational and 1,237 historical-only;
- 5 historical-only tickers have local OHLC but no date overlap;
- 5,326 historical-only tickers have no local OHLC match.

The provider metadata mapping is stronger than a bare name match, but local
OHLC remains ticker-keyed and has no permanent security identifier. Therefore
the market link is explicitly a candidate, not a permanent identity. The data
model permits multiple dated issuer/security episodes even though current local
evidence did not prove a reused-ticker episode.

All 8,993 recognized categories are common-stock, primary-class, Canadian
common-stock, or ADR categories. ADR, OTC, foreign listing, active and delisted
status remain explicit attributes rather than automatic exclusions.

Fundamental-model applicability is separate. Current sector context identifies
3,014 candidate non-specialized and 677 Financial Services/Real Estate cases;
5,326 historical-only tickers lack sector context. Current taxonomy is not
historical PIT truth, so authoritative dated accounting classification is still
required before broad model application.

## Price and benchmark feasibility

Local USA OHLC, SPY and QQQ begin on 2018-01-02. SPY and QQQ each have 2,183
valid sessions through 2026-09-09. Stored prices are treated as split-adjusted;
dividends are excluded, so all later outcomes would be price returns, not total
returns.

The candidate event center is the first complete SPY session strictly after the
provider availability date. Event price requires valid closes on `t-2` through
`t+2` and becomes observable after the `t+2` close. Feasibility requires at
least 90% company-session coverage and an exact exit 30, 60, 120 or 180 sessions
after the observable session. No return was calculated.

| Scope | 30 sessions | 60 sessions | 120 sessions | 180 sessions |
|---|---:|---:|---:|---:|
| All, 217,638 endpoints | 101,452 | 101,076 | 96,947 | 94,067 |
| Operational, 87,420 | 73,796 | 73,589 | 70,829 | 68,763 |
| Historical-only, 130,218 | 27,656 | 27,487 | 26,118 | 25,304 |

All feasible labels also have aligned QQQ event/exit sessions. For the requested
time partitions, potential 180-session coverage is 47,802/91,423 in 2020-2023,
13,430/21,465 in 2024, 13,776/21,035 in retrospective 2025, and 0/15,573 in
not-yet-mature 2026 report-only data.

## Terminal events and censoring

Provider metadata marks 3,589 source tickers delisted, but the local corporate
action snapshot has only 156 recent rows from 2025-2026. Among locally linked
tickers, evidence finds one acquisition without consideration value, one
bankruptcy without liquidation value, three delisting events without terminal
value, and 125 terminal cases requiring metadata. Depending on horizon, 28 to
168 currently testable endpoints are right-censored.

V1 must use exact exits where present, explicit right-censoring where terminal
value is unknown, and separately sourced terminal returns only when cash/stock
consideration or liquidation evidence is authoritative. It must not assign zero
automatically, carry forward the last price, infer bankruptcy from disappearance,
or silently drop every missing exit. Complete-case, neutral and severe bounds
remain sensitivity analyses only.

## Survivorship assessment

The operational intersection omits 6,568 of 9,017 source tickers, or 72.84% of
the global ticker population. This is an upper coverage bound, not an estimate
of return bias. The directly price-linkable lower bound is 1,237 additional
historical-only tickers. At the endpoint level they add 25,304-27,656 feasible
labels, approximately 36.8-37.5% beyond the operational feasible count.

The direction of current-universe survivorship bias is plausibly upward, but its
exact magnitude is not identifiable until terminal outcomes and dated identities
are authoritative. No false point estimate is reported.

## Recommended architecture

Use a separate ignored SQLite database such as
`data/research/historical_fundamentals_research.db`. Keep identity episodes,
global revised fundamentals, label evidence and censoring there. Do not add them
to production provider, canonical, analysis or Snapshot schemas. Estimate 1-2
GB initial persistent storage and 3-5 GB working headroom for indexed rebuilds.

Before implementing it, acquire:

1. dated permaticker/CIK/listing/ticker/exchange intervals;
2. authoritative security type and historical accounting classification;
3. split-adjusted pre-2018 and delisted-security prices;
4. ticker-change, transfer and OTC continuation events;
5. merger consideration and bankruptcy/liquidation terminal values.

## Verification

The Phase 12B-12C.3 research and production-isolation suite passed 72 tests.
This includes all 11 Phase 12C.3 tests; Phase 12A label behavior is exercised
through the Phase 12B tests because there is no separate Phase 12A test module.
Python byte-code compilation and `git diff --check` also passed. The complete
Fundamentals V4 suite was not rerun because this phase adds only isolated
research code and does not change reusable production code.

The audit used read-only SQLite connections, loaded no credentials, made no
network request, and invoked no production writer. The stable production
preflight and postflight aggregate fingerprint is
`0a0197bed455a895bb127a54cf86bfbb887981d2d8a0a300cb0ea458b3b91094`.

## Operational Phase 12D

Phase 12D may be proposed separately for the unchanged operational universe:
canonicalize the already imported extended history, rebuild TTM and downstream
revised history, preserve current readers and Snapshot behavior, and rerun the
unchanged locked Phase 12B with an explicit current-universe survivorship
limitation. Production authorization, backups and replay gates remain required.

Detailed deterministic evidence is under
`temp/fundamentals_v4_phase12c3/20260910T_PHASE12C3_FINAL_V5/`.
