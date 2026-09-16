# Phase 13G.3 Sector/Industry Administration CLI

Date: 2026-09-15

## Summary

Phase 13G.3 added an independent `CHECK_UPDATE_SECTOR_INDUSTRY` administration CLI for comparing persisted Sector/Industry classifications against `data/osakedata.db.ticker_meta`.

The operation is copy-only for apply mode. It does not call Batch Add Tickers, fetch provider/network data, add or remove universe members, or write production databases.

## Scope

- Source of truth: `ticker_meta.sector` and `ticker_meta.industry`.
- Persisted target inspected and corrected on copies: `valuation_revised_result.sector` and `valuation_revised_result.industry`.
- Default scan: full active operational universe from the active universe version.
- Optional scan: positional ticker filters and `--input-file`.
- Review-only boundaries: ambiguous source rows, missing source classification, multi-security identity rows, structural-event rows, and non-applicable rows.

## Durable Runs

Runs are written under `fundamental_reports/admin_runs/` with:

- `request.json`
- `preview.json`
- `sector_industry_preview_payload.json`
- `items.csv`
- `result.json`
- `report.md`
- progress status, stages, events and heartbeat logs

Apply mode validates the saved preview fingerprint and source state before any copy mutation. Stale previews are rejected.

## Production-Shaped Evidence

Full production read-only preview:

- Run: `20260915T172851Z_check_update_sector_industry_6cd2344cb214`
- Preview fingerprint: `7aa8299333cc7bd2c5c8b033c457907eb68fd099d60e8b3ac46c1554bc253e4f`
- Inspected: `2453`
- Exact match: `2440`
- Identity review required: `11`
- Not applicable: `2`
- Correctable: `0`

Copy-only apply from that preview:

- Run: `20260915T172924Z_check_update_sector_industry_94ec7faf309f_apply`
- Outcome: `COMPLETED`
- Classification correction: `NO_CHANGE`, `rows_changed=0`
- Downstream invocation counts: package `0`, Relative Position `0`, Relative Valuation `0`
- Repeat outcome: `NO_CHANGE`
- Copy lane cleanup: completed; copy lane removed
- Production databases: unchanged by design

Filtered production preview:

- Run: `20260915T173048Z_check_update_sector_industry_d6a4f9622595`
- Inputs: `AG AAPL GOOG MISSING13G3`
- Inspected: `4`
- Exact match: `2`
- Identity review required: `1`
- Not applicable: `1`
- Correctable: `0`

## Phase 13G.3.1 Population Reconciliation

Read-only audit run:

- Run: `20260915T181656Z_check_update_sector_industry_4538db5d046d_phase13g31_audit`
- Outcome: `OUTCOME A - SECTOR/INDUSTRY SCAN POPULATION FULLY RECONCILED`
- Production databases changed: `no`
- Production DB health: `quick_check=ok`, `foreign_key_check_rows=0` for provider, canonical, analysis, market and taxonomy databases
- Active package, Relative Position and Relative Valuation identities: unchanged before/after audit

The Phase 13G.3 full-scan denominator is the active operational-universe membership population:

```text
2469 total OU member rows
- 16 historical retained/no-active rows
= 2453 active OU member rows
= 2453 Phase 13G.3 scan subjects
= 2440 exact + 0 normalized + 11 identity-review + 2 not-applicable
  + 0 missing-source + 0 ambiguous-source + 0 structural-review
  + 0 change-required + 0 missing-persisted
```

The apparent mismatch with the active-security count is expected. The active universe has `2464` active securities because `11` active multi-security companies each have two active security components. Phase 13G.3 intentionally scans active membership rows and records these `11` multi-security companies as `IDENTITY_REVIEW_REQUIRED` instead of automatically expanding and mutating per-security classifications.

SNDK and all ten Phase 13G.2.4 production-onboarded tickers (`AG`, `ALOY`, `ARM`, `ASML`, `ASX`, `BABA`, `BHP`, `BIDU`, `BTDR`, `CAMT`) are active single-security operational-universe members, included in the Phase 13G.3 scan, resolved with market `usa`, and classified as `EXACT_MATCH` against `ticker_meta`.

The `IDENTITY_REVIEW_REQUIRED` cases are:

```text
CENT,CENTA
FOX,FOXA
FWONA,FWONK
GOOG,GOOGL
LBTYA,LBTYK
LILA,LILAK
LLYVA,LLYVK
METC,METCB
NWS,NWSA
UA,UAA
Z,ZG
```

The `NOT_APPLICABLE` cases are:

```text
BATRK
BELFB
```

Durable 13G.3.1 artifacts include `population_reconciliation.json`, full `ticker_reconciliation.csv/json`, `named_ticker_reconciliation.csv/json`, `identity_review_not_applicable_cases.csv/json`, `production_db_integrity.json`, `active_identity_pre_post.json`, `disk_hygiene.json`, `report.md`, `result.json`, `status.json`, `exit_code` and `artifact_manifest.json`.

## Phase 13G.3.2 Protected Production Mode

Phase 13G.3.2 added protected production-mode CLI wiring for `CHECK_UPDATE_SECTOR_INDUSTRY`.

The production mode is no-change-only for this phase: it requires a saved full-universe preview, exact protected production paths, clean worktree, maintenance lock, accepted 13G.3.1 population counts and zero safely applicable changes. If any safe production classification change appears, the runner stops before the write boundary.

Details and evidence are documented in [fundamentals_v4_phase13g3_2_protected_production_mode.md](fundamentals_v4_phase13g3_2_protected_production_mode.md).

## Phase 13G.3.2.1 Production NO_CHANGE Closure

Phase 13G.3.2.1 ran a fresh protected production verification after the corrected logical-state comparator and the `NO_CHANGE` terminal-result contract were in place.

- Fresh preview: `20260916T054622Z_check_update_sector_industry_6cd2344cb214`
- Preview fingerprint: `f6b178372c72474df3463f5236f724968ce37020990e27bfa1947afc074bcdc1`
- Production run: `20260916T054727Z_check_update_sector_industry_b29afb4f6b77_production`
- Outcome: `NO_CHANGE`
- Write boundary crossed: `false`
- Classification writes: `0`
- Package/RP/RV invocations: `0/0/0`
- Backup or rollback: `not required`

The stock update scheduler was stopped through its user-systemd timer/service before verification and kept stopped until postflight checks completed. Details and evidence are documented in [fundamentals_v4_phase13g3_2_1_production_no_change_closure.md](fundamentals_v4_phase13g3_2_1_production_no_change_closure.md).

## Test Evidence

Focused regression suite:

```text
25 passed in 7.87s
25 passed in 7.91s
25 passed in 8.00s
26 passed in 8.49s
46 passed in 124.35s (admin regression)
```

Covered behavior includes full scan classification, filtered ticker and alias resolution, durable progress artifacts, stale preview rejection, copy-lane correction and repeat no-change, downstream skip for no-change, and rollback after injected post-mutation failure.
