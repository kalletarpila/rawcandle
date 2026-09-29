# Daily-research result-publication service

Date: 2026-09-29

Projection rule: `result_publication_daily_research_v1`

Decision: `DAILY_RESEARCH_SERVICE_READY`

## 1. Purpose

`DailyResearchPublicationService` makes the validated daily-research publication boundary available to application and export code without persisting research state or changing canonical authority. It assembles one or more canonical quarter identities, current SEC evidence, security identities, observed OHLC calendars, and optional Yahoo/V2 inputs, then delegates every heuristic decision to `project_daily_research`.

The service is read-only by construction. It does not expose a write, migration, cache-persistence, or canonical-resolution API.

## 2. Architecture

```text
canonical authority/evidence (read-only)
security identity + osakedata calendar (read-only)
optional Yahoo/V2 providers
                |
                v
DailyResearchPublicationService (assembly only)
                |
                v
project_daily_research (all heuristic decisions)
                |
                v
DailyResearchServiceResult
```

The service is in `rawcandle/fundamentals/result_publication_daily_research_service.py`. The existing projection remains in `rawcandle/fundamentals/result_publication_daily_research.py`; no heuristic branch is duplicated in the service.

## 3. Canonical and research separation

The stable lookup identity is `(company_id, fiscal_year, fiscal_quarter)`. Ticker is used only to load a practical OHLC calendar and optional Yahoo observations. Evidence is scoped to the requested quarter and restricted to current `SEC_8K_ITEM_2_02` rows with `ACCEPTED` or `CONFLICT` disposition.

Canonical VERIFIED rows bypass Yahoo and V2 providers and project directly to EXACT. Rows without SEC candidates also skip both providers. AMBIGUOUS rows may become heuristic. UNRESOLVED and NOT_FOUND remain UNUSABLE without current SEC candidates; Yahoo alone cannot make them usable.

Both database connections use SQLite URI `mode=ro` plus `PRAGMA query_only=ON`. There are no INSERT, UPDATE, DELETE, schema, or migration paths.

## 4. Service API

```python
from rawcandle.fundamentals.result_publication_daily_research_service import (
    DailyResearchPublicationService,
    QuarterKey,
)

with DailyResearchPublicationService(
    "data/fundamentals_v4.db",
    "data/osakedata.db",
    yahoo_provider=yahoo_provider,
    v2_provider=v2_provider,
) as service:
    one = service.get_daily_research_result(7, 2026, "Q3")
    many = service.get_daily_research_results([
        QuarterKey(7, 2026, "Q3"),
        (448, 2025, "Q1"),
    ])
```

`get_daily_research_result` and `get_daily_research_results` return `DailyResearchServiceResult`. Its `result` is the existing `DailyResearchResult`; `to_dict()` flattens the projection fields together with ticker, calendar, Yahoo, V2, canonical flag, and warning metadata.

Missing canonical identities raise `QuarterNotFoundError`. Duplicate batch keys raise `ValueError`. Input order is preserved.

## 5. Data sources

The service reads:

- `v4_result_publication_authority` joined to `v4_quarter` by `quarter_id`;
- quarter-scoped `v4_result_publication_evidence` SEC rows;
- every `security.current_ticker` for requested company identities;
- ticker-scoped `osakedata(osake,pvm)` rows;
- optional injected Yahoo and V2 providers.

Batch SQL uses bounded chunks and two long-lived read-only connections. Security and evidence joins use company/quarter identity, never ticker identity.

## 6. OHLC calendar semantics

Observed ticker dates are cached in process memory for the service lifetime. No calendar cache is written to disk or either production database. Security history is handled by considering all company tickers and retaining calendars whose observed range covers the relevant canonical/candidate publication dates.

When multiple relevant tickers exist, the projection runs against each calendar. Status, method, selected timestamp, and effective day must agree. A heuristic disagreement becomes `UNUSABLE/TICKER_CALENDAR_DISAGREEMENT`; an EXACT row remains canonical but exposes no guessed effective day. Missing OHLC produces `OHLC_CALENDAR_UNAVAILABLE` for non-canonical evidence.

Session and first-full-day semantics remain owned by the existing projection. No market-calendar package or invented trading date was added.

## 7. Optional Yahoo behavior

`YahooObservationProvider` is an injected protocol. Provider exceptions are converted to assembly provenance such as `ERROR:RuntimeError`; projection continues with no Yahoo observations. VERIFIED rows do not call the provider.

`MappingYahooObservationProvider` supports deterministic frozen observations for tests, exports, and reproducible validation. `YFinanceYahooObservationProvider` is a narrow live adapter around `Ticker.get_earnings_dates()`. It imports yfinance lazily, accepts only timezone-aware observations between canonical period end and +180 days, and writes nothing.

