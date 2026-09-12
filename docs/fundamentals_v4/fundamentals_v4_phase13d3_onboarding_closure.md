# Fundamentals V4 Phase 13D.3 Onboarding Closure

Phase 13D.3 is a copy-only closure pass for the SNDK/AREB onboarding rehearsal. It does not authorize production writes, pointer changes, Scheduler changes, report publication, or network access.

## Corrections

- The active test suite now excludes only tests explicitly marked `retired_v3`. The retired set is the 14 real-CSV tests that require `temp/v3_active_tickers_99_27.csv`. Synthetic V4 identity-calendar bootstrap tests remain active.
- Snapshot report determinism separates `source_state_audit` from rendered `source_state`. Run-local audit fields remain machine-readable but are excluded from the rendered report source-state fingerprint.
- SNDK and SNDK1 remain distinct securities with corporate lineage. SNDK uses permaticker `643888`; SNDK1 uses permaticker `197210`.
- AREB taxonomy membership must not be invented. Local evidence currently identifies AREB as `AMERICAN REBEL HOLDINGS INC`, but local `ticker_meta` classifies it as `Consumer Cyclical / Footwear & Accessories`, not the expected `Industrials / Commercial Services & Supplies`. Until that classification source is reconciled, the correct D13D.3 closure status is review required, not an activated membership.

## Artifacts

Run:

```bash
python3 -m rawcandle.cli.run_phase13d3_onboarding_closure \
  --output temp/fundamentals_v4_phase13d3_onboarding_closure/20260912T_PHASE13D3_CLOSURE
```

The run writes the requested D13D.3 artifacts, including production pre/postflight inventories, D13D.2 evidence audit, active/retired test manifests, AREB/SNDK reconciliation, Snapshot nondeterminism root cause, rollback smoke evidence, corrected batch rehearsal output, storage manifest, and command log.

## Outcome Rule

Outcome A is available only when SNDK is ready, Snapshot determinism is stable, rollback evidence is complete, active tests pass, production is immutable, and AREB classification/taxonomy handling is no longer ambiguous. If AREB remains locally classification-mismatched, Phase 13E must stay blocked for batch AREB+SNDK production onboarding; a narrower SNDK-only production plan still requires protected confirmation and complete rollback evidence.
