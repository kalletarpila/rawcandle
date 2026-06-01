# Canonical V3 Ecosystem Entity Model Design

## 1. Purpose

Canonical V3 is introduced because Canonical V2 evolved toward a report-section-oriented schema instead of a clean analytical ecosystem/entity model.

V3 should reset the architecture around persistent canonical facts so that:

- ecosystems, taxonomy, watchlists, entities, windows, signals, events, and metrics are modeled explicitly
- reports become downstream views over DB-backed canonical facts instead of acting as hidden source systems
- Datacenter is treated as the first ecosystem implementation, not as a hard-coded schema exception

The design direction is to preserve V2 as a useful transitional and source-mapping reference while making V3 the clean long-term canonical model.

## 2. Explicit Decisions

- Stop V2 extension builder implementation.
- Keep V2 schema and V2 tables as transitional/reference assets.
- Implement V3 as new `eco_*` tables inside existing `/home/kalle/projects/rawcandle/data/analysis.db`.
- Do not create a separate V3 database for now.
- Persist taxonomy in DB, not CSV.
- Persist watchlists in DB, not TXT.
- Make watchlists ecosystem-specific.
- Support ticker membership in multiple subindustries within the same taxonomy version.
- Make report windows generic: `daily`, `rolling2`, `rolling5`, `rolling30`.
- Make all facts attach to `ecosystem`, `entity`, `signal_date`, and `window` where applicable.

## 3. Conceptual Model

Canonical V3 centers on a generic ecosystem/entity model.

### Core concepts

- `ecosystem`: a named analytical domain such as Datacenter, Space Technology, or Humanoid Robotics
- `taxonomy version`: a versioned classification structure for one ecosystem
- `entity`: any modeled node in the ecosystem hierarchy
- `entity hierarchy / membership`: explicit parent-child and membership relations between entities within a taxonomy version
- `watchlist`: an ecosystem-specific curated list of tracked entities
- `report run`: one canonical materialization run or build attempt
- `report window`: a reusable analytical horizon such as `daily`, `rolling2`, `rolling5`, or `rolling30`
- `entity snapshot`: one entity/window/date state summary
- `metrics`: named numeric or categorical values attached to an entity/window/date grain
- `signals`: observed analytical conditions, triggers, or states
- `relevance`: interpretation or prioritization attached to a signal observation
- `events`: dated ecosystem or entity events that may or may not be tied to report windows
- `coverage`: completeness and availability facts for an entity/window/date
- `quality`: summarized quality facts at a chosen scope

### Entity types

V3 uses these entity types:

- `ECOSYSTEM`
- `LAYER`
- `SUBINDUSTRY`
- `TICKER`

The core modeling rule is that hierarchy is data-driven, not embedded in table names. A Datacenter ticker is therefore just a `TICKER` entity inside one ecosystem and one taxonomy version, not a special-case schema branch.

## 4. Proposed V3 Table Set

The first planned V3 table set uses the `eco_` prefix and separates durable master data from time-bound facts.

### `eco_ecosystem`

- Purpose: master list of supported ecosystems.
- Intended grain: one row per ecosystem.
- Most important columns: `ecosystem_id`, `ecosystem_code`, `ecosystem_name`, `status`, `created_at_utc`.
- Important constraints or uniqueness expectations: unique `ecosystem_code`; stable identifier for all downstream links.
- Type: dimension/master data.

### `eco_taxonomy_version`

- Purpose: versioned taxonomy definition for one ecosystem.
- Intended grain: one row per ecosystem taxonomy version.
- Most important columns: `taxonomy_version_id`, `ecosystem_id`, `version_code`, `version_label`, `source_type`, `source_reference`, `effective_from`, `effective_to`, `is_active`.
- Important constraints or uniqueness expectations: unique `(ecosystem_id, version_code)`; at most one active version per ecosystem if active-state semantics are used.
- Type: dimension/master data.

### `eco_entity`

- Purpose: canonical entity registry across all ecosystems and entity types.
- Intended grain: one row per canonical entity.
- Most important columns: `entity_id`, `ecosystem_id`, `entity_type`, `entity_code`, `entity_name`, `ticker`, `exchange`, `market`, `status`.
- Important constraints or uniqueness expectations: unique entity key within ecosystem, likely via `(ecosystem_id, entity_type, entity_code)`; ticker naming must not assume one exchange format forever.
- Type: dimension/master data.

