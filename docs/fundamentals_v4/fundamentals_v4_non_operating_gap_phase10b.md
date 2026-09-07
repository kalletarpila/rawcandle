# Fundamentals V4 Non-Operating Earnings Gap Phase 10B

Status: `IMPLEMENTED_AND_REHEARSED_NOT_PRODUCTION_ACTIVE`

## Scope and decision

Phase 10B implements `NON_OPERATING_EARNINGS_GAP_CANDIDATE` as the eighth
Diagnostic Flags V2 evaluation. It is a review candidate only. It changes no
Fundamental Score, Valuation Score, Lifecycle, Delta, Relative Position,
reported earnings value, or severity. It does not infer the economic cause of
the gap.

The implementation is a versioned candidate beside the active seven-flag
package. Production remains on package
`a36d6903c3d640da5e9bd7034faee700b7b064e74ea871880c1bfa2348f4964d`.

## Economic contract

For one coherent current TTM endpoint:

```text
gap_amount = ttm_ebit - ttm_operating_income
gap_abs_amount = abs(gap_amount)
revenue_denominator = max(ttm_revenue, 10_000_000)
gap_signed_to_revenue = gap_amount / revenue_denominator
gap_abs_to_revenue = gap_abs_amount / revenue_denominator
active = gap_abs_to_revenue >= 0.10
```

Calculation and the inclusive boundary use finite, unrounded binary64 values.
`ttm_revenue` must still be strictly positive; the USD 10 million floor does
not make zero or negative revenue evaluable. `UPLIFT`, `DRAG`, and `ZERO` mean
positive, negative, and zero signed gap respectively. These labels describe
direction only and do not identify investment gains or any other cause.

## Readiness and applicability

The candidate inherits the exact active operating-model applicability contract:

| Classification | Result |
|---|---|
| Supported non-financial operating sector | evaluable |
| Supported real-estate operating industry | evaluable |
| Financial Data & Stock Exchanges | evaluable |
| Bank | `FLAG_NOT_APPLICABLE` |
| Insurer | `FLAG_NOT_APPLICABLE` |
| REIT | `FLAG_NOT_APPLICABLE` |
| Asset Management, Capital Markets, Credit Services, Financial Conglomerates, Mortgage Finance, Shell Companies | `FLAG_NOT_APPLICABLE` |
| Missing or unrecognized classification | `FLAG_NOT_READY` |

Both TTM result measures and revenue must be observed and finite. The endpoint
audit requires four ordered consecutive input quarters, one company, matching
endpoint sequence, ready EBIT, Operating Income and revenue TTM chains, and an
availability date equal to the maximum input availability date. The canonical
TTM row supplies all three values on the same provider unit and currency basis;
there is no imputation or fallback.

Reason codes distinguish missing and non-finite EBIT, Operating Income and
revenue, nonpositive revenue, incoherent endpoint, unsupported classification,
and missing classification. Evaluated rows use distinct threshold-met and
below-threshold reasons.

## Evidence and persistence

The numeric evidence layout stores TTM EBIT, TTM Operating Income, TTM revenue,
signed and absolute gap amounts, denominator, signed and absolute ratios,
direction code, and threshold. Units are source currency for amounts and a
unitless fraction for ratios. Direction codes are `1 = UPLIFT`, `-1 = DRAG`,
and `0 = ZERO`; the reader reconstructs the readable direction deterministically.

The existing 16 numeric slots are sufficient. No schema migration is required.
The new `DIAGNOSTIC_SCALAR_EVIDENCE_V3` identity prevents reinterpretation of
the V2 layout. The candidate uses persistence version
`OPERATING_INCOME_V2_PARALLEL_PERSISTENCE_V2` because the coherent package and
diagnostic layout identities changed.

## Version identities

| Identity | Candidate value |
|---|---|
| Diagnostic model | `CURRENTLY_REVISED_DIAGNOSTIC_FLAGS_V2_EIGHT_FLAG_V1` |
| Diagnostic fingerprint | `0ac66c6749afc889cf553c47436757a54f644b6a81febd161cf947885e444904` |
| Snapshot model | `CURRENT_REVISED_COMPANY_SNAPSHOT_V2_EIGHT_FLAG_V1` |
| Snapshot economic fingerprint | `f04e5dedf0cadecbd6039eabdcfc16d77a17b8cce729a63a810df7914d352a11` |
| Snapshot presentation contract | `CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V7` |
| Snapshot presentation fingerprint | `b539ceb4e4745aa1233b27d9883b442d6106a2a1b4769a7c52bcf099cb55ad87` |
| Candidate package fingerprint | `0e269e52a63500342df8a08ee2f91552fdc8fb216fa68cfe469bafb6aa8e3c30` |
| Diagnostic layout fingerprint | `d2040687f976f6e3807f5de6b2022a384bedeee02eb8d5294e98101b3fe06979` |
| Diagnostic source fingerprint | `ae75df9522de07ea2113f505d32f06dc4b112057c1cd74ac103af3b89b6414df` |
| Diagnostic economic-result fingerprint | `a3dde822dbfff98081d50fd4dd7534ee346b31cc74d75d3a40a1d91c45aeff5d` |
| Diagnostic physical-content fingerprint | `7f4ea56523a403a2789a4f74977301a299bc4941228b205fe84c820adc36f8bf` |
| Package economic-result fingerprint | `da43d4f0c466c06dbf7a7777ae8e92d2f69b5fb7d27d5280345cb76c92be69fb` |
| Package physical-content fingerprint | `d0b39ac2b568623e59b50288ebe304fa169f99830d615715b69a68b492f4b362` |

