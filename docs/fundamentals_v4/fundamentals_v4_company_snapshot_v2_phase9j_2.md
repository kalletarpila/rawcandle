# Company Snapshot V2 Phase 9J.2

Status: `COMPLETE_PRESENTATION_ONLY`

## Scope

Phase 9J.2 adds one compact seven-row definition table to Diagnostic Flags and
replaces the ambiguous zero-active-flags message with readiness-aware Finnish
wording. It changes no formula, threshold, operator, status precedence, reason
code, evidence, economic result, active package or production data.

The renderer obtains every numeric threshold and operator from Diagnostic Flags
V2 `MODEL_CONTRACT`. `DIAGNOSTIC_DEFINITIONS` adds only readable terminology,
comparison horizons and applicability text. Its order is asserted against the
engine's seven-item `FLAG_NAMES` contract. The independent mapping is recorded
in `fundamentals_v4_company_snapshot_v2_phase9j_2_definition_audit.csv`.

## Definition Contract

| Flag | Comparison and measurement | Trigger |
|---|---|---|
| Abrupt Fundamental Shift | Current TTM vs exact fiscal Q−1; maximum of absolute Revenue and Operating Income changes divided by `R = max(average absolute revenue, $10M)` | either ratio `>= 20%`; positive revenue and supported operating model |
| Earnings-Cash Divergence | Current TTM vs exact fiscal Q−1; absolute difference between changes in Reported Common Earnings and operating cash flow divided by the same `R` | `>= 20%`; positive revenue and supported operating model |
| Capex Intensity Shift | Current TTM vs exact fiscal Q−1; absolute difference between period-specific `abs(CAPEX) / max(Revenue, $10M)` intensities | `>= 10 pp`; positive revenue and supported operating model |
| Net Debt Shift | Current TTM vs exact fiscal Q−1; absolute change in Total Debt minus Cash divided by the same `R` | `>= 50%`; positive revenue and supported operating model |
| Valuation Yield Outlier | Current valuation endpoint only; median and maximum of available Operating Income/EV, FCF/Market Cap and Reported Common Earnings/Market Cap yields | median `>= 25%` OR maximum `>= 50%`; `VALUATION_FULL` and applicable classification |
| Recent Margin Deceleration | Current TTM vs exact fiscal Q−1; signed sequential Operating Margin change plus current Trajectory | Trajectory `>= 7` AND margin change `<= -2 pp`; positive revenue; Operating Income may be negative; supported model |
| Working Capital Shift | Current canonical period vs exact fiscal Q−1; absolute ONWC change divided by `max(average Total Assets, $10M)`; ONWC is receivables plus inventory minus payables and deferred revenue | `>= 10%`; both Total Assets strictly positive and supported model |

All operators remain inclusive. The engine requires observed finite inputs and
never converts missing data to clear. Exact evidence fields and formulas remain
those of Diagnostic Flags V2 model fingerprint
`7f6291bf04e69cf22944ea3f81e07b284ccffd8edbd0edea4190ddc79050b031`.

## Zero-Flag Rules

- Seven `EVALUATED_CLEAR` rows: the report says none of the seven evaluated
  conditions is met and explicitly does not claim absence of other risks.
- Zero active with `FLAG_NOT_READY` or `FLAG_NOT_APPLICABLE`: the report refers
  only to calculation-ready conditions and states that all seven may not have
  been evaluable or applicable. NOT_READY and NOT_APPLICABLE are not CLEAR.
- One or more active rows: the existing `TARKASTETTAVA EHDOKAS` presentation is
  retained. No suspected cause is represented as confirmed.

Every report also states that these seven numeric conditions are not an
exhaustive accounting or risk analysis. No new flag, severity, combined score
or investment-suitability conclusion was introduced.

## Example Evidence

Reports were generated only under
`temp/fundamentals_v4_company_snapshot_phase9j_2/reports/`.

