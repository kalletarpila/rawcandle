# Valuation V1 Phase 3C.2 Additive Migration

## Outcome

Phase 3C.2 retires the full `v4_field_provenance` rebuild and replaces it with the additive design proven in Phase 3C.1. Valuation V1 model behavior, source semantics, statuses and fingerprints are unchanged. Production databases were not modified and no pipeline was activated.

Schema version is `v4_3c2_additive_provenance`. Legacy provenance remains in its original constrained `v4_field_provenance` table. `v4_common_earnings_provenance` has the same logical columns, uniqueness and quarter foreign key, but database checks permit only `canonical_field='net_income_common'` and `source_native_field='netinccmn'`. The public `read_provenance`, `write_provenance`, and `write_provenance_many` functions validate fields, route physical storage, return one logical shape and deterministic ordering, and reject unknown or conflicting values.

Fresh schema and upgraded production-shaped schema have matching columns, constraints, foreign keys and indexes. The migration is one canonical-database transaction. Schema version advances only after schema, common-earnings backfill, provenance and TTM rebuild succeed. Injected failures after schema, backfill and TTM all roll back to the original valid schema and data. An identical rerun changes zero canonical, provenance or TTM rows and does not alter schema metadata or file size.

## Storage evidence

Rehearsal artifacts are under `temp/fundamentals_v4_valuation_phase3c2/20260901T153524Z`.

| Stage | Bytes | Pages | Freelist pages | Seconds |
|---|---:|---:|---:|---:|
| fresh copy | 269,901,824 | 65,894 | 0 | 0.000 |
| schema migration | 269,901,824 | 65,898 | 0 | 0.044 |
| canonical common earnings | 287,531,008 | 70,225 | 0 | 1.706 |
| TTM common earnings | 288,509,952 | 70,450 | 0 | 0.248 |
| final close/checkpoint | 288,563,200 | 70,450 | 0 | 0.000 |

Canonical growth was 18,661,376 bytes instead of the retired migration's 163,508,224 bytes. The approximately 153 MB freelist did not recur. The analysis copy grew from 253,874,176 to 302,678,016 bytes, as in Phase 3C. No `VACUUM` was used or is required. Production `VACUUM` is not recommended because it adds an unrelated full-database rewrite and operational failure surface.

The storage regression fixture preserves the legacy table SQL, root page and content hash, requires zero freelist, bounds representative growth below 8 MiB, and permits less than 64 KiB repeated-run growth. These deliberately generous limits detect a table-sized copy without depending on one machine's exact page layout.

## Logical evidence

- canonical rows backfilled: 50,171; repeated run: 0
- common provenance rows added: 50,171; repeated run: 0
- TTM rows changed: 42,596; repeated run: 0
- first valuation apply: 50,585 inserts
- second valuation apply: 0 inserts, updates, deletes or replacements; 50,585 unchanged
- historical statuses: 39,117 FULL, 2,903 NOT_APPLICABLE, 8,565 NOT_READY
- exact-zero FULL rows: 11,595; every row had finite EBIT, FCF and common earnings at or below zero
- source fingerprint: `e552cf0b01a1e649d6269a968c4ea7e96b903acccce9c8b73d21d7c6cd230e47`
- result fingerprint: `46bdde9bd6711180b9bc1b75462c42c39e2ff5498ee93ad0c711cbbf88e69a18`

Common provenance, canonical common earnings and TTM common earnings hashes match the original Phase 3C rehearsal. Existing financials, `net_income`, existing TTM values, Score and Lifecycle inputs were unchanged.

At 2026-09-01 with 180-day freshness, current universe remained 2,431 companies: 2,246 FULL, 139 NOT_APPLICABLE and 46 NOT_READY. Exact zero remained 631, exact 100 remained 6, and median remained 24.6288. The deterministic zero sample remained 24 rows.

Production Score remained 50,585 results and 354,095 components with fingerprint `47add84845743b33bc9e43d35296871890c1e850d0c9ca23b10e3b10c861f7bc`. Lifecycle remained 50,585 rows with model fingerprint `db72e072fc2f0d9e3ceb13db1ee4cc92045383a5f44bfb65d21858b80190832f` and result fingerprint `43fee8da28ea454236263c93a09f2a3fe089473509fc4d926b7cc3aae811729c`.

## Production gate

Production provider, canonical, analysis and market paths, sizes, mtimes, schemas and quick checks were identical before and after rehearsal. Phase 3D may proceed through the corrected runbook after explicit authorization. Remaining operational risks are independent canonical/analysis transactions and the normal need for verified online backups and sufficient temporary disk space; the retired provenance rebuild and production `VACUUM` are not part of that path.
