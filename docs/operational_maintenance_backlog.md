# RawCandle operational maintenance backlog

| Priority | Owner / item | Current disposition / next action |
|---|---|---|
| P0 | EC scheduler pre-write backup retention, G-OPS-06 | COMPLETE: exact 23-image retirement reclaimed 278,384,205,824 allocated bytes in Linux; one October 24 general Analysis point remains. Historical hold RELEASED with evidence-bound recovery protection. Future accepted EC points supersede earlier registered accepted points; unresolved/failed/reused points require owner review. See [release](g_ops_06_retention_hold_release.md). |
| P1 | Historical DC/EC vintage propagation policy | G-OPS-05 qualified source/publication vintages and closed old rollback obligations; G-OPS-06 reproduced unchanged differences and released the storage hold without recalculation. Any historical mirroring/invalidation policy remains separately authorized work, not a requirement to retain retired whole images. |
| P0 | Existing Windows temporary cleanup | Installed maintained script protects the entire EC source-layer family; existing 21:00 task and unrelated rules unchanged. Other age-based families need their own owner review before any wider policy change. |
| P0 | Fundamentals FULL_WORKFLOW blocker | Still present in the October 26 scheduler outcome; EC skipped with NO_EC_CATCHUP_NEEDED, Fundamentals production publication not invoked. Separate owner follow-up; G-OPS-06 did not repair or rerun it. |
| P1 | Historical pre-taxonomy rebuild restore reference | August documentation refers to `temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/analysis_before_datacenter_v2_full_rebuild.sqlite`; file is currently absent. Current deployment is ACTIVE/validated and current EC scoped recovery is qualified separately. Reconcile this historical full-taxonomy-reversal promise with its owner; do not substitute a daily EC image or claim it still exists. No G-OPS-04 candidate is that pre-August image. |
| P1 | General Analysis replacement / evidence durability | Preserve the qualified October 24 image and G-OPS-05/06 compact bundle. No qualified independent recent full replacement or off-host database recovery is established. A future replacement needs owner qualification and explicit evidence rebinding; missing/changed release evidence blocks pruning. Fixed general point plus one latest accepted EC point is bounded; unresolved failures may add protected images. |
| P1 | Failed/manual EC recovery scopes | Review any future RECOVERY_REQUIRED or RETIRE_PENDING receipt explicitly after forward repair/acceptance. Dead process or an old timestamp is insufficient release evidence. |
| P2 | Non-EC storage | Fundamentals generation retention, forecast recovery and weighting migration images retain their existing independent owners. G-OPS-04 grants no cleanup of those groups. |

This RawCandle-owned backlog updates the RawCandle actions described in StockCore's
read-only `docs/g_ops_01_artifact_lifecycle_backlog.md`; that repository is unchanged.
