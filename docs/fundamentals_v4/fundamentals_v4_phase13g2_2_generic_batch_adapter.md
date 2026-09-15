# Phase 13G.2.2 Generic Batch Add Tickers Adapter

Date: 2026-09-15

Outcome: `OUTCOME B — CORRECTABLE SOURCE, IDENTITY, ELIGIBILITY OR IMPLEMENTATION LIMITATION REMAINS; PRODUCTION UNCHANGED`

Reason: the generic copy-only adapter and acceptance lanes completed successfully, but the repository-wide full-suite gate finished red with two failures outside the Phase 13G.2.2 implementation surface. A production handoff should wait for that suite to be green.

## Implementation

Phase 13G.2.2 replaces the Phase 13G.2 authoritative-downstream gap with a generic copy-only Add Tickers adapter.

The adapter now builds an immutable per-batch plan from:

- canonical identity evidence;
- Sharadar `fundamentals` metadata, with non-fundamentals metadata rows ignored for identity ambiguity;
- current US market evidence;
- `data/osakedata.db.ticker_meta` sector/industry under `CURRENT_REVISED_NON_PIT_CLASSIFICATION`;
- existing provider rows, verified local archive rows, or bounded Sharadar network rows when `--allow-network` is set.

The saved plan drives preview, apply, replay and durable reporting. It does not store API secrets or authenticated URLs.

Generic apply on production-shaped copies now:

1. persists canonical company/security/alias/provider identity rows for every accepted ticker;
2. stages Sharadar fundamentals for all accepted tickers before downstream refresh;
3. rebuilds canonical quarters and TTM;
4. applies the structural contract;
5. updates current revised classification where applicable;
6. runs Operating-Income V2 once per accepted batch;
7. runs full-universe Relative Position once per accepted batch;
8. runs full-universe Relative Valuation once per accepted batch;
9. attaches dependencies;
10. generates eligible Snapshot smoke reports.

The old Phase 13D compatibility fallback remains only for lightweight test fixtures that do not contain the production provider schema.

## Acceptance Evidence

Public durable ARM apply:

- Preview run: `20260915T094004Z_add_tickers_0b6029d1d9b0`
- Apply run: `20260915T094057Z_add_tickers_00871354efca_apply`
- Outcome: `COMPLETED`
- Applied: `ARM`
- Invocation counts: package `1`, Relative Position `1`, Relative Valuation `1`

Retained-lane acceptance summaries:

- Lane 1: `fundamental_reports/admin_runs/phase13g2_2_acceptance/lane1_acceptance_summary.json`
- Lane 2: `fundamental_reports/admin_runs/phase13g2_2_acceptance/lane2_acceptance_summary.json`
- Replay economic fingerprint: `58537b24927a2bc334a481ab11aa5d028676fea4b28100feef1217397cf06280`

Lane 1 and Lane 2 matched exactly on economic fingerprints:

- `ARM` apply: `APPLIED`, accepted `ARM`, package/RP/RV `1/1/1`
- `ARM` repeat: `NO_CHANGE`, package/RP/RV `0/0/0`
- ten-ticker apply: `APPLIED`, accepted `AG ALOY ASML ASX BABA BHP BIDU BTDR CAMT`; `ARM` was already present
- ten-ticker repeat: `NO_CHANGE`, package/RP/RV `0/0/0`

The ten-ticker request did not silently correct `ALOY`; it was resolved and accepted as requested.

Key deterministic fingerprints:

- ARM package economic: `73971b35ca92efb89cf4907df37f6c5f3f6e3d262f1fc50e3a0771c6a5bcd176`
- ARM Relative Position result: `4901f361fc1ead2af3a3d2f0419e482165f0f7afd182f9c08351401609d296a2`
- ARM Relative Valuation result: `f17956274f69270abe4dde0c69bee26b50d7b5499ebc2610f4a7e21a9586093c`
- Ten-ticker package economic: `bff4596b0a41214a8abf7137eedee25a69904a4ca1545ecbc44121e9206d7df0`
- Ten-ticker Relative Position result: `ba3be324ad9f164f3557e1008dda4f5458734fc047ec79ea7787383af5985b28`
- Ten-ticker Relative Valuation result: `9bededf06fbeb8542cb89b6d68a6c16947b1f03cddaf5148f1b5d767d11808ea`

Rollback lane:

- Evidence: `fundamental_reports/admin_runs/phase13g2_2_acceptance/rollback_summary.json`
- Injected error: `PHASE13G2_INJECTED_AFTER_IDENTITY`
- Partial ARM security rows before restore: `1`
- ARM security rows after restore: `0`
- Restored to baseline: `true`

## Production Safety

Production writes were prohibited and not performed.

Runtime postflight after acceptance:

- analysis `PRAGMA quick_check`: `ok`
- active package: `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- active Relative Valuation snapshot: `1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b`
- production ARM security rows: `0`

Copy database files, WAL, SHM and journal files were removed after acceptance. Final `/tmp/phase13g22_accept` size was approximately `1.6M`; filesystem free space remained approximately `599G`.

## Tests

Focused tests:

```text
python3 -m pytest tests/test_fundamentals_admin_batch_add_tickers.py
13 passed
```

Additional compile check:

```text
python3 -m compileall rawcandle/fundamentals/admin/batch_add_tickers.py rawcandle/cli/run_fundamentals_admin_add_tickers.py
```

Full repository suite:

```text
python3 -m pytest > fundamental_reports/admin_runs/phase13g2_2_acceptance/full_suite.log 2>&1
2991 passed, 2 failed, 14 deselected, 8 warnings
exit_code=1
```

The two failures were:

- `tests/test_fundamentals_v4_company_snapshot_phase9f.py::test_v2_report_formats_values_and_restores_context`
- `tests/test_phase13f3_ticker_transition.py::test_enhanced_listing_population_resolves_former_transition_tickers`

Focused Phase 13G.2.2 and Phase 13D/13F regression tests passed; the full-suite failure keeps this phase from being a production-deployment handoff.
