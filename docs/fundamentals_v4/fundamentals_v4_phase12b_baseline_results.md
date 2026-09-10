# Fundamentals V4 Phase 12B Baseline Results

## Outcome

**OUTCOME C - NO RELIABLE BASELINE SIGNAL; DO NOT PROCEED TO ML.**

Phase 12B implemented the locked
`PHASE12B_REVISED_HISTORY_FUNDAMENTAL_PROFILE_BASELINE_V1` research framework.
The contract fingerprint is
`26a2826841ca024aa40682a3160df4fcff83cd2af1e3cbe9cccbb401f7201139`,
locked in commit `5c92a42` before the result runs.

The feature history is currently revised and was reconstructed from a provider
snapshot obtained in 2026. It is not original point-in-time history. Results
describe retrospective associations and cannot establish real-time historical
investability.

## Blocking finding

The locked primary common cohort requires full Score, Valuation, two-quarter
Delta, Lifecycle and Diagnostic inputs plus a valid 63-session label. After the
locked period-end purge, the 2021-2023 development cohort contains only:

- 70 observations;
- 68 companies;
- 3 signal months.

This fails the preregistered 200 observations, 100 companies and 12 months
gate. The common profile becomes broadly available only late in the development
period, and the 63-session purge removes most of that tail. Models B0-B4 were
calculated and serialized for diagnostic transparency, but they are marked
`NOT_TESTABLE_DEVELOPMENT_SAMPLE_GATE_FAILED`. They are not validation evidence.
All H1-H8 hypotheses are therefore `NOT_TESTABLE_WITH_CURRENT_DATA`.

## Samples And Labels

The retained primary common-cohort counts are:

| Period | Rows |
|---|---:|
| DEVELOPMENT, 2021-2023 | 70 |
| TEMPORAL_VALIDATION, 2024 | 3,873 |
| RETROSPECTIVE_CONFIRMATION, 2025 | 3,953 |
| FORWARD_REPORT_ONLY, matured 2026 | 1,835 |

Current session-zero label coverage is 48,967 at 21 sessions, 47,427 at 42
sessions and 47,268 at 63 sessions from 50,585 endpoints. At 63 sessions there
are 136 missing exact exits, 59 insufficient-coverage cases, 585 missing entry
prices, 258 unresolved identities and 2,279 labels that have not matured.

The complete-case result remains conditional on the security being observable
at the exact exit. Neutral and severe missing-exit bounds are audit views only;
they never enter model fitting.

## Reconciliation

Endpoint count and 258 unresolved identities reconcile. Canonical, provider
and Fundamentals analysis database hashes are byte-identical to Phase 12A.
The market database changed after Phase 12A:

- Phase 12A `osakedata.db` hash:
  `0ed1ed6b737c7e7f1ec44a09bb743317154212a28870f9f4c20bf8df46ca700b`;
- Phase 12B input hash:
  `38078094058004539dcb155df8b4172cb6822dc20c465c02cd7468710a1d1cdd`.

The Phase 12A reference counts and exact current-source recalculation are both
retained in `source_reconciliation.json`. The accepted reconciliation status
is `PASSED_WITH_DOCUMENTED_MARKET_AND_NONPREDICTOR_TAXONOMY_DRIFT`; no result
tolerance was widened.

The current classification/taxonomy `analysis.db` was checkpointed by an
external process during a later replay. It is not a Phase 12B predictor. The
accepted replay fingerprints its stable post-checkpoint bytes and reports the
drift separately as non-PIT descriptive context.

## Determinism And Safety

Two complete runs produced 41 byte-identical artifacts. Identities:

- source: `d35d68069707477913269e4c7e4febb10f84f3a5c1d09b174e5329357942e59c`;
- contract: `26a2826841ca024aa40682a3160df4fcff83cd2af1e3cbe9cccbb401f7201139`;
- sample: `f6426c1e09ea9467302230ccba95dbf06f589a2a62f307f34f966fb5734c98cd`;
- result: `83c4c58573253e30bf6ae9aa9b28879de8fc5896f072798929669282c087df06`.

Accepted artifacts are under
`temp/fundamentals_v4_phase12b/20260910T_PHASE12B_ACCEPTED_B/`; the independent
replay is `20260910T_PHASE12B_ACCEPTED_C/`. Preflight and postflight production
state fingerprints are identical. No database, production report, active
package, Relative Valuation snapshot, Snapshot contract or Scheduler path was
changed.

## Next Phase

Do not expand to an ML candidate from this result. Start the separately scoped
prospective PIT collection phase described in
`prospective_pit_collection_recommendation.md`. A future baseline may be
preregistered after enough genuinely prospective observations cover a usable
development interval. Do not redefine the current periods after seeing this
coverage failure.

## Verification

Focused command:

```text
pytest -q tests/test_phase12b_research_contract.py tests/test_phase12b_fundamental_profile_baseline.py
```

Result: 27 passed.

Relevant broad command:

```text
pytest -q tests/test_fundamentals_v4*.py tests/test_phase12b_research_contract.py tests/test_phase12b_fundamental_profile_baseline.py <market/alias/corporate-action isolation tests>
```

Result: 840 passed, one existing data-coupled test failed. The failure expects a
hard-coded latest report price date of 2026-09-08, while the updated read-only
market database now returns 2026-09-09. Phase 12B does not change that test or
the Company Snapshot implementation. `compileall` and `git diff --check` pass.
