# Phase 13G.3.2 Protected Sector/Industry Production Mode

Date: 2026-09-15

## Outcome

`OUTCOME C - MATERIAL WRITE-PATH OR ROLLBACK DEFECT; PRODUCTION UNCHANGED OR RESTORED`

Production was not changed. The single allowed protected production invocation stopped before the write boundary with `write_boundary_crossed=false`.

The failed production invocation exposed a production no-change verification defect: the logical-state compare used the full physical `database_inventory` payload, which can include physical/noise fields that are not part of the logical database state. The implementation was corrected to compare only schema fingerprints, row counts, table logical fingerprints, integrity results and active package/RP/RV identities. The corrected code was verified, but the production invocation was not rerun because this phase allowed no more than one production invocation.

## Implementation Summary

Phase 13G.3.2 added protected production mode to the independent `CHECK_UPDATE_SECTOR_INDUSTRY` workflow.

- Preview remains the default.
- Copy-only apply remains available.
- Production mode requires `--apply --production --confirm-production`.
- Production mode consumes a saved preview payload and preview fingerprint.
- Production mode requires a full-universe preview.
- Production mode rejects stale or mismatched previews.
- Production mode validates exact protected production paths and rejects path aliases, symlinks and SQLite URI variants through the shared Phase 13G production path contract.
- Production mode acquires the established maintenance lock.
- Production mode fails closed unless the accepted Phase 13G.3.1 population contract is still present and safely applicable changes remain zero.
- The permitted production path in this phase is no-change only: zero classification writes and zero package/RP/RV invocations.

Writable/read-only role contract:

- Writable only when separately authorized for changes: `analysis`, because Sector/Industry corrections, package refresh, Relative Position, Relative Valuation and dependency attachment persist there.
- Read-only: `provider`, `canonical`, `market`, `taxonomy`.
- `market` remains the authoritative `ticker_meta` source.
- `taxonomy` remains Datacenter taxonomy and is not modified by this operation.

## Commands

Fresh production preview:

```bash
python3 -m rawcandle.cli.run_fundamentals_admin_sector_industry --quiet-progress
```

Protected production invocation:

```bash
python3 -m rawcandle.cli.run_fundamentals_admin_sector_industry \
  --apply \
  --production \
  --confirm-production \
  --preview-payload fundamental_reports/admin_runs/20260915T190342Z_check_update_sector_industry_6cd2344cb214/sector_industry_preview_payload.json \
  --preview-fingerprint 7aa8299333cc7bd2c5c8b033c457907eb68fd099d60e8b3ac46c1554bc253e4f \
  --quiet-progress
```

## Fresh Production Preview

- Run: `20260915T190342Z_check_update_sector_industry_6cd2344cb214`
- Preview fingerprint: `7aa8299333cc7bd2c5c8b033c457907eb68fd099d60e8b3ac46c1554bc253e4f`
- Scan subjects: `2453`
- Exact matches: `2440`
- Identity review required: `11`
- Not applicable: `2`
- Safely applicable changes: `0`

The eleven review-only multi-security cases remained:

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

The not-applicable cases remained:

```text
BATRK
BELFB
```

SNDK and all Phase 13G.2.4 tickers remained included and exact:

```text
SNDK
AG
ALOY
ARM
ASML
ASX
BABA
BHP
BIDU
BTDR
CAMT
```

## Production Invocation

- Run: `20260915T190413Z_check_update_sector_industry_94ec7faf309f_production`
- CLI outcome: `FAILED`
- Terminal stage: `FAILED_BEFORE_WRITE`
- Write boundary crossed: `false`
- Rollback required: `no`
- Backup required: `no`
- Production classification writes: `0`
- Package/RP/RV invocations: `0/0/0`

The run accepted the Phase 13G.3.1 population gate and recorded:

```text
Production no-change gate accepted; no write boundary will be crossed.
```

It then failed during final state comparison with:

```text
PHASE13G3_PRODUCTION_LOGICAL_STATE_CHANGED_UNEXPECTEDLY
```

Root cause: the compare included full physical inventory fields instead of logical-only database state. The code now uses `_production_logical_state(...)`, which compares only logical database content and active identities.

No second production invocation was run.

## Verification

Focused and admin tests:

```text
pytest tests/test_fundamentals_admin_sector_industry.py
12 passed in 10.16s

pytest tests/test_fundamentals_admin_*.py
50 passed in 130.10s

pytest tests/test_fundamentals_admin_sector_industry.py
13 passed in 9.13s

pytest tests/test_fundamentals_admin_*.py
51 passed in 125.37s
```

Relevant downstream/readers tests:

```text
pytest tests/test_phase13f1_reconciliation.py tests/test_phase13f2_date_aware_policy.py tests/test_phase13f3_1_package_recovery.py tests/test_phase13f3_4_structural_integration.py tests/test_structural_break_contract.py tests/test_fundamentals_v4_relative_position_production.py tests/test_fundamentals_v4_relative_valuation_source.py tests/test_fundamentals_v4_relative_valuation_persistence.py tests/test_fundamentals_v4_relative_valuation_production.py tests/test_fundamentals_v4_company_snapshot.py
118 passed in 21.37s
```

Durable full suite before production invocation:

```text
temp/fundamentals_admin_phase13g3_2_sector_industry/full_active_suite
exit_code=0
3017 passed, 14 deselected, 8 warnings in 904.94s
```

Durable full suite after logical-state fix:

```text
temp/fundamentals_admin_phase13g3_2_sector_industry/full_active_suite_after_logical_state_fix
exit_code=0
3018 passed, 14 deselected, 8 warnings in 872.65s
```

Compile and whitespace:

```text
python3 -m compileall rawcandle/fundamentals/admin/sector_industry.py rawcandle/cli/run_fundamentals_admin_sector_industry.py tests/test_fundamentals_admin_sector_industry.py
passed
```

Post-invocation read-only production checks:

- Provider DB: `quick_check=ok`, `foreign_key_check_rows=0`
- Canonical DB: `quick_check=ok`, `foreign_key_check_rows=0`
- Analysis DB: `quick_check=ok`, `foreign_key_check_rows=0`
- Market DB: `quick_check=ok`, `foreign_key_check_rows=0`
- Taxonomy DB: `quick_check=ok`, `foreign_key_check_rows=0`
- Active Operating-Income package: `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- Active Relative Valuation result: `07134cf7346b7535779a93f5aa56196c59a49093b4880c220a24c5d2ab11a428`

## Durable Evidence

- Fresh preview: `fundamental_reports/admin_runs/20260915T190342Z_check_update_sector_industry_6cd2344cb214`
- Production invocation: `fundamental_reports/admin_runs/20260915T190413Z_check_update_sector_industry_94ec7faf309f_production`
- Full suite before production: `temp/fundamentals_admin_phase13g3_2_sector_industry/full_active_suite`
- Full suite after fix: `temp/fundamentals_admin_phase13g3_2_sector_industry/full_active_suite_after_logical_state_fix`

## Disk Hygiene

- No Phase 13G.3.2 production backups were created.
- No Phase 13G.3.2 production copy lane was created.
- Phase-owned durable pytest logs and production run artifacts were retained as evidence.
- Final retained temp evidence size: approximately `892K`.

## Remaining Risk

Production no-change mode is implemented and tested after the logical-state fix, but the protected production invocation was not rerun because the phase allowed exactly one production invocation. A later phase should run a fresh preview and a new protected production no-change invocation using the corrected logical-state comparison.
