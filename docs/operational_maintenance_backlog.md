# RawCandle operational maintenance backlog

| Priority | Owner / item | Current disposition / next action |
|---|---|---|
| P0 | EC scheduler pre-write backup retention, G-OPS-04 | Implemented and tested; pruning BLOCKED by explicit historical recovery hold. 24 full images remain; see [policy](g_ops_04_retention_policy.md) and [execution](g_ops_04_cleanup_execution.md). Failed, interrupted and explicitly reused images retain their own recovery obligations. |
| P0 | Historical DC/EC parity and vintage ownership | 19 dates September 21–October 15: 15,269 semantic + 2,033 required-lineage mismatches; six latest dates pass. Resolve accepted historical source/EC vintages and dirty-history propagation under separate authorization before releasing `temp/.ec-backup-retention-hold.json`. No live repair/backfill authorized or performed. |
| P0 | Existing Windows temporary cleanup | Installed maintained script protects the entire EC source-layer family; existing 21:00 task and unrelated rules unchanged. Other age-based families need their own owner review before any wider policy change. |
| P0 | October 25 Fundamentals FULL_WORKFLOW blocker | Separate unresolved operational error; EC skipped with NO_EC_CATCHUP_NEEDED, production publication not invoked. G-OPS-04 does not repair or rerun Fundamentals. |
| P1 | Historical pre-taxonomy rebuild restore reference | August documentation refers to `temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/analysis_before_datacenter_v2_full_rebuild.sqlite`; file is currently absent. Current deployment is ACTIVE/validated and current EC scoped recovery is qualified separately. Reconcile this historical full-taxonomy-reversal promise with its owner; do not substitute a daily EC image or claim it still exists. No G-OPS-04 candidate is that pre-August image. |
| P1 | Failed/manual EC recovery scopes | Review any future RECOVERY_REQUIRED or RETIRE_PENDING receipt explicitly after forward repair/acceptance. Dead process or an old timestamp is insufficient release evidence. |
| P2 | Non-EC storage | Fundamentals generation retention, forecast recovery and weighting migration images retain their existing independent owners. G-OPS-04 grants no cleanup of those groups. |

This RawCandle-owned backlog updates the RawCandle actions described in StockCore's
read-only `docs/g_ops_01_artifact_lifecycle_backlog.md`; that repository is unchanged.
