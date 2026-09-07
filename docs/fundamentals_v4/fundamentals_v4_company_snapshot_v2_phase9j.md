# Company Snapshot V2 Phase 9J

Status: `COMPLETE_PRESENTATION_ONLY`

## Scope

Phase 9J changes only the Company Snapshot V2 presentation contract and Markdown
rendering. No formula, threshold, numeric result, readiness decision, persisted
reason code, model identity, production database, active package or existing
production report changed.

The report remains currently revised rather than original PIT history. Reported
Common Earnings remain GAAP-based and are not normalized. Current-price
valuation remains indicative. Diagnostic flags remain numeric review candidates,
not confirmed accounting events.

## Presentation changes

1. Dates backed by `source_availability_date` are now labelled as source
   availability dates. Fiscal quarter and TTM period end identify the economic
   period; source availability date identifies when RawCandle treats the data as
   available; price date identifies the market observation; report date identifies
   snapshot generation. Source availability is not automatically claimed to be a
   legally verified filing timestamp.
2. `Valuation-komponenttien pistemuutokset` explicitly reports QoQ, 2Q and YoY
   component-score changes in points. The total Valuation Score row is also a
   score-point change. Raw-yield percentage-point values and market-price
   percentages remain separate.
3. The seven-row diagnostic table now has `Tulkinta` instead of `Reason code`.
   It renders deterministic Finnish explanations without exposing internal reason
   identifiers in the main report.
4. Active package and model-family hashes were removed from the opening summary.
   Active package, model family, Snapshot economic and report presentation
   fingerprints each appear explicitly in the technical appendix.

Representative label changes:

| Before | After |
|---|---|
| `Latest filing` | `Latest endpoint (availability date)` |
| `Previous filing` | `Previous endpoint (exact Q-1 availability date)` |
| `Source availability / filing date` | `Source availability date` |
| `Filing-date Valuation comparisons` | `Valuation-komponenttien pistemuutokset` |
| `Reason code: CAPEX_INTENSITY_SHIFT_THRESHOLD_MET` | `CAPEX-intensiteetin muutoksen tarkastusraja täyttyi; havainto on tarkastettava ehdokas.` |

## Diagnostic coverage

The renderer maps all 26 reason codes declared by the active Diagnostic Flags V2
engine. The active production package contains 50 distinct flag/status/reason
combinations and 23 distinct reason codes; every one resolves to a readable
explanation. Coverage includes active, clear, missing-input, non-finite-input,
missing comparison, non-consecutive fiscal chain, denominator/readiness,
unavailable valuation and unsupported accounting-model outcomes. An unknown
future reason renders the neutral text `Tarkempaa käyttäjäselitettä ei ole
saatavilla.` without leaking the identifier.

Status, reason code, triggered value, evidence and threshold continue to come
unchanged from the structured reader result. `EVALUATED_FLAGGED`,
`EVALUATED_CLEAR`, `FLAG_NOT_READY` and `FLAG_NOT_APPLICABLE` are not collapsed.

## Fingerprints

| Identity | Before Phase 9J | Phase 9J | Decision |
|---|---|---|---|
| Snapshot economic | `1b4963c3b968008dd753d86c9a95c5f21737956113ea5c70f481b2ee96757f64` | unchanged | no economic change |
| Presentation | `e9660690c9ccedc2936c14d8b5d2bb3abc7d62f0d10f11a75d349f770f7fe779` | `783c00b8d88cb9cf7715e867f41a7dd673618ab10d92bb4451559c2c9cab6aec` | labels, explanations and placement changed |
| Active package | `a36d6903c3d640da5e9bd7034faee700b7b064e74ea871880c1bfa2348f4964d` | unchanged | presentation is outside package economics |
| Model family | `634824f179652da81ea6f38962d9a7c87df37c0627fed089a918ce9efa83d8e9` | unchanged | no model composition change |
| Per-report content | report-specific V3 value | report-specific V4 value | rendered bytes changed deterministically |

The production package manifest does not require the presentation fingerprint,
so no production activation or manifest update was needed.

## Example reports

Reports were generated only under
`temp/fundamentals_v4_company_snapshot_phase9j/reports/`:

