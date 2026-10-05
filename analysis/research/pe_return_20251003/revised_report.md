# Revised Quarterly P/E Versus Subsequent 12-Month Return

Run date: 2026-10-05. Semantic: **revised_quarter_PE_2025_10_03**.

**This analysis does NOT reconstruct the exact P/E visible to investors on 2025-10-03.** Quarter eligibility is constrained by existing VERIFIED result-publication authority, but EPS is obtained from RawCandle's current accepted historical provider observations. This is exploratory revised-history relationship research, **not an original PIT backtest**.

The previous [preflight stop](report.md) remains correct under its original requirement. The user explicitly accepted revised-history financial values for this continuation. No production contract, calculation, identity or publication decision was changed.

## Deliverables

- [Three-column dataset](revised_outputs/revised_quarter_pe_returns.csv).
- [Scatter plot](revised_outputs/scatter.png), all 120 observations, unmodified OLS line and zero-return line.
- [Validation/provenance artifact](revised_outputs/validation.json), including each ticker's selected quarter or mutually exclusive exclusion, unrounded values and input fingerprints. This is a separate internal audit artifact, not extra columns in the requested CSV.
- [Reproducible script](revised_analysis.py).

```bash
MPLCONFIGDIR=/tmp/rawcandle-pe-matplotlib \
  python3 analysis/research/pe_return_20251003/revised_analysis.py
pytest -q tests/test_revised_quarter_pe_research.py
```

The script has no provider/SEC/Yahoo acquisition calls. It reads production SQLite databases with `mode=ro` and `query_only=ON`; outputs are restricted to this research directory or `/tmp`. Input file fingerprints are checked before and after execution. Reproduction uses the then-active generation and stops on taxonomy drift or source-file changes; the committed validation artifact identifies this run's exact generation and hashes.

## Sources And EPS Definition

| Source | Database / table / field |
| --- | --- |
| Active taxonomy | `data/analysis.db`: `ec_taxonomy_version` / `ec_ecosystem` / `ec_membership` / `ec_entity` |
| Exact stored prices | `data/osakedata.db`: `osakedata.osake`, `pvm`, `close` |
| Canonical quarterly identity | Active generation's `fundamentals_v4.db`: `v4_quarter` |
| Actual publication authority | `v4_result_publication_authority`: VERIFIED `result_publication_timestamp_utc` |
| Provider-observation binding | `v4_common_earnings_provenance.provider_observation_id` for canonical `net_income_common` |
| EPS value | Active `fundamentals_provider.db`: `provider_observation.payload_json`, JSON field **`$.epsdil`**, dimension **ARQ** |
| Currency/security basis | Same payload `fxusd`, `sharefactor`, `shareswadil`, `eps`, `epsusd`; `sharadar_ticker_metadata`, canonical `provider_security_identity` |
| Corporate-action guards | `osakedata.db.splits_data`, provider `sharadar_action_metadata` |

Active generation: `publication_drain_20261005T064921Z_43a1e040` under `data/fundamentals_generations/`. Stale flat Fundamentals files are not used.

### Meaning Of EPS

Sharadar defines `epsdil` as the company's financial-statement diluted earnings per share, associated with common earnings, diluted weighted-average shares and share-factor treatment. It is a reported figure, not analyst-adjusted EPS. We use that scalar as supplied, not basic EPS and not a recomputation from net income or end-period shares. Basic `eps`/`epsusd` are used only for a currency crosscheck, never as the denominator. [Provider field documentation](https://sharadar.com/docs/fundamentals).

