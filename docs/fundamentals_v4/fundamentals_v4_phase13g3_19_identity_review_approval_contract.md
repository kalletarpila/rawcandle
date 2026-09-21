# Phase 13G.3.19 - Identity Review Approval Contract

## Scope and safety

This phase adds a durable approval contract to the ticker identity resolver. It does not approve an identity interpretation and does not write provider, canonical, analysis, market, or taxonomy databases. Identity Preview remains read-only. Add Tickers Test and Production remain separate guarded operations.

An APPROVED identity review authorizes only the exact reviewed interpretation while the bound provider/canonical state remains compatible. Approval is not a permanent ticker-level override.

`PROPOSED_READY_FOR_OPERATOR_APPROVAL` is not mutation authority.

## Registry audit

The Phase 13G.3.18 registry used schema `1.0`. It recorded the proposed resolution, continuity dimensions, CIK/permaticker, canonical references, event context, and evidence. `PROPOSED` was non-authoritative, `REJECTED` was non-authoritative, and `APPROVED` could authorize mutation after several direct provider/canonical checks.

The old contract had two material gaps:

1. It did not bind approval to a deterministic fingerprint of the reviewed evidence and expected state.
2. It could not prove that an approval still represented the exact provider/canonical state seen by the operator.

Schema `2.0` adds `expected_state` and `unresolved_assumptions`. An approved record must additionally contain a complete `approved_resolution`, its `approval_fingerprint`, and lightweight `approval_metadata`. No record was promoted to `APPROVED` in this phase.

## Lifecycle

The lifecycle is:

`research -> PROPOSED -> readiness Preview -> operator decision -> version-controlled APPROVED record -> fresh Identity Preview -> Add Tickers Preview -> Test on copies -> separately authorized Production update`

Readiness and authority are independent:

- `PROPOSED_NOT_READY`: material facts or state binding are incomplete.
- `PROPOSED_READY_FOR_OPERATOR_APPROVAL`: structurally complete and currently consistent, but not authorized.
- `APPROVED_VALID`: approval fingerprint is valid and current state matches the approved assertions.
- `APPROVED_INVALID`: the approved contract is stale or conflicting and cannot authorize mutation.
- `APPROVED_SUPERSEDED_BY_LOCAL_DETERMINISTIC`: compatible provider evidence became available and the normal deterministic resolver, not review authority, controls the result.
- `REJECTED`: never mutation authority.

## Approval fingerprint

`approval_fingerprint` is SHA-256 over canonical JSON containing only material approval facts:

- registry schema version and normalized subject ticker;
- resolution and continuity dimensions;
- predecessor/ticker relationship;
- canonical company/security references;
- normalized CIK, provider permaticker, exchange, and effective date where applicable;
- sorted expected-state assertions;
- authoritative evidence type, authority, reference, and fact.

JSON key order, descriptive reason text, research timestamp, report timestamp, file path, and Markdown formatting are excluded. The same facts therefore reproduce the same fingerprint, while a material identity change produces a different fingerprint.

## Current-state binding

Every consumption of a reviewed record reads provider and canonical databases again in read-only mode. It compares the approved expected state to current:

- provider availability and provider CIK/permaticker/exchange;
- subject current-security and alias matches;
- CIK-to-company and permaticker-to-security mappings;
- referenced company key/status/CIK set;
- referenced security company, current ticker, exchange, and active state.

A fingerprint mismatch yields `APPROVED_REVIEW_EVIDENCE_MISMATCH`. Provider contradictions yield `APPROVED_REVIEW_PROVIDER_CONFLICT`. Canonical contradictions yield `APPROVED_REVIEW_CANONICAL_CONFLICT`. State drift also yields `APPROVED_REVIEW_STALE`. All are fail-closed `IDENTITY_REVIEW_REQUIRED` outcomes.

Current deterministic provider truth remains stronger than a review. An approved review cannot override contradictory provider identity. A deterministic current resolution may make the reviewed path unnecessary.

If provider metadata was absent at approval but later appears, a provider-status change alone does not replay the approval. Compatible metadata is routed through the normal local deterministic resolver. Any material CIK, permaticker, or canonical mapping contradiction remains fail-closed.

## Mutation plan

An `APPROVED_VALID` resolution produces an explicit plan rather than a ticker-level permission. Operations include:

- reuse or create company;
- reuse, preserve, or create security;
- close a predecessor alias interval;
- add the new current alias;
- update the current ticker only for proven same-security continuity;
- populate CIK and provider identity only when included in the approved contract.

The plan includes concrete current references and marks newly allocated candidate IDs explicitly. Same-security transitions preserve both `company_id` and `security_id`. Same-company/new-security resolutions preserve the predecessor security and create a separate security. New-company/new-security resolutions create both identities. Add Tickers rejects a reviewed plan unless its authority is `APPROVED_REVIEW`, readiness is `APPROVED_VALID`, the reason is `APPROVED_REVIEW_VALID`, and the approval fingerprint is present.

## Real-case readiness on 2026-09-21

| Ticker | Readiness | Proposed canonical consequence | Approval fingerprint |
|---|---|---|---|
| DRK | `PROPOSED_NOT_READY` | None | `081c4844dc8b84d2d0a95c82a2104a8c06167399c68f3404306173e73d25a895` |
| KRSA | `PROPOSED_READY_FOR_OPERATOR_APPROVAL` | Reuse company 627, preserve security 628/CYCN, create successor security | `9440127ada42c4531eb4c2dd53c468efbe92810951bffcad64811488839ef7ee` |
| PSQL | `PROPOSED_READY_FOR_OPERATOR_APPROVAL` | Create company and security; do not alias BBCQ | `ef64506712560ac892323bcfa590b7e454fa22feb2619363b6aee61f9eec6b6c` |
| QVCG | `PROPOSED_READY_FOR_OPERATOR_APPROVAL` | Create successor company and new security; do not alias old cancelled equity | `2f6ac6bb546181dfe7e228bbae25cfacebc488d820eb46b5e66a8e95d65591c4` |

DRK differs because the latest authoritative filing still says DRK is reserved and subject to Nasdaq procedures while ANY remains the trading symbol. The effective date, exchange-effective change, and exact security continuity are therefore unresolved. It has no mutation plan.

KRSA is bound to the existing CYCN issuer (`company_id=627`, CIK `0001755237`) and predecessor security (`security_id=628`). The reviewed interpretation creates a distinct successor security because the event included a reverse split and new CUSIP.

PSQL is a new public issuer/security after the multi-step business combination. BBCQ ticker or security continuity is not inferred. QVCG is a reorganized successor issuer with newly issued equity; cancelled QVCAQ/QVCBQ equity is not represented as QVCG alias history.

## Tests

Focused tests cover fingerprint stability and material change, proposed/rejected non-authority, approved same-security planning, stale canonical state, same-company/new-security planning, new-company/new-security planning, provider conflict, evidence mismatch, and a fixture-sized real Add Tickers producer/application path. The production-shaped same-security fixture proves stable company/security IDs and preserved ticker history.

## Operational result

- Live Identity Preview was read-only.
- No reviewed record was approved.
- No Add Tickers Test or Production operation was run.
- No scheduler state was changed.
- No phase-owned candidate or full-size database was created.
