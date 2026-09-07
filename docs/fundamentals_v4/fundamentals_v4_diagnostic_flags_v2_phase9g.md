# Fundamentals V4 Diagnostic Flags V2 Phase 9G

Status: `IMPLEMENTED_AND_REHEARSED_NOT_PRODUCTION_DEPLOYED`

## Scope and root cause

Phase 9G repairs two Phase 9F findings without changing a diagnostic formula,
threshold, operator, status precedence, reason code, or persistence layout.

The V2 loader selected `v4_ttm_values.*`, but the five Working Capital fields
are endpoint balance observations in `v4_quarter_financials`. Although
`DiagnosticEndpoint` declared the fields, its constructor did not pass them.
Every supported observation therefore reached the missing-input gate.

The corrected path joins `v4_ttm_values.endpoint_quarter_id` to
`v4_quarter_financials.quarter_id` and reads `accounts_receivable`,
`inventory`, `accounts_payable`, `deferred_revenue`, and `total_assets`.
The current and exact `fiscal_sequence - 1` predecessor use the same path.
Missing remains missing and zero remains zero. Working Capital chronology uses
the canonical quarter availability date. The six TTM/valuation diagnostics
retain the prior V2 TTM chronology rule.

The old V2 adapter that assigned Operating Income to a V1 field named `ebit`
has been removed. Diagnostic Flags V2 now has a native pure engine whose input,
variables, formulas, evidence, and yield names use Operating Income. V1 code,
identities, and rows are unchanged. There is no EBIT/EBITDA fallback.

## Locked calculation

```text
ONWC = accounts_receivable + inventory
       - accounts_payable - deferred_revenue
asset_scale = max((total_assets_t + total_assets_t-1) / 2, 10,000,000)
WCShift = abs(ONWC_t - ONWC_t-1) / asset_scale
active when WCShift >= 0.10
```

Both asset values must be finite and strictly positive. Accounting-specialized
companies remain `FLAG_NOT_APPLICABLE`. Missing/non-finite fields and invalid
chains retain their explicit `FLAG_NOT_READY` reasons.

## Fingerprints

| Identity | Before | Corrected rehearsal | Decision |
|---|---|---|---|
| Diagnostic model | `d5434e139b68ee8af44dffce34cb9225538f0badb61d5d1074fb976a4de3185d` | `7f6291bf04e69cf22944ea3f81e07b284ccffd8edbd0edea4190ddc79050b031` | changed |
| Package | `cf4ce8134c362399ea94667e4659e27a32b1e8b9de199eaaba32c91b450a51bc` | `a36d6903c3d640da5e9bd7034faee700b7b064e74ea871880c1bfa2348f4964d` | changed |
| Diagnostic source | `0a2f2248cfff7d6c956b8582f5a28e64645994b7e3d66ec1e09d5dcf2c349c25` | `ac3703717563f884555ed3a3e442f05cbb7d58bff52787342249f3812f21dc3d` | changed |
| Diagnostic result | `e7bef9b66feb5fdf55ccdb220cb7794e04b00c8bd16c2b1279ce8f970f18f142` | `f51858c047c3070fda072ffe3fdd683b0537cfc790cd6e2a81ffb0d19c6bbf80` | changed |
| Diagnostic physical | `bcc61ee04f644f59e6c80d22e9ed07a4b13b5bc8a1b4c39872d88b436647e766` | `124ca6c140b9a466a34133fd5d468e2d5e04c0119dddd3addd50aef484f02c27` | changed |
| Diagnostic layout | `75b83b2c228fc2ce87c218d00c946ef65c5c408aca2a7ad12db92ee1a485a955` | same | preserved |
| Snapshot economic | `7bfa88aa64f3897ea610894a1b7a3613abfc7881d9b9ea8e26912ef0426e7ee8` | `1b4963c3b968008dd753d86c9a95c5f21737956113ea5c70f481b2ee96757f64` | changed |
| Snapshot presentation | `bc4b4a3b355063697f1fe3182a105342d804a59bb41a86ec40ef6fe4364abee2` | same | preserved |

Economic identities change because required observations now produce
evaluations. The layout identity is preserved because the tables, 16 numeric
slots, field order, and boolean mask are unchanged. Other model fingerprints
are unchanged. Active readers resolve the activated package's own manifest,
so the deployed pre-9G package remains usable until separate deployment.

## Rehearsal evidence

The safe-copy run is under
`temp/fundamentals_v4_diagnostic_phase9g/20260907T093359Z/`.

- 50,585 endpoints and 354,095 evaluations
- exactly seven evaluations per endpoint; zero duplicates and orphans
- `quick_check = ok`; no foreign-key violations
- pure engine equals persistence and reader at tolerance `1e-12`
- deterministic replay; second apply `NO_CHANGE` with zero growth
- injected diagnostic-stage failure rolled back
- all 303,510 evaluations for the other six V2 flags unchanged
- all 50,585 V1/V2 Working Capital endpoints exactly reconciled
- Score, Lifecycle, Valuation, Delta, and Relative Position hashes unchanged

Full-history Working Capital changed from zero evaluated rows, 47,682 not-ready,
and 2,903 not-applicable to:

| Status | Count |
|---|---:|
| EVALUATED_FLAGGED | 1,265 |
| EVALUATED_CLEAR | 43,861 |
| FLAG_NOT_READY | 2,556 |
| FLAG_NOT_APPLICABLE | 2,903 |

The previously reported 2,451-company distribution (51 flagged, 2,255 clear,
6 not ready, and 139 not applicable) is the latest endpoint for every company,
not the current-fresh cohort. Phase 9H verification found 2,431 current-fresh
companies as of 2026-09-06 using `ttm_source_available_date` and a maximum age
of 180 calendar days. This terminology correction does not change the complete
diagnostic history or any economic result. Snapshot checks produced CRMD 1.9700%, APD
1.8119%, NVDA 9.0264%, active AGEN 11.4504%, not-applicable AAT, and not-ready
BNC. Reader evidence and Markdown status matched.

## Safety

Production databases and existing `fundamental_reports` were not modified.
The only sidecar difference was a byte-identical taxonomy SHM mtime update from
read-only SQLite access. Phase 9G does not deploy or activate the correction.

Verification passed 11 focused Phase 9G tests, all 741 Fundamentals V4/UI
tests, 79 final activation/snapshot regressions, compileall, and
`git diff --check`. Ruff was unavailable and was not installed. The complete
repository suite was not run because the change does not touch shared
infrastructure outside Fundamentals V4.
