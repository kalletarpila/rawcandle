# Fundamental Delta V1 Phase 5C Persistence

## Retired Before Deployment

Phase 5C originally rehearsed persistence version `V4_FUNDAMENTAL_DELTA_REVISED_HISTORY_V1`. It copied Fundamental total/component history plus Lifecycle context and Valuation diagnostic JSON into five wide Delta-owned tables. That layout was never migrated or deployed to production.

Phase 5C.1 measured the layout at approximately 602 MB and selected normalized Alternative D. Phase 5C.2 replaced the unshipped migration definition with `V4_FUNDAMENTAL_DELTA_REVISED_HISTORY_V2`. The production migration path is therefore directly from the current schema with no Delta objects to the additive V2 schema. There is no production V1-to-V2 migration.

The retired objects are:

- `fundamental_delta_revised_meta`
- `fundamental_delta_revised_result`
- `fundamental_delta_revised_component`
- `lifecycle_change_revised_context`
- `valuation_change_revised_diagnostic`
- `idx_fundamental_delta_component_reader`
- `idx_lifecycle_change_current`
- `idx_valuation_change_current`

V2 migration rejects a disposable development database containing these objects with `NEVER_DEPLOYED_DELTA_V1_LAYOUT_REQUIRES_DISPOSABLE_DATABASE_RECREATION`. It does not add production `DROP` statements for a schema production never received.

The active persistence record is `fundamentals_v4_delta_v1_phase5c2_normalized_persistence.md`. Delta remains not production-active; Phase 5D is still a separate authorization and deployment step.
