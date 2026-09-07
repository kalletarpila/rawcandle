# Company Snapshot V2 Phase 9I

Status: `COMPLETE_REPORTING_TRANSPARENCY_ONLY`

## Scope and display contract

Phase 9I changes only Company Snapshot V2 assembly, reconciliation and Markdown
presentation. It does not change a valuation formula, anchor, weight, readiness
rule, canonical/TTM value, persisted result, production database or active
package manifest.

The presentation contract changes from
`CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V2` to
`CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V3`. The established ten
metrics and their order remain unchanged. The two renamed labels are:

| Prior label | V3 label |
|---|---|
| P/E | P/E (Reported Common Earnings) |
| Earnings Yield | Reported Common Earnings Yield |

All other common-earnings labels now use `Reported Common Earnings`. The report
contains one nearby note stating that this is a GAAP-based common-shareholder
measure, may contain recognized non-operating items, and is not normalized.

## Economic and time contract

The authoritative source chain is `Sharadar netinccmn -> canonical
net_income_common -> ttm_net_income_common -> reported common-earnings valuation`.
No normalized, adjusted, sustainable or recurring earnings value is calculated.
RawCandle produces no investment-gain adjustment.

The unchanged formulas are:

```text
Reported Common Earnings Yield = ttm_net_income_common / market_cap
P / Reported Common Earnings = market_cap / ttm_net_income_common
market_cap = selected_price * compatible shares_outstanding
```

Calculations use stored binary64 values without pre-rounding. Missing required
input renders `N/A`. Zero or negative reported common earnings make the ratio or
multiple economically non-meaningful and render `N/M`; the signed TTM amount is
still visible in Valuation basis.

The three contexts remain:

| Context | Fundamentals | Price |
|---|---|---|
| Current moment | latest eligible TTM | latest eligible current close |
| Latest endpoint (availability date) | same latest TTM | that endpoint's availability-date price |
| Previous endpoint (exact Q-1 availability date) | exact fiscal Q-1 TTM | exact Q-1 availability-date price |

There is no substitute when exact fiscal Q-1 is unavailable. Valuation basis
shows fiscal year/quarter, TTM period end, source availability date,
price date, price, shares, calculated market cap and Reported Common Earnings
TTM for every context. Currency remains `N/A` because no validated currency
field belongs to the report contract.

Phase 9J clarified that this is RawCandle's source-availability date, not an
automatic claim about a legally verified filing timestamp. It did not alter the
date values or selection logic.

Operating measures retain explicit Operating Income terminology. Reported
Common Earnings affect only the 20-point common-earnings portion of Absolute
Valuation Score V2 and related displayed ratios. They do not directly affect
Fundamental Score V2. Operating Income and reported FCF remain separate.

## Fingerprints

| Identity | Prior | Phase 9I | Decision |
|---|---|---|---|
| Snapshot economic | `1b4963c3b968008dd753d86c9a95c5f21737956113ea5c70f481b2ee96757f64` | unchanged | no economic change |
| Presentation | `bc4b4a3b355063697f1fe3182a105342d804a59bb41a86ec40ef6fe4364abee2` | `e9660690c9ccedc2936c14d8b5d2bb3abc7d62f0d10f11a75d349f770f7fe779` | fields, labels and Markdown changed |
| Active package | `a36d6903c3d640da5e9bd7034faee700b7b064e74ea871880c1bfa2348f4964d` | unchanged | presentation is not package economics |
| Per-report content | report-specific | changed | deterministic rendered bytes changed |

The active package does not store or require the presentation fingerprint, so
the CLI and UI remain coherent without a production activation. V2 and archived
package readers are unchanged.

## Reconciliation evidence

Every context now carries deterministic checks for the authoritative
`ttm_net_income_common`, price-times-shares market cap, persisted/current engine
market cap where available, earnings yield and reciprocal multiple. Comparisons
use full precision with relative and absolute tolerance `1e-12`; any failed
check aborts Snapshot assembly.

