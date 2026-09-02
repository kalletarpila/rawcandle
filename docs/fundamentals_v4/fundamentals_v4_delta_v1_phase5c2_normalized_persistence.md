# Fundamental Delta V1 Phase 5C.2 Normalized Persistence

## Locked Contract

Persistence version is `V4_FUNDAMENTAL_DELTA_REVISED_HISTORY_V2` and storage-layout fingerprint is `001d4d86ff3f279b2c44f497d536883a8f63bf281ee34c9086881e14635997c0`.

The economic model remains `CURRENTLY_REVISED_FUNDAMENTAL_DELTA_V1`, fingerprint `7cd5ff99c623f047940f296e4b2f7c504dd1f9b868b3079f6ef7d3a3f9b0d49d`. QoQ, 2Q and YoY semantics, eligibility, status/reason behavior, exact zero versus NULL, component reconciliation and all economic fingerprints are unchanged. The layout fingerprint is physical provenance and does not identify a new economic model.

## Physical Schema

V2 creates six tables and two indexes:

| Object | Contract |
|---|---|
| `fundamental_delta_package` | One bounded metadata/provenance row per Delta model and history mode |
| `fundamental_delta_status` | Small normalized status vocabulary |
| `fundamental_delta_reason` | Small normalized reason vocabulary |
| `fundamental_delta_component_type` | Seven component identities and locked maxima |
| `fundamental_delta_result` | One compact three-horizon total endpoint |
| `fundamental_delta_component` | Seven narrow component rows per endpoint, `WITHOUT ROWID` |
| `idx_fundamental_delta_current` | `(package_id,company_id,fiscal_sequence DESC)` |
| `idx_fundamental_delta_cross_section` | `(package_id,fiscal_year,fiscal_quarter,company_id)` |

The component primary key is `(endpoint_id,component_id)`. There is no component company-history index, Lifecycle/Valuation copy table, context cache, payload JSON, trigger, view, unrelated `ALTER`, table rebuild or `VACUUM`.

Package metadata stores persistence/layout identity, Delta and upstream model identities, Fundamental/Lifecycle/Valuation source and aggregate result fingerprints, the unchanged economic package fingerprint, the V2 physical content fingerprint, counts and bounded apply time. Endpoint/component rows use integer package, status, reason and component references rather than repeated text. Endpoint audit retains fiscal identity, availability date, current/prior Score result IDs, independent horizon outputs, reconciliation evidence and engine/physical row fingerprints. Components retain current/prior points and signed changes.

## Writer And Validation

`build_persistence_package` remains the locked economic audit boundary. It calculates the same temporary Lifecycle and Valuation contexts needed to prove full-package equivalence, but `apply_package` writes only Fundamental total and component history.

Full apply atomically replaces one complete model history. Company apply atomically replaces complete histories for selected companies, including deterministic removal. Identical rows and package metadata return `NO_CHANGE` before a write transaction. Changed package provenance is not incorrectly treated as a no-op. Other package fingerprints are retained.

`quick_check` verifies SQLite/FKs, V2 persistence/layout identity, absence of V1 tables, package counts and content fingerprint, physical row fingerprints, codebook coherence, exactly seven components, finite/NULL readiness, prior references and component/total reconciliation within `1e-9`.

Six rollback boundaries were rehearsed. The legacy stage names `after_lifecycle` and `after_valuation` are retained only as failure-injection aliases around the two V2 material write stages; they do not represent persisted context writes.

## Reader Contract

`FundamentalDeltaRepository` directly supports current company, company history, fiscal endpoint, current universe with optional availability freshness, fiscal-quarter cross-section and total plus seven components. Every call requires the locked Delta model fingerprint and deterministic ordering.

`LifecycleChangeRepository` and `ValuationChangeRepository` are derived-context readers. They query targeted authoritative `lifecycle_revised_result` or `valuation_revised_result` histories through existing `(model_fingerprint,history_mode,company_id,fiscal_sequence)` indexes and call the centralized Phase 5B context engines. They support current company, company history and explicit-company batch. They require the corresponding source model fingerprint, use package-level source provenance and do not write a cache or Delta-owned context row.

