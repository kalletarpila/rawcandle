# Company Snapshot V2 Phase 9J.1

Status: `COMPLETE_PRESENTATION_ONLY`

## Corrections

Phase 9J.1 corrects exactly two presentation defects:

1. The mixed-unit current-price row changed from
   `Valuation Score (muutos pistettä) | 27.02 | 24.15 | −2.87` to
   `Valuation Score | 27.02 | 24.15 | −2.87 p`. The first two cells are score
   levels; only the final cell is a score-point change. The shared `Muutos`
   heading remains unit-neutral because its column also contains absolute price
   changes, price percentages and raw-yield percentage-point changes.
2. The remaining `Availability date` row in the Finnish Fundamental Score
   history table changed to `Saatavuuspäivä`. No date value or selection changed.

Searches of the Phase 9J renderer and examples found no other instance of these
two semantic defects. The separate `Valuation-komponenttien pistemuutokset`
table was already correct and remains unchanged.

## Identities

| Identity | Phase 9J | Phase 9J.1 | Decision |
|---|---|---|---|
| Presentation contract | `CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V4` | `CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V5` | presentation corrected |
| Presentation fingerprint | `783c00b8d88cb9cf7715e867f41a7dd673618ab10d92bb4451559c2c9cab6aec` | `8af475ace78803aa6ea4e703cb85c2cd19b3090081340fff7228bfe432671153` | deterministic presentation change |
| Snapshot economic | `1b4963c3b968008dd753d86c9a95c5f21737956113ea5c70f481b2ee96757f64` | unchanged | no economic change |
| Active package | `a36d6903c3d640da5e9bd7034faee700b7b064e74ea871880c1bfa2348f4964d` | unchanged | no activation |

All Score, Lifecycle, Valuation, Delta, Relative Position and Diagnostic Flags
model fingerprints remain unchanged. The production manifest is unchanged.

## Example evidence

Reports were generated only under
`temp/fundamentals_v4_company_snapshot_phase9j_1/reports/`:

| Company | V5 content fingerprint |
|---|---|
| NVDA | `83766099b095bc3d613165f80811267bf590903292fd79e8f07d574f58a559a4` |
| CRMD | `30180354c4b03ab9b60e0f37be34f4bc6d6d8500d48732b01d0f14ac4917300c` |
| APD | `264a4971bd67d02449b26fff0d716944b1fe6451918aade7f005377daa02108f` |
| AAT | `a74519fad8458a3208d6a62dfb94ef30b4f10217fe870e43a30f8466cd7a8b58` |
| BNC | `20a7b2cdc7606d70edfa801e5049fbdda922213c7917d9eedfec32beebc65e39` |
| AGEN | `35a072ccb53e1ee04f2bdffeb03537bc84927f7b97bc0da06efe371e27dfa813` |

Every applicable mixed-unit table retains plain score levels and uses `p` only
for the Valuation Score difference, `%` for the price percentage and `pp` for
raw-yield differences. Missing score differences remain `—`, without a false
unit. Diagnostic explanations remain unchanged, and the active package hash
appears only in the technical appendix. Repeated NVDA generation returned
`NO_CHANGE` with byte-identical output.

## Numeric invariance

A complete line diff of each V4/V5 example pair contains only:

- `Availability date` to `Saatavuuspäivä`, with identical dates;
- the Valuation Score row label and `p` suffix, with identical numbers;
- report contract, presentation fingerprint and derived report-content
  fingerprint rows.

No other report line changed. This proves unchanged assembled values, dates,
scores, components, yields, valuation inputs, lifecycle, deltas, relative
positions, diagnostic statuses, explanations, evidence, thresholds and
readiness for the six representative source states.

## Production immutability

Preflight SHA-256 values:

| Artifact | SHA-256 |
|---|---|
| `data/fundamentals_v4.db` | `f553639e7f25ce75fed51af0c2127121a96573cd88728c2eafa84b9dfdc087da` |
| `data/fundamentals_analysis.db` | `ea61ea956449a89834e5b473cbd654ad586dad1bfeebb55e8d09a4f4207d8ad3` |
| `data/osakedata.db` | `be9563618ccdadb98cbafc385acc91b2b4a516c926c664c129cd15fe5d04a9f5` |
| `data/analysis.db` | `c95f9b163241c1e3998d6011b3375fe5df73fd1a83fca9d25aa94b5a2b9d2ed2` |
| `data/fundamentals_provider.db` | `1905d09cf93901622ae178e7b472e571bc872ba2b243ff3b02a5957f9b6e2c14` |
| aggregate `fundamental_reports` content | `cc658c23869cdb2d9a27b2ee9f0143b01e8c4561a42b180f448b73fd2fd0245c` |

Postflight values matched exactly. SQLite integrity and active-package checks
also remained unchanged. No production report was overwritten and no database,
provider, canonical, TTM, schema, package or manifest operation was performed.

## Verification

- Focused Snapshot renderer and assembler tests: `70 passed`.
- Broader Fundamentals V4 plus relevant Snapshot/UI/CLI/Scheduler group:
  `945 passed` in 98.71 seconds.
- `compileall` and `git diff --check`: passed.
- Full repository suite was not run because shared infrastructure outside the
  Snapshot presentation path did not change.

The existing UI service remains unchanged. Its regression tests cover
multi-ticker parsing, deterministic generation, secure byte-identical download,
traversal rejection and symlink rejection.

## Limitations

The report remains currently revised rather than original PIT history. Source
availability remains RawCandle's availability contract, not a legally verified
filing timestamp. Reported Common Earnings remain GAAP-based and unnormalized,
current-price valuation remains indicative, and diagnostic flags remain numeric
review candidates rather than confirmed accounting events.
