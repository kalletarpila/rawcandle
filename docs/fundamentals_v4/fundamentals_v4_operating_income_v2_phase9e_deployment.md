# Operating-Income V2 Phase 9E Production Deployment

## Outcome

Operating-Income V2 was persisted on 2026-09-06 at `20260906T193735Z` and activated atomically at `20260906T194347Z`. The only modified economic database was:

`/home/kalle/projects/rawcandle/data/fundamentals_analysis.db`

Canonical, provider, market and taxonomy databases were opened with WAL-aware SQLite `mode=ro` reads and remained content-identical, allowing only byte-identical SHM read-lock metadata changes. Canonical and TTM data were not rebuilt. No provider update ran, and existing files under `fundamental_reports/` remained byte-identical.

Code commits before activation:

- `f8cdb3b` - production activation, active readers, V2 Snapshot dispatch, pipeline and safety command
- `8ec9f9d` - V1 preservation comparison excludes additive V2-only columns
- `15372bd` - maintenance lock moved to ignored `temp/` state

The deployment-record commit is the commit containing this document.

## Package Identity

| Layer | Fingerprint |
|---|---|
| Family | `634824f179652da81ea6f38962d9a7c87df37c0627fed089a918ce9efa83d8e9` |
| Persistence | `cf4ce8134c362399ea94667e4659e27a32b1e8b9de199eaaba32c91b450a51bc` |
| Economic result | `341b440711cdb91723310346caa39d29e5415fce7ea2c5b4a8786e5b90befba1` |
| Physical content | `9cb8d830f7124e216981a534143036d6bbf3c592644c42d927e4f733c7afb570` |
| Score | `271585e4136f6733c047e89dac7646f2ff91f8c84b10f88c56356ad495970360` |
| Lifecycle | `0502822c20501c1487d09a20a378e86c0908a0953dfcb13b384428822fc4e175` |
| Valuation | `9675c2d947a86d2115f366424eab7454ec013cc100c7548af004c19c691c9aeb` |
| Delta | `c65062c1ac66f1e98ab239404dba96c43060708a35a84bcfd2ed01c30d5e2f11` |
| Relative Position | `993a3cfbbfd7d724852cf78466a91edf0a1adca8cd08c35e8bcc2891a5cbe30f` |
| Diagnostic Flags | `d5434e139b68ee8af44dffce34cb9225538f0badb61d5d1074fb976a4de3185d` |
| Company Snapshot | `7bfa88aa64f3897ea610894a1b7a3613abfc7881d9b9ea8e26912ef0426e7ee8` |

The activation row and package manifest identify this exact bundle. Default reads fail closed if either identity differs. Explicit V1 and V2 reads remain available through `ParallelModelRepository`.

## Safety And Backups

Preflight found no database holder, conflicting writer, Scheduler process or provider/Fundamentals update. Free space was approximately 509 GB against a conservative 2,936,212,480-byte requirement. No WAL or SHM file was deleted, moved, truncated or checkpointed.

The retained pre-write online backup is:

`backups/fundamentals_analysis.phase9e.20260906T193735Z.db`

- Size: 476,631,040 bytes
- SHA-256: `32d49e89a40ff35ebc89304f326b9e564cf6bab6e06d3ec5f2032c1d119a3597`
- `quick_check=ok`; no foreign-key violations

A second recovery-boundary online backup was retained at:

`backups/fundamentals_analysis.phase9e.20260906T194347Z.db`

- Size: 952,266,752 bytes
- SHA-256: `864d98fffa769a4532a067e78ed9c09e493f37e91b80a308c809333d11c7d58b`
- `quick_check=ok`; no foreign-key violations

The final analysis database size is 952,270,848 bytes. The approximately 475.6 MB increase agrees with Phase 9D.

## Apply And Reconciliation

The first production transaction persisted all seven V2 layers. The post-write V1 gate then stopped before activation because its initial `SELECT *` comparison included newly added nullable V2 columns on V1 Lifecycle and Valuation rows. Layer-specific comparison against the pre-write backup proved that every locked V1 economic field was unchanged. The gate was corrected and committed before activation.

The recovery execution independently recalculated the complete package. Its first check and mandatory second check were both true `NO_CHANGE` operations. Deep reconciliation returned `ok=true`, no differences, `quick_check=ok`, no foreign-key violations and these exact counts:

| Layer | Rows |
|---|---:|
| Score | 50,585 |
| Score components | 354,095 |
| Lifecycle | 50,585 |
| Valuation | 50,585 |
| Delta | 50,585 |
| Delta components | 354,095 |
| Diagnostic endpoints | 50,585 |
| Diagnostic evaluations | 354,095 |
| Relative Position results | 13,737 |
| Relative Position coverage | 19,596 |

Total V2 persistence is 1,348,543 rows. AMZN, GOOG, NVDA, CRMD and APD matched the locked reference values within 0.02 points. The V1 content fingerprint across all six stored V1 result families remained `17ac56e282d5952b9588c8cb13d4248c6858e46d72e759d8fa320482f40e01e1`.

## Runtime Activation

`fundamentals_active_model_family` switches the complete package as one unit. `ActiveModelRepository` validates the activation row and complete V2 manifest before reading. The active pipeline order is Score, Lifecycle, Valuation, Delta, Diagnostic Flags and Relative Position; Snapshot consumes the completed package and is never generated automatically. A provider-disabled pipeline smoke recalculated the bundle and returned `NO_CHANGE`.

Manual Snapshot generation now dispatches to V2 after activation. Temporary reports for AMZN, NVDA, CRMD, APD, AAT, ABOS and AAON were generated twice; every second publication returned `NO_CHANGE`. The Scheduler service preserved batch partial success, secure byte-identical download and traversal rejection. The `/fundamentals` ASGI route returned HTTP 200. No running UI process existed, so no restart was required.

The full pre-deployment Fundamentals V4, Snapshot and Scheduler UI test scope passed: `756 passed`. Focused post-correction safety tests also passed with no skips.

## V1 And Rollback

V1 remains stored and auditable, and is frozen at this deployment boundary. Future source refreshes rebuild the coherent V2 package; ongoing dual calculation was not introduced.

For an activation-only rollback, hold the maintenance lock and atomically delete singleton row 1 from `fundamentals_active_model_family`, then verify V1 readers, Snapshot and UI. Do not delete V2 rows. If database integrity itself is damaged, stop writers, retain the failed database and use `sqlite3.Connection.backup()` to restore the pre-write backup above. Verify its SHA-256, `quick_check`, foreign keys, V1 counts and V1 report generation before release.

## Evidence

The complete machine-readable record is under:

`temp/fundamentals_v4_operating_income_v2_phase9e/20260906T_PHASE9E_PRODUCTION_RECOVERY/`

The initial dry-run is under `20260906T_PHASE9E_DRYRUN/`; the stopped pre-activation execution is under `20260906T_PHASE9E_PRODUCTION/`.

Known residual risks are limited to current-revised rather than PIT history, the intentionally current taxonomy classification, full-package refresh runtime, and the absence of ongoing V1 recalculation after this boundary.
