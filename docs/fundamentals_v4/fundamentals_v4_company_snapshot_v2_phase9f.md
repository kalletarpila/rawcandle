# Company Snapshot V2 Phase 9F

## Scope

Phase 9F restores the approved Phase 7B/7C Company Snapshot presentation while retaining the active Operating-Income V2 model family. The change is limited to report assembly, reading, rendering, tests, and audit tooling. It does not change economic formulas, persisted rows, production schemas, canonical data, provider data, or automatic scheduling.

The report remains a currently revised view, not an original point-in-time reconstruction.

## Active report contract

The V2 report presentation contract is `CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V2`. Its deterministic presentation fingerprint is defined by `REPORT_CONTRACT_SPEC` in `snapshot/v2_assembler.py`.

The active economic Snapshot fingerprint remains `7bfa88aa64f3897ea610894a1b7a3613abfc7881d9b9ea8e26912ef0426e7ee8`. The active package fingerprint remains `cf4ce8134c362399ea94667e4659e27a32b1e8b9de199eaaba32c91b450a51bc`. These identities describe the persisted V2 economic bundle, not Markdown layout. Changing them would require an unauthorized production package rewrite. The report therefore carries a separate presentation fingerprint.

All Score, Lifecycle, Valuation, Delta, Relative Position, and Diagnostic Flags economic fingerprints remain unchanged.

## Report content

The report uses authoritative fiscal year and fiscal quarter labels. Database primary keys, endpoint IDs, quarter IDs, and fiscal sequence values are not rendered.

- Fundamental Score: five exact fiscal endpoints, oldest to newest, including total, readiness, all seven components, and component evidence.
- Filing-date Valuation: five exact fiscal endpoints, oldest to newest, including persisted score, status, filing price date, component points, and raw yields.
- Lifecycle: four exact fiscal endpoints with raw state, confirmed state, status, candidate confirmation count, Operating Margin, Operating Margin Direction, and transition state.
- Delta: current QoQ, 2Q, and YoY totals and component contributions.
- Three-point valuation: indicative current moment, latest filing, and exact previous fiscal Q-1. A missing Q-1 is not replaced by an older endpoint.

The three-point table contains Market Capitalization, Enterprise Value, P/E, Earnings Yield, P/FCF, FCF Yield, EV / Operating Income, Operating Income / EV, EV/Sales, and P/S. Current and filing-date valuation scores are labelled separately. Current calculations hold the latest filing fundamentals fixed and use the latest eligible close.

Percentages, percentage-point changes, multiples, and compact monetary amounts are formatted only after calculation. Missing values remain `N/A`, economically non-meaningful multiples remain `N/M`, and zero remains zero. No currency is invented when the validated source contract lacks one.

Taxonomy memberships are shown separately from Relative Position. Relative results use persisted percentile and peer count values and display the peer scope and group name without silent fallback.

## Diagnostic Flags V2 audit

Phase 9F reconciles the complete active chain:

`canonical/TTM -> pure V2 engine -> persisted endpoint/evaluation -> reader -> assembler -> Markdown`

The full deterministic replay covers 50,585 endpoints and 354,095 evaluations. Each endpoint must have exactly seven evaluations. Statuses, reason codes, comparison endpoints, effective dates, triggered values, and all persisted numeric evidence are compared against the pure engine. Numeric comparison uses relative and absolute tolerance `1e-12`.

The Markdown report includes a readable active-flag explanation with the calculated value and threshold and retains a complete seven-row technical audit table. `FLAG_NOT_READY`, `FLAG_NOT_APPLICABLE`, `EVALUATED_CLEAR`, and `EVALUATED_FLAGGED` remain distinct.

## Audit findings

### High: Working Capital inputs are not wired

The deployed V2 diagnostic endpoint builder does not pass `accounts_receivable`, `inventory`, `accounts_payable`, `deferred_revenue`, or `total_assets` from canonical TTM rows into `DiagnosticEndpoint`. Consequently, all 50,585 Working Capital evaluations are either `FLAG_NOT_READY` or `FLAG_NOT_APPLICABLE`; none is evaluated clear or active.

Phase 9F does not change this economic behavior. A separately versioned corrective Diagnostic Flags phase must wire the fields, update the economic contract and fingerprint as required, rehearse the complete history, and deploy through the normal persistence and activation controls.

### Medium: V2 uses an internal V1 EBIT adapter

No Diagnostic Flags V2 source query reads `ebit` or `ttm_ebit`, and no EBIT/EBITDA fallback exists. However, the V2 pure engine currently maps `operating_income` to the V1 engine's internal `ebit` property and maps the resulting evidence names back to Operating Income. Thus the economic source semantics are correct, but the strict architectural criterion that no V2 calculation uses an EBIT-named internal field is not met.

The corrective phase should replace this adapter with a native Operating-Income implementation and prove identical intended behavior before introducing any newly fingerprinted economic correction.

## Safety and artifacts

The Phase 9F audit opens production databases with URI `mode=ro`, `PRAGMA query_only=ON`, and WAL-aware reads. It records database hashes, schema hashes, key row counts, quick checks, foreign-key checks, and WAL/SHM state before and after. Verification reports are written only below `temp/fundamentals_v4_company_snapshot_phase9f/`.

The audit artifacts include the contract matrix, full reconciliation, status distribution, current prevalence, boundary cases, diagnostic report examples, report manifest, fingerprint decision, and database integrity evidence.
