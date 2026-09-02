# Fundamental Delta V1 Phase 5C Persistence

## Status And Boundary

Phase 5C implements `V4_FUNDAMENTAL_DELTA_REVISED_HISTORY_V1` as an additive, non-production persistence foundation. The name follows the existing revised-history Lifecycle and Valuation conventions. Delta remains `CURRENTLY_REVISED_FUNDAMENTAL_HISTORY_DELTA`, not PIT history.

No real production schema, data, pipeline or provider operation is changed. The protected CLI blocks production paths, aliases, symlinks, source databases and the persistent backup directory. It has no production-confirmation option.

## Physical Contract

The selected compact-hybrid schema adds only these objects to the analysis database:

| Object | Purpose |
|---|---|
| `fundamental_delta_revised_meta` | One metadata row per Delta model fingerprint |
| `fundamental_delta_revised_result` | One wide QoQ/2Q/YoY total row per company endpoint |
| `fundamental_delta_revised_component` | One wide QoQ/2Q/YoY row per endpoint and component |
| `lifecycle_change_revised_context` | One categorical wide context row per endpoint |
| `valuation_change_revised_diagnostic` | One wide diagnostic row with three deterministic explanatory payloads |
| `idx_fundamental_delta_current` | Current and history company reader |
| `idx_fundamental_delta_cross_section` | Fiscal-quarter cross-section reader |
| `idx_fundamental_delta_component_reader` | Seven-component endpoint reader |
| `idx_lifecycle_change_current` | Lifecycle current/history reader |
| `idx_valuation_change_current` | Valuation current/history reader |

The component, Lifecycle and Valuation rows reference the new Fundamental total endpoint with `ON DELETE CASCADE`. Existing Score, Lifecycle, Valuation, Relative Position, canonical and provenance tables are not altered. Migration uses only `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`; there is no table rebuild, trigger, view, `ALTER`, `DROP`, rename or `VACUUM`.

Unavailable numeric changes are SQL NULL. Exact zero remains numeric zero. Binary64 engine values are stored without rounding. The Valuation JSON payload is canonical JSON containing already persisted endpoint values; it does not copy canonical Revenue, EBIT, FCF, shares or balance-sheet inputs.

## Package And Writer

`build_persistence_package` calculates the full revised history from explicit read-only sources. It produces separate Fundamental, Lifecycle and Valuation source/result fingerprints plus a persistence package fingerprint covering all row fingerprints.

`apply_package` requires a migrated destination and a clean transaction boundary. Full apply atomically replaces only the selected Delta model and mode. Company apply replaces every endpoint for each selected company and may remove a selected company whose complete new package contains no history. Quarter-only replacement is absent.

An identical package returns `NO_CHANGE` before opening a write transaction. Changed logical identities are reported separately as inserted, deleted, updated and unchanged even though changed scopes use atomic delete/insert physically. Other model fingerprints are retained. Failure at delete, total, component, Lifecycle, Valuation or metadata stages rolls back the complete transaction.

## Readers And Quick Check

The explicit-fingerprint repositories are:

- `FundamentalDeltaRepository`: current company, company history, fiscal endpoint, current universe, fiscal cross-section and total plus seven components.
- `LifecycleChangeRepository`: current company and history with categorical horizon context.
- `ValuationChangeRepository`: current company and history with decoded filing-date diagnostic payloads.

Wrong fingerprints are rejected. Readers preserve deterministic company/fiscal ordering and expose `REVISED_HISTORY`; they do not calculate Lifecycle ordinals, missing endpoints or Relative Position history.

Reusable `quick_check` verifies SQLite and foreign keys, metadata counts and fingerprints, row fingerprints, endpoint relationships, seven components and maxima, finite/NULL readiness contracts, fiscal lags, total arithmetic, component reconciliation within `1e-9`, Lifecycle vocabularies and Valuation component reconciliation.

## Rehearsal Results

Artifacts and the writable SQLite online backup are under:

```text
temp/fundamentals_v4_delta_phase5c/20260902T130000Z/
```

`phase5c_report.json` contains the complete apply, rollback and storage rehearsal. `phase5c_dry_run_report.json` records before/after resolved paths, sizes, mtimes, SHA-256 values, schema hashes, page/freelist counts, key row counts and SQLite checks for all five read-only production sources; every before/after object is identical.

