# Phase 13G.2.5A: V2 current-state source correction

## Outcome and architecture

Completed on copies, without a production apply. Current V2 calculation no longer takes Score V1 implementation or persisted Score/Valuation V1/RP history as current-state authority. Score V2 owns its scoring arithmetic in `score_calculation.py`; Valuation V2 consumes canonical V4 TTM and the current `osakedata.db` price/classification source; RP V2 uses current `ticker_meta` for Sector/Industry and active `analysis.db` `dc_ecosystem` for Ecosystem. The package still publishes Score, Lifecycle, Valuation, Delta, Diagnostics and RP together. No RP-only publication path was added.

The V2 date contract is `as_of_date` on `rehearsal.calculate`, `phase10b.calculate` and `pipeline.refresh_active_package`. It controls information availability, 180-day freshness, structural eligibility and RP snapshot date. The centralized omitted-date resolver uses the current UTC date. Archived Phase 9 rehearsals pass their historical date explicitly; it is no longer the current-production default.

## Score and Valuation

Score V2 formerly called `score.engine.compute_score_rows` and `trajectory_points` after mapping operating income into the V1 EBIT field. The V2-owned calculation retains the same arithmetic and output/evidence schema, with no V1 production-engine import. Across all 87,860 production-shaped Score rows, persisted V2 versus corrected V2 had **0 status and 0 total-score changes**. A test blocks V1 scoring functions and still computes V2; the V1-row isolation run reproduced every V2 fingerprint.

Valuation V2 formerly preferred persisted V1 Valuation fields (including selected price, shares and classification) whenever a V1 row existed. Every row now uses `valuation.persistence.load_canonical_source`: canonical V4 supplies period, financials, cash, debt and shares; `osakedata.db` supplies the source-date price and `ticker_meta` supplies Sector/Industry. No persisted V1 Valuation row is used in the calculation or persistence context. The V1-row isolation run produced identical V2 fingerprints.

At fixed source data, 5,965 Valuation quarter rows across 2,011 companies changed. Selected price changed in 5,846 rows, shares in 184, market cap and EV in 5,920, score in 5,752, and status in 5,696. Sector and Industry changed in **0** rows. Status transitions were 5,634 `NOT_READY -> FULL` and 62 `FULL -> NOT_READY`. Example: early `A` quarters gained source-date prices and became FULL; `ARTL` quarters use lower canonical shares, yielding nonpositive EV and correctly becoming NOT_READY. `APH` illustrates split-related price/shares differences. These are source corrections, not a Score formula change.

## RP and taxonomy dependency

Sector/Industry still read `ticker_meta`; prior RP snapshots are no longer queried for ecosystem membership. The active Datacenter taxonomy is stored in the existing `ec_*` sidecar tables and interpreted by the admin `dc_ecosystem` contract. `CORE` and `EXTENDED` qualify, `WATCH_ONLY` does not. The ranking group remains `DATACENTER` at ecosystem level; primary flag and layer/subindustry do not create separate RP groups. Multiple eligible memberships remain deterministic and deduplicate into one company/ecosystem group. Membership mapping uses all active canonical `security` ticker identities, so the active `GOOGL` membership maps to the same company as its `GOOG` TTM security. 32 taxonomy tickers currently lack an active canonical security mapping and cannot produce RP membership until identity/source coverage is reconciled.

The exact loaded taxonomy dependency is: domain `dc_ecosystem`, version `DC_TAXONOMY_FULL_V2_1`, admin semantic fingerprint `801698f6b352c445cc8e6f5fd51a1cac2779d11f6ce72a1c10bf71bb8aae4559`. The same loaded rows supply both membership construction and that existing semantic hash. RP uses the hash in its source fingerprint; the copy's `relative_position_v2_taxonomy_dependency` row records domain, version, semantic hash, snapshot date and RP source fingerprint (`46f5962ca4938fa2f65e9e9579f557fe42c844ea3f9e337530e48b409c55a54d`). Tests establish stable hashing and role/version sensitivity.

## Production-shaped copy rehearsal

