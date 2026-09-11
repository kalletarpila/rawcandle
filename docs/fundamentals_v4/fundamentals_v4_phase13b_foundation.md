# Fundamentals V4 Phase 13B Foundation

Selected outcome: **OUTCOME A - UNIVERSE AND TAXONOMY DEPENDENCY FOUNDATION READY FOR PRODUCTION MIGRATION**.

Phase 13B rehearsed the foundation required by Phase 13A and Phase 13A.1 before Add Tickers or Fundamentals Taxonomy Update can become safe UI operations. The rehearsal used production-shaped SQLite online backup copies only. Production data, active result pointers, Scheduler state, ticker aliases and taxonomy content were not modified.

## Candidate Contract

The candidate foundation is additive:

- `fundamentals_operational_universe_version`
- `fundamentals_operational_universe_active_version`
- `fundamentals_operational_universe_member`
- `fundamentals_operational_universe_member_alias`
- `fundamentals_result_dependency`
- `relative_valuation_snapshot_dependency`

Existing readers remain compatible because no existing table, view, active pointer or runtime reader contract is changed. New dependency tables are consulted only by Phase 13B candidate checks.

## Universe Backfill

The authoritative candidate universe is company-level. `security_id` is populated only when exactly one active security exists for the canonical company.

- Universe members: `2458`
- Canonical companies: `2458`
- Active securities represented: `2453`
- Companies with no active security retained historically: `16`
- Companies with multiple active securities requiring later security selection: `11`
- Universe economic fingerprint: `d21fff93d3f01a4056c0f6ed765f2e5f6169aafdb5f1e708b026d6c5ec7d4bdb`
- Universe version id: `7f50deaa1eb83a536ae7152a759b185a`

This resolves the Phase 13A count discrepancy: the operational Fundamentals population is the canonical company population, while active securities differ because some companies have no active security and some have two active share classes.

## Dependency Tracking

The rehearsal attached dependency metadata for:

- Relative Valuation snapshots
- Relative Position snapshots
- Operating Income V2 package manifests

Relative Valuation compatibility checks preserve the Phase 11E non-future snapshot selection rule and then classify the selected snapshot as:

- `COMPATIBLE`
- `PRESENTATION_ONLY_DRIFT`
- `ECONOMIC_TAXONOMY_MISMATCH`
- `OPERATIONAL_UNIVERSE_MISMATCH`
- `DEPENDENCY_UNKNOWN`
- `SNAPSHOT_NOT_AVAILABLE`

Phase 13B does not recalculate economics. It records and checks the operational universe fingerprint and taxonomy economic fingerprint needed to decide whether a result can be reused coherently.

## Rehearsal Evidence

Primary artifact directory:

`temp/fundamentals_v4_phase13b_foundation/20260911T_PHASE13B_RUN1`

Key artifacts:

- `PHASE13B_FOUNDATION_REHEARSAL_REPORT.md`
- `operational_universe_backfill.csv`
- `company_security_reconciliation.csv`
- `universe_dependency_reconciliation.csv`
- `taxonomy_dependency_reconciliation.csv`
- `relative_valuation_dependency_reconciliation.csv`
- `migration_first_apply.json`
- `migration_second_apply.json`
- `failure_injection_results.json`
- `production_preflight_postflight.json`
- `recommended_phase13c_scope.md`

The rehearsal produced result fingerprint:

`719e63b9638051f1e4a430ea986eb2f10ccac64a1d7697e1f829f67783674c77`

After tightening dependency idempotency, the same production-shaped RUN1 copies were replayed once more and wrote `corrected_idempotency_replay.json`. That replay reported schema, universe and dependency outcomes as `NO_CHANGE` and verified unchanged physical fingerprints.

Failure injection covered schema, universe and dependency boundaries. Each injected failure restored the rehearsal copy from source production backups and passed `PRAGMA quick_check`.

## Production Guard

Candidate migration code rejects exact production paths and symlinks. Phase 13B is not a production migration. Phase 13C must explicitly opt into exact production paths only after independent backups, maintenance lock acquisition and postflight reconciliation.
