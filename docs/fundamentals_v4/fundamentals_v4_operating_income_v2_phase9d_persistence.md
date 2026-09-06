# Operating-Income V2 Phase 9D Persistence

Status: `PARALLEL_V2_PERSISTENCE_REHEARSED_NOT_PRODUCTION_ACTIVE`

Phase 9D adds parallel persistence for the complete Operating-Income V2 family. It does not migrate production, activate V2 readers, replace reports, update provider data, or remove V1.

## Architecture

The implementation reuses the existing fingerprinted production tables:

- `score_result` and `score_component`
- `lifecycle_revised_result`
- `valuation_revised_result`
- normalized `fundamental_delta_*`
- normalized `diagnostic_flag_*`
- snapshot-based `relative_position_*`

The only additive objects are:

- `operating_income_v2_package_manifest`, which binds all seven model identities to one complete economic and physical result
- `operating_income_v2_diagnostic_evidence_field`, which maps V2 numeric evidence names to the existing 16 numeric slots
- two Operating Margin columns on Lifecycle history
- three Operating Income columns on Valuation history

No V2-specific duplicate result tables, PIT tables, activation registry, copied Lifecycle/Valuation Delta context, combined diagnostic score, or diagnostic JSON were introduced.

`apply_package()` writes Score, Lifecycle, Valuation, Delta, Diagnostic Flags, Relative Position, and the family manifest in one `BEGIN IMMEDIATE` transaction. The manifest is written last. A matching economic fingerprint is a true no-op, but only after a streaming physical fingerprint confirms every V2 parent row, child row, codebook mapping, snapshot row, and active V2 pointer. V1 rows and its active Relative Position pointer are addressed by their own fingerprints and remain untouched.

An individual company source change is treated as a company-scoped trigger for a complete coherent package rebuild. This deliberately recalculates the company's complete history and the complete cross-sectional Relative Position snapshot. It avoids a partially updated model family; it does not promise fewer physical writes than a full rebuild.

## Resolved Preconditions

The Phase 9C diagnostic count `335,272` omitted the seven status records at each endpoint that had no preceding fiscal quarter. There are `2,689` such endpoints: `(50,585 - 2,689) * 7 = 335,272`. The persistence contract requires one row for every endpoint and every flag, including not-ready and not-applicable results. The corrected identity is therefore `50,585 * 7 = 354,095` evaluations.

The Phase 9C Relative Position difference was three Fundamental Score rows for LFCR in UNIVERSE, SECTOR, and INDUSTRY. Phase 9C selected its latest Score endpoint by TTM availability date and skipped a newer `SCORE_NOT_READY` quarter. Production semantics select the endpoint by the canonical quarter `source_availability_date`. With that correction LFCR is ineligible and both V1 and V2 contain `13,737` result rows.

## WAL Resolution

`data/analysis.db-wal` belongs to the taxonomy database. It contains committed state newer than the main database. `immutable=1` ignored that state and was therefore invalid. Snapshot and rehearsal readers now use SQLite `mode=ro`, which resolves the WAL safely. Rehearsal copies use `sqlite3.Connection.backup()`.

A read-only WAL-aware connection may acquire locks in the `-shm` file and update only its mtime. Integrity comparison permits this only when SHM path, size, and SHA-256 remain identical. Any main database, WAL, SHM content, schema, row count, page, freelist, quick-check, or foreign-key difference fails closed.

## Rehearsal Result

The production-shaped rehearsal persisted:

| Layer | V2 rows |
|---|---:|
| Score totals | 50,585 |
| Score components | 354,095 |
| Lifecycle | 50,585 |
| Valuation | 50,585 |
| Delta totals | 50,585 |
| Delta components | 354,095 |
| Diagnostic endpoints | 50,585 |
| Diagnostic evaluations | 354,095 |
| Relative Position results | 13,737 |
| Relative Position coverage | 19,596 |

The analysis copy grew from 476,635,136 bytes to 952,971,264 bytes, an increase of 476,336,128 bytes. The second identical apply made zero logical changes and no database growth. No added secondary index or JSON result table was required. The growth is accepted for parallel V1/V2 auditability; production free-space preflight must allow the database plus backup and temporary WAL headroom.

Reference results matched the Phase 9C targets without pre-comparison rounding: AMZN `56.078938 / 18.428950`, GOOG `77.526912 / 27.820337`, NVDA `96.938928 / 27.024079`, CRMD `91.082566 / 100`, and APD `26.958851 / 0` for Score / Valuation.

Phase 9E remains separately authorized. The deployment procedure is in `fundamentals_v4_operating_income_v2_phase9e_runbook.md`.