Full validation used frozen observations from the previously reviewed 651-quarter Yahoo artifact. Live Yahoo was intentionally not used for the count gate because availability and provider output can change.

## 8. Optional V2 behavior

`V2CandidateProvider` supplies only an externally validated SEC candidate identifier. `MappingV2CandidateProvider` is the deterministic implementation used for validation. The service neither embeds nor recreates the experimental V2 semantic classifier.

The identifier still has to match a current quarter-scoped SEC evidence candidate inside the projection. Without a provider or match, projection continues through the existing Yahoo/SEC-only rules.

## 9. Provenance and warning contract

Every response preserves research status, confidence, method, projection rule version, canonical status/timestamp, selected SEC reference, Yahoo date/distance, ticker set, calendar status, Yahoo provider status, and V2 identifier.

`is_canonical` is true only for EXACT. Every HIGH or MEDIUM result uses the shared warning:

```text
Suitable for hobby daily-OHLC research. Not canonical publication authority and not intended for precision event studies.
```

UNUSABLE has a separate compact unavailable warning. Warning prose is defined once in the service module and is not scattered through UI code.

## 10. Tests

Focused service tests cover:

- VERIFIED -> EXACT without Yahoo/V2 calls;
- same-effective-day ambiguity;
- Yahoo-near-unique SEC selection;
- V2 precedence;
- Yahoo failure degradation;
- UNRESOLVED and NOT_FOUND without SEC candidates;
- missing OHLC;
- ticker lookup and multi-ticker disagreement;
- batch ordering and calendar reuse;
- actual read-only write rejection and unchanged rows;
- warning/provenance output;
- missing/duplicate keys and deterministic repeated results.

Together with projection and existing authority/PIT tests, 38 focused tests passed. No unrelated score, valuation, or DC tests ran.

## 11. Production read-only validation

The new service processed all 16,210 FY2025+ authority rows with frozen Yahoo observations and the externally validated V2 map. It exactly reproduced the accepted validation:

| Research status | Count |
|---|---:|
| EXACT | 12,782 |
| HEURISTIC_HIGH | 570 |
| HEURISTIC_MEDIUM | 0 |
| UNUSABLE | 2,858 |

Methods were canonical 12,782; same-effective-day 11; V2 strong 76; Yahoo-near-unique 483; Yahoo no-unique-cluster 52; SEC candidates too dispersed 29; and no SEC candidate 2,777.

Representative production checks included:

- AAPL, NVDA, AMZN, and ADBE -> EXACT;
- CF -> HIGH / all candidates same effective day;
- ABG, ORN, and BKD -> HIGH / Yahoo-near-unique;
- DTE and GSIT -> HIGH / V2 strong;
- three UNRESOLVED and three NOT_FOUND controls -> UNUSABLE / no SEC candidate.

All calls used the same read-only service path as the full batch.

## 12. Performance

The first full 16,210-row batch, including authority/evidence/security assembly, ticker calendar loading, frozen provider lookup, and projection, completed in 10.37 seconds: approximately 1,563 rows/second on the current host.

The service avoids one connection per row, loads SQL in chunks, caches each ticker calendar once per process, and skips Yahoo/V2 for VERIFIED rows. No concurrency was required.

## 13. Limitations

- Live Yahoo remains optional and nondeterministic; reproducible exports should inject frozen reviewed observations.
- V2 candidate production is external to this service by design.
- Research results are computed on demand and are not historical snapshots.
- One latest-date VERIFIED after-market row can remain EXACT with a null effective day until the next OHLC date is observed.
- Calendar history is practical ticker OHLC coverage, not an exchange master calendar.
- The service is not yet wired into a UI, export command, or broader application facade.

## 14. Safety and next step

Before and after implementation and validation:

- `data/fundamentals_v4.db` SHA-256: `9c1c14be2f52165f93d4c9d30aba8bb64fc5489e37190ed9fb672ffa993caaad`;
- authority counts: 12,782 VERIFIED, 864 UNRESOLVED, 651 AMBIGUOUS, 1,913 NOT_FOUND;
- evidence counts: 12,782 ACCEPTED and 1,318 CONFLICT;
- `PRAGMA quick_check`: `ok`; foreign-key errors: zero;
- `data/forecasts.db` SHA-256: `8fc6785ce83f8a94a0cb80be8d1514e6a9f3ea1d42ac33b9d2081f83ffc9cd42`;
- scheduler and systemd unit files: unchanged.

Gate: `DAILY_RESEARCH_SERVICE_READY`.

The exact next step is to wire this service into one read-only research/export consumer, inject a reviewed Yahoo observation source and V2 map at that composition boundary, display the shared non-canonical warning for heuristic rows, and keep UNUSABLE rows excluded. That integration must continue to avoid persistence and canonical authority changes.
