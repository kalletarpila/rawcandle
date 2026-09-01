# Fundamentals V4 Lifecycle V1 PIT Persistence

Status: `PERSISTENCE_FOUNDATION_IMPLEMENTED_NOT_PRODUCTION_ACTIVE`

Lifecycle model version: `V4_FUNDAMENTAL_LIFECYCLE_V1`

Lifecycle model fingerprint: `db72e072fc2f0d9e3ceb13db1ee4cc92045383a5f44bfb65d21858b80190832f`

Persistence schema version: `V4_LIFECYCLE_PIT_1`

## Time contracts

Fiscal sequence and knowledge time remain separate. Fiscal year and quarter determine canonical order; `period_end` labels the economic period. `knowledge_date` determines when a source version and every result derived from it may become visible in PIT history. A correction is never backdated to period end or original publication.

`PIT` answers what was knowable on an as-of date. `REVISED_HISTORY` applies the latest eligible source versions retrospectively and is stored or returned under a separate replay mode. The two modes cannot collide under the persistence uniqueness contract.

## Versioned quarter input

`LifecycleQuarterVersion` carries stable company, security and quarter identities, fiscal coordinates, period end, knowledge date, source version and fingerprint, canonical precedence, quarterly Revenue, EBIT and FCF, and the instant values needed by the established V4 core-TTM readiness contract.

The service rebuilds current and lag4 TTM evidence from the winning quarterly versions known at each batch date. It does not use calendar subtraction or row offsets. A valid lag4 chain requires all eight canonical fiscal sequences from the lag TTM through the current TTM. The exact four current quarterly Revenue values are retained for PRE_REVENUE evaluation.

The current canonical SQLite adapter opens its source with `mode=ro`. It exposes the currently accepted canonical quarter version. Historical restatement feeds can use the same versioned input API, but reconstructing an authoritative old canonical winner chain from provider archives is not inferred by this phase.

## Knowledge batches

Rows are grouped by company and date. Every winning change on that date is applied before classification. Distinct fiscal quarters are ordered by canonical fiscal sequence and each may contribute one state-machine observation. Duplicate source fingerprints do not contribute another observation.

For multiple versions of the same quarter and date, the greatest explicit `canonical_precedence` wins. Equal highest precedence with different fingerprints is ambiguous and fails closed. Retrieval order, insertion order and SQLite rowid are never tie-breakers. Stable quarter identity cannot change across restatements.

Date-level batching is used because the established canonical availability contract has date precision. Timestamp splitting is deferred until a reliable timestamp contract exists.

## Suffix replay

For every PIT batch:

1. Apply all changed winning quarter versions atomically.
2. Ignore exact source-version repetitions.
3. Find the earliest changed fiscal sequence.
4. Rebuild the as-known TTM observations and replay the state machine in canonical fiscal order.
5. Emit new versions from the earliest changed sequence through the latest known quarter.

The prefix establishes the correct machine state immediately before the suffix. Only suffix results are appended. This allows a corrected raw state to alter later candidates, final states, immediate DISTRESSED entry and DISTRESSED recovery without mutating earlier PIT rows.

## Append-only schema

`ensure_lifecycle_pit_schema()` creates only:

- `lifecycle_persistence_schema`, an idempotent component schema marker;
- `lifecycle_pit_result`, immutable result versions;
- `idx_lifecycle_pit_current`, for latest lookup;
- `idx_lifecycle_pit_asof`, for knowledge-date lookup;
- `idx_lifecycle_pit_quarter_audit`, for fiscal-quarter version audit.

The old `lifecycle_result`, Score tables and canonical tables are not altered. Result identity hashes the batch, company, fiscal sequence, knowledge date, complete source-input fingerprint, lifecycle fingerprint, replay mode and state outcome. A uniqueness constraint independently covers the key semantic identity.

`LifecycleResultRepository.append()` uses plain `INSERT`. A matching existing result is counted as a duplicate after identity comparison; changed inputs append another version. There is no update, delete, replace or delete-then-insert API. The original `generated_at_utc` remains unchanged on an idempotent later run.

For a future production migration, rollback is operational rather than destructive: disable the not-yet-active reader/writer and preserve appended audit rows. Dropping tables is appropriate only for disposable rehearsal databases unless a separately approved production recovery procedure says otherwise.

## Persisted evidence

Each result stores raw and final state, readiness, startup profiles, classification and transition reason codes, missing inputs, last confirmed audit state, candidate and count, all four raw metrics, PRE_REVENUE evidence, source-version chain, batch identity, source-input fingerprint, model identity and replay mode.

For UNCLASSIFIED, `raw_state` is `UNCLASSIFIED`, status is `LIFECYCLE_NOT_READY`, `final_state` is NULL and candidate state is cleared. `last_confirmed_state` is audit history only.

## Read API

`LifecycleResultRepository` provides:

```python
current_pit(company_id, model_fingerprint=...)
as_of_pit(company_id, as_of_date, model_fingerprint=...)
fiscal_quarter_history(company_id, fiscal_year, fiscal_quarter,
                       model_fingerprint=..., replay_mode="PIT")
```

Every query requires an explicit model fingerprint. Current and as-of APIs read only PIT mode and never substitute `last_confirmed_state` for an UNCLASSIFIED public result. Audit history is ordered by knowledge date and deterministic result identity.

## Safe validation interface

The CLI is:

```text
python -m rawcandle.cli.run_fundamentals_v4_lifecycle_pit \
  --source-db /path/to/fundamentals_v4.db \
  [--company-id 123 | --ticker NVDA] \
  [--knowledge-date-from YYYY-MM-DD] \
  [--knowledge-date-to YYYY-MM-DD]
```

It is dry-run by default. Writes require both `--apply` and `--destination-db`. Source and destination must differ, and the RawCandle production analysis path is forbidden in Phase 2B. The source is read-only. A lower date filter retains older source events as replay seed and filters only emitted results; an upper bound excludes genuinely future events.

The summary reports model identity, source-version and computed-result counts, status/class distributions, inserts, duplicate skips, revised versions and errors. No scheduler hook exists.

## Phase 2C boundary

Phase 2C may, only after explicit authorization:

- establish and validate the production canonical-version event feed;
- rehearse authoritative historical PIT coverage and unresolved ambiguity counts;
- back up and migrate the production analysis database;
- run an idempotent production backfill;
- activate current/as-of readers and operational monitoring;
- add scheduler or report integration.

Phase 2C must not change Lifecycle V1 economics or Score V1. UI/report behavior and production activation remain outside Phase 2B.