The current canonical ARQ observation is selected through exact common-earnings provenance. This does **not** switch to MRQ or claim all ARQ figures contain restatements: ARQ and MRQ have distinct provider meanings. Here revised history describes the current local reconstructed financial history rather than a proven original investor-visible scalar. [Sharadar reporting-dimension documentation](https://sharadar.com/docs/fundamentals).

### Currency And Share Compatibility

One consistent retained definition is **reported diluted EPS in USD per unit-share-factor domestic primary common share**. Eligibility requires:

1. Metadata category `Domestic Common Stock` or `Domestic Common Stock Primary Class`.
2. Finite `fxusd=1` and `sharefactor=1`; `eps` equals `epsusd` within `1e-8` tolerance as an independent USD crosscheck.
3. Finite positive `shareswadil` to confirm the diluted-share basis. Missing diluted-share data does not cause substitution of basic EPS.
4. Permanent provider security identity and exact ARQ fiscal/report-period identity match the canonical quarter.
5. No locally recorded split after the selected quarter's period end, no uncorrected price split, and no recorded later spinoff/ADR-ratio event in the inspected action types. The US market designation must match for both price rows.

The RawCandle [valuation contract](../../../docs/fundamentals_v4/fundamentals_v4_valuation_v1_implementation.md) treats prices/shares as retrospectively split-compatible. Provider documentation describes share-factor treatment but does not establish that every raw EPS field is automatically rebased to every later split. Therefore **we do not assert universal split adjustment of epsdil**: known later-action cases are excluded rather than inventing a conversion. ADR/non-USD/non-unit-share-factor inputs are not converted or mixed into this sample. Local action inventories are a guard, not proof of global corporate-action completeness.

Bootstrap observations often have NULL `provider_security_id` but durable matching `company_id` and `security_id`. Such rows are accepted only if both IDs equal the canonical security and that security has exactly one Sharadar permanent mapping. Explicit provider IDs, when present, must match. No ticker-only identity fallback is used. This corrected an over-restrictive preliminary research adapter, not production data.

The denominator is the **current accepted canonical ARQ observation's** `epsdil`, not another provider version chosen to fill gaps. Eight selected quarters lacked the field in that bound payload and remain excluded, even if basic EPS or another record might be available.

## Universe And Selection

Active taxonomy: **Datacenter taxonomy full v2 1 / DC_TAXONOMY_FULL_V2_1**.
**350 active membership rows / 257 unique tickers**. CORE 230 rows, EXTENDED 106, WATCH_ONLY 14. Every unique active ticker is considered; neither role nor `is_primary` filters the taxonomy universe.

Price dates are exactly **2025-10-03** and **2026-10-02**. No fallback, interpolation, dividends, forecasts, consensus or external financial values are added. Prices must be unique, finite and positive.

For each uniquely mapped active company, join all canonical quarters to publication authority by `(company_id, fiscal_year, fiscal_quarter)`. Select the quarter having the latest VERIFIED UTC timestamp whose UTC calendar date is no later than 2025-10-03. This implementation uses `< 2025-10-04` on normalized stored UTC timestamps. An authority/canonical quarter-ID mismatch, non-accepted fiscal identity or impossible period/publication relation is invalid. Tied latest timestamps across quarters are excluded rather than broken by an arbitrary quarter ID.

### Incomplete Publication Authority Rule

After selecting that VERIFIED candidate, inspect every other canonical quarter with period end no later than the cutoff. A missing/unverified-authority quarter blocks older-quarter fallback if either:

- Its existing `source_availability_date` or `first_public_result_date` is on/before the cutoff, and its period is at least as recent as the selected period **or** that date is at least as recent as the selected publication date; or
- Existing non-Yahoo evidence has an event timestamp between the selected publication and cutoff, inclusive of the selected timestamp and exclusive of 2025-10-04.

Provider dates here are **uncertainty flags only**, never publication authority. Their earlier-before-cutoff values can show that an unverified result may displace the chosen quarter. Later provider dates alone do not prove a before-cutoff release. Thus latest selection is proven among stored VERIFIED candidates and conservatively screened against observable unverified before-cutoff hints, not certified against all possible uncaptured issuer releases.

Seven companies were excluded by this rule: **AXTI, CSW, FCX, INTC, ITW, KLAC, WULF**. Their blocking quarter IDs are recorded in validation JSON. Where no eligible VERIFIED quarter exists, the primary category is `NO_ELIGIBLE_PUBLISHED_QUARTER`, not a guessed publication date. Zero/negative/missing EPS is evaluated only **after** quarter selection and never causes selection of an older positive quarter.

The semantic boundary is calendar-date eligibility, not exact market-close investability. A same-day after-close release could be date-eligible by the requested convention; this is another reason not to represent the study as an investable PIT strategy.

## Coverage And Exclusions

Independent price coverage: **256** valid exact start closes, **257** valid exact end closes. After price/publication screening, **190** quarterly results are selected; **182** have finite `epsdil`; **147** are positive before basis checks; **120** pass all checks.

Mutually exclusive exclusions follow the script's order: price absence/validity, identity, publication availability/completeness, EPS presence/sign, then basis. A malformed/nonfinite record is invalid rather than coerced to zero. Only the first applicable reason is counted.

| Exclusion | Count |
| --- | ---: |
| MISSING_START_PRICE | 1 |
| MISSING_END_PRICE | 0 |
| NO_ELIGIBLE_PUBLISHED_QUARTER | 59 |
| INCOMPLETE_PUBLICATION_AUTHORITY | 7 |
| MISSING_EPSDIL | 8 |
| ZERO_EPS | 0 |
| NEGATIVE_EPS | 35 |
| INVALID_EPS_BASIS | 27 |
| OTHER_INVALID_DATA | 0 |
| Total exclusions | **137** |

**257 - 137 = 120 final observations.** Basis exclusions: 21 missing diluted-share basis, four known later-action/split cases (APG, APH, IESC, NOW), and two not-confirmed domestic-primary common-share cases (CLS, IREN). This is deliberate conservative research coverage, not a production-quality diagnosis or evidence that all excluded EPS values are wrong.

## Formulas And Descriptive Statistics

```text
annualized_eps = selected_quarter_epsdil * 4
pe_2025_10_03 = close_2025_10_03 / annualized_eps
return_12m_pct = ((close_2026_10_02 / close_2025_10_03) - 1) * 100
```

Statistics and OLS use unrounded double-precision inputs. P10/P90 use linear-interpolated percentiles. CSV formatting alone uses two decimals. Sort is unrounded P/E ascending, with ticker tie-breaker. No TTM, normalization, winsorization, outlier deletion or weighting.

| Statistic | Quarterly annualized P/E | 12-month stored-Close return (%) |
| --- | ---: | ---: |
| N | 120 | 120 |
| Minimum | 8.495762 | -59.454421 |
| P10 | 17.904300 | -27.568196 |
| Median | 31.002793 | 30.915281 |
| Mean | 83.931562 | 55.799177 |
| P90 | 86.620591 | 149.392532 |
| Maximum | 3795.500183 | 562.609157 |

## Relationship

Unweighted OLS with intercept:

```text
return_12m_pct = 55.0919815321 + 0.0084258600 * pe_2025_10_03
N = 120
Pearson correlation = 0.0293584294
R-squared = 0.0008619174
```

Beta is percentage points of subsequent return per one P/E unit. In this unmodified sample, the linear relationship is extremely weak; R-squared corresponds to about **0.0862%** explained sample variance. This does not establish causality, a return forecast, statistical significance, or absence of a nonlinear relationship. No significance claim or trading recommendation is made.

## Outlier Inspection

| Ticker | Selected quarter end | Revised diluted EPS | P/E | Return (%) |
| --- | --- | ---: | ---: | ---: |
| DDOG | 2025-06-30 | 0.01 | 3795.50 | 82.60 |
| LSCC | 2025-06-28 | 0.02 | 908.87 | 84.29 |
| FLNC | 2025-06-30 | 0.01 | 344.75 | -44.82 |
| LITE | 2025-06-28 | 3.09 | 13.25 | 562.61 |
| VICR | 2025-06-30 | 0.91 | 13.47 | 530.02 |
| MU | 2025-08-28 | 2.84 | 16.52 | 472.74 |
| LEU | 2025-06-30 | 1.59 | 54.01 | -59.45 |
| BLDR | 2025-06-30 | 1.66 | 19.36 | -56.24 |
| ACM | 2025-06-30 | 0.98 | 32.89 | -53.72 |

Manual inspection re-read these nine bound provider payloads and both exact-date OHLC rows. Reported EPS and stored price endpoints reproduce the calculations; all nine closes lie between their positive stored Low/High. No demonstrable violation of the inspected source contract was found, so **all are retained**. Very small rounded reported EPS explains very large P/E and creates substantial leverage/rounding sensitivity. Reported diluted EPS need not equal a mechanically recomputed common-income/share ratio; no substitute EPS was constructed. Large price changes remain flagged as data-sensitive rather than independently externally verified.

The full-scale linear scatter preserves DDOG and LSCC rather than truncating the X axis. This compresses most observations toward the left and makes OLS sensitivity to extreme P/E visually apparent. Only DDOG and LITE are labeled.

## Interpretation And Validation

- Current taxonomy induces survivorship/current-membership selection; the result does not describe a historical all-stock universe.
- Publication-authority coverage and conservative EPS-basis checks select only 120 of 257 stocks. Excluded observations may differ systematically from the retained sample.
- Current reconstructed ARQ values are not original PIT EPS. A VERIFIED result timestamp does not make the scalar originally investor-visible.
- Return is the requested arithmetic ratio of stored Close fields. No dividend cashflow, reinvestment or total-return transformation is added. Existing price backadjustments are retained: RawCandle split refetch uses Yahoo `history()` defaults, so some stored history may already contain dividend backadjustment. This study cannot certify a universally unadjusted exchange-price return and must be read as **stored-Close return**, not verified total return. No new Yahoo data was fetched and no correction was applied.
- Eight focused pure-function tests passed, including fiscal-versus-publication selection, unverified newer/event blocking, timestamp ties, EPS basis, nonfinite inputs and unmodified OLS. No full suite ran.
- CSV validation passed: exactly three requested columns, 120 unique taxonomy tickers, exact price dates, positive EPS/prices, finite values, no NULLs, formula parity, two-decimal formatting, unrounded ordering and exact exclusion reconciliation.
- Plot inspected visually; all 120 observations, OLS and zero-return line render without overlap or clipping.
- Before/after SHA-256 checks passed for provider, canonical, Fundamentals analysis, market, taxonomy database files and the active-generation pointer. No production DB/schema/calculation/taxonomy/scheduler changes. No acquisition, enrichment, publication retry, refresh or scheduler operation.
- Documentation-only public lookups established provider field semantics; every numeric observation came from existing local RawCandle data. No external financial values entered the sample.
- Commit contains research script, focused tests, this report, small final CSV/plot and provenance validation artifact only. No DB copies, cache files, raw provider payloads or runtime logs; no push.
