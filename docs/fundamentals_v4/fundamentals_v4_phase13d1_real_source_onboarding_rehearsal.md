# Fundamentals V4 Phase 13D.1 Real-Source Onboarding Rehearsal

Outcome: **OUTCOME C — REAL-SOURCE REBUILD, DEPENDENCY OR ROLLBACK CONTRACT NOT READY**

Phase 13D.1 rehearsed real-source ticker onboarding on production-shaped copies only. Production databases, Scheduler configuration and existing `fundamental_reports` were not intentionally modified.

## Local-Provider Lane

The local-provider candidate set came from the Phase 13A candidates:

`ALUR AREB AVB BSLK CERO LBRDA LEG LYRA MAPS MSPR NOTE PTIX RMAX SSKN TALK VSTD`

The deterministic selection rule was maximum local Sharadar provider rows, then maximum OHLC rows, then ticker. The selected local-provider ticker was `AREB`.

The selection also confirmed an important readiness limit: none of the 16 candidates had existing active Fundamentals taxonomy membership. The local lane therefore proves local source availability and deterministic selection, but not complete taxonomy-ready production activation.

## SNDK Identity And Source

SNDK was processed as the required acquisition-path case.

Observed identity:

- ticker: `SNDK`
- company: `SANDISK CORP`
- Sharadar permaticker: `643888`
- SEC CIK: `0002023554`
- related ticker: `SNDKV`
- market: `usa`
- OHLC range: `2025-02-13` through `2026-09-11`

Ticker reuse/predecessor risk is real: Sharadar metadata also contains delisted `SNDK1`, `SANDISK CORP`, permaticker `197210`, with historical dates through 2016. The rehearsal therefore rejects ticker-only identity and anchors the new SNDK lane to permaticker `643888` and CIK `0002023554`.

The managed Phase 12C archive was verified:

- path: `data/source_archives/sharadar/fundamentals/phase12c_20260910/sharadar_fundamentals_10y.zip`
- SHA-256: `dc9d3f729830c1881873d10dec2dc2a3e7035d2a247e1737983bdb64cd0e0d36`
- API requests performed: `0`

The archive contained 61 SNDK rows, including 13 ARQ rows. These were staged only into the provider copy.

## SNDK Taxonomy

SNDK already had an active taxonomy entity and active membership in production taxonomy:

- `MEMORY_HBM_DRAM_NAND_SSD`
- `STORAGE`

The rehearsal did not create a duplicate taxonomy company or membership. On the taxonomy copy it connected the existing SNDK taxonomy entity to the newly resolved copy-only canonical identity by adding schema-valid `ec_entity_alias` evidence:

- `LEGACY_CODE:SHARADAR_PERMATICKER:643888`
- `LEGACY_CODE:SEC_CIK:0002023554`
- `LEGACY_CODE:CANONICAL_COMPANY_ID:<copy id>`
- `LEGACY_CODE:CANONICAL_SECURITY_ID:<copy id>`
- `TICKER:SNDKV`

No duplicate membership was created. The taxonomy economic fingerprint remained unchanged because the valid economic membership already existed.

## Copy Rebuild Result

On isolated copies, the SNDK path produced:

- provider observations: 61
- provider ARQ observations: 13
- canonical quarters: 9
- TTM endpoints: 9
- operational universe: changed on copy
- Relative Valuation before refresh: `OPERATIONAL_UNIVERSE_MISMATCH`

This proves the archive-to-provider-copy, canonical history, TTM and Phase 13B dependency transition portions of the path. It does not prove full production readiness because the separate explicit full-universe Relative Valuation refresh, Snapshot generation after restored compatibility, complete failure-injection matrix and second deterministic full run remain incomplete.

## Readiness Matrix

For SNDK:

- `identity_status`: `RESOLVED_WITH_PREDECESSOR_RISK`
- `fundamentals_status`: `READY`
- `operational_universe_status`: `ADDED_ON_COPY`
- `taxonomy_status`: `CONNECTED_EXISTING_MEMBERSHIP`
- `downstream_status`: `LIMITED_COPY_REBUILD`
- `relative_valuation_status`: `OPERATIONAL_UNIVERSE_MISMATCH`

## Artifacts

Artifact directory:

`temp/fundamentals_v4_phase13d1_real_source/20260912T_PHASE13D1_REAL_SOURCE`

Key files:

- `production_preflight.json`
- `candidate_selection.json`
- `sndk_identity_evidence.json`
- `sndk_source_acquisition.json`
- `staged_provider_validation.json`
- `onboarding_previews.json`
- `onboarding_apply_results.json`
- `readiness_matrix.csv`
- `dependency_transitions.json`
- `relative_position_reconciliation.json`
- `relative_valuation_compatibility.json`
- `taxonomy_rehearsal.json`
- `snapshot_reconciliation.json`
- `failure_injection_results.json`
- `no_change_results.json`
- `production_postflight.json`
- `artifact_manifest.json`
- `commands_run.txt`

## Production Safety Note

During early exploratory read-only inspection, SQLite created `data/analysis.db-wal` and `data/analysis.db-shm` sidecar files for the taxonomy database. This was recorded as a read-only sidecar effect, not an economic database change. The rehearsal writes themselves were performed only on copies under `temp/fundamentals_v4_phase13d1_real_source/`.