| Company | Flagged / clear / not ready / not applicable | Active flags | V6 content fingerprint |
|---|---:|---|---|
| NVDA | 0 / 7 / 0 / 0 | none; Working Capital 9.0264% vs 10.00% | `7021783530ddb69157eb8c46b50157c662dc1fb88dcd2a7f005d0fe542e9d4f7` |
| BNC | 0 / 1 / 6 / 0 | none; Working Capital clear | `85b91de662141df30df762290f9adaa3829523de3aa439d76223b89843e90e3d` |
| AAT | 0 / 0 / 0 / 7 | none; unsupported classification | `e1caa8508a41a32e1e18d67fd20f1839bdc0065ea33a6d7d1ce964359560affc` |
| AGEN | 3 / 4 / 0 / 0 | Abrupt, Earnings-Cash, Working Capital | `f0b98cad1ce94017eca1f1c6f0e39aeb1e335655594e9809f9ff99c2e9bc9590` |
| APD | 2 / 5 / 0 / 0 | Abrupt, Earnings-Cash | `6ebc794eab3181223601190c57ec3ecc580df41460e816cdb6ebb2d2bf450cdd` |
| AAOI | 1 / 6 / 0 / 0 | Capex Intensity | `36545cea3cf9ceb0ddf33a2d101b750b9668a4f01ab8a77275edb901603652a7` |
| ILLR | 1 / 0 / 6 / 0 | Working Capital | `8081e07382fd2950d1705e7b0f55433329e701bab5ed72e979a439fb28b4e610` |
| CRMD | 1 / 6 / 0 / 0 | Valuation Yield Outlier | `99234b0a3e0ae87b3766facfbc90cbb034dff709ab67d2367cf7704e353593f0` |

Repeated NVDA generation returned `NO_CHANGE` with the same bytes and content
fingerprint.

## Identities And Invariance

| Identity | Phase 9J.1 | Phase 9J.2 | Decision |
|---|---|---|---|
| Presentation contract | `CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V5` | `CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V6` | presentation extended |
| Presentation fingerprint | `8af475ace78803aa6ea4e703cb85c2cd19b3090081340fff7228bfe432671153` | `8e88c312548974e14347b3db99853e63482a9dbf295af0e8f57671ca95930bfe` | deterministic presentation change |
| Snapshot economic fingerprint | `1b4963c3b968008dd753d86c9a95c5f21737956113ea5c70f481b2ee96757f64` | unchanged | no economic change |
| Active package | `a36d6903c3d640da5e9bd7034faee700b7b064e74ea871880c1bfa2348f4964d` | unchanged | no activation |
| Diagnostic Flags V2 | `7f6291bf04e69cf22944ea3f81e07b284ccffd8edbd0edea4190ddc79050b031` | unchanged | no model change |

Structured snapshot comparisons and existing regression assertions preserve all
statuses, reasons, evidence, thresholds, counts, scores, Lifecycle, Valuation,
Delta, Relative Position, dates and valuation calculations. Only the report
contract, presentation fingerprint, new prose/table and derived report-content
fingerprint change.

## Production Immutability

Preflight SHA-256 values:

| Artifact | SHA-256 |
|---|---|
| `data/fundamentals_v4.db` | `f553639e7f25ce75fed51af0c2127121a96573cd88728c2eafa84b9dfdc087da` |
| `data/fundamentals_analysis.db` | `ea61ea956449a89834e5b473cbd654ad586dad1bfeebb55e8d09a4f4207d8ad3` |
| `data/osakedata.db` | `be9563618ccdadb98cbafc385acc91b2b4a516c926c664c129cd15fe5d04a9f5` |
| `data/analysis.db` | `c95f9b163241c1e3998d6011b3375fe5df73fd1a83fca9d25aa94b5a2b9d2ed2` |
| `data/fundamentals_provider.db` | `1905d09cf93901622ae178e7b472e571bc872ba2b243ff3b02a5957f9b6e2c14` |
| aggregate `fundamental_reports` content | `cc658c23869cdb2d9a27b2ee9f0143b01e8c4561a42b180f448b73fd2fd0245c` |

Postflight hashes matched every preflight value exactly. `PRAGMA
integrity_check` returned `ok` for all five databases. No production report,
database, provider, schema, package or manifest was written by this phase.

## Verification

- Focused Phase 9F/9J.2 Snapshot test module: `31 passed`.
- Complete Fundamentals V4 plus Snapshot UI group: `760 passed` in 96.19
  seconds. This includes Diagnostic Flags V2 engine, boundary, persistence,
  production-contract, package/fingerprint, Company Snapshot, UI generation,
  batch parsing, overwrite protection and secure-download regressions.
- Isolated eight-company generation and repeated NVDA no-change check: passed.
- `compileall`, `git diff --check`, database integrity and artifact hashes:
  passed.

The complete repository suite was not run because no shared infrastructure
outside the Fundamentals Snapshot presentation path changed. No optional tools
were installed.

## Remaining Limitations

The report remains currently revised rather than an original PIT
reconstruction. Source availability uses RawCandle's availability contract.
Reported Common Earnings remain GAAP-based and unnormalized, current-price
valuation remains indicative, and diagnostic flags remain numeric review
candidates rather than confirmed accounting events.
