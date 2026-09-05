# Phase 6B implementation and rehearsal

## Implementation

Phase 6B adds a pure immutable engine, read-only canonical/analysis adapter, deterministic rehearsal runner and safe CLI. There is no production schema, write repository, migration, backfill, pipeline integration, aggregate score, severity, event classifier, or provider update.

The adapter reads canonical TTM and Phase 6A.2 balance fields from the migrated rehearsal copy, and reads persisted Score Trajectory, Lifecycle and Absolute Valuation results from production analysis in SQLite `mode=ro` with `query_only=ON`. It resolves an exact fiscal predecessor and rejects chronology reversals. Arbitrary `payload_json` is not read.

## Rehearsal

Final artifacts:

`temp/fundamentals_v4_diagnostic_flags_phase6b/20260905T190000Z/`

The two independent 50,585-endpoint runs each emitted 354,095 normalized evaluations. Their output was byte-identical.

- Source fingerprint: `6c0ef9696386e8c9e47856d5e61ab4456dea4f6b05a6982f7a87c76e87c9dfe3`
- Replay SHA-256: `0e33b3647055a8c6a3c1095380ee3fe5211d46fb9e5ea6e4ba0662a4ccb8e410`
- Result fingerprint: `13b53055cb5d33886604d05d55d11c7136ab1f213c596eabaac28892804e1eb7`
- Current snapshot: as of 2026-09-02, maximum age 180 days, 2,441 companies

| Flag | Evaluated | Flagged | Flag rate |
|---|---:|---:|---:|
| Abrupt fundamental shift | 2,097 | 282 | 13.45% |
| Earnings/cash divergence | 2,097 | 239 | 11.40% |
| CAPEX intensity shift | 2,097 | 74 | 3.53% |
| Net debt shift | 2,097 | 169 | 8.06% |
| Valuation yield outlier | 2,245 | 36 | 1.60% |
| Recent margin deceleration | 2,062 | 22 | 1.07% |
| Working capital shift | 2,296 | 51 | 2.22% |

For the common 2,097-company operating cohort, 1,664 had zero flags, 174 exactly one, 124 exactly two, and 135 at least three. At least one flag occurred for 433 companies, or 20.65%. The maximum was five. The union is below the 50% review blocker.

The largest overlap is abrupt shift with earnings/cash divergence: 192 shared, Jaccard 0.584. This mirrors Phase 6A and is economically understandable because large income-statement changes can affect both tests, while the underlying questions and evidence remain distinct.

## Anchor reconciliation

Valuation (36) and working capital (51) exactly reproduce the research flag counts. Working-capital evaluated coverage changes from 2,297 to 2,296 because Phase 6A.2 rejects zero/negative assets strictly.

The four revenue-scaled counts are lower than Phase 6A because Phase 6B applies the existing unsupported accounting-class classification before evaluation and requires an exact valid fiscal chain. CAPEX falls from 112 to 74 principally because the research population included unsupported accounting classes where CAPEX concentration was known to be high. Margin moves from 23 to 22 and 2,198 to 2,062 for the same applicability tightening plus flag-specific missing Trajectory/input readiness. Formulas and thresholds were not changed to force anchor counts.

## CRMD and APD

CRMD is flagged for valuation yield outlier and recent margin deceleration. Its working-capital metric is 0.0197001 and clear. APD is flagged for abrupt fundamental shift and earnings/cash divergence. Its working-capital metric is 0.0181191 and clear.

The Phase 6A.1 detailed tables contain these same 1.97% and 1.81% calculations, while their concluding prose says 3.93% and 5.93%. The latter statements are documentation errors inconsistent with both the locked ONWC/assets formula and the artifact's own scalar rows. No threshold or formula was altered. `ncfbus`, impairment, acquisition and project-exit explanations are not engine inputs or outputs.

## Validation and Phase 6C

Synthetic boundary tests cover below, exact and above behavior for every inclusive operator. No current real observation lands exactly on a threshold; deterministic nearest-below/above samples are in `flag_boundary_samples.csv`.

The largest safe Phase 6C scope is additive normalized persistence for one immutable result header per endpoint/model and one child row per flag, with scalar evidence stored in normalized fields. It may consume only this engine output, preserve statuses and reason codes, be idempotent and transactional, and add no economic logic. Production migration, backfill and activation require separate authorization.

Phase 6B does not deploy the model.
