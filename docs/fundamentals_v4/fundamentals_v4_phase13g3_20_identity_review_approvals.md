# Phase 13G.3.20 - Identity Review Approvals

## Operator decision

The operator explicitly approved the reviewed identity interpretations for `KRSA`, `PSQL`, and `QVCG`. `DRK` was explicitly not approved and remains `PROPOSED_NOT_READY`.

Approval changes reviewed identity authority only. It does not apply the identity mutation to Production.

DRK remains PROPOSED_NOT_READY and is not authorized for Add Tickers mutation.

## Pre-approval validation

A fresh read-only Identity Resolution Preview was run against the current provider and canonical databases before editing the registry. All expected-state validations were `MATCH`.

| Ticker | Pre-approval readiness | Fingerprint |
|---|---|---|
| DRK | `PROPOSED_NOT_READY` | `081c4844dc8b84d2d0a95c82a2104a8c06167399c68f3404306173e73d25a895` |
| KRSA | `PROPOSED_READY_FOR_OPERATOR_APPROVAL` | `9440127ada42c4531eb4c2dd53c468efbe92810951bffcad64811488839ef7ee` |
| PSQL | `PROPOSED_READY_FOR_OPERATOR_APPROVAL` | `ef64506712560ac892323bcfa590b7e454fa22feb2619363b6aee61f9eec6b6c` |
| QVCG | `PROPOSED_READY_FOR_OPERATOR_APPROVAL` | `2f6ac6bb546181dfe7e228bbae25cfacebc488d820eb46b5e66a8e95d65591c4` |

The recomputed fingerprints exactly matched the Phase 13G.3.19 audit references. No reviewed material fact had drifted.

## Registry approval

Exactly three schema `2.0` records were promoted from `PROPOSED` to `APPROVED`. Each contains:

- the complete immutable `approved_resolution` reviewed by the operator;
- the canonical SHA-256 `approval_fingerprint`;
- generic `operator_approved` metadata outside the fingerprint.

DRK and its material evidence were not changed. No unrelated record was changed.

## Post-approval validation

A fresh read-only Preview consumed the committed approval shape generically:

| Ticker | Review status | Post-approval readiness | Authority | State validation |
|---|---|---|---|---|
| DRK | `PROPOSED` | `PROPOSED_NOT_READY` | `PROPOSED_REVIEW` | `MATCH` |
| KRSA | `APPROVED` | `APPROVED_VALID` | `APPROVED_REVIEW` | `MATCH` |
| PSQL | `APPROVED` | `APPROVED_VALID` | `APPROVED_REVIEW` | `MATCH` |
| QVCG | `APPROVED` | `APPROVED_VALID` | `APPROVED_REVIEW` | `MATCH` |

Each approved record reproduced the same fingerprint after approval. Approval did not change its reviewed material facts.

## Mutation plans

### KRSA

- reuse canonical company `627`;
- preserve CYCN security `628` and its history;
- create a distinct successor security;
- add only the KRSA alias to the new security from `2026-09-09`;
- retain CIK `0001755237` at company level.

Security `628` is not converted into KRSA.

### PSQL

- create a new company with CIK `0002119292`;
- create a new security;
- add PSQL as the new security's ticker from `2026-08-28`;
- do not reuse or alias BBCQ company/security identity.

### QVCG

- create the approved successor company with CIK `0001254699`;
- create a new post-emergence security;
- add QVCG as the new security's ticker from `2026-08-06`;
- keep cancelled predecessor equity separate; do not alias QVCAQ or QVCBQ into QVCG.

## Safety

- Only read-only Identity Resolution Previews were run.
- Add Tickers Preview, Test, Production, and Full Workflow were not run.
- No provider, canonical, analysis, market, or taxonomy database was written.
- No scheduler state was changed.
- No database candidates, backups, journals, or large phase-owned files were created.