### `eco_taxonomy_entity_relation`

- Purpose: versioned taxonomy membership and hierarchy mapping between entities.
- Intended grain: one row per taxonomy-versioned parent-child or membership relation.
- Most important columns: `relation_id`, `taxonomy_version_id`, `ecosystem_id`, `parent_entity_id`, `child_entity_id`, `relation_type`, `weight`, `is_primary`, `membership_role`, `valid_from`, `valid_to`.
- Important constraints or uniqueness expectations: unique relation per `(taxonomy_version_id, parent_entity_id, child_entity_id, relation_type)`; must allow multiple subindustry memberships for the same ticker in one taxonomy version.
- Type: dimension/master data.

### `eco_watchlist`

- Purpose: persistent ecosystem-specific watchlist definition.
- Intended grain: one row per watchlist.
- Most important columns: `watchlist_id`, `ecosystem_id`, `watchlist_code`, `watchlist_name`, `status`, `source_type`, `source_reference`, `created_at_utc`.
- Important constraints or uniqueness expectations: unique `(ecosystem_id, watchlist_code)`; multiple watchlists per ecosystem allowed.
- Type: dimension/master data.

### `eco_watchlist_member`

- Purpose: membership of entities in ecosystem-specific watchlists.
- Intended grain: one row per watchlist membership entry.
- Most important columns: `watchlist_member_id`, `watchlist_id`, `entity_id`, `member_status`, `effective_from`, `effective_to`, `added_at_utc`, `removed_at_utc`, `notes`.
- Important constraints or uniqueness expectations: unique active membership per `(watchlist_id, entity_id)`; must support status values such as `ACTIVE` and `INACTIVE`.
- Type: dimension/master data.

### `eco_report_run`

- Purpose: operational metadata for one V3 canonical build or load run.
- Intended grain: one row per run.
- Most important columns: `run_id`, `ecosystem_id`, `taxonomy_version_id`, `signal_date`, `run_type`, `status`, `created_at_utc`, `completed_at_utc`, `warning_count`, `error_count`, `notes`.
- Important constraints or uniqueness expectations: `run_id` unique; multiple runs for the same date should be allowed for repeatability and auditability.
- Type: fact/operational metadata.

### `eco_report_window`

- Purpose: controlled vocabulary for generic report windows.
- Intended grain: one row per window code.
- Most important columns: `window_code`, `window_label`, `window_days`, `is_active`, `sort_order`.
- Important constraints or uniqueness expectations: unique `window_code`; expected seeded values include `daily`, `rolling2`, `rolling5`, `rolling30`.
- Type: dimension/master data.

### `eco_entity_window_snapshot`

- Purpose: one canonical entity/window/date snapshot row for summary state.
- Intended grain: `run_id / signal_date / taxonomy_version_id / window_code / entity_id`.
- Most important columns: `run_id`, `ecosystem_id`, `signal_date`, `taxonomy_version_id`, `window_code`, `entity_id`, `snapshot_status`, `timing_state`, `trend_state`, `summary_state`, `asof_observed_at`.
- Important constraints or uniqueness expectations: unique at the stated grain; should contain only one summary row per entity/window/date/run.
- Type: fact data.

### `eco_entity_metric_value`

- Purpose: flexible storage for named metric values at entity/window/date grain.
- Intended grain: `run_id / signal_date / taxonomy_version_id / window_code / entity_id / metric_name`.
- Most important columns: `run_id`, `ecosystem_id`, `signal_date`, `taxonomy_version_id`, `window_code`, `entity_id`, `metric_name`, `metric_value_num`, `metric_value_text`, `metric_unit`, `value_status`.
- Important constraints or uniqueness expectations: one row per metric name at the stated grain; metric value typing rules must be explicit in later implementation.
- Type: fact data.

### `eco_signal_observation`

- Purpose: observed signals for an entity/window/date, including window-history-derived signals.
- Intended grain: `run_id / signal_date / taxonomy_version_id / window_code / entity_id / signal_name / observed_date`.
- Most important columns: `signal_observation_id`, `run_id`, `ecosystem_id`, `signal_date`, `taxonomy_version_id`, `window_code`, `entity_id`, `signal_name`, `signal_value`, `observed_date`, `source_event_id`, `signal_status`.
- Important constraints or uniqueness expectations: unique observation identity at the stated grain; multiple observed dates within one report window are allowed when materially distinct.
- Type: fact data.