Two independent source builds produced package fingerprint `c94b25c4a11195f2fdb7c021231187ae126143421b01e407cdcfcd9249453bb3` and exact Phase 5B result fingerprints:

- Fundamental: `6c811ee39d0fd6cc88873c6aec8b30743449e2ffda0348ed22b019bf8d338f2d`
- Lifecycle: `24cd7ead3ba0e5e945355e0a203d2cb4dd31eb94f5bceca2180ed2cc70b4a7c0`
- Valuation: `cfb056f0f27e98c90fa11d908eb7af0bce6f749b11ecb4a0f7ff4573f2ba31f1`

Persisted rows are 50,585 total, 354,095 component, 50,585 Lifecycle and 50,585 Valuation. First apply inserted all rows in 17.12 seconds. The identical second apply made zero logical writes and changed neither database size nor page count.

Readiness exactly reconciles Phase 5B. Historical Fundamental QoQ/2Q/YoY ready counts are 27,490 / 25,210 / 20,717 over 50,585 endpoints. The current-fresh set has 2,441 endpoints and 2,187 / 2,179 / 2,149 ready totals. Lifecycle 2Q is ready for 2,385 independently fresh Lifecycle endpoints, and Valuation diagnostic 2Q is ready for 2,221 independently fresh Valuation endpoints. Maximum strict-ready total/component reconciliation error is `3.907985046680551e-14`, below `1e-9`.

Company 1 has 20 endpoints. Its unchanged rebuild was a no-op; changed-source simulation updated 20 totals and 140 components; its second apply was a no-op; removal deleted the complete 20/140/20/20 history; restore inserted it completely. All six injected failures preserved the prior content fingerprint.

CRMD reads `-2.4822450134938663 / -3.11564573300889 / -2.8940667320374303` for QoQ/2Q/YoY. APD reads `-26.7023531089393 / 5.376062770577377 / -4.330330445282925`. Both return seven component rows.

## Storage Audit

The production analysis online backup started at 322,220,032 bytes and 78,667 pages. Additive migration alone added 90,112 bytes and 22 pages with zero freelist. First full apply reached 923,983,872 bytes and 225,582 pages, a 601,673,728-byte increase from the migrated copy. Final company exercises reached 924,008,448 bytes and 225,588 pages, with zero freelist and no WAL/SHM residue.

New object storage after first apply:

| Object group | Bytes |
|---|---:|
| Fundamental total table | 50,819,072 |
| Fundamental component table | 157,286,400 |
| Lifecycle table | 38,522,880 |
| Valuation diagnostic table | 207,704,064 |
| Five indexes | 68,681,728 |
| Constraint-owned automatic indexes | 78,729,216 |
| Metadata | 4,096 |

The five named indexes are 68,681,728 bytes; SQLite's uniqueness and primary-key constraints require another 78,729,216 bytes of automatic indexes. Together, all Delta-owned indexes are 147,410,944 bytes. This materially exceeds Phase 5B's Fundamental-only 82 MB table plus 21 MB index estimate. The estimate did not model the separate Lifecycle/Valuation contracts, and actual audit columns repeat status, reason, fingerprint and endpoint strings. Valuation's three explanatory JSON payloads are the largest object. Growth remains bounded below 1 GB, full apply is fast, no-op does not grow the file and company rebuild leaves zero freelist, so Phase 5C does not prematurely redesign or compress the audit contract. Phase 5D must accept this approximately 602 MB growth explicitly or authorize a separate normalization study before deployment.

## Future Refresh Order

The existing active order is Score, Lifecycle, Valuation, Relative Position. Phase 5D should insert Delta after Valuation and before Relative Position:

```text
provider/canonical -> TTM -> Score -> Lifecycle -> Valuation -> Delta -> Relative Position
```

Delta and Relative Position do not depend on each other. Delta uses its own transaction. An unchanged source makes zero result/context writes. A trustworthy changed-company set may use complete-company rebuild; otherwise full-history rebuild is required. Delta failure preserves previous Delta history and cannot roll back committed upstream layers. A Delta-only run must not call a provider.
