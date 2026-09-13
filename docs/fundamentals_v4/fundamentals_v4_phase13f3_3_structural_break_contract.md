# Phase 13F.3.3 Structural-Break Contract

Phase 13F.3.3 implemented a copy-only candidate economic structural-break contract that separates legal/security identity continuity from fundamental comparability.

Final rehearsal artifact:

`temp/fundamentals_v4_phase13f3_3_structural_break_contract/20260913T_PHASE13F3_3_FINAL3`

Outcome:

`OUTCOME A — VERSIONED STRUCTURAL-BREAK CONTRACT IMPLEMENTED AND COPY-ONLY REHEARSAL VERIFIED`

Production writes:

None. Production provider, canonical and analysis databases remained immutable and passed `PRAGMA quick_check`.

## Contract

The additive candidate contract is owned by `rawcandle.fundamentals.structural_break` and creates these copy-only tables:

- `fundamentals_economic_structural_event`
- `fundamentals_quarter_economic_regime`
- `fundamentals_ttm_economic_regime`

The contract version is:

`ECONOMIC_STRUCTURAL_BREAK_CONTRACT_V1`

When the candidate tables are absent, RP/RV/Snapshot readers retain legacy behavior. When present, the readers include the structural fingerprint in source identity and reject current report endpoints that would silently cross a material economic event.

## Decisions

| ticker | decision | current 2026-09-12 status |
| --- | --- | --- |
| VMRK | `MAJOR_BUSINESS_COMBINATION` | current report blocked until post-event clean TTM exists |
| IA | `NO_ECONOMIC_BREAK` | eligible |
| VAI | `BUSINESS_COMPARABILITY_REVIEW_REQUIRED` | current report blocked pending comparability review or clean post-event evidence |
| NXH | `TICKER_REUSE_SEPARATION` | current issuer lineage eligible; bankrupt BBBYQ remains separate |
| NMAD | `REVERSE_MERGER_MAJOR_BUSINESS_CHANGE` | current report blocked until post-event clean TTM exists |

Because canonical fiscal period start dates are not available, the contract does not infer a clean post-event quarter from period end alone. Pre-event endpoints remain preserved for historical report dates. Current post-event reports require `POST_EVENT_COHERENT` TTM.

## FINAL3 Evidence

- Pre-refresh Relative Valuation compatibility: `OPERATIONAL_UNIVERSE_MISMATCH`
- Post-refresh Relative Valuation compatibility: `COMPATIBLE`
- RV excluded input counts: `{"CURRENT_REPORT_REQUIRES_POST_EVENT_CLEAN_TTM": 3, "NOT_ACTIVE_OPERATIONAL_UNIVERSE_MEMBER": 16}`
- RV company count after structural gate: `2435`
- Deterministic replay: `true`
- Production immutable: `true`
- Snapshot smoke: `AREB`, `IA`, `NMAD`, `NVDA`, `NXH`, `VAI`, `VMRK` all created
- Rehearsal copy cleanup: no `.db`, `.sqlite`, WAL, SHM or journal artifacts retained under FINAL3

Structural event counts:

| ticker | pre-event coherent TTM | post-event clean TTM |
| --- | ---: | ---: |
| VMRK | 38 | 0 |
| IA | 0 | 0 |
| VAI | 31 | 0 |
| NXH | 0 | 0 |
| NMAD | 36 | 0 |

## Notes

The candidate dependency fingerprint is recorded as `4ba542c7e28c2d92ba65863f2932e2683a60b053cb4b2debe344b051a84441ad`. It is an audit/dependency identity for the copy-only structural contract, not a production activation.

Phase 13F.3.3 does not authorize production deployment, raw provider rewrites, market/taxonomy changes, formula changes or Scheduler/UI activation.