### `eco_signal_relevance`

- Purpose: derived relevance, priority, or interpretive labeling for a signal observation.
- Intended grain: one row per signal observation relevance assignment.
- Most important columns: `signal_relevance_id`, `signal_observation_id`, `relevance_label`, `relevance_score`, `relevance_reason`, `assigned_at_utc`.
- Important constraints or uniqueness expectations: preferably unique per `(signal_observation_id, relevance_label)` or restricted to one current relevance row per signal observation depending on later policy.
- Type: fact data.

### `eco_entity_event`

- Purpose: dated events attached to an entity, regardless of whether they map directly to one report window.
- Intended grain: `run_id / taxonomy_version_id / entity_id / event_date / event_type / source_event_id`.
- Most important columns: `entity_event_id`, `run_id`, `ecosystem_id`, `taxonomy_version_id`, `entity_id`, `event_date`, `event_type`, `source_event_id`, `event_label`, `event_payload_ref`, `event_status`.
- Important constraints or uniqueness expectations: unique at the stated grain; event identity should remain stable when source systems provide a durable event key.
- Type: fact data.

### `eco_entity_coverage`

- Purpose: coverage and completeness status for one entity/window/date grain.
- Intended grain: `run_id / signal_date / taxonomy_version_id / window_code / entity_id`.
- Most important columns: `run_id`, `ecosystem_id`, `signal_date`, `taxonomy_version_id`, `window_code`, `entity_id`, `coverage_status`, `source_row_count`, `missing_component_count`, `coverage_notes`.
- Important constraints or uniqueness expectations: unique at the stated grain; should summarize whether expected upstream components were present.
- Type: fact data.

### `eco_quality_summary`

- Purpose: summarized quality facts at a chosen scope for a run/window/date.
- Intended grain: `run_id / signal_date / taxonomy_version_id / window_code / quality_scope / scope_entity_id`.
- Most important columns: `quality_summary_id`, `run_id`, `ecosystem_id`, `signal_date`, `taxonomy_version_id`, `window_code`, `quality_scope`, `scope_entity_id`, `quality_status`, `issue_count`, `warning_count`, `summary_note`.
- Important constraints or uniqueness expectations: unique at the stated grain; `scope_entity_id` may be nullable for ecosystem-level summaries if later design permits.
- Type: fact data.

## 5. Multi-Ecosystem Support

V3 supports multiple ecosystems by making ecosystem identity a first-class dimension instead of encoding Datacenter into table names or schema branches.

Key model properties:

- all master tables that define business meaning link to `ecosystem_id`
- taxonomy versioning is scoped per ecosystem
- watchlists are scoped per ecosystem
- entities are stored in a generic registry with type-based semantics
- facts can be filtered by ecosystem without needing dedicated Datacenter-only tables

This lets the same canonical model support `datacenter`, `space technology`, `humanoid robotics`, `quantum computing`, `edge computing`, `small modular nuclear`, and `AI inference / memory chips` without renaming tables or duplicating logic by domain.

## 6. Taxonomy DB Model

Taxonomy should move from CSV-backed runtime lookup to DB-persisted canonical master data.

The V3 taxonomy model must support:

- versioned taxonomy per ecosystem via `eco_taxonomy_version`
- generic entity storage via `eco_entity`
- layer/subindustry/ticker hierarchy via `eco_taxonomy_entity_relation`
- multiple subindustry memberships for the same ticker within the same taxonomy version
- optional `weight`
- optional `is_primary`
- optional `membership_role` such as `CORE`, `ADJACENT`, `WATCH_ONLY`, or `OPTIONAL`

Recommended modeling rule:

- treat hierarchy as explicit relations rather than embedding `primary_subindustry` into ticker rows

That approach preserves multi-membership, supports future non-strict hierarchies, and avoids flattening the taxonomy into report-era assumptions.

## 7. Watchlist DB Model

Watchlists should move from TXT-backed runtime lookup to DB-persisted canonical master data plus membership rows.

The V3 watchlist model must support:

- ecosystem-specific watchlists
- multiple watchlists per ecosystem where needed
- membership by entity, starting with ticker entities
- membership status such as `ACTIVE` and `INACTIVE`
- later import from the current Datacenter watchlist TXT file as a migration/import step rather than a runtime source

Current import-source candidate only:

- `/home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt`

This path should be treated as a transitional import source, not as the target state of the canonical model.