Controlled date: **2026-09-18**. Only `fundamentals_analysis.db` was backed up into a writable temporary copy. Canonical, provider, market and taxonomy databases were opened for reading; `analysis.db` taxonomy was not modified. First corrected package: `APPLIED`; second identical calculation and apply: `NO_CHANGE`, 0 logical changes. Economic fingerprint `f377ebd50789b2f9ed6d7932528fb8c2faeb7f779a35ab03dea9cad27026980c`; physical fingerprint `8a87b1d4ff8c6a650a6da487defd7df176b8a3e23986b76ad287b7d6660d5d49`. All seven calculation-layer fingerprints matched between runs. RP snapshot ID remained `40595b1b66c784a7ebda47f1aa5e61c437d26970d26b6d5b2a923cf4283bf9a7` on the repeat; no physical snapshot was recreated by `NO_CHANGE`.

The copy held 87,860 Score, 87,860 Valuation and 13,799 RP result rows (19,696 RP coverage rows). V1 Score/result components, Valuation, RP snapshots/results/coverage had identical row counts and value hashes before and after. `PRAGMA quick_check=ok`, 0 foreign-key errors. The source copy was removed after success. Durable events, full fingerprints/counts, and a plain-language operation report are in `temp/phase13g25a_20260918_copy_retry/`.

An additional isolated copy had all V1 Score results/components (50,585/354,095), V1 Valuation results (50,585), and V1 RP snapshots/results/coverage (2/27,468/39,192) removed. `phase10b.calculate(..., verify_v1_overlap=False, as_of_date='2026-09-18')` still produced 87,860 Score, 87,860 Valuation and 13,799 RP rows with **identical fingerprints on every V2 calculation layer**. This intentionally incomplete test copy was deleted immediately afterward. No production V1 data was deleted.

The first rehearsal attempt stopped on a faulty test-only digest that serialized `sqlite3.Row` object addresses rather than values. A later retry exposed a test-driver error: it applied the default persistence fingerprint instead of the active `TEN_YEAR` package fingerprint, which RV source validation correctly rejected. The driver now uses the active fingerprint; all failed-attempt copies were removed after diagnosis. Neither issue wrote to production.

## Delta and date separation

The current production V2 RP snapshot is dated **2026-09-06** and has 13,797 results: Sector 4,464, Industry 4,464, Ecosystem 405, Universe 4,464. Recalculating corrected V2 at the **same** 2026-09-06 date with current read-only sources yields 13,805: Sector 4,462, Industry 4,462, Ecosystem 419, Universe 4,462. At this fixed date, Ecosystem adds 14 results and removes 0; shared-result changes are Sector 685, Industry 328, Ecosystem 401 and Universe 2,254. This comparison isolates the new code/source behavior from the changed calculation date, but cannot reconstruct historical taxonomy content that is no longer active.

At **2026-09-18**, corrected RP has 13,799 results: Sector 4,460, Industry 4,460, Ecosystem 419, Universe 4,460. Thus moving the corrected calculation date from September 6 to September 18 removes two result rows each from Sector/Industry/Universe and none from Ecosystem. Compared directly with current production at different dates, Sector/Industry/Universe each have one added and five removed result keys; Ecosystem has 14 added and 0 removed. Rank changes at different dates must not be attributed solely to the source correction.

The seven newly participating ecosystem tickers are `AG`, `ALOY`, `ARM`, `ASML`, `ASX`, `BABA` and `SNDK`, two RP measures each. `GOOG` remains included through its other active ticker `GOOGL`; the original TTM-only identity attempt incorrectly dropped it and was corrected before acceptance.

## Recent ticker audit

`EC` is the number of ready ecosystem RP measures (Score and Valuation); all listed Sector/Industry values come from current `ticker_meta`. Production EC was 0 for every listed ticker.

