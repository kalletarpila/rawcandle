# Fundamentals V4 Phase 12A Forward-Return Readiness

## Outcome

**OUTCOME B - PARTIAL RESEARCH IS POSSIBLE, BUT UPSTREAM DATA WORK IS REQUIRED.**

Phase 12A is a read-only feasibility and leakage audit. It does not train a
model, change any economic contract, persist predictions, or modify Company
Snapshot. The study covers 50,585 Fundamentals V4 endpoints.

The evidence supports leakage-controlled **revised-history exploratory
association** research. It does not support a PIT backtest, causal claims, or
realistic investable-performance claims.

## Hard PIT gate

The provider database contains one successful Sharadar bootstrap run fetched
on 2026-08-30. Stored availability dates identify a candidate information date,
but all historical economic values came from that current provider snapshot.
There is no append-only sequence of historical provider observations proving
what value was known at each original date.

There are 759 provider keys with more than one content hash. They are
intra-snapshot alternatives and do not form a temporal version chain. Therefore:

- PIT-proven endpoints: 0;
- revised-history endpoints: 50,585;
- validity: `REVISED_HISTORY_EXPLORATORY_ONLY`.

Score V2, Lifecycle V2 replay, Absolute Valuation V2, Delta V2 and all eight
Diagnostic Flags inherit this limitation. Lifecycle uses only earlier fiscal
endpoints in replay order, but those input values may contain later
restatements. Current classifications and taxonomy are descriptive only.
Current Relative Position and Relative Valuation snapshots are rejected as
historical predictors.

## Signal and label contract

The recommended signal becomes tradable on the first complete SPY market
session strictly after `source_availability_date`. The security must have a
valid bar on that exact session. Entry is the stored adjusted open.

The primary target for Phase 12B is 63-session arithmetic excess return versus
SPY. The 21- and 42-session targets are secondary. The exact exit session must
exist and security-bar coverage must be at least 90%. The 30/60/90 calendar-day
mapping is retained only as a robustness definition.

The loader calls `yfinance.Ticker.history` without an explicit `auto_adjust`
argument. Installed yfinance 0.2.66 defaults it to true, and all 6,342 split
events are marked price-data-corrected. The database does not retain loader
version, adjustment factors, or dividend provenance per row. Results are thus
called **stored adjusted-price returns**, not verified total returns.

## Coverage and identity

The market database has 8,702,131 rows for 4,871 tickers from 2018-01-02 through
2026-09-09. There are zero duplicate `(ticker,date,market)` keys. Strict OHLC
validation rejects 12,720 rows.

Dated aliases resolve 50,327 endpoints (99.49%); 258 are unresolved or
ambiguous. At 63 sessions, 47,283 of all endpoints have a valid label (93.47%).
After requiring `SCORE_FULL`, the descriptive 63-session sample is 27,365 rows
and 2,264 companies.

Stable `company_id` is available for fundamentals, and dated aliases have no
overlapping cross-security ticker reuse. Market rows remain ticker-keyed and
have no stable security ID. Sharadar metadata contains delistings and actions
include ticker changes, regulatory delistings, bankruptcy and acquisitions,
but the market database has no delisting return or terminal-value field.
Terminal and missing exits remain explicit coverage failures.

## Limited baselines

These are descriptive associations on revised history. Dependence-aware
confidence intervals and locked OOS tests were not performed in Phase 12A.

At 63 sessions, univariate Spearman correlations with excess return are modest:

| Feature | Spearman IC |
|---|---:|
| FCF yield | 0.091 |
| Operating Income / EV | 0.090 |
| Absolute Valuation Score | 0.088 |
| Fundamental Score | 0.078 |
| FCF Margin points | 0.080 |
| Diagnostic active-flag count | -0.073 |
| 2Q Fundamental Delta | 0.019 |

The full 63-session sample has mean excess return -0.69%, median -4.18%, and
positive-excess rate 40.97%. Results vary materially by calendar year. The
predefined high-Fundamental/high-Valuation cell has 304 rows, 144 companies and
161 dates, with mean excess +3.72% and median +2.64%, but this is not evidence
of stable prediction until chronological, purged and clustered checks pass.
The multi-flag/cheap cell is explicitly undersized.

## Phase 12B scope

Phase 12B may implement only leakage-controlled revised-history exploratory
baselines. Lock 2021-2023 for development, 2024 for validation, 2025 as untouched
OOS, and incomplete 2026 as report-only forward validation. Apply a 63-session
purge and an embargo at fold boundaries. Use date-level cross-sectional IC,
calendar-date clustering, and company/date block bootstrap. Random row splits
are prohibited.

Permitted predictors are Score/components, Delta, Lifecycle, Absolute
Valuation, and Diagnostic decisions/statuses. Current relative snapshots,
taxonomy, sector and industry are excluded as predictors. No production model,
composite score, recommendation, Snapshot integration, or score calibration is
authorized.

Upstream work needed for stronger claims:

1. append-only provider versions with original release-time semantics;
2. stable security identity in market bars;
3. explicit price adjustment and distribution provenance;
4. delisting and terminal-return data and policy.

## Evidence

Research directory:
`temp/fundamentals_v4_phase12a/20260909T_PHASE12A/`

Source fingerprint:
`870bd5128d33a0257bb6a94886996f7a4aee6a58279df80f49985a67b5604e65`

Result fingerprint:
`0f35b3b5575ee41a1d32be1a62fc7dd7d6b696ce716c077920b5de39d4220403`

Two independent label/baseline recalculations produced byte-identical selected
artifacts. Full preflight and postflight show identical bytes, schemas, row
counts, WAL/SHM contents, `quick_check=ok`, zero foreign-key errors, active
package pointers, and production report aggregate. Generated artifacts were
parsed as CSV or JSON after writing.

No provider update, canonical/TTM rebuild, Relative Valuation refresh,
production database write, report overwrite, or push occurred.
