# Phase 13G.3.48 Live Publication-Date Bootstrap

## Outcome

- Run ID: `20260926T163001Z_first_public_result_date_bootstrap_production`
- Outcome: `COMPLETED`
- Postflight: `PASSED`
- Rollback/recovery: `NOT_REQUIRED`
- Publication roles: `provider`, `canonical`, `analysis`
- Calculation as-of: `2026-09-22`, matching the previously active analysis generation

The operation used the shared production lock, scheduler lock, authoritative
taxonomy lock, durable publication journal, verified three-role backups, and
role-by-role fsynced replacement contract. No Refresh source acquisition or
Refresh Full Workflow was executed.

## Preflight

The locked preflight matched the accepted Phase 13G.3.47 baseline:

- Canonical quarters: 89,872
- Established `first_public_result_date`: 88,856
- Missing values: 1,016
- Bootstrap eligible: 1,015
- Repair required: 1, SPCB company 2532 FY2022 Q4
- Provider SHA-256: `5663ad710809199fe1b87f8828e1110092c831469123fe9bb86d41993b46a7d7`
- Canonical SHA-256: `c5c5db991b6e24864e2ec7796638533561f8c3de4a7fedca7356a0a12e84ee62`
- Analysis SHA-256: `c6a5d4a31444801514163f558faae7ea130f8451b276a89c5a489e0a13c0bdda`
- Publication journal: clear
- SQLite quick checks: `ok`; foreign-key errors: 0

SPCB quarter 89588 started with source availability `2022-05-20`, NULL
first-public date, and total assets 45,077,000. The provider contained the valid
`2023-04-20` observation and invalid newer-lastupdated `2022-05-20`
observation exactly as audited.

## Candidate Evidence

- Initial safe bootstrap rows initialized: 1,015
- SPCB rows initialized after generic reconciliation: 1
- Total rows initialized: 1,016
- Established dates changed: 0
- Quarter IDs changed: 0
- Company/security identity changed: no
- Canonical financial keys changed: only `(2532, 2022, Q4)`
- Unrelated financial values changed: no
- SPCB accepted whole-observation winner date: `2023-04-20`
- SPCB accepted winner total assets: 42,040,000

The provider candidate was byte-identical and semantically equivalent to the
live provider immediately before publication. Its SHA-256 remained
`5663ad710809199fe1b87f8828e1110092c831469123fe9bb86d41993b46a7d7`.
No source refresh change entered this operation.

Because the valid SPCB canonical observation also changed a financial value,
the operation rebuilt TTM and used the normal single full V2 + RP V2 + RV path.
The as-of date remained `2026-09-22` to avoid unrelated market-date drift.
Candidate package, taxonomy lineage, RP, RV, SQLite, and foreign-key validation
all passed before backups or the publication journal were created.

## Publication And Postflight

The journal was durably `PREPARED` before the first replacement. Provider,
canonical, and analysis were each replaced and fingerprint-verified, followed
by independent published-generation postflight. The terminal journal is:

- State: `COMPLETED`
- Postflight state: `PASSED`
- Rollback/recovery state: `NOT_REQUIRED`
- Production writes blocked: no

Live postflight:

- Canonical quarters: 89,872
- Established first-public dates: 89,872
- NULL first-public dates: 0
- Bootstrap eligible: 0
- Repair required: 0
- SPCB quarter ID: 89588
- SPCB source availability: `2023-04-20`
- SPCB first-public date: `2023-04-20`
- SPCB total assets: 42,040,000
- Publication-date component of `future_test_authorized`: true
- Provider live SHA-256 unchanged from preflight
- Provider/canonical/analysis quick checks: `ok`
- Provider/canonical/analysis foreign-key errors: 0

Published SHA-256 values:

- Provider: `5663ad710809199fe1b87f8828e1110092c831469123fe9bb86d41993b46a7d7`
- Canonical: `2693feca6729be3b767145d9e1962cd962f902c96bce482a49e7c538425c7084`
- Analysis: `b068d87d027427b1afd11ec338b84ae2c01c3d2eb4dba022df980643e6535dde`

## Retained Rollback Backups

- Provider: `backups/fundamentals_admin_production/20260926T163001Z_first_public_result_date_bootstrap_production/provider.db`, SHA-256 `9d439fcf499bbad128d1e39d6b809033d639b07b268d907242c09a2e14be7d89`
- Canonical: `backups/fundamentals_admin_production/20260926T163001Z_first_public_result_date_bootstrap_production/canonical.db`, SHA-256 `7cd67b7b5b3f4b4678cb30ec68c493cd9b12d1077417e0fc373f149fbe905cb2`
- Analysis: `backups/fundamentals_admin_production/20260926T163001Z_first_public_result_date_bootstrap_production/analysis.db`, SHA-256 `df52870404ed6c5fc461c2a3cc71403f379591c852b8a55b96432478a0452935`

All three backups passed SQLite quick and foreign-key checks. They remain for
the normal operator acceptance and cleanup workflow.

## Cleanup And Evidence

The run-owned candidate/source-bundle lane was removed after terminal success.
Remaining phase-owned large temp files: 0. The scheduler/systemd state was not
changed. Runtime evidence remains at:

`fundamental_reports/admin_runs/20260926T163001Z_first_public_result_date_bootstrap_production/operation_report.md`

No source code was changed, no Git commit was created, and nothing was pushed.
