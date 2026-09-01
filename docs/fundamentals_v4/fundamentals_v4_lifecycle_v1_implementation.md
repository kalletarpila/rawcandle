# Fundamentals V4 Lifecycle V1 Implementation

## Phase result

Phase 2A implements the locked methodology as a pure deterministic engine. Phase 2C adds a production-capable but unactivated revised-history adapter, persistence layer, readers and guarded CLI. Production remains unchanged until separately authorized Phase 2D.

## Files and API

- `rawcandle/fundamentals/lifecycle/engine.py` defines the model contract, enums, immutable input/output dataclasses, raw classifier, one-step state transition and deterministic replay.
- `rawcandle/fundamentals/lifecycle/revised_history.py` maps current canonical/TTM data to engine observations, replays companies in fiscal order and owns revised-history persistence and readers.
- `rawcandle/cli/run_fundamentals_v4_lifecycle_revised.py` is dry-run by default, requires explicit scope and destination, and blocks the production analysis database in Phase 2C.
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

## Fiscal and source mapping

`LifecycleObservation` receives the existing V4 identities and TTM values rather than querying a database. `endpoint_fiscal_year` and `endpoint_fiscal_quarter` identify the economic period; `endpoint_quarter_id` is the stable canonical endpoint; `lag4_chain_valid` records that the caller used the canonical fiscal chain rather than row offsets or calendar subtraction. `source_available_date` remains required source provenance and readiness evidence, while `source_data_version` can identify the currently accepted provider/canonical input.

The pure replay validates the caller-provided non-decreasing availability sequence and never sorts or mutates its inputs. This validation remains part of the Phase 2A pure contract. It does not imply that RawCandle preserves every historical information version.

## Numerical behavior

Input values are finite-checked before use. Rule metrics follow the locked formulas. Decimal comparisons are calculated from source-number string representations to preserve exact `>`, `>=`, `<` and `<=` semantics at economic thresholds. Public metric evidence remains unrounded numeric output. PRE_REVENUE never divides by zero.

## Missing-rule evaluation

Each rule evaluates only when its own required metrics are valid. This is material for missing FCF: SCALING, GROWTH and DECLINING can still classify when complete, but TRANSITION cannot. DISTRESSED can classify before lag4 validation because lag4 is not one of its inputs. No current or historical metric is inferred or imputed.

## State output semantics

For a ready economic observation, `final_state` is the current confirmed public state and may differ from `raw_state` while a candidate awaits confirmation. For UNCLASSIFIED, `final_state` is always `None`, status is `LIFECYCLE_NOT_READY`, and `last_confirmed_state` is exposed only as historical machine context. Candidate state is cleared.

Startup profile is retained with a confirmed STARTUP state. A stable confirmed STARTUP observation updates its current startup profile; a candidate STARTUP profile becomes confirmed only with the state transition.

## Revised-history direction

The unactivated Phase 2B PIT persistence experiment was removed from the active codebase in Phase 2B.1. No historical PIT lifecycle dataset is claimed. Git history retains the retired experiment, but there is no active PIT schema, repository, reader, writer or CLI.

Phase 2C implements a small deterministic `REVISED_HISTORY` solution based on the currently accepted canonical and TTM history. It replays observations in canonical fiscal-quarter order and answers: "What does the company's lifecycle history look like using the currently accepted fundamental data?"

That history may change retrospectively after restatements. Source availability dates remain useful provenance, but the system will not guarantee the exact class an investor would have seen on every historical date. This simplification is accepted for the personal research scope.

## Phase 2C revised-history persistence

The only active history mode is `REVISED_HISTORY`. The adapter reads the currently accepted `v4_ttm_values` row and its exact `v4_ttm_input_quarter` links from the canonical database. Lag4 is matched by company and fiscal sequence; it is valid only across a complete five-snapshot fiscal chain. Ticker is descriptive metadata while `company_id` is the stable replay identity.

`lifecycle_revised_result` stores one row per company, fiscal quarter, lifecycle fingerprint and history mode. It includes raw/public states, status, startup profiles, reason and transition codes, state-machine audit fields, G/M/DeltaM/F evidence, PRE_REVENUE evidence and deterministic source fingerprints. It does not modify the legacy empty `lifecycle_result` table.

The complete target set is calculated and validated before writing. Full rebuild replaces the locked fingerprint inside one savepoint and removes stale universe rows; a filtered refresh replaces only the selected companies' complete histories. A matching logical fingerprint causes no row writes, and parallel fingerprints are retained. Readers require an explicit fingerprint and never fall back from a latest `UNCLASSIFIED` result to an earlier economic state.

## Phase 2D operational activation

Production apply is authorized only when the CLI receives `--apply`, the exact production analysis destination, `--confirm-production`, `--full-universe` and the explicit locked model fingerprint. The canonical source and analysis destination must be the exact non-symlink repository paths. Confirmation cannot authorize a temporary, canonical or market-data destination.

The normal V4 Score production path invokes `refresh_lifecycle_after_score` only after Score has committed and passed its existing integrity checks. The current upstream path does not expose a trustworthy changed-company set, so operational refresh uses `FULL_UNIVERSE_FALLBACK`. The reusable refresh API also supports complete-history replay for an explicit changed-company set when a trustworthy set becomes available.

Lifecycle refresh owns its SQLite transaction. A failed replacement rolls back and preserves the prior revised-history rows; already committed canonical, TTM and Score data are outside that transaction. Failures are written to the Score run summary and raised to the existing CLI/job boundary. The old `lifecycle_result` table remains an untouched schema placeholder; all active Lifecycle V1 writes and readers use `lifecycle_revised_result`.

No scheduler parallel to the existing Fundamentals V4 path, UI or report consumer is added. Lifecycle calculation remains independent of Score values and methodology.
