# Historical P/E Versus 12-Month Return: Feasibility Stop

Inspected: 2026-10-05. Starting HEAD: `7c76616ce9cdb17203941fc827fa525574884481`.

**STOP_INSUFFICIENT_ORIGINAL_PIT_EPS_HISTORY**

No P/E dataset, regression or scatter plot was produced. This honors the explicit instruction to stop if the EPS actually known on 2025-10-03 cannot be reconstructed without look-ahead. No proxy, empty substitute dataset or revised-history result is presented as PIT-valid.

## Data Sources

| Role | Authoritative source |
| --- | --- |
| Active taxonomy | `data/analysis.db`: `ec_ecosystem`, `ec_taxonomy_version`, `ec_membership`, `ec_entity` |
| OHLCV | `data/osakedata.db`: `osakedata.osake`, `pvm`, `close` |
| Fundamentals | Active generation `publication_drain_20261005T064921Z_43a1e040`: `fundamentals_v4.db` |
| Quarterly identity / financials | `v4_quarter`, `v4_quarter_financials` |
| Financial provenance | `v4_field_provenance`, `v4_common_earnings_provenance` |
| Publication authority | `v4_result_publication_authority.result_publication_timestamp_utc`, only VERIFIED resolutions |
| Provider versions | Same generation's `fundamentals_provider.db`: `provider_observation`, `sharadar_fundamental_observation` |
| EPS actually used | **None: calculation stopped** |

The active-generation resolver is used, not the stale flat `data/fundamentals_v4.db` path. `data/taxonomy.db` and `data/datacenter_taxonomy.db` are not the authoritative active taxonomy stores.

## Universe And Price Coverage

Active name: **Datacenter taxonomy full v2 1**.
Version: **DC_TAXONOMY_FULL_V2_1**, version ID 3, ecosystem DATACENTER.

- Active ticker-membership rows: **350**.
- Unique ticker universe: **257**, deduplicated across all groups.
- Membership roles: CORE 230 rows, EXTENDED 106, WATCH_ONLY 14. No role/primary filter.
- Non-NULL stored closes on exactly **2025-10-03**: **256 tickers**.
- Non-NULL stored closes on exactly **2026-10-02**: **257 tickers**.
- Duplicate ticker/date keys on these dates: **0**.
- Exact active Fundamentals security mappings: **257 tickers**, no multiple active security rows per ticker in this universe.

These are independent preflight coverage counts, not a validated final sample. Price positivity/finiteness, EPS exclusions, outliers and statistical calculation were deliberately not executed after the PIT gate failed. Missing one start close is observable price coverage, but is not reported as a final mutually exclusive exclusion count because denominator selection never ran.

The proposed price source is the normal stored `close`, without dividends or a new download. Existing [valuation contract](../../../docs/fundamentals_v4/fundamentals_v4_valuation_v1_implementation.md) treats stored prices and shares as retrospectively split-compatible. Therefore stored Close should not be mislabeled guaranteed original unadjusted exchange prices. No price transformation or alternate day was applied here.

## EPS And PIT Findings

1. **The existing history contract explicitly rejects original PIT claims.** [Phase 12B research contract](../../../docs/fundamentals_v4/fundamentals_v4_phase12b_research_contract.md) identifies feature history as revised history reconstructed from a provider snapshot obtained in 2026. The valuation contract also distinguishes revised economic history from exact investor-visible PIT history. The older Sharadar acceptance's ARQ preference does not supersede this explicit later limitation.
2. **No stored local provider observation predates the cutoff.** Across the active provider database, earliest fetched timestamp is `2026-08-30T20:54:47Z`, latest is `2026-10-04T17:38:40Z`, and earliest non-NULL observed value is `2026-05-01`. Rows with either observation/fetch timestamp before `2025-10-04`: **0**. A later fetch is not itself proof of restatement, but the database and current contract do not establish the original pre-cutoff value.
3. **Publication evidence is not financial-value version evidence.** The taxonomy's exact active-security mapped companies have **513 VERIFIED authority rows** with timestamps before `2025-10-04`. These can establish a result's public timestamp, but do not prove that today's EPS payload equals the EPS published then, nor that no later eligible unverified quarter exists. They are not 513 validated denominator inputs.
4. **There is no canonical reported EPS scalar.** `v4_quarter_financials` stores `net_income_common` and `shares_outstanding`, among other financial fields, but not `eps` or `epsdil`. The existing valuation model uses TTM common earnings divided by market capitalization, not the requested annualized-quarter EPS P/E. `shares_outstanding` maps to `sharesbas`, not weighted-average diluted shares. Deriving EPS from those fields would silently introduce a different per-share definition and is not authorized.
5. **Raw EPS fields exist, but are not an approved PIT workaround.** Of **9,847** ARQ provider observations matching taxonomy tickers, **9,434** payloads contain each of `eps` and `epsdil`. These are JSON key-presence counts, not valid EPS counts. Basic/diluted provider fields must not be mixed, and an accepted reported GAAP EPS definition, currency/share basis and historical-value contract would need to be established before use. No GAAP/non-GAAP EPS definition was selected or mixed in this task.