## 8. Facts and Grains

The intended fact-table grains are:

- `eco_entity_window_snapshot`: `run_id / signal_date / taxonomy_version_id / window_code / entity_id`
- `eco_entity_metric_value`: `run_id / signal_date / taxonomy_version_id / window_code / entity_id / metric_name`
- `eco_signal_observation`: `run_id / signal_date / taxonomy_version_id / window_code / entity_id / signal_name / observed_date`
- `eco_signal_relevance`: anchored to `signal_observation_id` or an equivalent immutable signal reference grain
- `eco_entity_event`: `run_id / taxonomy_version_id / entity_id / event_date / event_type / source_event_id`
- `eco_entity_coverage`: `run_id / signal_date / taxonomy_version_id / window_code / entity_id`
- `eco_quality_summary`: `run_id / signal_date / taxonomy_version_id / window_code / quality_scope / scope_entity_id`

General grain rules:

- `run_id` preserves operational reproducibility
- `signal_date` preserves canonical reporting date alignment where applicable
- `taxonomy_version_id` preserves classification reproducibility
- `window_code` is used only for windowed facts
- `entity_id` is the default fact attachment point for entity-scoped facts
- separate tables are preferred when grain or semantics differ materially rather than forcing unrelated facts into one wide table

## 9. Relationship to V2

Canonical V2 is not deleted by this design.

V2 remains:

- a transitional schema
- a reference for source mapping and report lineage
- a useful record of how report-visible facts were previously materialized

However:

- V2 extension builders are stopped
- V3 migrations and builders will be new work
- V2 source-data audits remain useful for identifying available upstream sources
- V3 should avoid V2's report-section-table proliferation and instead model reusable canonical facts at ecosystem/entity/window grain

## 10. First Implementation Sequence

The safe staged sequence is:

- `DB-V3-02`: create V3 base dimension schema, no builders
- `DB-V3-03`: import/persist Datacenter taxonomy into V3 tables
- `DB-V3-04`: import/persist Datacenter watchlist into V3 tables
- `DB-V3-05`: implement V3 run/window base builder
- `DB-V3-06`: implement entity coverage builder
- `DB-V3-07`: implement entity snapshot and metric builder pilot for Datacenter
- `DB-V3-08`: implement signal observation/relevance pilot
- `DB-V3-09`: implement event and quality summary pilot
- formatter/CLI/report rendering later
- V2-to-V3 parity/coverage audit later

This sequence preserves low-risk base modeling first, then persistent taxonomy and watchlist state, and only after that windowed fact builders.

## 11. Non-Goals

- no V3 SQL migration in this task
- no table creation in this task
- no builder implementation
- no production DB writes
- no formatter changes
- no scheduler changes
- no dashboard changes
- no V2 deletion

## 12. Open Questions

- What is the exact approved taxonomy import source and format for the first V3 load, given that current taxonomy appears to be CSV-driven and not reliably persisted in `analysis.db`?
- Should taxonomy version identifiers be numeric surrogate IDs, stable text codes, or both?
- Should entity identifiers be surrogate integers, stable text keys, or a hybrid model with both?
- Are ticker membership weights required from day one or only as an optional later extension?
- How should ticker aliases, symbol changes, and exchange suffix variants be modeled?
- Can watchlist membership later include non-ticker entities such as `SUBINDUSTRY` or `LAYER`, or should V3 enforce ticker-only membership?
- Should V3 reuse V2 run identifiers when source lineage overlaps, or should it define fully separate V3 run IDs from the start?
- How should relation typing be constrained in `eco_taxonomy_entity_relation` so that hierarchy edges and softer membership edges can coexist without ambiguity?
- Should `eco_signal_relevance` allow multiple simultaneous relevance labels per observation or only one current canonical relevance result?
- Which quality scopes are mandatory in the first migration, for example ecosystem-level, watchlist-level, and entity-level?

## Notes from Current Audit Findings

The following current-state findings materially affect the V3 design direction:

- current taxonomy data is not reliably persisted in `analysis.db`
- the inspected `dc_ecosystem_membership` table exists but is empty
- taxonomy appears to be loaded from CSV in the current flow
- watchlist source should no longer be a `.txt` file in the V3 target model
- multi-membership must be modeled explicitly rather than collapsed into a single `primary_subindustry`

These findings reinforce the need to move taxonomy and watchlist state into DB-backed canonical master data before building further V3 fact layers.