| Ticker | Score V2 | Valuation V2 | Sector / Industry | Active DC role | Corrected EC | Explanation |
| --- | --- | --- | --- | --- | ---: | --- |
| SNDK | FULL | FULL | Technology / Computer Hardware | EXTENDED, CORE | 2 | New eligible member |
| AG | FULL | FULL | Basic Materials / Silver | EXTENDED | 2 | New eligible member |
| ALOY | FULL | FULL | Basic Materials / Other Industrial Metals & Mining | EXTENDED | 2 | New eligible member |
| ARM | FULL | FULL | Technology / Semiconductors | CORE, CORE | 2 | Two memberships, one ecosystem group |
| ASML | FULL | FULL | Technology / Semiconductor Equipment & Materials | CORE | 2 | New eligible member |
| ASX | FULL | FULL | Technology / Semiconductors | EXTENDED | 2 | New eligible member |
| BABA | FULL | FULL | Consumer Cyclical / Internet Retail | CORE | 2 | New eligible member |
| BHP | NOT_READY | NOT_READY | Basic Materials / Other Industrial Metals & Mining | EXTENDED | 0 | Financial input not ready |
| BIDU | NOT_READY | NOT_READY | Communication Services / Internet Content & Information | CORE | 0 | Financial input not ready |
| BTDR | FULL | FULL | Technology / Software - Application | None | 0 | No active DC membership |
| CAMT | NOT_READY | NOT_READY | Technology / Semiconductor Equipment & Materials | CORE, CORE | 0 | Financial input not ready |

## RV, remaining V1 code, and next phase

RV's read-only source fingerprint changed from `22224dc8f6115aab8b279b4875bfbcdc928d07ce46db94cf28acd5fb53b5e5c7` to `b256f99f72042261ba75d9e4d11aede3b4448cf04ec166e48d5d11d133c8e94b` on the copy at the same date, while both sources held 2,444 inputs. Future V2 production repair must recalculate and validate RV after publishing the corrected V2 package. No production RV calculation or apply was run here.

Score V2 no longer imports the V1 production engine. Active V2 Valuation, RP, Lifecycle and Delta wrappers still import V1 engines or types as implementation dependencies; those are **future full-V1-retirement blockers**, not V1 persisted-result authority in this corrected current-state calculation. V1 overlap comparison is diagnostic and opt-in. The Phase 13F3.1 Add Tickers caller still opts into that comparison for certain packages; its routing was deliberately not changed. Historical V1 routes and tests/docs remain. The next single phase is **V2-only update/persistence paths and caller integration** for Add Tickers and later taxonomy synchronization, followed by a separately authorized production repair.

## Tests and safety

Final relevant suite: **239 passed, 0 skipped, 0 failed** in 245.92 seconds. Exact test command:

```bash
pytest -q tests/test_fundamentals_v4_operating_income_v2.py tests/test_fundamentals_v4_operating_income_v2_persistence.py tests/test_fundamentals_v4_operating_income_v2_phase9e.py tests/test_fundamentals_v4_operating_income_v2_phase10c.py tests/test_fundamentals_v4_diagnostic_flags_phase10b.py tests/test_fundamentals_v4_relative_position_engine.py tests/test_fundamentals_v4_relative_position_source.py tests/test_fundamentals_v4_relative_position_persistence.py tests/test_fundamentals_v4_relative_valuation_engine.py tests/test_fundamentals_v4_relative_valuation_source.py tests/test_fundamentals_v4_relative_valuation_persistence.py tests/test_fundamentals_v4_relative_valuation_production.py tests/test_fundamentals_v4_operating_income_v2_current_sources.py tests/test_fundamentals_admin_taxonomy.py tests/test_fundamentals_admin_taxonomy_acceptance.py tests/test_fundamentals_admin_taxonomy_production.py tests/test_fundamentals_admin_batch_add_tickers.py tests/test_phase13b_foundation.py tests/test_phase13f3_1_package_recovery.py
```

The copy rehearsal's successful invocation was `python3 -m rawcandle.fundamentals.operating_income_v2.phase13g25a_rehearsal --output temp/phase13g25a_20260918_copy_retry --as-of-date 2026-09-18 --resume-copy`. The output directory contains its JSONL event log and machine-readable result. The V1-row isolation was an additional one-off copy calculation, not a committed production path. No test skips or persistent failures; the two rehearsal-driver failures above were diagnosed and corrected.

No production database writes, pointer changes, taxonomy writes, Add Tickers routing changes, production RV run, V1 data deletion, global V1 retirement or push occurred. All write operations were confined to phase-owned temporary copies, which were removed. Source code, tests and this report are the only intended committed changes.