Concrete example: AAPL's stored ARQ quarter ending `2025-06-28` has provider date `2025-08-01`, payload `eps=1.57` and `epsdil=1.57`, but was fetched `2026-08-30T20:54:47Z` and has `lastupdated=2026-07-31`. Merely filtering that provider date before 2025-10-03 cannot prove its per-share value and adjustment basis were available then. This example is not a claim that AAPL's EPS necessarily changed.

`first_public_result_date` and `source_availability_date` must not replace the official publication authority. A verified release timestamp also cannot retroactively make a revised financial scalar PIT-safe. Local immutable observations preserve versions encountered after collection began; none provide the required 2025 information boundary.

## Proposed Joins And Selection Logic

The following is the intended calculation plan, **not an executed or currently feasible query**:

1. Select the unique active DATACENTER taxonomy version and all ACTIVE CONTAINS memberships whose child entity is a TICKER. Deduplicate ticker strings; retain every membership role.
2. Resolve each taxonomy ticker to permanent security/company identity using authoritative security/provider identities. Join to `v4_quarter` by company and natural fiscal identity, not ticker text alone.
3. Join VERIFIED `v4_result_publication_authority` by `(company_id, fiscal_year, fiscal_quarter)` and require the current `quarter_id` to match. Retain actual result publication dates on or before 2025-10-03, not merely period-end dates.
4. Join a **proven original EPS value version**, tied to that exact earnings event and available at the cutoff. This required relation cannot be established from the current revised canonical/provider history. A simple `source_availability_date <= cutoff` is insufficient.
5. Select the most recently published eligible quarter per company. Same-timestamp fiscal/event conflicts require a deterministic reviewed rule; do not silently prefer a quarter ID. Coverage must establish that an unverified later quarter is not being skipped.
6. After selection, exclude missing/zero/negative EPS. Never substitute a previous positive quarter. Join `osakedata` twice using exact ticker and `pvm='2025-10-03'` / `pvm='2026-10-02'`; no trading-day fallback.
7. Calculate with unrounded finite values, then export only the three requested columns, sorting by unrounded P/E with a stable ticker tie-breaker and formatting numeric outputs to two decimals.

Formulas remain exactly:

```text
annualized_eps = latest_known_quarterly_eps * 4
pe_2025_10_03 = close_start / annualized_eps
return_12m_pct = ((close_end / close_start) - 1) * 100
```

No TTM, forecasts, current ratios, absolute EPS, winsorization or total-return adjustment is proposed. Current-taxonomy survivorship remains a sample property requested by the user, distinct from EPS look-ahead protection. A resumed genuinely intraday PIT study should also explicitly define whether same-day after-close releases are eligible for a valuation at that day's Close.

## Missing Evidence Required To Resume

- Original/as-published quarterly EPS values or demonstrably versioned historical financial observations known on or before 2025-10-03, with provenance showing revisions and split/currency/share-basis treatment. Later ARQ retrieval alone is not sufficient under the accepted revised-history contract.
- Reliable official release evidence for the relevant quarters, sufficient to prove which result was most recently public at the cutoff. Existing authority is useful but incomplete evidence of the full eligible-quarter ordering.
- One reviewed reported EPS definition across the sample, such as consistently diluted reported GAAP EPS, tied to that original result and compatible with the stored price share basis. No automatic proxy from end-period shares.

Existing local official source archives could be considered in a separately scoped reconstruction task if they actually preserve the original release values. This task did not crawl unrelated archives or call external APIs. It did not broaden into building missing PIT history.

## Execution Status And Validation

Reproduce the read-only inspection:

```bash
python3 analysis/research/pe_return_20251003/preflight.py
```

The script prints source paths, active taxonomy counts, exact-date price coverage, canonical fields, authority coverage and provider timestamp/EPS-payload evidence as JSON to stdout. It intentionally has no valuation or regression implementation and no production write connection. Its STOP outcome records this task's reviewed feasibility decision rather than certifying any future schema/version as sufficient automatically.

- Eligible quarterly EPS / positive EPS: **not established**.
- Final sample size: **not calculated**, not a synthetic zero-row result.
- Requested final exclusion categories and reconciliation: **not calculated**, because the global original-PIT requirement failed before per-ticker denominator selection.
- P/E/return statistics, Pearson correlation, OLS alpha/beta/R-squared and outlier inspection: **not calculated**.
- Three-column CSV and scatter plot: **not created**, rather than producing misleading artifacts.
- Source databases opened with `mode=ro` and `query_only=ON`; no external requests.
- Production databases, schema, calculations, taxonomy, active generation and schedulers: **unchanged**.
- Validation: repeated read-only preflight and focused output assertions; `git diff --check`. No full suite.
- Commit scope: this preflight script and feasibility report only. No database copies, caches or raw financial payloads. No push.
