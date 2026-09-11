# Fundamentals V4 Phase 13D Backend and CLI Report

Outcome: **OUTCOME B — BACKEND READY WITH EXPLICIT SOURCE OR IDENTITY LIMITATIONS**

Phase 13D adds protected backend and CLI workflows for copy-only ticker onboarding and Fundamentals taxonomy updates. The implementation is deliberately not authorized for production writes, real Sharadar/API requests, Scheduler automation or UI wiring.

## Implemented Backend

The shared backend lives in `rawcandle/fundamentals/phase13d_backend.py`.

Ticker onboarding now supports:

- normalized 1-25 ticker input from commas, spaces, tabs or line breaks;
- malformed symbol rejection and deterministic duplicate removal;
- read-only preview with market, provider, canonical identity, alias and limited-taxonomy evidence;
- explicit statuses including `READY_WITH_LIMITATIONS`, `ALREADY_PRESENT`, `MARKET_DATA_NOT_FOUND`, `MARKET_AMBIGUOUS`, `API_FETCH_REQUIRED`, `IDENTITY_AMBIGUOUS` and `UNSUPPORTED_SECURITY_TYPE`;
- immutable preview fingerprint and source-state fingerprints;
- dry-run default;
- exact preview fingerprint validation before apply;
- stale preview rejection based on database, universe, taxonomy, package and Relative Valuation source state;
- production path, SQLite URI and database alias refusal;
- maintenance lock, online backups and multi-database restore on injected failure;
- idempotent second apply with genuine `NO_CHANGE`;
- Relative Valuation compatibility state reporting after operational-universe changes.

Taxonomy update now supports:

- read-only taxonomy preview;
- deterministic classification of presentation-only, peer-group and accounting-applicability changes;
- separation of presentation-only compatibility from economically material taxonomy changes;
- immutable preview fingerprint and stale preview rejection;
- dry-run default, explicit confirmation, maintenance lock, online backups and rollback;
- Relative Valuation compatibility states for presentation-only versus economic taxonomy updates.

Mock provider staging supports local JSON responses only and records `network_request_performed: false`.

## CLI Entrypoints

The protected CLIs are:

- `rawcandle/cli/run_phase13d_ticker_preview.py`
- `rawcandle/cli/run_phase13d_ticker_apply.py`
- `rawcandle/cli/run_phase13d_taxonomy_check.py`
- `rawcandle/cli/run_phase13d_taxonomy_apply.py`
- `rawcandle/cli/run_phase13d_compatibility_status.py`
- `rawcandle/cli/run_phase13d_provider_stage_mock.py`

All database-path based commands require explicit copy database paths. Production database paths are rejected by the backend before reads that would become apply-sensitive and before every apply operation.

## Rehearsal Evidence

Focused tests cover:

- ticker token normalization and malformed input;
- strictly read-only ticker preview;
- market ambiguity and unsupported security category classification;
- limited curated taxonomy absence not blocking eligible local-provider onboarding;
- dry-run apply behavior;
- confirmed ticker apply with operational-universe dependency rebuild on copies;
- second apply returning `NO_CHANGE` without physical inventory drift;
- injected apply failure restoring copy databases;
- taxonomy presentation-only versus economic-impact classification;
- taxonomy apply compatibility state;
- mock provider staging without network requests;
- production path refusal.

Regression tests were run for the Phase 13B foundation, Phase 13C production foundation, Relative Valuation persistence and production compatibility, Snapshot UI integration and production database isolation.

## Explicit Limitations

This is Outcome B, not Outcome A, because Phase 13D intentionally stops before UI integration and before true end-to-end production provider acquisition. The backend can stage local/mock provider evidence and can insert staged canonical identity rows into copy databases, but it does not perform a real Sharadar request or add a production ticker.

The apply path proves the protected preview/apply/rollback/idempotency contract and records dependency compatibility state. It does not yet run a full production-equivalent canonical statement, TTM, package, Relative Position and Relative Valuation recomputation for a newly acquired real ticker. Economically material taxonomy changes are detected and reported as Relative Valuation incompatible unless a future confirmed operation performs the coherent refresh.

## Phase 13E Recommendation

Phase 13E should wire these backend contracts into the Fundamentals UI only after a production-shaped copy rehearsal uses real staged provider rows and demonstrates a coherent full refresh plan for every economically affected layer. The UI should expose blocked compatibility states directly instead of presenting stale Relative Valuation results as coherent.