Score, Lifecycle, Valuation, Delta and Relative Position fingerprints are
unchanged. The active seven-flag model fingerprint remains
`7f6291bf04e69cf22944ea3f81e07b284ccffd8edbd0edea4190ddc79050b031`.

## Reconciliation and distribution

The full history contains 50,585 endpoints and exactly 404,680 candidate
evaluations. All 354,095 evaluations for the existing seven flags reconcile
exactly in decision, status, reason and evidence.

The new flag reconciles to Phase 10A analysis fingerprint
`30652d3a1a5f7bf2fb73258f3c715d62addc2713f2fe4c9a16e3329433d1d2c0`:

| Population | Evaluable | Active | Rate among evaluable |
|---|---:|---:|---:|
| Full revised history | 36,893 | 5,319 | 14.42% |
| Current fresh | 2,110 | 334 | 15.83% |

Current active directions are 230 UPLIFT and 104 DRAG. Against the complete
2,431-company current-fresh universe, new-flag prevalence is 13.74%.

Within the 2,110-company relevant evaluable comparison, the seven-flag union is
423, overlap is 226, incremental candidates are 108, and the combined union is
531. Combined-union prevalence is 25.17% of the evaluable comparison and 21.84%
of the entire current-fresh universe. NOT_READY and NOT_APPLICABLE observations
remain visible outside the evaluable denominator.

Current reference values reproduce Phase 10A: NVDA is UPLIFT by USD 32.628B
and 10.7694%, AMZN by USD 84.515B and 10.8956%, and GOOG by USD 152.615B and
34.2288%.

Lifecycle and industry concentrations remain descriptive context. They do not
change eligibility, threshold, score, or status.

## Snapshot presentation

Candidate Company Snapshot V2 reports contain eight definitions and eight
status rows. Evaluated gap rows show signed amount, UPLIFT/DRAG/ZERO direction,
absolute gap-to-revenue ratio, inclusive 10% threshold, and status. The
zero-active wording distinguishes eight clear evaluations from incomplete or
inapplicable coverage. Existing Phase 9J.2 sections and the prohibition on
internal database IDs remain unchanged.

Candidate reports are generated only under the Phase 10B `temp` artifact
directory. Production `fundamental_reports` files are not touched.

## Rehearsal and safety

The production-shaped rehearsal uses three SQLite backup copies. It verifies
two independent first applies, a true zero-write `NO_CHANGE`, rollback after
diagnostic-stage failure injection, strict pure-engine/persistence/reader
reconciliation, archived seven-flag readability, candidate Snapshot rendering,
quick check, foreign keys, duplicate and orphan checks, and preflight/postflight
production hashes. Company-scoped mutation is not supported by this full-history
package and was therefore not simulated.

The authoritative run details, physical fingerprints, durations, storage
measurements and generated report fingerprints are in
`temp/fundamentals_v4_non_operating_gap_phase10b/20260907T193000Z/phase10b_rehearsal.json`.
The database grows by about 103 MB. No schema migration or `VACUUM` is needed.
The copied database uses rollback-journal mode, so a WAL peak is not applicable.
The first apply took 40.24 seconds and inserted 455,265 candidate diagnostic
endpoint/evaluation rows. The repeated apply returned `NO_CHANGE` with zero
logical writes in 27.93 seconds. Both independent applies produced identical
source, economic and physical fingerprints.

## Verification

- New engine, boundary, applicability and identity tests: 30 passed.
- Complete Fundamentals V4 plus Snapshot UI group: 789 passed in 95.27 seconds.
- Full-history deterministic calculation, two independent applies, no-op,
  rollback, reader and report reconciliation: passed.
- Compile checks, `git diff --check`, SQLite `quick_check`, foreign keys,
  duplicates, orphans and report internal-ID search: passed.

The full repository suite was not run because no shared infrastructure outside
Fundamentals V4 and Company Snapshot was changed. No optional tool was installed.

Production preflight and postflight matched byte for byte. The analysis database
SHA-256 remained
`ea61ea956449a89834e5b473cbd654ad586dad1bfeebb55e8d09a4f4207d8ad3`;
canonical remained `f553639e...`, market `be956361...`, provider `1905d09c...`,
and taxonomy `c95f9b16...`. Every schema hash, size, mtime, relevant row count,
sidecar state, quick check and foreign-key result also matched.

## Remaining risks and Phase 10C

The history is currently revised, not PIT. The diagnostic identifies a provider
EBIT versus Operating Income gap but cannot establish its accounting cause.
Current taxonomy is not historically versioned. Source currencies are coherent
within an endpoint but are not converted for cross-company amount comparison.

Phase 10C should be limited to protected production preflight, backup, additive
candidate backfill, exact reconciliation, atomic activation of the complete
eight-flag package, active-reader and Snapshot/UI smoke tests, mandatory second
`NO_CHANGE`, rollback evidence, and postflight immutability checks for every
non-analysis database and production report not explicitly regenerated. It must
not alter formulas, thresholds, scores, source data, or other model layers.