| Company | Validation case | V4 content fingerprint |
|---|---|---|
| NVDA | all seven clear; working-capital evidence near its threshold | `1cdc878529907a54c7a269df02989c327a51a83a4c12b5b36054026d7de9d229` |
| AGEN | active Working Capital Shift | `a7f2f7525db144e394b466a17bb3c92c6c825a4e81d47c1f0254d00d5f80f83e` |
| CRMD | clear Working Capital; high valuation | `ce12aa788fe0e3b7b10b03337e4fbf62be37ea42c134259cd3f698bedf2626bc` |
| APD | negative Reported Common Earnings and `N/M` | `18cf6c455a65eef44a159b925e369cfa8010ee706b8843e0a195b8a999d76f67` |
| AAT | unsupported accounting model; not applicable | `8197e7e37f805168df91ddeb84e287e40f5860cfbd160a5067b5d564441a1332` |
| BNC | mixed readiness and missing input | `6f5bfeeaef5e80d58184467be5b75d6b257083b86f211cce4916a91ac34b80f8` |
| AAOI | active non-working-capital CAPEX-intensity flag | `4a19f11a284e8374c313b971423bdb86f98e3f9ccc17892783d36a9fcbeb8c16` |
| ILLR | genuine non-consecutive fiscal chain | `f600e5b2a08e92b2ae30fee4fb05645e4a58428f194af3b3bfdd8696dac95c99` |

NVDA generation repeated with `NO_CHANGE` and the same fingerprint. No raw
diagnostic reason identifier, ambiguous filing-date label or internal database
ID appears in the main reports. Package identifiers occur only after
`Tekninen liite`.

## Invariance and safety

The assembler's economic paths are unchanged; its only Phase 9J changes are the
presentation contract identifier and presentation-spec declarations. Renderer
changes consume the same structured values. Focused assertions preserve dates,
scores, components, raw yields, Reported Common Earnings, three-point valuation,
diagnostic statuses/reasons/evidence and all economic fingerprints. Existing
reconciliation checks retain binary64 values and tolerance `1e-12`.

Preflight SHA-256 values were:

| Artifact | SHA-256 |
|---|---|
| `data/fundamentals_v4.db` | `f553639e7f25ce75fed51af0c2127121a96573cd88728c2eafa84b9dfdc087da` |
| `data/fundamentals_analysis.db` | `ea61ea956449a89834e5b473cbd654ad586dad1bfeebb55e8d09a4f4207d8ad3` |
| `data/osakedata.db` | `be9563618ccdadb98cbafc385acc91b2b4a516c926c664c129cd15fe5d04a9f5` |
| `data/analysis.db` | `c95f9b163241c1e3998d6011b3375fe5df73fd1a83fca9d25aa94b5a2b9d2ed2` |
| `data/fundamentals_provider.db` | `1905d09cf93901622ae178e7b472e571bc872ba2b243ff3b02a5957f9b6e2c14` |
| aggregate `fundamental_reports` content | `cc658c23869cdb2d9a27b2ee9f0143b01e8c4561a42b180f448b73fd2fd0245c` |

Postflight values matched these values exactly. SQLite `quick_check` remained
`ok`, foreign-key checks remained empty, and the active package remained
`a36d6903...`. No database write, migration, rebuild, provider update, package
activation or production-report overwrite occurred.

## Verification

- Phase 9J focused renderer/assembler tests: `25 passed`.
- Complete Fundamentals V4 plus relevant Snapshot/UI/CLI/Scheduler group:
  `943 passed` in 98.06 seconds.
- `compileall` and `git diff --check`: passed.
- Full repository suite: not run because no shared infrastructure outside
  Fundamentals V4 Snapshot presentation changed.
- Optional formatters/linters: not installed or run.

The existing UI and service code are unchanged. Regression coverage verifies
multi-ticker separators, stable de-duplication, partial success, overwrite
protection, recent-report listing, secure byte-identical download, traversal
rejection and symlink rejection.

## Remaining limitations

This is still a currently revised snapshot, not an original point-in-time
reconstruction. Source availability is RawCandle's availability contract, not a
legal filing-time verification. Readable diagnostic explanations do not infer
causes, normalize earnings or convert candidates into confirmed events.

## Phase 9J.1 follow-up

Phase 9J.1 superseded presentation V4 with V5. The mixed-unit current-price
table now labels the row `Valuation Score`; only its difference cell carries the
score-point suffix `p`. Score levels remain plain values, while price changes
retain price units or `%` and raw-yield changes retain `pp`. The remaining
Finnish history-table label `Availability date` is now `Saatavuuspäivä`.

No economic value, date selection, diagnostic presentation or economic identity
changed. See `fundamentals_v4_company_snapshot_v2_phase9j_1.md`.