NVDA's latest local endpoint is FY2027 Q2, TTM period end 2026-07-26 and
availability date 2026-08-26. Authoritative Reported Common Earnings TTM is
`192879000000`, not a hardcoded estimate. Current uses price
`230.36000061035156` dated 2026-09-04 and market cap
`5551676014709.473`, yielding `0.03474248127753789` and `28.783206127725013x`.
The latest availability-date endpoint uses price `209.66000366210938` dated 2026-08-26 and market cap
`5052806088256.836`, yielding `0.038172650331519294` and
`26.196766305594885x`. The TTM numerator is identical; only price and market cap
differ. Exact Q-1 is FY2027 Q1, period end 2026-04-26, with its own TTM amount
`159613000000` and price date 2026-05-20. No USD 167.522 billion or other
investment-gain-adjusted estimate appears.

## Edge-case evidence

Temporary deterministic reports are under
`temp/fundamentals_v4_company_snapshot_phase9i/reports/`:

| Company | Evidence |
|---|---|
| NVDA | material reported non-operating items; three contexts reconcile |
| CRMD | current reported earnings yield `0.28485843013706236`; valid ceiling case |
| APD | TTM amount `-47300000` remains visible; yield and P/E are `N/M` |
| AIV | missing current TTM common earnings renders `N/A`, not zero |
| OXY | TTM net income `7254000000` differs from common earnings `6575000000`; report uses the latter |
| LEG | 2026-08-27 current price is 11 days old; current valuation is `VALUATION_NOT_READY` and ratios are `N/A` |
| AAT | `VALUATION_NOT_APPLICABLE` / `UNSUPPORTED_REIT_MODEL` remains explicit |

Synthetic boundary coverage additionally verifies exactly zero common earnings
as `N/M`, negative amounts as signed values with `N/M`, and missing common
earnings as `N/A`. Exact Q-1 selection, no internal database IDs, no external
filing value and no adjusted estimate are asserted. OXY provides a valid current
universe case where `ttm_net_income` and `ttm_net_income_common` differ.

V3 report-content fingerprints are NVDA `1be7146b...`, CRMD `c401191d...`, APD
`798278a8...`, AIV `38364e70...`, OXY `369c26b7...`, LEG `30d8b5d3...` and AAT
`1dd60eba...`. A repeated generation produces `NO_CHANGE` and the same content
fingerprint.

## UI, safety and limitations

The existing UI service remains unchanged. Tests preserve multi-ticker parsing,
input order, duplicate removal, partial success, overwrite protection, recent
reports, secure download and traversal/symlink rejection. All Phase 9I examples
were written only below `temp`; files in `fundamental_reports` were not
overwritten.

Preflight source hashes were canonical `f553639e...`, analysis `ea61ea95...`,
market `be956361...`, taxonomy `c95f9b16...` and provider `1905d09c...`.
The aggregate existing-production-report hash was `cc658c23...`. Postflight
matched every hash, file size and main-database mtime exactly. The active package
remained `a36d6903...` with activation time `20260907T102623Z`;
`quick_check=ok` and the foreign-key check was empty. No provider update,
canonical/TTM rebuild, schema migration, production write or package activation
occurred.

Focused Snapshot/UI tests passed `109/109`; the broader Valuation, V2 package,
Snapshot, UI and Scheduler group passed `377/377`; and the complete Fundamentals
V4 plus relevant UI/CLI group passed `937/937` in 89.63 seconds. `compileall` and
`git diff --check` passed. The complete repository suite was not run because no
shared infrastructure outside Fundamentals V4 Snapshot reporting changed, as
allowed by the Phase 9I test policy. No optional tool was installed.

The report remains currently revised rather than PIT. Reported Common Earnings
remain unnormalized GAAP earnings, and current-price valuation continues to use
the latest endpoint's shares and balance sheet. A current descriptive multiple can
be calculable while the model status is `VALUATION_NOT_APPLICABLE`; the status
is displayed separately and is not converted into readiness or model eligibility.

## Phase 9J presentation follow-up

Phase 9J introduced presentation contract V4. It replaced ambiguous filing-date
labels with source-availability terminology, identified Valuation comparison
values as score-point changes, rendered readable diagnostic explanations, and
moved package identities from the opening summary to the technical appendix.
The Phase 9I economic contract and all values documented above remain unchanged.
