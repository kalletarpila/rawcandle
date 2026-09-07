# Company Snapshot V2 Phase 9F

## Scope

Phase 9F restores the approved Phase 7B/7C Company Snapshot presentation while retaining the active Operating-Income V2 model family. The change is limited to report assembly, reading, rendering, tests, and audit tooling. It does not change economic formulas, persisted rows, production schemas, canonical data, provider data, or automatic scheduling.

The report remains a currently revised view, not an original point-in-time reconstruction.

## Active report contract

Phase 9J.1 superseded the original Phase 9F presentation contract with
`CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V5`. Its deterministic
presentation fingerprint is defined by `REPORT_CONTRACT_SPEC` in
`snapshot/v2_assembler.py`. The Snapshot economic model remains unchanged.

Phase 9H activated economic Snapshot fingerprint `1b4963c3b968008dd753d86c9a95c5f21737956113ea5c70f481b2ee96757f64` and package fingerprint `a36d6903c3d640da5e9bd7034faee700b7b064e74ea871880c1bfa2348f4964d`. Phase 9J changed the report presentation fingerprint while keeping it separate from these unchanged economic identities.

Score, Lifecycle, Valuation, Delta and Relative Position fingerprints remain
unchanged. Phase 9H changed only the Diagnostic Flags and dependent Snapshot
economic fingerprints shown above.

## Report content

The report uses authoritative fiscal year and fiscal quarter labels. Database primary keys, endpoint IDs, quarter IDs, and fiscal sequence values are not rendered.

- Fundamental Score: five exact fiscal endpoints, oldest to newest, including total, readiness, all seven components, and component evidence.
- Availability-date Valuation: five exact fiscal endpoints, oldest to newest, including persisted score, status, availability-date price, component points, and raw yields.
- Lifecycle: four exact fiscal endpoints with raw state, confirmed state, status, candidate confirmation count, Operating Margin, Operating Margin Direction, and transition state.
- Delta: current QoQ, 2Q, and YoY totals and component contributions.
- Three-point valuation: indicative current moment, latest availability-date endpoint, and exact previous fiscal Q-1 availability-date endpoint. A missing Q-1 is not replaced by an older endpoint.

The three-point table contains Market Capitalization, Enterprise Value, P/E
(Reported Common Earnings), Reported Common Earnings Yield, P/FCF, FCF Yield,
EV / Operating Income, Operating Income / EV, EV/Sales, and P/S. A separate
Valuation basis table exposes the fiscal quarter, TTM period end, availability
date, price date, price, shares, market cap and Reported Common Earnings TTM for
all three contexts. Current calculations hold the latest endpoint fundamentals
fixed and use the latest eligible close.

The availability date is RawCandle's authoritative source-availability date; it
is not automatically asserted to be a legally verified filing timestamp.
Valuation comparison tables show component-score and total-score changes in
points. Raw-yield percentage points and market-price percentages remain separate.

Reported Common Earnings are GAAP-based common-shareholder earnings and are not
normalized. They affect only the common-earnings portion of Valuation Score V2
and the related displayed ratios; they do not directly affect Fundamental Score
V2 or Operating Income / EV. See
`fundamentals_v4_company_snapshot_v2_phase9i.md`.

Percentages, percentage-point changes, multiples, and compact monetary amounts are formatted only after calculation. Missing values remain `N/A`, economically non-meaningful multiples remain `N/M`, and zero remains zero. No currency is invented when the validated source contract lacks one.

Taxonomy memberships are shown separately from Relative Position. Relative results use persisted percentile and peer count values and display the peer scope and group name without silent fallback.

## Diagnostic Flags V2 audit

Phase 9F reconciles the complete active chain:

`canonical/TTM -> pure V2 engine -> persisted endpoint/evaluation -> reader -> assembler -> Markdown`

The full deterministic replay covers 50,585 endpoints and 354,095 evaluations. Each endpoint must have exactly seven evaluations. Statuses, reason codes, comparison endpoints, effective dates, triggered values, and all persisted numeric evidence are compared against the pure engine. Numeric comparison uses relative and absolute tolerance `1e-12`.

The Markdown report includes a readable active-flag explanation with the calculated value and threshold and retains a complete seven-row status table. Phase 9J renders deterministic Finnish explanations instead of internal reason-code identifiers. `FLAG_NOT_READY`, `FLAG_NOT_APPLICABLE`, `EVALUATED_CLEAR`, and `EVALUATED_FLAGGED` remain distinct; persisted reason codes and evidence remain unchanged.

## Historical audit findings (corrected in Phase 9G and deployed in Phase 9H)

### High at Phase 9F: Working Capital inputs were not wired

At the time of the Phase 9F audit, the deployed V2 diagnostic endpoint builder
did not pass `accounts_receivable`, `inventory`, `accounts_payable`,
`deferred_revenue`, or `total_assets` into `DiagnosticEndpoint`. Consequently,
all 50,585 Working Capital evaluations were either `FLAG_NOT_READY` or
`FLAG_NOT_APPLICABLE`; none was evaluated clear or active.

Phase 9F did not change this economic behavior. Phase 9G supplied the separately
versioned correction, and Phase 9H deployed it through the normal persistence
and activation controls.

### Medium at Phase 9F: V2 used an internal V1 EBIT adapter

No Diagnostic Flags V2 source query read `ebit` or `ttm_ebit`, and no
EBIT/EBITDA fallback existed. However, at Phase 9F the V2 pure engine mapped
`operating_income` to the V1 engine's internal `ebit` property and mapped the
resulting evidence names back to Operating Income. Thus the economic source
semantics were correct, but the strict architectural criterion that no V2
calculation use an EBIT-named internal field was not met.

Phase 9G replaced this adapter with a native Operating-Income implementation and
proved identical intended behavior for the six unaffected flags before the
newly fingerprinted correction was deployed.

## Phase 9G follow-up

Both findings were corrected and fully rehearsed in Phase 9G, then deployed and
activated in Phase 9H. The pre-9G package and Diagnostic rows remain explicitly
readable through their archived manifest and fingerprints.

## Safety and artifacts

The Phase 9F audit opens production databases with URI `mode=ro`, `PRAGMA query_only=ON`, and WAL-aware reads. It records database hashes, schema hashes, key row counts, quick checks, foreign-key checks, and WAL/SHM state before and after. Verification reports are written only below `temp/fundamentals_v4_company_snapshot_phase9f/`.

The audit artifacts include the contract matrix, full reconciliation, status distribution, current prevalence, boundary cases, diagnostic report examples, report manifest, fingerprint decision, and database integrity evidence.
