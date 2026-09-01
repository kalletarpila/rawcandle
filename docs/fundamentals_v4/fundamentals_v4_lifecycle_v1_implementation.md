# Fundamentals V4 Lifecycle V1 Pure Engine Implementation

## Phase result

Phase 2A implements the locked Lifecycle V1 methodology as a pure deterministic Python package. It is not production-active and creates no lifecycle rows.

## Files and API

- `rawcandle/fundamentals/lifecycle/engine.py` defines the model contract, enums, immutable input/output dataclasses, raw classifier, one-step state transition and deterministic replay.
- `rawcandle/fundamentals/lifecycle/__init__.py` exposes the public pure API.
- `tests/test_fundamentals_v4_lifecycle_engine.py` covers exact priority, boundaries, missing inputs, invalid values and state-machine behavior.
- `docs/fundamentals_v4/fundamentals_v4_lifecycle_v1_specification.md` is the active methodology specification.

Public entry points:

```python
classify_raw_state(observation) -> RawLifecycleResult
advance_state_machine(state, raw_result) -> (LifecycleMachineState, StateMachineResult)
replay_state_machine(raw_results) -> tuple[StateMachineResult, ...]
```

All input, machine-state and output dataclasses are frozen. The module imports neither Score nor SwingMaster and contains no SQLite, network, persistence or filesystem operation.

## Model identity

```text
model_version = V4_FUNDAMENTAL_LIFECYCLE_V1
model_fingerprint = db72e072fc2f0d9e3ceb13db1ee4cc92045383a5f44bfb65d21858b80190832f
input_ttm_model_version = V4_TTM_EBIT_FIRST_V1
```

The SHA-256 fingerprint covers public classes/statuses, exact priority, thresholds, PRE_REVENUE contract, state-machine policy and excluded input families.

## Fiscal and PIT mapping

`LifecycleObservation` receives the existing V4 identities and TTM values rather than querying a database. `endpoint_fiscal_year` and `endpoint_fiscal_quarter` identify the economic period; `endpoint_quarter_id` is the stable canonical endpoint; `lag4_chain_valid` records that the caller used the canonical fiscal chain rather than row offsets or calendar subtraction. `source_available_date` orders PIT replay, while `source_data_version` can identify the provider/canonical vintage in the future persistence phase.

The pure replay validates non-decreasing ISO availability dates. It does not sort or mutate inputs because equal-date event tie-breaking belongs to the future PIT event builder. Later restatements therefore become new ordered observations rather than rewrites of prior result objects.

## Numerical behavior

Input values are finite-checked before use. Rule metrics follow the locked formulas. Decimal comparisons are calculated from source-number string representations to preserve exact `>`, `>=`, `<` and `<=` semantics at economic thresholds. Public metric evidence remains unrounded numeric output. PRE_REVENUE never divides by zero.

## Missing-rule evaluation

Each rule evaluates only when its own required metrics are valid. This is material for missing FCF: SCALING, GROWTH and DECLINING can still classify when complete, but TRANSITION cannot. DISTRESSED can classify before lag4 validation because lag4 is not one of its inputs. No current or historical metric is inferred or imputed.

## State output semantics

For a ready economic observation, `final_state` is the current confirmed public state and may differ from `raw_state` while a candidate awaits confirmation. For UNCLASSIFIED, `final_state` is always `None`, status is `LIFECYCLE_NOT_READY`, and `last_confirmed_state` is exposed only as historical machine context. Candidate state is cleared.

Startup profile is retained with a confirmed STARTUP state. A stable confirmed STARTUP observation updates its current startup profile; a candidate STARTUP profile becomes confirmed only with the state transition.

## Deferred production boundary

Phase 2A deliberately does not provide a database loader, writer, migration, CLI, backfill or activation path. The next PIT persistence phase owns:

- canonical TTM and exact four-quarter input loading;
- immutable availability/version event identity;
- same-date deterministic tie-breaking;
- append-only PIT result persistence;
- revised-history replay separation;
- production rehearsal, idempotency and activation controls.

The existing `lifecycle_result` schema was not changed or written in this phase. Its suitability for immutable PIT event versions must be reviewed before persistence is implemented.