## Rehearsal Evidence

Final artifacts are under `temp/fundamentals_v4_delta_phase5c2/20260902T180000Z/`. The independent dry-run is under `20260902T160000Z`. Production-copy rehearsal used a SQLite online backup; all five real source databases remained byte-for-byte and schema-identical.

Economic reconciliation:

| Measure | Result |
|---|---:|
| Total rows | 50,585 |
| Component rows | 354,095 |
| Delta-owned Lifecycle rows | 0 |
| Delta-owned Valuation rows | 0 |
| Historical ready QoQ / 2Q / YoY | 27,490 / 25,210 / 20,717 |
| Current-fresh endpoints | 2,441 |
| Current-fresh ready QoQ / 2Q / YoY | 2,187 / 2,179 / 2,149 |
| Derived Lifecycle 2Q ready | 2,385 |
| Derived Valuation 2Q ready | 2,221 |
| Maximum reconciliation error | `3.907985046680551e-14` |

Economic package fingerprint remained `c94b25c4a11195f2fdb7c021231187ae126143421b01e407cdcfcd9249453bb3`. Aggregate result fingerprints remained:

- Fundamental: `6c811ee39d0fd6cc88873c6aec8b30743449e2ffda0348ed22b019bf8d338f2d`
- Lifecycle: `24cd7ead3ba0e5e945355e0a203d2cb4dd31eb94f5bceca2180ed2cc70b4a7c0`
- Valuation: `cfb056f0f27e98c90fa11d908eb7af0bce6f749b11ecb4a0f7ff4573f2ba31f1`

V2 physical content fingerprint is `f6beb12f7bf13f425b21a1031cf7cdc4cf41d63367c64878382c97f4b5cd639c`.

First apply inserted 50,585/354,095 rows in 11.80 seconds. Identical second apply wrote zero rows and changed neither size nor page count. Company 1 unchanged rebuild was a no-op; changed rebuild updated one endpoint; repeat was a no-op; removal deleted 20/140 rows; restore inserted 20/140 rows. All six injected failures preserved the prior content fingerprint.

An explicit deep authoritative replay rebuilt the complete economic package from the read-only Score/Lifecycle/Valuation histories and compared every V2 physical row. It completed in 61.71 seconds with no detail errors, SQLite `ok`, zero FK violations and matching economic/physical fingerprints.

CRMD QoQ/2Q/YoY remained `-2.4822450134938663 / -3.11564573300889 / -2.8940667320374303`. APD remained `-26.7023531089393 / 5.376062770577377 / -4.330330445282925`.

## Storage And Performance

The production-copy database grew from 322,220,032 to 390,258,688 bytes: 68,038,656 bytes, 5.55% above the 64,458,752-byte prototype target and about 88.69% below V1's 601,673,728-byte growth. The modest prototype variance is the compact endpoint's retained availability and audit evidence.

| V2 object | Bytes |
|---|---:|
| Component table | 49,897,472 |
| Total table | 13,148,160 |
| Current/history index | 1,622,016 |
| Cross-section index | 1,708,032 |
| Package and three codebooks | 16,384 |

Final freelist was zero and no `VACUUM` was used. Company exercises caused no final file growth.

Warm local median/P90 timings were 0.013/0.015 ms for persisted current Fundamental, 0.107/0.118 ms for company history, 5.724/6.278 ms for a CRMD Fundamental+Lifecycle+Valuation snapshot, 15.448/17.772 ms for 20-company derived contexts and 15.697/17.049 ms for a 2025 Q4 cross-section. Query plans use both endpoint indexes, the component primary key and targeted authoritative Lifecycle/Valuation company indexes; one-company reads do not scan full history.

## Production Boundary

No production migration, write, pipeline activation, provider update or push occurred. Phase 5D must add a separately reviewed exact-path production wrapper, retained backup, first apply, identical no-op, reader/context checks, pipeline hook after Valuation and before Relative Position, and rollback/deployment record.
