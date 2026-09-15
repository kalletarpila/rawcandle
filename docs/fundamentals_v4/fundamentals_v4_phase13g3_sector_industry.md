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

## Test Evidence

Focused regression suite:

```text
25 passed in 7.87s
25 passed in 7.91s
25 passed in 8.00s
```

Covered behavior includes full scan classification, filtered ticker and alias resolution, durable progress artifacts, stale preview rejection, copy-lane correction and repeat no-change, downstream skip for no-change, and rollback after injected post-mutation failure.
