# Phase 13G.2.4 Protected Batch Add Tickers Production Deployment

Date: 2026-09-15

Outcome: `OUTCOME A - BATCH ADD TICKERS ACTIVE AND STABLE IN PRODUCTION`

Implementation commit: `6d3ca32385a27b55a2aa6943c1a3b5ed50e2a852`

Production run:

- Run ID: `20260915T155830Z_add_tickers_91f5674ef226_production`
- Evidence: `fundamental_reports/admin_runs/20260915T155830Z_add_tickers_91f5674ef226_production`
- Preview payload: `fundamental_reports/admin_runs/20260915T152833Z_add_tickers_65f32b9a5201/phase13d_preview_payload.json`
- Preview fingerprint: `a0a937069657ff8f6b7df9851488aa68d2fe28f41e9f7ef3f4dd97ae34feb0fb`

## Authorized Batch

The production apply processed exactly one batch:

`AG ALOY ARM ASML ASX BABA BHP BIDU BTDR CAMT`

All ten tickers were accepted from verified local archive data. Network access was disabled.

## Prewrite Evidence

The worktree was clean at implementation commit `6d3ca32`. Required baseline commits were ancestors of HEAD:

- `5651286`
- `3170b3ed591c10c67bfd01246448fe46f11c8066`
- `6704ed042d67b9ddce57c9bc19ce558fbd463d2f`

Runtime preflight confirmed exact configured production paths, no writable SQLite sidecars, successful integrity checks, sufficient disk space, and the retained active identities:

- Operating-Income package: `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- Relative Valuation model: `76c2974108b2c5085b7dfa102acd4bb04eea36a5267bbdb1930a2bc7dc8cb35e`
- Relative Valuation snapshot: `1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b`
- Relative Valuation result: `9c642e80b06fdbb8c6e703a46a6bda2c7031bc270fbd195b0a3acd7cdeba30f3`

Two fresh all-ten production-shaped copy candidates matched each other:

- Provider rows staged: `1808`
- Package economic fingerprint: `8b895b36bffc6be864c0f7f1bf32652155f08b8ce32ae89b8006a4a50c0ebb47`
- Relative Position result: `1ce3fbc772ef2c1c38f28776b8d4903542c22c2fa29ef725e04da0756d407fd3`
- Relative Valuation result: `07134cf7346b7535779a93f5aa56196c59a49093b4880c220a24c5d2ab11a428`

The retained Phase 13G.2.2 ten-ticker fingerprint differed because that evidence applied ARM first and then accepted nine more tickers. The fresh production-shaped run staged all ten together. The row delta reconciled exactly: retained ten-step provider rows `1717` plus retained ARM rows `91` equals all-ten provider rows `1808`.

## Backups

Fresh verified production backups were retained under:

`backups/fundamentals_v4_phase13g2_4_batch_add_tickers/20260915T155830Z_add_tickers_91f5674ef226_production`

Backup SHA-256 values:

- provider: `cc542c137c76f6eaafdc74c8c7dd1d857b23af17f73e00a4fec523ffc0cd0102`
- canonical: `0d4a80ff2707c0b9e8b287b958534e28a349cd1f7a3854936f4d60ae4672bbb4`
- analysis: `21d3a166e5a22d66412372d337e6e8c681bf09f5069311db317e86f12c51719c`

The complete backup set was restored to rehearsal paths, verified, and the rehearsal database copies were removed. The retained backup set size is approximately `3.0G`.

## Production Result

First apply:

- Accepted tickers: `AG ALOY ARM ASML ASX BABA BHP BIDU BTDR CAMT`
- Provider rows staged: `1808`
- Canonical rows present after apply: AG `41`, ALOY `41`, ARM `13`, ASML `41`, ASX `35`, BABA `41`, BHP `19`, BIDU `41`, BTDR `22`, CAMT `41`
- TTM rows present after apply: AG `41`, ALOY `41`, ARM `13`, ASML `41`, ASX `35`, BABA `41`, BHP `19`, BIDU `41`, BTDR `22`, CAMT `41`
- Operational-universe rows: `1` per ticker
- Package/RP/RV invocation counts: `1/1/1`
- Package economic fingerprint: `8b895b36bffc6be864c0f7f1bf32652155f08b8ce32ae89b8006a4a50c0ebb47`
- Relative Position result: `1ce3fbc772ef2c1c38f28776b8d4903542c22c2fa29ef725e04da0756d407fd3`
- Relative Valuation result: `07134cf7346b7535779a93f5aa56196c59a49093b4880c220a24c5d2ab11a428`
- Active Relative Valuation snapshot: `1245d2deb9d92ee897bd8df3049f6419777f92874bcac7f145bcb4b55015e082`

Second identical apply:

- Outcome: `NO_CHANGE`
- Package/RP/RV invocation counts: `0/0/0`
- Blocking database content differences: `0`

Snapshot smoke:

- Created: `AG ALOY ARM ASML ASX BABA BIDU BTDR CAMT NVDA`
- Explicit readiness limitation: `BHP` (`NO_FUNDAMENTAL_ENDPOINT_ON_OR_BEFORE_REPORT_DATE:BHP:2026-09-12`)

Post-success integrity:

- `quick_check=ok` for provider, canonical, analysis, market and taxonomy
- Foreign-key errors: `0` for all five databases
- Writable production sidecars: none for provider, canonical or analysis
- Maintenance lock released

## Tests

Focused tests after implementation:

```text
pytest tests/test_fundamentals_admin_batch_add_tickers.py tests/test_fundamentals_admin_progress.py
25 passed in 120.43s
```

Full repository suite after production apply:

```text
3005 passed, 14 deselected, 8 warnings in 880.06s (0:14:40)
exit_code=0
```

Full-suite evidence:

- `fundamental_reports/admin_runs/20260915T155830Z_add_tickers_91f5674ef226_production/full_suite_rerun/full_suite.log`
- `fundamental_reports/admin_runs/20260915T155830Z_add_tickers_91f5674ef226_production/full_suite_rerun/heartbeat.jsonl`
- `fundamental_reports/admin_runs/20260915T155830Z_add_tickers_91f5674ef226_production/full_suite_rerun/exit_code`
- `fundamental_reports/admin_runs/20260915T155830Z_add_tickers_91f5674ef226_production/full_suite_rerun/summary.json`

## Disk Hygiene

Phase-owned copy lanes and restore-rehearsal databases were removed. The verified production backup set was retained. Phase-owned pytest fixture trees `/tmp/pytest-of-kalle/pytest-114`, `/tmp/pytest-of-kalle/pytest-115`, `/tmp/pytest-of-kalle/pytest-116`, and `/tmp/pytest-of-kalle/pytest-current` were removed.

Final free space was approximately `596G` on `/home/kalle/projects/rawcandle` and `/tmp`.

No push was performed.
